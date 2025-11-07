"""
OpenRouter.ai LLM provider implementation.

OpenRouter provides access to multiple LLM providers (Anthropic, OpenAI, Google, etc.)
through a unified API with pay-per-use pricing.
"""

import asyncio
import json
import logging
from typing import AsyncIterator, Optional

import httpx

from src.llm.base import LLMProvider
from src.llm.types import (
    LLMRequest,
    LLMError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMConnectionError,
    LLMAuthenticationError,
)

logger = logging.getLogger(__name__)


class OpenRouterProvider(LLMProvider):
    """
    OpenRouter.ai LLM provider.

    Supports streaming via Server-Sent Events (SSE) with the OpenRouter API.
    """

    API_BASE = "https://openrouter.ai/api/v1"
    TIMEOUT_FIRST_TOKEN = 30.0  # seconds (reduced from 60s for faster failure detection)
    TIMEOUT_BETWEEN_TOKENS = 30.0  # seconds

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        """
        Initialize OpenRouter provider.

        Args:
            api_key: OpenRouter API key
            base_url: Override API base URL (for testing)
        """
        super().__init__(api_key=api_key, base_url=base_url or self.API_BASE)

        if not self.api_key:
            raise ValueError("OpenRouter API key is required")

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=self.TIMEOUT_FIRST_TOKEN,
                write=10.0,
                pool=10.0,
            ),
            follow_redirects=True,
        )

        logger.info(f"🤖 LLM [openrouter]: Initialized with base URL {self.base_url}")

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Generate streaming response from OpenRouter.

        Yields text chunks as they arrive via SSE.

        Args:
            request: LLMRequest with messages, model, temperature

        Yields:
            str: Text chunks

        Raises:
            LLMTimeoutError: Request timeout
            LLMRateLimitError: Rate limit (429 status)
            LLMAuthenticationError: Invalid API key (401/403)
            LLMConnectionError: Network error
            LLMError: Other errors
        """
        url = f"{self.base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://voxbridge.local",
            "X-Title": "VoxBridge",
            "Content-Type": "application/json",
        }

        payload = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "stream": True,
        }

        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        logger.info(f"🤖 LLM [openrouter]: Streaming request to model '{request.model}'")
        logger.debug(f"🤖 LLM [openrouter]: Request payload size: {len(json.dumps(payload))} bytes, {len(request.messages)} messages")

        try:
            # Use retry decorator for transient errors
            logger.debug(f"🤖 LLM [openrouter]: Sending POST to {url}")
            response = await self._make_request_with_retry(url, headers, payload)

            # Stream SSE response
            chunk_count = 0
            async for chunk in self._parse_sse_stream(response):
                chunk_count += 1
                yield chunk

            logger.info(f"🤖 LLM [openrouter]: Streaming complete ({chunk_count} chunks)")

        except httpx.TimeoutException as e:
            logger.error(f"🤖 LLM [openrouter]: Timeout - {e}")
            raise LLMTimeoutError(f"OpenRouter request timeout: {e}") from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error(f"🤖 LLM [openrouter]: Rate limit exceeded")
                raise LLMRateLimitError("OpenRouter rate limit exceeded") from e
            elif e.response.status_code in (401, 403):
                logger.error(f"🤖 LLM [openrouter]: Authentication failed (status {e.response.status_code})")
                raise LLMAuthenticationError("Invalid OpenRouter API key") from e
            else:
                logger.error(f"🤖 LLM [openrouter]: HTTP error {e.response.status_code}")
                raise LLMError(f"OpenRouter HTTP error: {e.response.status_code}") from e

        except httpx.RequestError as e:
            logger.error(f"🤖 LLM [openrouter]: Connection error - {e}")
            raise LLMConnectionError(f"OpenRouter connection error: {e}") from e

        except Exception as e:
            logger.error(f"🤖 LLM [openrouter]: Unexpected error - {e}")
            raise LLMError(f"OpenRouter unexpected error: {e}") from e

        finally:
            # Don't close client here - it's reused across requests
            pass

    async def _make_request_with_retry(
        self,
        url: str,
        headers: dict,
        payload: dict,
        attempt: int = 1,
    ) -> httpx.Response:
        """
        Make streaming POST request with manual retry logic for transient errors.

        Note: httpx.AsyncClient.post() doesn't support stream parameter.
        Instead, we use client.stream() context manager for SSE streaming.

        Args:
            url: API endpoint URL
            headers: Request headers
            payload: JSON payload
            attempt: Current attempt number (for retry logic)

        Returns:
            httpx.Response: Streaming response

        Raises:
            httpx.HTTPStatusError: Non-2xx status code
            httpx.TimeoutException: Timeout
            httpx.RequestError: Connection error
        """
        try:
            # Use stream() context manager for SSE streaming
            # This returns an httpx.Response with streaming enabled
            request = self.client.build_request(
                "POST",
                url,
                headers=headers,
                json=payload,
            )
            logger.debug(f"🤖 LLM [openrouter]: Sending HTTP request (attempt {attempt}/{3})")
            response = await self.client.send(request, stream=True)
            logger.debug(f"🤖 LLM [openrouter]: Received HTTP response (status={response.status_code})")
            response.raise_for_status()
            return response

        except (httpx.RequestError, httpx.TimeoutException) as e:
            if attempt < 3:
                wait_time = min(2 ** attempt, 10)  # Exponential backoff: 2, 4, 8 seconds
                logger.warning(f"🤖 LLM [openrouter]: Request failed (attempt {attempt}/3), retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
                return await self._make_request_with_retry(url, headers, payload, attempt + 1)
            else:
                logger.error(f"🤖 LLM [openrouter]: All retry attempts exhausted: {e}")
                raise

    async def _parse_sse_stream(self, response: httpx.Response) -> AsyncIterator[str]:
        """
        Parse Server-Sent Events stream from OpenRouter.

        OpenRouter sends data in SSE format:
        data: {"choices":[{"delta":{"content":"hello"}}]}
        data: [DONE]

        Args:
            response: httpx.Response with streaming body

        Yields:
            str: Content deltas from SSE stream
        """
        line_count = 0
        content_chunks = 0

        async for line in response.aiter_lines():
            line = line.strip()
            line_count += 1

            # Skip empty lines and non-data lines
            if not line or not line.startswith("data: "):
                continue

            # Extract data payload
            data = line[6:]  # Remove "data: " prefix

            # Check for stream end marker
            if data == "[DONE]":
                logger.info(f"🤖 LLM [openrouter]: SSE stream ended after {line_count} lines, {content_chunks} content chunks")
                break

            # Parse JSON chunk
            try:
                chunk = json.loads(data)

                # Debug: Log first chunk structure
                if line_count <= 2:
                    logger.info(f"🤖 LLM [openrouter]: SSE chunk #{line_count} structure: {json.dumps(chunk)[:250]}")

                # Extract content delta
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")

                    if content:
                        content_chunks += 1
                        yield content
                    elif line_count <= 5:
                        # Debug: Log why content is empty (first 5 chunks only)
                        logger.info(f"🤖 LLM [openrouter]: Empty content in chunk #{line_count} (delta keys: {list(delta.keys())})")

            except json.JSONDecodeError as e:
                logger.warning(f"🤖 LLM [openrouter]: Failed to parse SSE chunk: {e}, data: {data[:100]}")
                continue

    async def health_check(self) -> bool:
        """
        Check if OpenRouter API is available.

        Makes a lightweight request to verify connectivity and authentication.

        Returns:
            bool: True if API is healthy, False otherwise
        """
        try:
            url = f"{self.base_url}/models"
            headers = {"Authorization": f"Bearer {self.api_key}"}

            response = await self.client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()

            logger.info("🤖 LLM [openrouter]: Health check passed")
            return True

        except Exception as e:
            logger.error(f"🤖 LLM [openrouter]: Health check failed - {e}")
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
