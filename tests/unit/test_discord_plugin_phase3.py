"""
Unit tests for DiscordPlugin Phase 3: Discord Plugin API Endpoints

Tests Phase 3 changes (2025-10-28):
- DiscordPlugin.join_voice_channel() method
- DiscordPlugin.leave_voice_channel() method
- DiscordPlugin.get_voice_status() method
- PluginManager.get_discord_plugin_by_agent() method
- PluginManager.discord_join_voice() routing method
- PluginManager.discord_leave_voice() routing method
- PluginManager.discord_get_voice_status() routing method
- FastAPI routes: POST /api/plugins/discord/voice/join
- FastAPI routes: POST /api/plugins/discord/voice/leave
- FastAPI routes: GET /api/plugins/discord/voice/status/{agent_id}

Test Coverage:
- Voice control methods (join, leave, status)
- PluginManager routing to correct plugin instance
- HTTP API endpoint integration (200, 404, 422, 500 status codes)
- Error handling (guild not found, channel not found, already connected)
- AudioReceiver registration on join
- Session cleanup on leave
- Voice status reporting

Target: 80%+ coverage of Phase 3 code
"""
from __future__ import annotations

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from typing import Dict, Any
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient

# Import Discord plugin components
from src.plugins.discord_plugin import DiscordPlugin
from src.services.plugin_manager import PluginManager, get_plugin_manager
from src.routes.discord_plugin_routes import (
    router,
    VoiceJoinRequest,
    VoiceLeaveRequest,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def agent_id():
    """Generate a test agent UUID"""
    return uuid.uuid4()


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
    bot.guilds = []
    return bot


@pytest.fixture
def mock_guild():
    """Mock Discord Guild (server)"""
    guild = MagicMock()
    guild.id = 1234567890
    guild.name = "Test Guild"
    return guild


@pytest.fixture
def mock_voice_channel():
    """Mock Discord VoiceChannel"""
    channel = MagicMock()
    channel.id = 9876543210
    channel.name = "Test Voice Channel"
    # Mock connect() to return a mock VoiceClient
    mock_voice_client = AsyncMock()
    mock_voice_client.guild = MagicMock()
    mock_voice_client.guild.name = "Test Guild"
    mock_voice_client.channel = channel
    mock_voice_client.is_connected = Mock(return_value=True)
    mock_voice_client.disconnect = AsyncMock()
    channel.connect = AsyncMock(return_value=mock_voice_client)
    return channel


@pytest.fixture
def mock_bot_with_guild(mock_discord_bot, mock_guild, mock_voice_channel):
    """Mock Discord Bot with guild and channel"""
    mock_discord_bot.get_guild = Mock(return_value=mock_guild)
    mock_guild.get_channel = Mock(return_value=mock_voice_channel)
    return mock_discord_bot


@pytest.fixture
def mock_conversation_service():
    """Mock ConversationService"""
    service = AsyncMock()
    service.start = AsyncMock()
    service.stop = AsyncMock()
    return service


@pytest.fixture
def mock_stt_service():
    """Mock STTService singleton"""
    service = AsyncMock()
    service.connect = AsyncMock()
    service.disconnect = AsyncMock()
    return service


@pytest.fixture
def mock_llm_service():
    """Mock LLMService singleton"""
    service = AsyncMock()
    service.generate_response = AsyncMock()
    return service


@pytest.fixture
def mock_tts_service():
    """Mock TTSService singleton"""
    service = AsyncMock()
    service.synthesize_speech = AsyncMock()
    return service


@pytest.fixture
async def initialized_plugin(
    mock_agent,
    valid_config,
    mock_bot_with_guild,
    mock_conversation_service,
    mock_stt_service,
    mock_llm_service,
    mock_tts_service
):
    """Create initialized DiscordPlugin with mocked services"""
    plugin = DiscordPlugin()

    with patch('src.plugins.discord_plugin.commands.Bot', return_value=mock_bot_with_guild):
        with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_conversation_service):
            with patch('src.plugins.discord_plugin.get_stt_service', return_value=mock_stt_service):
                with patch('src.plugins.discord_plugin.get_llm_service', return_value=mock_llm_service):
                    with patch('src.plugins.discord_plugin.get_tts_service', return_value=mock_tts_service):
                        await plugin.initialize(mock_agent, valid_config)

    return plugin


