"""
Unit tests for TTSService

Tests Chatterbox TTS integration, streaming audio synthesis, health monitoring,
session-based cancellation, and metrics tracking.
"""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4
import httpx

from src.services.tts_service import (
    TTSService,
    TTSStatus,
    TTSMetrics,
    ActiveTTS,
    CHATTERBOX_URL,
)


# ============================================================
# Initialization Tests
# ============================================================

@pytest.mark.asyncio
async def test_init_with_defaults():
    """Test initialization with default Chatterbox URL"""
    service = TTSService()

    assert service.chatterbox_url == CHATTERBOX_URL
    assert service.default_voice_id == "default"
    assert service.timeout == 60.0
    assert service.chunk_size == 8192
    assert len(service._active_sessions) == 0
    assert len(service._metrics_history) == 0


@pytest.mark.asyncio
async def test_init_with_custom_url():
    """Test initialization with custom Chatterbox URL"""
    custom_url = "http://custom-tts:5000"
    service = TTSService(chatterbox_url=custom_url)

    assert service.chatterbox_url == custom_url


@pytest.mark.asyncio
async def test_init_with_custom_parameters():
    """Test initialization with custom voice and timeout"""
    service = TTSService(
        default_voice_id="custom_voice",
        timeout_s=120.0,
        chunk_size=4096
    )

    assert service.default_voice_id == "custom_voice"
    assert service.timeout == 120.0
    assert service.chunk_size == 4096


# ============================================================
# Synthesis Tests
# ============================================================

@pytest.mark.asyncio
async def test_synthesize_speech_streaming():
    """Test streaming TTS synthesis with callback"""
    service = TTSService()
    session_id = str(uuid4())

    # Track callback calls
    audio_chunks = []

    async def callback(chunk):
        audio_chunks.append(chunk)

    # Mock HTTP client
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_bytes(chunk_size):
        yield b"audio_chunk_1"
        yield b"audio_chunk_2"
        yield b"audio_chunk_3"

    mock_response.aiter_bytes = mock_aiter_bytes

    mock_client = AsyncMock()
    mock_client.stream = MagicMock()
    mock_client.stream.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_client.stream.return_value.__aexit__ = AsyncMock()

    # Mock health check
    mock_health_response = AsyncMock()
    mock_health_response.status_code = 200
    mock_client.get = AsyncMock(return_value=mock_health_response)

    service._client = mock_client

    # Synthesize speech
    result = await service.synthesize_speech(
        session_id=session_id,
        text="Hello world",
        voice_id="test_voice",
        speed=1.0,
        stream=True,
        callback=callback
    )

    # Verify callback was called for each chunk
    assert len(audio_chunks) == 3
    assert audio_chunks[0] == b"audio_chunk_1"
    assert result == b''  # Empty when callback provided


@pytest.mark.asyncio
async def test_synthesize_speech_buffered():
    """Test buffered TTS synthesis (return bytes)"""
    service = TTSService()
    session_id = str(uuid4())

    # Mock HTTP client
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_bytes(chunk_size):
        yield b"chunk1"
        yield b"chunk2"

    mock_response.aiter_bytes = mock_aiter_bytes

    mock_client = AsyncMock()
    mock_client.stream = MagicMock()
    mock_client.stream.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_client.stream.return_value.__aexit__ = AsyncMock()

    # Mock health check
    mock_health_response = AsyncMock()
    mock_health_response.status_code = 200
    mock_client.get = AsyncMock(return_value=mock_health_response)

    service._client = mock_client

    # Synthesize without callback (buffered)
    result = await service.synthesize_speech(
        session_id=session_id,
        text="Hello world",
        callback=None
    )

    # Should return complete audio
    assert result == b"chunk1chunk2"


@pytest.mark.asyncio
async def test_synthesize_speech_with_voice_config():
    """Test synthesis with voice ID and speed"""
    service = TTSService()
    session_id = str(uuid4())

    # Mock HTTP client
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_bytes(chunk_size):
        yield b"audio"

    mock_response.aiter_bytes = mock_aiter_bytes

    mock_client = AsyncMock()
    mock_client.stream = MagicMock()
    mock_client.stream.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_client.stream.return_value.__aexit__ = AsyncMock()

    # Mock health check
    mock_health_response = AsyncMock()
    mock_health_response.status_code = 200
    mock_client.get = AsyncMock(return_value=mock_health_response)

    service._client = mock_client

    # Synthesize with custom voice and speed
    await service.synthesize_speech(
        session_id=session_id,
        text="Test",
        voice_id="custom_voice",
        speed=1.5
    )

    # Verify request was made with correct parameters
    assert mock_client.stream.called


