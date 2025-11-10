"""
Factory for creating LLM provider instances.

Supports dynamic provider selection based on configuration or runtime parameters.
"""

import logging
import os
from typing import Optional

from src.llm.base import LLMProvider
from src.llm.openrouter import OpenRouterProvider
from src.llm.local_llm import LocalLLMProvider

logger = logging.getLogger(__name__)


class LLMProviderFactory:
    """
    Factory for creating LLM provider instances.

    Supports:
    - 'openrouter': OpenRouter.ai (requires OPENROUTER_API_KEY)
    - 'local': Local OpenAI-compatible LLM (requires LOCAL_LLM_BASE_URL)
    """

    @staticmethod
    def create_provider(
        provider_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> LLMProvider:
        """
        Create LLM provider instance.

        Args:
            provider_name: Provider name ('openrouter' or 'local')
            api_key: API key (or None to read from environment)
            base_url: Base URL (for local LLM or custom OpenRouter endpoint)

        Returns:
            LLMProvider: Initialized provider instance

        Raises:
            ValueError: Invalid provider name or missing configuration
        """
        provider_name = provider_name.lower().strip()

        if provider_name == "openrouter":
            # Get API key from parameter or environment
            api_key = api_key or os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError(
                    "OpenRouter API key not found. "
                    "Set OPENROUTER_API_KEY environment variable or pass api_key parameter."
                )

            logger.info("🤖 LLM Factory: Creating OpenRouter provider")
            return OpenRouterProvider(api_key=api_key, base_url=base_url)

        elif provider_name == "local":
            # Get base URL from parameter or environment
            base_url = base_url or os.getenv("LOCAL_LLM_BASE_URL")
            if not base_url:
                # Default to Ollama's standard endpoint
                base_url = "http://localhost:11434/v1"
                logger.warning(
                    f"🤖 LLM Factory: LOCAL_LLM_BASE_URL not set, using default: {base_url}"
                )

            logger.info(f"🤖 LLM Factory: Creating Local LLM provider (base_url={base_url})")
            return LocalLLMProvider(base_url=base_url, api_key=api_key)

        else:
            raise ValueError(
                f"Unknown LLM provider: '{provider_name}'. "
                f"Supported providers: 'openrouter', 'local'"
            )

    @staticmethod
    def create_from_agent_config(
        llm_provider: str,
        llm_model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> tuple[LLMProvider, str]:
        """
        Create provider from agent configuration.

        This is a convenience method for creating providers from database agent records.

        Args:
            llm_provider: Provider name from agent.llm_provider
            llm_model: Model name from agent.llm_model
            api_key: Optional API key override
            base_url: Optional base URL override

        Returns:
            tuple: (LLMProvider instance, model name)

        Raises:
            ValueError: Invalid configuration
        """
        provider = LLMProviderFactory.create_provider(
            provider_name=llm_provider,
            api_key=api_key,
            base_url=base_url,
        )

        return provider, llm_model
