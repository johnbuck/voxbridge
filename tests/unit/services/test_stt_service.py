"""
Unit tests for STTService

Tests WhisperX connection management, audio streaming, transcription callbacks,
reconnection logic, health monitoring, and multi-session support.
"""
import pytest
import asyncio
import time
import json
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

from src.services.stt_service import (
    STTService,
    ConnectionStatus,
    WhisperXConnection,
    WHISPER_SERVER_URL,
)


# ============================================================
# Initialization Tests
# ============================================================

@pytest.mark.asyncio
async def test_init_with_defaults():
    """Test initialization with default WhisperX URL"""
    service = STTService()

    assert service.default_whisper_url == WHISPER_SERVER_URL
    assert service.max_retries == 5
    assert service.backoff_multiplier == 2.0
    assert service.timeout_s == 30.0
    assert len(service.connections) == 0
    assert service.total_connections == 0


@pytest.mark.asyncio
async def test_init_with_custom_url():
    """Test initialization with custom WhisperX URL"""
    custom_url = "ws://custom-whisper:8000"
    service = STTService(default_whisper_url=custom_url)

    assert service.default_whisper_url == custom_url


@pytest.mark.asyncio
async def test_init_with_custom_parameters():
    """Test initialization with custom retry/timeout parameters"""
    service = STTService(
        max_retries=10,
        backoff_multiplier=1.5,
        timeout_s=60.0
    )

    assert service.max_retries == 10
    assert service.backoff_multiplier == 1.5
    assert service.timeout_s == 60.0


# ============================================================
# Connection Management Tests
# ============================================================

@pytest.mark.asyncio
async def test_connect_success():
    """Test successful WhisperX connection"""
    service = STTService()
    session_id = str(uuid4())

    # Mock WebSocket connection
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        # Mock receive loop
        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            success = await service.connect(session_id)

            assert success is True
            assert session_id in service.connections
            assert service.connections[session_id].status == ConnectionStatus.CONNECTED
            assert service.total_connections == 1


@pytest.mark.asyncio
async def test_connect_retry_on_failure():
    """Test automatic retry with exponential backoff"""
    service = STTService(max_retries=2, backoff_multiplier=1.5)
    session_id = str(uuid4())

    # Mock WebSocket to fail first attempt, succeed on second
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        # Fail first, succeed second
        mock_connect.side_effect = [
            Exception("Connection refused"),
            mock_ws
        ]

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                success = await service.connect(session_id)

                # Should succeed on retry
                assert success is True
                assert mock_connect.call_count == 2
                # Should have slept for backoff
                assert mock_sleep.called


@pytest.mark.asyncio
async def test_connect_max_retries_exceeded():
    """Test failure after max retries exceeded"""
    service = STTService(max_retries=1)
    session_id = str(uuid4())

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        # Always fail
        mock_connect.side_effect = Exception("Connection refused")

        with patch('asyncio.sleep', new_callable=AsyncMock):
            success = await service.connect(session_id)

            assert success is False
            assert service.connections[session_id].status == ConnectionStatus.FAILED
            assert service.total_failures == 1


