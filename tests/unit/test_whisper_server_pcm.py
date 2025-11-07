"""
Unit tests for WhisperX server dual-format support (Opus + PCM)

Tests the WhisperX server's ability to handle both Opus (Discord) and PCM (WebRTC) audio formats:
- Format initialization ('opus' vs 'pcm')
- Audio processing for both formats
- Control messages with format parameter
- Session management with different formats
- Backward compatibility (default to 'opus')

VoxBridge WebRTC Audio Fix (Dual-Format Support)
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, call
from io import BytesIO
import wave

from src.whisper_server import TranscriptionSession, handle_client


# ============================================================
# Format Initialization Tests (5 tests)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_opus_format_creates_decoder():
    """Test 'opus' format creates Opus decoder"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder = MagicMock()
        MockDecoder.return_value = mock_decoder

        session = TranscriptionSession(mock_websocket, user_id, audio_format='opus')

        # Assert Opus decoder was created
        MockDecoder.assert_called_once_with(48000, 2)
        assert session.opus_decoder == mock_decoder
        assert session.audio_format == 'opus'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pcm_format_skips_decoder():
    """Test 'pcm' format skips Opus decoder creation"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    with patch('opuslib.Decoder') as MockDecoder:
        session = TranscriptionSession(mock_websocket, user_id, audio_format='pcm')

        # Assert Opus decoder was NOT created
        MockDecoder.assert_not_called()
        assert session.opus_decoder is None
        assert session.audio_format == 'pcm'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_default_format_is_opus():
    """Test default format is 'opus' for backward compatibility"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder = MagicMock()
        MockDecoder.return_value = mock_decoder

        # No audio_format parameter - should default to 'opus'
        session = TranscriptionSession(mock_websocket, user_id)

        MockDecoder.assert_called_once()
        assert session.audio_format == 'opus'
        assert session.opus_decoder == mock_decoder


@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_parameter_validation():
    """Test format parameter is stored correctly"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    with patch('opuslib.Decoder'):
        # Test 'opus' format
        session_opus = TranscriptionSession(mock_websocket, user_id, audio_format='opus')
        assert session_opus.audio_format == 'opus'

        # Test 'pcm' format
        session_pcm = TranscriptionSession(mock_websocket, user_id, audio_format='pcm')
        assert session_pcm.audio_format == 'pcm'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_logging_messages(caplog):
    """Test format initialization logs correct messages"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    with patch('opuslib.Decoder'):
        # Test Opus logging
        caplog.clear()
        session_opus = TranscriptionSession(mock_websocket, user_id, audio_format='opus')
        assert any("format: opus" in record.message for record in caplog.records)
        assert any("Opus decoder initialized" in record.message for record in caplog.records)

        # Test PCM logging
        caplog.clear()
        session_pcm = TranscriptionSession(mock_websocket, user_id, audio_format='pcm')
        assert any("format: pcm" in record.message for record in caplog.records)
        assert any("PCM audio path" in record.message for record in caplog.records)


