"""
VoxBridge 2.0 Phase 5.2 - STTService

Purpose: Speech-to-Text abstraction layer for WhisperX WebSocket communication.
Manages STT connections per session with automatic reconnection and health monitoring.

Key Features:
- Multi-session support (Dict[session_id, WhisperXConnection])
- Auto-reconnect with exponential backoff
- Connection pooling per session
- Graceful degradation (empty transcript on failure)
- Health monitoring (latency tracking, connection status)
- Async callback pattern for transcription results

Design Patterns:
- Connection Pool Pattern: Per-session WebSocket connections
- Retry Pattern: Exponential backoff with max attempts
- Observer Pattern: Callback-based transcription delivery
- Health Check Pattern: Connection status monitoring
"""

import os
import asyncio
import time
import logging
from typing import Dict, Optional, Callable, Any, Awaitable
from dataclasses import dataclass
from enum import Enum
import websockets
import json

from src.types.error_events import ServiceErrorEvent, ServiceErrorType

logger = logging.getLogger(__name__)

# Configuration from environment variables
WHISPER_SERVER_URL = os.getenv('WHISPER_SERVER_URL', 'ws://whisperx:4901')
WHISPER_RECONNECT_MAX_RETRIES = int(os.getenv('WHISPER_RECONNECT_MAX_RETRIES', '5'))
WHISPER_RECONNECT_BACKOFF = float(os.getenv('WHISPER_RECONNECT_BACKOFF', '2.0'))
WHISPER_TIMEOUT_S = float(os.getenv('WHISPER_TIMEOUT_S', '30.0'))
WHISPER_LANGUAGE = os.getenv('WHISPER_LANGUAGE', 'en')


