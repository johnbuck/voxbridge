"""
Local LLM provider implementation for OpenAI-compatible endpoints.

Supports any LLM service that implements the OpenAI Chat Completions API:
- Ollama (http://localhost:11434/v1)
- vLLM (http://localhost:8000/v1)
- LM Studio (http://localhost:1234/v1)
- LocalAI (http://localhost:8080/v1)
- Text Generation WebUI (http://localhost:5000/v1)
"""

import json
import logging
from typing import AsyncIterator, Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.llm.base import LLMProvider
from src.llm.types import (
    LLMRequest,
    LLMError,
    LLMTimeoutError,
    LLMConnectionError,
)

logger = logging.getLogger(__name__)


class LocalLLMProvider(LLMProvider):
    """
    Local LLM provider for OpenAI-compatible endpoints.

    Supports any service implementing the OpenAI Chat Completions API with streaming.
    """

    TIMEOUT_FIRST_TOKEN = 120.0  # seconds (local models may be slower)
    TIMEOUT_BETWEEN_TOKENS = 60.0  # seconds

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        """
        Initialize Local LLM provider.

        Args:
            base_url: Base URL for OpenAI-compatible API (e.g., http://localhost:11434/v1)
            api_key: Optional API key (not required for most local deployments)
        """
        super().__init__(api_key=api_key, base_url=base_url)

        if not self.base_url:
            raise ValueError("Base URL is required for local LLM provider")

        # Ensure base_url ends without trailing slash for consistent URL construction
        self.base_url = self.base_url.rstrip("/")

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=self.TIMEOUT_FIRST_TOKEN,
                write=10.0,
                pool=10.0,
            ),
            follow_redirects=True,
        )

        logger.info(f"🤖 LLM [local]: Initialized with base URL {self.base_url}")

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Generate streaming response from local LLM.

        Yields text chunks as they arrive via SSE.

        Args:
            request: LLMRequest with messages, model, temperature

        Yields:
            str: Text chunks

        Raises:
            LLMTimeoutError: Request timeout
            LLMConnectionError: Network/connection error
            LLMError: Other errors
        """
        url = f"{self.base_url}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "stream": True,
        }

        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        logger.info(f"🤖 LLM [local]: Streaming request to model '{request.model}' at {self.base_url}")

        try:
            # Use retry decorator for transient errors
            response = await self._make_request_with_retry(url, headers, payload)

            # Stream SSE response
            chunk_count = 0
            async for chunk in self._parse_sse_stream(response):
                chunk_count += 1
                yield chunk

            logger.info(f"🤖 LLM [local]: Streaming complete ({chunk_count} chunks)")

        except httpx.TimeoutException as e:
            logger.error(f"🤖 LLM [local]: Timeout - {e}")
            raise LLMTimeoutError(f"Local LLM request timeout: {e}") from e

        except httpx.RequestError as e:
            logger.error(f"🤖 LLM [local]: Connection error - {e}")
            raise LLMConnectionError(f"Local LLM connection error: {e}") from e

        except Exception as e:
            logger.error(f"🤖 LLM [local]: Unexpected error - {e}")
            raise LLMError(f"Local LLM unexpected error: {e}") from e

        finally:
            # Don't close client here - it's reused across requests
            pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        reraise=True,
    )
    async def _make_request_with_retry(
        self,
        url: str,
        headers: dict,
        payload: dict,
    ) -> httpx.Response:
        """
        Make POST request with retry logic for transient errors.

        Args:
            url: API endpoint URL
            headers: Request headers
            payload: JSON payload

        Returns:
            httpx.Response: Streaming response

        Raises:
            httpx.HTTPStatusError: Non-2xx status code
            httpx.TimeoutException: Timeout
            httpx.RequestError: Connection error
        """
        response = await self.client.post(
            url,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response

    async def _parse_sse_stream(self, response: httpx.Response) -> AsyncIterator[str]:
        """
        Parse Server-Sent Events stream from local LLM.

        OpenAI-compatible format:
        data: {"choices":[{"delta":{"content":"hello"}}]}
        data: [DONE]

        Args:
            response: httpx.Response with streaming body

        Yields:
            str: Content deltas from SSE stream
        """
        async for line in response.aiter_lines():
            line = line.strip()

            # Skip empty lines and non-data lines
            if not line or not line.startswith("data: "):
                continue

            # Extract data payload
            data = line[6:]  # Remove "data: " prefix

            # Check for stream end marker
            if data == "[DONE]":
                break

            # Parse JSON chunk
            try:
                chunk = json.loads(data)

                # Extract content delta (OpenAI format)
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")

                    if content:
                        yield content

            except json.JSONDecodeError as e:
                logger.warning(f"🤖 LLM [local]: Failed to parse SSE chunk: {e}")
                continue

    async def health_check(self) -> bool:
        """
        Check if local LLM endpoint is available.

        Makes a lightweight request to verify connectivity.

        Returns:
            bool: True if endpoint is healthy, False otherwise
        """
        try:
            # Try GET /models endpoint (OpenAI-compatible standard)
            url = f"{self.base_url}/models"
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            response = await self.client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()

            logger.info("🤖 LLM [local]: Health check passed")
            return True

        except Exception as e:
            logger.warning(f"🤖 LLM [local]: Health check failed - {e}")

            # Fallback: Try root endpoint
            try:
                response = await self.client.get(self.base_url, timeout=10.0)
                if response.status_code < 500:  # Accept any non-5xx as "alive"
                    logger.info("🤖 LLM [local]: Health check passed (fallback)")
                    return True
            except Exception:
                pass

            logger.error("🤖 LLM [local]: Health check failed (all attempts)")
            return False

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
