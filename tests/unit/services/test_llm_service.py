"""
Unit tests for LLMService

Tests LLM provider routing, streaming support, fallback logic, health monitoring,
and error handling.
"""
import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

from src.services.llm_service import (
    LLMService,
    LLMConfig,
    ProviderType,
)
from src.llm import (
    LLMProvider,
    LLMMessage,
    LLMRequest,
    LLMError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMConnectionError,
    LLMAuthenticationError,
)


# ============================================================
# Initialization Tests
# ============================================================

@pytest.mark.asyncio
async def test_init_with_openrouter_only():
    """Test initialization with OpenRouter API key"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)
        mock_factory.return_value = mock_provider

        service = LLMService(openrouter_api_key="test_key_123")

        assert service.openrouter_api_key == "test_key_123"
        assert ProviderType.OPENROUTER in service._providers
        assert service._providers[ProviderType.OPENROUTER] == mock_provider


@pytest.mark.asyncio
async def test_init_with_local_only():
    """Test initialization with local LLM base URL"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)
        mock_factory.return_value = mock_provider

        service = LLMService(
            openrouter_api_key=None,
            local_base_url="http://localhost:11434/v1"
        )

        # OpenRouter should be disabled
        assert service._providers[ProviderType.OPENROUTER] is None
        # Local should be initialized
        assert service._providers[ProviderType.LOCAL] == mock_provider


@pytest.mark.asyncio
async def test_init_with_both_providers():
    """Test initialization with both providers"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)
        mock_factory.return_value = mock_provider

        service = LLMService(
            openrouter_api_key="test_key",
            local_base_url="http://localhost:11434/v1"
        )

        # Both should be initialized
        assert service._providers[ProviderType.OPENROUTER] is not None
        assert service._providers[ProviderType.LOCAL] is not None


@pytest.mark.asyncio
async def test_init_fallback_disabled():
    """Test initialization with fallback disabled"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)
        mock_factory.return_value = mock_provider

        service = LLMService(
            openrouter_api_key="test_key",
            fallback_enabled=False
        )

        assert service.fallback_enabled is False


# ============================================================
# Provider Routing Tests
# ============================================================

@pytest.mark.asyncio
async def test_generate_response_openrouter():
    """Test routing to OpenRouter provider"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        # Mock OpenRouter provider
        mock_openrouter = AsyncMock(spec=LLMProvider)

        async def mock_stream(*args, **kwargs):
            yield "Hello"
            yield " world"

        mock_openrouter.generate_stream = mock_stream

        # Mock local provider (shouldn't be called)
        mock_local = AsyncMock(spec=LLMProvider)

        mock_factory.side_effect = [mock_openrouter, mock_local]

        service = LLMService(
            openrouter_api_key="test_key",
            local_base_url="http://localhost:11434/v1"
        )

        # Create config for OpenRouter
        config = LLMConfig(
            provider=ProviderType.OPENROUTER,
            model="gpt-4",
            temperature=0.7
        )

        # Generate response
        response = await service.generate_response(
            session_id=str(uuid4()),
            messages=[{"role": "user", "content": "Hello"}],
            config=config,
            stream=False
        )

        assert response == "Hello world"


@pytest.mark.asyncio
async def test_generate_response_local():
    """Test routing to local LLM provider"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        # Mock local provider
        mock_local = AsyncMock(spec=LLMProvider)

        async def mock_stream(*args, **kwargs):
            yield "Response from"
            yield " local LLM"

        mock_local.generate_stream = mock_stream

        mock_factory.return_value = mock_local

        service = LLMService(
            openrouter_api_key=None,
            local_base_url="http://localhost:11434/v1"
        )

        # Create config for local
        config = LLMConfig(
            provider=ProviderType.LOCAL,
            model="llama3",
            temperature=0.7
        )

        # Generate response
        response = await service.generate_response(
            session_id=str(uuid4()),
            messages=[{"role": "user", "content": "Hello"}],
            config=config,
            stream=False
        )

        assert response == "Response from local LLM"


# ============================================================
# Streaming Tests
# ============================================================

