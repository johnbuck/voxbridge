"""
Mock WhisperX WebSocket Server for Testing

Simulates WhisperX transcription service without requiring GPU/model
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional, Callable
from contextlib import asynccontextmanager
import websockets
from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)


class MockWhisperXServer:
    """Mock WhisperX server for testing"""

    def __init__(
        self,
        port: int = 14901,  # Different from real server
        auto_respond: bool = True,
        latency_ms: int = 100,
        error_mode: bool = False
    ):
        """
        Initialize mock WhisperX server

        Args:
            port: Port to listen on
            auto_respond: Automatically send partial/final transcripts
            latency_ms: Simulated processing latency
            error_mode: Inject errors for testing
        """
        self.port = port
        self.auto_respond = auto_respond
        self.latency_ms = latency_ms
        self.error_mode = error_mode

        self.server: Optional[websockets.WebSocketServer] = None
        self.connections: list[WebSocketServerProtocol] = []
        self.received_messages: list[dict] = []
        self.received_audio_chunks: list[bytes] = []

        # NEW: Format tracking per session (for WebRTC audio fix validation)
        self.session_formats: dict[str, str] = {}  # user_id -> audio_format
        self.format_indicators_received: list[dict] = []  # Track all format messages

        # NEW: Audio statistics per session (for format validation)
        self.session_audio_stats: dict[str, dict] = {}  # user_id -> {bytes_received, chunk_count, format, chunks}

        # NEW: WebSocket connection to session mapping (for concurrent sessions)
        self.connection_to_session: dict[WebSocketServerProtocol, str] = {}  # websocket -> user_id

        # Callbacks for custom behavior
        self.on_start_callback: Optional[Callable] = None
        self.on_audio_callback: Optional[Callable] = None
        self.on_finalize_callback: Optional[Callable] = None

    async def handle_connection(self, websocket: WebSocketServerProtocol):
        """
        Handle WebSocket connection from client

        Args:
            websocket: WebSocket connection
        """
        self.connections.append(websocket)
        logger.info(f"📡 Mock WhisperX: Client connected")

        try:
            async for message in websocket:
                await self.handle_message(websocket, message)

        except websockets.exceptions.ConnectionClosed:
            logger.info("📡 Mock WhisperX: Client disconnected")
        finally:
            if websocket in self.connections:
                self.connections.remove(websocket)

    async def handle_message(
        self,
        websocket: WebSocketServerProtocol,
        message: str | bytes
    ):
        """
        Handle incoming message from client

        Args:
            websocket: WebSocket connection
            message: Message from client (JSON or binary audio)
        """
        # Binary message = audio chunk
        if isinstance(message, bytes):
            self.received_audio_chunks.append(message)

            # Track audio statistics for format validation (pass websocket for session tracking)
            await self._track_audio_stats(websocket, message)

            logger.debug(f"📡 Mock WhisperX: Received audio chunk ({len(message)} bytes)")

            if self.auto_respond:
                # Send partial transcript
                await self.send_partial_transcript(websocket)

            if self.on_audio_callback:
                await self.on_audio_callback(message)

        # Text message = JSON command
        else:
            try:
                data = json.loads(message)
                self.received_messages.append(data)
                msg_type = data.get('type')

                logger.info(f"📡 Mock WhisperX: Received {msg_type} message")

                if msg_type == 'start':
                    await self.handle_start(websocket, data)
                elif msg_type == 'finalize':
                    await self.handle_finalize(websocket)
                elif msg_type == 'close':
                    await websocket.close()

            except json.JSONDecodeError:
                logger.error(f"📡 Mock WhisperX: Invalid JSON: {message}")
                if self.error_mode:
                    await self.send_error(websocket, "Invalid JSON")

    async def handle_start(self, websocket: WebSocketServerProtocol, data: dict):
        """
        Handle start message with format tracking

        Args:
            websocket: WebSocket connection
            data: Start message data
        """
        user_id = data.get('userId')
        language = data.get('language', 'en')
        audio_format = data.get('audio_format', 'opus')  # NEW: Track audio format

        # Store format for this session
        self.session_formats[user_id] = audio_format
        self.format_indicators_received.append({
            'userId': user_id,
            'audio_format': audio_format,
            'timestamp': __import__('time').time()
        })

        # NEW: Map this websocket connection to this session
        self.connection_to_session[websocket] = user_id

        logger.info(f"📡 Mock WhisperX: Started session for user {user_id} "
                   f"(language: {language}, format: {audio_format})")

        if self.on_start_callback:
            await self.on_start_callback(user_id, language)

    async def handle_finalize(self, websocket: WebSocketServerProtocol):
        """
        Handle finalize message - send final transcript

        Args:
            websocket: WebSocket connection
        """
        logger.info("📡 Mock WhisperX: Finalization requested")

        # Simulate processing latency
        await asyncio.sleep(self.latency_ms / 1000.0)

        if self.error_mode:
            await self.send_error(websocket, "Transcription failed")
        else:
            await self.send_final_transcript(websocket)

        if self.on_finalize_callback:
            await self.on_finalize_callback()

    async def send_partial_transcript(
        self,
        websocket: WebSocketServerProtocol,
        text: str = "test partial transcript"
    ):
        """
        Send partial transcript to client

        Args:
            websocket: WebSocket connection
            text: Partial transcript text
        """
        # Simulate processing latency
        await asyncio.sleep(self.latency_ms / 1000.0)

        message = json.dumps({
            'type': 'partial',
            'text': text
        })

        await websocket.send(message)
        logger.debug(f"📡 Mock WhisperX: Sent partial: \"{text}\"")

    async def send_final_transcript(
        self,
        websocket: WebSocketServerProtocol,
        text: str = None
    ):
        """
        Send final transcript to client

        Args:
            websocket: WebSocket connection
            text: Final transcript text (auto-generated if None)
        """
        if text is None:
            # Generate transcript based on audio chunks received
            chunk_count = len(self.received_audio_chunks)
            if chunk_count > 0:
                text = f"Mock transcript from {chunk_count} audio chunks"
            else:
                text = ""

        message = json.dumps({
            'type': 'final',
            'text': text
        })

        await websocket.send(message)
        logger.info(f"📡 Mock WhisperX: Sent final: \"{text}\"")

    async def send_error(
        self,
        websocket: WebSocketServerProtocol,
        error: str = "Server error"
    ):
        """
        Send error message to client

        Args:
            websocket: WebSocket connection
            error: Error message
        """
        message = json.dumps({
            'type': 'error',
            'error': error
        })

        await websocket.send(message)
        logger.error(f"📡 Mock WhisperX: Sent error: {error}")

    async def start(self):
        """Start the mock WebSocket server"""
        self.server = await websockets.serve(
            self.handle_connection,
            'localhost',
            self.port
        )
        logger.info(f"✅ Mock WhisperX server started on ws://localhost:{self.port}")

    async def stop(self):
        """Stop the mock WebSocket server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("🛑 Mock WhisperX server stopped")

    def reset(self):
        """Reset server state (for testing)"""
        self.received_messages.clear()
        self.received_audio_chunks.clear()
        self.session_formats.clear()
        self.format_indicators_received.clear()
        self.session_audio_stats.clear()
        self.connection_to_session.clear()

    def get_received_audio_count(self) -> int:
        """Get number of audio chunks received"""
        return len(self.received_audio_chunks)

    def get_received_messages(self) -> list[dict]:
        """Get all received JSON messages"""
        return self.received_messages.copy()

    def get_format_for_session(self, user_id: str) -> str:
        """
        Get declared audio format for a session

        Args:
            user_id: User ID to look up

        Returns:
            Audio format ('opus' or 'pcm'), defaults to 'opus' if not found
        """
        return self.session_formats.get(user_id, 'opus')

    def get_format_indicator_count(self, user_id: str) -> int:
        """
        Count how many format indicators received for a session

        Args:
            user_id: User ID to count indicators for

        Returns:
            Number of format indicator messages received
        """
        return len([
            msg for msg in self.format_indicators_received
            if msg['userId'] == user_id
        ])

    def get_all_session_formats(self) -> dict[str, str]:
        """
        Get all session formats

        Returns:
            Dictionary mapping user_id to audio_format
        """
        return self.session_formats.copy()

    async def _track_audio_stats(self, websocket: WebSocketServerProtocol, audio_chunk: bytes):
        """
        Track audio statistics for format validation

        This method is called whenever binary audio is received.
        It tracks statistics per session to validate audio format matches expectations.

        Args:
            websocket: WebSocket connection that sent the audio
            audio_chunk: Binary audio data received
        """
        # Look up which session this websocket belongs to
        user_id = self.connection_to_session.get(websocket)
        if not user_id:
            # No session associated with this connection yet - might be audio before 'start' message
            return

        # Initialize stats if first audio for this session
        if user_id not in self.session_audio_stats:
            self.session_audio_stats[user_id] = {
                'bytes_received': 0,
                'chunk_count': 0,
                'format': self.session_formats.get(user_id, 'opus'),
                'chunks': []  # Store chunk sizes for analysis
            }

        stats = self.session_audio_stats[user_id]
        chunk_size = len(audio_chunk)

        stats['bytes_received'] += chunk_size
        stats['chunk_count'] += 1
        stats['chunks'].append(chunk_size)

        # Validate chunk size matches format expectations
        declared_format = stats['format']

        if declared_format == 'opus':
            # Opus frames: typically 120-200 bytes per 20ms
            if chunk_size < 50 or chunk_size > 500:
                logger.warning(
                    f"⚠️ Suspicious Opus chunk size: {chunk_size} bytes "
                    f"(expected 120-200 for 20ms frame) - session: {user_id}"
                )

        elif declared_format == 'pcm':
            # PCM frames: 3,840 bytes per 20ms (960 samples × 2 bytes × 2 channels)
            # But might receive variable sizes from PyAV decode
            if chunk_size < 1000:  # Suspiciously small for PCM
                logger.warning(
                    f"⚠️ Suspicious PCM chunk size: {chunk_size} bytes "
                    f"(expected ~3,840+ for 20ms frame) - session: {user_id}"
                )

        logger.debug(
            f"🎵 Audio stats: user={user_id}, format={declared_format}, "
            f"chunk={chunk_size}B, total={stats['bytes_received']}B, "
            f"chunks={stats['chunk_count']}"
        )

    def get_session_stats(self, user_id: str) -> dict:
        """
        Get audio statistics for a session

        Args:
            user_id: User ID to get stats for

        Returns:
            Statistics dict with keys: bytes_received, chunk_count, format, chunks
            Returns empty dict if session not found
        """
        return self.session_audio_stats.get(user_id, {})

    def get_avg_chunk_size(self, user_id: str) -> float:
        """
        Calculate average audio chunk size for validation

        Args:
            user_id: User ID to calculate average for

        Returns:
            Average chunk size in bytes (0.0 if no chunks)
        """
        stats = self.session_audio_stats.get(user_id)
        if not stats or not stats['chunks']:
            return 0.0

        return sum(stats['chunks']) / len(stats['chunks'])

    def validate_format_match(self, user_id: str) -> bool:
        """
        Validate that received audio matches declared format

        This checks if audio chunk sizes match format expectations:
        - Opus: Small chunks (50-500 bytes)
        - PCM: Large chunks (1000+ bytes)

        Args:
            user_id: User ID to validate

        Returns:
            True if audio size distribution matches format expectations
        """
        stats = self.session_audio_stats.get(user_id)
        if not stats or not stats['chunks']:
            return False

        avg_size = self.get_avg_chunk_size(user_id)
        declared_format = stats['format']

        if declared_format == 'opus':
            # Opus: expect small chunks (120-200 bytes typical, allow 50-500)
            return 50 < avg_size < 500

        elif declared_format == 'pcm':
            # PCM: expect large chunks (1000+ bytes)
            return avg_size > 1000

        return False


