"""
Unit tests for OpenRouter LLM provider.

Tests streaming responses, error handling, retry logic, and health checks.
"""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch, call
import json

from src.llm.openrouter import OpenRouterProvider
from src.llm.types import (
    LLMMessage,
    LLMRequest,
    LLMError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMConnectionError,
    LLMAuthenticationError,
)


# ============================================================
# Provider Initialization Tests
# ============================================================


@pytest.mark.unit
def test_openrouter_initialization():
    """Test OpenRouter provider initialization"""
    # ACT
    provider = OpenRouterProvider(api_key="test_key")

    # ASSERT
    assert provider.api_key == "test_key"
    assert provider.base_url == "https://openrouter.ai/api/v1"
    assert provider.client is not None


@pytest.mark.unit
def test_openrouter_initialization_custom_base_url():
    """Test OpenRouter provider with custom base URL"""
    # ACT
    provider = OpenRouterProvider(
        api_key="test_key",
        base_url="https://custom.openrouter.ai/api/v1",
    )

    # ASSERT
    assert provider.base_url == "https://custom.openrouter.ai/api/v1"


@pytest.mark.unit
def test_openrouter_initialization_missing_api_key():
    """Test OpenRouter provider fails without API key"""
    # ACT & ASSERT
    with pytest.raises(ValueError) as exc_info:
        OpenRouterProvider(api_key="")

    assert "OpenRouter API key is required" in str(exc_info.value)


# ============================================================
# Streaming Response Tests
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_streaming_success():
    """Test OpenRouter provider streaming response"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Hello")],
        temperature=0.7,
        model="anthropic/claude-3.5-sonnet",
    )

    # Mock SSE response
    mock_response = AsyncMock()
    mock_response.status_code = 200

    # Simulate SSE stream
    async def mock_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
        yield 'data: {"choices":[{"delta":{"content":" there"}}]}'
        yield 'data: {"choices":[{"delta":{"content":"!"}}]}'
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines

    # Mock httpx.AsyncClient.post
    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        mock_response.raise_for_status = MagicMock()

        # ACT
        chunks = []
        async for chunk in provider.generate_stream(request):
            chunks.append(chunk)

        # ASSERT
        assert chunks == ["Hello", " there", "!"]
        mock_post.assert_called_once()

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_streaming_with_max_tokens():
    """Test OpenRouter streaming includes max_tokens in request"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.5,
        model="gpt-4",
        max_tokens=500,
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":"Test"}}]}'
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines

    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        mock_response.raise_for_status = MagicMock()

        # ACT
        async for _ in provider.generate_stream(request):
            pass

        # ASSERT
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert payload["max_tokens"] == 500

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_streaming_no_max_tokens():
    """Test OpenRouter streaming omits max_tokens if None"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":"Test"}}]}'
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines

    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        mock_response.raise_for_status = MagicMock()

        # ACT
        async for _ in provider.generate_stream(request):
            pass

        # ASSERT
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert "max_tokens" not in payload

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_streaming_request_headers():
    """Test OpenRouter includes correct headers in request"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_api_key_123")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines

    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        mock_response.raise_for_status = MagicMock()

        # ACT
        async for _ in provider.generate_stream(request):
            pass

        # ASSERT
        call_args = mock_post.call_args
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer test_api_key_123"
        assert headers["Content-Type"] == "application/json"
        assert "HTTP-Referer" in headers
        assert "X-Title" in headers

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_streaming_empty_chunks():
    """Test OpenRouter handles empty content in SSE chunks"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
        yield 'data: {"choices":[{"delta":{}}]}'  # Empty delta
        yield 'data: {"choices":[{"delta":{"content":""}}]}'  # Empty content
        yield 'data: {"choices":[{"delta":{"content":"!"}}]}'
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines

    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        mock_response.raise_for_status = MagicMock()

        # ACT
        chunks = []
        async for chunk in provider.generate_stream(request):
            chunks.append(chunk)

        # ASSERT
        assert chunks == ["Hello", "!"]  # Empty chunks filtered out

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_streaming_malformed_json():
    """Test OpenRouter handles malformed JSON in SSE stream"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":"Valid"}}]}'
        yield "data: {invalid json}"  # Malformed
        yield 'data: {"choices":[{"delta":{"content":"!"}}]}'
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines

    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        mock_response.raise_for_status = MagicMock()

        # ACT
        chunks = []
        async for chunk in provider.generate_stream(request):
            chunks.append(chunk)

        # ASSERT
        assert chunks == ["Valid", "!"]  # Malformed chunk skipped

    await provider.close()


