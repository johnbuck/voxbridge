"""
Unit tests for WebRTCVoiceHandler

Tests WebRTC voice streaming:
- Session validation (valid session, invalid session, wrong user)
- Opus audio decoding (valid Opus data, invalid data)
- WhisperX integration (streaming audio, receiving transcripts)
- VAD logic (silence detection, transcript finalization)
- Database message persistence (user messages, AI responses)
- LLM integration (streaming responses, error handling)
- Error handling (WebSocket disconnect, WhisperX errors, LLM errors)

VoxBridge 2.0 Phase 4: Web Voice Interface
"""
from __future__ import annotations

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import UUID, uuid4
import opuslib
from fastapi import WebSocketDisconnect

from src.voice.webrtc_handler import WebRTCVoiceHandler


# ============================================================
# Session Validation Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_valid_session_initialization():
    """Test handler initializes with valid session"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    # Assertions
    assert handler.websocket == mock_websocket
    assert handler.user_id == user_id
    assert handler.session_id == session_id
    assert handler.is_active is True
    assert handler.current_transcript == ""
    assert handler.is_finalizing is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_validation_success():
    """Test start() validates session successfully"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    # Mock session
    mock_session = MagicMock()
    mock_session.user_id = user_id
    mock_session.agent_id = uuid4()
    mock_session.title = "Test Session"

    with patch('src.voice.webrtc_handler.SessionService') as MockSessionService:
        MockSessionService.get_session = AsyncMock(return_value=mock_session)

        with patch.object(handler, '_connect_whisperx', new_callable=AsyncMock) as mock_connect:
            with patch.object(handler, '_audio_loop', new_callable=AsyncMock) as mock_loop:
                await handler.start()

                # Verify session was retrieved
                MockSessionService.get_session.assert_called_once_with(session_id)

                # Verify WhisperX connection
                mock_connect.assert_called_once()

                # Verify audio loop started
                mock_loop.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_validation_not_found():
    """Test start() handles session not found"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    with patch('src.voice.webrtc_handler.SessionService') as MockSessionService:
        MockSessionService.get_session = AsyncMock(return_value=None)

        with patch.object(handler, '_send_error', new_callable=AsyncMock) as mock_error:
            await handler.start()

            # Verify error was sent
            mock_error.assert_called_once_with("Session not found")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_validation_wrong_user():
    """Test start() rejects session belonging to different user"""
    mock_websocket = AsyncMock()
    user_id = "user_123"
    session_id = uuid4()

    handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

    # Mock session with different user_id
    mock_session = MagicMock()
    mock_session.user_id = "different_user"

    with patch('src.voice.webrtc_handler.SessionService') as MockSessionService:
        MockSessionService.get_session = AsyncMock(return_value=mock_session)

        with patch.object(handler, '_send_error', new_callable=AsyncMock) as mock_error:
            await handler.start()

            # Verify error was sent
            mock_error.assert_called_once_with("Session does not belong to user")


# ============================================================
# Opus Audio Decoding Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_opus_decode_valid_data():
    """Test decoding valid Opus audio data"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    # Mock WhisperClient
    mock_whisper = AsyncMock()
    mock_whisper.is_connected = True
    mock_whisper.send_audio = AsyncMock()
    handler.whisper_client = mock_whisper

    # Create valid Opus frame (silence for simplicity)
    # Opus encoder for testing
    opus_encoder = opuslib.Encoder(16000, 1, opuslib.APPLICATION_VOIP)
    pcm_data = b'\x00' * 640  # 320 samples * 2 bytes = 640 bytes (20ms @ 16kHz mono)
    opus_frame = opus_encoder.encode(pcm_data, 320)

    # Mock WebSocket receive - return frame once, then raise to exit loop
    call_count = 0
    async def mock_receive_bytes():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return opus_frame
        # Raise exception to exit loop after one frame
        raise WebSocketDisconnect()

    mock_websocket.receive_bytes = mock_receive_bytes

    # Mock silence monitoring to prevent it from running
    async def mock_monitor_silence():
        pass

    with patch.object(handler, '_monitor_silence', new=mock_monitor_silence):
        # Create audio loop task
        loop_task = asyncio.create_task(handler._audio_loop())

        # Wait for loop to complete
        try:
            await asyncio.wait_for(loop_task, timeout=1.0)
        except asyncio.TimeoutError:
            loop_task.cancel()

    # Verify audio was sent to WhisperX
    mock_whisper.send_audio.assert_called()
    # Verify it was called with PCM data
    call_args = mock_whisper.send_audio.call_args
    assert call_args is not None
    assert len(call_args[0][0]) > 0  # PCM data should be non-empty


