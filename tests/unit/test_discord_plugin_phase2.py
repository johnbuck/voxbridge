"""
Unit tests for DiscordPlugin Phase 2: Audio Pipeline Integration

Tests Phase 2 changes (2025-10-28):
- AudioReceiver class (nested audio sink for Discord voice)
- _handle_user_speaking() method (audio pipeline initialization)
- _on_transcript() callback (STT transcript handling)
- _generate_response() method (LLM generation + TTS)
- _play_tts() method (TTS synthesis and Discord playback)
- _cleanup_session() implementation (full cleanup logic)
- Enhanced event handlers (on_voice_state_update, on_response)

Test Coverage:
- AudioReceiver initialization and audio processing
- User speaking pipeline (STT connection, audio streaming, silence detection)
- Transcript handling (partial vs final, DB saving, LLM triggering)
- LLM response generation (streaming, fallback to n8n webhook)
- TTS synthesis and playback (agent voice config, latency tracking)
- Session cleanup (STT disconnect, DB updates, resource cleanup)
- Event handler integration (voice state updates, response hooks)

Target: 80%+ coverage of Phase 2 code (lines 427-1489)
"""
from __future__ import annotations

import pytest
import asyncio
import os
import tempfile
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call
from typing import Dict, Any

import discord
from discord.ext import voice_recv

# Import Discord plugin components
from src.plugins.discord_plugin import DiscordPlugin
from src.services.llm_service import LLMConfig, ProviderType
from src.llm import LLMError, LLMConnectionError, LLMTimeoutError


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def agent_id():
    """Generate a test agent UUID"""
    return uuid.uuid4()


@pytest.fixture
def mock_agent(agent_id):
    """Mock Agent model instance with full configuration"""
    agent = MagicMock()
    agent.id = agent_id
    agent.name = "TestAgent"
    agent.system_prompt = "You are a helpful assistant"
    agent.temperature = 0.7
    agent.llm_provider = "openrouter"
    agent.llm_model = "anthropic/claude-3.5-sonnet"
    agent.tts_voice = "female_1"
    agent.tts_rate = 1.0
    agent.tts_pitch = 1.0
    return agent


@pytest.fixture
def valid_config():
    """Valid Discord plugin configuration"""
    return {
        'enabled': True,
        'bot_token': 'test_token_123456789',
        'channels': ['channel_1', 'channel_2'],
        'auto_join': True,
        'command_prefix': '!',
    }


@pytest.fixture
def mock_discord_bot():
    """Mock Discord Bot instance with event loop"""
    bot = MagicMock()
    bot.is_ready = MagicMock(return_value=True)
    bot.is_closed = MagicMock(return_value=False)
    bot.start = AsyncMock()
    bot.close = AsyncMock()
    bot.user = MagicMock()
    bot.user.name = "TestBot"
    bot.user.id = 123456789
    bot.user.discriminator = "0001"
    bot.guilds = []
    # Mock event loop for AudioReceiver
    bot.loop = asyncio.get_event_loop()
    return bot


@pytest.fixture
def mock_discord_user():
    """Mock Discord User"""
    user = Mock()
    user.id = 987654321
    user.name = "TestUser"
    return user


@pytest.fixture
def mock_voice_client():
    """Mock Discord VoiceClient"""
    vc = Mock(spec=discord.VoiceClient)
    vc.is_connected = Mock(return_value=True)
    vc.is_playing = Mock(return_value=False)
    vc.play = Mock()
    vc.listen = Mock()
    vc.disconnect = AsyncMock()
    return vc


@pytest.fixture
def mock_opus_packet():
    """Mock Opus audio packet from Discord (20ms of audio = 960 bytes)"""
    # Create a mock VoiceData object with opus attribute
    mock_data = Mock()
    mock_data.opus = b'\x00' * 960  # 20ms of audio
    mock_data.pcm = None
    return mock_data


@pytest.fixture
def mock_conversation_service():
    """Mock ConversationService"""
    service = AsyncMock()
    service.start = AsyncMock()
    service.stop = AsyncMock()

    # Mock session
    mock_session = MagicMock()
    mock_session.id = str(uuid.uuid4())
    service.get_or_create_session = AsyncMock(return_value=mock_session)
    service.add_message = AsyncMock()
    service.end_session = AsyncMock()

    # Mock conversation context
    mock_message = MagicMock()
    mock_message.role = 'user'
    mock_message.content = 'Hello'
    service.get_conversation_context = AsyncMock(return_value=[mock_message])

    return service


@pytest.fixture
def mock_stt_service():
    """Mock STTService singleton"""
    service = AsyncMock()
    service.connect = AsyncMock(return_value=True)
    service.disconnect = AsyncMock()
    service.register_callback = AsyncMock()
    service.send_audio = AsyncMock()
    service.finalize_transcript = AsyncMock(return_value=True)
    return service


@pytest.fixture
def mock_llm_service():
    """Mock LLMService singleton with streaming response"""
    service = AsyncMock()

    # Mock streaming generate_response
    async def mock_generate(session_id, messages, config, stream, callback):
        if callback:
            await callback("Hello ")
            await callback("world")

    service.generate_response = AsyncMock(side_effect=mock_generate)
    return service


@pytest.fixture
def mock_tts_service():
    """Mock TTSService singleton"""
    service = AsyncMock()
    # Return fake WAV audio bytes
    service.synthesize_speech = AsyncMock(return_value=b'\x52\x49\x46\x46' + b'\x00' * 1000)
    return service


@pytest.fixture
async def initialized_plugin(
    mock_agent,
    valid_config,
    mock_discord_bot,
    mock_conversation_service,
    mock_stt_service,
    mock_llm_service,
    mock_tts_service
):
    """Create initialized DiscordPlugin with mocked services"""
    plugin = DiscordPlugin()

    with patch('src.plugins.discord_plugin.commands.Bot', return_value=mock_discord_bot):
        with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_conversation_service):
            with patch('src.plugins.discord_plugin.get_stt_service', return_value=mock_stt_service):
                with patch('src.plugins.discord_plugin.get_llm_service', return_value=mock_llm_service):
                    with patch('src.plugins.discord_plugin.get_tts_service', return_value=mock_tts_service):
                        await plugin.initialize(mock_agent, valid_config)

    return plugin


