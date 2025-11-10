"""
Unit tests for STTService format routing and indicator sending

Tests STTService's ability to route different audio formats and send format indicators:
- Format parameter handling ('opus' vs 'pcm')
- Format indicator sent on first audio
- Format persistence in connection object
- Backward compatibility (default to 'opus')

VoxBridge WebRTC Audio Fix (Dual-Format Support)
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

from src.services.stt_service import STTService, ConnectionStatus, WhisperXConnection


# ============================================================
# Format Parameter Tests (4 tests)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_audio_with_opus_format():
    """Test send_audio with format='opus'"""
    service = STTService()
    session_id = str(uuid4())

    # Setup connection
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            # Connect
            await service.connect(session_id)

            # Send audio with opus format
            opus_data = b'\xff\xfe' * 100
            success = await service.send_audio(
                session_id=session_id,
                audio_data=opus_data,
                audio_format='opus'
            )

            assert success is True

            # Verify format indicator sent
            calls = mock_ws.send.call_args_list
            format_call = calls[1]  # First call is 'start', second is format indicator
            format_msg = json.loads(format_call[0][0])

            assert format_msg['type'] == 'start'
            assert format_msg['audio_format'] == 'opus'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_audio_with_pcm_format():
    """Test send_audio with format='pcm'"""
    service = STTService()
    session_id = str(uuid4())

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            await service.connect(session_id)

            # Send audio with pcm format
            pcm_data = b'\x00\x01' * 960
            success = await service.send_audio(
                session_id=session_id,
                audio_data=pcm_data,
                audio_format='pcm'
            )

            assert success is True

            # Verify format indicator sent
            calls = mock_ws.send.call_args_list
            format_call = calls[1]
            format_msg = json.loads(format_call[0][0])

            assert format_msg['type'] == 'start'
            assert format_msg['audio_format'] == 'pcm'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_audio_without_format_defaults_opus():
    """Test send_audio without format defaults to 'opus'"""
    service = STTService()
    session_id = str(uuid4())

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            await service.connect(session_id)

            # Send audio WITHOUT format parameter
            audio_data = b'\xff\xfe' * 100
            success = await service.send_audio(
                session_id=session_id,
                audio_data=audio_data
                # No audio_format parameter - should default to 'opus'
            )

            assert success is True

            # Verify default format is 'opus'
            calls = mock_ws.send.call_args_list
            format_call = calls[1]
            format_msg = json.loads(format_call[0][0])

            assert format_msg['audio_format'] == 'opus'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_parameter_passed_correctly():
    """Test format parameter passed correctly to WhisperX"""
    service = STTService()
    session_id = str(uuid4())

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            await service.connect(session_id)

            # Send with custom format
            await service.send_audio(
                session_id=session_id,
                audio_data=b'\x00\x01' * 100,
                audio_format='pcm'
            )

            # Verify format message structure
            calls = mock_ws.send.call_args_list
            format_call = calls[1]
            format_msg = json.loads(format_call[0][0])

            # Verify message fields
            assert format_msg['type'] == 'start'
            assert format_msg['userId'] == session_id
            assert format_msg['audio_format'] == 'pcm'


# ============================================================
# Format Indicator Tests (4 tests)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_indicator_sent_on_first_audio():
    """Test format indicator sent on first audio"""
    service = STTService()
    session_id = str(uuid4())

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            await service.connect(session_id)

            # First audio send
            await service.send_audio(
                session_id=session_id,
                audio_data=b'\x00\x01' * 100,
                audio_format='pcm'
            )

            # Should have sent format indicator
            calls = mock_ws.send.call_args_list
            assert len(calls) >= 2  # 'start' message + format indicator + audio data

            # Verify format indicator
            format_call = calls[1]
            assert isinstance(format_call[0][0], str)  # JSON string
            format_msg = json.loads(format_call[0][0])
            assert format_msg['type'] == 'start'
            assert format_msg['audio_format'] == 'pcm'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_indicator_sent_only_once():
    """Test format indicator sent only once per connection"""
    service = STTService()
    session_id = str(uuid4())

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            await service.connect(session_id)

            # Send multiple audio chunks
            for i in range(5):
                await service.send_audio(
                    session_id=session_id,
                    audio_data=b'\x00\x01' * 100,
                    audio_format='opus'
                )

            # Count JSON messages (format indicators)
            json_messages = [
                call for call in mock_ws.send.call_args_list
                if isinstance(call[0][0], str)
            ]

            # Should be 2: initial 'start' message + format indicator (sent only once)
            assert len(json_messages) == 2

            # Verify binary audio sent 5 times
            binary_messages = [
                call for call in mock_ws.send.call_args_list
                if isinstance(call[0][0], bytes)
            ]
            assert len(binary_messages) == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_indicator_includes_userid_and_format():
    """Test format indicator includes userId and audio_format"""
    service = STTService()
    session_id = str(uuid4())

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            await service.connect(session_id)

            await service.send_audio(
                session_id=session_id,
                audio_data=b'\x00\x01' * 100,
                audio_format='pcm'
            )

            # Find format indicator message
            calls = mock_ws.send.call_args_list
            format_call = calls[1]
            format_msg = json.loads(format_call[0][0])

            # Verify required fields
            assert 'userId' in format_msg
            assert 'audio_format' in format_msg
            assert format_msg['userId'] == session_id
            assert format_msg['audio_format'] == 'pcm'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_persisted_in_connection_object():
    """Test format persisted in connection object"""
    service = STTService()
    session_id = str(uuid4())

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            await service.connect(session_id)

            # Send audio with format
            await service.send_audio(
                session_id=session_id,
                audio_data=b'\x00\x01' * 100,
                audio_format='pcm'
            )

            # Check connection object
            connection = service.connections[session_id]

            # Verify format_sent flag
            assert hasattr(connection, 'format_sent')
            assert connection.format_sent is True

            # Verify audio_format stored
            assert hasattr(connection, 'audio_format')
            assert connection.audio_format == 'pcm'


# ============================================================
# Backward Compatibility Tests (2 tests)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_discord_plugin_defaults_to_opus():
    """Test Discord plugin (no format param) defaults to 'opus'"""
    service = STTService()
    session_id = str(uuid4())

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            await service.connect(session_id)

            # Simulate Discord plugin call (no format parameter)
            success = await service.send_audio(
                session_id=session_id,
                audio_data=b'\xff\xfe' * 100
                # No audio_format - simulates old Discord plugin code
            )

            assert success is True

            # Verify defaulted to opus
            calls = mock_ws.send.call_args_list
            format_call = calls[1]
            format_msg = json.loads(format_call[0][0])

            assert format_msg['audio_format'] == 'opus'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_existing_tests_pass_with_default_format():
    """Test existing tests still pass with default format"""
    service = STTService()
    session_id = str(uuid4())

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            # Existing test pattern (no format parameter)
            success = await service.connect(session_id)
            assert success is True

            # Send audio without format
            success = await service.send_audio(
                session_id=session_id,
                audio_data=b'\xff\xfe' * 100
            )
            assert success is True

            # Should work without breaking
            assert session_id in service.connections
            connection = service.connections[session_id]
            assert connection.status == ConnectionStatus.CONNECTED


# ============================================================
# Integration Tests (format + indicator flow)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_indicator_before_audio_data():
    """Test format indicator sent before audio data"""
    service = STTService()
    session_id = str(uuid4())

    mock_ws = AsyncMock()
    send_order = []

    # Track send order
    async def mock_send(data):
        send_order.append(('json' if isinstance(data, str) else 'binary', data))

    mock_ws.send = mock_send

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            await service.connect(session_id)

            await service.send_audio(
                session_id=session_id,
                audio_data=b'\x00\x01' * 100,
                audio_format='pcm'
            )

            # Verify order: initial start message, format indicator, then binary audio
            assert len(send_order) == 3
            assert send_order[0][0] == 'json'  # Initial start message
            assert send_order[1][0] == 'json'  # Format indicator
            assert send_order[2][0] == 'binary'  # Audio data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multiple_sessions_different_formats():
    """Test multiple sessions with different formats"""
    service = STTService()
    session_opus = str(uuid4())
    session_pcm = str(uuid4())

    mock_ws_opus = AsyncMock()
    mock_ws_opus.send = AsyncMock()
    mock_ws_pcm = AsyncMock()
    mock_ws_pcm.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        # Return different WebSocket mocks for different sessions
        mock_connect.side_effect = [mock_ws_opus, mock_ws_pcm]

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            # Connect both sessions
            await service.connect(session_opus)
            await service.connect(session_pcm)

            # Send opus format to first session
            await service.send_audio(
                session_id=session_opus,
                audio_data=b'\xff\xfe' * 100,
                audio_format='opus'
            )

            # Send pcm format to second session
            await service.send_audio(
                session_id=session_pcm,
                audio_data=b'\x00\x01' * 960,
                audio_format='pcm'
            )

            # Verify opus session
            opus_calls = mock_ws_opus.send.call_args_list
            opus_format_msg = json.loads(opus_calls[1][0][0])
            assert opus_format_msg['audio_format'] == 'opus'

            # Verify pcm session
            pcm_calls = mock_ws_pcm.send.call_args_list
            pcm_format_msg = json.loads(pcm_calls[1][0][0])
            assert pcm_format_msg['audio_format'] == 'pcm'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_indicator_not_sent_if_connection_failed():
    """Test format indicator not sent if connection not established"""
    service = STTService()
    session_id = str(uuid4())

    # Don't connect - just try to send audio
    success = await service.send_audio(
        session_id=session_id,
        audio_data=b'\x00\x01' * 100,
        audio_format='pcm'
    )

    # Should fail gracefully
    assert success is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_change_between_reconnects():
    """Test format can change if connection is recreated"""
    service = STTService()
    session_id = str(uuid4())

    mock_ws1 = AsyncMock()
    mock_ws1.send = AsyncMock()
    mock_ws2 = AsyncMock()
    mock_ws2.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.side_effect = [mock_ws1, mock_ws2]

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            # First connection with opus
            await service.connect(session_id)
            await service.send_audio(
                session_id=session_id,
                audio_data=b'\xff\xfe' * 100,
                audio_format='opus'
            )

            # Disconnect
            await service.disconnect(session_id)

            # Reconnect with pcm
            await service.connect(session_id)
            await service.send_audio(
                session_id=session_id,
                audio_data=b'\x00\x01' * 960,
                audio_format='pcm'
            )

            # Verify first connection used opus
            opus_calls = mock_ws1.send.call_args_list
            opus_format_msg = json.loads(opus_calls[1][0][0])
            assert opus_format_msg['audio_format'] == 'opus'

            # Verify second connection used pcm
            pcm_calls = mock_ws2.send.call_args_list
            pcm_format_msg = json.loads(pcm_calls[1][0][0])
            assert pcm_format_msg['audio_format'] == 'pcm'