@pytest.mark.asyncio
async def test_streaming_response_callback():
    """Test streaming with callback"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)

        async def mock_stream(*args, **kwargs):
            yield "Chunk "
            yield "1 "
            yield "2 "
            yield "3"

        mock_provider.generate_stream = mock_stream
        mock_factory.return_value = mock_provider

        service = LLMService(local_base_url="http://localhost:11434/v1")

        # Track callback calls
        callback_chunks = []

        async def callback(chunk):
            callback_chunks.append(chunk)

        config = LLMConfig(
            provider=ProviderType.LOCAL,
            model="llama3",
            temperature=0.7
        )

        # Generate with streaming callback
        response = await service.generate_response(
            session_id=str(uuid4()),
            messages=[{"role": "user", "content": "Test"}],
            config=config,
            stream=True,
            callback=callback
        )

        # Verify callback was called for each chunk
        assert len(callback_chunks) == 4
        assert callback_chunks == ["Chunk ", "1 ", "2 ", "3"]
        assert response == "Chunk 1 2 3"


@pytest.mark.asyncio
async def test_non_streaming_response():
    """Test non-streaming (buffered) response"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)

        async def mock_stream(*args, **kwargs):
            yield "Complete "
            yield "response"

        mock_provider.generate_stream = mock_stream
        mock_factory.return_value = mock_provider

        service = LLMService(local_base_url="http://localhost:11434/v1")

        config = LLMConfig(
            provider=ProviderType.LOCAL,
            model="llama3",
            temperature=0.7
        )

        # Generate without streaming (no callback)
        response = await service.generate_response(
            session_id=str(uuid4()),
            messages=[{"role": "user", "content": "Test"}],
            config=config,
            stream=False
        )

        assert response == "Complete response"


@pytest.mark.asyncio
async def test_streaming_callback_sync():
    """Test streaming with synchronous callback"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)

        async def mock_stream(*args, **kwargs):
            yield "Test"

        mock_provider.generate_stream = mock_stream
        mock_factory.return_value = mock_provider

        service = LLMService(local_base_url="http://localhost:11434/v1")

        # Sync callback
        callback_calls = []

        def sync_callback(chunk):
            callback_calls.append(chunk)

        config = LLMConfig(
            provider=ProviderType.LOCAL,
            model="llama3",
            temperature=0.7
        )

        await service.generate_response(
            session_id=str(uuid4()),
            messages=[{"role": "user", "content": "Test"}],
            config=config,
            stream=True,
            callback=sync_callback
        )

        assert len(callback_calls) == 1


# ============================================================
# Fallback Tests
# ============================================================

@pytest.mark.asyncio
async def test_fallback_openrouter_to_local():
    """Test fallback from OpenRouter to local on transient error"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        # Mock OpenRouter provider (fails with timeout)
        mock_openrouter = AsyncMock(spec=LLMProvider)

        async def failing_stream(*args, **kwargs):
            raise LLMTimeoutError("Request timed out")
            yield  # Never reached

        mock_openrouter.generate_stream = failing_stream

        # Mock local provider (succeeds)
        mock_local = AsyncMock(spec=LLMProvider)

        async def successful_stream(*args, **kwargs):
            yield "Fallback response"

        mock_local.generate_stream = successful_stream

        mock_factory.side_effect = [mock_openrouter, mock_local]

        service = LLMService(
            openrouter_api_key="test_key",
            local_base_url="http://localhost:11434/v1",
            fallback_enabled=True
        )

        config = LLMConfig(
            provider=ProviderType.OPENROUTER,
            model="gpt-4",
            temperature=0.7
        )

        # Should fallback to local
        response = await service.generate_response(
            session_id=str(uuid4()),
            messages=[{"role": "user", "content": "Test"}],
            config=config,
            stream=False
        )

        assert response == "Fallback response"