# ============================================================
# Fixture Helper
# ============================================================

@asynccontextmanager
async def create_mock_whisperx_server(
    port: int = 14901,
    auto_respond: bool = True,
    latency_ms: int = 100,
    error_mode: bool = False
):
    """
    Create and manage mock WhisperX server as async context manager

    Args:
        port: Port to listen on
        auto_respond: Automatically send partial/final transcripts
        latency_ms: Simulated processing latency
        error_mode: Inject errors for testing

    Yields:
        Port number of the running server

    Usage:
        async with create_mock_whisperx_server() as port:
            # Server is running
            client = WhisperClient()
            await client.connect(url=f"ws://localhost:{port}")
        # Server automatically stopped
    """
    server = MockWhisperXServer(
        port=port,
        auto_respond=auto_respond,
        latency_ms=latency_ms,
        error_mode=error_mode
    )

    await server.start()

    try:
        yield port
    finally:
        await server.stop()


# ============================================================
# Preset Server Configurations
# ============================================================

@asynccontextmanager
async def create_fast_mock_whisperx():
    """Create mock WhisperX with minimal latency for fast tests"""
    async with create_mock_whisperx_server(latency_ms=10) as port:
        yield port


@asynccontextmanager
async def create_slow_mock_whisperx():
    """Create mock WhisperX with high latency for timeout testing"""
    async with create_mock_whisperx_server(latency_ms=2000) as port:
        yield port


@asynccontextmanager
async def create_error_mock_whisperx():
    """Create mock WhisperX that always returns errors"""
    async with create_mock_whisperx_server(error_mode=True) as port:
        yield port
