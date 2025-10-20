"""
Unit tests for SpeakerManager

Tests speaker lock management, transcription workflow, n8n integration,
silence detection, timeout enforcement, and cleanup
"""
from __future__ import annotations

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call
import httpx

from src.speaker_manager import SpeakerManager


# ============================================================
# Speaker Lock Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_speaker_lock_acquisition():
    """Test first speaker acquires lock"""
    manager = SpeakerManager()

    # Mock audio stream
    async def mock_audio_stream():
        yield b'\x00' * 960

    with patch.object(manager, '_start_transcription', new_callable=AsyncMock) as mock_start:
        with patch('asyncio.create_task') as mock_create_task:
            audio_gen = mock_audio_stream()
            result = await manager.on_speaking_start("user_123", audio_gen)

            # Assertions
            assert result is True
            assert manager.active_speaker == "user_123"
            assert manager.lock_start_time is not None
            assert manager.last_audio_time is not None

            # Verify _start_transcription was called with correct user_id
            mock_start.assert_called_once()
            assert mock_start.call_args[0][0] == "user_123"

            # Verify timeout task was created
            assert mock_create_task.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_speaker_lock_rejection_when_locked():
    """Test second speaker is rejected when lock is held"""
    manager = SpeakerManager()
    manager.active_speaker = "user_123"

    async def mock_audio_stream():
        yield b'\x00' * 960

    result = await manager.on_speaking_start("user_456", mock_audio_stream())

    # Assertions
    assert result is False
    assert manager.active_speaker == "user_123"  # Still first speaker


@pytest.mark.unit
@pytest.mark.asyncio
async def test_speaker_lock_release_after_silence():
    """Test lock is released after silence threshold"""
    manager = SpeakerManager()
    manager.silence_threshold_ms = 100  # Fast for testing
    manager.active_speaker = "user_123"
    manager.last_audio_time = time.time()
    manager.whisper_client = AsyncMock()
    manager.whisper_client.finalize = AsyncMock(return_value="test transcript")
    manager.whisper_client.close = AsyncMock()

    # Start silence monitor
    await manager._silence_monitor()

    # After silence threshold, finalization should be triggered
    # Lock should be released (active_speaker = None)
    assert manager.active_speaker is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_speaker_lock_timeout_enforcement():
    """Test lock is force released after max speaking time"""
    manager = SpeakerManager()
    manager.max_speaking_time_ms = 100  # Fast for testing
    manager.active_speaker = "user_123"
    manager.lock_start_time = time.time()
    manager.whisper_client = AsyncMock()
    manager.whisper_client.finalize = AsyncMock(return_value="test transcript")
    manager.whisper_client.close = AsyncMock()

    # Start timeout monitor
    await manager._timeout_monitor()

    # After timeout, finalization should be triggered
    # Lock should be released
    assert manager.active_speaker is None


# ============================================================
# Transcription Flow Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_transcription_creates_whisper_client():
    """Test WhisperClient is created and connected"""
    manager = SpeakerManager()

    async def mock_audio_stream():
        yield b'\x00' * 960

    with patch('src.speaker_manager.WhisperClient') as MockWhisperClient:
        mock_client = AsyncMock()
        MockWhisperClient.return_value = mock_client

        with patch('asyncio.create_task'):
            await manager._start_transcription("user_123", mock_audio_stream())

            # Assertions
            MockWhisperClient.assert_called_once()
            mock_client.connect.assert_called_once_with("user_123")
            assert manager.whisper_client == mock_client


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audio_forwarding_to_whisper():
    """Test audio chunks are forwarded to WhisperClient"""
    manager = SpeakerManager()

    # Create mock WhisperClient
    mock_client = AsyncMock()
    mock_client.is_connected = True
    mock_client.send_audio = AsyncMock()
    manager.whisper_client = mock_client

    # Create audio stream with 3 chunks
    async def mock_audio_stream():
        for i in range(3):
            yield b'\x00' * 960

    await manager._stream_audio(mock_audio_stream())

    # Verify all 3 chunks were sent
    assert mock_client.send_audio.call_count == 3
    assert manager.last_audio_time is not None


