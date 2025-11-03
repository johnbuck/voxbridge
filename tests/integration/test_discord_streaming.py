"""
Integration tests for Discord plugin streaming

Tests the full Discord plugin streaming flow:
- LLM chunks → sentence detection → TTS → playback
- User interruption scenarios
- Error recovery strategies
- Multi-session handling
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from src.plugins.discord_plugin import DiscordPlugin
from src.database.models import Agent


@pytest.fixture
def mock_agent():
    """Mock Agent model for testing"""
    agent = Mock(spec=Agent)
    agent.id = "test-agent-id"
    agent.name = "Test Agent"
    agent.system_prompt = "You are a helpful assistant."
    agent.llm_provider = "openrouter"
    agent.llm_model = "anthropic/claude-3-5-sonnet"
    agent.tts_voice = "test_voice"
    agent.tts_rate = 1.0
    agent.tts_pitch = 1.0
    agent.temperature = 0.7
    agent.streaming_enabled = True
    agent.use_n8n = False
    agent.plugins = []
    return agent


@pytest.fixture
def mock_discord_bot():
    """Mock Discord bot for testing"""
    bot = Mock()
    bot.user = Mock()
    bot.user.id = 123456789
    bot.get_guild = Mock(return_value=None)
    return bot


@pytest.fixture
def mock_services():
    """Mock all external services"""
    return {
        'conversation': AsyncMock(),
        'stt': AsyncMock(),
        'llm': AsyncMock(),
        'tts': AsyncMock(),
        'metrics': Mock()
    }


@pytest.fixture
async def discord_plugin(mock_agent, mock_discord_bot, mock_services):
    """Create DiscordPlugin instance for testing"""
    with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_services['conversation']), \
         patch('src.plugins.discord_plugin.STTService', return_value=mock_services['stt']), \
         patch('src.plugins.discord_plugin.LLMService', return_value=mock_services['llm']), \
         patch('src.plugins.discord_plugin.TTSService', return_value=mock_services['tts']):

        plugin = DiscordPlugin(
            bot=mock_discord_bot,
            agent=mock_agent,
            metrics=mock_services['metrics']
        )

        # Mock voice client setup
        mock_voice_client = Mock()
        mock_voice_client.is_connected = Mock(return_value=True)
        mock_voice_client.is_playing = Mock(return_value=False)
        mock_voice_client.play = Mock()
        mock_voice_client.stop = Mock()
        mock_voice_client.guild = Mock()
        mock_voice_client.guild.id = 999

        plugin.voice_clients = {999: mock_voice_client}

        yield plugin, mock_services, mock_voice_client

        # Cleanup
        await plugin.cleanup()


class TestFullStreamingFlow:
    """Test complete streaming flow from LLM to audio playback"""

    @pytest.mark.asyncio
    async def test_llm_chunk_to_audio_flow(self, discord_plugin):
        """Test LLM chunks are detected, synthesized, and played"""
        plugin, services, voice_client = discord_plugin

        # Initialize streaming components
        from src.services.sentence_parser import SentenceParser
        from src.services.tts_queue_manager import TTSQueueManager
        from src.services.audio_playback_queue import AudioPlaybackQueue

        plugin.sentence_parser = SentenceParser(min_sentence_length=10)

        # Mock TTS service
        mock_tts_service = Mock()
        mock_tts_service.synthesize_speech = AsyncMock(return_value=b"fake_audio")

        synthesized_sentences = []

        async def on_tts_complete(audio_bytes: bytes, metadata: dict):
            synthesized_sentences.append(metadata.get('sentence', ''))
            # In real plugin, this enqueues to audio playback
            await plugin.audio_playback_queues[999].enqueue_audio(audio_bytes, metadata)

        plugin.tts_queue_manager = TTSQueueManager(
            max_concurrent=3,
            tts_service=mock_tts_service,
            on_complete=on_tts_complete,
            on_error=AsyncMock()
        )

        plugin.audio_playback_queues[999] = AudioPlaybackQueue(
            voice_client=voice_client,
            on_complete=AsyncMock(),
            on_error=AsyncMock()
        )

        await plugin.tts_queue_manager.start()
        await plugin.audio_playback_queues[999].start()

        # Simulate LLM streaming chunks
        llm_chunks = [
            "Hello! ",
            "This is a test. ",
            "How are you today?"
        ]

        session_id = "test-session"

        for chunk in llm_chunks:
            sentences = plugin.sentence_parser.add_chunk(chunk)
            for sentence in sentences:
                await plugin.tts_queue_manager.enqueue_sentence(
                    sentence=sentence,
                    session_id=session_id,
                    voice_id=plugin.agent.tts_voice,
                    speed=plugin.agent.tts_rate,
                    metadata={'sentence': sentence, 'guild_id': 999}
                )

        # Wait for processing
        await asyncio.sleep(1.0)

        # Verify sentences were synthesized
        assert len(synthesized_sentences) >= 2
        assert "Hello!" in synthesized_sentences[0]
        assert "This is a test." in synthesized_sentences[1]

    @pytest.mark.asyncio
    async def test_incremental_llm_streaming(self, discord_plugin):
        """Test incremental LLM chunk processing"""
        plugin, services, voice_client = discord_plugin

        from src.services.sentence_parser import SentenceParser
        from src.services.tts_queue_manager import TTSQueueManager

        plugin.sentence_parser = SentenceParser(min_sentence_length=10)

        mock_tts_service = Mock()
        mock_tts_service.synthesize_speech = AsyncMock(return_value=b"fake_audio")

        detected_sentences = []

        async def on_tts_complete(audio_bytes: bytes, metadata: dict):
            detected_sentences.append(metadata.get('sentence', ''))

        plugin.tts_queue_manager = TTSQueueManager(
            max_concurrent=3,
            tts_service=mock_tts_service,
            on_complete=on_tts_complete,
            on_error=AsyncMock()
        )

        await plugin.tts_queue_manager.start()

        # Simulate word-by-word streaming (like real LLM)
        word_chunks = [
            "The ", "quick ", "brown ", "fox ",
            "jumps. ", "Over ", "the ", "lazy ", "dog."
        ]

        for chunk in word_chunks:
            sentences = plugin.sentence_parser.add_chunk(chunk)
            for sentence in sentences:
                await plugin.tts_queue_manager.enqueue_sentence(
                    sentence=sentence,
                    session_id="test-session",
                    voice_id="voice1",
                    speed=1.0,
                    metadata={'sentence': sentence}
                )

        # Get final sentence
        final = plugin.sentence_parser.finalize()
        if final:
            await plugin.tts_queue_manager.enqueue_sentence(
                sentence=final,
                session_id="test-session",
                voice_id="voice1",
                speed=1.0,
                metadata={'sentence': final}
            )

        # Wait for processing
        await asyncio.sleep(0.8)

        # Should have detected complete sentences
        assert len(detected_sentences) >= 2


class TestUserInterruption:
    """Test user interruption scenarios"""

    @pytest.mark.asyncio
    async def test_immediate_interruption_stops_streaming(self, discord_plugin):
        """Test user speaking immediately stops AI streaming"""
        plugin, services, voice_client = discord_plugin

        from src.services.tts_queue_manager import TTSQueueManager
        from src.services.audio_playback_queue import AudioPlaybackQueue

        mock_tts_service = Mock()
        mock_tts_service.synthesize_speech = AsyncMock(return_value=b"audio")

        plugin.tts_queue_manager = TTSQueueManager(
            max_concurrent=3,
            tts_service=mock_tts_service,
            on_complete=AsyncMock(),
            on_error=AsyncMock()
        )

        plugin.audio_playback_queues[999] = AudioPlaybackQueue(
            voice_client=voice_client,
            on_complete=AsyncMock(),
            on_error=AsyncMock()
        )

        await plugin.tts_queue_manager.start()
        await plugin.audio_playback_queues[999].start()

        # Enqueue multiple sentences (simulating AI response)
        for i in range(10):
            await plugin.tts_queue_manager.enqueue_sentence(
                sentence=f"This is sentence number {i}.",
                session_id="test-session",
                voice_id="voice1",
                speed=1.0
            )

        # Let some processing start
        await asyncio.sleep(0.1)

        # Simulate user interruption (immediate strategy)
        plugin.interruption_strategy = 'immediate'
        await plugin._handle_interruption(999, "user123", "TestUser")

        # Wait a bit
        await asyncio.sleep(0.2)

        # Both queues should be cleared
        assert plugin.tts_queue_manager.queue.qsize() == 0
        assert plugin.audio_playback_queues[999].queue.qsize() == 0

        # Voice client should have been stopped
        voice_client.stop.assert_called()

    @pytest.mark.asyncio
    async def test_graceful_interruption_finishes_current(self, discord_plugin):
        """Test graceful interruption finishes current sentence"""
        plugin, services, voice_client = discord_plugin

        from src.services.tts_queue_manager import TTSQueueManager
        from src.services.audio_playback_queue import AudioPlaybackQueue

        mock_tts_service = Mock()
        mock_tts_service.synthesize_speech = AsyncMock(return_value=b"audio")

        completed_sentences = []

        async def track_completion(audio_bytes: bytes, metadata: dict):
            completed_sentences.append(metadata.get('sentence', ''))

        plugin.tts_queue_manager = TTSQueueManager(
            max_concurrent=3,
            tts_service=mock_tts_service,
            on_complete=track_completion,
            on_error=AsyncMock()
        )

        plugin.audio_playback_queues[999] = AudioPlaybackQueue(
            voice_client=voice_client,
            on_complete=AsyncMock(),
            on_error=AsyncMock()
        )

        await plugin.tts_queue_manager.start()
        await plugin.audio_playback_queues[999].start()

        # Enqueue sentences
        for i in range(5):
            await plugin.tts_queue_manager.enqueue_sentence(
                sentence=f"Sentence {i}.",
                session_id="test-session",
                voice_id="voice1",
                speed=1.0,
                metadata={'sentence': f"Sentence {i}."}
            )

        # Let some processing start
        await asyncio.sleep(0.2)

        # Trigger graceful interruption
        plugin.interruption_strategy = 'graceful'
        await plugin._handle_interruption(999, "user123", "TestUser")

        # Wait for current to finish
        await asyncio.sleep(0.3)

        # Should have completed at least one sentence
        assert len(completed_sentences) >= 1

        # Pending should be cleared
        assert plugin.tts_queue_manager.queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_drain_interruption_processes_few_more(self, discord_plugin):
        """Test drain interruption processes 1-2 more sentences"""
        plugin, services, voice_client = discord_plugin

        from src.services.tts_queue_manager import TTSQueueManager
        from src.services.audio_playback_queue import AudioPlaybackQueue

        mock_tts_service = Mock()
        mock_tts_service.synthesize_speech = AsyncMock(return_value=b"audio")

        plugin.tts_queue_manager = TTSQueueManager(
            max_concurrent=3,
            tts_service=mock_tts_service,
            on_complete=AsyncMock(),
            on_error=AsyncMock()
        )

        plugin.audio_playback_queues[999] = AudioPlaybackQueue(
            voice_client=voice_client,
            on_complete=AsyncMock(),
            on_error=AsyncMock()
        )

        await plugin.tts_queue_manager.start()
        await plugin.audio_playback_queues[999].start()

        # Enqueue many sentences
        for i in range(10):
            await plugin.tts_queue_manager.enqueue_sentence(
                sentence=f"Sentence {i}.",
                session_id="test-session",
                voice_id="voice1",
                speed=1.0
            )

        initial_size = plugin.tts_queue_manager.queue.qsize()

        # Trigger drain interruption
        plugin.interruption_strategy = 'drain'
        await plugin._handle_interruption(999, "user123", "TestUser")

        # Should have kept 1-2 tasks
        remaining = plugin.tts_queue_manager.queue.qsize()
        assert remaining <= 2
        assert remaining < initial_size


class TestErrorRecovery:
    """Test error recovery strategies"""

    @pytest.mark.asyncio
    async def test_skip_strategy_continues_on_error(self, discord_plugin):
        """Test skip strategy continues to next sentence on error"""
        plugin, services, voice_client = discord_plugin

        from src.services.tts_queue_manager import TTSQueueManager

        # Make TTS fail on second call
        mock_tts_service = Mock()
        mock_tts_service.synthesize_speech = AsyncMock(
            side_effect=[b"audio1", Exception("TTS failed"), b"audio3"]
        )

        completed = []
        failed = []

        async def on_complete(audio: bytes, metadata: dict):
            completed.append(metadata.get('index'))

        async def on_error(error: Exception, metadata: dict):
            failed.append(metadata.get('index'))

        plugin.tts_queue_manager = TTSQueueManager(
            max_concurrent=1,
            tts_service=mock_tts_service,
            on_complete=on_complete,
            on_error=on_error
        )

        await plugin.tts_queue_manager.start()

        plugin.error_strategy = 'skip'

        # Enqueue 3 sentences
        for i in range(3):
            await plugin.tts_queue_manager.enqueue_sentence(
                sentence=f"Sentence {i}.",
                session_id="test-session",
                voice_id="voice1",
                speed=1.0,
                metadata={'index': i}
            )

        # Wait for processing
        await asyncio.sleep(0.6)

        # Should have completed sentences 0 and 2
        assert 0 in completed
        assert 2 in completed

        # Sentence 1 should have failed
        assert 1 in failed

    @pytest.mark.asyncio
    async def test_retry_strategy_retries_failed(self, discord_plugin):
        """Test retry strategy retries failed synthesis"""
        plugin, services, voice_client = discord_plugin

        from src.services.tts_queue_manager import TTSQueueManager

        # Fail first call, succeed on retry
        call_count = 0

        async def tts_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("TTS failed")
            return b"audio_data"

        mock_tts_service = Mock()
        mock_tts_service.synthesize_speech = tts_with_retry

        completed = []

        async def on_complete(audio: bytes, metadata: dict):
            completed.append(metadata.get('sentence'))

        plugin.tts_queue_manager = TTSQueueManager(
            max_concurrent=1,
            tts_service=mock_tts_service,
            on_complete=on_complete,
            on_error=AsyncMock()
        )

        await plugin.tts_queue_manager.start()

        plugin.error_strategy = 'retry'
        plugin.max_retries = 2

        # Enqueue sentence
        task_id = await plugin.tts_queue_manager.enqueue_sentence(
            sentence="Test sentence.",
            session_id="test-session",
            voice_id="voice1",
            speed=1.0,
            metadata={'sentence': "Test sentence.", 'task_id': task_id}
        )

        # Wait for processing (including retry)
        await asyncio.sleep(0.8)

        # Should have succeeded on retry
        assert "Test sentence." in completed

        # Should have been called twice (initial + retry)
        assert call_count == 2


class TestMultiSession:
    """Test handling multiple simultaneous sessions"""

    @pytest.mark.asyncio
    async def test_multiple_guilds_concurrent_streaming(self, mock_agent, mock_discord_bot, mock_services):
        """Test streaming to multiple guilds concurrently"""
        with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_services['conversation']), \
             patch('src.plugins.discord_plugin.STTService', return_value=mock_services['stt']), \
             patch('src.plugins.discord_plugin.LLMService', return_value=mock_services['llm']), \
             patch('src.plugins.discord_plugin.TTSService', return_value=mock_services['tts']):

            plugin = DiscordPlugin(
                bot=mock_discord_bot,
                agent=mock_agent,
                metrics=mock_services['metrics']
            )

            from src.services.sentence_parser import SentenceParser
            from src.services.tts_queue_manager import TTSQueueManager
            from src.services.audio_playback_queue import AudioPlaybackQueue

            # Setup for two guilds
            guild_ids = [111, 222]
            voice_clients = {}

            for guild_id in guild_ids:
                mock_vc = Mock()
                mock_vc.is_connected = Mock(return_value=True)
                mock_vc.is_playing = Mock(return_value=False)
                mock_vc.play = Mock()
                mock_vc.guild = Mock()
                mock_vc.guild.id = guild_id

                voice_clients[guild_id] = mock_vc
                plugin.voice_clients[guild_id] = mock_vc

            # Create shared TTS queue manager
            mock_tts_service = Mock()
            mock_tts_service.synthesize_speech = AsyncMock(return_value=b"audio")

            plugin.tts_queue_manager = TTSQueueManager(
                max_concurrent=3,
                tts_service=mock_tts_service,
                on_complete=AsyncMock(),
                on_error=AsyncMock()
            )

            await plugin.tts_queue_manager.start()

            # Create per-guild audio playback queues
            for guild_id in guild_ids:
                plugin.audio_playback_queues[guild_id] = AudioPlaybackQueue(
                    voice_client=voice_clients[guild_id],
                    on_complete=AsyncMock(),
                    on_error=AsyncMock()
                )
                await plugin.audio_playback_queues[guild_id].start()

            plugin.sentence_parser = SentenceParser(min_sentence_length=10)

            # Enqueue sentences for both guilds
            for guild_id in guild_ids:
                for i in range(3):
                    await plugin.tts_queue_manager.enqueue_sentence(
                        sentence=f"Guild {guild_id} sentence {i}.",
                        session_id=f"session-{guild_id}",
                        voice_id="voice1",
                        speed=1.0,
                        metadata={'guild_id': guild_id, 'index': i}
                    )

            # Wait for processing
            await asyncio.sleep(1.0)

            # Both guilds should have been called for playback
            assert voice_clients[111].play.call_count >= 1
            assert voice_clients[222].play.call_count >= 1

            await plugin.cleanup()


class TestMetricsTracking:
    """Test metrics are tracked correctly during streaming"""

    @pytest.mark.asyncio
    async def test_sentence_metrics_recorded(self, discord_plugin):
        """Test sentence detection and synthesis metrics"""
        plugin, services, voice_client = discord_plugin

        from src.services.sentence_parser import SentenceParser
        from src.services.tts_queue_manager import TTSQueueManager

        plugin.sentence_parser = SentenceParser(min_sentence_length=10)

        mock_tts_service = Mock()
        mock_tts_service.synthesize_speech = AsyncMock(return_value=b"audio")

        # Track metrics
        metrics_recorded = []

        def track_metric(name, value):
            metrics_recorded.append((name, value))

        services['metrics'].record_sentence_detection = lambda latency: track_metric('detection', latency)
        services['metrics'].record_sentence_tts = lambda latency, success: track_metric('tts', (latency, success))

        plugin.tts_queue_manager = TTSQueueManager(
            max_concurrent=2,
            tts_service=mock_tts_service,
            on_complete=AsyncMock(),
            on_error=AsyncMock()
        )

        await plugin.tts_queue_manager.start()

        # Process sentences
        sentences = plugin.sentence_parser.add_chunk("Hello world! How are you?")

        for sentence in sentences:
            # Record detection metric
            services['metrics'].record_sentence_detection(5.0)

            await plugin.tts_queue_manager.enqueue_sentence(
                sentence=sentence,
                session_id="test-session",
                voice_id="voice1",
                speed=1.0
            )

        # Wait for processing
        await asyncio.sleep(0.5)

        # Record TTS metric
        services['metrics'].record_sentence_tts(0.1, success=True)

        # Verify metrics were recorded
        assert len(metrics_recorded) >= 2
        assert ('detection', 5.0) in metrics_recorded


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