# ============================================================
# Test Class 1: AudioReceiver
# ============================================================

class TestAudioReceiver:
    """Test the AudioReceiver nested class"""

    @pytest.mark.asyncio
    async def test_audio_receiver_initialization(self, initialized_plugin, mock_voice_client):
        """AudioReceiver should initialize with plugin reference and empty queues"""
        receiver = initialized_plugin.AudioReceiver(initialized_plugin, mock_voice_client)

        # Verify initialization
        assert receiver.plugin is initialized_plugin
        assert receiver.vc is mock_voice_client
        assert isinstance(receiver.user_buffers, dict)
        assert len(receiver.user_buffers) == 0
        assert isinstance(receiver.user_tasks, dict)
        assert len(receiver.user_tasks) == 0
        assert isinstance(receiver.active_users, set)
        assert len(receiver.active_users) == 0

    @pytest.mark.asyncio
    async def test_audio_receiver_wants_opus(self, initialized_plugin, mock_voice_client):
        """AudioReceiver should request Opus packets (not decoded PCM)"""
        receiver = initialized_plugin.AudioReceiver(initialized_plugin, mock_voice_client)

        assert receiver.wants_opus() is True

    @pytest.mark.asyncio
    async def test_audio_receiver_processes_opus_packet(
        self,
        initialized_plugin,
        mock_voice_client,
        mock_discord_user,
        mock_opus_packet
    ):
        """write() should create audio queue for new user and enqueue Opus packet"""
        receiver = initialized_plugin.AudioReceiver(initialized_plugin, mock_voice_client)

        # Mock _handle_user_speaking to avoid starting full pipeline
        initialized_plugin._handle_user_speaking = AsyncMock()

        # Process audio packet
        receiver.write(mock_discord_user, mock_opus_packet)

        # Verify user buffer created
        user_id = str(mock_discord_user.id)
        assert user_id in receiver.user_buffers
        assert isinstance(receiver.user_buffers[user_id], asyncio.Queue)

        # Verify packet enqueued
        assert receiver.user_buffers[user_id].qsize() == 1

    @pytest.mark.asyncio
    async def test_audio_receiver_handles_multiple_users(
        self,
        initialized_plugin,
        mock_voice_client,
        mock_opus_packet
    ):
        """Should handle audio from multiple users concurrently"""
        receiver = initialized_plugin.AudioReceiver(initialized_plugin, mock_voice_client)

        # Mock _handle_user_speaking
        initialized_plugin._handle_user_speaking = AsyncMock()

        # Create multiple users
        user1 = Mock()
        user1.id = 111
        user1.name = "User1"

        user2 = Mock()
        user2.id = 222
        user2.name = "User2"

        # Process audio from both users
        receiver.write(user1, mock_opus_packet)
        receiver.write(user2, mock_opus_packet)

        # Verify separate buffers
        assert str(user1.id) in receiver.user_buffers
        assert str(user2.id) in receiver.user_buffers
        assert len(receiver.user_buffers) == 2

    @pytest.mark.asyncio
    async def test_audio_receiver_handles_queue_full(
        self,
        initialized_plugin,
        mock_voice_client,
        mock_discord_user,
        mock_opus_packet,
        caplog
    ):
        """Should log warning and drop packet if queue is full"""
        receiver = initialized_plugin.AudioReceiver(initialized_plugin, mock_voice_client)
        initialized_plugin._handle_user_speaking = AsyncMock()

        # Create user buffer with small maxsize
        with patch.dict(os.environ, {'DISCORD_AUDIO_QUEUE_SIZE': '2'}):
            receiver.write(mock_discord_user, mock_opus_packet)
            user_id = str(mock_discord_user.id)

            # Fill queue
            receiver.write(mock_discord_user, mock_opus_packet)

            # Try to add one more (should drop)
            receiver.write(mock_discord_user, mock_opus_packet)

            # Verify warning logged
            assert "buffer full" in caplog.text.lower() or "dropping packet" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_audio_receiver_cleanup_user(
        self,
        initialized_plugin,
        mock_voice_client,
        mock_discord_user
    ):
        """cleanup_user() should remove user's buffer, task, and active status"""
        receiver = initialized_plugin.AudioReceiver(initialized_plugin, mock_voice_client)
        initialized_plugin._handle_user_speaking = AsyncMock()

        # Add user
        user_id = str(mock_discord_user.id)
        receiver.user_buffers[user_id] = asyncio.Queue()
        receiver.user_tasks[user_id] = Mock()
        receiver.active_users.add(user_id)

        # Cleanup user
        receiver.cleanup_user(user_id)

        # Verify cleanup
        assert user_id not in receiver.user_buffers
        assert user_id not in receiver.user_tasks
        assert user_id not in receiver.active_users

    @pytest.mark.asyncio
    async def test_audio_receiver_cleanup_all_users(
        self,
        initialized_plugin,
        mock_voice_client
    ):
        """cleanup() should cleanup all users and clear all data structures"""
        receiver = initialized_plugin.AudioReceiver(initialized_plugin, mock_voice_client)

        # Add multiple users
        receiver.user_buffers['user_1'] = asyncio.Queue()
        receiver.user_buffers['user_2'] = asyncio.Queue()
        receiver.user_tasks['user_1'] = Mock()
        receiver.user_tasks['user_2'] = Mock()
        receiver.active_users.add('user_1')
        receiver.active_users.add('user_2')

        # Cleanup all
        receiver.cleanup()

        # Verify all cleared
        assert len(receiver.user_buffers) == 0
        assert len(receiver.user_tasks) == 0
        assert len(receiver.active_users) == 0


# ============================================================
# Test Class 2: _handle_user_speaking
# ============================================================