@pytest.fixture
def mock_plugin_manager(initialized_plugin, agent_id):
    """Mock PluginManager with initialized Discord plugin"""
    manager = PluginManager()
    manager.active_plugins[agent_id] = {
        'discord': initialized_plugin
    }
    return manager


# ============================================================
# Test Class 1: DiscordPlugin Voice Control Methods
# ============================================================

class TestVoiceControlMethods:
    """Test DiscordPlugin voice control methods"""

    @pytest.mark.asyncio
    async def test_join_voice_channel_success(
        self,
        initialized_plugin,
        mock_bot_with_guild,
        mock_guild,
        mock_voice_channel
    ):
        """Should join voice channel and register AudioReceiver"""
        guild_id = mock_guild.id
        channel_id = mock_voice_channel.id

        # Mock voice_recv.VoiceRecvClient
        with patch('src.plugins.discord_plugin.voice_recv'):
            result = await initialized_plugin.join_voice_channel(guild_id, channel_id)

        # Verify result
        assert result['success'] is True
        assert result['guild_id'] == guild_id
        assert result['guild_name'] == mock_guild.name
        assert result['channel_id'] == channel_id
        assert result['channel_name'] == mock_voice_channel.name
        assert result['agent_id'] == str(initialized_plugin.agent_id)
        assert result['agent_name'] == initialized_plugin.agent_name

        # Verify voice client stored
        assert guild_id in initialized_plugin.voice_clients

        # Verify AudioReceiver registered
        assert guild_id in initialized_plugin.audio_receivers

    @pytest.mark.asyncio
    async def test_join_voice_channel_already_connected(
        self,
        initialized_plugin,
        mock_guild
    ):
        """Should raise ValueError if already connected to guild"""
        guild_id = mock_guild.id
        channel_id = 9876543210

        # Add existing voice client
        mock_voice_client = MagicMock()
        initialized_plugin.voice_clients[guild_id] = mock_voice_client

        # Attempt to join again
        with pytest.raises(ValueError) as exc_info:
            await initialized_plugin.join_voice_channel(guild_id, channel_id)

        assert "Already connected" in str(exc_info.value)
        assert str(guild_id) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_join_voice_channel_guild_not_found(
        self,
        initialized_plugin,
        mock_bot_with_guild
    ):
        """Should raise ValueError if guild not found"""
        guild_id = 9999999999  # Non-existent guild
        channel_id = 9876543210

        # Mock get_guild to return None
        mock_bot_with_guild.get_guild = Mock(return_value=None)

        with pytest.raises(ValueError) as exc_info:
            await initialized_plugin.join_voice_channel(guild_id, channel_id)

        assert "Guild" in str(exc_info.value)
        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_join_voice_channel_channel_not_found(
        self,
        initialized_plugin,
        mock_bot_with_guild,
        mock_guild
    ):
        """Should raise ValueError if channel not found in guild"""
        guild_id = mock_guild.id
        channel_id = 9999999999  # Non-existent channel

        # Mock get_channel to return None
        mock_guild.get_channel = Mock(return_value=None)

        with pytest.raises(ValueError) as exc_info:
            await initialized_plugin.join_voice_channel(guild_id, channel_id)

        assert "Channel" in str(exc_info.value)
        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_join_voice_channel_connection_failure(
        self,
        initialized_plugin,
        mock_bot_with_guild,
        mock_guild,
        mock_voice_channel
    ):
        """Should raise RuntimeError on connection error"""
        guild_id = mock_guild.id
        channel_id = mock_voice_channel.id

        # Mock connect() to raise exception
        mock_voice_channel.connect = AsyncMock(side_effect=Exception("Connection failed"))

        with pytest.raises(RuntimeError) as exc_info:
            await initialized_plugin.join_voice_channel(guild_id, channel_id)

        assert "Failed to join voice channel" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_leave_voice_channel_success(
        self,
        initialized_plugin,
        mock_guild
    ):
        """Should disconnect voice client and cleanup sessions"""
        guild_id = mock_guild.id

        # Add voice client and sessions
        mock_voice_client = MagicMock()
        mock_voice_client.disconnect = AsyncMock()
        initialized_plugin.voice_clients[guild_id] = mock_voice_client

        # Add audio receiver
        mock_receiver = MagicMock()
        mock_receiver.cleanup = Mock()
        initialized_plugin.audio_receivers[guild_id] = mock_receiver

        # Add active sessions
        user_id = "user_123"
        session_id = str(uuid.uuid4())
        initialized_plugin.active_sessions[user_id] = session_id

        # Mock _cleanup_session
        initialized_plugin._cleanup_session = AsyncMock()

        result = await initialized_plugin.leave_voice_channel(guild_id)

        # Verify result
        assert result['success'] is True
        assert result['guild_id'] == guild_id
        assert result['agent_id'] == str(initialized_plugin.agent_id)
        assert result['agent_name'] == initialized_plugin.agent_name

        # Verify cleanup
        mock_receiver.cleanup.assert_called_once()
        mock_voice_client.disconnect.assert_called_once()
        assert guild_id not in initialized_plugin.voice_clients
        assert guild_id not in initialized_plugin.audio_receivers

    @pytest.mark.asyncio
    async def test_leave_voice_channel_not_connected(
        self,
        initialized_plugin
    ):
        """Should raise ValueError if not connected to guild"""
        guild_id = 9999999999  # Not connected to this guild

        with pytest.raises(ValueError) as exc_info:
            await initialized_plugin.leave_voice_channel(guild_id)

        assert "Not connected" in str(exc_info.value)
        assert str(guild_id) in str(exc_info.value)

    def test_get_voice_status_with_connections(
        self,
        initialized_plugin,
        mock_guild,
        mock_voice_channel
    ):
        """Should return status with active connections"""
        guild_id = mock_guild.id

        # Add voice client
        mock_voice_client = MagicMock()
        mock_voice_client.guild = mock_guild
        mock_voice_client.channel = mock_voice_channel
        mock_voice_client.is_connected = Mock(return_value=True)
        initialized_plugin.voice_clients[guild_id] = mock_voice_client

        # Add active sessions
        initialized_plugin.active_sessions['user_1'] = str(uuid.uuid4())
        initialized_plugin.active_sessions['user_2'] = str(uuid.uuid4())

        result = initialized_plugin.get_voice_status()

        # Verify result
        assert result['agent_id'] == str(initialized_plugin.agent_id)
        assert result['agent_name'] == initialized_plugin.agent_name
        assert len(result['connections']) == 1
        assert result['active_sessions'] == 2

        # Verify connection details
        conn = result['connections'][0]
        assert conn['guild_id'] == guild_id
        assert conn['guild_name'] == mock_guild.name
        assert conn['channel_id'] == mock_voice_channel.id
        assert conn['channel_name'] == mock_voice_channel.name
        assert conn['connected'] is True

    def test_get_voice_status_no_connections(
        self,
        initialized_plugin
    ):
        """Should return status with empty connections list"""
        result = initialized_plugin.get_voice_status()

        # Verify result
        assert result['agent_id'] == str(initialized_plugin.agent_id)
        assert result['agent_name'] == initialized_plugin.agent_name
        assert result['connections'] == []
        assert result['active_sessions'] == 0


