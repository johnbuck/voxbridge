"""
System Settings API Routes (VoxBridge 2.0 Phase 2)

Endpoints for managing global system configuration.

Current Settings:
- embedding_config: Global embedding provider configuration
  {
    "provider": "azure" | "local",
    "azure_api_key": "...",  # Encrypted (TODO)
    "azure_endpoint": "https://...",
    "azure_deployment": "text-embedding-3-large",
    "model": "sentence-transformers/all-mpnet-base-v2",
    "dims": 768
  }

NOTE: These endpoints will be restricted to admin-only access in a future phase.
"""

import os
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.sql import func

from src.database.models import SystemSettings
from src.database.session import get_db_session
from src.config.logging_config import get_logger
from src.services.memory_service import get_embedding_model_status
from src.utils.encryption import encrypt_api_key, decrypt_api_key, is_encryption_configured

logger = get_logger(__name__)

router = APIRouter(prefix="/api/system-settings", tags=["system-settings"])


# Request/Response Models
class EmbeddingConfigRequest(BaseModel):
    """Request model for updating embedding configuration."""
    provider: str = Field(..., description="Embedding provider: 'azure' or 'local'")

    # Azure settings
    azure_api_key: Optional[str] = Field(None, description="Azure OpenAI API key")
    azure_endpoint: Optional[str] = Field(None, description="Azure OpenAI endpoint URL")
    azure_deployment: Optional[str] = Field(None, description="Azure deployment name")
    azure_api_version: Optional[str] = Field(None, description="Azure API version")

    # Local settings
    local_model: Optional[str] = Field(None, description="Local embedding model name")
    local_dims: Optional[int] = Field(None, description="Local embedding dimensions")


class EmbeddingConfigResponse(BaseModel):
    """Response model for embedding configuration."""
    source: str = Field(..., description="Config source: 'database' or 'environment'")
    config: dict = Field(..., description="Embedding configuration")


@router.get("/embedding-config", response_model=EmbeddingConfigResponse)
async def get_embedding_config():
    """
    Get global embedding configuration.

    Priority:
    1. Database (system_settings table)
    2. Environment variables

    Returns:
        EmbeddingConfigResponse with source and config
    """
    try:
        async with get_db_session() as db:
            # Check database first
            result = await db.execute(
                select(SystemSettings).where(SystemSettings.setting_key == "embedding_config")
            )
            setting = result.scalar_one_or_none()

            if setting:
                logger.info("📊 Returning embedding config from database")
                return EmbeddingConfigResponse(
                    source="database",
                    config=setting.setting_value
                )

            # Fall back to environment variables
            logger.info("🌍 Returning embedding config from environment variables")
            env_config = {
                "provider": os.getenv("EMBEDDING_PROVIDER", "local"),
            }

            # Add provider-specific config
            if env_config["provider"] == "azure":
                env_config.update({
                    "azure_endpoint": os.getenv("AZURE_EMBEDDING_ENDPOINT"),
                    "azure_deployment": os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"),
                    "azure_api_version": os.getenv("AZURE_EMBEDDING_API_VERSION", "2024-12-01-preview"),
                })
            else:  # local
                env_config.update({
                    "model": os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"),
                    "dims": int(os.getenv("LOCAL_EMBEDDING_DIMS", "768"))
                })

            return EmbeddingConfigResponse(
                source="environment",
                config=env_config
            )

    except Exception as e:
        logger.error(f"❌ Failed to get embedding config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get embedding config: {str(e)}")