# ============================================================
# Error Handling Tests
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_timeout_error():
    """Test OpenRouter provider timeout handling"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    # Mock timeout
    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Request timed out")

        # ACT & ASSERT
        with pytest.raises(LLMTimeoutError) as exc_info:
            async for chunk in provider.generate_stream(request):
                pass

        assert "timeout" in str(exc_info.value).lower()

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_rate_limit_error():
    """Test OpenRouter provider rate limit (429) handling"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    # Mock 429 response
    mock_response = MagicMock()
    mock_response.status_code = 429

    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Rate limit",
            request=MagicMock(),
            response=mock_response,
        )

        # ACT & ASSERT
        with pytest.raises(LLMRateLimitError) as exc_info:
            async for chunk in provider.generate_stream(request):
                pass

        assert "rate limit" in str(exc_info.value).lower()

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_authentication_error_401():
    """Test OpenRouter provider authentication error (401)"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="invalid_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    # Mock 401 response
    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=mock_response,
        )

        # ACT & ASSERT
        with pytest.raises(LLMAuthenticationError) as exc_info:
            async for chunk in provider.generate_stream(request):
                pass

        assert "api key" in str(exc_info.value).lower()

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_authentication_error_403():
    """Test OpenRouter provider authentication error (403)"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="invalid_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    # Mock 403 response
    mock_response = MagicMock()
    mock_response.status_code = 403

    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden",
            request=MagicMock(),
            response=mock_response,
        )

        # ACT & ASSERT
        with pytest.raises(LLMAuthenticationError):
            async for chunk in provider.generate_stream(request):
                pass

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_connection_error():
    """Test OpenRouter provider connection error"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    # Mock connection error
    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.RequestError("Connection failed")

        # ACT & ASSERT
        with pytest.raises(LLMConnectionError) as exc_info:
            async for chunk in provider.generate_stream(request):
                pass

        assert "connection" in str(exc_info.value).lower()

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_http_error_500():
    """Test OpenRouter provider handles HTTP 500 error"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    # Mock 500 response
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal Server Error",
            request=MagicMock(),
            response=mock_response,
        )

        # ACT & ASSERT
        with pytest.raises(LLMError) as exc_info:
            async for chunk in provider.generate_stream(request):
                pass

        # Should be generic LLMError, not specific subclass
        assert type(exc_info.value) == LLMError
        assert "500" in str(exc_info.value)

    await provider.close()


# ============================================================
# Health Check Tests
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_health_check_success():
    """Test OpenRouter health check passes with 200 response"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        # ACT
        result = await provider.health_check()

        # ASSERT
        assert result is True
        mock_get.assert_called_once()

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_health_check_failure():
    """Test OpenRouter health check fails on error"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    with patch.object(provider.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.RequestError("Connection failed")

        # ACT
        result = await provider.health_check()

        # ASSERT
        assert result is False

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_health_check_timeout():
    """Test OpenRouter health check handles timeout"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    with patch.object(provider.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Health check timeout")

        # ACT
        result = await provider.health_check()

        # ASSERT
        assert result is False

    await provider.close()


# ============================================================
# Async Context Manager Tests
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_context_manager():
    """Test OpenRouter provider as async context manager"""
    # ACT & ASSERT
    async with OpenRouterProvider(api_key="test_key") as provider:
        assert provider is not None
        assert provider.api_key == "test_key"

    # Client should be closed after context exit
    # (We can't easily test this without accessing private state)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_close():
    """Test OpenRouter provider close method"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    # Mock the client's aclose method
    with patch.object(provider.client, "aclose", new_callable=AsyncMock) as mock_close:
        # ACT
        await provider.close()

        # ASSERT
        mock_close.assert_called_once()


# ============================================================
# Retry Logic Tests
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_retry_on_connection_error():
    """Test OpenRouter retries on transient connection errors"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":"Success"}}]}'
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines
    mock_response.raise_for_status = MagicMock()

    # Mock post to fail twice, then succeed
    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [
            httpx.RequestError("Transient error 1"),
            httpx.RequestError("Transient error 2"),
            mock_response,
        ]

        # ACT
        chunks = []
        async for chunk in provider.generate_stream(request):
            chunks.append(chunk)

        # ASSERT
        assert chunks == ["Success"]
        assert mock_post.call_count == 3  # 2 retries + 1 success

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_retry_exhausted():
    """Test OpenRouter exhausts retries and raises error"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    # Mock post to always fail
    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.RequestError("Persistent error")

        # ACT & ASSERT
        with pytest.raises(LLMConnectionError):
            async for chunk in provider.generate_stream(request):
                pass

        # Should have tried 3 times (initial + 2 retries)
        assert mock_post.call_count == 3

    await provider.close()


# ============================================================
# Edge Case Tests
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_multiple_requests_same_provider():
    """Test OpenRouter provider can handle multiple sequential requests"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request1 = LLMRequest(
        messages=[LLMMessage(role="user", content="Request 1")],
        temperature=0.7,
        model="gpt-4",
    )
    request2 = LLMRequest(
        messages=[LLMMessage(role="user", content="Request 2")],
        temperature=0.7,
        model="gpt-4",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":"Response"}}]}'
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        # ACT
        chunks1 = []
        async for chunk in provider.generate_stream(request1):
            chunks1.append(chunk)

        chunks2 = []
        async for chunk in provider.generate_stream(request2):
            chunks2.append(chunk)

        # ASSERT
        assert chunks1 == ["Response"]
        assert chunks2 == ["Response"]
        assert mock_post.call_count == 2

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openrouter_done_marker_stops_stream():
    """Test [DONE] marker immediately stops stream processing"""
    # ARRANGE
    provider = OpenRouterProvider(api_key="test_key")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="gpt-4",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":"Before"}}]}'
        yield "data: [DONE]"
        yield 'data: {"choices":[{"delta":{"content":"After"}}]}'  # Should not be processed

    mock_response.aiter_lines = mock_aiter_lines
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        # ACT
        chunks = []
        async for chunk in provider.generate_stream(request):
            chunks.append(chunk)

        # ASSERT
        assert chunks == ["Before"]  # "After" not included

    await provider.close()