# ============================================================
# Test Class 2: PluginManager Routing Methods
# ============================================================

class TestPluginManagerRouting:
    """Test PluginManager routing methods"""

    def test_get_discord_plugin_by_agent_found(
        self,
        mock_plugin_manager,
        initialized_plugin,
        agent_id
    ):
        """Should return Discord plugin for agent"""
        plugin = mock_plugin_manager.get_discord_plugin_by_agent(agent_id)

        assert plugin is initialized_plugin
        assert plugin.agent_id == agent_id

    def test_get_discord_plugin_by_agent_not_found(
        self,
        mock_plugin_manager
    ):
        """Should return None if agent has no Discord plugin"""
        non_existent_agent_id = uuid.uuid4()

        plugin = mock_plugin_manager.get_discord_plugin_by_agent(non_existent_agent_id)

        assert plugin is None

    def test_get_discord_plugin_by_agent_no_discord_plugin(
        self,
        mock_plugin_manager,
        agent_id
    ):
        """Should return None if agent has no Discord plugin"""
        # Create agent with only n8n plugin (no discord)
        mock_plugin_manager.active_plugins[agent_id] = {
            'n8n': MagicMock()
        }

        plugin = mock_plugin_manager.get_discord_plugin_by_agent(agent_id)

        assert plugin is None

    @pytest.mark.asyncio
    async def test_discord_join_voice_delegates_to_plugin(
        self,
        mock_plugin_manager,
        initialized_plugin,
        agent_id
    ):
        """Should call plugin.join_voice_channel()"""
        guild_id = 1234567890
        channel_id = 9876543210

        # Mock join_voice_channel
        initialized_plugin.join_voice_channel = AsyncMock(return_value={
            'success': True,
            'guild_id': guild_id,
            'channel_id': channel_id
        })

        result = await mock_plugin_manager.discord_join_voice(
            agent_id,
            guild_id,
            channel_id
        )

        # Verify delegation
        initialized_plugin.join_voice_channel.assert_called_once_with(guild_id, channel_id)
        assert result['success'] is True

    @pytest.mark.asyncio
    async def test_discord_join_voice_plugin_not_found(
        self,
        mock_plugin_manager
    ):
        """Should raise ValueError if plugin not found"""
        non_existent_agent_id = uuid.uuid4()
        guild_id = 1234567890
        channel_id = 9876543210

        with pytest.raises(ValueError) as exc_info:
            await mock_plugin_manager.discord_join_voice(
                non_existent_agent_id,
                guild_id,
                channel_id
            )

        assert "Discord plugin not found" in str(exc_info.value)
        assert str(non_existent_agent_id) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_discord_leave_voice_delegates_to_plugin(
        self,
        mock_plugin_manager,
        initialized_plugin,
        agent_id
    ):
        """Should call plugin.leave_voice_channel()"""
        guild_id = 1234567890

        # Mock leave_voice_channel
        initialized_plugin.leave_voice_channel = AsyncMock(return_value={
            'success': True,
            'guild_id': guild_id
        })

        result = await mock_plugin_manager.discord_leave_voice(
            agent_id,
            guild_id
        )

        # Verify delegation
        initialized_plugin.leave_voice_channel.assert_called_once_with(guild_id)
        assert result['success'] is True

    @pytest.mark.asyncio
    async def test_discord_leave_voice_plugin_not_found(
        self,
        mock_plugin_manager
    ):
        """Should raise ValueError if plugin not found"""
        non_existent_agent_id = uuid.uuid4()
        guild_id = 1234567890

        with pytest.raises(ValueError) as exc_info:
            await mock_plugin_manager.discord_leave_voice(
                non_existent_agent_id,
                guild_id
            )

        assert "Discord plugin not found" in str(exc_info.value)

    def test_discord_get_voice_status_delegates_to_plugin(
        self,
        mock_plugin_manager,
        initialized_plugin,
        agent_id
    ):
        """Should call plugin.get_voice_status()"""
        # Mock get_voice_status
        initialized_plugin.get_voice_status = Mock(return_value={
            'connections': [],
            'active_sessions': 0
        })

        result = mock_plugin_manager.discord_get_voice_status(agent_id)

        # Verify delegation
        initialized_plugin.get_voice_status.assert_called_once()
        assert 'connections' in result
        assert 'active_sessions' in result

    def test_discord_get_voice_status_plugin_not_found(
        self,
        mock_plugin_manager
    ):
        """Should raise ValueError if plugin not found"""
        non_existent_agent_id = uuid.uuid4()

        with pytest.raises(ValueError) as exc_info:
            mock_plugin_manager.discord_get_voice_status(non_existent_agent_id)

        assert "Discord plugin not found" in str(exc_info.value)


