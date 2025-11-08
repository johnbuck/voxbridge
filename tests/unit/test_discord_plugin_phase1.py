"""
Unit tests for DiscordPlugin Phase 1: Service Layer Integration

Tests Phase 1 changes (2025-10-28):
- Service layer dependencies initialization
- Session tracking infrastructure
- MetricsTracker integration
- Enhanced cleanup in stop() method
- Stub methods for Phase 2 audio pipeline

Test Coverage:
- Service initialization and lifecycle
- Session tracking (active_sessions, session_timings)
- Metrics tracker functionality
- Plugin lifecycle (initialize, start, stop)
- Stub methods existence and structure
"""
from __future__ import annotations

import pytest
import asyncio
import time
import logging
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock, call
from uuid import uuid4, UUID
from typing import Dict, Any

# Import Discord plugin components
from src.plugins.discord_plugin import DiscordPlugin, MetricsTracker

# Configure logging for test visibility
logger = logging.getLogger(__name__)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def agent_id():
    """Generate a test agent UUID"""
    return uuid4()


@pytest.fixture
def mock_agent(agent_id):
    """Mock Agent model instance"""
    agent = MagicMock()
    agent.id = agent_id
    agent.name = "TestAgent"
    agent.system_prompt = "You are a helpful assistant"
    agent.temperature = 0.7
    agent.llm_provider = "openrouter"
    agent.llm_model = "anthropic/claude-3.5-sonnet"
    agent.tts_voice = "female_1"
    agent.tts_exaggeration = 1.0
    agent.tts_cfg_weight = 0.7
    agent.tts_temperature = 0.3
    agent.tts_language = "en"
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
    """Mock Discord Bot instance"""
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
    return bot


@pytest.fixture
def mock_conversation_service():
    """Mock ConversationService"""
    service = MagicMock()
    service.start = AsyncMock()
    service.stop = AsyncMock()
    return service


@pytest.fixture
def mock_stt_service():
    """Mock STTService singleton"""
    service = MagicMock()
    service.connect = AsyncMock()
    service.disconnect = AsyncMock()
    service.is_connected = AsyncMock(return_value=False)
    service.send_audio = AsyncMock()
    return service


@pytest.fixture
def mock_llm_service():
    """Mock LLMService singleton"""
    service = MagicMock()
    service.generate_response = AsyncMock(return_value="Test response")
    return service


@pytest.fixture
def mock_tts_service():
    """Mock TTSService singleton"""
    service = MagicMock()
    service.synthesize_speech = AsyncMock(return_value=b"fake_audio_data")
    return service


@pytest.fixture
def plugin():
    """Create DiscordPlugin instance without initialization"""
    return DiscordPlugin()


# ============================================================
# Test Class 1: Service Layer Integration
# ============================================================

