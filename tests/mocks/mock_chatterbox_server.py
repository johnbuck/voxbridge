"""
Mock Chatterbox TTS Server for Testing

Simulates Chatterbox TTS streaming endpoint without actual TTS generation
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Callable
from contextlib import asynccontextmanager
from fastapi import FastAPI, Form, Request
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn

logger = logging.getLogger(__name__)


class MockChatterboxServer:
    """Mock Chatterbox TTS server for testing"""

    def __init__(
        self,
        port: int = 14123,  # Different from real Chatterbox
        latency_ms: int = 100,
        error_mode: bool = False,
        chunk_size: int = 8192
    ):
        """
        Initialize mock Chatterbox server

        Args:
            port: Port to listen on
            latency_ms: Simulated TTS generation latency
            error_mode: Inject errors for testing
            chunk_size: Size of audio chunks to stream
        """
        self.port = port
        self.latency_ms = latency_ms
        self.error_mode = error_mode
        self.chunk_size = chunk_size

        self.app = FastAPI(title="Mock Chatterbox TTS Server")
        self.server: Optional[uvicorn.Server] = None
        self.received_requests: list[dict] = []

        # Callbacks for custom behavior
        self.on_request_callback: Optional[Callable] = None

        # Setup routes
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes"""

        @self.app.post("/v1/audio/speech/stream/upload")
        async def tts_stream_upload(
            input: str = Form(...),
            voice: str = Form(default="default"),
            response_format: str = Form(default="wav"),
            speed: float = Form(default=1.0),
            streaming_strategy: str = Form(default="sentence"),
            streaming_quality: str = Form(default="fast"),
            streaming_chunk_size: int = Form(default=100),
            temperature: Optional[float] = Form(default=None),
            exaggeration: Optional[float] = Form(default=None),
            cfg_weight: Optional[float] = Form(default=None)
        ):
            """Mock TTS streaming endpoint"""
            try:
                request_data = {
                    "input": input,
                    "voice": voice,
                    "response_format": response_format,
                    "speed": speed,
                    "streaming_strategy": streaming_strategy,
                    "streaming_quality": streaming_quality,
                    "streaming_chunk_size": streaming_chunk_size
                }

                if temperature is not None:
                    request_data["temperature"] = temperature
                if exaggeration is not None:
                    request_data["exaggeration"] = exaggeration
                if cfg_weight is not None:
                    request_data["cfg_weight"] = cfg_weight

                self.received_requests.append(request_data)

                logger.info(f"🔊 Mock Chatterbox: TTS request - \"{input[:50]}...\"")
                logger.debug(f"   Voice: {voice}, Strategy: {streaming_strategy}, Quality: {streaming_quality}")

                if self.on_request_callback:
                    await self.on_request_callback(request_data)

                # Error mode
                if self.error_mode:
                    return JSONResponse(
                        status_code=500,
                        content={"error": "Mock TTS generation failed"}
                    )

                # Return streaming audio response
                return StreamingResponse(
                    self._generate_audio_stream(input),
                    media_type="audio/wav"
                )

            except Exception as e:
                logger.error(f"❌ Mock Chatterbox error: {e}")
                return JSONResponse(
                    status_code=500,
                    content={"error": str(e)}
                )

        @self.app.post("/v1/audio/speech")
        async def tts_standard(
            input: str = Form(...),
            voice: str = Form(default="default"),
            response_format: str = Form(default="wav"),
            speed: float = Form(default=1.0)
        ):
            """Mock standard (non-streaming) TTS endpoint"""
            request_data = {
                "input": input,
                "voice": voice,
                "response_format": response_format,
                "speed": speed
            }

            self.received_requests.append(request_data)
            logger.info(f"🔊 Mock Chatterbox: Standard TTS - \"{input[:50]}...\"")

            if self.error_mode:
                return JSONResponse(
                    status_code=500,
                    content={"error": "Mock TTS generation failed"}
                )

            # Simulate generation time
            await asyncio.sleep(self.latency_ms / 1000.0)

            # Return complete audio
            audio_data = self._generate_fake_wav(duration_ms=2000)
            return StreamingResponse(
                iter([audio_data]),
                media_type="audio/wav"
            )

        @self.app.get("/v1/audio/speech/history")
        async def tts_history():
            """Get request history (for test verification)"""
            return {"requests": self.received_requests}

        @self.app.post("/v1/audio/speech/reset")
        async def tts_reset():
            """Reset request history"""
            self.received_requests.clear()
            return {"status": "reset"}

    async def _generate_audio_stream(self, text: str):
        """
        Generate streaming audio response

        Args:
            text: Input text (used to calculate audio length)

        Yields:
            Audio chunks
        """
        # Estimate audio duration based on text length
        # Rough estimate: 150 words per minute, 5 chars per word
        duration_ms = max(500, len(text) * 60)  # Minimum 500ms

        # Generate fake WAV audio
        audio_data = self._generate_fake_wav(duration_ms)

        # Stream in chunks
        total_chunks = (len(audio_data) + self.chunk_size - 1) // self.chunk_size

        for i in range(total_chunks):
            start = i * self.chunk_size
            end = min(start + self.chunk_size, len(audio_data))
            chunk = audio_data[start:end]

            # Simulate streaming latency per chunk
            await asyncio.sleep(self.latency_ms / 1000.0 / total_chunks)

            yield chunk

        logger.debug(f"🔊 Mock Chatterbox: Streamed {total_chunks} chunks ({len(audio_data)} bytes total)")

    def _generate_fake_wav(self, duration_ms: int) -> bytes:
        """
        Generate fake WAV audio file

        Args:
            duration_ms: Duration in milliseconds

        Returns:
            WAV file bytes
        """
        import struct

        sample_rate = 48000
        num_samples = int(sample_rate * duration_ms / 1000)

        # WAV header (44 bytes)
        header = bytearray()

        # RIFF chunk
        header.extend(b'RIFF')
        header.extend(struct.pack('<I', 36 + num_samples * 2))  # File size - 8
        header.extend(b'WAVE')

        # fmt sub-chunk
        header.extend(b'fmt ')
        header.extend(struct.pack('<I', 16))  # Sub-chunk size
        header.extend(struct.pack('<H', 1))   # Audio format (1 = PCM)
        header.extend(struct.pack('<H', 1))   # Num channels (1 = mono)
        header.extend(struct.pack('<I', sample_rate))  # Sample rate
        header.extend(struct.pack('<I', sample_rate * 2))  # Byte rate
        header.extend(struct.pack('<H', 2))   # Block align
        header.extend(struct.pack('<H', 16))  # Bits per sample

        # data sub-chunk
        header.extend(b'data')
        header.extend(struct.pack('<I', num_samples * 2))  # Data size

        # Generate silence (zeros) for audio data
        # In real tests, this would be actual audio
        audio_data = b'\x00' * (num_samples * 2)

        return bytes(header) + audio_data

    async def start(self):
        """Start the mock HTTP server"""
        config = uvicorn.Config(
            self.app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning"  # Reduce noise in tests
        )
        self.server = uvicorn.Server(config)

        # Run in background task
        asyncio.create_task(self.server.serve())

        # Wait for server to be ready
        await asyncio.sleep(0.5)

        logger.info(f"✅ Mock Chatterbox server started on http://127.0.0.1:{self.port}")

    async def stop(self):
        """Stop the mock HTTP server"""
        if self.server:
            self.server.should_exit = True
            # Give it time to shutdown
            await asyncio.sleep(0.5)
            logger.info("🛑 Mock Chatterbox server stopped")

    def reset(self):
        """Reset server state (for testing)"""
        self.received_requests.clear()

    def get_received_requests(self) -> list[dict]:
        """Get all received requests"""
        return self.received_requests.copy()

    def get_last_request(self) -> Optional[dict]:
        """Get the last received request"""
        if self.received_requests:
            return self.received_requests[-1]
        return None