# ============================================================
# Test Class 3: FastAPI Endpoint Tests
# ============================================================

class TestAPIEndpoints:
    """Test FastAPI routes using TestClient"""

    @pytest.mark.asyncio
    async def test_post_join_voice_success(
        self,
        mock_plugin_manager,
        agent_id
    ):
        """POST /voice/join should return 200 with connection status"""
        guild_id = 1234567890
        channel_id = 9876543210

        request_data = {
            'agent_id': str(agent_id),
            'guild_id': guild_id,
            'channel_id': channel_id
        }

        expected_response = {
            'success': True,
            'guild_id': guild_id,
            'channel_id': channel_id,
            'agent_id': str(agent_id)
        }

        with patch('src.routes.discord_plugin_routes.get_plugin_manager', return_value=mock_plugin_manager):
            mock_plugin_manager.discord_join_voice = AsyncMock(return_value=expected_response)

            from src.routes.discord_plugin_routes import join_voice_channel
            request = VoiceJoinRequest(**request_data)
            result = await join_voice_channel(request)

            assert result['success'] is True
            assert result['guild_id'] == guild_id
            assert result['channel_id'] == channel_id

    @pytest.mark.asyncio
    async def test_post_join_voice_agent_not_found(
        self,
        mock_plugin_manager
    ):
        """POST /voice/join should return 404 if agent not found"""
        agent_id = uuid.uuid4()
        guild_id = 1234567890
        channel_id = 9876543210

        request_data = {
            'agent_id': str(agent_id),
            'guild_id': guild_id,
            'channel_id': channel_id
        }

        with patch('src.routes.discord_plugin_routes.get_plugin_manager', return_value=mock_plugin_manager):
            mock_plugin_manager.discord_join_voice = AsyncMock(
                side_effect=ValueError(f"Discord plugin not found for agent {agent_id}")
            )

            from src.routes.discord_plugin_routes import join_voice_channel
            request = VoiceJoinRequest(**request_data)

            with pytest.raises(HTTPException) as exc_info:
                await join_voice_channel(request)

            assert exc_info.value.status_code == 404
            assert "Discord plugin not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_post_join_voice_invalid_agent_id(
        self,
        mock_plugin_manager
    ):
        """POST /voice/join should raise ValueError if agent_id not UUID"""
        request_data = {
            'agent_id': 'not-a-uuid',
            'guild_id': 1234567890,
            'channel_id': 9876543210
        }

        # Pydantic will validate and raise ValidationError before route handler
        with pytest.raises(Exception):  # ValidationError from Pydantic
            VoiceJoinRequest(**request_data)

    @pytest.mark.asyncio
    async def test_post_join_voice_connection_failure(
        self,
        mock_plugin_manager,
        agent_id
    ):
        """POST /voice/join should return 500 on connection error"""
        guild_id = 1234567890
        channel_id = 9876543210

        request_data = {
            'agent_id': str(agent_id),
            'guild_id': guild_id,
            'channel_id': channel_id
        }

        with patch('src.routes.discord_plugin_routes.get_plugin_manager', return_value=mock_plugin_manager):
            mock_plugin_manager.discord_join_voice = AsyncMock(
                side_effect=RuntimeError("Failed to join voice channel")
            )

            from src.routes.discord_plugin_routes import join_voice_channel
            request = VoiceJoinRequest(**request_data)

            with pytest.raises(HTTPException) as exc_info:
                await join_voice_channel(request)

            assert exc_info.value.status_code == 500
            assert "Failed to join voice channel" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_post_leave_voice_success(
        self,
        mock_plugin_manager,
        agent_id
    ):
        """POST /voice/leave should return 200 with disconnection status"""
        guild_id = 1234567890

        request_data = {
            'agent_id': str(agent_id),
            'guild_id': guild_id
        }

        expected_response = {
            'success': True,
            'guild_id': guild_id,
            'agent_id': str(agent_id)
        }

        with patch('src.routes.discord_plugin_routes.get_plugin_manager', return_value=mock_plugin_manager):
            mock_plugin_manager.discord_leave_voice = AsyncMock(return_value=expected_response)

            from src.routes.discord_plugin_routes import leave_voice_channel
            request = VoiceLeaveRequest(**request_data)
            result = await leave_voice_channel(request)

            assert result['success'] is True
            assert result['guild_id'] == guild_id

    @pytest.mark.asyncio
    async def test_post_leave_voice_not_connected(
        self,
        mock_plugin_manager,
        agent_id
    ):
        """POST /voice/leave should return 404 if not connected"""
        guild_id = 1234567890

        request_data = {
            'agent_id': str(agent_id),
            'guild_id': guild_id
        }

        with patch('src.routes.discord_plugin_routes.get_plugin_manager', return_value=mock_plugin_manager):
            mock_plugin_manager.discord_leave_voice = AsyncMock(
                side_effect=ValueError(f"Not connected to voice channel in guild {guild_id}")
            )

            from src.routes.discord_plugin_routes import leave_voice_channel
            request = VoiceLeaveRequest(**request_data)

            with pytest.raises(HTTPException) as exc_info:
                await leave_voice_channel(request)

            assert exc_info.value.status_code == 404
            assert "Not connected" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_voice_status_success(
        self,
        mock_plugin_manager,
        agent_id
    ):
        """GET /voice/status/{agent_id} should return 200 with status"""
        expected_response = {
            'agent_id': str(agent_id),
            'connections': [],
            'active_sessions': 0
        }

        with patch('src.routes.discord_plugin_routes.get_plugin_manager', return_value=mock_plugin_manager):
            mock_plugin_manager.discord_get_voice_status = Mock(return_value=expected_response)

            from src.routes.discord_plugin_routes import get_voice_status
            result = await get_voice_status(str(agent_id))

            assert result['agent_id'] == str(agent_id)
            assert 'connections' in result
            assert 'active_sessions' in result

    @pytest.mark.asyncio
    async def test_get_voice_status_agent_not_found(
        self,
        mock_plugin_manager
    ):
        """GET /voice/status/{agent_id} should return 404 if agent not found"""
        agent_id = uuid.uuid4()

        with patch('src.routes.discord_plugin_routes.get_plugin_manager', return_value=mock_plugin_manager):
            mock_plugin_manager.discord_get_voice_status = Mock(
                side_effect=ValueError(f"Discord plugin not found for agent {agent_id}")
            )

            from src.routes.discord_plugin_routes import get_voice_status

            with pytest.raises(HTTPException) as exc_info:
                await get_voice_status(str(agent_id))

            assert exc_info.value.status_code == 404
            assert "Discord plugin not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_voice_status_invalid_agent_id(
        self,
        mock_plugin_manager
    ):
        """GET /voice/status/{agent_id} should return 500 if agent_id not UUID"""
        agent_id_str = 'not-a-uuid'

        with patch('src.routes.discord_plugin_routes.get_plugin_manager', return_value=mock_plugin_manager):
            from src.routes.discord_plugin_routes import get_voice_status

            with pytest.raises(Exception):  # ValueError from UUID() conversion
                await get_voice_status(agent_id_str)

    @pytest.mark.asyncio
    async def test_post_join_voice_unexpected_error(
        self,
        mock_plugin_manager,
        agent_id
    ):
        """POST /voice/join should return 500 on unexpected error"""
        guild_id = 1234567890
        channel_id = 9876543210

        request_data = {
            'agent_id': str(agent_id),
            'guild_id': guild_id,
            'channel_id': channel_id
        }

        with patch('src.routes.discord_plugin_routes.get_plugin_manager', return_value=mock_plugin_manager):
            mock_plugin_manager.discord_join_voice = AsyncMock(
                side_effect=Exception("Unexpected database error")
            )

            from src.routes.discord_plugin_routes import join_voice_channel
            request = VoiceJoinRequest(**request_data)

            with pytest.raises(HTTPException) as exc_info:
                await join_voice_channel(request)

            assert exc_info.value.status_code == 500
            assert "Unexpected error" in exc_info.value.detail