@pytest.mark.asyncio
async def test_connect_already_connected():
    """Test connecting when already connected (idempotent)"""
    service = STTService()
    session_id = str(uuid4())

    # Pre-create connection
    mock_ws = AsyncMock()
    connection = WhisperXConnection(
        session_id=session_id,
        websocket=mock_ws,
        status=ConnectionStatus.CONNECTED,
        callback=None,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Try to connect again
    success = await service.connect(session_id)

    # Should return success without reconnecting
    assert success is True


@pytest.mark.asyncio
async def test_disconnect():
    """Test clean disconnection"""
    service = STTService()
    session_id = str(uuid4())

    # Create mock connection
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.close = AsyncMock()

    mock_task = AsyncMock()
    mock_task.done.return_value = False
    mock_task.cancel = MagicMock()

    connection = WhisperXConnection(
        session_id=session_id,
        websocket=mock_ws,
        status=ConnectionStatus.CONNECTED,
        callback=None,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=mock_task
    )
    service.connections[session_id] = connection

    # Disconnect
    await service.disconnect(session_id)

    # Verify cleanup
    assert session_id not in service.connections
    assert mock_ws.send.called  # Should send close message
    assert mock_ws.close.called
    assert mock_task.cancel.called


@pytest.mark.asyncio
async def test_disconnect_no_connection():
    """Test disconnecting when no connection exists (graceful)"""
    service = STTService()
    session_id = str(uuid4())

    # Should not raise error
    await service.disconnect(session_id)


# ============================================================
# Audio Streaming Tests
# ============================================================

@pytest.mark.asyncio
async def test_send_audio_success():
    """Test sending audio frame to WhisperX"""
    service = STTService()
    session_id = str(uuid4())

    # Create mock connection
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    connection = WhisperXConnection(
        session_id=session_id,
        websocket=mock_ws,
        status=ConnectionStatus.CONNECTED,
        callback=None,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Send audio
    audio_data = b'\x00' * 960  # Mock audio frame
    success = await service.send_audio(session_id, audio_data)

    assert success is True
    mock_ws.send.assert_called_once_with(audio_data)


@pytest.mark.asyncio
async def test_send_audio_not_connected():
    """Test sending audio when not connected (graceful failure)"""
    service = STTService()
    session_id = str(uuid4())

    # No connection exists
    success = await service.send_audio(session_id, b'\x00' * 960)

    assert success is False


@pytest.mark.asyncio
async def test_send_audio_connection_lost():
    """Test handling connection loss during send"""
    service = STTService()
    session_id = str(uuid4())

    # Create mock connection
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock(side_effect=Exception("Connection lost"))

    connection = WhisperXConnection(
        session_id=session_id,
        websocket=mock_ws,
        status=ConnectionStatus.CONNECTED,
        callback=None,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Mock reconnect attempt
    with patch.object(service, '_attempt_reconnect', new_callable=AsyncMock):
        success = await service.send_audio(session_id, b'\x00' * 960)

        assert success is False
        assert connection.status == ConnectionStatus.DISCONNECTED


@pytest.mark.asyncio
async def test_send_audio_bytearray_conversion():
    """Test sending audio with bytearray (auto-conversion to bytes)"""
    service = STTService()
    session_id = str(uuid4())

    # Create mock connection
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    connection = WhisperXConnection(
        session_id=session_id,
        websocket=mock_ws,
        status=ConnectionStatus.CONNECTED,
        callback=None,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Send bytearray
    audio_data = bytearray(960)
    success = await service.send_audio(session_id, audio_data)

    assert success is True
    # Should convert to bytes
    assert mock_ws.send.called


# ============================================================
# Callback Tests
# ============================================================

@pytest.mark.asyncio
async def test_register_callback():
    """Test registering transcription callback"""
    service = STTService()
    session_id = str(uuid4())

    # Create connection
    connection = WhisperXConnection(
        session_id=session_id,
        websocket=None,
        status=ConnectionStatus.CONNECTING,
        callback=None,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Register callback
    async def mock_callback(text: str, is_final: bool, metadata: dict):
        pass

    await service.register_callback(session_id, mock_callback)

    assert connection.callback == mock_callback


@pytest.mark.asyncio
async def test_callback_on_partial_transcript():
    """Test callback fires on partial transcript"""
    service = STTService()
    session_id = str(uuid4())

    # Track callback calls
    callback_calls = []

    async def mock_callback(text: str, is_final: bool, metadata: dict):
        callback_calls.append((text, is_final, metadata))

    # Create connection with callback
    connection = WhisperXConnection(
        session_id=session_id,
        websocket=None,
        status=ConnectionStatus.CONNECTED,
        callback=mock_callback,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Simulate partial transcript message
    message = json.dumps({
        'type': 'partial',
        'text': 'Hello',
        'confidence': 0.95
    })

    await service._handle_message(session_id, message)

    # Verify callback was called
    assert len(callback_calls) == 1
    assert callback_calls[0][0] == 'Hello'
    assert callback_calls[0][1] is False  # Not final


@pytest.mark.asyncio
async def test_callback_on_final_transcript():
    """Test callback fires on final transcript"""
    service = STTService()
    session_id = str(uuid4())

    callback_calls = []

    async def mock_callback(text: str, is_final: bool, metadata: dict):
        callback_calls.append((text, is_final, metadata))

    connection = WhisperXConnection(
        session_id=session_id,
        websocket=None,
        status=ConnectionStatus.CONNECTED,
        callback=mock_callback,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Simulate final transcript message
    message = json.dumps({
        'type': 'final',
        'text': 'Hello world',
        'confidence': 0.98,
        'duration': 1.5
    })

    await service._handle_message(session_id, message)

    # Verify callback was called
    assert len(callback_calls) == 1
    assert callback_calls[0][0] == 'Hello world'
    assert callback_calls[0][1] is True  # Final


@pytest.mark.asyncio
async def test_callback_error_handling():
    """Test callback exceptions don't crash service"""
    service = STTService()
    session_id = str(uuid4())

    # Callback that raises exception
    async def failing_callback(text: str, is_final: bool, metadata: dict):
        raise Exception("Callback error")

    connection = WhisperXConnection(
        session_id=session_id,
        websocket=None,
        status=ConnectionStatus.CONNECTED,
        callback=failing_callback,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Simulate message (should not crash)
    message = json.dumps({
        'type': 'final',
        'text': 'Test',
    })

    # Should not raise exception
    await service._handle_message(session_id, message)


@pytest.mark.asyncio
async def test_callback_on_error_message():
    """Test callback fires on error message from WhisperX"""
    service = STTService()
    session_id = str(uuid4())

    callback_calls = []

    async def mock_callback(text: str, is_final: bool, metadata: dict):
        callback_calls.append((text, is_final, metadata))

    connection = WhisperXConnection(
        session_id=session_id,
        websocket=None,
        status=ConnectionStatus.CONNECTED,
        callback=mock_callback,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Simulate error message
    message = json.dumps({
        'type': 'error',
        'error': 'Audio processing failed'
    })

    await service._handle_message(session_id, message)

    # Verify callback was called with empty text
    assert len(callback_calls) == 1
    assert callback_calls[0][0] == ''
    assert callback_calls[0][1] is True  # Final (error ends transcription)
    assert 'error' in callback_calls[0][2]


# ============================================================
# Status Tests
# ============================================================

@pytest.mark.asyncio
async def test_is_connected():
    """Test connection status check"""
    service = STTService()
    session_id = str(uuid4())

    # Not connected initially
    assert await service.is_connected(session_id) is False

    # Create connected connection
    connection = WhisperXConnection(
        session_id=session_id,
        websocket=AsyncMock(),
        status=ConnectionStatus.CONNECTED,
        callback=None,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Now connected
    assert await service.is_connected(session_id) is True


@pytest.mark.asyncio
async def test_get_connection_status():
    """Test detailed connection status retrieval"""
    service = STTService()
    session_id = str(uuid4())

    # No connection
    status = await service.get_connection_status(session_id)
    assert status['connected'] is False
    assert status['status'] == ConnectionStatus.DISCONNECTED.value

    # Create connection
    connection = WhisperXConnection(
        session_id=session_id,
        websocket=AsyncMock(),
        status=ConnectionStatus.CONNECTED,
        callback=lambda *args: None,
        reconnect_attempts=2,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Get status
    status = await service.get_connection_status(session_id)
    assert status['connected'] is True
    assert status['status'] == ConnectionStatus.CONNECTED.value
    assert status['reconnect_attempts'] == 2
    assert status['has_callback'] is True
    assert 'uptime_seconds' in status
    assert 'idle_seconds' in status


# ============================================================
# Metrics Tests
# ============================================================

@pytest.mark.asyncio
async def test_get_metrics():
    """Test service-wide metrics retrieval"""
    service = STTService()

    # Initial metrics
    metrics = await service.get_metrics()
    assert metrics['active_connections'] == 0
    assert metrics['total_connections'] == 0
    assert metrics['total_transcriptions'] == 0

    # Add connection
    session_id = str(uuid4())
    connection = WhisperXConnection(
        session_id=session_id,
        websocket=AsyncMock(),
        status=ConnectionStatus.CONNECTED,
        callback=None,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection
    service.total_connections = 1

    # Updated metrics
    metrics = await service.get_metrics()
    assert metrics['active_connections'] == 1
    assert metrics['total_connections'] == 1
    assert session_id in metrics['sessions']


@pytest.mark.asyncio
async def test_metrics_track_transcriptions():
    """Test metrics track total transcriptions"""
    service = STTService()
    session_id = str(uuid4())

    # Create connection with callback
    connection = WhisperXConnection(
        session_id=session_id,
        websocket=None,
        status=ConnectionStatus.CONNECTED,
        callback=AsyncMock(),
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Simulate final transcription
    message = json.dumps({
        'type': 'final',
        'text': 'Test transcription'
    })

    await service._handle_message(session_id, message)

    # Check metrics
    metrics = await service.get_metrics()
    assert metrics['total_transcriptions'] == 1


# ============================================================
# Concurrency Tests
# ============================================================

@pytest.mark.asyncio
async def test_multiple_sessions_concurrent():
    """Test multiple simultaneous sessions"""
    service = STTService()

    # Create 3 concurrent sessions
    session_ids = [str(uuid4()) for _ in range(3)]

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            # Connect all sessions concurrently
            tasks = [service.connect(sid) for sid in session_ids]
            results = await asyncio.gather(*tasks)

            # All should succeed
            assert all(results)
            assert len(service.connections) == 3


# ============================================================
# Reconnection Tests
# ============================================================

@pytest.mark.asyncio
async def test_attempt_reconnect():
    """Test reconnection attempt"""
    service = STTService(max_retries=1)
    session_id = str(uuid4())

    # Create disconnected connection
    connection = WhisperXConnection(
        session_id=session_id,
        websocket=None,
        status=ConnectionStatus.DISCONNECTED,
        callback=None,
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Mock successful reconnection
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            success = await service._attempt_reconnect(session_id)

            assert success is True
            assert service.total_reconnections == 1


# ============================================================
# Cleanup Tests
# ============================================================

@pytest.mark.asyncio
async def test_shutdown():
    """Test graceful shutdown of all connections"""
    service = STTService()

    # Create multiple connections
    session_ids = [str(uuid4()) for _ in range(3)]

    for sid in session_ids:
        connection = WhisperXConnection(
            session_id=sid,
            websocket=AsyncMock(),
            status=ConnectionStatus.CONNECTED,
            callback=None,
            reconnect_attempts=0,
            last_activity=time.time(),
            created_at=time.time(),
            url=service.default_whisper_url,
            listen_task=None
        )
        service.connections[sid] = connection

    # Shutdown
    await service.shutdown()

    # All connections should be closed
    assert len(service.connections) == 0


@pytest.mark.asyncio
async def test_handle_invalid_json():
    """Test handling of invalid JSON from WhisperX"""
    service = STTService()
    session_id = str(uuid4())

    connection = WhisperXConnection(
        session_id=session_id,
        websocket=None,
        status=ConnectionStatus.CONNECTED,
        callback=AsyncMock(),
        reconnect_attempts=0,
        last_activity=time.time(),
        created_at=time.time(),
        url=service.default_whisper_url,
        listen_task=None
    )
    service.connections[session_id] = connection

    # Send invalid JSON (should not crash)
    await service._handle_message(session_id, "invalid json {{{")


@pytest.mark.asyncio
async def test_custom_whisper_url_per_session():
    """Test using custom WhisperX URL for specific session"""
    service = STTService(default_whisper_url="ws://default:4901")
    session_id = str(uuid4())
    custom_url = "ws://custom:5000"

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws

        with patch.object(service, '_receive_loop', new_callable=AsyncMock):
            await service.connect(session_id, whisper_url=custom_url)

            # Verify custom URL was used
            connection = service.connections[session_id]
            assert connection.url == custom_url