@router.put("/embedding-config")
async def update_embedding_config(request: EmbeddingConfigRequest):
    """
    Update global embedding configuration.

    Stores config in database (highest priority).
    Changes take effect on next MemoryService initialization.

    Args:
        request: EmbeddingConfigRequest with provider and settings

    Returns:
        Updated configuration
    """
    try:
        # Validate provider
        if request.provider not in ['azure', 'local']:
            raise HTTPException(status_code=400, detail="Provider must be 'azure' or 'local'")

        # Build config dict
        config_value = {"provider": request.provider}

        if request.provider == 'azure':
            # Validate Azure credentials
            if not request.azure_api_key or not request.azure_endpoint:
                raise HTTPException(
                    status_code=400,
                    detail="Azure provider requires azure_api_key and azure_endpoint"
                )

            # Encrypt Azure API key before storing
            encrypted_key = encrypt_api_key(request.azure_api_key)
            if not is_encryption_configured():
                logger.warning("⚠️ ENCRYPTION_KEY not set - Azure API key stored without encryption")

            config_value.update({
                "azure_api_key": encrypted_key,
                "azure_endpoint": request.azure_endpoint,
                "azure_deployment": request.azure_deployment or "text-embedding-3-large",
                "azure_api_version": request.azure_api_version or "2024-12-01-preview",
            })
            logger.info(f"💾 Saving Azure embedding config to database: {request.azure_endpoint}")

        else:  # local
            config_value.update({
                "model": request.local_model or "sentence-transformers/all-mpnet-base-v2",
                "dims": request.local_dims or 768
            })
            logger.info(f"💾 Saving local embedding config to database: {config_value['model']}")

        # Update or insert in database
        async with get_db_session() as db:
            result = await db.execute(
                select(SystemSettings).where(SystemSettings.setting_key == "embedding_config")
            )
            setting = result.scalar_one_or_none()

            if setting:
                # Update existing
                setting.setting_value = config_value
                setting.updated_at = func.now()
                logger.info("✏️ Updated existing embedding config in database")
            else:
                # Create new
                setting = SystemSettings(
                    setting_key="embedding_config",
                    setting_value=config_value
                )
                db.add(setting)
                logger.info("➕ Created new embedding config in database")

            await db.commit()
            await db.refresh(setting)

            return {
                "status": "updated",
                "config": setting.setting_value,
                "updated_at": setting.updated_at.isoformat()
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to update embedding config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update embedding config: {str(e)}")


@router.post("/embedding-config/reset")
async def reset_embedding_config():
    """
    Reset embedding config to environment variable defaults.

    Deletes database config, causing fallback to .env settings.

    Returns:
        Environment variable configuration
    """
    try:
        async with get_db_session() as db:
            # Delete database config
            await db.execute(
                delete(SystemSettings).where(SystemSettings.setting_key == "embedding_config")
            )
            await db.commit()
            logger.info("🔄 Reset embedding config to environment defaults (deleted database config)")

        # Return environment defaults
        env_config = {
            "provider": os.getenv("EMBEDDING_PROVIDER", "local"),
        }

        if env_config["provider"] == "azure":
            env_config.update({
                "azure_endpoint": os.getenv("AZURE_EMBEDDING_ENDPOINT"),
                "azure_deployment": os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"),
                "azure_api_version": os.getenv("AZURE_EMBEDDING_API_VERSION", "2024-12-01-preview"),
            })
        else:  # local
            env_config.update({
                "model": os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"),
                "dims": int(os.getenv("LOCAL_EMBEDDING_DIMS", "768"))
            })

        return {
            "status": "reset",
            "config": env_config
        }

    except Exception as e:
        logger.error(f"❌ Failed to reset embedding config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset embedding config: {str(e)}")


@router.get("/embedding-model-status")
async def get_embedding_model_cache_status(model: Optional[str] = None):
    """
    Get embedding model download/cache status.

    Args:
        model: Optional specific model to check (e.g., "BAAI/bge-large-en-v1.5")
               If not provided, uses the currently configured model.

    Returns cache status, size, file count for local models.
    Azure models return "API-based, no cache needed" message.

    Returns:
        {
            "provider": "local" | "azure",
            "model": "sentence-transformers/all-mpnet-base-v2",
            "status": {
                "is_cached": true,
                "cache_size_mb": 420.5,
                "cache_location": "/home/appuser/.cache/huggingface/...",
                "last_modified": "2025-11-22T12:34:56",
                "files_count": 15
            }
        }
    """
    try:
        # If specific model requested, check its cache status directly
        if model:
            logger.info(f"📦 Checking cache status for specific model: {model}")
            model_status = await get_embedding_model_status(model)
            return {
                "provider": "local",
                "model": model,
                "status": model_status,
                "source": "query_parameter"
            }

        # Otherwise, get current embedding config
        async with get_db_session() as db:
            result = await db.execute(
                select(SystemSettings).where(SystemSettings.setting_key == "embedding_config")
            )
            setting = result.scalar_one_or_none()

            if setting:
                config = setting.setting_value
                provider = config.get('provider', 'local')
                source = "database"
            else:
                # Use environment defaults
                provider = os.getenv("EMBEDDING_PROVIDER", "local")
                config = {
                    "provider": provider,
                    "model": os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")
                }
                source = "environment"

        # Handle Azure provider (no local cache)
        if provider == "azure":
            return {
                "provider": "azure",
                "model": "text-embedding-3-large",
                "status": {
                    "is_cached": False,
                    "message": "Azure embeddings are API-based, no local cache required"
                },
                "source": source
            }

        # Handle local provider (check cache)
        model_name = config.get("model", "sentence-transformers/all-mpnet-base-v2")
        model_status = await get_embedding_model_status(model_name)

        return {
            "provider": "local",
            "model": model_name,
            "status": model_status,
            "source": source
        }

    except Exception as e:
        logger.error(f"❌ Failed to get model cache status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get model cache status: {str(e)}")


@router.post("/embedding-model/download")
async def download_embedding_model():
    """
    Trigger download of the configured embedding model.

    This endpoint initializes the embedding model, which triggers HuggingFace
    to download it if not already cached. The download happens asynchronously
    in the background.

    Returns:
        {
            "status": "downloading" | "already_cached",
            "model": "sentence-transformers/all-mpnet-base-v2",
            "message": "..."
        }
    """
    try:
        # Get current embedding config
        async with get_db_session() as db:
            result = await db.execute(
                select(SystemSettings).where(SystemSettings.setting_key == "embedding_config")
            )
            setting = result.scalar_one_or_none()

            if setting:
                config = setting.setting_value
                provider = config.get('provider', 'local')
            else:
                # Use environment defaults
                provider = os.getenv("EMBEDDING_PROVIDER", "local")
                config = {
                    "provider": provider,
                    "model": os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")
                }

        # Only download for local provider
        if provider != "local":
            return {
                "status": "skipped",
                "model": None,
                "message": "Azure provider does not require model download"
            }

        model_name = config.get("model", "sentence-transformers/all-mpnet-base-v2")

        # Check if already cached
        model_status = await get_embedding_model_status(model_name)
        if model_status.get("is_cached"):
            logger.info(f"📦 Model {model_name} already cached")
            return {
                "status": "already_cached",
                "model": model_name,
                "message": f"Model {model_name} is already downloaded"
            }

        # Trigger download by initializing SentenceTransformer
        logger.info(f"⬇️ Starting download for model: {model_name}")

        # Import here to avoid circular dependencies
        from sentence_transformers import SentenceTransformer

        # This will trigger download if not cached
        # Run in executor to avoid blocking the event loop
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: SentenceTransformer(model_name)
        )

        logger.info(f"✅ Model {model_name} downloaded successfully")

        return {
            "status": "downloaded",
            "model": model_name,
            "message": f"Model {model_name} downloaded successfully"
        }

    except Exception as e:
        logger.error(f"❌ Failed to download embedding model: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download model: {str(e)}")