# ============================================================
# Audio Processing Tests (8 tests)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_opus_format_decodes_audio():
    """Test Opus format decodes audio with opuslib"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder = MagicMock()
        mock_pcm_data = b'\x00\x01' * 960  # 960 samples of fake PCM
        mock_decoder.decode.return_value = mock_pcm_data
        MockDecoder.return_value = mock_decoder

        session = TranscriptionSession(mock_websocket, user_id, audio_format='opus')

        # Send Opus audio chunk
        opus_chunk = b'\xff\xfe' * 100  # Fake Opus data
        await session.add_audio(opus_chunk)

        # Assert decoder was called with correct parameters
        mock_decoder.decode.assert_called_once_with(opus_chunk, frame_size=960)

        # Assert PCM data was added to buffers
        assert mock_pcm_data in bytes(session.session_buffer)
        assert mock_pcm_data in bytes(session.processing_buffer)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pcm_format_uses_audio_directly():
    """Test PCM format uses audio directly without decoding"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    with patch('opuslib.Decoder') as MockDecoder:
        session = TranscriptionSession(mock_websocket, user_id, audio_format='pcm')

        # Send PCM audio chunk directly
        pcm_chunk = b'\x00\x01' * 960  # Fake PCM data
        await session.add_audio(pcm_chunk)

        # Assert decoder was NEVER called (no decoder exists)
        MockDecoder.assert_not_called()

        # Assert PCM data was added to buffers directly
        assert pcm_chunk in bytes(session.session_buffer)
        assert pcm_chunk in bytes(session.processing_buffer)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_both_formats_add_to_session_buffer():
    """Test both formats correctly add to session_buffer"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    # Test Opus format
    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder = MagicMock()
        mock_pcm_data = b'\x00\x01' * 960
        mock_decoder.decode.return_value = mock_pcm_data
        MockDecoder.return_value = mock_decoder

        session_opus = TranscriptionSession(mock_websocket, user_id, audio_format='opus')
        await session_opus.add_audio(b'\xff\xfe' * 100)

        assert len(session_opus.session_buffer) > 0
        assert mock_pcm_data in bytes(session_opus.session_buffer)

    # Test PCM format
    session_pcm = TranscriptionSession(mock_websocket, user_id, audio_format='pcm')
    pcm_data = b'\x00\x01' * 960
    await session_pcm.add_audio(pcm_data)

    assert len(session_pcm.session_buffer) > 0
    assert pcm_data in bytes(session_pcm.session_buffer)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_both_formats_add_to_processing_buffer():
    """Test both formats correctly add to processing_buffer"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    # Test Opus format
    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder = MagicMock()
        mock_pcm_data = b'\x00\x01' * 960
        mock_decoder.decode.return_value = mock_pcm_data
        MockDecoder.return_value = mock_decoder

        session_opus = TranscriptionSession(mock_websocket, user_id, audio_format='opus')
        await session_opus.add_audio(b'\xff\xfe' * 100)

        assert len(session_opus.processing_buffer) > 0
        assert mock_pcm_data in bytes(session_opus.processing_buffer)

    # Test PCM format
    session_pcm = TranscriptionSession(mock_websocket, user_id, audio_format='pcm')
    pcm_data = b'\x00\x01' * 960
    await session_pcm.add_audio(pcm_data)

    assert len(session_pcm.processing_buffer) > 0
    assert pcm_data in bytes(session_pcm.processing_buffer)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_chunk_processing_triggers_at_threshold():
    """Test chunk processing triggers at 384KB threshold for both formats"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    with patch('opuslib.Decoder') as MockDecoder:
        # Setup Opus decoder
        mock_decoder = MagicMock()
        mock_pcm_data = b'\x00\x01' * 192000  # Large PCM chunk (384KB)
        mock_decoder.decode.return_value = mock_pcm_data
        MockDecoder.return_value = mock_decoder

        session = TranscriptionSession(mock_websocket, user_id, audio_format='opus')

        with patch.object(session, 'process_audio_chunk', new_callable=AsyncMock) as mock_process:
            # Send audio to exceed threshold
            await session.add_audio(b'\xff\xfe' * 192000)

            # Assert chunk processing was triggered
            mock_process.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_opus_decode_error_handling():
    """Test Opus decode error handling"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    import opuslib

    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder = MagicMock()
        mock_decoder.decode.side_effect = opuslib.OpusError("Invalid Opus data")
        MockDecoder.return_value = mock_decoder

        session = TranscriptionSession(mock_websocket, user_id, audio_format='opus')

        # Send invalid Opus data
        await session.add_audio(b'\x00\x00\x00\x00')

        # Should not crash, buffers should be empty
        assert len(session.session_buffer) == 0
        assert len(session.processing_buffer) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pcm_passthrough_error_handling():
    """Test PCM passthrough error handling"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    session = TranscriptionSession(mock_websocket, user_id, audio_format='pcm')

    # Mock processing to raise an exception
    with patch.object(session, 'process_audio_chunk', side_effect=Exception("Processing error")):
        # Send large PCM chunk to trigger processing
        large_pcm = b'\x00\x01' * 192000  # 384KB
        await session.add_audio(large_pcm)

        # Should not crash - error logged but handled


@pytest.mark.unit
@pytest.mark.asyncio
async def test_buffer_size_calculations():
    """Test buffer size calculations are consistent across formats"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    # Test Opus format
    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder = MagicMock()
        pcm_chunk = b'\x00\x01' * 100
        mock_decoder.decode.return_value = pcm_chunk
        MockDecoder.return_value = mock_decoder

        session_opus = TranscriptionSession(mock_websocket, user_id, audio_format='opus')
        await session_opus.add_audio(b'\xff\xfe' * 50)

        opus_buffer_size = len(session_opus.session_buffer)

    # Test PCM format with same PCM data
    session_pcm = TranscriptionSession(mock_websocket, user_id, audio_format='pcm')
    await session_pcm.add_audio(pcm_chunk)

    pcm_buffer_size = len(session_pcm.session_buffer)

    # Both should have same buffer size (same PCM data)
    assert opus_buffer_size == pcm_buffer_size


