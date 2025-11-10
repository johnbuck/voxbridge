"""
Abstract base class for LLM providers.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from src.llm.types import LLMRequest


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All LLM providers must implement streaming generation and health checks.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize LLM provider.

        Args:
            api_key: API key for authentication (if required)
            base_url: Base URL for API endpoint (for local/custom deployments)
        """
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Generate streaming response from LLM.

        This method must yield text chunks as they arrive from the LLM without buffering.
        Each chunk should be yielded immediately for low-latency streaming.

        Args:
            request: LLMRequest with messages, temperature, model, etc.

        Yields:
            str: Text chunks as they arrive from LLM

        Raises:
            LLMTimeoutError: Request timeout (first token or inter-token)
            LLMRateLimitError: Rate limit exceeded
            LLMConnectionError: Network/connection error
            LLMAuthenticationError: Authentication failure
            LLMError: Other LLM errors
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if provider is available and responding.

        This should be a lightweight check (e.g., GET /health or list models).

        Returns:
            bool: True if provider is healthy, False otherwise
        """
        pass

    @property
    def provider_name(self) -> str:
        """Return provider name (for logging)."""
        return self.__class__.__name__.replace("Provider", "").lower()