@router.post("/embedding-model/cleanup")
async def cleanup_embedding_models():
    """
    Delete all cached embedding models except the currently configured one.

    This helps manage disk space when experimenting with different models.
    Only affects local provider models (Azure models are API-based and don't cache).

    Returns:
        {
            "status": "cleaned" | "skipped",
            "models_deleted": ["model1", "model2"],
            "space_reclaimed_mb": 1234.56,
            "current_model": "sentence-transformers/all-mpnet-base-v2"
        }
    """
    try:
        # Get current embedding config
        async with get_db_session() as db:
            result = await db.execute(
                select(SystemSettings).where(SystemSettings.setting_key == "embedding_config")
            )
            setting = result.scalar_one_or_none()

            if setting:
                config = setting.setting_value
                provider = config.get('provider', 'local')
                current_model = config.get('model', 'sentence-transformers/all-mpnet-base-v2')
            else:
                # Use environment defaults
                provider = os.getenv("EMBEDDING_PROVIDER", "local")
                current_model = os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")

        # Only cleanup for local provider
        if provider != "local":
            return {
                "status": "skipped",
                "models_deleted": [],
                "space_reclaimed_mb": 0,
                "current_model": None,
                "message": "Azure provider does not cache models locally"
            }

        # Scan cache and delete unused models
        from huggingface_hub import scan_cache_dir

        cache_info = scan_cache_dir()
        models_deleted = []
        space_reclaimed = 0

        for repo in cache_info.repos:
            # Skip the current model
            if repo.repo_id == current_model:
                logger.info(f"✅ Keeping current model: {current_model}")
                continue

            # Delete this model
            logger.info(f"🗑️ Deleting cached model: {repo.repo_id} ({repo.size_on_disk / (1024 * 1024):.2f} MB)")

            # Collect all revision hashes for this repo
            revision_hashes = [rev.commit_hash for rev in repo.revisions]

            # Use delete_revisions strategy with actual revision hashes
            delete_strategy = cache_info.delete_revisions(*revision_hashes)
            delete_strategy.execute()

            models_deleted.append(repo.repo_id)
            space_reclaimed += repo.size_on_disk

        space_reclaimed_mb = round(space_reclaimed / (1024 * 1024), 2)

        logger.info(f"✅ Cleanup complete: Deleted {len(models_deleted)} models, reclaimed {space_reclaimed_mb} MB")

        return {
            "status": "cleaned",
            "models_deleted": models_deleted,
            "space_reclaimed_mb": space_reclaimed_mb,
            "current_model": current_model
        }

    except Exception as e:
        logger.error(f"❌ Failed to cleanup embedding models: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup models: {str(e)}")


# Admin Memory Policy Endpoints (VoxBridge 2.0 Phase 2 Extension)
class AdminMemoryPolicyRequest(BaseModel):
    """Request model for updating admin memory policy."""
    allow_agent_specific_memory_globally: bool = Field(
        ...,
        description="When true, allows agent-specific memories. When false, forces all memories to global scope."
    )


