"""
Unit tests for Local LLM provider.

Tests streaming responses, error handling, retry logic, and health checks
for OpenAI-compatible local LLM endpoints (Ollama, vLLM, etc.).
"""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from src.llm.local_llm import LocalLLMProvider
from src.llm.types import (
    LLMMessage,
    LLMRequest,
    LLMError,
    LLMTimeoutError,
    LLMConnectionError,
)


# ============================================================
# Provider Initialization Tests
# ============================================================


@pytest.mark.unit
def test_local_llm_initialization():
    """Test Local LLM provider initialization"""
    # ACT
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    # ASSERT
    assert provider.base_url == "http://localhost:11434/v1"
    assert provider.api_key is None
    assert provider.client is not None


@pytest.mark.unit
def test_local_llm_initialization_with_api_key():
    """Test Local LLM provider initialization with optional API key"""
    # ACT
    provider = LocalLLMProvider(
        base_url="http://localhost:1234/v1",
        api_key="optional_key",
    )

    # ASSERT
    assert provider.api_key == "optional_key"


@pytest.mark.unit
def test_local_llm_initialization_missing_base_url():
    """Test Local LLM provider fails without base URL"""
    # ACT & ASSERT
    with pytest.raises(ValueError) as exc_info:
        LocalLLMProvider(base_url="")

    assert "Base URL is required" in str(exc_info.value)


@pytest.mark.unit
def test_local_llm_strips_trailing_slash():
    """Test Local LLM provider strips trailing slash from base URL"""
    # ACT
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1/")

    # ASSERT
    assert provider.base_url == "http://localhost:11434/v1"


@pytest.mark.unit
def test_local_llm_no_trailing_slash_preserved():
    """Test Local LLM provider preserves URL without trailing slash"""
    # ACT
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    # ASSERT
    assert provider.base_url == "http://localhost:11434/v1"