class TestServiceLayerIntegration:
    """Test service initialization and lifecycle"""

    @pytest.mark.asyncio
    async def test_services_initialized_in_initialize_method(
        self,
        plugin,
        mock_agent,
        valid_config,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """Services should be initialized when plugin.initialize() is called"""
        with patch('src.plugins.discord_plugin.commands.Bot') as MockBot:
            MockBot.return_value = MagicMock()

            with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_conversation_service):
                with patch('src.plugins.discord_plugin.get_stt_service', return_value=mock_stt_service):
                    with patch('src.plugins.discord_plugin.get_llm_service', return_value=mock_llm_service):
                        with patch('src.plugins.discord_plugin.get_tts_service', return_value=mock_tts_service):
                            # Initialize plugin
                            await plugin.initialize(mock_agent, valid_config)

                            # Verify services are initialized
                            assert plugin.conversation_service is not None
                            assert plugin.stt_service is not None
                            assert plugin.llm_service is not None
                            assert plugin.tts_service is not None

                            # Verify ConversationService.start() was called
                            mock_conversation_service.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_services_are_singleton_references(
        self,
        plugin,
        mock_agent,
        valid_config,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """STT/LLM/TTS services should be singletons (shared across plugins)"""
        with patch('src.plugins.discord_plugin.commands.Bot') as MockBot:
            MockBot.return_value = MagicMock()

            with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_conversation_service):
                with patch('src.plugins.discord_plugin.get_stt_service', return_value=mock_stt_service) as mock_get_stt:
                    with patch('src.plugins.discord_plugin.get_llm_service', return_value=mock_llm_service) as mock_get_llm:
                        with patch('src.plugins.discord_plugin.get_tts_service', return_value=mock_tts_service) as mock_get_tts:
                            # Initialize plugin
                            await plugin.initialize(mock_agent, valid_config)

                            # Verify singleton getters were called
                            mock_get_stt.assert_called_once()
                            mock_get_llm.assert_called_once()
                            mock_get_tts.assert_called_once()

                            # Verify services are the same singleton instances
                            assert plugin.stt_service is mock_stt_service
                            assert plugin.llm_service is mock_llm_service
                            assert plugin.tts_service is mock_tts_service

    @pytest.mark.asyncio
    async def test_conversation_service_is_per_plugin(
        self,
        mock_agent,
        valid_config,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """Each plugin should have its own ConversationService instance"""
        plugin1 = DiscordPlugin()
        plugin2 = DiscordPlugin()

        with patch('src.plugins.discord_plugin.commands.Bot') as MockBot:
            MockBot.return_value = MagicMock()

            # Create separate ConversationService instances for each plugin
            mock_conv_service_1 = MagicMock()
            mock_conv_service_1.start = AsyncMock()
            mock_conv_service_1.stop = AsyncMock()

            mock_conv_service_2 = MagicMock()
            mock_conv_service_2.start = AsyncMock()
            mock_conv_service_2.stop = AsyncMock()

            with patch('src.plugins.discord_plugin.ConversationService', side_effect=[mock_conv_service_1, mock_conv_service_2]):
                with patch('src.plugins.discord_plugin.get_stt_service', return_value=mock_stt_service):
                    with patch('src.plugins.discord_plugin.get_llm_service', return_value=mock_llm_service):
                        with patch('src.plugins.discord_plugin.get_tts_service', return_value=mock_tts_service):
                            # Initialize both plugins
                            await plugin1.initialize(mock_agent, valid_config)
                            await plugin2.initialize(mock_agent, valid_config)

                            # Verify each plugin has its own ConversationService instance
                            assert plugin1.conversation_service is not plugin2.conversation_service
                            assert plugin1.conversation_service is mock_conv_service_1
                            assert plugin2.conversation_service is mock_conv_service_2

    @pytest.mark.asyncio
    async def test_service_initialization_logging(
        self,
        plugin,
        mock_agent,
        valid_config,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service,
        caplog
    ):
        """Should log service initialization with agent name"""
        with patch('src.plugins.discord_plugin.commands.Bot') as MockBot:
            MockBot.return_value = MagicMock()

            with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_conversation_service):
                with patch('src.plugins.discord_plugin.get_stt_service', return_value=mock_stt_service):
                    with patch('src.plugins.discord_plugin.get_llm_service', return_value=mock_llm_service):
                        with patch('src.plugins.discord_plugin.get_tts_service', return_value=mock_tts_service):
                            with caplog.at_level(logging.INFO):
                                await plugin.initialize(mock_agent, valid_config)

                            # Verify logging contains agent name and success message
                            assert "Initialized services" in caplog.text or "services for Discord plugin" in caplog.text
                            assert "TestAgent" in caplog.text

    @pytest.mark.asyncio
    async def test_service_initialization_error_handling(
        self,
        plugin,
        mock_agent,
        valid_config
    ):
        """Should raise exception if service initialization fails"""
        with patch('src.plugins.discord_plugin.commands.Bot') as MockBot:
            MockBot.return_value = MagicMock()

            # Mock ConversationService to raise error during start()
            failing_service = MagicMock()
            failing_service.start = AsyncMock(side_effect=Exception("Service startup failed"))

            with patch('src.plugins.discord_plugin.ConversationService', return_value=failing_service):
                with pytest.raises(Exception) as exc_info:
                    await plugin.initialize(mock_agent, valid_config)

                assert "Service startup failed" in str(exc_info.value)


# ============================================================
# Test Class 2: Session Tracking
# ============================================================