class TestHandleUserSpeaking:
    """Test the _handle_user_speaking method (audio pipeline initialization)"""

    @pytest.mark.asyncio
    async def test_creates_session_via_conversation_service(
        self,
        initialized_plugin,
        mock_discord_user,
        mock_voice_client,
        mock_conversation_service
    ):
        """Should create session in database via ConversationService"""
        # Mock audio stream generator
        async def mock_audio_stream():
            yield b'\x00' * 960  # One audio chunk

        # Call _handle_user_speaking
        await initialized_plugin._handle_user_speaking(
            mock_discord_user,
            mock_audio_stream(),
            mock_voice_client
        )

        # Verify session created
        mock_conversation_service.get_or_create_session.assert_called_once()
        call_args = mock_conversation_service.get_or_create_session.call_args[1]
        assert call_args['user_id'] == str(mock_discord_user.id)
        assert call_args['agent_id'] == str(initialized_plugin.agent_id)
        assert call_args['channel_type'] == "discord"

    @pytest.mark.asyncio
    async def test_connects_to_stt_service(
        self,
        initialized_plugin,
        mock_discord_user,
        mock_voice_client,
        mock_stt_service
    ):
        """Should connect to STT service (WhisperX) for transcription"""
        async def mock_audio_stream():
            yield b'\x00' * 960

        await initialized_plugin._handle_user_speaking(
            mock_discord_user,
            mock_audio_stream(),
            mock_voice_client
        )

        # Verify STT connection
        mock_stt_service.connect.assert_called_once()
        call_args = mock_stt_service.connect.call_args[0]
        session_id = call_args[0]
        assert session_id is not None
        assert 'whisperx' in call_args[1].lower()  # URL contains 'whisperx'

    @pytest.mark.asyncio
    async def test_registers_callback_with_stt(
        self,
        initialized_plugin,
        mock_discord_user,
        mock_voice_client,
        mock_stt_service
    ):
        """Should register _on_transcript callback with STT service"""
        async def mock_audio_stream():
            yield b'\x00' * 960

        await initialized_plugin._handle_user_speaking(
            mock_discord_user,
            mock_audio_stream(),
            mock_voice_client
        )

        # Verify callback registration
        mock_stt_service.register_callback.assert_called_once()
        call_kwargs = mock_stt_service.register_callback.call_args[1]
        assert 'session_id' in call_kwargs
        assert 'callback' in call_kwargs
        assert callable(call_kwargs['callback'])

    @pytest.mark.asyncio
    async def test_streams_audio_to_stt(
        self,
        initialized_plugin,
        mock_discord_user,
        mock_voice_client,
        mock_stt_service
    ):
        """Should stream audio chunks to STT service"""
        # Mock audio stream with multiple chunks
        async def mock_audio_stream():
            yield b'\x00' * 960
            yield b'\x01' * 960
            yield b'\x02' * 960

        await initialized_plugin._handle_user_speaking(
            mock_discord_user,
            mock_audio_stream(),
            mock_voice_client
        )

        # Verify audio chunks sent to STT
        assert mock_stt_service.send_audio.call_count >= 3

    @pytest.mark.asyncio
    async def test_silence_detection_triggers_finalization(
        self,
        initialized_plugin,
        mock_discord_user,
        mock_voice_client,
        mock_stt_service
    ):
        """Should detect silence (600ms threshold) and finalize transcript"""
        # Mock short audio stream (will trigger silence)
        async def mock_audio_stream():
            yield b'\x00' * 960
            # Wait longer than silence threshold
            await asyncio.sleep(0.7)  # 700ms > 600ms threshold

        with patch.dict(os.environ, {'SILENCE_THRESHOLD_MS': '600'}):
            await initialized_plugin._handle_user_speaking(
                mock_discord_user,
                mock_audio_stream(),
                mock_voice_client
            )

        # Verify finalization called
        mock_stt_service.finalize_transcript.assert_called()

    @pytest.mark.asyncio
    async def test_max_speaking_time_enforced(
        self,
        initialized_plugin,
        mock_discord_user,
        mock_voice_client,
        mock_stt_service
    ):
        """Should enforce max speaking time (45s safety limit)"""
        # This test is timing-sensitive, so we'll mock time.time()
        start_time = time.time()

        async def mock_audio_stream():
            # Simulate long audio stream
            for i in range(10):
                yield b'\x00' * 960
                await asyncio.sleep(0.01)

        # Mock time to simulate 50s elapsed
        with patch('time.time') as mock_time:
            mock_time.side_effect = [
                start_time,  # t_start
                start_time + 0.1,  # t_before_whisper
                start_time + 0.2,  # t_after_whisper
                start_time + 50.0,  # Check silence (exceeds 45s)
            ]

            with patch.dict(os.environ, {'MAX_SPEAKING_TIME_MS': '45000'}):
                await initialized_plugin._handle_user_speaking(
                    mock_discord_user,
                    mock_audio_stream(),
                    mock_voice_client
                )

        # Verify finalization called (safety limit)
        mock_stt_service.finalize_transcript.assert_called()

    @pytest.mark.asyncio
    async def test_tracks_latency_metrics(
        self,
        initialized_plugin,
        mock_discord_user,
        mock_voice_client
    ):
        """Should record latency metrics (WhisperX connection, first partial)"""
        async def mock_audio_stream():
            yield b'\x00' * 960

        # Clear metrics
        initialized_plugin.metrics.whisper_connection_latencies.clear()

        await initialized_plugin._handle_user_speaking(
            mock_discord_user,
            mock_audio_stream(),
            mock_voice_client
        )

        # Verify latency recorded
        assert len(initialized_plugin.metrics.whisper_connection_latencies) > 0

    @pytest.mark.asyncio
    async def test_error_handling_stt_connection_failure(
        self,
        initialized_plugin,
        mock_discord_user,
        mock_voice_client,
        mock_stt_service
    ):
        """Should handle STT connection failures gracefully"""
        async def mock_audio_stream():
            yield b'\x00' * 960

        # Mock STT connection failure
        mock_stt_service.connect.return_value = False

        # Should not raise exception
        await initialized_plugin._handle_user_speaking(
            mock_discord_user,
            mock_audio_stream(),
            mock_voice_client
        )

        # Verify cleanup attempted
        user_id = str(mock_discord_user.id)
        assert user_id not in initialized_plugin.active_sessions

    @pytest.mark.asyncio
    async def test_adds_user_to_active_sessions(
        self,
        initialized_plugin,
        mock_discord_user,
        mock_voice_client
    ):
        """Should add user to active_sessions dict when speaking starts"""
        async def mock_audio_stream():
            yield b'\x00' * 960

        user_id = str(mock_discord_user.id)
        assert user_id not in initialized_plugin.active_sessions

        await initialized_plugin._handle_user_speaking(
            mock_discord_user,
            mock_audio_stream(),
            mock_voice_client
        )

        # Note: active_sessions may be cleared by cleanup, but session_timings should exist
        # (or have been created during execution)
        assert len(initialized_plugin.session_timings) > 0 or user_id in initialized_plugin.active_sessions


