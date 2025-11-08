"""
LLM Service Layer - Provider abstraction with hybrid routing

Business logic for managing LLM interactions in VoxBridge 2.0.
Provides session-based routing, streaming support, health monitoring, and fallback chains.

Design Patterns:
- Factory pattern: LLMProviderFactory for provider instantiation
- Strategy pattern: Provider selection based on agent configuration
- Singleton-like: Shared provider instances per service instance
- Observer pattern: Callback mechanism for streaming chunks
"""

import asyncio
import logging
import os
import time
from typing import Dict, List, Optional, Callable, AsyncIterator, Awaitable
from dataclasses import dataclass
from enum import Enum

from src.llm import (
    LLMProvider,
    LLMProviderFactory,
    LLMMessage,
    LLMRequest,
    LLMError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMConnectionError,
    LLMAuthenticationError,
)
from src.types.error_events import ServiceErrorEvent, ServiceErrorType

logger = logging.getLogger(__name__)


class ProviderType(Enum):
    """Supported LLM provider types"""
    OPENROUTER = "openrouter"
    LOCAL = "local"


@dataclass
class LLMConfig:
    """
    LLM configuration for a session/agent.

    Extracted from agent database model for service layer usage.
    """
    provider: ProviderType
    model: str
    temperature: float
    system_prompt: Optional[str] = None


