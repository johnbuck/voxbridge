"""
LLM Provider Abstraction Layer for VoxBridge 2.0

This package provides a unified interface for interacting with different LLM providers
(OpenRouter, Local LLMs via OpenAI-compatible APIs) with streaming support.
"""

from src.llm.base import LLMProvider
from src.llm.factory import LLMProviderFactory
from src.llm.types import (
    LLMMessage,
    LLMRequest,
    LLMError,
    LLMTimeoutError,
    LLMRateLimitError,
)

__all__ = [
    "LLMProvider",
    "LLMProviderFactory",
    "LLMMessage",
    "LLMRequest",
    "LLMError",
    "LLMTimeoutError",
    "LLMRateLimitError",
]
