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
        Handle start message

        Args:
            websocket: WebSocket connection
            data: Start message data
        """
        user_id = data.get('userId')
        language = data.get('language', 'en')

        logger.info(f"📡 Mock WhisperX: Started session for user {user_id} (language: {language})")

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

    def get_received_audio_count(self) -> int:
        """Get number of audio chunks received"""
        return len(self.received_audio_chunks)

    def get_received_messages(self) -> list[dict]:
        """Get all received JSON messages"""
        return self.received_messages.copy()


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
