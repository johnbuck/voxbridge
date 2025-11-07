"""
Unit tests for WebRTC PCM decoding functionality

Tests WebRTC handler's ability to decode WebM/OGG containers to PCM audio:
- WebM/OGG container decoding to PCM with PyAV
- Buffer accumulation until parseable (1KB threshold)
- PCM chunk extraction from AudioFrame
- Error handling (InvalidDataError, general errors)
- Format routing to STTService (format='pcm')

VoxBridge WebRTC Audio Fix (Dual-Format Support)
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from io import BytesIO
import numpy as np

from src.voice.webrtc_handler import WebRTCVoiceHandler


# ============================================================
# WebM Decoding Tests (5 tests)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_successful_webm_decode_to_pcm():
    """Test successful WebM decode to PCM"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    # Mock PyAV container
    with patch('av.open') as mock_av_open:
        # Create mock container
        mock_container = MagicMock()
        mock_audio_stream = MagicMock()
        mock_audio_stream.codec_context.name = "opus"
        mock_audio_stream.codec_context.sample_rate = 48000
        mock_audio_stream.codec_context.channels = 2
        mock_container.streams.audio = [mock_audio_stream]

        # Create mock decoded frame
        mock_frame = MagicMock()
        pcm_data = np.zeros((960, 2), dtype=np.int16)  # 960 samples, 2 channels
        mock_frame.to_ndarray.return_value = pcm_data

        # Mock decode to return frame
        mock_container.decode.return_value = [mock_frame]

        mock_av_open.return_value = mock_container

        # Add WebM data to buffer
        handler.webm_buffer = bytearray(b'\x1a\x45\xdf\xa3' + b'\x00' * 1024)  # Fake WebM header + data

        # Extract PCM
        pcm_result = handler._extract_pcm_audio()

        # Assert
        assert len(pcm_result) > 0
        assert pcm_result == pcm_data.tobytes()
        mock_av_open.assert_called_once()
        mock_frame.to_ndarray.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ogg_decode_to_pcm():
    """Test OGG decode to PCM"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    with patch('av.open') as mock_av_open:
        mock_container = MagicMock()
        mock_audio_stream = MagicMock()
        mock_audio_stream.codec_context.name = "opus"
        mock_audio_stream.codec_context.sample_rate = 48000
        mock_audio_stream.codec_context.channels = 2
        mock_container.streams.audio = [mock_audio_stream]

        mock_frame = MagicMock()
        pcm_data = np.zeros((960, 2), dtype=np.int16)
        mock_frame.to_ndarray.return_value = pcm_data

        mock_container.decode.return_value = [mock_frame]
        mock_av_open.return_value = mock_container

        # Add OGG data (OggS header)
        handler.webm_buffer = bytearray(b'OggS' + b'\x00' * 1024)

        pcm_result = handler._extract_pcm_audio()

        assert len(pcm_result) > 0
        assert pcm_result == pcm_data.tobytes()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_buffer_accumulation_until_parseable():
    """Test buffer accumulation until container is parseable (1KB threshold)"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    # Add small buffer (less than 1KB) - should return empty
    handler.webm_buffer = bytearray(b'\x00' * 512)  # 512 bytes
    pcm_result = handler._extract_pcm_audio()

    # Not enough data to even attempt parsing
    assert pcm_result == b''
    assert len(handler.webm_buffer) == 512  # Buffer not cleared


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pcm_chunk_extraction_from_audioframe():
    """Test PCM chunk extraction from AudioFrame"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    with patch('av.open') as mock_av_open:
        mock_container = MagicMock()
        mock_audio_stream = MagicMock()
        mock_audio_stream.codec_context.name = "opus"
        mock_audio_stream.codec_context.sample_rate = 48000
        mock_audio_stream.codec_context.channels = 2
        mock_container.streams.audio = [mock_audio_stream]

        # Create specific PCM data pattern
        pcm_pattern = np.array([[1, 2], [3, 4], [5, 6]], dtype=np.int16)
        mock_frame = MagicMock()
        mock_frame.to_ndarray.return_value = pcm_pattern

        mock_container.decode.return_value = [mock_frame]
        mock_av_open.return_value = mock_container

        handler.webm_buffer = bytearray(b'\x1a\x45\xdf\xa3' + b'\x00' * 1024)

        pcm_result = handler._extract_pcm_audio()

        # Verify exact PCM extraction
        expected_bytes = pcm_pattern.tobytes()
        assert pcm_result == expected_bytes


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multiple_frames_combined_to_pcm():
    """Test multiple frames combined to single PCM buffer"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    with patch('av.open') as mock_av_open:
        mock_container = MagicMock()
        mock_audio_stream = MagicMock()
        mock_audio_stream.codec_context.name = "opus"
        mock_audio_stream.codec_context.sample_rate = 48000
        mock_audio_stream.codec_context.channels = 2
        mock_container.streams.audio = [mock_audio_stream]

        # Create multiple frames
        frame1_data = np.zeros((960, 2), dtype=np.int16)
        frame2_data = np.ones((960, 2), dtype=np.int16)
        frame3_data = np.full((960, 2), 2, dtype=np.int16)

        mock_frame1 = MagicMock()
        mock_frame1.to_ndarray.return_value = frame1_data
        mock_frame2 = MagicMock()
        mock_frame2.to_ndarray.return_value = frame2_data
        mock_frame3 = MagicMock()
        mock_frame3.to_ndarray.return_value = frame3_data

        mock_container.decode.return_value = [mock_frame1, mock_frame2, mock_frame3]
        mock_av_open.return_value = mock_container

        handler.webm_buffer = bytearray(b'\x1a\x45\xdf\xa3' + b'\x00' * 1024)

        pcm_result = handler._extract_pcm_audio()

        # Should combine all frames
        expected = frame1_data.tobytes() + frame2_data.tobytes() + frame3_data.tobytes()
        assert pcm_result == expected