@pytest.mark.asyncio
async def test_no_fallback_on_auth_error():
    """Test no fallback on authentication error"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_openrouter = AsyncMock(spec=LLMProvider)

        async def auth_error_stream(*args, **kwargs):
            raise LLMAuthenticationError("Invalid API key")
            yield

        mock_openrouter.generate_stream = auth_error_stream

        mock_local = AsyncMock(spec=LLMProvider)
        mock_factory.side_effect = [mock_openrouter, mock_local]

        service = LLMService(
            openrouter_api_key="invalid_key",
            local_base_url="http://localhost:11434/v1",
            fallback_enabled=True
        )

        config = LLMConfig(
            provider=ProviderType.OPENROUTER,
            model="gpt-4",
            temperature=0.7
        )

        # Should raise auth error (no fallback)
        with pytest.raises(LLMAuthenticationError):
            await service.generate_response(
                session_id=str(uuid4()),
                messages=[{"role": "user", "content": "Test"}],
                config=config,
                stream=False
            )


@pytest.mark.asyncio
async def test_fallback_disabled():
    """Test fallback can be disabled via config"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_openrouter = AsyncMock(spec=LLMProvider)

        async def failing_stream(*args, **kwargs):
            raise LLMTimeoutError("Timeout")
            yield

        mock_openrouter.generate_stream = failing_stream

        mock_local = AsyncMock(spec=LLMProvider)
        mock_factory.side_effect = [mock_openrouter, mock_local]

        service = LLMService(
            openrouter_api_key="test_key",
            local_base_url="http://localhost:11434/v1",
            fallback_enabled=False
        )

        config = LLMConfig(
            provider=ProviderType.OPENROUTER,
            model="gpt-4",
            temperature=0.7
        )

        # Should raise error (fallback disabled)
        with pytest.raises(LLMTimeoutError):
            await service.generate_response(
                session_id=str(uuid4()),
                messages=[{"role": "user", "content": "Test"}],
                config=config,
                stream=False
            )


@pytest.mark.asyncio
async def test_no_fallback_for_local_provider():
    """Test no fallback when local provider fails"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_local = AsyncMock(spec=LLMProvider)

        async def failing_stream(*args, **kwargs):
            raise LLMConnectionError("Connection failed")
            yield

        mock_local.generate_stream = failing_stream
        mock_factory.return_value = mock_local

        service = LLMService(
            openrouter_api_key=None,
            local_base_url="http://localhost:11434/v1",
            fallback_enabled=True
        )

        config = LLMConfig(
            provider=ProviderType.LOCAL,
            model="llama3",
            temperature=0.7
        )

        # Should raise error (no fallback for local)
        with pytest.raises(LLMConnectionError):
            await service.generate_response(
                session_id=str(uuid4()),
                messages=[{"role": "user", "content": "Test"}],
                config=config,
                stream=False
            )


# ============================================================
# Health Monitoring Tests
# ============================================================

@pytest.mark.asyncio
async def test_get_provider_status():
    """Test provider health status retrieval"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        # Mock providers with health check
        mock_openrouter = AsyncMock(spec=LLMProvider)
        mock_openrouter.health_check = AsyncMock(return_value=True)

        mock_local = AsyncMock(spec=LLMProvider)
        mock_local.health_check = AsyncMock(return_value=False)

        mock_factory.side_effect = [mock_openrouter, mock_local]

        service = LLMService(
            openrouter_api_key="test_key",
            local_base_url="http://localhost:11434/v1"
        )

        # Get provider status
        status = await service.get_provider_status()

        assert status['openrouter'] is True
        assert status['local'] is False


@pytest.mark.asyncio
async def test_test_provider_health():
    """Test individual provider health check"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)
        mock_provider.health_check = AsyncMock(return_value=True)
        mock_factory.return_value = mock_provider

        service = LLMService(local_base_url="http://localhost:11434/v1")

        # Test specific provider
        is_healthy = await service.test_provider_health(ProviderType.LOCAL)

        assert is_healthy is True
        mock_provider.health_check.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_failure():
    """Test health check when provider fails"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)
        mock_provider.health_check = AsyncMock(side_effect=Exception("Health check failed"))
        mock_factory.return_value = mock_provider

        service = LLMService(local_base_url="http://localhost:11434/v1")

        # Should return False on exception
        is_healthy = await service.test_provider_health(ProviderType.LOCAL)

        assert is_healthy is False


# ============================================================
# Error Handling Tests
# ============================================================