# ============================================================
# Streaming Response Tests
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_streaming_success():
    """Test Local LLM provider streaming response"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Hello")],
        temperature=0.7,
        model="llama3:8b",
    )

    # Mock SSE response
    mock_response = AsyncMock()
    mock_response.status_code = 200

    # Simulate SSE stream
    async def mock_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
        yield 'data: {"choices":[{"delta":{"content":" from"}}]}'
        yield 'data: {"choices":[{"delta":{"content":" Ollama"}}]}'
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
        assert chunks == ["Hello", " from", " Ollama"]
        mock_post.assert_called_once()

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_streaming_with_max_tokens():
    """Test Local LLM streaming includes max_tokens in request"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.5,
        model="llama3:8b",
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
async def test_local_llm_streaming_no_max_tokens():
    """Test Local LLM streaming omits max_tokens if None"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
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
async def test_local_llm_streaming_request_headers():
    """Test Local LLM includes correct headers in request"""
    # ARRANGE
    provider = LocalLLMProvider(
        base_url="http://localhost:11434/v1",
        api_key="optional_key",
    )

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
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
        assert headers["Authorization"] == "Bearer optional_key"
        assert headers["Content-Type"] == "application/json"

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_streaming_no_auth_header():
    """Test Local LLM omits Authorization header if no API key"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
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
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_streaming_empty_chunks():
    """Test Local LLM handles empty content in SSE chunks"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
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
async def test_local_llm_streaming_malformed_json():
    """Test Local LLM handles malformed JSON in SSE stream"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
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
async def test_local_llm_timeout_error():
    """Test Local LLM provider timeout handling"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
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
async def test_local_llm_connection_error():
    """Test Local LLM provider connection error (server not running)"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
    )

    # Mock connection error
    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.RequestError("Connection refused")

        # ACT & ASSERT
        with pytest.raises(LLMConnectionError) as exc_info:
            async for chunk in provider.generate_stream(request):
                pass

        assert "connection" in str(exc_info.value).lower()

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_unexpected_error():
    """Test Local LLM provider handles unexpected errors"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
    )

    # Mock unexpected error
    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = RuntimeError("Unexpected error")

        # ACT & ASSERT
        with pytest.raises(LLMError) as exc_info:
            async for chunk in provider.generate_stream(request):
                pass

        assert "unexpected" in str(exc_info.value).lower()

    await provider.close()


# ============================================================
# Health Check Tests
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_health_check_success():
    """Test Local LLM health check passes with 200 response"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

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
async def test_local_llm_health_check_with_api_key():
    """Test Local LLM health check includes Authorization header if API key set"""
    # ARRANGE
    provider = LocalLLMProvider(
        base_url="http://localhost:11434/v1",
        api_key="test_key",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        # ACT
        result = await provider.health_check()

        # ASSERT
        assert result is True
        call_args = mock_get.call_args
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer test_key"

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_health_check_fallback():
    """Test Local LLM health check falls back to root endpoint"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    mock_models_response = AsyncMock()
    mock_models_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not found", request=MagicMock(), response=MagicMock()
    )

    mock_root_response = AsyncMock()
    mock_root_response.status_code = 200

    with patch.object(provider.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [
            mock_models_response,  # /models fails
            mock_root_response,  # root succeeds
        ]

        # ACT
        result = await provider.health_check()

        # ASSERT
        assert result is True
        assert mock_get.call_count == 2

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_health_check_fallback_non_5xx():
    """Test Local LLM health check accepts non-5xx status as alive"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    mock_root_response = AsyncMock()
    mock_root_response.status_code = 404  # Not found, but server is alive

    with patch.object(provider.client, "get", new_callable=AsyncMock) as mock_get:
        # First call (/models) raises exception
        # Second call (root) returns 404
        mock_get.side_effect = [
            httpx.RequestError("Models endpoint failed"),
            mock_root_response,
        ]

        # ACT
        result = await provider.health_check()

        # ASSERT
        assert result is True  # 404 is acceptable (server is alive)

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_health_check_failure():
    """Test Local LLM health check fails when all attempts fail"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    with patch.object(provider.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.RequestError("Connection failed")

        # ACT
        result = await provider.health_check()

        # ASSERT
        assert result is False
        assert mock_get.call_count == 2  # Primary + fallback

    await provider.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_health_check_timeout():
    """Test Local LLM health check handles timeout"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

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
async def test_local_llm_context_manager():
    """Test Local LLM provider as async context manager"""
    # ACT & ASSERT
    async with LocalLLMProvider(base_url="http://localhost:11434/v1") as provider:
        assert provider is not None
        assert provider.base_url == "http://localhost:11434/v1"

    # Client should be closed after context exit


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_close():
    """Test Local LLM provider close method"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

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
async def test_local_llm_retry_on_connection_error():
    """Test Local LLM retries on transient connection errors"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
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
async def test_local_llm_retry_exhausted():
    """Test Local LLM exhausts retries and raises error"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_retry_on_timeout():
    """Test Local LLM retries on timeout errors"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":"Success"}}]}'
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines
    mock_response.raise_for_status = MagicMock()

    # Mock post to timeout once, then succeed
    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [
            httpx.TimeoutException("Timeout"),
            mock_response,
        ]

        # ACT
        chunks = []
        async for chunk in provider.generate_stream(request):
            chunks.append(chunk)

        # ASSERT
        assert chunks == ["Success"]
        assert mock_post.call_count == 2  # 1 retry + 1 success

    await provider.close()


# ============================================================
# Edge Case Tests
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_multiple_requests_same_provider():
    """Test Local LLM provider can handle multiple sequential requests"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request1 = LLMRequest(
        messages=[LLMMessage(role="user", content="Request 1")],
        temperature=0.7,
        model="llama3:8b",
    )
    request2 = LLMRequest(
        messages=[LLMMessage(role="user", content="Request 2")],
        temperature=0.7,
        model="llama3:8b",
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
async def test_local_llm_done_marker_stops_stream():
    """Test [DONE] marker immediately stops stream processing"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_llm_url_construction():
    """Test Local LLM constructs correct API endpoint URL"""
    # ARRANGE
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        temperature=0.7,
        model="llama3:8b",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        # ACT
        async for _ in provider.generate_stream(request):
            pass

        # ASSERT
        call_args = mock_post.call_args
        url = call_args.args[0]
        assert url == "http://localhost:11434/v1/chat/completions"

    await provider.close()