# ============================================================
# n8n Integration Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_to_n8n_non_streaming_mode():
    """Test sending transcript to n8n in non-streaming mode"""
    manager = SpeakerManager()
    manager.n8n_webhook_url = "http://localhost:8888/webhook/test"
    manager.use_streaming = False
    manager.active_speaker = "user_123"

    with patch('httpx.AsyncClient') as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        await manager._send_to_n8n("Hello world")

        # Verify POST was made
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://localhost:8888/webhook/test"
        assert call_args[1]['json']['text'] == "Hello world"
        assert call_args[1]['json']['userId'] == "user_123"
        assert call_args[1]['json']['useStreaming'] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_to_n8n_streaming_mode():
    """Test sending transcript to n8n in streaming mode"""
    manager = SpeakerManager()
    manager.n8n_webhook_url = "http://localhost:8888/webhook/test"
    manager.use_streaming = True
    manager.active_speaker = "user_123"
    manager.voice_connection = MagicMock()  # Mock voice connection

    with patch.object(manager, '_handle_streaming_response', new_callable=AsyncMock) as mock_handle:
        with patch('httpx.AsyncClient') as MockClient:
            mock_client = MockClient.return_value.__aenter__.return_value

            await manager._send_to_n8n("Hello world")

            # Verify streaming handler was called
            mock_handle.assert_called_once()
            # First arg is the client, second is payload
            call_args = mock_handle.call_args[0]
            payload = call_args[1]
            assert payload['text'] == "Hello world"
            assert payload['useStreaming'] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_to_n8n_retry_on_failure():
    """Test n8n webhook retries on network error"""
    manager = SpeakerManager()
    manager.n8n_webhook_url = "http://localhost:8888/webhook/test"
    manager.use_streaming = False
    manager.active_speaker = "user_123"

    with patch('httpx.AsyncClient') as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value

        # First 2 attempts fail, 3rd succeeds
        mock_success = AsyncMock()
        mock_success.status_code = 200
        mock_success.raise_for_status = MagicMock()

        mock_client.post = AsyncMock(side_effect=[
            httpx.TimeoutException("Timeout"),
            httpx.TimeoutException("Timeout"),
            mock_success
        ])

        # Should succeed after retries
        await manager._send_to_n8n("Hello world")

        # Verify 3 attempts were made
        assert mock_client.post.call_count == 3


# ============================================================
# Cleanup Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_cleanup_cancels_timeout_task():
    """Test cleanup cancels timeout monitoring task"""
    manager = SpeakerManager()
    manager.active_speaker = "user_123"

    # Create a mock task
    mock_task = MagicMock()
    mock_task.done.return_value = False
    mock_task.cancel = MagicMock()
    manager.timeout_task = mock_task

    # Mock asyncio.gather to avoid waiting
    with patch('asyncio.gather', new_callable=AsyncMock) as mock_gather:
        await manager._unlock()

        # Verify task was cancelled (check before it's set to None)
        mock_task.cancel.assert_called_once()
        mock_gather.assert_called_once()

        # Verify state reset
        assert manager.active_speaker is None
        assert manager.timeout_task is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cleanup_cancels_silence_task():
    """Test cleanup cancels silence monitoring task"""
    manager = SpeakerManager()
    manager.active_speaker = "user_123"

    # Create a mock task
    mock_task = MagicMock()
    mock_task.done.return_value = False
    mock_task.cancel = MagicMock()
    manager.silence_task = mock_task

    with patch('asyncio.gather', new_callable=AsyncMock) as mock_gather:
        await manager._unlock()

        # Verify task was cancelled (check before it's set to None)
        mock_task.cancel.assert_called_once()
        mock_gather.assert_called_once()

        # Verify state reset
        assert manager.silence_task is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cleanup_closes_whisper_client():
    """Test cleanup properly closes WhisperClient connection"""
    manager = SpeakerManager()
    manager.active_speaker = "user_123"
    manager.lock_start_time = time.time()

    # Create mock WhisperClient
    mock_client = AsyncMock()
    mock_client.finalize = AsyncMock(return_value="test transcript")
    mock_client.close = AsyncMock()
    manager.whisper_client = mock_client

    # Mock asyncio.gather to prevent task waiting
    with patch('asyncio.gather', new_callable=AsyncMock):
        # Finalize should close the client
        await manager._finalize_transcription('test')

        # Verify WhisperClient was finalized and closed (check mock before it's set to None)
        mock_client.finalize.assert_called_once()
        mock_client.close.assert_called_once()

        # Verify lock was released
        assert manager.active_speaker is None
        assert manager.whisper_client is None