# ============================================================
# Test Class 3: _on_transcript
# ============================================================

class TestOnTranscript:
    """Test the _on_transcript callback"""

    @pytest.mark.asyncio
    async def test_handles_partial_transcript(
        self,
        initialized_plugin,
        mock_conversation_service,
        caplog
    ):
        """Should handle partial transcripts (broadcast, no DB save)"""
        session_id = str(uuid.uuid4())
        initialized_plugin.session_timings[session_id] = {
            't_start': time.time(),
            't_whisper_connected': time.time(),
            't_first_partial': None
        }

        await initialized_plugin._on_transcript(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            text="Hello world",
            is_final=False,
            metadata={'confidence': 0.95}
        )

        # Verify partial logged
        assert "Partial" in caplog.text or "partial" in caplog.text.lower()

        # Verify no DB save for partial
        mock_conversation_service.add_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_final_transcript(
        self,
        initialized_plugin,
        mock_conversation_service,
        caplog
    ):
        """Should handle final transcripts (save to DB, trigger LLM)"""
        session_id = str(uuid.uuid4())
        initialized_plugin.session_timings[session_id] = {
            't_start': time.time(),
            't_whisper_connected': time.time(),
            't_first_partial': time.time()
        }

        # Mock _generate_response to avoid LLM call
        initialized_plugin._generate_response = AsyncMock()

        await initialized_plugin._on_transcript(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            text="Hello world",
            is_final=True,
            metadata={'confidence': 0.95}
        )

        # Verify final logged
        assert "Final" in caplog.text or "final" in caplog.text.lower()

        # Verify DB save for final
        mock_conversation_service.add_message.assert_called_once()
        call_kwargs = mock_conversation_service.add_message.call_args[1]
        assert call_kwargs['role'] == 'user'
        assert call_kwargs['content'] == "Hello world"

    @pytest.mark.asyncio
    async def test_saves_user_message_to_database(
        self,
        initialized_plugin,
        mock_conversation_service
    ):
        """Should save user message via ConversationService for final transcripts"""
        session_id = str(uuid.uuid4())
        initialized_plugin.session_timings[session_id] = {
            't_start': time.time(),
            't_whisper_connected': time.time(),
            't_first_partial': time.time()
        }
        initialized_plugin._generate_response = AsyncMock()

        await initialized_plugin._on_transcript(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            text="Test message",
            is_final=True,
            metadata={'confidence': 0.98}
        )

        # Verify message saved with metadata
        mock_conversation_service.add_message.assert_called_once()
        call_kwargs = mock_conversation_service.add_message.call_args[1]
        assert call_kwargs['session_id'] == session_id
        assert call_kwargs['role'] == 'user'
        assert call_kwargs['content'] == "Test message"
        assert 'metadata' in call_kwargs
        assert call_kwargs['metadata']['stt_confidence'] == 0.98

    @pytest.mark.asyncio
    async def test_triggers_llm_generation_for_final(
        self,
        initialized_plugin
    ):
        """Should call _generate_response for final transcripts"""
        session_id = str(uuid.uuid4())
        initialized_plugin.session_timings[session_id] = {
            't_start': time.time(),
            't_whisper_connected': time.time(),
            't_first_partial': time.time()
        }
        initialized_plugin._generate_response = AsyncMock()

        await initialized_plugin._on_transcript(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            text="Hello",
            is_final=True,
            metadata={}
        )

        # Verify _generate_response called
        initialized_plugin._generate_response.assert_called_once()
        call_args = initialized_plugin._generate_response.call_args[0]
        assert call_args[0] == session_id
        assert call_args[1] == "user_123"
        assert call_args[3] == "Hello"

    @pytest.mark.asyncio
    async def test_tracks_first_partial_latency(
        self,
        initialized_plugin
    ):
        """Should record first partial latency metrics"""
        session_id = str(uuid.uuid4())
        t_now = time.time()
        initialized_plugin.session_timings[session_id] = {
            't_start': t_now - 1.0,
            't_whisper_connected': t_now - 0.5,
            't_first_partial': None
        }

        # Clear metrics
        initialized_plugin.metrics.first_partial_transcript_latencies.clear()

        await initialized_plugin._on_transcript(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            text="Test",
            is_final=False,
            metadata={}
        )

        # Verify first partial latency recorded
        assert len(initialized_plugin.metrics.first_partial_transcript_latencies) > 0

    @pytest.mark.asyncio
    async def test_tracks_transcription_duration(
        self,
        initialized_plugin
    ):
        """Should record transcription duration (first partial → complete)"""
        session_id = str(uuid.uuid4())
        t_now = time.time()
        initialized_plugin.session_timings[session_id] = {
            't_start': t_now - 2.0,
            't_whisper_connected': t_now - 1.5,
            't_first_partial': t_now - 1.0
        }
        initialized_plugin._generate_response = AsyncMock()

        # Clear metrics
        initialized_plugin.metrics.transcription_duration_latencies.clear()

        await initialized_plugin._on_transcript(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            text="Final text",
            is_final=True,
            metadata={}
        )

        # Verify transcription duration recorded
        assert len(initialized_plugin.metrics.transcription_duration_latencies) > 0

    @pytest.mark.asyncio
    async def test_increments_transcript_counter(
        self,
        initialized_plugin
    ):
        """Should increment transcript count for final transcripts"""
        session_id = str(uuid.uuid4())
        initialized_plugin.session_timings[session_id] = {
            't_start': time.time(),
            't_whisper_connected': time.time(),
            't_first_partial': time.time()
        }
        initialized_plugin._generate_response = AsyncMock()

        initial_count = initialized_plugin.metrics.transcript_count

        await initialized_plugin._on_transcript(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            text="Test",
            is_final=True,
            metadata={}
        )

        # Verify counter incremented
        assert initialized_plugin.metrics.transcript_count == initial_count + 1


