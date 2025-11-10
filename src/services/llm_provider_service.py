"""
LLM Provider Service Layer

Business logic for managing LLM providers in VoxBridge 2.0.
Provides CRUD operations with API key encryption and model fetching.

Phase 6.5.4: LLM Provider Management System
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import LLMProvider
from src.database.session import get_db_session
from src.plugins.encryption import PluginEncryption, PluginEncryptionError

logger = logging.getLogger(__name__)


class LLMProviderService:
    """Service for managing LLM providers"""

    # Register 'llm_provider' as a plugin type with sensitive fields
    # This allows us to reuse the existing PluginEncryption system
    @classmethod
    def _ensure_encryption_registered(cls):
        """Register API key as sensitive field for llm_provider plugin type"""
        if 'llm_provider' not in PluginEncryption.SENSITIVE_FIELDS:
            PluginEncryption.register_sensitive_fields('llm_provider', {'api_key'})

    @classmethod
    def _encrypt_api_key(cls, api_key: Optional[str]) -> Optional[str]:
        """
        Encrypt API key using PluginEncryption.

        Args:
            api_key: Plain API key or None

        Returns:
            Encrypted API key or None
        """
        if not api_key:
            return None

        cls._ensure_encryption_registered()

        try:
            # Use PluginEncryption to encrypt the config
            encrypted_config = PluginEncryption.encrypt_config(
                'llm_provider',
                {'api_key': api_key}
            )
            return encrypted_config.get('api_key')
        except PluginEncryptionError as e:
            logger.warning(f"⚠️ Could not encrypt API key: {e}")
            # Fall back to unencrypted if encryption fails
            return api_key

    @classmethod
    def _decrypt_api_key(cls, encrypted_api_key: Optional[str]) -> Optional[str]:
        """
        Decrypt API key using PluginEncryption.

        Args:
            encrypted_api_key: Encrypted API key or None

        Returns:
            Decrypted API key or None
        """
        if not encrypted_api_key:
            return None

        cls._ensure_encryption_registered()

        try:
            # Use PluginEncryption to decrypt the config
            decrypted_config = PluginEncryption.decrypt_config(
                'llm_provider',
                {'api_key': encrypted_api_key}
            )
            return decrypted_config.get('api_key')
        except PluginEncryptionError as e:
            logger.warning(f"⚠️ Could not decrypt API key: {e}")
            # Return as-is if decryption fails
            return encrypted_api_key

    @staticmethod
    async def create_provider(
        name: str,
        base_url: str,
        api_key: Optional[str] = None,
        provider_type: Optional[str] = None,
        default_model: Optional[str] = None,
        is_active: bool = True,
    ) -> LLMProvider:
        """
        Create a new LLM provider.

        Args:
            name: Provider display name
            base_url: OpenAI-compatible API base URL (e.g., https://openrouter.ai/api/v1)
            api_key: API key for authentication (will be encrypted)
            provider_type: Provider type (openrouter, ollama, openai, vllm, custom)
            default_model: Default model identifier
            is_active: Whether provider is active

        Returns:
            Created LLMProvider instance

        Raises:
            ValueError: If validation fails
        """
        # Validation
        if not name or len(name) > 255:
            raise ValueError("Provider name must be 1-255 characters")
        if not base_url or len(base_url) > 512:
            raise ValueError("Base URL must be 1-512 characters")
        if provider_type and len(provider_type) > 50:
            raise ValueError("Provider type must be 1-50 characters")
        if default_model and len(default_model) > 255:
            raise ValueError("Default model must be 1-255 characters")

        # Encrypt API key before storing
        encrypted_api_key = LLMProviderService._encrypt_api_key(api_key)

        async with get_db_session() as session:
            provider = LLMProvider(
                name=name,
                base_url=base_url,
                api_key_encrypted=encrypted_api_key,
                provider_type=provider_type,
                default_model=default_model,
                is_active=is_active,
                models=[],  # Empty models list initially
            )

            session.add(provider)
            await session.commit()
            await session.refresh(provider)

        logger.info(f"✅ Created LLM provider: {provider.name} (ID: {provider.id})")
        return provider

    @staticmethod
    async def get_all_providers() -> List[LLMProvider]:
        """
        Get all LLM providers.

        Returns:
            List of all LLMProvider instances
        """
        async with get_db_session() as session:
            result = await session.execute(select(LLMProvider).order_by(LLMProvider.created_at))
            providers = result.scalars().all()
            return list(providers)

    @staticmethod
    async def get_provider(provider_id: UUID) -> Optional[LLMProvider]:
        """
        Get LLM provider by ID.

        Args:
            provider_id: Provider UUID

        Returns:
            LLMProvider instance or None if not found
        """
        async with get_db_session() as session:
            result = await session.execute(select(LLMProvider).where(LLMProvider.id == provider_id))
            provider = result.scalar_one_or_none()
            return provider

    @staticmethod
    async def update_provider(
        provider_id: UUID,
        name: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        provider_type: Optional[str] = None,
        default_model: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[LLMProvider]:
        """
        Update LLM provider fields.

        Args:
            provider_id: Provider UUID
            name: New provider name (optional)
            base_url: New base URL (optional)
            api_key: New API key (optional, will be re-encrypted)
            provider_type: New provider type (optional)
            default_model: New default model (optional)
            is_active: New active status (optional)

        Returns:
            Updated LLMProvider instance or None if not found

        Raises:
            ValueError: If validation fails
        """
        async with get_db_session() as session:
            result = await session.execute(select(LLMProvider).where(LLMProvider.id == provider_id))
            provider = result.scalar_one_or_none()

            if not provider:
                return None

            # Update fields with validation
            if name is not None:
                if not name or len(name) > 255:
                    raise ValueError("Provider name must be 1-255 characters")
                provider.name = name

            if base_url is not None:
                if not base_url or len(base_url) > 512:
                    raise ValueError("Base URL must be 1-512 characters")
                provider.base_url = base_url

            if api_key is not None:
                # Re-encrypt API key if changed
                encrypted_api_key = LLMProviderService._encrypt_api_key(api_key)
                provider.api_key_encrypted = encrypted_api_key

            if provider_type is not None:
                if len(provider_type) > 50:
                    raise ValueError("Provider type must be 1-50 characters")
                provider.provider_type = provider_type

            if default_model is not None:
                if len(default_model) > 255:
                    raise ValueError("Default model must be 1-255 characters")
                provider.default_model = default_model

            if is_active is not None:
                provider.is_active = is_active

            await session.commit()
            await session.refresh(provider)

        logger.info(f"✅ Updated LLM provider: {provider.name} (ID: {provider.id})")
        return provider

    @staticmethod
    async def delete_provider(provider_id: UUID) -> bool:
        """
        Delete LLM provider by ID.

        Args:
            provider_id: Provider UUID

        Returns:
            True if deleted, False if not found
        """
        async with get_db_session() as session:
            result = await session.execute(select(LLMProvider).where(LLMProvider.id == provider_id))
            provider = result.scalar_one_or_none()

            if not provider:
                return False

            provider_name = provider.name
            await session.delete(provider)
            await session.commit()

        logger.info(f"✅ Deleted LLM provider: {provider_name} (ID: {provider_id})")
        return True

    @staticmethod
    async def test_connection(provider_id: UUID) -> Dict[str, Any]:
        """
        Test connection to LLM provider by calling /v1/models endpoint.

        Args:
            provider_id: Provider UUID

        Returns:
            Dict with test results:
            {
                "success": bool,
                "models_count": int (optional),
                "error": str (optional),
                "response_time_ms": float (optional)
            }
        """
        provider = await LLMProviderService.get_provider(provider_id)

        if not provider:
            return {
                "success": False,
                "error": f"Provider with ID {provider_id} not found"
            }

        # Decrypt API key for testing
        decrypted_api_key = LLMProviderService._decrypt_api_key(provider.api_key_encrypted)

        # Build request headers
        headers = {}
        if decrypted_api_key:
            headers["Authorization"] = f"Bearer {decrypted_api_key}"

        # Test connection to /v1/models endpoint
        models_url = f"{provider.base_url.rstrip('/')}/models"

        try:
            import time
            start_time = time.time()

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(models_url, headers=headers)

            response_time_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                models = data.get("data", [])

                logger.info(f"✅ Connection test successful for provider '{provider.name}': {len(models)} models found")

                return {
                    "success": True,
                    "models_count": len(models),
                    "response_time_ms": response_time_ms,
                }
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.warning(f"❌ Connection test failed for provider '{provider.name}': {error_msg}")

                return {
                    "success": False,
                    "error": error_msg,
                    "response_time_ms": response_time_ms,
                }

        except httpx.TimeoutException:
            logger.warning(f"❌ Connection test timeout for provider '{provider.name}'")
            return {
                "success": False,
                "error": "Connection timeout (10s)"
            }
        except Exception as e:
            logger.warning(f"❌ Connection test error for provider '{provider.name}': {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    async def fetch_models(provider_id: UUID) -> Dict[str, Any]:
        """
        Fetch available models from LLM provider and update database.

        Args:
            provider_id: Provider UUID

        Returns:
            Dict with fetch results:
            {
                "success": bool,
                "models_count": int (optional),
                "models": List[str] (optional),
                "error": str (optional)
            }
        """
        provider = await LLMProviderService.get_provider(provider_id)

        if not provider:
            return {
                "success": False,
                "error": f"Provider with ID {provider_id} not found"
            }

        # Decrypt API key for fetching
        decrypted_api_key = LLMProviderService._decrypt_api_key(provider.api_key_encrypted)

        # Build request headers
        headers = {}
        if decrypted_api_key:
            headers["Authorization"] = f"Bearer {decrypted_api_key}"

        # Fetch models from /v1/models endpoint
        models_url = f"{provider.base_url.rstrip('/')}/models"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(models_url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                models_data = data.get("data", [])

                # Extract model IDs
                model_ids = [model.get("id") for model in models_data if model.get("id")]

                # Update provider with fetched models
                async with get_db_session() as session:
                    result = await session.execute(select(LLMProvider).where(LLMProvider.id == provider_id))
                    provider = result.scalar_one_or_none()

                    if provider:
                        provider.models = model_ids
                        await session.commit()

                logger.info(f"✅ Fetched {len(model_ids)} models for provider '{provider.name}'")

                return {
                    "success": True,
                    "models_count": len(model_ids),
                    "models": model_ids,
                }
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.warning(f"❌ Model fetch failed for provider '{provider.name}': {error_msg}")

                return {
                    "success": False,
                    "error": error_msg,
                }

        except httpx.TimeoutException:
            logger.warning(f"❌ Model fetch timeout for provider '{provider.name}'")
            return {
                "success": False,
                "error": "Connection timeout (10s)"
            }
        except Exception as e:
            logger.warning(f"❌ Model fetch error for provider '{provider.name}': {e}")
            return {
                "success": False,
                "error": str(e)
            }
