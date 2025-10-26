"""
LLM Provider Type Definitions

Common types used across LLM provider implementations.
"""

from typing import Dict, List, Literal, Optional
from dataclasses import dataclass


@dataclass
class LLMMessage:
    """
    A single message in a conversation.

    Attributes:
        role: Message role (system, user, assistant)
        content: Message text content
    """
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMStreamChunk:
    """
    A chunk of streamed LLM response.

    Attributes:
        content: Text content of the chunk
        finish_reason: Reason streaming finished (if applicable)
        usage: Token usage information (if available)
    """
    content: str
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None


@dataclass
class LLMResponse:
    """
    Complete LLM response (non-streaming).

    Attributes:
        content: Full response text
        usage: Token usage statistics
        model: Model used for generation
        finish_reason: Why generation stopped
    """
    content: str
    usage: Optional[Dict[str, int]] = None
    model: Optional[str] = None
    finish_reason: Optional[str] = None


@dataclass
class LLMError(Exception):
    """
    LLM provider error.

    Attributes:
        message: Error message
        provider: Provider name that raised the error
        status_code: HTTP status code (if applicable)
        retryable: Whether the error can be retried
    """
    message: str
    provider: str
    status_code: Optional[int] = None
    retryable: bool = False
