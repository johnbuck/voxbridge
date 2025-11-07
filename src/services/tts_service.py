"""
VoxBridge 2.0 Phase 5.4 - TTSService

Purpose: Text-to-Speech abstraction layer for Chatterbox TTS API integration.
Manages TTS synthesis per session with streaming support and health monitoring.

Key Features:
- Multi-session support (track active TTS per session)
- Streaming audio chunks via callback
- HTTP client connection pooling
- Health monitoring (latency tracking, availability)
- Graceful degradation (return empty bytes on failure)
- Session-based cancellation

Design Patterns:
- Connection Pool Pattern: Single HTTP client for all requests
- Observer Pattern: Callback-based audio chunk delivery
- Health Check Pattern: Service availability monitoring
- Metrics Pattern: Per-session latency and throughput tracking
"""

import os
import asyncio
import time
import logging
from typing import Dict, List, Optional, Callable, Any, Awaitable
from dataclasses import dataclass
from enum import Enum
import httpx
import json

from src.types.error_events import ServiceErrorEvent, ServiceErrorType
from src.config.streaming import StreamingConfig, get_streaming_config

logger = logging.getLogger(__name__)

# Configuration from environment variables
CHATTERBOX_URL = os.getenv('CHATTERBOX_URL', 'http://chatterbox-tts:4123')
CHATTERBOX_VOICE_ID = os.getenv('CHATTERBOX_VOICE_ID', 'default')
TTS_TIMEOUT_S = float(os.getenv('TTS_TIMEOUT_S', '60'))
TTS_STREAM_CHUNK_SIZE = int(os.getenv('TTS_STREAM_CHUNK_SIZE', '8192'))
TTS_STREAMING_STRATEGY = os.getenv('TTS_STREAMING_STRATEGY', 'word')
TTS_STREAMING_CHUNK_SIZE = int(os.getenv('TTS_STREAMING_CHUNK_SIZE', '100'))
TTS_STREAMING_BUFFER_SIZE = int(os.getenv('TTS_STREAMING_BUFFER_SIZE', '3'))
TTS_STREAMING_QUALITY = os.getenv('TTS_STREAMING_QUALITY', 'fast')


class TTSStatus(Enum):
    """TTS synthesis status"""
    IDLE = "idle"
    SYNTHESIZING = "synthesizing"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TTSMetrics:
    """
    Metrics for a single TTS synthesis operation.

    Attributes:
        session_id: UUID of the session this synthesis belongs to
        text_length: Length of input text (characters)
        audio_bytes: Total audio bytes generated
        time_to_first_byte_s: Time from request start to first audio byte
        total_duration_s: Total time from request to completion
        voice_id: Voice ID used for synthesis
        success: Whether synthesis completed successfully
        error: Error message if synthesis failed
        timestamp: When synthesis was initiated
    """
    session_id: str
    text_length: int
    audio_bytes: int
    time_to_first_byte_s: float
    total_duration_s: float
    voice_id: str
    success: bool
    error: Optional[str] = None
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class ActiveTTS:
    """
    Represents an active TTS synthesis for a session.

    Attributes:
        session_id: UUID of the session
        text: Text being synthesized
        voice_id: Voice ID being used
        exaggeration: Emotion intensity (Chatterbox parameter)
        cfg_weight: Pace control (Chatterbox parameter)
        temperature: Sampling randomness (Chatterbox parameter)
        language_id: Language code
        status: Current synthesis status
        started_at: When synthesis started
        cancel_event: Event to signal cancellation
        stream_task: Background task for streaming
    """
    session_id: str
    text: str
    voice_id: str
    exaggeration: Optional[float]
    cfg_weight: Optional[float]
    temperature: Optional[float]
    language_id: str
    status: TTSStatus
    started_at: float
    cancel_event: asyncio.Event
    stream_task: Optional[asyncio.Task] = None


