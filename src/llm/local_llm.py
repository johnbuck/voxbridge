"""
Local LLM Provider

OpenAI-compatible API for local LLMs (Ollama, LM Studio, etc.)
"""

import json
import logging
from typing import AsyncIterator, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.llm.base import LLMProvider
from src.llm.types import LLMMessage, LLMStreamChunk, LLMError

logger = logging.getLogger(__name__)


class LocalLLMProvider(LLMProvider):
    """Local LLM provider using OpenAI-compatible API"""

    def __init__(self, model: str, base_url: str, api_key: Optional[str] = None):
        super().__init__(model, api_key, base_url)
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
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
        Generate streaming response from local LLM.

        Args:
            messages: Conversation history
            temperature: Sampling temperature
            max_tokens: Maximum tokens

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
            async with httpx.AsyncClient(timeout=120.0) as client:  # Longer timeout for local
                async with client.stream("POST", url, json=payload, headers=self.headers) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise LLMError(
                            message=f"Local LLM error: {error_text.decode()}",
                            provider="local_llm",
                            status_code=response.status_code,
                            retryable=False
                        )

                    # Process SSE stream (OpenAI-compatible format)
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]

                            if data_str == "[DONE]":
                                break

                            try:
                                data = json.loads(data_str)

                                if "choices" in data and len(data["choices"]) > 0:
                                    choice = data["choices"][0]
                                    delta = choice.get("delta", {})
                                    content = delta.get("content", "")

                                    if content:
                                        yield LLMStreamChunk(
                                            content=content,
                                            finish_reason=choice.get("finish_reason")
                                        )

                                    if choice.get("finish_reason") and data.get("usage"):
                                        yield LLMStreamChunk(
                                            content="",
                                            finish_reason=choice["finish_reason"],
                                            usage=data["usage"]
                                        )
                            except json.JSONDecodeError:
                                continue

        except httpx.ConnectError as e:
            raise LLMError(
                message=f"Cannot connect to local LLM at {self.base_url}: {e}",
                provider="local_llm",
                retryable=False
            )
        except httpx.TimeoutException as e:
            raise LLMError(
                message=f"Local LLM timeout: {e}",
                provider="local_llm",
                retryable=True
            )
        except Exception as e:
            raise LLMError(
                message=f"Local LLM error: {e}",
                provider="local_llm",
                retryable=False
            )