@pytest.mark.asyncio
async def test_timeout_error():
    """Test handling of LLM timeout"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)

        async def timeout_stream(*args, **kwargs):
            raise LLMTimeoutError("Request timeout")
            yield

        mock_provider.generate_stream = timeout_stream
        mock_factory.return_value = mock_provider

        service = LLMService(
            local_base_url="http://localhost:11434/v1",
            fallback_enabled=False
        )

        config = LLMConfig(
            provider=ProviderType.LOCAL,
            model="llama3",
            temperature=0.7
        )

        with pytest.raises(LLMTimeoutError):
            await service.generate_response(
                session_id=str(uuid4()),
                messages=[{"role": "user", "content": "Test"}],
                config=config,
                stream=False
            )


@pytest.mark.asyncio
async def test_rate_limit_error():
    """Test handling of rate limiting (triggers fallback if enabled)"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        # OpenRouter rate limited
        mock_openrouter = AsyncMock(spec=LLMProvider)

        async def rate_limit_stream(*args, **kwargs):
            raise LLMRateLimitError("Rate limit exceeded")
            yield

        mock_openrouter.generate_stream = rate_limit_stream

        # Local succeeds
        mock_local = AsyncMock(spec=LLMProvider)

        async def success_stream(*args, **kwargs):
            yield "Fallback success"

        mock_local.generate_stream = success_stream

        mock_factory.side_effect = [mock_openrouter, mock_local]

        service = LLMService(
            openrouter_api_key="test_key",
            local_base_url="http://localhost:11434/v1",
            fallback_enabled=True
        )

        config = LLMConfig(
            provider=ProviderType.OPENROUTER,
            model="gpt-4",
            temperature=0.7
        )

        # Should fallback to local
        response = await service.generate_response(
            session_id=str(uuid4()),
            messages=[{"role": "user", "content": "Test"}],
            config=config,
            stream=False
        )

        assert response == "Fallback success"


@pytest.mark.asyncio
async def test_connection_error():
    """Test handling of connection errors"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)

        async def connection_error_stream(*args, **kwargs):
            raise LLMConnectionError("Cannot connect")
            yield

        mock_provider.generate_stream = connection_error_stream
        mock_factory.return_value = mock_provider

        service = LLMService(
            local_base_url="http://localhost:11434/v1",
            fallback_enabled=False
        )

        config = LLMConfig(
            provider=ProviderType.LOCAL,
            model="llama3",
            temperature=0.7
        )

        with pytest.raises(LLMConnectionError):
            await service.generate_response(
                session_id=str(uuid4()),
                messages=[{"role": "user", "content": "Test"}],
                config=config,
                stream=False
            )


@pytest.mark.asyncio
async def test_provider_unavailable():
    """Test error when requested provider is unavailable"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        # Only local provider initialized
        mock_local = AsyncMock(spec=LLMProvider)
        mock_factory.return_value = mock_local

        service = LLMService(
            openrouter_api_key=None,  # No OpenRouter
            local_base_url="http://localhost:11434/v1"
        )

        # Try to use OpenRouter (unavailable)
        config = LLMConfig(
            provider=ProviderType.OPENROUTER,
            model="gpt-4",
            temperature=0.7
        )

        with pytest.raises(LLMError, match="not available"):
            await service.generate_response(
                session_id=str(uuid4()),
                messages=[{"role": "user", "content": "Test"}],
                config=config,
                stream=False
            )


# ============================================================
# Cleanup Tests
# ============================================================

@pytest.mark.asyncio
async def test_close():
    """Test closing all provider connections"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_openrouter = AsyncMock(spec=LLMProvider)
        mock_openrouter.close = AsyncMock()

        mock_local = AsyncMock(spec=LLMProvider)
        mock_local.close = AsyncMock()

        mock_factory.side_effect = [mock_openrouter, mock_local]

        service = LLMService(
            openrouter_api_key="test_key",
            local_base_url="http://localhost:11434/v1"
        )

        # Close service
        await service.close()

        # Verify both providers closed
        mock_openrouter.close.assert_called_once()
        mock_local.close.assert_called_once()


@pytest.mark.asyncio
async def test_context_manager():
    """Test async context manager (auto-close)"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)
        mock_provider.close = AsyncMock()
        mock_factory.return_value = mock_provider

        async with LLMService(local_base_url="http://localhost:11434/v1") as service:
            # Service is active
            assert service is not None

        # Should auto-close after context exit
        mock_provider.close.assert_called_once()


@pytest.mark.asyncio
async def test_callback_error_does_not_crash():
    """Test that callback errors don't crash generation"""
    with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock(spec=LLMProvider)

        async def mock_stream(*args, **kwargs):
            yield "Test"

        mock_provider.generate_stream = mock_stream
        mock_factory.return_value = mock_provider

        service = LLMService(local_base_url="http://localhost:11434/v1")

        # Callback that raises exception
        async def failing_callback(chunk):
            raise Exception("Callback failed")

        config = LLMConfig(
            provider=ProviderType.LOCAL,
            model="llama3",
            temperature=0.7
        )

        # Should not crash (callback errors are caught)
        response = await service.generate_response(
            session_id=str(uuid4()),
            messages=[{"role": "user", "content": "Test"}],
            config=config,
            stream=True,
            callback=failing_callback
        )

        assert response == "Test"