class ConnectionStatus(Enum):
    """WhisperX WebSocket connection status"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class WhisperXConnection:
    """
    Represents a single WhisperX WebSocket connection for a session.

    Attributes:
        session_id: UUID of the session this connection belongs to
        websocket: WebSocket client protocol instance (None when disconnected)
        status: Current connection status
        callback: Async callback for transcription results
        reconnect_attempts: Number of reconnection attempts made
        last_activity: Timestamp of last activity (for health monitoring)
        created_at: Timestamp when connection was created
        url: WhisperX WebSocket URL
        listen_task: Background task for receiving messages
    """
    session_id: str
    websocket: Optional[websockets.WebSocketClientProtocol]
    status: ConnectionStatus
    callback: Optional[Callable[[str, bool, Dict], None]]
    reconnect_attempts: int
    last_activity: float
    created_at: float
    url: str
    listen_task: Optional[asyncio.Task] = None


class STTService:
    """
    Speech-to-Text service managing WhisperX connections per session.

    This service replaces the global WhisperClient with session-based routing,
    enabling multiple concurrent users to have independent STT streams.

    Usage:
        # Initialize service
        stt_service = STTService(
            default_whisper_url="ws://whisperx:4901",
            max_retries=5,
            backoff_multiplier=2.0,
            timeout_s=30.0
        )

        # Connect session
        success = await stt_service.connect(session_id="550e8400-...")

        # Register callback for transcriptions
        async def handle_transcript(text: str, is_final: bool, metadata: Dict):
            logger.info(f"Transcription: {text} (final={is_final})")

        await stt_service.register_callback(session_id, handle_transcript)

        # Send audio
        await stt_service.send_audio(session_id, audio_chunk)

        # Disconnect when done
        await stt_service.disconnect(session_id)
    """

    def __init__(
        self,
        default_whisper_url: Optional[str] = None,
        max_retries: int = WHISPER_RECONNECT_MAX_RETRIES,
        backoff_multiplier: float = WHISPER_RECONNECT_BACKOFF,
        timeout_s: float = WHISPER_TIMEOUT_S,
        error_callback: Optional[Callable[[ServiceErrorEvent], Awaitable[None]]] = None
    ):
        """
        Initialize STTService.

        Args:
            default_whisper_url: Default WhisperX WebSocket URL (overrides env var)
            max_retries: Maximum reconnection attempts
            backoff_multiplier: Exponential backoff multiplier
            timeout_s: Operation timeout in seconds
            error_callback: Optional async callback for error events
        """
        self.default_whisper_url = default_whisper_url or WHISPER_SERVER_URL
        self.max_retries = max_retries
        self.backoff_multiplier = backoff_multiplier
        self.timeout_s = timeout_s
        self.error_callback = error_callback

        # Connection pool: session_id -> WhisperXConnection
        self.connections: Dict[str, WhisperXConnection] = {}

        # Metrics tracking
        self.total_connections = 0
        self.total_reconnections = 0
        self.total_failures = 0
        self.total_transcriptions = 0

        logger.info(
            f"🎤 STTService initialized (url={self.default_whisper_url}, "
            f"max_retries={self.max_retries}, timeout={self.timeout_s}s)"
        )

    async def connect(self, session_id: str, whisper_url: Optional[str] = None) -> bool:
        """
        Connect to WhisperX for a specific session.

        Args:
            session_id: UUID of the session
            whisper_url: Optional custom WhisperX URL (overrides default)

        Returns:
            True if connection successful, False otherwise
        """
        url = whisper_url or self.default_whisper_url

        # Check if already connected
        if session_id in self.connections:
            conn = self.connections[session_id]
            if conn.status == ConnectionStatus.CONNECTED:
                logger.warning(f"⚠️ STT already connected for session {session_id}")
                return True

        # Create new connection object
        connection = WhisperXConnection(
            session_id=session_id,
            websocket=None,
            status=ConnectionStatus.CONNECTING,
            callback=None,
            reconnect_attempts=0,
            last_activity=time.time(),
            created_at=time.time(),
            url=url,
            listen_task=None
        )
        self.connections[session_id] = connection

        # Attempt to establish connection
        success = await self._establish_connection(session_id, url)

        if success:
            self.total_connections += 1
            logger.info(f"✅ STT connected for session {session_id}")
        else:
            logger.error(f"❌ STT connection failed for session {session_id}")
            connection.status = ConnectionStatus.FAILED
            self.total_failures += 1

        return success

    async def disconnect(self, session_id: str) -> None:
        """
        Disconnect WhisperX for a specific session.

        Args:
            session_id: UUID of the session
        """
        if session_id not in self.connections:
            logger.warning(f"⚠️ No STT connection found for session {session_id}")
            return

        connection = self.connections[session_id]

        # Cancel listen task
        if connection.listen_task and not connection.listen_task.done():
            connection.listen_task.cancel()
            try:
                await connection.listen_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket
        if connection.websocket:
            try:
                logger.info(f"🔒 Closing STT connection for session {session_id}")
                close_message = json.dumps({'type': 'close'})
                await connection.websocket.send(close_message)
                await connection.websocket.close()
            except Exception as e:
                error_msg = f"Error closing STT WebSocket: {e}"
                logger.error(f"❌ {error_msg}")

                # Emit error event if callback registered (non-critical, just a warning)
                if self.error_callback:
                    await self.error_callback(ServiceErrorEvent(
                        service_name="whisperx",
                        error_type=ServiceErrorType.STT_WEBSOCKET_CLOSED,
                        user_message="Speech recognition cleanup warning (non-critical).",
                        technical_details=error_msg,
                        session_id=session_id,
                        severity="warning",
                        retry_suggested=False
                    ))

        # Remove from pool
        del self.connections[session_id]
        logger.info(f"✅ STT disconnected for session {session_id}")

    async def send_audio(self, session_id: str, audio_data: bytes, audio_format: str = 'opus') -> bool:
        """
        Send audio frame to WhisperX for transcription with format indicator.

        Args:
            session_id: UUID of the session
            audio_data: Raw audio bytes (Opus frames for Discord, PCM for WebRTC)
            audio_format: Audio format - 'opus' (Discord) or 'pcm' (WebRTC)
                         Defaults to 'opus' for backward compatibility

        Returns:
            True if audio sent successfully, False otherwise
        """
        if session_id not in self.connections:
            logger.warning(f"⚠️ No STT connection for session {session_id}")
            return False

        connection = self.connections[session_id]

        if connection.status != ConnectionStatus.CONNECTED or not connection.websocket:
            logger.warning(f"⚠️ STT not connected for session {session_id} (status={connection.status})")
            return False

        try:
            # Send format indicator on first audio (if not already sent)
            if not hasattr(connection, 'format_sent'):
                logger.info(f"📡 Sending audio format to WhisperX: {audio_format}")
                import json
                await connection.websocket.send(json.dumps({
                    'type': 'start',
                    'userId': str(session_id),  # Convert UUID to string
                    'audio_format': audio_format
                }))
                connection.format_sent = True
                connection.audio_format = audio_format

            # Ensure audio_data is bytes (handle bytearray, memoryview, etc.)
            if not isinstance(audio_data, bytes):
                audio_data = bytes(audio_data)

            await connection.websocket.send(audio_data)
            connection.last_activity = time.time()
            return True

        except Exception as e:
            error_msg = f"Error sending audio to STT: {e}"
            logger.error(f"❌ {error_msg}")
            connection.status = ConnectionStatus.DISCONNECTED

            # Emit error event if callback registered
            if self.error_callback:
                await self.error_callback(ServiceErrorEvent(
                    service_name="whisperx",
                    error_type=ServiceErrorType.STT_CONNECTION_FAILED,
                    user_message="Speech recognition connection lost. Reconnecting...",
                    technical_details=error_msg,
                    session_id=session_id,
                    severity="warning",
                    retry_suggested=True
                ))

            # Attempt reconnect in background
            asyncio.create_task(self._attempt_reconnect(session_id))
            return False

    async def register_callback(
        self,
        session_id: str,
        callback: Callable[[str, bool, Dict], None]
    ) -> None:
        """
        Register callback for transcription results.

        Callback signature: async def callback(text: str, is_final: bool, metadata: Dict)

        Args:
            session_id: UUID of the session
            callback: Async callback function for transcription results
        """
        if session_id not in self.connections:
            logger.warning(f"⚠️ No STT connection for session {session_id}")
            return

        connection = self.connections[session_id]
        connection.callback = callback
        logger.info(f"✅ STT callback registered for session {session_id}")

    async def finalize_transcript(self, session_id: str) -> bool:
        """
        Send finalize message to WhisperX to trigger final transcript.

        This tells WhisperX to process all accumulated audio and send the final result.

        Args:
            session_id: UUID of the session

        Returns:
            True if finalize message sent successfully, False otherwise
        """
        if session_id not in self.connections:
            logger.warning(f"⚠️ No STT connection for session {session_id}")
            return False

        connection = self.connections[session_id]

        if connection.status != ConnectionStatus.CONNECTED or not connection.websocket:
            logger.warning(f"⚠️ STT not connected for session {session_id} (status={connection.status})")
            return False

        try:
            # Send finalize message to WhisperX
            finalize_message = json.dumps({'type': 'finalize'})
            await connection.websocket.send(finalize_message)
            logger.info(f"🏁 Sent finalize message to WhisperX for session {session_id}")
            return True

        except Exception as e:
            error_msg = f"Error sending finalize message to STT: {e}"
            logger.error(f"❌ {error_msg}")

            # Emit error event if callback registered
            if self.error_callback:
                await self.error_callback(ServiceErrorEvent(
                    service_name="whisperx",
                    error_type=ServiceErrorType.STT_TRANSCRIPTION_FAILED,
                    user_message="Speech recognition failed. Please speak again.",
                    technical_details=error_msg,
                    session_id=session_id,
                    severity="warning",
                    retry_suggested=True
                ))

            return False

    async def is_connected(self, session_id: str) -> bool:
        """
        Check if session has active WhisperX connection.

        Args:
            session_id: UUID of the session

        Returns:
            True if connected, False otherwise
        """
        if session_id not in self.connections:
            return False

        connection = self.connections[session_id]
        return connection.status == ConnectionStatus.CONNECTED and connection.websocket is not None

    async def get_connection_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get detailed connection status for session.

        Args:
            session_id: UUID of the session

        Returns:
            Dictionary with connection status details
        """
        if session_id not in self.connections:
            return {
                'session_id': session_id,
                'connected': False,
                'status': ConnectionStatus.DISCONNECTED.value,
                'error': 'No connection found'
            }

        connection = self.connections[session_id]
        uptime = time.time() - connection.created_at
        idle_time = time.time() - connection.last_activity

        return {
            'session_id': session_id,
            'connected': connection.status == ConnectionStatus.CONNECTED,
            'status': connection.status.value,
            'url': connection.url,
            'reconnect_attempts': connection.reconnect_attempts,
            'uptime_seconds': uptime,
            'idle_seconds': idle_time,
            'has_callback': connection.callback is not None,
            'created_at': connection.created_at,
            'last_activity': connection.last_activity
        }

    async def _establish_connection(self, session_id: str, url: str) -> bool:
        """
        Internal: Establish WebSocket connection with retry logic.

        Args:
            session_id: UUID of the session
            url: WhisperX WebSocket URL

        Returns:
            True if connection successful, False otherwise
        """
        if session_id not in self.connections:
            return False

        connection = self.connections[session_id]
        attempt = 0

        while attempt <= self.max_retries:
            try:
                logger.info(
                    f"🔌 Connecting to WhisperX at {url} "
                    f"(session={session_id}, attempt={attempt + 1}/{self.max_retries + 1})"
                )

                connection.status = ConnectionStatus.CONNECTING if attempt == 0 else ConnectionStatus.RECONNECTING

                # Establish WebSocket connection
                ws = await asyncio.wait_for(
                    websockets.connect(
                        url,
                        ping_interval=20,
                        ping_timeout=10
                    ),
                    timeout=self.timeout_s
                )

                connection.websocket = ws
                connection.status = ConnectionStatus.CONNECTED
                connection.reconnect_attempts = attempt
                connection.last_activity = time.time()

                # Send initial metadata
                start_message = json.dumps({
                    'type': 'start',
                    'userId': str(session_id),  # Convert UUID to string
                    'language': WHISPER_LANGUAGE
                })
                await ws.send(start_message)

                logger.info(f"✅ WhisperX connected for session {session_id}")

                # Start background listener task
                connection.listen_task = asyncio.create_task(self._receive_loop(session_id))

                return True

            except asyncio.TimeoutError:
                attempt += 1
                logger.error(
                    f"⏱️ WhisperX connection timeout (session={session_id}, "
                    f"attempt={attempt}/{self.max_retries + 1})"
                )

            except Exception as e:
                attempt += 1
                logger.error(
                    f"❌ Failed to connect to WhisperX (session={session_id}, "
                    f"attempt={attempt}/{self.max_retries + 1}): {e}"
                )

            # Exponential backoff before retry
            if attempt <= self.max_retries:
                delay = min(self.backoff_multiplier ** attempt, 30.0)  # Cap at 30s
                logger.info(f"⏳ Retrying WhisperX connection in {delay:.1f}s...")
                await asyncio.sleep(delay)

        # All attempts failed
        connection.status = ConnectionStatus.FAILED
        return False

    async def _receive_loop(self, session_id: str) -> None:
        """
        Internal: Background task to receive transcription results.

        Args:
            session_id: UUID of the session
        """
        if session_id not in self.connections:
            return

        connection = self.connections[session_id]

        try:
            logger.info(f"👂 Started STT receive loop for session {session_id}")

            async for message in connection.websocket:
                connection.last_activity = time.time()
                await self._handle_message(session_id, message)

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"🔌 WhisperX connection closed for session {session_id}")
            connection.status = ConnectionStatus.DISCONNECTED

        except asyncio.CancelledError:
            logger.info(f"🛑 STT receive loop cancelled for session {session_id}")

        except Exception as e:
            logger.error(f"❌ Error in STT receive loop (session={session_id}): {e}")
            connection.status = ConnectionStatus.DISCONNECTED

    async def _handle_message(self, session_id: str, message: str) -> None:
        """
        Internal: Handle incoming transcription message from WhisperX.

        Args:
            session_id: UUID of the session
            message: JSON message from WhisperX server
        """
        if session_id not in self.connections:
            return

        connection = self.connections[session_id]

        try:
            data = json.loads(message)
            msg_type = data.get('type')

            if msg_type == 'partial':
                # Partial transcription result (real-time)
                text = data.get('text', '')
                if text:
                    logger.info(f"🔄 STT Partial (session={session_id}): \"{text}\"")
                    if connection.callback:
                        metadata = {
                            'type': 'partial',
                            'timestamp': time.time(),
                            'confidence': data.get('confidence')
                        }
                        await connection.callback(text, False, metadata)

            elif msg_type == 'final':
                # Final transcription result
                text = data.get('text', '')
                logger.info(f"✅ STT Final (session={session_id}): \"{text or '(empty)'}\"")

                self.total_transcriptions += 1

                if connection.callback:
                    metadata = {
                        'type': 'final',
                        'timestamp': time.time(),
                        'confidence': data.get('confidence'),
                        'duration': data.get('duration')
                    }
                    await connection.callback(text, True, metadata)

            elif msg_type == 'error':
                error_msg = data.get('error', 'Unknown error')
                logger.error(f"❌ WhisperX error (session={session_id}): {error_msg}")

                if connection.callback:
                    metadata = {
                        'type': 'error',
                        'timestamp': time.time(),
                        'error': error_msg
                    }
                    await connection.callback('', True, metadata)

        except json.JSONDecodeError:
            logger.error(f"❌ Invalid JSON from WhisperX (session={session_id}): {message}")

        except Exception as e:
            logger.error(f"❌ Error handling STT message (session={session_id}): {e}")

    async def _attempt_reconnect(self, session_id: str) -> bool:
        """
        Internal: Attempt to reconnect with exponential backoff.

        Args:
            session_id: UUID of the session

        Returns:
            True if reconnection successful, False otherwise
        """
        if session_id not in self.connections:
            return False

        connection = self.connections[session_id]
        logger.warning(f"🔄 Attempting to reconnect STT for session {session_id}")

        self.total_reconnections += 1

        # Close existing WebSocket if any
        if connection.websocket:
            try:
                await connection.websocket.close()
            except Exception:
                pass
            connection.websocket = None

        # Attempt reconnection
        success = await self._establish_connection(session_id, connection.url)

        if success:
            logger.info(f"✅ STT reconnected for session {session_id}")
        else:
            logger.error(f"❌ STT reconnection failed for session {session_id}")
            self.total_failures += 1

        return success

    async def get_metrics(self) -> Dict[str, Any]:
        """
        Get service-wide metrics.

        Returns:
            Dictionary with metrics (connections, reconnections, failures, etc.)
        """
        active_connections = sum(
            1 for conn in self.connections.values()
            if conn.status == ConnectionStatus.CONNECTED
        )

        return {
            'active_connections': active_connections,
            'total_connections': self.total_connections,
            'total_reconnections': self.total_reconnections,
            'total_failures': self.total_failures,
            'total_transcriptions': self.total_transcriptions,
            'sessions': list(self.connections.keys())
        }

    async def shutdown(self) -> None:
        """
        Shutdown service and disconnect all sessions.

        Should be called during graceful shutdown to clean up resources.
        """
        logger.info(f"🛑 Shutting down STTService ({len(self.connections)} connections)...")

        # Disconnect all sessions
        disconnect_tasks = [
            self.disconnect(session_id)
            for session_id in list(self.connections.keys())
        ]

        await asyncio.gather(*disconnect_tasks, return_exceptions=True)

        logger.info("✅ STTService shutdown complete")


# Singleton instance
_stt_service: Optional[STTService] = None


def get_stt_service() -> STTService:
    """
    Get singleton STTService instance.

    Returns:
        Singleton STTService instance
    """
    global _stt_service
    if _stt_service is None:
        _stt_service = STTService()
    return _stt_service