@pytest.mark.unit
@pytest.mark.asyncio
async def test_opus_decode_invalid_data():
    """Test handling invalid Opus data gracefully"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    # Mock WhisperClient
    mock_whisper = AsyncMock()
    mock_whisper.is_connected = True
    mock_whisper.send_audio = AsyncMock()
    handler.whisper_client = mock_whisper

    # Invalid Opus data
    invalid_opus = b'\xff\xfe\xfd\xfc'

    # Mock WebSocket receive - return invalid data once, then raise to exit loop
    call_count = 0
    async def mock_receive_bytes():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return invalid_opus
        # Raise exception to exit loop after one frame
        raise WebSocketDisconnect()

    mock_websocket.receive_bytes = mock_receive_bytes

    # Mock silence monitoring to prevent it from running
    async def mock_monitor_silence():
        pass

    with patch.object(handler, '_monitor_silence', new=mock_monitor_silence):
        # Create audio loop task
        loop_task = asyncio.create_task(handler._audio_loop())

        # Wait for loop to complete
        try:
            await asyncio.wait_for(loop_task, timeout=1.0)
        except asyncio.TimeoutError:
            loop_task.cancel()

    # Should continue processing despite error (logged but not raised)
    # Verify send_audio was NOT called due to decode error
    mock_whisper.send_audio.assert_not_called()


# ============================================================
# WhisperX Integration Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_connect_whisperx_success():
    """Test connecting to WhisperX server"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    with patch('src.voice.webrtc_handler.WhisperClient') as MockWhisperClient:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        MockWhisperClient.return_value = mock_client

        await handler._connect_whisperx()

        # Verify WhisperClient was created
        MockWhisperClient.assert_called_once()

        # Verify connection was established
        mock_client.connect.assert_called_once_with("user_123")

        # Verify callbacks were set
        assert handler.whisper_client == mock_client
        assert handler.whisper_client.on_partial_callback is not None
        assert handler.whisper_client.on_final_callback is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_whisper_partial_transcript_callback():
    """Test partial transcript callback sends to browser"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    with patch('src.voice.webrtc_handler.WhisperClient') as MockWhisperClient:
        mock_client = AsyncMock()
        MockWhisperClient.return_value = mock_client

        await handler._connect_whisperx()

        # Get the partial callback
        partial_callback = handler.whisper_client.on_partial_callback

        # Trigger callback
        await partial_callback("Hello world")

        # Verify transcript was updated
        assert handler.current_transcript == "Hello world"

        # Verify WebSocket message was sent
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args['event'] == 'partial_transcript'
        assert call_args['data']['text'] == "Hello world"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_whisper_final_transcript_callback():
    """Test final transcript callback (logs but doesn't process)"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    with patch('src.voice.webrtc_handler.WhisperClient') as MockWhisperClient:
        mock_client = AsyncMock()
        MockWhisperClient.return_value = mock_client

        await handler._connect_whisperx()

        # Get the final callback
        final_callback = handler.whisper_client.on_final_callback

        # Trigger callback (should just log)
        await final_callback("Final transcript")

        # No processing should happen until finalize() is called
        # (finalization is triggered by silence detection, not callback)


# ============================================================
# VAD (Silence Detection) Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_silence_monitor_detects_silence():
    """Test silence monitor triggers finalization after threshold"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())
    handler.silence_threshold_ms = 100  # Fast for testing

    # Mock WhisperClient
    mock_whisper = AsyncMock()
    mock_whisper.finalize = AsyncMock(return_value="test transcript")
    mock_whisper.close = AsyncMock()
    handler.whisper_client = mock_whisper

    # Set last audio time to past
    handler.last_audio_time = time.time() - 0.2  # 200ms ago

    # Mock finalization
    with patch.object(handler, '_finalize_transcription', new_callable=AsyncMock) as mock_finalize:
        # Start silence monitor
        monitor_task = asyncio.create_task(handler._monitor_silence())

        # Wait for detection
        await asyncio.sleep(0.15)

        # Verify finalization was triggered
        mock_finalize.assert_called_once()

        # Cancel task
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass


@pytest.mark.unit
@pytest.mark.asyncio
async def test_silence_monitor_resets_on_audio():
    """Test silence monitor resets when audio continues"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())
    handler.silence_threshold_ms = 200  # 200ms

    # Set initial audio time
    handler.last_audio_time = time.time()

    with patch.object(handler, '_finalize_transcription', new_callable=AsyncMock) as mock_finalize:
        # Start silence monitor
        monitor_task = asyncio.create_task(handler._monitor_silence())

        # Wait half the threshold
        await asyncio.sleep(0.1)

        # Simulate more audio
        handler.last_audio_time = time.time()

        # Wait another half threshold
        await asyncio.sleep(0.1)

        # Should NOT have finalized (timer reset)
        mock_finalize.assert_not_called()

        # Cancel task
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass


# ============================================================
# Transcript Finalization Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_finalize_transcription_success():
    """Test successful transcription finalization and LLM routing"""
    mock_websocket = AsyncMock()
    session_id = uuid4()
    agent_id = uuid4()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", session_id)

    # Mock WhisperClient
    mock_whisper = AsyncMock()
    mock_whisper.finalize = AsyncMock(return_value="Hello world")
    handler.whisper_client = mock_whisper

    # Mock session
    mock_session = MagicMock()
    mock_session.agent_id = agent_id

    # Mock agent
    mock_agent = MagicMock()
    mock_agent.name = "Test Agent"
    mock_agent.llm_provider = "openrouter"
    mock_agent.llm_model = "anthropic/claude-3-sonnet"
    mock_agent.system_prompt = "You are a helpful assistant"
    mock_agent.temperature = 0.7

    with patch('src.voice.webrtc_handler.SessionService') as MockSessionService:
        MockSessionService.get_session = AsyncMock(return_value=mock_session)
        MockSessionService.add_message = AsyncMock()

        with patch('src.voice.webrtc_handler.AgentService') as MockAgentService:
            MockAgentService.get_agent = AsyncMock(return_value=mock_agent)

            with patch.object(handler, '_handle_llm_response', new_callable=AsyncMock) as mock_llm:
                with patch.object(handler, '_send_final_transcript', new_callable=AsyncMock) as mock_send:
                    await handler._finalize_transcription()

                    # Verify final transcript was sent to browser
                    mock_send.assert_called_once_with("Hello world")

                    # Verify message was saved to database
                    MockSessionService.add_message.assert_called_once_with(
                        session_id=session_id,
                        role="user",
                        content="Hello world"
                    )

                    # Verify LLM handler was called
                    mock_llm.assert_called_once()
                    call_args = mock_llm.call_args[0]
                    assert call_args[0] == "Hello world"
                    assert call_args[1] == mock_agent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_finalize_empty_transcript():
    """Test finalization with empty transcript (skipped)"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    # Mock WhisperClient returning empty transcript
    mock_whisper = AsyncMock()
    mock_whisper.finalize = AsyncMock(return_value="   ")  # Whitespace only
    handler.whisper_client = mock_whisper

    with patch('src.voice.webrtc_handler.SessionService') as MockSessionService:
        MockSessionService.add_message = AsyncMock()

        await handler._finalize_transcription()

        # Should not save message (empty transcript)
        MockSessionService.add_message.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_finalize_duplicate_prevention():
    """Test finalization can only happen once"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    # Mock WhisperClient
    mock_whisper = AsyncMock()
    mock_whisper.finalize = AsyncMock(return_value="test")
    handler.whisper_client = mock_whisper

    # First finalization
    await handler._finalize_transcription()
    assert handler.is_finalizing is True

    # Second finalization should be no-op
    with patch('src.voice.webrtc_handler.SessionService') as MockSessionService:
        MockSessionService.add_message = AsyncMock()

        await handler._finalize_transcription()

        # Should not call database (duplicate)
        MockSessionService.add_message.assert_not_called()


# ============================================================
# LLM Integration Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_llm_response_streaming():
    """Test LLM response streaming to browser"""
    mock_websocket = AsyncMock()
    session_id = uuid4()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", session_id)

    # Mock agent
    mock_agent = MagicMock()
    mock_agent.name = "Test Agent"
    mock_agent.system_prompt = "You are helpful"
    mock_agent.temperature = 0.7
    mock_agent.llm_provider = "openrouter"
    mock_agent.llm_model = "anthropic/claude-3-sonnet"

    # Mock LLM provider - new API returns plain strings
    mock_provider = AsyncMock()

    async def mock_stream(request):
        yield "Hello "
        yield "world"
        yield "!"

    mock_provider.generate_stream = mock_stream
    mock_provider.close = AsyncMock()

    with patch('src.voice.webrtc_handler.LLMProviderFactory') as MockFactory:
        MockFactory.create_from_agent_config = MagicMock(return_value=(mock_provider, "anthropic/claude-3-sonnet"))

        with patch('src.voice.webrtc_handler.SessionService') as MockSessionService:
            MockSessionService.add_message = AsyncMock()

            with patch.object(handler, '_send_ai_response_chunk', new_callable=AsyncMock) as mock_chunk:
                with patch.object(handler, '_send_ai_response_complete', new_callable=AsyncMock) as mock_complete:
                    await handler._handle_llm_response("test transcript", mock_agent)

                    # Verify all chunks were sent
                    assert mock_chunk.call_count == 3
                    mock_chunk.assert_any_call("Hello ")
                    mock_chunk.assert_any_call("world")
                    mock_chunk.assert_any_call("!")

                    # Verify completion was sent
                    mock_complete.assert_called_once_with("Hello world!")

                    # Verify full response was saved to database
                    MockSessionService.add_message.assert_called_once_with(
                        session_id=session_id,
                        role="assistant",
                        content="Hello world!"
                    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_llm_error():
    """Test LLM error handling"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    # Mock agent
    mock_agent = MagicMock()
    mock_agent.name = "Test Agent"
    mock_agent.system_prompt = "You are helpful"
    mock_agent.temperature = 0.7
    mock_agent.llm_provider = "openrouter"
    mock_agent.llm_model = "anthropic/claude-3-sonnet"

    # Mock LLM provider that raises error
    from src.llm.types import LLMError

    mock_provider = AsyncMock()

    async def mock_stream_error(request):
        raise LLMError("Rate limit exceeded")
        yield  # Make it a generator

    mock_provider.generate_stream = mock_stream_error
    mock_provider.close = AsyncMock()

    with patch('src.voice.webrtc_handler.LLMProviderFactory') as MockFactory:
        MockFactory.create_from_agent_config = MagicMock(return_value=(mock_provider, "anthropic/claude-3-sonnet"))

        with patch.object(handler, '_send_error', new_callable=AsyncMock) as mock_error:
            await handler._handle_llm_response("test", mock_agent)

            # Verify error was sent to browser
            mock_error.assert_called_once()
            call_args = mock_error.call_args[0][0]
            # LLMError should be caught and prefixed with "AI error:"
            assert "AI error:" in call_args
            assert "Rate limit exceeded" in call_args


# ============================================================
# Database Message Persistence Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_save_user_message_to_database():
    """Test user message is saved to database after finalization"""
    mock_websocket = AsyncMock()
    session_id = uuid4()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", session_id)

    # Mock WhisperClient
    mock_whisper = AsyncMock()
    mock_whisper.finalize = AsyncMock(return_value="User message")
    handler.whisper_client = mock_whisper

    # Mock session
    mock_session = MagicMock()
    mock_session.agent_id = uuid4()

    with patch('src.voice.webrtc_handler.SessionService') as MockSessionService:
        MockSessionService.get_session = AsyncMock(return_value=mock_session)
        MockSessionService.add_message = AsyncMock()

        with patch('src.voice.webrtc_handler.AgentService') as MockAgentService:
            MockAgentService.get_agent = AsyncMock(return_value=None)  # Skip LLM

            with patch.object(handler, '_send_final_transcript', new_callable=AsyncMock):
                await handler._finalize_transcription()

                # Verify user message was saved
                MockSessionService.add_message.assert_called_once_with(
                    session_id=session_id,
                    role="user",
                    content="User message"
                )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_save_ai_message_to_database():
    """Test AI response is saved to database after streaming"""
    mock_websocket = AsyncMock()
    session_id = uuid4()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", session_id)

    # Mock agent
    mock_agent = MagicMock()
    mock_agent.system_prompt = "System"
    mock_agent.temperature = 0.7
    mock_agent.llm_provider = "openrouter"
    mock_agent.llm_model = "anthropic/claude-3-sonnet"

    # Mock LLM provider - new API returns plain strings
    mock_provider = AsyncMock()

    async def mock_stream(request):
        yield "AI response"

    mock_provider.generate_stream = mock_stream
    mock_provider.close = AsyncMock()

    with patch('src.voice.webrtc_handler.LLMProviderFactory') as MockFactory:
        MockFactory.create_from_agent_config = MagicMock(return_value=(mock_provider, "anthropic/claude-3-sonnet"))

        with patch('src.voice.webrtc_handler.SessionService') as MockSessionService:
            MockSessionService.add_message = AsyncMock()

            with patch.object(handler, '_send_ai_response_chunk', new_callable=AsyncMock):
                with patch.object(handler, '_send_ai_response_complete', new_callable=AsyncMock):
                    await handler._handle_llm_response("test", mock_agent)

                    # Verify AI message was saved
                    MockSessionService.add_message.assert_called_once_with(
                        session_id=session_id,
                        role="assistant",
                        content="AI response"
                    )


# ============================================================
# WebSocket Message Sending Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_partial_transcript():
    """Test sending partial transcript to browser"""
    mock_websocket = AsyncMock()
    session_id = uuid4()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", session_id)

    await handler._send_partial_transcript("Partial text")

    # Verify WebSocket message
    mock_websocket.send_json.assert_called_once()
    call_args = mock_websocket.send_json.call_args[0][0]
    assert call_args['event'] == 'partial_transcript'
    assert call_args['data']['text'] == "Partial text"
    assert call_args['data']['session_id'] == str(session_id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_final_transcript():
    """Test sending final transcript to browser"""
    mock_websocket = AsyncMock()
    session_id = uuid4()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", session_id)

    await handler._send_final_transcript("Final text")

    # Verify WebSocket message
    mock_websocket.send_json.assert_called_once()
    call_args = mock_websocket.send_json.call_args[0][0]
    assert call_args['event'] == 'final_transcript'
    assert call_args['data']['text'] == "Final text"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_ai_response_chunk():
    """Test sending AI response chunk to browser"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    await handler._send_ai_response_chunk("AI chunk")

    # Verify WebSocket message
    mock_websocket.send_json.assert_called_once()
    call_args = mock_websocket.send_json.call_args[0][0]
    assert call_args['event'] == 'ai_response_chunk'
    assert call_args['data']['text'] == "AI chunk"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_error():
    """Test sending error message to browser"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    await handler._send_error("Test error")

    # Verify WebSocket message
    mock_websocket.send_json.assert_called_once()
    call_args = mock_websocket.send_json.call_args[0][0]
    assert call_args['event'] == 'error'
    assert call_args['data']['message'] == "Test error"


# ============================================================
# Cleanup Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_cleanup_closes_resources():
    """Test cleanup properly closes all resources"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    # Mock WhisperClient
    mock_whisper = AsyncMock()
    mock_whisper.close = AsyncMock()
    handler.whisper_client = mock_whisper

    # Mock silence task
    mock_task = MagicMock()
    mock_task.done = MagicMock(return_value=False)
    mock_task.cancel = MagicMock()
    handler.silence_task = mock_task

    await handler._cleanup()

    # Verify WhisperClient was closed
    mock_whisper.close.assert_called_once()

    # Verify silence task was cancelled
    mock_task.cancel.assert_called_once()

    # Verify WebSocket was closed
    mock_websocket.close.assert_called_once()

    # Verify is_active flag was cleared
    assert handler.is_active is False


# ============================================================
# Error Handling Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_websocket_disconnect_during_processing():
    """Test handling WebSocket disconnect during audio processing"""
    from fastapi import WebSocketDisconnect

    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    # Mock session validation
    mock_session = MagicMock()
    mock_session.user_id = "user_123"

    with patch('src.voice.webrtc_handler.SessionService') as MockSessionService:
        MockSessionService.get_session = AsyncMock(return_value=mock_session)

        with patch.object(handler, '_connect_whisperx', new_callable=AsyncMock):
            # Mock audio loop to raise WebSocketDisconnect
            with patch.object(handler, '_audio_loop', new_callable=AsyncMock) as mock_loop:
                mock_loop.side_effect = WebSocketDisconnect

                with patch.object(handler, '_cleanup', new_callable=AsyncMock) as mock_cleanup:
                    # Should handle disconnect gracefully
                    await handler.start()

                    # Verify cleanup was called
                    mock_cleanup.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_whisperx_connection_failure():
    """Test handling WhisperX connection failure"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    with patch('src.voice.webrtc_handler.WhisperClient') as MockWhisperClient:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock(side_effect=Exception("Connection failed"))
        MockWhisperClient.return_value = mock_client

        # Should raise exception
        with pytest.raises(Exception, match="Connection failed"):
            await handler._connect_whisperx()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_provider_creation_failure():
    """Test handling LLM provider creation failure"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    # Mock agent
    mock_agent = MagicMock()
    mock_agent.llm_provider = "invalid_provider"
    mock_agent.llm_model = "invalid_model"

    with patch('src.voice.webrtc_handler.LLMProviderFactory') as MockFactory:
        MockFactory.create_from_agent_config = MagicMock(side_effect=Exception("Unknown provider"))

        with patch.object(handler, '_send_error', new_callable=AsyncMock) as mock_error:
            await handler._handle_llm_response("test", mock_agent)

            # Verify error was sent
            mock_error.assert_called_once()
            call_args = mock_error.call_args[0][0]
            assert "Error generating AI response" in call_args


# ============================================================
# Latency Tracking Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_latency_tracking_first_transcript():
    """Test latency tracking for first transcript"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    # Record start time
    handler.t_start = time.time()
    handler.t_first_transcript = None

    with patch('src.voice.webrtc_handler.WhisperClient') as MockWhisperClient:
        mock_client = AsyncMock()
        MockWhisperClient.return_value = mock_client

        await handler._connect_whisperx()

        # Get partial callback
        partial_callback = handler.whisper_client.on_partial_callback

        # Trigger callback
        await partial_callback("First transcript")

        # Verify latency timestamp was recorded
        assert handler.t_first_transcript is not None
        assert handler.t_first_transcript >= handler.t_start


@pytest.mark.unit
@pytest.mark.asyncio
async def test_latency_tracking_llm_first_chunk():
    """Test latency tracking for LLM first chunk"""
    mock_websocket = AsyncMock()
    handler = WebRTCVoiceHandler(mock_websocket, "user_123", uuid4())

    # Mock agent
    mock_agent = MagicMock()
    mock_agent.system_prompt = "System"
    mock_agent.temperature = 0.7
    mock_agent.llm_provider = "openrouter"
    mock_agent.llm_model = "anthropic/claude-3-sonnet"

    # Mock LLM provider with delayed chunks - new API returns plain strings
    mock_provider = AsyncMock()

    async def mock_stream(request):
        await asyncio.sleep(0.05)  # Simulate network delay
        yield "First chunk"
        yield "Second chunk"

    mock_provider.generate_stream = mock_stream
    mock_provider.close = AsyncMock()

    with patch('src.voice.webrtc_handler.LLMProviderFactory') as MockFactory:
        MockFactory.create_from_agent_config = MagicMock(return_value=(mock_provider, "anthropic/claude-3-sonnet"))

        with patch('src.voice.webrtc_handler.SessionService') as MockSessionService:
            MockSessionService.add_message = AsyncMock()

            with patch.object(handler, '_send_ai_response_chunk', new_callable=AsyncMock):
                with patch.object(handler, '_send_ai_response_complete', new_callable=AsyncMock):
                    # Latency should be logged (test passes if no exception)
                    await handler._handle_llm_response("test", mock_agent)