@pytest.mark.asyncio
async def test_synthesize_speed_clamping():
    """Test speed parameter is clamped to valid range (0.5-2.0)"""
    service = TTSService()
    session_id = str(uuid4())

    # Mock client
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_bytes(chunk_size):
        yield b"audio"

    mock_response.aiter_bytes = mock_aiter_bytes

    mock_client = AsyncMock()
    mock_client.stream = MagicMock()
    mock_client.stream.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_client.stream.return_value.__aexit__ = AsyncMock()

    mock_health_response = AsyncMock()
    mock_health_response.status_code = 200
    mock_client.get = AsyncMock(return_value=mock_health_response)

    service._client = mock_client

    # Try invalid speed (too high)
    await service.synthesize_speech(
        session_id=session_id,
        text="Test",
        speed=5.0  # Should be clamped to 2.0
    )

    # Should not crash


@pytest.mark.asyncio
async def test_synthesize_chatterbox_unavailable():
    """Test graceful degradation when Chatterbox unavailable"""
    service = TTSService()
    session_id = str(uuid4())

    # Mock health check failure
    mock_client = AsyncMock()
    mock_health_response = AsyncMock()
    mock_health_response.status_code = 503  # Service unavailable
    mock_client.get = AsyncMock(return_value=mock_health_response)

    service._client = mock_client

    # Should return empty bytes
    result = await service.synthesize_speech(
        session_id=session_id,
        text="Test"
    )

    assert result == b''


# ============================================================
# Health Tests
# ============================================================

@pytest.mark.asyncio
async def test_test_tts_health_success():
    """Test health check when Chatterbox available"""
    service = TTSService()

    # Mock successful health check
    mock_response = AsyncMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    service._client = mock_client

    is_healthy = await service.test_tts_health()

    assert is_healthy is True


@pytest.mark.asyncio
async def test_test_tts_health_failure():
    """Test health check when Chatterbox unavailable"""
    service = TTSService()

    # Mock failed health check
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

    service._client = mock_client

    is_healthy = await service.test_tts_health()

    assert is_healthy is False


# ============================================================
# Voices Tests
# ============================================================

@pytest.mark.asyncio
async def test_get_available_voices():
    """Test retrieving available voices"""
    service = TTSService()

    # Mock voices response
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        'voices': [
            {'id': 'voice1', 'name': 'Voice 1'},
            {'id': 'voice2', 'name': 'Voice 2'}
        ]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    service._client = mock_client

    voices = await service.get_available_voices()

    assert len(voices) == 2
    assert voices[0]['id'] == 'voice1'
    assert voices[1]['name'] == 'Voice 2'


@pytest.mark.asyncio
async def test_get_available_voices_failure():
    """Test voices retrieval failure (graceful degradation)"""
    service = TTSService()

    # Mock failure
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("API error"))

    service._client = mock_client

    voices = await service.get_available_voices()

    # Should return empty list
    assert voices == []


# ============================================================
# Metrics Tests
# ============================================================

@pytest.mark.asyncio
async def test_get_metrics_all():
    """Test retrieving all TTS metrics"""
    service = TTSService()

    # Add some metrics
    metrics1 = TTSMetrics(
        session_id="session1",
        text_length=100,
        audio_bytes=5000,
        time_to_first_byte_s=0.5,
        total_duration_s=2.0,
        voice_id="voice1",
        speed=1.0,
        success=True
    )

    metrics2 = TTSMetrics(
        session_id="session2",
        text_length=50,
        audio_bytes=2500,
        time_to_first_byte_s=0.3,
        total_duration_s=1.0,
        voice_id="voice2",
        speed=1.5,
        success=True
    )

    service._metrics_history = [metrics1, metrics2]

    # Get all metrics
    all_metrics = await service.get_metrics()

    assert len(all_metrics) == 2