# ============================================================
# Fixture Helper
# ============================================================

@asynccontextmanager
async def create_mock_chatterbox_server(
    port: int = 14123,
    latency_ms: int = 100,
    error_mode: bool = False,
    chunk_size: int = 8192
):
    """
    Create and manage mock Chatterbox server as async context manager

    Args:
        port: Port to listen on
        latency_ms: Simulated TTS generation latency
        error_mode: Inject errors for testing
        chunk_size: Size of audio chunks

    Yields:
        Base URL of the running server

    Usage:
        async with create_mock_chatterbox_server() as base_url:
            # Server is running
            response = await client.post(f"{base_url}/v1/audio/speech/stream/upload", data=tts_data)
        # Server automatically stopped
    """
    server = MockChatterboxServer(
        port=port,
        latency_ms=latency_ms,
        error_mode=error_mode,
        chunk_size=chunk_size
    )

    await server.start()

    try:
        yield f"http://127.0.0.1:{port}/v1"
    finally:
        await server.stop()


# ============================================================
# Preset Server Configurations
# ============================================================

@asynccontextmanager
async def create_fast_mock_chatterbox():
    """Create mock Chatterbox with minimal latency for fast tests"""
    async with create_mock_chatterbox_server(latency_ms=10) as base_url:
        yield base_url


@asynccontextmanager
async def create_slow_mock_chatterbox():
    """Create mock Chatterbox with high latency for timeout testing"""
    async with create_mock_chatterbox_server(latency_ms=2000) as base_url:
        yield base_url


@asynccontextmanager
async def create_error_mock_chatterbox():
    """Create mock Chatterbox that always returns errors"""
    async with create_mock_chatterbox_server(error_mode=True) as base_url:
        yield base_url