# ============================================================
# Additional Behavior Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_on_audio_data_updates_silence_timer():
    """Test receiving audio data resets silence detection"""
    manager = SpeakerManager()
    manager.active_speaker = "user_123"
    manager.last_audio_time = time.time() - 1.0  # 1 second ago

    # Create mock silence task
    mock_task = MagicMock()
    mock_task.done = MagicMock(return_value=False)  # Synchronous return, not async
    mock_task.cancel = MagicMock()
    manager.silence_task = mock_task

    with patch.object(manager, '_start_silence_detection', new_callable=AsyncMock) as mock_start:
        initial_time = manager.last_audio_time

        await manager.on_audio_data("user_123")

        # Verify last_audio_time was updated
        assert manager.last_audio_time > initial_time

        # Verify silence task was cancelled and restarted
        mock_task.cancel.assert_called_once()
        mock_start.assert_called_once()


@pytest.mark.unit
def test_get_status_returns_correct_info():
    """Test get_status returns current manager state"""
    manager = SpeakerManager()

    # Test when no speaker
    status = manager.get_status()
    assert status['locked'] is False
    assert status['activeSpeaker'] is None

    # Test when speaker is active
    manager.active_speaker = "user_123"
    manager.lock_start_time = time.time()
    manager.last_audio_time = time.time()

    status = manager.get_status()
    assert status['locked'] is True
    assert status['activeSpeaker'] == "user_123"
    assert status['speakingDuration'] is not None
    assert status['silenceDuration'] is not None


@pytest.mark.unit
def test_set_voice_connection():
    """Test setting voice connection for streaming support"""
    manager = SpeakerManager()
    mock_voice = MagicMock()

    manager.set_voice_connection(mock_voice)

    assert manager.voice_connection == mock_voice


@pytest.mark.unit
def test_set_streaming_handler():
    """Test setting streaming response handler"""
    manager = SpeakerManager()
    mock_handler = MagicMock()

    manager.set_streaming_handler(mock_handler)

    assert manager.streaming_handler == mock_handler


# ============================================================
# Edge Case Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_malformed_webhook_response():
    """Test handling malformed n8n webhook response"""
    manager = SpeakerManager()
    manager.n8n_webhook_url = "http://localhost:8888/webhook/test"
    manager.use_streaming = False
    manager.active_speaker = "user_123"

    with patch('httpx.AsyncClient') as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value

        # Response with malformed JSON
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = AsyncMock(side_effect=Exception("Invalid JSON"))
        mock_response.text = "Not valid JSON"
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        # Should not raise exception
        await manager._send_to_n8n("Hello world")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrent_finalization_requests():
    """Test handling concurrent finalization requests from multiple sources"""
    manager = SpeakerManager()
    manager.active_speaker = "user_123"
    manager.lock_start_time = time.time()

    mock_client = AsyncMock()
    mock_client.finalize = AsyncMock(return_value="test transcript")
    mock_client.close = AsyncMock()
    manager.whisper_client = mock_client

    with patch('asyncio.gather', new_callable=AsyncMock):
        # First finalization
        await manager._finalize_transcription('timeout')

        # Verify speaker is None after first finalization
        assert manager.active_speaker is None

        # Second finalization should be no-op (no active speaker)
        await manager._finalize_transcription('silence')

        # Client should only be finalized once
        assert mock_client.finalize.call_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multiple_simultaneous_speaker_requests():
    """Test handling multiple users trying to speak simultaneously"""
    manager = SpeakerManager()

    async def mock_audio_stream():
        yield b'\x00' * 960

    # First speaker acquires lock
    with patch.object(manager, '_start_transcription', new_callable=AsyncMock):
        with patch('asyncio.create_task'):
            result1 = await manager.on_speaking_start("user_123", mock_audio_stream())
            assert result1 is True
            assert manager.active_speaker == "user_123"

    # All subsequent speakers should be rejected
    for i in range(5):
        result = await manager.on_speaking_start(f"user_{i}", mock_audio_stream())
        assert result is False
        assert manager.active_speaker == "user_123"  # Still first speaker