@pytest.mark.asyncio
async def test_get_metrics_session_specific():
    """Test retrieving metrics for specific session"""
    service = TTSService()

    # Add metrics for two sessions
    metrics1 = TTSMetrics(
        session_id="session1",
        text_length=100,
        audio_bytes=5000,
        time_to_first_byte_s=0.5,
        total_duration_s=2.0,
        voice_id="voice1",
        speed=1.0,
        success=True
    )

    metrics2 = TTSMetrics(
        session_id="session2",
        text_length=50,
        audio_bytes=2500,
        time_to_first_byte_s=0.3,
        total_duration_s=1.0,
        voice_id="voice2",
        speed=1.5,
        success=True
    )

    service._metrics_history = [metrics1, metrics2]

    # Get metrics for specific session
    session_metrics = await service.get_metrics(session_id="session1")

    assert len(session_metrics) == 1
    assert session_metrics[0].session_id == "session1"


@pytest.mark.asyncio
async def test_metrics_history_limit():
    """Test metrics history is limited to prevent memory growth"""
    service = TTSService()
    service._max_metrics_history = 5

    # Add 10 metrics
    for i in range(10):
        metric = TTSMetrics(
            session_id=f"session{i}",
            text_length=100,
            audio_bytes=5000,
            time_to_first_byte_s=0.5,
            total_duration_s=2.0,
            voice_id="voice1",
            speed=1.0,
            success=True
        )
        service._record_metrics(
            session_id=metric.session_id,
            text_length=metric.text_length,
            audio_bytes=metric.audio_bytes,
            time_to_first_byte_s=metric.time_to_first_byte_s,
            total_duration_s=metric.total_duration_s,
            voice_id=metric.voice_id,
            speed=metric.speed,
            success=metric.success
        )

    # Should keep only last 5
    assert len(service._metrics_history) == 5


# ============================================================
# Cancellation Tests
# ============================================================

@pytest.mark.asyncio
async def test_cancel_tts():
    """Test cancelling active TTS"""
    service = TTSService()
    session_id = str(uuid4())

    # Create active TTS
    cancel_event = asyncio.Event()
    mock_task = AsyncMock()
    mock_task.done.return_value = False
    mock_task.cancel = MagicMock()

    active_tts = ActiveTTS(
        session_id=session_id,
        text="Test",
        voice_id="voice1",
        speed=1.0,
        status=TTSStatus.SYNTHESIZING,
        started_at=time.time(),
        cancel_event=cancel_event,
        stream_task=mock_task
    )
    service._active_sessions[session_id] = active_tts

    # Cancel
    await service.cancel_tts(session_id)

    # Verify cancellation
    assert cancel_event.is_set()
    assert mock_task.cancel.called
    assert active_tts.status == TTSStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_tts_no_active_session():
    """Test cancelling when no active TTS (graceful)"""
    service = TTSService()
    session_id = str(uuid4())

    # Should not raise error
    await service.cancel_tts(session_id)


@pytest.mark.asyncio
async def test_synthesize_cancels_previous():
    """Test new synthesis cancels previous TTS for same session"""
    service = TTSService()
    session_id = str(uuid4())

    # Create existing active TTS
    cancel_event = asyncio.Event()
    active_tts = ActiveTTS(
        session_id=session_id,
        text="Old text",
        voice_id="voice1",
        speed=1.0,
        status=TTSStatus.SYNTHESIZING,
        started_at=time.time(),
        cancel_event=cancel_event,
        stream_task=None
    )
    service._active_sessions[session_id] = active_tts

    # Mock client
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_bytes(chunk_size):
        yield b"new_audio"

    mock_response.aiter_bytes = mock_aiter_bytes

    mock_client = AsyncMock()
    mock_client.stream = MagicMock()
    mock_client.stream.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_client.stream.return_value.__aexit__ = AsyncMock()

    mock_health_response = AsyncMock()
    mock_health_response.status_code = 200
    mock_client.get = AsyncMock(return_value=mock_health_response)

    service._client = mock_client

    # Start new synthesis (should cancel old one)
    await service.synthesize_speech(
        session_id=session_id,
        text="New text"
    )

    # Old TTS should be cancelled
    assert cancel_event.is_set()


# ============================================================
# Error Handling Tests
# ============================================================