class TestSessionTracking:
    """Test session dictionaries and tracking"""

    def test_active_sessions_initialized(self, plugin):
        """active_sessions dict should be initialized in __init__"""
        assert hasattr(plugin, 'active_sessions')
        assert isinstance(plugin.active_sessions, dict)
        assert len(plugin.active_sessions) == 0

    def test_session_timings_initialized(self, plugin):
        """session_timings dict should be initialized in __init__"""
        assert hasattr(plugin, 'session_timings')
        assert isinstance(plugin.session_timings, dict)
        assert len(plugin.session_timings) == 0

    @pytest.mark.asyncio
    async def test_cleanup_session_stub(self, plugin):
        """_cleanup_session stub should exist and be callable"""
        # Verify method exists
        assert hasattr(plugin, '_cleanup_session')
        assert callable(plugin._cleanup_session)

        # Add test session
        user_id = "test_user_123"
        session_id = str(uuid4())
        plugin.active_sessions[user_id] = session_id
        plugin.session_timings[session_id] = {"start_time": time.time()}

        # Call stub (should not raise)
        await plugin._cleanup_session(user_id, session_id)

        # Verify session removed from tracking
        assert user_id not in plugin.active_sessions
        assert session_id not in plugin.session_timings

    @pytest.mark.asyncio
    async def test_multiple_sessions_tracked(self, plugin):
        """Plugin should track multiple concurrent user sessions"""
        # Simulate multiple users with active sessions
        sessions = {
            "user_1": str(uuid4()),
            "user_2": str(uuid4()),
            "user_3": str(uuid4()),
        }

        for user_id, session_id in sessions.items():
            plugin.active_sessions[user_id] = session_id
            plugin.session_timings[session_id] = {
                "start_time": time.time(),
                "last_activity": time.time()
            }

        # Verify all sessions tracked
        assert len(plugin.active_sessions) == 3
        assert len(plugin.session_timings) == 3

        for user_id, session_id in sessions.items():
            assert plugin.active_sessions[user_id] == session_id
            assert session_id in plugin.session_timings

    @pytest.mark.asyncio
    async def test_cleanup_session_removes_timing_data(self, plugin):
        """_cleanup_session should remove both session and timing data"""
        user_id = "test_user"
        session_id = str(uuid4())

        # Add session with timing data
        plugin.active_sessions[user_id] = session_id
        plugin.session_timings[session_id] = {
            "start_time": time.time(),
            "transcript_time": time.time(),
            "llm_start": time.time()
        }

        # Cleanup session
        await plugin._cleanup_session(user_id, session_id)

        # Verify both dictionaries cleaned up
        assert user_id not in plugin.active_sessions
        assert session_id not in plugin.session_timings


# ============================================================
# Test Class 3: MetricsTracker Integration
# ============================================================

class TestMetricsTrackerIntegration:
    """Test metrics tracking functionality"""

    def test_metrics_tracker_initialized(self, plugin):
        """MetricsTracker should be initialized in __init__"""
        assert hasattr(plugin, 'metrics')
        assert isinstance(plugin.metrics, MetricsTracker)

    def test_metrics_tracker_records_latency(self, plugin):
        """Should be able to record latency samples"""
        # Record some latencies
        plugin.metrics.record_latency(100.0)
        plugin.metrics.record_latency(150.0)
        plugin.metrics.record_latency(120.0)

        # Verify recorded
        assert len(plugin.metrics.latencies) == 3
        assert plugin.metrics.total_requests == 3

    def test_metrics_tracker_calculates_stats(self):
        """Should calculate mean/median/p95 correctly"""
        metrics = MetricsTracker(max_samples=100)

        # Record latencies: 50, 100, 150, 200, 250 ms
        for latency in [50.0, 100.0, 150.0, 200.0, 250.0]:
            metrics.record_latency(latency)

        stats = metrics.get_metrics()

        # Verify statistics
        assert stats['latency']['avg'] == 150  # Mean: (50+100+150+200+250)/5
        assert stats['latency']['p50'] == 150  # Median
        assert stats['latency']['p95'] == 250  # 95th percentile
        assert stats['latency']['p99'] == 250  # 99th percentile

    def test_metrics_exposed_in_get_bot_info(self, plugin):
        """get_bot_info() should include metrics statistics"""
        # Record some metrics
        plugin.metrics.record_latency(100.0)
        plugin.metrics.record_n8n_response_latency(2.5)

        # Get bot info
        bot_info = plugin.get_bot_info()

        # Verify metrics included
        assert 'metrics' in bot_info
        assert isinstance(bot_info['metrics'], dict)

        # Check metrics structure
        metrics = bot_info['metrics']
        assert 'latency' in metrics
        assert 'n8nResponseLatency' in metrics

    def test_metrics_tracker_phase1_methods_exist(self):
        """Verify Phase 1 latency tracking methods exist"""
        metrics = MetricsTracker()

        # Verify Phase 1 methods exist
        assert hasattr(metrics, 'record_whisper_connection_latency')
        assert hasattr(metrics, 'record_first_partial_transcript_latency')
        assert hasattr(metrics, 'record_transcription_duration')
        assert hasattr(metrics, 'record_silence_detection_latency')

        # Verify they're callable
        assert callable(metrics.record_whisper_connection_latency)
        assert callable(metrics.record_first_partial_transcript_latency)
        assert callable(metrics.record_transcription_duration)
        assert callable(metrics.record_silence_detection_latency)

    def test_metrics_tracker_deque_max_samples(self):
        """MetricsTracker should enforce max_samples limit"""
        metrics = MetricsTracker(max_samples=5)

        # Record 10 latencies (exceeds max_samples)
        for i in range(10):
            metrics.record_latency(float(i))

        # Verify only last 5 samples kept
        assert len(metrics.latencies) == 5
        assert list(metrics.latencies) == [5.0, 6.0, 7.0, 8.0, 9.0]