class TTSService:
    """
    Text-to-Speech service for Chatterbox API integration.

    This service manages TTS synthesis across multiple sessions with streaming
    support, connection pooling, and health monitoring. It follows the proven
    pattern from webrtc_handler.py but adds session-based routing and metrics.

    Usage:
        tts_service = TTSService()

        # Streaming with callback
        await tts_service.synthesize_speech(
            session_id="abc-123",
            text="Hello world",
            callback=lambda chunk: await websocket.send_bytes(chunk)
        )

        # Buffered (return full audio)
        audio_bytes = await tts_service.synthesize_speech(
            session_id="abc-123",
            text="Hello world"
        )

    Configuration:
        All parameters can be set via environment variables:
        - CHATTERBOX_URL: Chatterbox API URL (default: http://chatterbox-tts:4123)
        - CHATTERBOX_VOICE_ID: Default voice ID (default: default)
        - TTS_TIMEOUT_S: Request timeout in seconds (default: 60)
        - TTS_STREAM_CHUNK_SIZE: Audio chunk size (default: 8192)
        - TTS_STREAMING_STRATEGY: Streaming strategy (default: word)
        - TTS_STREAMING_CHUNK_SIZE: Chunks per buffer (default: 100)
        - TTS_STREAMING_BUFFER_SIZE: Buffer size (default: 3)
        - TTS_STREAMING_QUALITY: Quality preset (default: fast)
    """

    def __init__(
        self,
        chatterbox_url: Optional[str] = None,
        default_voice_id: Optional[str] = None,
        timeout_s: Optional[float] = None,
        chunk_size: Optional[int] = None,
        error_callback: Optional[Callable[[ServiceErrorEvent], Awaitable[None]]] = None,
        streaming_config: Optional[StreamingConfig] = None
    ):
        """
        Initialize TTSService.

        Args:
            chatterbox_url: Override default Chatterbox URL
            default_voice_id: Override default voice ID
            timeout_s: Override default timeout
            chunk_size: Override default chunk size
            error_callback: Optional async callback for error events
            streaming_config: Sentence-level streaming configuration (defaults to global config)
        """
        # Initialize Chatterbox URL and validate format
        base_url = chatterbox_url or CHATTERBOX_URL

        # Strip /v1 suffix if present (backward compatibility)
        if base_url.endswith('/v1'):
            logger.warning(
                f"⚠️ CHATTERBOX_URL should not include '/v1' suffix. "
                f"Got: {base_url}. Stripping '/v1' for compatibility."
            )
            base_url = base_url.rstrip('/v1')

        self.chatterbox_url = base_url
        self.default_voice_id = default_voice_id or CHATTERBOX_VOICE_ID
        self.timeout = timeout_s or TTS_TIMEOUT_S
        self.chunk_size = chunk_size or TTS_STREAM_CHUNK_SIZE
        self.error_callback = error_callback

        # Sentence-level streaming configuration
        self.streaming_config = streaming_config or get_streaming_config()

        # HTTP client (lazy initialized)
        self._client: Optional[httpx.AsyncClient] = None

        # Active TTS sessions
        self._active_sessions: Dict[str, ActiveTTS] = {}

        # Metrics history (limited to last 100 for memory efficiency)
        self._metrics_history: List[TTSMetrics] = []
        self._max_metrics_history = 100

        logger.info(
            f"🔊 TTSService initialized (url={self.chatterbox_url}, voice={self.default_voice_id}, "
            f"streaming={'enabled' if self.streaming_config.enabled else 'disabled'})"
        )

    async def synthesize_speech(
        self,
        session_id: str,
        text: str,
        voice_id: Optional[str] = None,
        exaggeration: Optional[float] = None,
        cfg_weight: Optional[float] = None,
        temperature: Optional[float] = None,
        language_id: str = "en",
        stream: bool = True,
        callback: Optional[Callable[[bytes], None]] = None
    ) -> bytes:
        """
        Synthesize speech from text using Chatterbox TTS API.

        This method supports two modes:
        1. Streaming mode (callback provided): Streams audio chunks to callback as they arrive
        2. Buffered mode (no callback): Returns complete audio as bytes

        Args:
            session_id: UUID of the session requesting TTS
            text: Text to synthesize
            voice_id: Voice ID to use (defaults to service default)
            exaggeration: Emotion intensity (0.25-2.0, default from Chatterbox)
            cfg_weight: Pace control (0.0-1.0, default from Chatterbox)
            temperature: Sampling randomness (0.05-5.0, default from Chatterbox)
            language_id: Language code (default: "en")
            stream: Enable streaming (default: True)
            callback: Optional callback for streaming audio chunks

        Returns:
            bytes: Complete audio (if no callback), or empty bytes (if streaming)

        Raises:
            None: Errors are logged and empty bytes returned (graceful degradation)
        """
        voice_id = voice_id or self.default_voice_id

        logger.info(
            f"🔊 TTS request: session={session_id}, text=\"{text[:50]}...\", voice={voice_id}, "
            f"exaggeration={exaggeration}, cfg_weight={cfg_weight}, temp={temperature}, lang={language_id}"
        )

        # Cancel any existing TTS for this session
        await self.cancel_tts(session_id)

        # Check Chatterbox health first
        if not await self.test_tts_health():
            logger.warning("⚠️ Chatterbox unavailable, cannot synthesize")
            self._record_metrics(
                session_id=session_id,
                text_length=len(text),
                audio_bytes=0,
                time_to_first_byte_s=0.0,
                total_duration_s=0.0,
                voice_id=voice_id,
                success=False,
                error="Service unavailable"
            )
            return b''

        # Create active TTS tracking
        active_tts = ActiveTTS(
            session_id=session_id,
            text=text,
            voice_id=voice_id,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
            temperature=temperature,
            language_id=language_id,
            status=TTSStatus.SYNTHESIZING,
            started_at=time.time(),
            cancel_event=asyncio.Event()
        )
        self._active_sessions[session_id] = active_tts

        try:
            # Stream TTS audio
            audio_bytes = await self._stream_tts(
                session_id=session_id,
                text=text,
                voice_id=voice_id,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                temperature=temperature,
                language_id=language_id,
                callback=callback,
                cancel_event=active_tts.cancel_event
            )

            # Mark as completed
            active_tts.status = TTSStatus.COMPLETED
            logger.info(f"✅ TTS complete: session={session_id}, bytes={len(audio_bytes)}")

            return audio_bytes

        except asyncio.CancelledError:
            logger.info(f"⚠️ TTS cancelled: session={session_id}")
            active_tts.status = TTSStatus.CANCELLED
            return b''

        except Exception as e:
            logger.error(f"❌ TTS error: session={session_id}, error={e}", exc_info=True)
            active_tts.status = TTSStatus.FAILED
            return b''

        finally:
            # Cleanup
            if session_id in self._active_sessions:
                del self._active_sessions[session_id]

    async def get_available_voices(self) -> List[Dict[str, str]]:
        """
        Get list of available voices from Chatterbox.

        Returns:
            List of voice dicts with 'id' and 'name' keys

        Example:
            [
                {"id": "default", "name": "Default Voice"},
                {"id": "voice2", "name": "Voice 2"}
            ]
        """
        try:
            client = await self._ensure_client()
            response = await client.get(f"{self.chatterbox_url}/v1/voices", timeout=5.0)
            response.raise_for_status()

            data = response.json()
            voices = data.get('voices', [])
            logger.info(f"🔊 Available voices: {len(voices)}")
            return voices

        except Exception as e:
            logger.error(f"❌ Failed to fetch voices: {e}", exc_info=True)
            return []

    async def test_tts_health(self) -> bool:
        """
        Check if Chatterbox TTS service is available.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Strip /v1 if present (health endpoint is at root)
            base_url = self.chatterbox_url.rstrip('/v1')
            client = await self._ensure_client()
            response = await client.get(f"{base_url}/health", timeout=5.0)
            return response.status_code == 200

        except Exception as e:
            logger.debug(f"⚠️ Chatterbox health check failed: {e}")
            return False

    async def get_metrics(self, session_id: Optional[str] = None) -> List[TTSMetrics]:
        """
        Get TTS metrics (all or filtered by session).

        Args:
            session_id: Optional session ID to filter by

        Returns:
            List of TTSMetrics objects
        """
        if session_id is None:
            return self._metrics_history.copy()
        else:
            return [m for m in self._metrics_history if m.session_id == session_id]

    async def cancel_tts(self, session_id: str) -> None:
        """
        Cancel active TTS synthesis for a session.

        Args:
            session_id: UUID of the session
        """
        if session_id in self._active_sessions:
            active = self._active_sessions[session_id]
            logger.info(f"⚠️ Cancelling TTS: session={session_id}")

            # Signal cancellation
            active.cancel_event.set()

            # Cancel stream task if exists
            if active.stream_task and not active.stream_task.done():
                active.stream_task.cancel()
                try:
                    await active.stream_task
                except asyncio.CancelledError:
                    pass

            # Update status
            active.status = TTSStatus.CANCELLED

    async def close(self) -> None:
        """
        Close HTTP client and cleanup resources.
        """
        # Cancel all active TTS
        for session_id in list(self._active_sessions.keys()):
            await self.cancel_tts(session_id)

        # Close HTTP client
        if self._client is not None:
            await self._client.aclose()
            self._client = None

        logger.info("🔊 TTSService closed")

    # Internal methods

    async def _ensure_client(self) -> httpx.AsyncClient:
        """
        Lazy initialization of HTTP client with connection pooling.

        Returns:
            Configured httpx.AsyncClient instance
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
        return self._client

    async def _stream_tts(
        self,
        session_id: str,
        text: str,
        voice_id: str,
        exaggeration: Optional[float],
        cfg_weight: Optional[float],
        temperature: Optional[float],
        language_id: str,
        callback: Optional[Callable],
        cancel_event: asyncio.Event
    ) -> bytes:
        """
        Internal: Stream TTS audio from Chatterbox API.

        Implements the proven pattern from webrtc_handler.py with session-based
        cancellation support.

        Args:
            session_id: Session UUID
            text: Text to synthesize
            voice_id: Voice ID
            exaggeration: Voice exaggeration factor
            cfg_weight: CFG weight for voice consistency
            temperature: Sampling temperature
            language_id: Language code (e.g. 'en')
            callback: Optional callback for streaming chunks
            cancel_event: Event to signal cancellation

        Returns:
            Complete audio bytes (empty if callback provided or on error)
        """
        t_start = time.time()
        audio_buffer = bytearray()

        try:
            # Build TTS request with Chatterbox-supported parameters
            tts_data = {
                'input': text,
                'response_format': 'wav',
                'voice': voice_id,
                'language': language_id,
                'streaming_strategy': TTS_STREAMING_STRATEGY,
                'streaming_chunk_size': TTS_STREAMING_CHUNK_SIZE,
                'streaming_buffer_size': TTS_STREAMING_BUFFER_SIZE,
                'streaming_quality': TTS_STREAMING_QUALITY
            }

            # Add Chatterbox-specific TTS parameters if provided
            if exaggeration is not None:
                tts_data['exaggeration'] = exaggeration
            if cfg_weight is not None:
                tts_data['cfg_weight'] = cfg_weight
            if temperature is not None:
                tts_data['temperature'] = temperature

            client = await self._ensure_client()

            # Stream audio from Chatterbox
            async with client.stream(
                'POST',
                f"{self.chatterbox_url}/audio/speech/stream/upload",
                data=tts_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            ) as response:
                response.raise_for_status()

                first_byte = True
                total_bytes = 0
                time_to_first_byte = 0.0

                # Update status to streaming
                if session_id in self._active_sessions:
                    self._active_sessions[session_id].status = TTSStatus.STREAMING

                async for chunk in response.aiter_bytes(chunk_size=self.chunk_size):
                    # Check for cancellation
                    if cancel_event.is_set():
                        logger.info(f"⚠️ TTS stream cancelled: session={session_id}")
                        raise asyncio.CancelledError()

                    # Log first byte latency (critical UX metric)
                    if first_byte:
                        t_first_byte = time.time()
                        time_to_first_byte = t_first_byte - t_start
                        logger.info(f"⏱️ ⭐ LATENCY [TTS first byte]: session={session_id}, latency={time_to_first_byte:.3f}s")
                        first_byte = False

                    # Stream chunk via callback or buffer
                    if callback is not None:
                        await callback(chunk)
                    else:
                        audio_buffer.extend(chunk)

                    total_bytes += len(chunk)

            # Log completion
            t_complete = time.time()
            total_duration = t_complete - t_start
            logger.info(f"✅ TTS streaming complete: session={session_id}, bytes={total_bytes:,}, duration={total_duration:.2f}s")

            # Record metrics
            self._record_metrics(
                session_id=session_id,
                text_length=len(text),
                audio_bytes=total_bytes,
                time_to_first_byte_s=time_to_first_byte,
                total_duration_s=total_duration,
                voice_id=voice_id,                success=True
            )

            return bytes(audio_buffer) if not callback else b''

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}"
            tech_details = f"Chatterbox HTTP error: status={e.response.status_code}, url={self.chatterbox_url}"
            logger.error(f"❌ {tech_details}", exc_info=True)

            self._record_metrics(
                session_id=session_id,
                text_length=len(text),
                audio_bytes=0,
                time_to_first_byte_s=0.0,
                total_duration_s=time.time() - t_start,
                voice_id=voice_id,                success=False,
                error=error_msg
            )

            # Emit error event if callback registered
            if self.error_callback:
                # Determine error type based on status code
                if e.response.status_code == 503:
                    error_type = ServiceErrorType.TTS_SERVICE_UNAVAILABLE
                    user_msg = "Voice synthesis service unavailable. Response will be text-only."
                elif e.response.status_code == 404:
                    error_type = ServiceErrorType.TTS_INVALID_VOICE
                    user_msg = f"Voice '{voice_id}' not found. Using default voice."
                else:
                    error_type = ServiceErrorType.TTS_SYNTHESIS_FAILED
                    user_msg = "Voice synthesis failed. Response will be text-only."

                await self.error_callback(ServiceErrorEvent(
                    service_name="chatterbox",
                    error_type=error_type,
                    user_message=user_msg,
                    technical_details=tech_details,
                    session_id=session_id,
                    severity="warning"
                ))

            return b''

        except httpx.TimeoutException:
            tech_details = f"Chatterbox TTS timeout: session={session_id}, timeout={self.timeout}s"
            logger.error(f"❌ {tech_details}", exc_info=True)

            self._record_metrics(
                session_id=session_id,
                text_length=len(text),
                audio_bytes=0,
                time_to_first_byte_s=0.0,
                total_duration_s=time.time() - t_start,
                voice_id=voice_id,                success=False,
                error="Timeout"
            )

            # Emit error event if callback registered
            if self.error_callback:
                await self.error_callback(ServiceErrorEvent(
                    service_name="chatterbox",
                    error_type=ServiceErrorType.TTS_TIMEOUT,
                    user_message="Voice synthesis timed out. Response will be text-only.",
                    technical_details=tech_details,
                    session_id=session_id,
                    severity="warning",
                    retry_suggested=True
                ))

            return b''

        except asyncio.CancelledError:
            # Re-raise cancellation
            raise

        except Exception as e:
            tech_details = f"TTS stream error: session={session_id}, error={e}"
            logger.error(f"❌ {tech_details}", exc_info=True)

            self._record_metrics(
                session_id=session_id,
                text_length=len(text),
                audio_bytes=0,
                time_to_first_byte_s=0.0,
                total_duration_s=time.time() - t_start,
                voice_id=voice_id,                success=False,
                error=str(e)
            )

            # Emit error event if callback registered
            if self.error_callback:
                await self.error_callback(ServiceErrorEvent(
                    service_name="chatterbox",
                    error_type=ServiceErrorType.TTS_SYNTHESIS_FAILED,
                    user_message="Voice synthesis failed. Response will be text-only.",
                    technical_details=tech_details,
                    session_id=session_id,
                    severity="warning"
                ))

            return b''

    def _record_metrics(
        self,
        session_id: str,
        text_length: int,
        audio_bytes: int,
        time_to_first_byte_s: float,
        total_duration_s: float,
        voice_id: str,
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """
        Record TTS metrics for analytics and monitoring.

        Args:
            session_id: Session UUID
            text_length: Length of input text
            audio_bytes: Total audio bytes generated
            time_to_first_byte_s: Time to first byte
            total_duration_s: Total duration
            voice_id: Voice ID used
            success: Whether synthesis succeeded
            error: Error message if failed
        """
        metrics = TTSMetrics(
            session_id=session_id,
            text_length=text_length,
            audio_bytes=audio_bytes,
            time_to_first_byte_s=time_to_first_byte_s,
            total_duration_s=total_duration_s,
            voice_id=voice_id,
            success=success,
            error=error
        )

        self._metrics_history.append(metrics)

        # Limit history size
        if len(self._metrics_history) > self._max_metrics_history:
            self._metrics_history = self._metrics_history[-self._max_metrics_history:]


# Singleton instance
_tts_service: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    """
    Get singleton TTSService instance.

    Returns:
        Initialized TTSService instance

    Usage:
        tts = get_tts_service()
        audio = await tts.synthesize_speech(session_id="abc", text="Hello")
    """
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service
