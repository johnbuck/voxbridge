"""
Type definitions for LLM provider abstraction layer.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    """A message in the conversation history."""

    role: str = Field(..., description="Message role: 'system', 'user', or 'assistant'")
    content: str = Field(..., description="Message content")

    class Config:
        frozen = True  # Immutable


class LLMRequest(BaseModel):
    """Request to generate LLM response."""

    messages: List[LLMMessage] = Field(..., description="Conversation history")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    model: str = Field(..., description="Model identifier")
    max_tokens: Optional[int] = Field(default=None, ge=1, description="Maximum tokens to generate")

    class Config:
        frozen = True  # Immutable


class LLMError(Exception):
    """Base exception for LLM provider errors."""
    pass


class LLMTimeoutError(LLMError):
    """LLM request timeout error."""
    pass


class LLMRateLimitError(LLMError):
    """LLM rate limit exceeded error."""
    pass


class LLMConnectionError(LLMError):
    """LLM connection/network error."""
    pass


class LLMAuthenticationError(LLMError):
    """LLM authentication error (invalid API key)."""
    pass
