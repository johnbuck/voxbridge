"""
LLM Provider Factory

Creates appropriate LLM provider instances based on agent configuration.
"""

import logging
import os
from typing import Optional

from src.database.models import Agent
from src.llm.base import LLMProvider
from src.llm.openrouter import OpenRouterProvider
from src.llm.local_llm import LocalLLMProvider
from src.llm.types import LLMError

logger = logging.getLogger(__name__)


class LLMProviderFactory:
    """Factory for creating LLM provider instances"""

    @staticmethod
    def create_provider(agent: Agent) -> LLMProvider:
        """
        Create appropriate LLM provider for an agent.

        Args:
            agent: Agent model with LLM configuration

        Returns:
            LLMProvider: Configured provider instance

        Raises:
            LLMError: If provider cannot be created
        """
        provider_type = agent.llm_provider.lower()

        try:
            if provider_type == "openrouter":
                api_key = os.getenv("OPENROUTER_API_KEY")
                if not api_key:
                    raise LLMError(
                        message="OPENROUTER_API_KEY not configured",
                        provider="openrouter",
                        retryable=False
                    )

                logger.info(f"🤖 Creating OpenRouter provider for model: {agent.llm_model}")
                return OpenRouterProvider(
                    model=agent.llm_model,
                    api_key=api_key
                )

            elif provider_type == "local":
                base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
                api_key = os.getenv("LOCAL_LLM_API_KEY")  # Optional for local

                logger.info(f"🏠 Creating Local LLM provider for model: {agent.llm_model} at {base_url}")
                return LocalLLMProvider(
                    model=agent.llm_model,
                    base_url=base_url,
                    api_key=api_key
                )

            else:
                raise LLMError(
                    message=f"Unknown LLM provider: {provider_type}. Supported: openrouter, local",
                    provider=provider_type,
                    retryable=False
                )

        except Exception as e:
            if isinstance(e, LLMError):
                raise
            raise LLMError(
                message=f"Failed to create LLM provider: {e}",
                provider=provider_type,
                retryable=False
            )
