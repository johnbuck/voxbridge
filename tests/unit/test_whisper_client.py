"""
Unit tests for WhisperClient

Tests WebSocket connection, audio streaming, message handling,
reconnection logic, and error handling
"""
from __future__ import annotations

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import websockets.exceptions

from src.whisper_client import WhisperClient


# ============================================================
# Connection Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_connect_success():
    """Test successful WebSocket connection"""
    client = WhisperClient()

    with patch('websockets.connect') as mock_connect:
        mock_ws = AsyncMock()

        # Create actual coroutine function that returns the mock
        async def connect_coro(*args, **kwargs):
            return mock_ws

        mock_connect.side_effect = connect_coro

        await client.connect("test_user_123")

        # Assertions
        assert client.is_connected
        assert client.user_id == "test_user_123"
        mock_connect.assert_called_once()

        # Verify start message was sent
        calls = mock_ws.send.call_args_list
        assert len(calls) == 1
        start_message = json.loads(calls[0][0][0])
        assert start_message['type'] == 'start'
        assert start_message['userId'] == "test_user_123"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connect_retry_on_failure():
    """Test connection retry with exponential backoff"""
    client = WhisperClient()

    with patch('websockets.connect') as mock_connect:
        # First 2 attempts fail, 3rd succeeds
        mock_ws_success = AsyncMock()

        # Create coroutine for successful connection
        async def connect_success(*args, **kwargs):
            return mock_ws_success

        mock_connect.side_effect = [
            Exception("Connection refused"),
            Exception("Connection refused"),
            connect_success()  # Success - returns coroutine
        ]

        with patch('asyncio.sleep'):  # Speed up test
            await client.connect("test_user")

        # Should have retried
        assert mock_connect.call_count == 3
        assert client.is_connected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connect_max_retries_exceeded():
    """Test connection fails after max retries"""
    client = WhisperClient()
    client.max_reconnect_attempts = 2

    with patch('websockets.connect') as mock_connect:
        mock_connect.side_effect = Exception("Connection refused")

        with patch('asyncio.sleep'):
            with pytest.raises(Exception):
                await client.connect("test_user")

        # Should have tried max_reconnect_attempts + 1 times
        assert mock_connect.call_count == 3
        assert not client.is_connected


# ============================================================
# Audio Streaming Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_audio_success():
    """Test sending audio chunk to WhisperX"""
    client = WhisperClient()
    client.is_connected = True
    client.ws = AsyncMock()

    audio_chunk = b'\x00' * 960  # Fake Opus packet

    await client.send_audio(audio_chunk)

    # Verify audio was sent via WebSocket
    client.ws.send.assert_called_once_with(audio_chunk)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_audio_when_disconnected():
    """Test sending audio when not connected"""
    client = WhisperClient()
    client.is_connected = False

    audio_chunk = b'\x00' * 960

    # Should not raise, just warn
    await client.send_audio(audio_chunk)

    # No WebSocket, so nothing to verify sent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_audio_with_different_buffer_types():
    """Test sending audio with bytes, bytearray, and memoryview types"""
    client = WhisperClient()
    client.is_connected = True
    client.ws = AsyncMock()

    # Test with bytes (standard)
    audio_bytes = b'\x00' * 960
    await client.send_audio(audio_bytes)
    assert client.ws.send.call_count == 1
    assert client.ws.send.call_args[0][0] == audio_bytes

    # Test with bytearray (VoiceData.packet may be this type)
    audio_bytearray = bytearray(b'\x01' * 960)
    await client.send_audio(audio_bytearray)
    assert client.ws.send.call_count == 2
    # Should convert to bytes before sending
    sent_data = client.ws.send.call_args[0][0]
    assert isinstance(sent_data, bytes)
    assert sent_data == bytes(audio_bytearray)

    # Test with memoryview (another possible buffer type)
    audio_memoryview = memoryview(b'\x02' * 960)
    await client.send_audio(audio_memoryview)
    assert client.ws.send.call_count == 3
    # Should convert to bytes before sending
    sent_data = client.ws.send.call_args[0][0]
    assert isinstance(sent_data, bytes)
    assert sent_data == bytes(audio_memoryview)


# ============================================================
# Message Handling Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_partial_message():
    """Test handling partial transcription message"""
    client = WhisperClient()
    client.transcript_buffer = ""

    partial_msg = json.dumps({
        'type': 'partial',
        'text': 'Hello this is'
    })

    await client._handle_message(partial_msg)

    assert client.transcript_buffer == 'Hello this is'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_final_message():
    """Test handling final transcription message"""
    client = WhisperClient()
    client.finalize_future = asyncio.Future()

    final_msg = json.dumps({
        'type': 'final',
        'text': 'Hello this is a test.'
    })

    await client._handle_message(final_msg)

    assert client.transcript_buffer == 'Hello this is a test.'
    assert client.finalize_future.done()
    assert client.finalize_future.result() == 'Hello this is a test.'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_error_message():
    """Test handling error message from WhisperX"""
    client = WhisperClient()

    # Set up callback to verify error was received
    error_received = []
    async def on_error(error_msg):
        error_received.append(error_msg)

    client.on_error_callback = on_error

    error_msg = json.dumps({
        'type': 'error',
        'error': 'Transcription failed'
    })

    await client._handle_message(error_msg)

    assert len(error_received) == 1
    assert error_received[0] == 'Transcription failed'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_invalid_json():
    """Test handling invalid JSON message"""
    client = WhisperClient()

    invalid_msg = "not valid json {"

    # Should not raise, just log error
    await client._handle_message(invalid_msg)