# ============================================================
# Test Class 4: Plugin Lifecycle
# ============================================================

class TestPluginLifecycle:
    """Test enhanced stop() method and lifecycle"""

    @pytest.mark.asyncio
    async def test_stop_cleans_up_sessions(
        self,
        plugin,
        mock_agent,
        valid_config,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service,
        mock_discord_bot
    ):
        """stop() should clean up all active sessions"""
        with patch('src.plugins.discord_plugin.commands.Bot', return_value=mock_discord_bot):
            with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_conversation_service):
                with patch('src.plugins.discord_plugin.get_stt_service', return_value=mock_stt_service):
                    with patch('src.plugins.discord_plugin.get_llm_service', return_value=mock_llm_service):
                        with patch('src.plugins.discord_plugin.get_tts_service', return_value=mock_tts_service):
                            # Initialize plugin
                            await plugin.initialize(mock_agent, valid_config)

                            # Add test sessions
                            plugin.active_sessions['user_1'] = str(uuid4())
                            plugin.active_sessions['user_2'] = str(uuid4())
                            plugin.session_timings[plugin.active_sessions['user_1']] = {"start": time.time()}
                            plugin.session_timings[plugin.active_sessions['user_2']] = {"start": time.time()}

                            # Stop plugin
                            await plugin.stop()

                            # Verify sessions cleaned up
                            assert len(plugin.active_sessions) == 0
                            assert len(plugin.session_timings) == 0

    @pytest.mark.asyncio
    async def test_stop_disconnects_voice_clients(
        self,
        plugin,
        mock_agent,
        valid_config,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service,
        mock_discord_bot
    ):
        """stop() should disconnect all voice clients (existing functionality)"""
        with patch('src.plugins.discord_plugin.commands.Bot', return_value=mock_discord_bot):
            with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_conversation_service):
                with patch('src.plugins.discord_plugin.get_stt_service', return_value=mock_stt_service):
                    with patch('src.plugins.discord_plugin.get_llm_service', return_value=mock_llm_service):
                        with patch('src.plugins.discord_plugin.get_tts_service', return_value=mock_tts_service):
                            # Initialize plugin
                            await plugin.initialize(mock_agent, valid_config)

                            # Add mock voice clients
                            mock_voice_1 = MagicMock()
                            mock_voice_1.disconnect = AsyncMock()
                            mock_voice_2 = MagicMock()
                            mock_voice_2.disconnect = AsyncMock()

                            plugin.voice_clients[123] = mock_voice_1
                            plugin.voice_clients[456] = mock_voice_2

                            # Stop plugin
                            await plugin.stop()

                            # Verify voice clients disconnected
                            mock_voice_1.disconnect.assert_called_once()
                            mock_voice_2.disconnect.assert_called_once()
                            assert len(plugin.voice_clients) == 0

    @pytest.mark.asyncio
    async def test_stop_stops_conversation_service(
        self,
        plugin,
        mock_agent,
        valid_config,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service,
        mock_discord_bot
    ):
        """stop() should stop ConversationService background tasks"""
        with patch('src.plugins.discord_plugin.commands.Bot', return_value=mock_discord_bot):
            with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_conversation_service):
                with patch('src.plugins.discord_plugin.get_stt_service', return_value=mock_stt_service):
                    with patch('src.plugins.discord_plugin.get_llm_service', return_value=mock_llm_service):
                        with patch('src.plugins.discord_plugin.get_tts_service', return_value=mock_tts_service):
                            # Initialize plugin
                            await plugin.initialize(mock_agent, valid_config)

                            # Stop plugin
                            await plugin.stop()

                            # Verify ConversationService.stop() was called
                            mock_conversation_service.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(
        self,
        plugin,
        mock_agent,
        valid_config,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service,
        mock_discord_bot
    ):
        """Calling stop() multiple times should not error"""
        with patch('src.plugins.discord_plugin.commands.Bot', return_value=mock_discord_bot):
            with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_conversation_service):
                with patch('src.plugins.discord_plugin.get_stt_service', return_value=mock_stt_service):
                    with patch('src.plugins.discord_plugin.get_llm_service', return_value=mock_llm_service):
                        with patch('src.plugins.discord_plugin.get_tts_service', return_value=mock_tts_service):
                            # Initialize plugin
                            await plugin.initialize(mock_agent, valid_config)

                            # Call stop multiple times (should not error)
                            await plugin.stop()
                            await plugin.stop()
                            await plugin.stop()

                            # Verify no exceptions raised

    @pytest.mark.asyncio
    async def test_stop_without_initialization_is_safe(self, plugin, caplog):
        """stop() without initialize() should be safe (no error)"""
        with caplog.at_level(logging.WARNING):
            # Stop without initialization (should warn but not error)
            await plugin.stop()

        # Verify warning logged
        assert "not initialized" in caplog.text


