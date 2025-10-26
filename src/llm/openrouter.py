"""
OpenRouter LLM Provider

Streaming implementation for OpenRouter API (https://openrouter.ai)
"""

import json
import logging
from typing import AsyncIterator, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.llm.base import LLMProvider
from src.llm.types import LLMMessage, LLMStreamChunk, LLMError

logger = logging.getLogger(__name__)


class OpenRouterProvider(LLMProvider):
    """OpenRouter API provider with streaming support"""

    def __init__(self, model: str, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        super().__init__(model, api_key, base_url)
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://voxbridge.ai",
            "X-Title": "VoxBridge 2.0",
            "Content-Type": "application/json"
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True
    )
    async def generate_stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """
        Generate streaming response from OpenRouter.

        Args:
            messages: Conversation history
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            LLMStreamChunk: Response chunks

        Raises:
            LLMError: On API errors
        """
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "temperature": temperature,
            "stream": True
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", url, json=payload, headers=self.headers) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise LLMError(
                            message=f"OpenRouter API error: {error_text.decode()}",
                            provider="openrouter",
                            status_code=response.status_code,
                            retryable=response.status_code in [429, 500, 502, 503, 504]
                        )

                    # Process SSE stream
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]  # Remove "data: " prefix

                            if data_str == "[DONE]":
                                break

                            try:
                                data = json.loads(data_str)

                                # Extract content from delta
                                if "choices" in data and len(data["choices"]) > 0:
                                    choice = data["choices"][0]
                                    delta = choice.get("delta", {})
                                    content = delta.get("content", "")

                                    if content:
                                        yield LLMStreamChunk(
                                            content=content,
                                            finish_reason=choice.get("finish_reason")
                                        )

                                    # Yield final chunk with usage if available
                                    if choice.get("finish_reason") and data.get("usage"):
                                        yield LLMStreamChunk(
                                            content="",
                                            finish_reason=choice["finish_reason"],
                                            usage=data["usage"]
                                        )
                            except json.JSONDecodeError as e:
                                logger.warning(f"Failed to parse SSE data: {e}")
                                continue

        except httpx.TimeoutException as e:
            raise LLMError(
                message=f"OpenRouter request timeout: {e}",
                provider="openrouter",
                retryable=True
            )
        except httpx.NetworkError as e:
            raise LLMError(
                message=f"OpenRouter network error: {e}",
                provider="openrouter",
                retryable=True
            )
        except Exception as e:
            raise LLMError(
                message=f"OpenRouter error: {e}",
                provider="openrouter",
                retryable=False
            )
