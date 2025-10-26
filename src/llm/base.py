"""
LLM Provider Base Class

Abstract base class for all LLM provider implementations.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional

from src.llm.types import LLMMessage, LLMResponse, LLMStreamChunk


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All providers must implement streaming generation with conversation history support.
    """

    def __init__(self, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize provider.

        Args:
            model: Model identifier (e.g., "anthropic/claude-3.5-sonnet")
            api_key: API key for authentication (optional)
            base_url: Base URL for API (optional, for local LLMs)
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    async def generate_stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """
        Generate streaming response.

        Args:
            messages: Conversation history (system + user messages)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate (optional)

        Yields:
            LLMStreamChunk: Streamed response chunks

        Raises:
            LLMError: On provider errors
        """
        pass

    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Generate complete response (non-streaming).

        Default implementation collects streaming chunks.
        Providers can override for efficiency.

        Args:
            messages: Conversation history
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            LLMResponse: Complete response

        Raises:
            LLMError: On provider errors
        """
        content = ""
        finish_reason = None
        usage = None

        async for chunk in self.generate_stream(messages, temperature, max_tokens):
            content += chunk.content
            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
            if chunk.usage:
                usage = chunk.usage

        return LLMResponse(
            content=content,
            usage=usage,
            model=self.model,
            finish_reason=finish_reason
        )