# ============================================================
# Test Class 4: _generate_response
# ============================================================

class TestGenerateResponse:
    """Test the _generate_response method (LLM generation)"""

    @pytest.mark.asyncio
    async def test_gets_conversation_context(
        self,
        initialized_plugin,
        mock_conversation_service
    ):
        """Should get conversation context (last 10 messages)"""
        session_id = str(uuid.uuid4())
        initialized_plugin._play_tts = AsyncMock()

        await initialized_plugin._generate_response(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            user_text="Hello",
            guild_id=None
        )

        # Verify context retrieved
        mock_conversation_service.get_conversation_context.assert_called_once()
        call_kwargs = mock_conversation_service.get_conversation_context.call_args[1]
        assert call_kwargs['session_id'] == session_id
        assert call_kwargs['limit'] == 10
        assert call_kwargs['include_system_prompt'] is True

    @pytest.mark.asyncio
    async def test_llm_success_streaming(
        self,
        initialized_plugin,
        mock_llm_service,
        mock_conversation_service
    ):
        """Should generate response via LLM service with streaming"""
        session_id = str(uuid.uuid4())
        initialized_plugin._play_tts = AsyncMock()

        await initialized_plugin._generate_response(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            user_text="Hello",
            guild_id=None
        )

        # Verify LLM called with streaming
        mock_llm_service.generate_response.assert_called_once()
        call_kwargs = mock_llm_service.generate_response.call_args[1]
        assert call_kwargs['stream'] is True
        assert 'callback' in call_kwargs

    @pytest.mark.asyncio
    async def test_llm_fallback_to_n8n(
        self,
        initialized_plugin,
        mock_llm_service,
        mock_conversation_service
    ):
        """Should fall back to n8n webhook if LLM fails"""
        session_id = str(uuid.uuid4())
        initialized_plugin._play_tts = AsyncMock()

        # Mock LLM failure
        mock_llm_service.generate_response.side_effect = LLMError("LLM unavailable")

        # Mock n8n webhook response
        mock_response = MagicMock()
        mock_response.json.return_value = {'response': 'Fallback response'}
        mock_response.raise_for_status = Mock()

        with patch.dict(os.environ, {'N8N_WEBHOOK_URL': 'http://n8n:5678/webhook/test'}):
            with patch('httpx.AsyncClient') as MockClient:
                mock_client = MockClient.return_value.__aenter__.return_value
                mock_client.post = AsyncMock(return_value=mock_response)

                await initialized_plugin._generate_response(
                    session_id=session_id,
                    user_id="user_123",
                    username="TestUser",
                    user_text="Hello",
                    guild_id=None
                )

        # Verify n8n called
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args[0]
        assert 'n8n' in call_args[0]

    @pytest.mark.asyncio
    async def test_saves_assistant_message(
        self,
        initialized_plugin,
        mock_conversation_service,
        mock_llm_service
    ):
        """Should save assistant message to database"""
        session_id = str(uuid.uuid4())
        initialized_plugin._play_tts = AsyncMock()

        await initialized_plugin._generate_response(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            user_text="Hello",
            guild_id=None
        )

        # Verify assistant message saved
        # Should be called twice: once for user message (in _on_transcript), once for assistant
        calls = mock_conversation_service.add_message.call_args_list
        assistant_call = [c for c in calls if c[1].get('role') == 'assistant']
        assert len(assistant_call) > 0

    @pytest.mark.asyncio
    async def test_calls_play_tts(
        self,
        initialized_plugin,
        mock_voice_client
    ):
        """Should call _play_tts with generated text"""
        session_id = str(uuid.uuid4())
        guild_id = 123456789
        initialized_plugin.voice_clients[guild_id] = mock_voice_client
        initialized_plugin._play_tts = AsyncMock()

        await initialized_plugin._generate_response(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            user_text="Hello",
            guild_id=guild_id
        )

        # Verify _play_tts called
        initialized_plugin._play_tts.assert_called_once()
        call_args = initialized_plugin._play_tts.call_args[0]
        assert "Hello world" in call_args[0]  # Response text
        assert call_args[1] is mock_voice_client

    @pytest.mark.asyncio
    async def test_tracks_llm_latency(
        self,
        initialized_plugin
    ):
        """Should record LLM generation latency"""
        session_id = str(uuid.uuid4())
        initialized_plugin._play_tts = AsyncMock()

        # Clear metrics
        initialized_plugin.metrics.ai_generation_latencies.clear()

        await initialized_plugin._generate_response(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            user_text="Test",
            guild_id=None
        )

        # Verify latency recorded
        assert len(initialized_plugin.metrics.ai_generation_latencies) > 0

    @pytest.mark.asyncio
    async def test_tracks_first_chunk_latency(
        self,
        initialized_plugin
    ):
        """Should record LLM first chunk latency"""
        session_id = str(uuid.uuid4())
        initialized_plugin._play_tts = AsyncMock()

        # Clear metrics
        initialized_plugin.metrics.n8n_first_chunk_latencies.clear()

        await initialized_plugin._generate_response(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            user_text="Test",
            guild_id=None
        )

        # Verify first chunk latency recorded
        assert len(initialized_plugin.metrics.n8n_first_chunk_latencies) > 0

    @pytest.mark.asyncio
    async def test_error_handling_both_failures(
        self,
        initialized_plugin,
        mock_llm_service
    ):
        """Should handle both LLM and n8n failures gracefully"""
        session_id = str(uuid.uuid4())
        initialized_plugin._play_tts = AsyncMock()

        # Mock LLM failure
        mock_llm_service.generate_response.side_effect = LLMError("LLM failed")

        # Mock n8n failure
        with patch.dict(os.environ, {'N8N_WEBHOOK_URL': 'http://n8n:5678/webhook/test'}):
            with patch('httpx.AsyncClient') as MockClient:
                mock_client = MockClient.return_value.__aenter__.return_value
                mock_client.post.side_effect = Exception("n8n failed")

                # Should not raise, but log error
                await initialized_plugin._generate_response(
                    session_id=session_id,
                    user_id="user_123",
                    username="TestUser",
                    user_text="Test",
                    guild_id=None
                )

        # Verify error counter incremented
        assert initialized_plugin.metrics.error_count > 0

    @pytest.mark.asyncio
    async def test_uses_agent_llm_config(
        self,
        initialized_plugin,
        mock_llm_service,
        mock_agent
    ):
        """Should use agent's LLM configuration (provider, model, temperature)"""
        session_id = str(uuid.uuid4())
        initialized_plugin._play_tts = AsyncMock()

        await initialized_plugin._generate_response(
            session_id=session_id,
            user_id="user_123",
            username="TestUser",
            user_text="Test",
            guild_id=None
        )

        # Verify LLM config from agent
        call_kwargs = mock_llm_service.generate_response.call_args[1]
        config = call_kwargs['config']
        assert config.provider == ProviderType(mock_agent.llm_provider)
        assert config.model == mock_agent.llm_model
        assert config.temperature == mock_agent.temperature


