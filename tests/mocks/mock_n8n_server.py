"""
Mock n8n Webhook Server for Testing

Simulates n8n webhook responses (both streaming and non-streaming)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Callable
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn

logger = logging.getLogger(__name__)


class MockN8NServer:
    """Mock n8n webhook server for testing"""

    def __init__(
        self,
        port: int = 18888,  # Different from real n8n
        streaming: bool = True,
        latency_ms: int = 100,
        error_mode: bool = False,
        echo_mode: bool = True
    ):
        """
        Initialize mock n8n server

        Args:
            port: Port to listen on
            streaming: Return streaming (SSE) responses
            latency_ms: Simulated processing latency
            error_mode: Inject errors for testing
            echo_mode: Echo back the transcript in response
        """
        self.port = port
        self.streaming = streaming
        self.latency_ms = latency_ms
        self.error_mode = error_mode
        self.echo_mode = echo_mode

        self.app = FastAPI(title="Mock n8n Server")
        self.server: Optional[uvicorn.Server] = None
        self.received_requests: list[dict] = []

        # Callbacks for custom behavior
        self.on_request_callback: Optional[Callable] = None

        # Setup routes
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes"""

        @self.app.post("/webhook/test")
        async def webhook_test(request: Request):
            """Mock webhook endpoint"""
            try:
                body = await request.json()
                self.received_requests.append(body)

                text = body.get('text', '')
                user_id = body.get('userId', '')
                use_streaming = body.get('useStreaming', self.streaming)

                logger.info(f"📬 Mock n8n: Received webhook - \"{text}\" from {user_id}")

                if self.on_request_callback:
                    await self.on_request_callback(body)

                # Simulate processing latency
                await asyncio.sleep(self.latency_ms / 1000.0)

                # Error mode
                if self.error_mode:
                    return JSONResponse(
                        status_code=500,
                        content={"error": "Mock n8n error"}
                    )

                # Streaming response
                if use_streaming:
                    return StreamingResponse(
                        self._generate_streaming_response(text),
                        media_type="text/event-stream"
                    )

                # Non-streaming response
                else:
                    return self._generate_simple_response(text)

            except Exception as e:
                logger.error(f"❌ Mock n8n error: {e}")
                return JSONResponse(
                    status_code=500,
                    content={"error": str(e)}
                )

        @self.app.post("/webhook/test/feedback")
        async def webhook_feedback(request: Request):
            """Mock feedback endpoint (for E2E testing)"""
            body = await request.json()
            logger.info(f"📬 Mock n8n: Received feedback - {body}")
            self.received_requests.append({"type": "feedback", **body})
            return {"status": "received"}

        @self.app.get("/webhook/test/history")
        async def webhook_history():
            """Get request history (for test verification)"""
            return {"requests": self.received_requests}

        @self.app.post("/webhook/test/reset")
        async def webhook_reset():
            """Reset request history"""
            self.received_requests.clear()
            return {"status": "reset"}

    async def _generate_streaming_response(self, text: str):
        """
        Generate SSE streaming response

        Args:
            text: Original transcript text

        Yields:
            SSE data chunks
        """
        # Generate response text
        if self.echo_mode:
            response_text = f"Echo: {text}"
        else:
            response_text = "Mock streaming response from n8n"

        # Split into chunks (word by word for streaming)
        words = response_text.split()

        for word in words:
            # Simulate chunk generation latency
            await asyncio.sleep(self.latency_ms / 1000.0 / len(words))
            yield f"data: {word} \n\n"

        # Send DONE marker
        yield "data: [DONE]\n\n"

    def _generate_simple_response(self, text: str) -> dict:
        """
        Generate simple JSON response

        Args:
            text: Original transcript text

        Returns:
            Response dict
        """
        if self.echo_mode:
            content = f"Echo: {text}"
        else:
            content = "Mock response from n8n"

        return {
            "output": {
                "content": content
            },
            "options": {
                "voiceMode": "default",
                "speedFactor": 1.0,
                "outputFormat": "wav",
                "streamingStrategy": "sentence",
                "streamingQuality": "fast",
                "chunkSize": 100
            }
        }

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

        logger.info(f"✅ Mock n8n server started on http://127.0.0.1:{self.port}")

    async def stop(self):
        """Stop the mock HTTP server"""
        if self.server:
            self.server.should_exit = True
            # Give it time to shutdown
            await asyncio.sleep(0.5)
            logger.info("🛑 Mock n8n server stopped")

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
async def create_mock_n8n_server(
    port: int = 18888,
    streaming: bool = True,
    latency_ms: int = 100,
    error_mode: bool = False,
    echo_mode: bool = True
):
    """
    Create and manage mock n8n server as async context manager

    Args:
        port: Port to listen on
        streaming: Return streaming responses
        latency_ms: Simulated processing latency
        error_mode: Inject errors for testing
        echo_mode: Echo back the transcript

    Yields:
        Base URL of the running server

    Usage:
        async with create_mock_n8n_server() as base_url:
            # Server is running
            response = await client.post(f"{base_url}/webhook/test", json=data)
        # Server automatically stopped
    """
    server = MockN8NServer(
        port=port,
        streaming=streaming,
        latency_ms=latency_ms,
        error_mode=error_mode,
        echo_mode=echo_mode
    )

    await server.start()

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await server.stop()


# ============================================================
# Preset Server Configurations
# ============================================================

@asynccontextmanager
async def create_fast_mock_n8n():
    """Create mock n8n with minimal latency for fast tests"""
    async with create_mock_n8n_server(latency_ms=10) as base_url:
        yield base_url


@asynccontextmanager
async def create_slow_mock_n8n():
    """Create mock n8n with high latency for timeout testing"""
    async with create_mock_n8n_server(latency_ms=2000) as base_url:
        yield base_url


@asynccontextmanager
async def create_error_mock_n8n():
    """Create mock n8n that always returns errors"""
    async with create_mock_n8n_server(error_mode=True) as base_url:
        yield base_url


@asynccontextmanager
async def create_non_streaming_mock_n8n():
    """Create mock n8n that returns non-streaming responses"""
    async with create_mock_n8n_server(streaming=False) as base_url:
        yield base_url