class LLMService:
    """
    LLM Service for routing and provider management.

    Features:
    - Session-based routing to appropriate LLM provider
    - Streaming support via async iteration or callbacks
    - Health monitoring per provider
    - Fallback chain (primary → backup → local)
    - Shared provider instances for connection reuse

    Environment Variables:
    - OPENROUTER_API_KEY: OpenRouter API key (optional)
    - LOCAL_LLM_BASE_URL: Local LLM endpoint (default: http://localhost:11434/v1)
    - LLM_FALLBACK_ENABLED: Enable fallback to local (default: true)
    - LLM_TIMEOUT_S: Request timeout in seconds (default: 60)
    - LLM_MAX_RETRIES: Max retry attempts (default: 2)
    """

    def __init__(
        self,
        openrouter_api_key: Optional[str] = None,
        local_base_url: Optional[str] = None,
        fallback_enabled: bool = True,
        timeout_s: float = 60.0,
        max_retries: int = 2,
        db_provider_config: Optional[dict] = None,
        error_callback: Optional[Callable[[ServiceErrorEvent], Awaitable[None]]] = None
    ):
        """
        Initialize LLM service with provider configuration.

        Priority for API keys:
        1. Database provider (db_provider_config) - highest priority
        2. Function parameters (openrouter_api_key, local_base_url)
        3. Environment variables (OPENROUTER_API_KEY, LOCAL_LLM_BASE_URL)

        Args:
            openrouter_api_key: OpenRouter API key (None = read from env)
            local_base_url: Local LLM base URL (None = read from env or default)
            fallback_enabled: Enable fallback to local LLM on failures
            timeout_s: Request timeout in seconds
            max_retries: Max retry attempts (handled by providers)
            db_provider_config: Database provider config dict with keys:
                - provider_type: str (openrouter, local, etc.)
                - api_key: str (decrypted API key)
                - base_url: str (API endpoint)
            error_callback: Optional async callback for error events
        """
        # Configuration
        # Priority: db_provider_config > function params > env vars
        if db_provider_config:
            # Use database provider config (highest priority)
            provider_type = db_provider_config.get('provider_type', 'openrouter')
            if provider_type == 'openrouter':
                self.openrouter_api_key = db_provider_config.get('api_key')
                # Still need local_base_url for fallback
                self.local_base_url = local_base_url or os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
                logger.info("🤖 LLM Service: Using database provider config for OpenRouter")
            elif provider_type in ('local', 'ollama', 'vllm'):
                self.local_base_url = db_provider_config.get('base_url', 'http://localhost:11434/v1')
                # Still need openrouter_api_key for fallback
                self.openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
                logger.info(f"🤖 LLM Service: Using database provider config for local LLM ({self.local_base_url})")
            else:
                # Unknown provider type - log warning and fall back to env vars
                logger.warning(f"🤖 LLM Service: Unknown provider type '{provider_type}' in database config, falling back to env vars")
                self.openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
                self.local_base_url = local_base_url or os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
        else:
            # No database config - use function params or env vars
            self.openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
            self.local_base_url = local_base_url or os.getenv(
                "LOCAL_LLM_BASE_URL", "http://localhost:11434/v1"
            )

        self.fallback_enabled = fallback_enabled or os.getenv(
            "LLM_FALLBACK_ENABLED", "true"
        ).lower() in ("true", "1", "yes")
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.error_callback = error_callback

        # Provider cache (shared instances for connection pooling)
        self._providers: Dict[ProviderType, Optional[LLMProvider]] = {}

        # Initialize providers
        self._init_providers()

        logger.info(
            f"🤖 LLM Service: Initialized (fallback={self.fallback_enabled}, "
            f"openrouter={'enabled' if self.openrouter_api_key else 'disabled'}, "
            f"local={self.local_base_url})"
        )

    def _init_providers(self) -> None:
        """
        Initialize available LLM providers.

        Providers are created lazily but availability is determined at startup.
        This allows graceful degradation if some providers are unavailable.
        """
        # OpenRouter provider (optional)
        if self.openrouter_api_key:
            try:
                provider = LLMProviderFactory.create_provider(
                    provider_name="openrouter",
                    api_key=self.openrouter_api_key,
                )
                self._providers[ProviderType.OPENROUTER] = provider
                logger.info("🤖 LLM Service: OpenRouter provider initialized")
            except Exception as e:
                logger.warning(f"🤖 LLM Service: Failed to initialize OpenRouter provider: {e}")
                self._providers[ProviderType.OPENROUTER] = None
        else:
            logger.info("🤖 LLM Service: OpenRouter provider disabled (no API key)")
            self._providers[ProviderType.OPENROUTER] = None

        # Local LLM provider (always attempt to initialize)
        try:
            provider = LLMProviderFactory.create_provider(
                provider_name="local",
                base_url=self.local_base_url,
            )
            self._providers[ProviderType.LOCAL] = provider
            logger.info(f"🤖 LLM Service: Local LLM provider initialized ({self.local_base_url})")
        except Exception as e:
            logger.warning(f"🤖 LLM Service: Failed to initialize Local LLM provider: {e}")
            self._providers[ProviderType.LOCAL] = None

    async def generate_response(
        self,
        session_id: str,
        messages: List[Dict[str, str]],
        config: LLMConfig,
        stream: bool = True,
        callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Generate LLM response with provider routing and streaming support.

        This is the main entry point for LLM generation in VoxBridge 2.0.

        Args:
            session_id: Session UUID for logging/tracking
            messages: Conversation history (list of {role, content} dicts)
            config: LLM configuration (provider, model, temperature, system_prompt)
            stream: Enable streaming response (default: True)
            callback: Optional callback for streaming chunks (sync or async)

        Returns:
            str: Complete LLM response text

        Raises:
            LLMError: Provider unavailable or generation failed
            LLMTimeoutError: Request timeout
            LLMAuthenticationError: Authentication failure
        """
        start_time = time.time()

        logger.info(
            f"🤖 LLM Service [{session_id[:8]}]: Generating response "
            f"(provider={config.provider.value}, model={config.model}, stream={stream})"
        )

        # Convert message dicts to LLMMessage objects
        llm_messages = [
            LLMMessage(role=msg["role"], content=msg["content"])
            for msg in messages
        ]

        # Create LLM request
        request = LLMRequest(
            messages=llm_messages,
            model=config.model,
            temperature=config.temperature,
        )

        # Generate with fallback chain
        try:
            full_response = await self._generate_with_fallback(
                session_id=session_id,
                request=request,
                config=config,
                stream=stream,
                callback=callback,
            )

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                f"🤖 LLM Service [{session_id[:8]}]: Response complete "
                f"({len(full_response)} chars, {elapsed_ms:.0f}ms)"
            )

            return full_response

        except LLMAuthenticationError as e:
            # Don't retry on auth errors - fail fast
            logger.error(f"🤖 LLM Service [{session_id[:8]}]: Authentication failed: {e}")
            raise

        except LLMError as e:
            # All LLM errors are already logged by providers
            logger.error(f"🤖 LLM Service [{session_id[:8]}]: Generation failed: {e}")
            raise

    async def _generate_with_fallback(
        self,
        session_id: str,
        request: LLMRequest,
        config: LLMConfig,
        stream: bool,
        callback: Optional[Callable[[str], None]],
    ) -> str:
        """
        Generate response with fallback chain.

        Fallback logic:
        1. Try primary provider (from config)
        2. If fallback enabled and primary fails:
           - If primary was OpenRouter → try local
           - If primary was local → fail (no fallback)

        Args:
            session_id: Session UUID
            request: LLM request
            config: LLM configuration
            stream: Enable streaming
            callback: Optional streaming callback

        Returns:
            str: Complete response text

        Raises:
            LLMError: All providers failed or unavailable
        """
        primary_provider_type = config.provider

        # Get primary provider
        provider = self._providers.get(primary_provider_type)
        if provider is None:
            raise LLMError(
                f"Primary LLM provider '{primary_provider_type.value}' is not available. "
                f"Check configuration and logs."
            )

        # Try primary provider
        try:
            logger.info(
                f"🤖 LLM Service [{session_id[:8]}]: Using primary provider "
                f"({primary_provider_type.value})"
            )

            return await self._generate_with_provider(
                provider=provider,
                request=request,
                stream=stream,
                callback=callback,
            )

        except (LLMTimeoutError, LLMRateLimitError, LLMConnectionError) as e:
            # Transient errors - consider fallback
            error_type_str = type(e).__name__
            tech_details = f"Primary provider failed: {error_type_str}: {e}"
            logger.warning(
                f"🤖 LLM Service [{session_id[:8]}]: {tech_details}"
            )

            # Determine error type for event
            if isinstance(e, LLMRateLimitError):
                svc_error_type = ServiceErrorType.LLM_RATE_LIMITED
            elif isinstance(e, LLMTimeoutError):
                svc_error_type = ServiceErrorType.LLM_TIMEOUT
            else:
                svc_error_type = ServiceErrorType.LLM_PROVIDER_FAILED

            # Check if fallback is enabled and available
            if not self.fallback_enabled:
                logger.error(
                    f"🤖 LLM Service [{session_id[:8]}]: Fallback disabled, failing"
                )

                # Emit error event (no fallback available)
                if self.error_callback:
                    await self.error_callback(ServiceErrorEvent(
                        service_name="llm_provider",
                        error_type=svc_error_type,
                        user_message="AI response failed. Please try again.",
                        technical_details=f"{tech_details} (fallback disabled)",
                        session_id=session_id,
                        severity="error",
                        retry_suggested=True
                    ))

                raise

            if primary_provider_type == ProviderType.LOCAL:
                logger.error(
                    f"🤖 LLM Service [{session_id[:8]}]: No fallback for local provider"
                )

                # Emit error event (no fallback available for local)
                if self.error_callback:
                    await self.error_callback(ServiceErrorEvent(
                        service_name="llm_provider",
                        error_type=svc_error_type,
                        user_message="Local AI failed. Please try again.",
                        technical_details=f"{tech_details} (no fallback for local provider)",
                        session_id=session_id,
                        severity="error",
                        retry_suggested=True
                    ))

                raise

            # Try fallback to local
            fallback_provider = self._providers.get(ProviderType.LOCAL)
            if fallback_provider is None:
                logger.error(
                    f"🤖 LLM Service [{session_id[:8]}]: Fallback provider not available"
                )

                # Emit error event (fallback not available)
                if self.error_callback:
                    await self.error_callback(ServiceErrorEvent(
                        service_name="llm_provider",
                        error_type=svc_error_type,
                        user_message="AI response failed. Please try again.",
                        technical_details=f"{tech_details} (fallback provider not available)",
                        session_id=session_id,
                        severity="error",
                        retry_suggested=True
                    ))

                raise LLMError(
                    f"Primary provider failed and fallback is unavailable: {e}"
                ) from e

            logger.info(
                f"🤖 LLM Service [{session_id[:8]}]: Falling back to local LLM"
            )

            # Emit warning event (fallback triggered)
            if self.error_callback:
                await self.error_callback(ServiceErrorEvent(
                    service_name="llm_provider",
                    error_type=ServiceErrorType.LLM_FALLBACK_TRIGGERED,
                    user_message="Primary AI unavailable. Using local AI as fallback.",
                    technical_details=f"{tech_details} (falling back to local LLM)",
                    session_id=session_id,
                    severity="warning",
                    retry_suggested=False
                ))

            try:
                # Update request model to local model (if needed)
                # Note: Assumes local LLM has a reasonable default model
                fallback_request = LLMRequest(
                    messages=request.messages,
                    model=request.model,  # Keep same model name, local LLM will handle
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )

                return await self._generate_with_provider(
                    provider=fallback_provider,
                    request=fallback_request,
                    stream=stream,
                    callback=callback,
                )

            except Exception as fallback_error:
                tech_details_fallback = f"Both primary and fallback providers failed. Primary: {e}, Fallback: {fallback_error}"
                logger.error(
                    f"🤖 LLM Service [{session_id[:8]}]: Fallback also failed: {fallback_error}"
                )

                # Emit error event (both providers failed)
                if self.error_callback:
                    await self.error_callback(ServiceErrorEvent(
                        service_name="llm_provider",
                        error_type=ServiceErrorType.LLM_PROVIDER_FAILED,
                        user_message="AI response failed. Both primary and fallback providers unavailable.",
                        technical_details=tech_details_fallback,
                        session_id=session_id,
                        severity="critical",
                        retry_suggested=True
                    ))

                raise LLMError(tech_details_fallback) from fallback_error

        except LLMAuthenticationError as e:
            # Don't attempt fallback on auth errors
            tech_details = f"LLM authentication failed: {e}"
            logger.error(f"🤖 LLM Service [{session_id[:8]}]: {tech_details}")

            # Emit error event (authentication failed)
            if self.error_callback:
                await self.error_callback(ServiceErrorEvent(
                    service_name="llm_provider",
                    error_type=ServiceErrorType.LLM_AUTHENTICATION_FAILED,
                    user_message="AI authentication failed. Please check API key configuration.",
                    technical_details=tech_details,
                    session_id=session_id,
                    severity="error",
                    retry_suggested=False
                ))

            raise

        except Exception as e:
            # Unexpected errors
            tech_details = f"Unexpected LLM error: {e}"
            logger.error(
                f"🤖 LLM Service [{session_id[:8]}]: {tech_details}"
            )

            # Emit error event (unexpected error)
            if self.error_callback:
                await self.error_callback(ServiceErrorEvent(
                    service_name="llm_provider",
                    error_type=ServiceErrorType.LLM_INVALID_RESPONSE,
                    user_message="AI response failed due to unexpected error.",
                    technical_details=tech_details,
                    session_id=session_id,
                    severity="error",
                    retry_suggested=True
                ))

            raise LLMError(tech_details) from e

    async def _generate_with_provider(
        self,
        provider: LLMProvider,
        request: LLMRequest,
        stream: bool,
        callback: Optional[Callable[[str], None]],
    ) -> str:
        """
        Generate response with specific provider.

        Handles both streaming and non-streaming modes.

        Args:
            provider: LLM provider instance
            request: LLM request
            stream: Enable streaming
            callback: Optional streaming callback

        Returns:
            str: Complete response text

        Raises:
            LLMTimeoutError: Service layer timeout (90s)
        """
        SERVICE_TIMEOUT = 90.0  # Service layer timeout (higher than provider's 60s)

        try:
            async with asyncio.timeout(SERVICE_TIMEOUT):
                if not stream:
                    # Non-streaming mode: Collect all chunks
                    chunks = []
                    async for chunk in provider.generate_stream(request):
                        chunks.append(chunk)
                    return "".join(chunks)

                # Streaming mode: Yield chunks to callback
                chunks = []
                async for chunk in provider.generate_stream(request):
                    chunks.append(chunk)

                    if callback:
                        # Call callback with chunk (supports both sync and async callbacks)
                        if hasattr(callback, "__call__"):
                            try:
                                result = callback(chunk)
                                # If callback is async, await it
                                if hasattr(result, "__await__"):
                                    await result
                            except Exception as e:
                                logger.warning(
                                    f"🤖 LLM Service: Callback error (continuing): {e}"
                                )

                return "".join(chunks)

        except asyncio.TimeoutError:
            logger.error(f"🤖 LLM Service: ⏱️ Service layer timeout after {SERVICE_TIMEOUT}s")
            raise LLMTimeoutError(f"LLM service timeout: No response in {SERVICE_TIMEOUT}s")

    async def get_provider_status(self) -> Dict[str, bool]:
        """
        Get health status of all providers.

        Returns:
            Dict[str, bool]: Provider name -> health status mapping
        """
        status = {}

        for provider_type, provider in self._providers.items():
            if provider is None:
                status[provider_type.value] = False
                continue

            try:
                is_healthy = await provider.health_check()
                status[provider_type.value] = is_healthy
            except Exception as e:
                logger.warning(
                    f"🤖 LLM Service: Health check failed for {provider_type.value}: {e}"
                )
                status[provider_type.value] = False

        logger.info(f"🤖 LLM Service: Provider status: {status}")
        return status

    async def test_provider_health(self, provider_type: ProviderType) -> bool:
        """
        Test specific provider health.

        Args:
            provider_type: Provider type to test

        Returns:
            bool: True if provider is healthy
        """
        provider = self._providers.get(provider_type)
        if provider is None:
            logger.warning(
                f"🤖 LLM Service: Provider {provider_type.value} not initialized"
            )
            return False

        try:
            is_healthy = await provider.health_check()
            logger.info(
                f"🤖 LLM Service: Provider {provider_type.value} health: {is_healthy}"
            )
            return is_healthy
        except Exception as e:
            logger.error(
                f"🤖 LLM Service: Health check failed for {provider_type.value}: {e}"
            )
            return False

    async def close(self):
        """
        Close all provider connections.

        Should be called during service shutdown.
        """
        logger.info("🤖 LLM Service: Closing provider connections")

        for provider_type, provider in self._providers.items():
            if provider is not None:
                try:
                    await provider.close()
                    logger.info(f"🤖 LLM Service: Closed {provider_type.value} provider")
                except Exception as e:
                    logger.warning(
                        f"🤖 LLM Service: Error closing {provider_type.value} provider: {e}"
                    )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Singleton instance (optional - can also be instantiated per-request)
_llm_service_instance: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """
    Get singleton LLM service instance.

    This ensures provider connections are reused across requests for efficiency.

    NOTE: For per-agent database provider configs, use get_llm_service_for_agent() instead.

    Returns:
        LLMService: Shared service instance
    """
    global _llm_service_instance

    if _llm_service_instance is None:
        _llm_service_instance = LLMService()
        logger.info("🤖 LLM Service: Created singleton instance")

    return _llm_service_instance


async def get_llm_service_for_agent(agent) -> LLMService:
    """
    Create LLM service instance with database provider config from agent.

    Priority for LLM provider configuration:
    1. Database provider (agent.llm_provider_id) - highest priority
    2. Environment variables (OPENROUTER_API_KEY, LOCAL_LLM_BASE_URL)

    Args:
        agent: Agent database model instance with llm_provider_id relationship

    Returns:
        LLMService: Service instance configured with agent's database provider or env vars

    Usage:
        # In Discord plugin initialize()
        llm_service = await get_llm_service_for_agent(self.agent)
    """
    # Import here to avoid circular dependency
    from src.services.llm_provider_service import LLMProviderService

    db_provider_config = None

    # Check if agent has llm_provider_id set
    if agent.llm_provider_id:
        try:
            # Fetch provider from database
            db_provider = await LLMProviderService.get_provider(agent.llm_provider_id)

            if db_provider and db_provider.is_active:
                # Decrypt API key
                decrypted_api_key = LLMProviderService._decrypt_api_key(
                    db_provider.api_key_encrypted
                )

                # Build config dict
                db_provider_config = {
                    'provider_type': db_provider.provider_type or 'openrouter',
                    'api_key': decrypted_api_key,
                    'base_url': db_provider.base_url,
                }

                logger.info(
                    f"🤖 LLM Service: Using database provider '{db_provider.name}' "
                    f"for agent '{agent.name}' (provider_type={db_provider.provider_type})"
                )
            else:
                logger.warning(
                    f"🤖 LLM Service: Agent '{agent.name}' has llm_provider_id but provider is "
                    f"{'inactive' if db_provider else 'not found'}, falling back to env vars"
                )
        except Exception as e:
            logger.error(
                f"🤖 LLM Service: Failed to fetch database provider for agent '{agent.name}': {e}, "
                f"falling back to env vars"
            )
    else:
        logger.info(
            f"🤖 LLM Service: Agent '{agent.name}' has no llm_provider_id, using env vars"
        )

    # Create LLM service with database config (or None to fall back to env vars)
    return LLMService(db_provider_config=db_provider_config)


async def get_global_provider_status() -> Dict[str, bool]:
    """
    Get global LLM provider status checking BOTH database and environment variables.

    This provides a comprehensive health check that reports True if ANY source has
    a valid API key (database OR env vars), unlike get_provider_status() which only
    checks the specific instance configuration.

    Returns:
        Dict[str, bool]: Provider status with True if available from ANY source
            - 'openrouter': True if OpenRouter API key in database OR env vars
            - 'local': True if Local LLM base URL in database OR env vars
            - 'database': True if ANY active database providers exist
            - 'env': True if ANY env var providers configured
    """
    from src.services.llm_provider_service import LLMProviderService

    status = {
        'openrouter': False,
        'local': False,
        'database': False,
        'env': False
    }

    # Check environment variables
    env_openrouter_key = os.getenv("OPENROUTER_API_KEY")
    env_local_url = os.getenv("LOCAL_LLM_BASE_URL")

    if env_openrouter_key:
        status['env'] = True
        status['openrouter'] = True
        logger.info("🤖 LLM Global Status: OpenRouter available via env vars")

    if env_local_url:
        status['env'] = True
        status['local'] = True
        logger.info(f"🤖 LLM Global Status: Local LLM available via env vars ({env_local_url})")

    # Check database providers
    try:
        db_providers = await LLMProviderService.get_all_providers()
        active_providers = [p for p in db_providers if p.is_active]

        if active_providers:
            status['database'] = True
            for provider in active_providers:
                provider_type = provider.provider_type or 'openrouter'
                if provider_type in status:
                    status[provider_type] = True
                    logger.info(
                        f"🤖 LLM Global Status: {provider.name} ({provider_type}) "
                        f"available via database"
                    )
    except Exception as e:
        logger.warning(f"🤖 LLM Global Status: Failed to check database providers: {e}")

    # Summary log
    logger.info(
        f"🤖 LLM Global Status: openrouter={status['openrouter']}, "
        f"local={status['local']}, database={status['database']}, env={status['env']}"
    )

    return status