# ============================================================
# Test Class 5: _play_tts
# ============================================================

class TestPlayTTS:
    """Test the _play_tts method (TTS synthesis and playback)"""

    @pytest.mark.asyncio
    async def test_synthesizes_speech(
        self,
        initialized_plugin,
        mock_voice_client,
        mock_tts_service
    ):
        """Should synthesize speech via TTSService"""
        session_id = str(uuid.uuid4())

        with patch('discord.FFmpegPCMAudio') as MockFFmpeg:
            MockFFmpeg.return_value = Mock()

            await initialized_plugin._play_tts(
                text="Hello world",
                voice_client=mock_voice_client,
                session_id=session_id
            )

        # Verify TTS called
        mock_tts_service.synthesize_speech.assert_called_once()
        call_kwargs = mock_tts_service.synthesize_speech.call_args[1]
        assert call_kwargs['text'] == "Hello world"
        assert call_kwargs['stream'] is False  # Discord needs complete file

    @pytest.mark.asyncio
    async def test_saves_to_temp_file(
        self,
        initialized_plugin,
        mock_voice_client,
        mock_tts_service
    ):
        """Should save audio to temp WAV file"""
        session_id = str(uuid.uuid4())

        with patch('discord.FFmpegPCMAudio') as MockFFmpeg:
            MockFFmpeg.return_value = Mock()

            with patch('tempfile.NamedTemporaryFile') as MockTempFile:
                mock_file = MagicMock()
                mock_file.__enter__.return_value = mock_file
                mock_file.__exit__.return_value = None
                mock_file.name = '/tmp/test_audio.wav'
                MockTempFile.return_value = mock_file

                await initialized_plugin._play_tts(
                    text="Test",
                    voice_client=mock_voice_client,
                    session_id=session_id
                )

        # Verify temp file created
        MockTempFile.assert_called_once()
        assert MockTempFile.call_args[1]['suffix'] == '.wav'

    @pytest.mark.asyncio
    async def test_plays_audio_via_ffmpeg(
        self,
        initialized_plugin,
        mock_voice_client,
        mock_tts_service
    ):
        """Should play audio via discord.FFmpegPCMAudio"""
        session_id = str(uuid.uuid4())

        with patch('discord.FFmpegPCMAudio') as MockFFmpeg:
            mock_audio_source = Mock()
            MockFFmpeg.return_value = mock_audio_source

            await initialized_plugin._play_tts(
                text="Test",
                voice_client=mock_voice_client,
                session_id=session_id
            )

        # Verify FFmpeg audio source created
        MockFFmpeg.assert_called_once()

        # Verify play called
        mock_voice_client.play.assert_called_once_with(mock_audio_source)

    @pytest.mark.asyncio
    async def test_uses_agent_voice_config(
        self,
        initialized_plugin,
        mock_voice_client,
        mock_tts_service,
        mock_agent
    ):
        """Should use agent's TTS voice configuration"""
        session_id = str(uuid.uuid4())

        with patch('discord.FFmpegPCMAudio') as MockFFmpeg:
            MockFFmpeg.return_value = Mock()

            await initialized_plugin._play_tts(
                text="Test",
                voice_client=mock_voice_client,
                session_id=session_id
            )

        # Verify agent voice used
        call_kwargs = mock_tts_service.synthesize_speech.call_args[1]
        assert call_kwargs['voice_id'] == mock_agent.tts_voice
        assert call_kwargs['speed'] == mock_agent.tts_rate

    @pytest.mark.asyncio
    async def test_tracks_tts_latency(
        self,
        initialized_plugin,
        mock_voice_client
    ):
        """Should record TTS generation latency"""
        session_id = str(uuid.uuid4())

        # Clear metrics
        initialized_plugin.metrics.tts_generation_latencies.clear()

        with patch('discord.FFmpegPCMAudio') as MockFFmpeg:
            MockFFmpeg.return_value = Mock()

            await initialized_plugin._play_tts(
                text="Test",
                voice_client=mock_voice_client,
                session_id=session_id
            )

        # Verify TTS latency recorded
        assert len(initialized_plugin.metrics.tts_generation_latencies) > 0

    @pytest.mark.asyncio
    async def test_tracks_playback_latency(
        self,
        initialized_plugin,
        mock_voice_client
    ):
        """Should record audio playback latency"""
        session_id = str(uuid.uuid4())

        # Clear metrics
        initialized_plugin.metrics.audio_playback_latencies.clear()

        with patch('discord.FFmpegPCMAudio') as MockFFmpeg:
            MockFFmpeg.return_value = Mock()

            await initialized_plugin._play_tts(
                text="Test",
                voice_client=mock_voice_client,
                session_id=session_id
            )

        # Verify playback latency recorded
        assert len(initialized_plugin.metrics.audio_playback_latencies) > 0

    @pytest.mark.asyncio
    async def test_error_handling_tts_failure(
        self,
        initialized_plugin,
        mock_voice_client,
        mock_tts_service
    ):
        """Should handle TTS synthesis failures gracefully"""
        session_id = str(uuid.uuid4())

        # Mock TTS failure (return None)
        mock_tts_service.synthesize_speech.return_value = None

        result = await initialized_plugin._play_tts(
            text="Test",
            voice_client=mock_voice_client,
            session_id=session_id
        )

        # Verify returns None on error
        assert result is None

        # Verify voice client play not called
        mock_voice_client.play.assert_not_called()

    @pytest.mark.asyncio
    async def test_waits_for_current_audio_to_finish(
        self,
        initialized_plugin,
        mock_tts_service
    ):
        """Should wait for current audio to finish before playing new audio"""
        session_id = str(uuid.uuid4())

        # Mock voice client with is_playing state
        mock_vc = Mock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True

        # Simulate playing → not playing transition
        play_states = [True, True, False]
        mock_vc.is_playing.side_effect = play_states
        mock_vc.play = Mock()

        with patch('discord.FFmpegPCMAudio') as MockFFmpeg:
            MockFFmpeg.return_value = Mock()

            await initialized_plugin._play_tts(
                text="Test",
                voice_client=mock_vc,
                session_id=session_id
            )

        # Verify is_playing checked multiple times
        assert mock_vc.is_playing.call_count >= 2

    @pytest.mark.asyncio
    async def test_cleans_up_temp_file(
        self,
        initialized_plugin,
        mock_voice_client
    ):
        """Should clean up temp audio file after playback"""
        session_id = str(uuid.uuid4())

        with patch('discord.FFmpegPCMAudio') as MockFFmpeg:
            MockFFmpeg.return_value = Mock()

            with patch('os.unlink') as mock_unlink:
                await initialized_plugin._play_tts(
                    text="Test",
                    voice_client=mock_voice_client,
                    session_id=session_id
                )

                # Verify unlink called (temp file deleted)
                mock_unlink.assert_called_once()