class AdminMemoryPolicyResponse(BaseModel):
    """Response model for admin memory policy."""
    source: str = Field(..., description="Config source: 'database' or 'environment'")
    policy: dict = Field(..., description="Admin memory policy configuration")


@router.get("/admin-memory-policy", response_model=AdminMemoryPolicyResponse)
async def get_admin_memory_policy():
    """
    Get admin-level memory policy.

    This controls the THREE-TIER HIERARCHY for agent-specific memory:
    1. Admin Global Policy (this setting) - Highest priority
    2. Per-Agent Default (Agent.memory_scope) - Only if admin allows
    3. User Restriction (User.allow_agent_specific_memory) - Can further restrict

    Priority:
    1. Database (system_settings table)
    2. Environment variables (ADMIN_ALLOW_AGENT_SPECIFIC_MEMORY)
    3. Hardcoded default (true)

    Returns:
        AdminMemoryPolicyResponse with source and policy
    """
    try:
        async with get_db_session() as db:
            # Check database first
            result = await db.execute(
                select(SystemSettings).where(SystemSettings.setting_key == "admin_memory_policy")
            )
            setting = result.scalar_one_or_none()

            if setting:
                logger.info("📊 Returning admin memory policy from database")
                return AdminMemoryPolicyResponse(
                    source="database",
                    policy=setting.setting_value
                )

            # Fall back to environment variables
            logger.info("🌍 Returning admin memory policy from environment variables")
            env_policy = {
                "allow_agent_specific_memory_globally": os.getenv(
                    "ADMIN_ALLOW_AGENT_SPECIFIC_MEMORY",
                    "true"
                ).lower() == "true"
            }

            return AdminMemoryPolicyResponse(
                source="environment",
                policy=env_policy
            )

    except Exception as e:
        logger.error(f"❌ Failed to get admin memory policy: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get admin memory policy: {str(e)}")


@router.put("/admin-memory-policy")
async def update_admin_memory_policy(request: AdminMemoryPolicyRequest):
    """
    Update admin-level memory policy.

    Stores policy in database (highest priority).

    BEHAVIOR:
    - When true: Allows agent-specific memories (current behavior)
    - When false: Forces ALL memories to global scope system-wide

    IMPORTANT: This is an ENFORCED policy that users cannot override.
    - If false, user and agent settings are ignored
    - If true, per-agent and per-user settings can apply

    Args:
        request: AdminMemoryPolicyRequest with allow_agent_specific_memory_globally

    Returns:
        Updated policy configuration
    """
    try:
        policy_value = {
            "allow_agent_specific_memory_globally": request.allow_agent_specific_memory_globally
        }

        logger.info(
            f"💾 Saving admin memory policy to database: "
            f"allow_agent_specific_memory_globally={request.allow_agent_specific_memory_globally}"
        )

        # Update or insert in database
        async with get_db_session() as db:
            result = await db.execute(
                select(SystemSettings).where(SystemSettings.setting_key == "admin_memory_policy")
            )
            setting = result.scalar_one_or_none()

            if setting:
                # Update existing
                setting.setting_value = policy_value
                setting.updated_at = func.now()
                logger.info("✏️ Updated existing admin memory policy in database")
            else:
                # Create new
                setting = SystemSettings(
                    setting_key="admin_memory_policy",
                    setting_value=policy_value
                )
                db.add(setting)
                logger.info("➕ Created new admin memory policy in database")

            await db.commit()
            await db.refresh(setting)

            return {
                "status": "updated",
                "policy": setting.setting_value,
                "updated_at": setting.updated_at.isoformat()
            }

    except Exception as e:
        logger.error(f"❌ Failed to update admin memory policy: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update admin memory policy: {str(e)}")


@router.post("/admin-memory-policy/reset")
async def reset_admin_memory_policy():
    """
    Reset admin memory policy to environment variable defaults.

    Deletes database policy, causing fallback to environment/hardcoded defaults.

    Returns:
        Environment variable/default policy
    """
    try:
        async with get_db_session() as db:
            # Delete database policy
            await db.execute(
                delete(SystemSettings).where(SystemSettings.setting_key == "admin_memory_policy")
            )
            await db.commit()
            logger.info("🔄 Reset admin memory policy to environment defaults (deleted database config)")

        # Return environment defaults
        env_policy = {
            "allow_agent_specific_memory_globally": os.getenv(
                "ADMIN_ALLOW_AGENT_SPECIFIC_MEMORY",
                "true"
            ).lower() == "true"
        }

        return {
            "status": "reset",
            "policy": env_policy
        }

    except Exception as e:
        logger.error(f"❌ Failed to reset admin memory policy: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset admin memory policy: {str(e)}")