# ============================================================
# Test Class 5: Phase 2 Stubs
# ============================================================

class TestPhase2Stubs:
    """Test stub methods are in place"""

    @pytest.mark.asyncio
    async def test_cleanup_session_stub_exists(self, plugin):
        """_cleanup_session method should exist with Phase 2 TODO"""
        # Verify method exists
        assert hasattr(plugin, '_cleanup_session')
        assert callable(plugin._cleanup_session)

        # Verify it's async
        import inspect
        assert inspect.iscoroutinefunction(plugin._cleanup_session)

        # Call stub (should not raise)
        await plugin._cleanup_session("test_user", str(uuid4()))

    @pytest.mark.asyncio
    async def test_handle_user_speaking_stub_exists(self, plugin):
        """_handle_user_speaking method should exist with Phase 2 TODO"""
        # Verify method exists
        assert hasattr(plugin, '_handle_user_speaking')
        assert callable(plugin._handle_user_speaking)

        # Verify it's async
        import inspect
        assert inspect.iscoroutinefunction(plugin._handle_user_speaking)

        # Create mock Discord user
        mock_user = MagicMock()
        mock_user.id = 123456789
        mock_user.name = "TestUser"

        # Create mock voice client
        mock_voice_client = MagicMock()

        # Call stub (should not raise)
        await plugin._handle_user_speaking(mock_user, b"fake_audio", mock_voice_client)

    def test_phase2_stub_signatures(self, plugin):
        """Verify Phase 2 stub method signatures match expectations"""
        import inspect

        # _cleanup_session signature
        cleanup_sig = inspect.signature(plugin._cleanup_session)
        cleanup_params = list(cleanup_sig.parameters.keys())
        assert 'user_id' in cleanup_params
        assert 'session_id' in cleanup_params

        # _handle_user_speaking signature
        speaking_sig = inspect.signature(plugin._handle_user_speaking)
        speaking_params = list(speaking_sig.parameters.keys())
        assert 'user' in speaking_params
        assert 'audio_data' in speaking_params
        assert 'voice_client' in speaking_params

    @pytest.mark.asyncio
    async def test_cleanup_session_removes_from_dicts(self, plugin, caplog):
        """_cleanup_session stub should remove from active_sessions and session_timings"""
        user_id = "test_user"
        session_id = str(uuid4())

        # Add to tracking
        plugin.active_sessions[user_id] = session_id
        plugin.session_timings[session_id] = {"start": time.time()}

        with caplog.at_level(logging.INFO):
            # Call cleanup
            await plugin._cleanup_session(user_id, session_id)

        # Verify removed
        assert user_id not in plugin.active_sessions
        assert session_id not in plugin.session_timings

        # Verify logging
        assert "Cleaning up session" in caplog.text or "cleanup" in caplog.text.lower()