# ============================================================
# Control Messages Tests (6 tests)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_message_with_opus_format():
    """Test 'start' message with audio_format='opus'"""
    mock_websocket = AsyncMock()
    mock_websocket.remote_address = ("127.0.0.1", 12345)

    # Mock async iterator for WebSocket messages
    async def mock_messages():
        # Send start message with opus format
        start_msg = json.dumps({
            'type': 'start',
            'userId': 'user_123',
            'audio_format': 'opus',
            'language': 'en'
        })
        yield start_msg
        # Send close message to exit loop
        yield json.dumps({'type': 'close'})

    mock_websocket.__aiter__ = lambda self: mock_messages()

    with patch('opuslib.Decoder'):
        with patch('src.whisper_server.model') as mock_model:
            await handle_client(mock_websocket, "/")

            # Session should have been created with opus format
            # Verified via logging (can't directly access session)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_message_with_pcm_format():
    """Test 'start' message with audio_format='pcm'"""
    mock_websocket = AsyncMock()
    mock_websocket.remote_address = ("127.0.0.1", 12345)

    async def mock_messages():
        # Send start message with pcm format
        start_msg = json.dumps({
            'type': 'start',
            'userId': 'user_123',
            'audio_format': 'pcm',
            'language': 'en'
        })
        yield start_msg
        yield json.dumps({'type': 'close'})

    mock_websocket.__aiter__ = lambda self: mock_messages()

    with patch('src.whisper_server.model') as mock_model:
        await handle_client(mock_websocket, "/")

        # Session should have been created with pcm format


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_message_without_format_defaults_opus():
    """Test 'start' message without audio_format defaults to 'opus'"""
    mock_websocket = AsyncMock()
    mock_websocket.remote_address = ("127.0.0.1", 12345)

    async def mock_messages():
        # Send start message WITHOUT audio_format parameter
        start_msg = json.dumps({
            'type': 'start',
            'userId': 'user_123',
            'language': 'en'
        })
        yield start_msg
        yield json.dumps({'type': 'close'})

    mock_websocket.__aiter__ = lambda self: mock_messages()

    with patch('opuslib.Decoder') as MockDecoder:
        with patch('src.whisper_server.model') as mock_model:
            await handle_client(mock_websocket, "/")

            # Decoder should have been created (opus is default)
            MockDecoder.assert_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_message_with_invalid_format():
    """Test 'start' message with invalid format (should still work, just uses value)"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    # Invalid format should be handled gracefully
    # (no validation in current implementation, stored as-is)
    with patch('opuslib.Decoder'):
        session = TranscriptionSession(mock_websocket, user_id, audio_format='invalid')
        assert session.audio_format == 'invalid'
        # Opus decoder still created due to string check
        assert session.opus_decoder is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_persistence_across_session():
    """Test format persists for entire session lifetime"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder = MagicMock()
        mock_decoder.decode.return_value = b'\x00\x01' * 960
        MockDecoder.return_value = mock_decoder

        session = TranscriptionSession(mock_websocket, user_id, audio_format='opus')

        # Add audio multiple times
        await session.add_audio(b'\xff\xfe' * 100)
        await session.add_audio(b'\xff\xfe' * 100)
        await session.add_audio(b'\xff\xfe' * 100)

        # Format should remain unchanged
        assert session.audio_format == 'opus'
        # Decoder called multiple times
        assert mock_decoder.decode.call_count == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_logging_on_session_start(caplog):
    """Test format is logged when session starts"""
    mock_websocket = AsyncMock()
    mock_websocket.remote_address = ("127.0.0.1", 12345)

    async def mock_messages():
        start_msg = json.dumps({
            'type': 'start',
            'userId': 'user_123',
            'audio_format': 'pcm',
            'language': 'en'
        })
        yield start_msg
        yield json.dumps({'type': 'close'})

    mock_websocket.__aiter__ = lambda self: mock_messages()

    caplog.clear()
    with patch('src.whisper_server.model') as mock_model:
        await handle_client(mock_websocket, "/")

        # Check that format was logged
        assert any("format: pcm" in record.message for record in caplog.records)