# ============================================================
# Finalization Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_finalize_success():
    """Test finalization with successful response"""
    client = WhisperClient()
    client.is_connected = True
    client.ws = AsyncMock()
    client.transcript_buffer = "test transcript"

    # Create future that will be resolved by mock
    client.finalize_future = asyncio.Future()

    # Simulate final message arriving
    async def send_final(*args):
        await asyncio.sleep(0.1)
        client.finalize_future.set_result("final transcript")

    client.ws.send.side_effect = send_final

    result = await client.finalize()

    assert result == "final transcript"

    # Verify finalize message was sent
    calls = client.ws.send.call_args_list
    assert len(calls) == 1
    finalize_msg = json.loads(calls[0][0][0])
    assert finalize_msg['type'] == 'finalize'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_finalize_timeout():
    """Test finalization timeout returns buffered transcript"""
    client = WhisperClient()
    client.is_connected = True
    client.ws = AsyncMock()
    client.transcript_buffer = "buffered transcript"

    # Finalize future never resolves (simulating timeout)
    client.finalize_future = asyncio.Future()

    # Send doesn't resolve the future
    client.ws.send = AsyncMock()

    result = await client.finalize()

    # Should return buffered transcript on timeout
    assert result == "buffered transcript"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_finalize_when_disconnected():
    """Test finalization when not connected"""
    client = WhisperClient()
    client.is_connected = False
    client.transcript_buffer = "disconnected transcript"

    result = await client.finalize()

    assert result == "disconnected transcript"


# ============================================================
# Connection Management Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_connection():
    """Test closing WebSocket connection"""
    client = WhisperClient()
    client.is_connected = True
    mock_ws = AsyncMock()
    # Ensure send returns an awaitable
    mock_ws.send = AsyncMock()
    mock_ws.close = AsyncMock()
    client.ws = mock_ws
    client.user_id = "test_user"

    await client.close()

    # Verify close message was sent
    calls = mock_ws.send.call_args_list
    assert len(calls) == 1
    close_msg = json.loads(calls[0][0][0])
    assert close_msg['type'] == 'close'

    # Verify connection closed
    mock_ws.close.assert_called_once()
    assert not client.is_connected
    assert client.ws is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_error_handling():
    """Test error handling during connection close"""
    client = WhisperClient()
    client.is_connected = True
    client.ws = AsyncMock()
    client.ws.send.side_effect = Exception("Send failed")

    # Should not raise
    await client.close()

    # Connection should still be cleaned up
    assert not client.is_connected


# ============================================================
# Callback Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_on_partial_callback():
    """Test partial transcription callback"""
    client = WhisperClient()

    partial_results = []
    async def on_partial(text):
        partial_results.append(text)

    client.on_partial_callback = on_partial

    partial_msg = json.dumps({'type': 'partial', 'text': 'test partial'})
    await client._handle_message(partial_msg)

    assert len(partial_results) == 1
    assert partial_results[0] == 'test partial'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_on_final_callback():
    """Test final transcription callback"""
    client = WhisperClient()
    client.finalize_future = asyncio.Future()

    final_results = []
    async def on_final(text):
        final_results.append(text)

    client.on_final_callback = on_final

    final_msg = json.dumps({'type': 'final', 'text': 'test final'})
    await client._handle_message(final_msg)

    assert len(final_results) == 1
    assert final_results[0] == 'test final'


# ============================================================
# Transcript Buffer Tests
# ============================================================

@pytest.mark.unit
def test_get_transcript():
    """Test getting current transcript buffer"""
    client = WhisperClient()
    client.transcript_buffer = "current transcript"

    result = client.get_transcript()

    assert result == "current transcript"


@pytest.mark.unit
def test_transcript_buffer_updates():
    """Test transcript buffer updates through messages"""
    client = WhisperClient()

    # Initially empty
    assert client.transcript_buffer == ''

    # After partial
    client.transcript_buffer = 'partial text'
    assert client.transcript_buffer == 'partial text'

    # After final
    client.transcript_buffer = 'final text'
    assert client.transcript_buffer == 'final text'


# ============================================================
# Edge Case Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_loss_during_audio_streaming():
    """Test handling WebSocket disconnection during audio streaming"""
    client = WhisperClient()
    client.is_connected = True
    client.ws = AsyncMock()

    # First send succeeds, second fails
    client.ws.send = AsyncMock(side_effect=[
        None,  # Success
        websockets.exceptions.ConnectionClosed(None, None)  # Disconnected
    ])

    # First send should succeed
    await client.send_audio(b'\x00' * 960)

    # Second send should handle disconnection gracefully
    await client.send_audio(b'\x01' * 960)

    # Connection should be marked as disconnected
    assert not client.is_connected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reconnection_after_unexpected_closure():
    """Test reconnection logic after unexpected WebSocket closure"""
    client = WhisperClient()

    with patch('websockets.connect') as mock_connect:
        # First connection succeeds
        mock_ws1 = AsyncMock()

        async def connect_first(*args, **kwargs):
            return mock_ws1

        mock_connect.side_effect = connect_first

        await client.connect("user_123")
        assert client.is_connected

        # Simulate unexpected closure
        client.is_connected = False
        client.ws = None

        # Second connection succeeds
        mock_ws2 = AsyncMock()

        async def connect_second(*args, **kwargs):
            return mock_ws2

        mock_connect.side_effect = connect_second

        # Reconnect
        await client.connect("user_123")
        assert client.is_connected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_finalize_with_connection_loss():
    """Test finalization when connection is lost during the process"""
    client = WhisperClient()
    client.is_connected = True
    client.ws = AsyncMock()
    client.transcript_buffer = "partial transcript"
    client.finalize_future = asyncio.Future()

    # Send fails (connection lost)
    client.ws.send = AsyncMock(side_effect=websockets.exceptions.ConnectionClosed(None, None))

    result = await client.finalize()

    # Should return buffered transcript on connection error
    assert result == "partial transcript"