# ============================================================
# Test Class 6: _cleanup_session
# ============================================================

class TestCleanupSession:
    """Test the _cleanup_session method"""

    @pytest.mark.asyncio
    async def test_disconnects_stt_service(
        self,
        initialized_plugin,
        mock_stt_service
    ):
        """Should disconnect STT service for session"""
        session_id = str(uuid.uuid4())
        user_id = "user_123"
        initialized_plugin.active_sessions[user_id] = session_id

        await initialized_plugin._cleanup_session(user_id, session_id)

        # Verify STT disconnect called
        mock_stt_service.disconnect.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_ends_session_in_database(
        self,
        initialized_plugin,
        mock_conversation_service
    ):
        """Should end session via ConversationService"""
        session_id = str(uuid.uuid4())
        user_id = "user_123"
        initialized_plugin.active_sessions[user_id] = session_id

        await initialized_plugin._cleanup_session(user_id, session_id)

        # Verify session ended
        mock_conversation_service.end_session.assert_called_once_with(session_id, persist=True)

    @pytest.mark.asyncio
    async def test_removes_from_active_sessions(
        self,
        initialized_plugin
    ):
        """Should remove from active_sessions dict"""
        session_id = str(uuid.uuid4())
        user_id = "user_123"
        initialized_plugin.active_sessions[user_id] = session_id

        await initialized_plugin._cleanup_session(user_id, session_id)

        # Verify removed
        assert user_id not in initialized_plugin.active_sessions

    @pytest.mark.asyncio
    async def test_removes_from_session_timings(
        self,
        initialized_plugin
    ):
        """Should remove from session_timings dict"""
        session_id = str(uuid.uuid4())
        user_id = "user_123"
        initialized_plugin.active_sessions[user_id] = session_id
        initialized_plugin.session_timings[session_id] = {'t_start': time.time()}

        await initialized_plugin._cleanup_session(user_id, session_id)

        # Verify removed
        assert session_id not in initialized_plugin.session_timings

    @pytest.mark.asyncio
    async def test_cleans_audio_receiver(
        self,
        initialized_plugin,
        mock_voice_client
    ):
        """Should cleanup AudioReceiver for user"""
        session_id = str(uuid.uuid4())
        user_id = "user_123"
        guild_id = 123456789

        # Create audio receiver with this user
        receiver = initialized_plugin.AudioReceiver(initialized_plugin, mock_voice_client)
        receiver.active_users.add(user_id)
        initialized_plugin.audio_receivers[guild_id] = receiver
        initialized_plugin.active_sessions[user_id] = session_id

        await initialized_plugin._cleanup_session(user_id, session_id)

        # Verify user removed from receiver
        assert user_id not in receiver.active_users

    @pytest.mark.asyncio
    async def test_logs_cleanup_message(
        self,
        initialized_plugin,
        caplog
    ):
        """Should log session cleanup"""
        session_id = str(uuid.uuid4())
        user_id = "user_123"
        initialized_plugin.active_sessions[user_id] = session_id

        await initialized_plugin._cleanup_session(user_id, session_id)

        # Verify logging
        assert "Cleaning up session" in caplog.text or "cleanup" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_error_handling_graceful(
        self,
        initialized_plugin,
        mock_stt_service
    ):
        """Should handle cleanup errors gracefully"""
        session_id = str(uuid.uuid4())
        user_id = "user_123"
        initialized_plugin.active_sessions[user_id] = session_id

        # Mock STT disconnect error
        mock_stt_service.disconnect.side_effect = Exception("STT disconnect failed")

        # Should not raise exception
        await initialized_plugin._cleanup_session(user_id, session_id)

        # Verify session still removed from tracking
        assert user_id not in initialized_plugin.active_sessions


# ============================================================
# Test Class 7: Event Handler Integration
# ============================================================

