"""
VoxBridge Error Event System - Phase 1

Purpose: Standardized error event schema for service-to-frontend error propagation.
All backend services (STT, TTS, LLM) emit ServiceErrorEvent objects when errors occur.
These are broadcast via WebSocket to the frontend for user-friendly error handling.

Key Features:
- Typed error categories (ServiceErrorType enum)
- User-friendly messages (for frontend display)
- Technical details (for server logs)
- Session context tracking
- Severity levels (warning, error, critical)
- Retry suggestions

Design Pattern: Observer Pattern - Services emit events, WebSocket handler broadcasts to clients
"""

from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field


class ServiceErrorType(str, Enum):
    """
    Enumeration of all possible service error types.

    Categories:
    - STT errors: WhisperX connection and transcription failures
    - TTS errors: Chatterbox synthesis and availability failures
    - LLM errors: Provider failures, rate limits, invalid responses
    """

    # STT (WhisperX) errors
    STT_CONNECTION_FAILED = "stt_connection_failed"
    STT_TRANSCRIPTION_FAILED = "stt_transcription_failed"
    STT_TIMEOUT = "stt_timeout"
    STT_WEBSOCKET_CLOSED = "stt_websocket_closed"

    # TTS (Chatterbox) errors
    TTS_SYNTHESIS_FAILED = "tts_synthesis_failed"
    TTS_SERVICE_UNAVAILABLE = "tts_service_unavailable"
    TTS_TIMEOUT = "tts_timeout"
    TTS_INVALID_VOICE = "tts_invalid_voice"

    # LLM Provider errors
    LLM_PROVIDER_FAILED = "llm_provider_failed"
    LLM_RATE_LIMITED = "llm_rate_limited"
    LLM_INVALID_RESPONSE = "llm_invalid_response"
    LLM_AUTHENTICATION_FAILED = "llm_authentication_failed"
    LLM_TIMEOUT = "llm_timeout"
    LLM_FALLBACK_TRIGGERED = "llm_fallback_triggered"


class ServiceErrorEvent(BaseModel):
    """
    Standardized error event emitted by backend services.

    Attributes:
        event_type: Always "service_error" for frontend routing
        service_name: Which service encountered the error ("whisperx", "chatterbox", "llm_provider")
        error_type: Specific error category (see ServiceErrorType)
        user_message: Human-readable message for frontend display
        technical_details: Detailed error info for server logs and debugging
        session_id: Optional session UUID if error is session-specific
        severity: Error severity level ("warning", "error", "critical")
        retry_suggested: Whether user should retry the operation
        timestamp: When the error occurred (auto-set by Pydantic)

    Example:
        ```python
        error_event = ServiceErrorEvent(
            service_name="whisperx",
            error_type=ServiceErrorType.STT_CONNECTION_FAILED,
            user_message="Speech recognition service unavailable. Please try again.",
            technical_details="Failed to connect to ws://whisperx:4901: Connection refused",
            session_id="550e8400-e29b-41d4-a716-446655440000",
            severity="error",
            retry_suggested=True
        )
        ```
    """

    event_type: Literal["service_error"] = "service_error"
    service_name: str = Field(
        ...,
        description="Service that encountered the error",
        examples=["whisperx", "chatterbox", "llm_provider"]
    )
    error_type: ServiceErrorType = Field(
        ...,
        description="Specific error category"
    )
    user_message: str = Field(
        ...,
        description="User-friendly error message for frontend display",
        min_length=1,
        max_length=500
    )
    technical_details: str = Field(
        ...,
        description="Technical error details for server logs",
        min_length=1,
        max_length=2000
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session UUID if error is session-specific"
    )
    severity: str = Field(
        default="error",
        description="Error severity level",
        pattern="^(warning|error|critical)$"
    )
    retry_suggested: bool = Field(
        default=False,
        description="Whether user should retry the operation"
    )

    class Config:
        """Pydantic config"""
        use_enum_values = True  # Serialize enums as strings
        json_schema_extra = {
            "example": {
                "event_type": "service_error",
                "service_name": "whisperx",
                "error_type": "stt_connection_failed",
                "user_message": "Speech recognition service unavailable. Please try again.",
                "technical_details": "Failed to connect to ws://whisperx:4901: Connection refused",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "severity": "error",
                "retry_suggested": True
            }
        }
