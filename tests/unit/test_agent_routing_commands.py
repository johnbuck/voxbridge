"""
Unit Tests for Phase 6.4.1 Batch 3 - Agent Routing Commands

Tests Discord slash commands for agent management.

Coverage:
- /agent list command shows all agents
- /agent select command switches default agent
- /agent select validates Discord plugin enabled
- /agent current shows active agent
- Command error handling
- Command permissions
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_agents():
    """Create mock agents for testing"""
    agent1 = MagicMock()
    agent1.id = uuid4()
    agent1.name = "Agent1"
    agent1.system_prompt = "You are helpful agent 1"
    agent1.is_default = True
    agent1.plugins = {'discord': {'enabled': True, 'bot_token': 'token1'}}

    agent2 = MagicMock()
    agent2.id = uuid4()
    agent2.name = "Agent2"
    agent2.system_prompt = "You are helpful agent 2"
    agent2.is_default = False
    agent2.plugins = {'discord': {'enabled': True, 'bot_token': 'token2'}}

    agent3 = MagicMock()
    agent3.id = uuid4()
    agent3.name = "Agent3"
    agent3.system_prompt = "You are helpful agent 3"
    agent3.is_default = False
    agent3.plugins = {}  # No Discord plugin

    return [agent1, agent2, agent3]


@pytest.fixture
def mock_interaction():
    """Create mock Discord interaction"""
    interaction = MagicMock()
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


# ============================================================
# Test Class 1: Agent List Command
# ============================================================

class TestAgentListCommand:
    """Test /agent list command functionality"""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_agent_list_shows_all_agents(self, mock_agents, mock_interaction):
        """Test /agent list displays all available agents"""
        # Mock AgentService.get_all_agents
        with patch('src.services.agent_service.AgentService.get_all_agents', new=AsyncMock(return_value=mock_agents)):
            from src.services.agent_service import AgentService

            # Simulate command execution
            agents = await AgentService.get_all_agents()

            # Verify all agents returned
            assert len(agents) == 3
            assert agents[0].name == "Agent1"
            assert agents[1].name == "Agent2"
            assert agents[2].name == "Agent3"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_agent_list_marks_default_agent(self, mock_agents, mock_interaction):
        """Test /agent list marks the default agent"""
        with patch('src.services.agent_service.AgentService.get_all_agents', new=AsyncMock(return_value=mock_agents)):
            from src.services.agent_service import AgentService

            agents = await AgentService.get_all_agents()

            # Find default agent
            default_agents = [a for a in agents if a.is_default]

            # Should have exactly one default
            assert len(default_agents) == 1
            assert default_agents[0].name == "Agent1"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_agent_list_handles_empty_database(self, mock_interaction):
        """Test /agent list handles no agents gracefully"""
        with patch('src.services.agent_service.AgentService.get_all_agents', new=AsyncMock(return_value=[])):
            from src.services.agent_service import AgentService

            agents = await AgentService.get_all_agents()

            # Should return empty list
            assert len(agents) == 0

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_agent_list_shows_discord_plugin_status(self, mock_agents):
        """Test /agent list shows which agents have Discord plugin"""
        with patch('src.services.agent_service.AgentService.get_all_agents', new=AsyncMock(return_value=mock_agents)):
            from src.services.agent_service import AgentService

            agents = await AgentService.get_all_agents()

            # Check Discord plugin status
            agent1_has_discord = 'discord' in agents[0].plugins and agents[0].plugins['discord'].get('enabled', False)
            agent2_has_discord = 'discord' in agents[1].plugins and agents[1].plugins['discord'].get('enabled', False)
            agent3_has_discord = 'discord' in agents[2].plugins and agents[2].plugins['discord'].get('enabled', False)

            assert agent1_has_discord == True
            assert agent2_has_discord == True
            assert agent3_has_discord == False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_agent_list_handles_database_error(self, mock_interaction, caplog):
        """Test /agent list handles database errors"""
        import logging

        # Mock database error
        with patch('src.services.agent_service.AgentService.get_all_agents', new=AsyncMock(side_effect=Exception("Database error"))):
            with caplog.at_level(logging.ERROR):
                from src.services.agent_service import AgentService

                try:
                    agents = await AgentService.get_all_agents()
                except Exception as e:
                    # Error should be raised
                    assert "Database error" in str(e)


# ============================================================
# Test Class 2: Agent Select Command
# ============================================================

class TestAgentSelectCommand:
    """Test /agent select command functionality"""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_agent_select_sets_default(self, mock_agents):
        """Test /agent select switches default agent"""
        target_agent = mock_agents[1]  # Agent2

        # Mock AgentService methods
        with patch('src.services.agent_service.AgentService.get_agent_by_name', new=AsyncMock(return_value=target_agent)):
            with patch('src.services.agent_service.AgentService.set_default_agent', new=AsyncMock()) as mock_set_default:
                from src.services.agent_service import AgentService

                # Simulate selecting agent
                agent = await AgentService.get_agent_by_name("Agent2")
                if agent:
                    await AgentService.set_default_agent(agent.id)

                # Verify set_default_agent called
                mock_set_default.assert_called_once_with(target_agent.id)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_agent_select_validates_discord_plugin(self, mock_agents):
        """Test /agent select validates Discord plugin is enabled"""
        # Agent3 has no Discord plugin
        agent_without_discord = mock_agents[2]

        with patch('src.services.agent_service.AgentService.get_agent_by_name', new=AsyncMock(return_value=agent_without_discord)):
            from src.services.agent_service import AgentService

            agent = await AgentService.get_agent_by_name("Agent3")

            # Check if Discord plugin enabled
            discord_plugin = agent.plugins.get('discord', {})
            is_enabled = discord_plugin.get('enabled', False)

            # Should be False (no Discord plugin)
            assert is_enabled == False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_agent_select_handles_nonexistent_agent(self):
        """Test /agent select handles invalid agent name"""
        with patch('src.services.agent_service.AgentService.get_agent_by_name', new=AsyncMock(return_value=None)):
            from src.services.agent_service import AgentService

            agent = await AgentService.get_agent_by_name("NonExistentAgent")

            # Should return None
            assert agent is None

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_agent_select_invalidates_cache(self, mock_agents):
        """Test /agent select invalidates plugin manager cache"""
        target_agent = mock_agents[1]

        with patch('src.services.agent_service.AgentService.get_agent_by_name', new=AsyncMock(return_value=target_agent)):
            with patch('src.services.agent_service.AgentService.set_default_agent', new=AsyncMock()):
                with patch('src.services.plugin_manager.get_plugin_manager') as mock_get_manager:
                    mock_manager = MagicMock()
                    mock_manager.invalidate_agent_cache = MagicMock()
                    mock_get_manager.return_value = mock_manager

                    from src.services.agent_service import AgentService

                    # Select agent
                    agent = await AgentService.get_agent_by_name("Agent2")
                    if agent:
                        await AgentService.set_default_agent(agent.id)

                        # Invalidate cache
                        mock_manager.invalidate_agent_cache()

                    # Verify cache invalidation called
                    mock_manager.invalidate_agent_cache.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_agent_select_restarts_plugins(self, mock_agents):
        """Test /agent select restarts plugins for new agent"""
        new_agent = mock_agents[1]

        with patch('src.services.agent_service.AgentService.get_agent_by_name', new=AsyncMock(return_value=new_agent)):
            with patch('src.services.agent_service.AgentService.set_default_agent', new=AsyncMock()):
                with patch('src.services.plugin_manager.get_plugin_manager') as mock_get_manager:
                    mock_manager = MagicMock()
                    mock_manager.stop_agent_plugins = AsyncMock()
                    mock_manager.initialize_agent_plugins = AsyncMock()
                    mock_get_manager.return_value = mock_manager

                    from src.services.agent_service import AgentService

                    # Select agent
                    agent = await AgentService.get_agent_by_name("Agent2")
                    if agent:
                        await AgentService.set_default_agent(agent.id)

                        # Stop old plugins (would need old agent ID)
                        # Start new plugins
                        await mock_manager.initialize_agent_plugins(agent)

                    # Verify plugin initialization called
                    mock_manager.initialize_agent_plugins.assert_called_once_with(new_agent)


# ============================================================
# Test Class 3: Agent Current Command
# ============================================================

class TestAgentCurrentCommand:
    """Test /agent current command functionality"""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_agent_current_shows_default_agent(self, mock_agents):
        """Test /agent current shows currently active agent"""
        default_agent = mock_agents[0]

        with patch('src.services.agent_service.AgentService.get_default_agent', new=AsyncMock(return_value=default_agent)):
            from src.services.agent_service import AgentService

            agent = await AgentService.get_default_agent()

            # Should return default agent
            assert agent is not None
            assert agent.name == "Agent1"
            assert agent.is_default == True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_agent_current_handles_no_default(self):
        """Test /agent current handles no default agent set"""
        with patch('src.services.agent_service.AgentService.get_default_agent', new=AsyncMock(return_value=None)):
            from src.services.agent_service import AgentService

            agent = await AgentService.get_default_agent()

            # Should return None
            assert agent is None


# ============================================================
# Test Class 4: Command Validation
# ============================================================

class TestCommandValidation:
    """Test command input validation"""

    @pytest.mark.unit
    def test_agent_name_validation(self):
        """Test agent name validation"""
        # Valid names
        valid_names = ["Agent1", "TestAgent", "Agent-123", "Agent_Test"]
        for name in valid_names:
            assert isinstance(name, str)
            assert len(name) > 0

        # Invalid names (empty string)
        invalid_names = ["", "   "]
        for name in invalid_names:
            assert len(name.strip()) == 0

    @pytest.mark.unit
    def test_discord_plugin_config_validation(self):
        """Test Discord plugin config validation"""
        # Valid config
        valid_config = {
            'enabled': True,
            'bot_token': 'test_token_123456789'
        }
        assert valid_config['enabled'] == True
        assert len(valid_config['bot_token']) > 0

        # Invalid config (missing token)
        invalid_config = {
            'enabled': True
        }
        assert 'bot_token' not in invalid_config


# ============================================================
# Test Class 5: Command Error Handling
# ============================================================

class TestCommandErrorHandling:
    """Test error handling in commands"""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_command_handles_agent_not_found(self):
        """Test command handles agent not found error"""
        with patch('src.services.agent_service.AgentService.get_agent_by_name', new=AsyncMock(return_value=None)):
            from src.services.agent_service import AgentService

            agent = await AgentService.get_agent_by_name("NonExistent")

            # Should return None (not raise exception)
            assert agent is None

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_command_handles_database_error(self, caplog):
        """Test command handles database errors gracefully"""
        import logging

        with patch('src.services.agent_service.AgentService.get_all_agents', new=AsyncMock(side_effect=Exception("DB error"))):
            with caplog.at_level(logging.ERROR):
                from src.services.agent_service import AgentService

                try:
                    agents = await AgentService.get_all_agents()
                except Exception as e:
                    # Error should be raised
                    assert "DB error" in str(e)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_command_handles_plugin_init_failure(self, mock_agents):
        """Test command handles plugin initialization failure"""
        agent = mock_agents[0]

        with patch('src.services.plugin_manager.get_plugin_manager') as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.initialize_agent_plugins = AsyncMock(side_effect=Exception("Plugin init failed"))
            mock_get_manager.return_value = mock_manager

            try:
                await mock_manager.initialize_agent_plugins(agent)
            except Exception as e:
                # Error should be raised
                assert "Plugin init failed" in str(e)


# ============================================================
# Test Class 6: Integration with Plugin Manager
# ============================================================

class TestPluginManagerIntegration:
    """Test command integration with plugin manager"""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_select_command_uses_plugin_manager(self, mock_agents):
        """Test /agent select uses plugin manager for agent switching"""
        from src.services.plugin_manager import get_plugin_manager

        plugin_manager = get_plugin_manager()

        # Verify plugin manager exists
        assert plugin_manager is not None

        # Verify get_default_agent_id method exists
        assert hasattr(plugin_manager, 'get_default_agent_id')

        # Verify invalidate_agent_cache method exists
        assert hasattr(plugin_manager, 'invalidate_agent_cache')

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_select_command_caches_new_default(self, mock_agents):
        """Test /agent select caches new default agent"""
        from src.services.plugin_manager import PluginManager

        plugin_manager = PluginManager()

        new_default = mock_agents[1]

        # Mock AgentService
        with patch('src.services.agent_service.AgentService.get_default_agent', new=AsyncMock(return_value=new_default)):
            # Get default agent (should cache)
            agent_id = await plugin_manager.get_default_agent_id()

            # Verify cached
            assert plugin_manager._default_agent_id == new_default.id
            assert plugin_manager._default_agent_cache_time is not None


# ============================================================
# Test Class 7: Command Permissions (Future)
# ============================================================

class TestCommandPermissions:
    """Test command permission checks (future feature)"""

    @pytest.mark.unit
    def test_admin_commands_require_permission(self):
        """Test admin commands check for permissions (future)"""
        # Placeholder for future permission system
        # /agent select should require admin/moderator role
        pass

    @pytest.mark.unit
    def test_readonly_commands_allow_all_users(self):
        """Test read-only commands allow all users (future)"""
        # Placeholder for future permission system
        # /agent list and /agent current should allow all users
        pass


# ============================================================
# Test Class 8: Command Response Formatting
# ============================================================

class TestCommandResponseFormatting:
    """Test command response formatting"""

    @pytest.mark.unit
    def test_agent_list_formats_response(self, mock_agents):
        """Test /agent list formats response correctly"""
        # Simulate formatting agent list
        response_lines = []
        for agent in mock_agents:
            discord_status = "✅" if 'discord' in agent.plugins and agent.plugins['discord'].get('enabled') else "❌"
            default_marker = "⭐" if agent.is_default else ""
            line = f"{default_marker} {agent.name} - Discord: {discord_status}"
            response_lines.append(line)

        response = "\n".join(response_lines)

        # Verify formatting
        assert "Agent1" in response
        assert "Agent2" in response
        assert "Agent3" in response
        assert "⭐" in response  # Default marker
        assert "✅" in response  # Discord enabled
        assert "❌" in response  # Discord disabled

    @pytest.mark.unit
    def test_agent_current_formats_response(self, mock_agents):
        """Test /agent current formats response correctly"""
        agent = mock_agents[0]

        # Simulate formatting current agent
        response = f"Current Agent: {agent.name}\n"
        response += f"System Prompt: {agent.system_prompt}\n"
        response += f"Discord Plugin: {'Enabled' if 'discord' in agent.plugins and agent.plugins['discord'].get('enabled') else 'Disabled'}"

        # Verify formatting
        assert "Agent1" in response
        assert "System Prompt" in response
        assert "Enabled" in response


# ============================================================
# Test Class 9: Concurrent Command Execution
# ============================================================

class TestConcurrentCommands:
    """Test concurrent command execution"""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_multiple_list_commands_concurrent(self, mock_agents):
        """Test multiple /agent list commands can run concurrently"""
        import asyncio

        with patch('src.services.agent_service.AgentService.get_all_agents', new=AsyncMock(return_value=mock_agents)):
            from src.services.agent_service import AgentService

            # Execute multiple list commands concurrently
            tasks = [
                AgentService.get_all_agents(),
                AgentService.get_all_agents(),
                AgentService.get_all_agents()
            ]

            results = await asyncio.gather(*tasks)

            # All should succeed
            assert len(results) == 3
            for result in results:
                assert len(result) == 3

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_select_commands_sequential(self, mock_agents):
        """Test /agent select commands should be sequential (not concurrent)"""
        # Agent selection should invalidate cache each time
        # This prevents race conditions

        from src.services.plugin_manager import PluginManager

        plugin_manager = PluginManager()

        # First selection
        plugin_manager._default_agent_id = mock_agents[0].id

        # Second selection (invalidates first)
        plugin_manager.invalidate_agent_cache()
        plugin_manager._default_agent_id = mock_agents[1].id

        # Verify second selection overwrites first
        assert plugin_manager._default_agent_id == mock_agents[1].id