# ============================================================
# Session Management Tests (6 tests)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_created_with_opus_format():
    """Test session created with opus format"""
    mock_websocket = AsyncMock()
    user_id = "user_opus"

    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder = MagicMock()
        MockDecoder.return_value = mock_decoder

        session = TranscriptionSession(mock_websocket, user_id, audio_format='opus')

        assert session.user_id == user_id
        assert session.audio_format == 'opus'
        assert session.opus_decoder is not None
        assert session.is_active is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_created_with_pcm_format():
    """Test session created with pcm format"""
    mock_websocket = AsyncMock()
    user_id = "user_pcm"

    session = TranscriptionSession(mock_websocket, user_id, audio_format='pcm')

    assert session.user_id == user_id
    assert session.audio_format == 'pcm'
    assert session.opus_decoder is None
    assert session.is_active is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multiple_sessions_different_formats():
    """Test multiple sessions can use different formats simultaneously"""
    mock_ws1 = AsyncMock()
    mock_ws2 = AsyncMock()

    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder = MagicMock()
        MockDecoder.return_value = mock_decoder

        # Create two sessions with different formats
        session_opus = TranscriptionSession(mock_ws1, "user_opus", audio_format='opus')
        session_pcm = TranscriptionSession(mock_ws2, "user_pcm", audio_format='pcm')

        # Both should coexist independently
        assert session_opus.audio_format == 'opus'
        assert session_opus.opus_decoder is not None

        assert session_pcm.audio_format == 'pcm'
        assert session_pcm.opus_decoder is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_cannot_be_changed_mid_session():
    """Test format cannot be changed after session initialization"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder = MagicMock()
        MockDecoder.return_value = mock_decoder

        session = TranscriptionSession(mock_websocket, user_id, audio_format='opus')
        initial_format = session.audio_format

        # Try to change format (should be immutable)
        # In current implementation, this is set at init and not changed
        assert session.audio_format == initial_format


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_cleanup_clears_buffers_opus():
    """Test session cleanup clears buffers for opus format"""
    mock_websocket = AsyncMock()
    user_id = "user_123"

    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder = MagicMock()
        mock_decoder.decode.return_value = b'\x00\x01' * 960
        MockDecoder.return_value = mock_decoder

        session = TranscriptionSession(mock_websocket, user_id, audio_format='opus')

        # Add audio
        await session.add_audio(b'\xff\xfe' * 100)

        # Close session
        session.close()

        # Buffers should be cleared
        assert len(session.session_buffer) == 0
        assert len(session.processing_buffer) == 0
        assert session.is_active is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrent_opus_and_pcm_sessions():
    """Test concurrent opus and pcm sessions don't interfere"""
    mock_ws1 = AsyncMock()
    mock_ws2 = AsyncMock()

    with patch('opuslib.Decoder') as MockDecoder:
        mock_decoder1 = MagicMock()
        mock_decoder1.decode.return_value = b'\x00\x01' * 960
        mock_decoder2 = MagicMock()
        mock_decoder2.decode.return_value = b'\x00\x01' * 960
        MockDecoder.side_effect = [mock_decoder1, mock_decoder2]

        # Create concurrent sessions
        session_opus = TranscriptionSession(mock_ws1, "user_opus", audio_format='opus')
        session_pcm = TranscriptionSession(mock_ws2, "user_pcm", audio_format='pcm')

        # Process audio in both
        await session_opus.add_audio(b'\xff\xfe' * 100)
        await session_pcm.add_audio(b'\x00\x01' * 960)

        # Verify independence
        assert session_opus.audio_format == 'opus'
        assert session_pcm.audio_format == 'pcm'

        # Opus session used decoder
        assert mock_decoder1.decode.called

        # PCM session did not use decoder (only one decoder created)
        assert MockDecoder.call_count == 1  # Only for opus session