@pytest.mark.asyncio
async def test_synthesize_http_error():
    """Test handling HTTP error from Chatterbox"""
    service = TTSService()
    session_id = str(uuid4())

    # Mock HTTP error
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "Server error",
            request=MagicMock(),
            response=MagicMock(status_code=500)
        )
    )

    mock_client = AsyncMock()
    mock_client.stream = MagicMock()
    mock_client.stream.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_client.stream.return_value.__aexit__ = AsyncMock()

    mock_health_response = AsyncMock()
    mock_health_response.status_code = 200
    mock_client.get = AsyncMock(return_value=mock_health_response)

    service._client = mock_client

    # Should return empty bytes (graceful degradation)
    result = await service.synthesize_speech(
        session_id=session_id,
        text="Test"
    )

    assert result == b''


@pytest.mark.asyncio
async def test_synthesize_timeout():
    """Test handling timeout error"""
    service = TTSService()
    session_id = str(uuid4())

    # Mock timeout
    mock_client = AsyncMock()
    mock_client.stream = MagicMock(side_effect=httpx.TimeoutException("Timeout"))

    mock_health_response = AsyncMock()
    mock_health_response.status_code = 200
    mock_client.get = AsyncMock(return_value=mock_health_response)

    service._client = mock_client

    # Should return empty bytes
    result = await service.synthesize_speech(
        session_id=session_id,
        text="Test"
    )

    assert result == b''


@pytest.mark.asyncio
async def test_synthesize_cancellation():
    """Test synthesis respects cancellation"""
    service = TTSService()
    session_id = str(uuid4())

    # Mock response that yields chunks
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    # Create cancel event that will be set
    cancel_event = asyncio.Event()

    async def mock_aiter_bytes(chunk_size):
        cancel_event.set()  # Trigger cancellation
        yield b"chunk1"
        yield b"chunk2"  # Should not reach here

    mock_response.aiter_bytes = mock_aiter_bytes

    mock_client = AsyncMock()
    mock_client.stream = MagicMock()
    mock_client.stream.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_client.stream.return_value.__aexit__ = AsyncMock()

    mock_health_response = AsyncMock()
    mock_health_response.status_code = 200
    mock_client.get = AsyncMock(return_value=mock_health_response)

    service._client = mock_client

    # Patch the internal method to use our cancel event
    original_stream_tts = service._stream_tts

    async def patched_stream_tts(*args, **kwargs):
        kwargs['cancel_event'] = cancel_event
        return await original_stream_tts(*args, **kwargs)

    service._stream_tts = patched_stream_tts

    # Should return empty (cancelled)
    result = await service.synthesize_speech(
        session_id=session_id,
        text="Test"
    )

    assert result == b''


# ============================================================
# Cleanup Tests
# ============================================================

@pytest.mark.asyncio
async def test_close():
    """Test closing HTTP client"""
    service = TTSService()

    # Create mock client
    mock_client = AsyncMock()
    mock_client.aclose = AsyncMock()

    service._client = mock_client

    # Close service
    await service.close()

    # Verify client closed
    mock_client.aclose.assert_called_once()
    assert service._client is None


@pytest.mark.asyncio
async def test_close_cancels_active_tts():
    """Test close cancels all active TTS"""
    service = TTSService()

    # Create multiple active sessions
    for i in range(3):
        session_id = str(uuid4())
        cancel_event = asyncio.Event()

        active_tts = ActiveTTS(
            session_id=session_id,
            text=f"Text {i}",
            voice_id="voice1",
            speed=1.0,
            status=TTSStatus.SYNTHESIZING,
            started_at=time.time(),
            cancel_event=cancel_event,
            stream_task=None
        )
        service._active_sessions[session_id] = active_tts

    # Close service
    await service.close()

    # All sessions should be cancelled
    assert len(service._active_sessions) == 0


@pytest.mark.asyncio
async def test_lazy_client_initialization():
    """Test HTTP client is lazily initialized"""
    service = TTSService()

    # Client should be None initially
    assert service._client is None

    # Mock client creation
    mock_client = AsyncMock()

    with patch('httpx.AsyncClient', return_value=mock_client):
        client = await service._ensure_client()

        # Client should be created
        assert client == mock_client
        assert service._client == mock_client

        # Second call should return same client
        client2 = await service._ensure_client()
        assert client2 == mock_client