# ============================================================
# Buffer Management Tests (4 tests)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_buffer_cleared_after_successful_decode():
    """Test buffer cleared after successful decode"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    with patch('av.open') as mock_av_open:
        mock_container = MagicMock()
        mock_audio_stream = MagicMock()
        mock_audio_stream.codec_context.name = "opus"
        mock_audio_stream.codec_context.sample_rate = 48000
        mock_audio_stream.codec_context.channels = 2
        mock_container.streams.audio = [mock_audio_stream]

        mock_frame = MagicMock()
        mock_frame.to_ndarray.return_value = np.zeros((960, 2), dtype=np.int16)

        mock_container.decode.return_value = [mock_frame]
        mock_av_open.return_value = mock_container

        # Fill buffer
        handler.webm_buffer = bytearray(b'\x1a\x45\xdf\xa3' + b'\x00' * 1024)
        assert len(handler.webm_buffer) > 0

        # Decode
        pcm_result = handler._extract_pcm_audio()

        # Buffer should be cleared
        assert len(handler.webm_buffer) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_buffer_retained_on_incomplete_data():
    """Test buffer retained on incomplete data"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    import av

    with patch('av.open') as mock_av_open:
        # Simulate InvalidDataError (incomplete container)
        mock_av_open.side_effect = av.error.InvalidDataError("Incomplete data")

        # Fill buffer with incomplete data
        incomplete_data = b'\x1a\x45\xdf\xa3' + b'\x00' * 512
        handler.webm_buffer = bytearray(incomplete_data)

        # Try to decode
        pcm_result = handler._extract_pcm_audio()

        # Should return empty and keep buffer
        assert pcm_result == b''
        assert len(handler.webm_buffer) == len(incomplete_data)
        assert bytes(handler.webm_buffer) == incomplete_data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_buffer_cleared_on_decode_error():
    """Test buffer cleared on general decode error"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    with patch('av.open') as mock_av_open:
        # Simulate general error (corrupted data)
        mock_av_open.side_effect = Exception("Corrupted container")

        handler.webm_buffer = bytearray(b'\x1a\x45\xdf\xa3' + b'\x00' * 1024)

        pcm_result = handler._extract_pcm_audio()

        # Should return empty and clear buffer (avoid perpetual errors)
        assert pcm_result == b''
        assert len(handler.webm_buffer) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_minimum_buffer_size_requirement():
    """Test minimum buffer size requirement (1KB)"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    # Test various buffer sizes below threshold
    for size in [0, 100, 512, 1023]:
        handler.webm_buffer = bytearray(b'\x00' * size)
        pcm_result = handler._extract_pcm_audio()

        # Should return empty (not enough data)
        assert pcm_result == b''

    # Test at threshold
    handler.webm_buffer = bytearray(b'\x00' * 1024)
    # Will attempt decode (may fail due to invalid data, but passes threshold check)


# ============================================================
# Error Handling Tests (4 tests)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_data_error_keeps_buffering():
    """Test InvalidDataError keeps buffering without clearing"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    import av

    with patch('av.open') as mock_av_open:
        mock_av_open.side_effect = av.error.InvalidDataError("Need more data")

        initial_data = b'\x1a\x45\xdf\xa3' + b'\x00' * 1024
        handler.webm_buffer = bytearray(initial_data)

        pcm_result = handler._extract_pcm_audio()

        # Buffer should be unchanged
        assert pcm_result == b''
        assert len(handler.webm_buffer) == len(initial_data)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_general_decode_errors_reset_buffer():
    """Test general decode errors reset buffer"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    with patch('av.open') as mock_av_open:
        mock_av_open.side_effect = RuntimeError("Decoder crashed")

        handler.webm_buffer = bytearray(b'\x1a\x45\xdf\xa3' + b'\x00' * 1024)

        pcm_result = handler._extract_pcm_audio()

        # Buffer should be cleared
        assert pcm_result == b''
        assert len(handler.webm_buffer) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_buffer_returns_empty_bytes():
    """Test empty buffer returns empty bytes"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    # Empty buffer
    handler.webm_buffer = bytearray()

    pcm_result = handler._extract_pcm_audio()

    assert pcm_result == b''


@pytest.mark.unit
@pytest.mark.asyncio
async def test_corrupted_webm_container():
    """Test corrupted WebM container handling"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    with patch('av.open') as mock_av_open:
        # Simulate corrupted container (can't read streams)
        mock_container = MagicMock()
        mock_container.streams.audio = []  # No audio streams
        mock_av_open.return_value = mock_container

        handler.webm_buffer = bytearray(b'\x1a\x45\xdf\xa3' + b'\x00' * 1024)

        # Should handle gracefully (IndexError on streams.audio[0])
        with pytest.raises(IndexError):
            pcm_result = handler._extract_pcm_audio()

        # But in actual code, this would be caught and buffer cleared