# ============================================================
# Test Class 4: Integration Scenarios
# ============================================================

class TestPhase3IntegrationScenarios:
    """Test complete Phase 3 integration scenarios"""

    @pytest.mark.asyncio
    async def test_complete_join_flow(
        self,
        initialized_plugin,
        mock_bot_with_guild,
        mock_guild,
        mock_voice_channel
    ):
        """Test complete join flow: API → PluginManager → DiscordPlugin → Discord"""
        agent_id = initialized_plugin.agent_id
        guild_id = mock_guild.id
        channel_id = mock_voice_channel.id

        # Create PluginManager
        manager = PluginManager()
        manager.active_plugins[agent_id] = {'discord': initialized_plugin}

        # Mock voice_recv for AudioReceiver
        with patch('src.plugins.discord_plugin.voice_recv'):
            # Call through PluginManager
            result = await manager.discord_join_voice(agent_id, guild_id, channel_id)

        # Verify result
        assert result['success'] is True
        assert result['guild_id'] == guild_id
        assert result['channel_id'] == channel_id

        # Verify voice client stored
        assert guild_id in initialized_plugin.voice_clients

        # Verify AudioReceiver registered
        assert guild_id in initialized_plugin.audio_receivers

    @pytest.mark.asyncio
    async def test_complete_leave_flow(
        self,
        initialized_plugin
    ):
        """Test complete leave flow: API → PluginManager → DiscordPlugin → Cleanup"""
        agent_id = initialized_plugin.agent_id
        guild_id = 1234567890

        # Setup voice connection
        mock_voice_client = MagicMock()
        mock_voice_client.disconnect = AsyncMock()
        initialized_plugin.voice_clients[guild_id] = mock_voice_client

        mock_receiver = MagicMock()
        mock_receiver.cleanup = Mock()
        initialized_plugin.audio_receivers[guild_id] = mock_receiver

        # Create PluginManager
        manager = PluginManager()
        manager.active_plugins[agent_id] = {'discord': initialized_plugin}

        # Mock _cleanup_session
        initialized_plugin._cleanup_session = AsyncMock()

        # Call through PluginManager
        result = await manager.discord_leave_voice(agent_id, guild_id)

        # Verify result
        assert result['success'] is True
        assert result['guild_id'] == guild_id

        # Verify cleanup
        mock_receiver.cleanup.assert_called_once()
        mock_voice_client.disconnect.assert_called_once()
        assert guild_id not in initialized_plugin.voice_clients

    @pytest.mark.asyncio
    async def test_multiple_agents_independent_connections(
        self,
        mock_agent,
        valid_config,
        mock_bot_with_guild,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """Test multiple agents can have independent voice connections"""
        # Create two plugins for two agents
        plugin1 = DiscordPlugin()
        plugin2 = DiscordPlugin()

        with patch('src.plugins.discord_plugin.commands.Bot', return_value=mock_bot_with_guild):
            with patch('src.plugins.discord_plugin.ConversationService', return_value=mock_conversation_service):
                with patch('src.plugins.discord_plugin.get_stt_service', return_value=mock_stt_service):
                    with patch('src.plugins.discord_plugin.get_llm_service', return_value=mock_llm_service):
                        with patch('src.plugins.discord_plugin.get_tts_service', return_value=mock_tts_service):
                            await plugin1.initialize(mock_agent, valid_config)
                            await plugin2.initialize(mock_agent, valid_config)

        # Setup PluginManager with both plugins
        agent1_id = uuid.uuid4()
        agent2_id = uuid.uuid4()
        manager = PluginManager()
        manager.active_plugins[agent1_id] = {'discord': plugin1}
        manager.active_plugins[agent2_id] = {'discord': plugin2}

        # Both agents should have independent status
        status1 = manager.discord_get_voice_status(agent1_id)
        status2 = manager.discord_get_voice_status(agent2_id)

        assert status1 != status2  # Different status dicts
        assert len(status1['connections']) == 0
        assert len(status2['connections']) == 0

    @pytest.mark.asyncio
    async def test_voice_status_reflects_active_connections(
        self,
        initialized_plugin,
        mock_guild,
        mock_voice_channel
    ):
        """Voice status should accurately reflect active connections"""
        agent_id = initialized_plugin.agent_id
        guild_id = mock_guild.id

        # Create PluginManager
        manager = PluginManager()
        manager.active_plugins[agent_id] = {'discord': initialized_plugin}

        # Initially no connections
        status = manager.discord_get_voice_status(agent_id)
        assert len(status['connections']) == 0

        # Add voice connection
        mock_voice_client = MagicMock()
        mock_voice_client.guild = mock_guild
        mock_voice_client.channel = mock_voice_channel
        mock_voice_client.is_connected = Mock(return_value=True)
        initialized_plugin.voice_clients[guild_id] = mock_voice_client

        # Now should show 1 connection
        status = manager.discord_get_voice_status(agent_id)
        assert len(status['connections']) == 1
        assert status['connections'][0]['guild_id'] == guild_id
        assert status['connections'][0]['connected'] is True