# ============================================================
# Test Class 6: Additional Integration Tests
# ============================================================

class TestAdditionalIntegration:
    """Additional integration tests for Phase 1"""

    def test_plugin_initialization_state(self, plugin):
        """Verify plugin initial state is correct"""
        # Verify Phase 1 attributes exist
        assert hasattr(plugin, 'conversation_service')
        assert hasattr(plugin, 'stt_service')
        assert hasattr(plugin, 'llm_service')
        assert hasattr(plugin, 'tts_service')
        assert hasattr(plugin, 'active_sessions')
        assert hasattr(plugin, 'session_timings')
        assert hasattr(plugin, 'metrics')

        # Verify initial values
        assert plugin.conversation_service is None
        assert plugin.stt_service is None
        assert plugin.llm_service is None
        assert plugin.tts_service is None
        assert len(plugin.active_sessions) == 0
        assert len(plugin.session_timings) == 0
        assert plugin.metrics is not None

    @pytest.mark.asyncio
    async def test_get_bot_info_includes_phase1_fields(
        self,
        plugin,
        mock_agent,
        valid_config,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service,
        mock_discord_bot
    ):
        """get_bot_info() should include Phase 1 fields (active_sessions, metrics)"""
        with patch('src.plugins.discord_plugin.commands.Bot', return_value=mock_discord_bot):
            with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_conversation_service):
                with patch('src.plugins.discord_plugin.get_stt_service', return_value=mock_stt_service):
                    with patch('src.plugins.discord_plugin.get_llm_service', return_value=mock_llm_service):
                        with patch('src.plugins.discord_plugin.get_tts_service', return_value=mock_tts_service):
                            # Initialize plugin
                            await plugin.initialize(mock_agent, valid_config)

                            # Add test sessions
                            plugin.active_sessions['user_1'] = str(uuid4())
                            plugin.active_sessions['user_2'] = str(uuid4())

                            # Get bot info
                            bot_info = plugin.get_bot_info()

                            # Verify Phase 1 fields
                            assert 'active_sessions' in bot_info
                            assert bot_info['active_sessions'] == 2
                            assert 'metrics' in bot_info
                            assert isinstance(bot_info['metrics'], dict)

    @pytest.mark.asyncio
    async def test_session_cleanup_on_voice_channel_leave(self, plugin):
        """Verify session cleanup logic exists for voice channel leave events"""
        # This tests the event handler registration, not the actual event
        # (full Discord event testing requires integration tests)

        # Verify _cleanup_session is callable
        assert callable(plugin._cleanup_session)

        # Simulate session cleanup
        user_id = "discord_user_123"
        session_id = str(uuid4())
        plugin.active_sessions[user_id] = session_id
        plugin.session_timings[session_id] = {"start": time.time()}

        await plugin._cleanup_session(user_id, session_id)

        # Verify cleanup occurred
        assert user_id not in plugin.active_sessions
        assert session_id not in plugin.session_timings

    def test_metrics_tracker_all_phase1_deques_exist(self):
        """Verify all Phase 1 latency deques exist in MetricsTracker"""
        metrics = MetricsTracker()

        # Phase 1: Speech → Transcription deques
        assert hasattr(metrics, 'whisper_connection_latencies')
        assert hasattr(metrics, 'first_partial_transcript_latencies')
        assert hasattr(metrics, 'transcription_duration_latencies')
        assert hasattr(metrics, 'silence_detection_latencies')

        # Verify they're deques
        from collections import deque
        assert isinstance(metrics.whisper_connection_latencies, deque)
        assert isinstance(metrics.first_partial_transcript_latencies, deque)
        assert isinstance(metrics.transcription_duration_latencies, deque)
        assert isinstance(metrics.silence_detection_latencies, deque)