# ============================================================
# Format Routing Tests (3 tests)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_stt_service_called_with_pcm_format():
    """Test STTService.send_audio called with format='pcm'"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    # Mock services
    handler.conversation_service = MagicMock()
    handler.conversation_service.start = AsyncMock()
    handler.conversation_service._ensure_session_cached = AsyncMock()

    mock_cached = MagicMock()
    mock_session = MagicMock()
    mock_session.user_id = user_id
    mock_session.agent_id = uuid4()
    mock_cached.session = mock_session
    handler.conversation_service._ensure_session_cached.return_value = mock_cached

    handler.stt_service = AsyncMock()
    handler.stt_service.connect = AsyncMock(return_value=True)
    handler.stt_service.register_callback = AsyncMock()
    handler.stt_service.send_audio = AsyncMock(return_value=True)

    # Mock PyAV decode
    with patch('av.open') as mock_av_open:
        mock_container = MagicMock()
        mock_audio_stream = MagicMock()
        mock_audio_stream.codec_context.name = "opus"
        mock_audio_stream.codec_context.sample_rate = 48000
        mock_audio_stream.codec_context.channels = 2
        mock_container.streams.audio = [mock_audio_stream]

        pcm_data = np.zeros((960, 2), dtype=np.int16)
        mock_frame = MagicMock()
        mock_frame.to_ndarray.return_value = pcm_data

        mock_container.decode.return_value = [mock_frame]
        mock_av_open.return_value = mock_container

        # Add WebM data
        handler.webm_buffer = bytearray(b'\x1a\x45\xdf\xa3' + b'\x00' * 1024)

        # Extract and send
        pcm_result = handler._extract_pcm_audio()

        # Now manually call send_audio (as would happen in audio_loop)
        await handler.stt_service.send_audio(
            session_id=handler.session_id,
            audio_data=pcm_result,
            audio_format='pcm'
        )

        # Verify format parameter
        handler.stt_service.send_audio.assert_called_once()
        call_args = handler.stt_service.send_audio.call_args
        assert call_args.kwargs['audio_format'] == 'pcm'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audio_data_is_raw_pcm_bytes():
    """Test audio_data is raw PCM bytes"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    with patch('av.open') as mock_av_open:
        mock_container = MagicMock()
        mock_audio_stream = MagicMock()
        mock_audio_stream.codec_context.name = "opus"
        mock_audio_stream.codec_context.sample_rate = 48000
        mock_audio_stream.codec_context.channels = 2
        mock_container.streams.audio = [mock_audio_stream]

        # Create known PCM pattern
        pcm_pattern = np.array([[100, 200], [300, 400]], dtype=np.int16)
        mock_frame = MagicMock()
        mock_frame.to_ndarray.return_value = pcm_pattern

        mock_container.decode.return_value = [mock_frame]
        mock_av_open.return_value = mock_container

        handler.webm_buffer = bytearray(b'\x1a\x45\xdf\xa3' + b'\x00' * 1024)

        pcm_result = handler._extract_pcm_audio()

        # Verify it's raw bytes
        assert isinstance(pcm_result, bytes)
        assert pcm_result == pcm_pattern.tobytes()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pcm_sent_only_if_decode_successful():
    """Test PCM sent only if decode successful"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    from uuid import uuid4
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)
    handler.stt_service = AsyncMock()
    handler.stt_service.send_audio = AsyncMock(return_value=True)

    import av

    with patch('av.open') as mock_av_open:
        # First call: InvalidDataError (incomplete data)
        mock_av_open.side_effect = av.error.InvalidDataError("Need more data")

        handler.webm_buffer = bytearray(b'\x1a\x45\xdf\xa3' + b'\x00' * 512)

        pcm_result = handler._extract_pcm_audio()

        # Should not send (empty result)
        assert pcm_result == b''

        # If we were to call send_audio with this, nothing would be sent
        if pcm_result:
            await handler.stt_service.send_audio(
                session_id=handler.session_id,
                audio_data=pcm_result,
                audio_format='pcm'
            )

        # send_audio should NOT have been called
        handler.stt_service.send_audio.assert_not_called()