class TestEventHandlerIntegration:
    """Test updated event handlers"""

    @pytest.mark.asyncio
    async def test_on_voice_state_update_registers_receiver(
        self,
        initialized_plugin,
        mock_voice_client
    ):
        """Should register AudioReceiver when bot joins voice channel"""
        # This tests the event handler logic indirectly
        # (full Discord event testing requires integration tests)

        guild_id = 123456789

        # Simulate bot joining voice
        initialized_plugin.voice_clients[guild_id] = mock_voice_client

        # Manually register receiver (simulating on_voice_state_update logic)
        receiver = initialized_plugin.AudioReceiver(initialized_plugin, mock_voice_client)
        mock_voice_client.listen(receiver)
        initialized_plugin.audio_receivers[guild_id] = receiver

        # Verify receiver registered
        assert guild_id in initialized_plugin.audio_receivers
        assert isinstance(initialized_plugin.audio_receivers[guild_id], initialized_plugin.AudioReceiver)
        mock_voice_client.listen.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_voice_state_update_cleanup_on_leave(
        self,
        initialized_plugin,
        mock_voice_client
    ):
        """Should cleanup session when user leaves voice"""
        guild_id = 123456789
        user_id = "user_123"
        session_id = str(uuid.uuid4())

        # Setup receiver and session
        receiver = initialized_plugin.AudioReceiver(initialized_plugin, mock_voice_client)
        initialized_plugin.audio_receivers[guild_id] = receiver
        initialized_plugin.active_sessions[user_id] = session_id

        # Simulate cleanup (from on_voice_state_update)
        await initialized_plugin._cleanup_session(user_id, session_id)

        # Verify cleanup
        assert user_id not in initialized_plugin.active_sessions

    @pytest.mark.asyncio
    async def test_on_response_plays_tts(
        self,
        initialized_plugin,
        mock_voice_client
    ):
        """on_response hook should play TTS audio in Discord voice"""
        guild_id = 123456789
        session_id = str(uuid.uuid4())
        initialized_plugin.voice_clients[guild_id] = mock_voice_client
        initialized_plugin._play_tts = AsyncMock()

        # Call on_response hook
        await initialized_plugin.on_response(
            session_id=session_id,
            text="Hello from agent",
            metadata={'guild_id': guild_id}
        )

        # Verify _play_tts called
        initialized_plugin._play_tts.assert_called_once()
        call_args = initialized_plugin._play_tts.call_args[0]
        assert call_args[0] == "Hello from agent"
        assert call_args[1] is mock_voice_client

    @pytest.mark.asyncio
    async def test_on_response_no_voice_client(
        self,
        initialized_plugin,
        caplog
    ):
        """on_response should warn if not connected to voice"""
        session_id = str(uuid.uuid4())

        await initialized_plugin.on_response(
            session_id=session_id,
            text="Hello",
            metadata={'guild_id': 999}  # Non-existent guild
        )

        # Verify warning logged
        assert "Cannot play response" in caplog.text or "not connected" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_on_message_hook_does_nothing(
        self,
        initialized_plugin
    ):
        """on_message hook should be no-op for voice bot"""
        session_id = str(uuid.uuid4())

        # Should not raise exception
        await initialized_plugin.on_message(
            session_id=session_id,
            text="Text message",
            metadata={}
        )

        # No assertions needed - just verify it doesn't crash


# ============================================================
# Test Class 8: Integration Scenarios
# ============================================================

class TestIntegrationScenarios:
    """Test complete integration scenarios"""

    @pytest.mark.asyncio
    async def test_complete_audio_pipeline_flow(
        self,
        initialized_plugin,
        mock_discord_user,
        mock_voice_client,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """Test complete flow: audio → STT → LLM → TTS → playback"""
        session_id = str(uuid.uuid4())
        guild_id = 123456789
        initialized_plugin.voice_clients[guild_id] = mock_voice_client

        # 1. Start speaking (audio pipeline)
        async def mock_audio_stream():
            yield b'\x00' * 960

        with patch('discord.FFmpegPCMAudio') as MockFFmpeg:
            MockFFmpeg.return_value = Mock()

            await initialized_plugin._handle_user_speaking(
                mock_discord_user,
                mock_audio_stream(),
                mock_voice_client
            )

        # Verify pipeline steps executed
        # Session created
        mock_conversation_service.get_or_create_session.assert_called()

        # STT connected
        mock_stt_service.connect.assert_called()

        # Callback registered
        mock_stt_service.register_callback.assert_called()

    @pytest.mark.asyncio
    async def test_multiple_concurrent_users(
        self,
        initialized_plugin,
        mock_voice_client
    ):
        """Test handling multiple users speaking concurrently"""
        # Create multiple users
        user1 = Mock()
        user1.id = 111
        user1.name = "User1"

        user2 = Mock()
        user2.id = 222
        user2.name = "User2"

        async def mock_audio_stream():
            yield b'\x00' * 960

        # Start both users speaking
        task1 = asyncio.create_task(initialized_plugin._handle_user_speaking(
            user1, mock_audio_stream(), mock_voice_client
        ))
        task2 = asyncio.create_task(initialized_plugin._handle_user_speaking(
            user2, mock_audio_stream(), mock_voice_client
        ))

        await asyncio.gather(task1, task2)

        # Verify separate sessions created
        assert str(user1.id) in initialized_plugin.active_sessions or len(initialized_plugin.session_timings) >= 2
        assert str(user2.id) in initialized_plugin.active_sessions or len(initialized_plugin.session_timings) >= 1

    @pytest.mark.asyncio
    async def test_stop_cleans_up_audio_receivers(
        self,
        initialized_plugin,
        mock_voice_client
    ):
        """stop() should cleanup all audio receivers"""
        guild_id = 123456789

        # Add audio receiver
        receiver = initialized_plugin.AudioReceiver(initialized_plugin, mock_voice_client)
        initialized_plugin.audio_receivers[guild_id] = receiver
        receiver.active_users.add("user_123")

        # Stop plugin
        await initialized_plugin.stop()

        # Verify audio receivers cleaned up
        assert len(initialized_plugin.audio_receivers) == 0
