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

            # TODO: Encrypt azure_api_key before storing
            config_value.update({
                "azure_api_key": request.azure_api_key,
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
