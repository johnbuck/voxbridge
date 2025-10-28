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

import logging
import os
import time
from typing import Dict, List, Optional, Callable, AsyncIterator
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
    ):
        """
        Initialize LLM service with provider configuration.

        Args:
            openrouter_api_key: OpenRouter API key (None = read from env)
            local_base_url: Local LLM base URL (None = read from env or default)
            fallback_enabled: Enable fallback to local LLM on failures
            timeout_s: Request timeout in seconds
            max_retries: Max retry attempts (handled by providers)
        """
        # Configuration
        self.openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        self.local_base_url = local_base_url or os.getenv(
            "LOCAL_LLM_BASE_URL", "http://localhost:11434/v1"
        )
        self.fallback_enabled = fallback_enabled or os.getenv(
            "LLM_FALLBACK_ENABLED", "true"
        ).lower() in ("true", "1", "yes")
        self.timeout_s = timeout_s
        self.max_retries = max_retries

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
            logger.warning(
                f"🤖 LLM Service [{session_id[:8]}]: Primary provider failed: {e}"
            )

            # Check if fallback is enabled and available
            if not self.fallback_enabled:
                logger.error(
                    f"🤖 LLM Service [{session_id[:8]}]: Fallback disabled, failing"
                )
                raise

            if primary_provider_type == ProviderType.LOCAL:
                logger.error(
                    f"🤖 LLM Service [{session_id[:8]}]: No fallback for local provider"
                )
                raise

            # Try fallback to local
            fallback_provider = self._providers.get(ProviderType.LOCAL)
            if fallback_provider is None:
                logger.error(
                    f"🤖 LLM Service [{session_id[:8]}]: Fallback provider not available"
                )
                raise LLMError(
                    f"Primary provider failed and fallback is unavailable: {e}"
                ) from e

            logger.info(
                f"🤖 LLM Service [{session_id[:8]}]: Falling back to local LLM"
            )

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
                logger.error(
                    f"🤖 LLM Service [{session_id[:8]}]: Fallback also failed: {fallback_error}"
                )
                raise LLMError(
                    f"Both primary and fallback providers failed. "
                    f"Primary: {e}, Fallback: {fallback_error}"
                ) from fallback_error

        except LLMAuthenticationError:
            # Don't attempt fallback on auth errors
            raise

        except Exception as e:
            # Unexpected errors
            logger.error(
                f"🤖 LLM Service [{session_id[:8]}]: Unexpected error: {e}"
            )
            raise LLMError(f"Unexpected LLM error: {e}") from e

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
        """
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

    Returns:
        LLMService: Shared service instance
    """
    global _llm_service_instance

    if _llm_service_instance is None:
        _llm_service_instance = LLMService()
        logger.info("🤖 LLM Service: Created singleton instance")

    return _llm_service_instance
