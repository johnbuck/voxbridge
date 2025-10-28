"""
Plugin Manager Service

Manages plugin lifecycle for all agents in VoxBridge 2.0.

Responsibilities:
- Initialize plugins for agents
- Start/stop plugins
- Route events to plugins (messages, responses)
- Handle plugin errors gracefully

Design:
- One PluginManager instance per application
- Tracks active plugin instances per agent
- Plugins are initialized when agent is created/activated
- Plugins are stopped when agent is deactivated
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from uuid import UUID

from src.plugins import PluginRegistry, PluginBase
from src.plugins.encryption import PluginEncryption, PluginEncryptionError

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Service for managing plugin lifecycle across all agents.

    Usage:
        # Initialize manager
        manager = PluginManager()

        # Initialize plugins for an agent
        await manager.initialize_agent_plugins(agent)

        # Stop plugins for an agent
        await manager.stop_agent_plugins(agent.id)

        # Route message event to plugins
        await manager.dispatch_message(agent.id, session_id, text, metadata)
    """

    def __init__(self):
        """Initialize Plugin Manager"""
        # Active plugin instances: {agent_id: {plugin_type: plugin_instance}}
        self.active_plugins: Dict[UUID, Dict[str, PluginBase]] = {}

        # Track plugin errors for monitoring
        self.error_counts: Dict[str, int] = {}

        logger.info("🔌 PluginManager initialized")

    async def initialize_agent_plugins(self, agent: Any) -> Dict[str, bool]:
        """
        Initialize all enabled plugins for an agent.

        This method:
        1. Iterates through agent.plugins JSONB
        2. For each enabled plugin, validates config
        3. Initializes and starts the plugin
        4. Stores active plugin instance

        Args:
            agent: Agent model instance (src.database.models.Agent)

        Returns:
            Dict[str, bool]: Plugin type -> success status

        Example:
            agent.plugins = {
                "discord": {"enabled": True, "bot_token": "..."},
                "n8n": {"enabled": True, "webhook_url": "..."}
            }

            results = await manager.initialize_agent_plugins(agent)
            # {"discord": True, "n8n": True}
        """
        results = {}

        if not hasattr(agent, 'plugins') or not agent.plugins:
            logger.info(f"🔌 Agent {agent.name} has no plugins configured")
            return results

        logger.info(f"🔌 Initializing plugins for agent {agent.name} (id={agent.id})")

        for plugin_type, config in agent.plugins.items():
            # Decrypt sensitive fields in config
            try:
                decrypted_config = PluginEncryption.decrypt_config(plugin_type, config)
            except PluginEncryptionError as e:
                logger.error(
                    f"❌ Failed to decrypt {plugin_type} plugin config for agent {agent.name}: {e}"
                )
                results[plugin_type] = False
                continue

            # Skip disabled plugins
            if not decrypted_config.get('enabled', False):
                logger.info(f"🔌 Plugin {plugin_type} disabled for agent {agent.name}")
                results[plugin_type] = False
                continue

            try:
                # Get plugin class from registry
                plugin_class = PluginRegistry.get_plugin(plugin_type)

                if not plugin_class:
                    logger.warning(
                        f"⚠️ Plugin type '{plugin_type}' not registered for agent {agent.name}"
                    )
                    results[plugin_type] = False
                    continue

                # Create plugin instance
                plugin = plugin_class()

                # Validate configuration (using decrypted config)
                try:
                    validated_config = plugin.validate_config(decrypted_config)
                except Exception as e:
                    logger.error(
                        f"❌ Plugin {plugin_type} config validation failed for agent {agent.name}: {e}"
                    )
                    results[plugin_type] = False
                    continue

                # Initialize plugin
                await plugin.initialize(agent, validated_config)

                # Start plugin
                await plugin.start()

                # Store active plugin instance
                if agent.id not in self.active_plugins:
                    self.active_plugins[agent.id] = {}

                self.active_plugins[agent.id][plugin_type] = plugin

                logger.info(
                    f"✅ Plugin {plugin_type} started for agent {agent.name}"
                )
                results[plugin_type] = True

            except Exception as e:
                logger.error(
                    f"❌ Failed to initialize plugin {plugin_type} for agent {agent.name}: {e}",
                    exc_info=True
                )
                self.error_counts[plugin_type] = self.error_counts.get(plugin_type, 0) + 1
                results[plugin_type] = False

        return results

    async def stop_agent_plugins(self, agent_id: UUID) -> Dict[str, bool]:
        """
        Stop all plugins for an agent.

        Args:
            agent_id: Agent UUID

        Returns:
            Dict[str, bool]: Plugin type -> success status

        Example:
            results = await manager.stop_agent_plugins(agent_id)
            # {"discord": True, "n8n": True}
        """
        results = {}

        if agent_id not in self.active_plugins:
            logger.info(f"🔌 No active plugins for agent {agent_id}")
            return results

        logger.info(f"🔌 Stopping plugins for agent {agent_id}")

        for plugin_type, plugin in self.active_plugins[agent_id].items():
            try:
                await plugin.stop()
                logger.info(f"✅ Stopped plugin {plugin_type} for agent {agent_id}")
                results[plugin_type] = True

            except Exception as e:
                logger.error(
                    f"❌ Error stopping plugin {plugin_type} for agent {agent_id}: {e}",
                    exc_info=True
                )
                results[plugin_type] = False

        # Remove from active plugins
        del self.active_plugins[agent_id]

        return results

    async def restart_plugin(self, agent: Any, plugin_type: str) -> bool:
        """
        Restart a specific plugin for an agent.

        Args:
            agent: Agent model instance
            plugin_type: Plugin type to restart

        Returns:
            bool: Success status

        Example:
            success = await manager.restart_plugin(agent, "discord")
        """
        logger.info(f"🔌 Restarting plugin {plugin_type} for agent {agent.name}")

        # Stop existing plugin
        if agent.id in self.active_plugins and plugin_type in self.active_plugins[agent.id]:
            try:
                await self.active_plugins[agent.id][plugin_type].stop()
            except Exception as e:
                logger.error(f"❌ Error stopping plugin during restart: {e}")

        # Reinitialize plugin
        config = agent.plugins.get(plugin_type, {})
        results = await self.initialize_agent_plugins(agent)

        return results.get(plugin_type, False)

    async def dispatch_message(
        self,
        agent_id: UUID,
        session_id: str,
        text: str,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Dispatch incoming message event to all active plugins for an agent.

        Plugins can handle incoming messages (e.g., forward to external platforms).

        Args:
            agent_id: Agent UUID
            session_id: Session UUID
            text: Message text
            metadata: Additional message metadata

        Example:
            await manager.dispatch_message(
                agent_id=agent.id,
                session_id=session_id,
                text="Hello, agent!",
                metadata={'user_id': '12345', 'channel_id': '67890'}
            )
        """
        if agent_id not in self.active_plugins:
            return

        # Dispatch to all plugins (non-blocking)
        tasks = []
        for plugin_type, plugin in self.active_plugins[agent_id].items():
            task = asyncio.create_task(
                self._safe_dispatch_message(plugin, plugin_type, session_id, text, metadata)
            )
            tasks.append(task)

        # Wait for all dispatches to complete (with timeout)
        if tasks:
            await asyncio.wait(tasks, timeout=5.0)

    async def _safe_dispatch_message(
        self,
        plugin: PluginBase,
        plugin_type: str,
        session_id: str,
        text: str,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Safely dispatch message to plugin (catches exceptions).

        Args:
            plugin: Plugin instance
            plugin_type: Plugin type (for logging)
            session_id: Session UUID
            text: Message text
            metadata: Message metadata
        """
        try:
            await plugin.on_message(session_id, text, metadata)
        except Exception as e:
            logger.error(
                f"❌ Error dispatching message to plugin {plugin_type}: {e}",
                exc_info=True
            )

    async def dispatch_response(
        self,
        agent_id: UUID,
        session_id: str,
        text: str,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Dispatch agent response event to all active plugins for an agent.

        Plugins can handle agent responses (e.g., send to external platforms).

        Args:
            agent_id: Agent UUID
            session_id: Session UUID
            text: Response text from agent
            metadata: Additional response metadata

        Example:
            await manager.dispatch_response(
                agent_id=agent.id,
                session_id=session_id,
                text="Hello, user!",
                metadata={'latency_ms': 1234, 'tokens': 56}
            )
        """
        if agent_id not in self.active_plugins:
            return

        # Dispatch to all plugins (non-blocking)
        tasks = []
        for plugin_type, plugin in self.active_plugins[agent_id].items():
            task = asyncio.create_task(
                self._safe_dispatch_response(plugin, plugin_type, session_id, text, metadata)
            )
            tasks.append(task)

        # Wait for all dispatches to complete (with timeout)
        if tasks:
            await asyncio.wait(tasks, timeout=5.0)

    async def _safe_dispatch_response(
        self,
        plugin: PluginBase,
        plugin_type: str,
        session_id: str,
        text: str,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Safely dispatch response to plugin (catches exceptions).

        Args:
            plugin: Plugin instance
            plugin_type: Plugin type (for logging)
            session_id: Session UUID
            text: Response text
            metadata: Response metadata
        """
        try:
            await plugin.on_response(session_id, text, metadata)
        except Exception as e:
            logger.error(
                f"❌ Error dispatching response to plugin {plugin_type}: {e}",
                exc_info=True
            )

    def get_plugin(self, agent_id: UUID, plugin_type: str) -> Optional[PluginBase]:
        """
        Get active plugin instance for an agent.

        Args:
            agent_id: Agent UUID
            plugin_type: Plugin type

        Returns:
            Plugin instance or None if not active

        Example:
            discord_plugin = manager.get_plugin(agent.id, "discord")
            if discord_plugin:
                await discord_plugin.join_voice_channel(channel_id)
        """
        if agent_id in self.active_plugins:
            return self.active_plugins[agent_id].get(plugin_type)
        return None

    def get_agent_plugins(self, agent_id: UUID) -> Dict[str, PluginBase]:
        """
        Get all active plugins for an agent.

        Args:
            agent_id: Agent UUID

        Returns:
            Dict mapping plugin_type -> plugin_instance

        Example:
            plugins = manager.get_agent_plugins(agent.id)
            for plugin_type, plugin in plugins.items():
                print(f"{plugin_type}: {plugin.running}")
        """
        return self.active_plugins.get(agent_id, {})

    def get_all_active_plugins(self) -> Dict[UUID, Dict[str, PluginBase]]:
        """
        Get all active plugins across all agents.

        Returns:
            Dict mapping agent_id -> {plugin_type -> plugin_instance}

        Example:
            all_plugins = manager.get_all_active_plugins()
            for agent_id, plugins in all_plugins.items():
                print(f"Agent {agent_id}: {list(plugins.keys())}")
        """
        return dict(self.active_plugins)

    async def shutdown(self) -> None:
        """
        Shutdown all plugins for all agents.

        Called during application shutdown to gracefully stop all plugins.

        Example:
            # In application shutdown handler:
            await plugin_manager.shutdown()
        """
        logger.info("🔌 Shutting down all plugins...")

        agent_ids = list(self.active_plugins.keys())

        for agent_id in agent_ids:
            await self.stop_agent_plugins(agent_id)

        logger.info("✅ All plugins shut down")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get plugin manager statistics.

        Returns:
            Dict with statistics (active agents, plugins, errors)

        Example:
            stats = manager.get_stats()
            # {
            #     'active_agents': 3,
            #     'total_plugins': 5,
            #     'plugins_by_type': {'discord': 2, 'n8n': 3},
            #     'error_counts': {'discord': 1}
            # }
        """
        plugins_by_type: Dict[str, int] = {}

        for plugins in self.active_plugins.values():
            for plugin_type in plugins.keys():
                plugins_by_type[plugin_type] = plugins_by_type.get(plugin_type, 0) + 1

        return {
            'active_agents': len(self.active_plugins),
            'total_plugins': sum(len(plugins) for plugins in self.active_plugins.values()),
            'plugins_by_type': plugins_by_type,
            'error_counts': dict(self.error_counts),
        }


# Singleton instance (optional - can also be instantiated per-request)
_plugin_manager_instance: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """
    Get singleton PluginManager instance.

    This ensures plugin state is shared across the application.

    Returns:
        PluginManager: Shared service instance

    Example:
        from src.services.plugin_manager import get_plugin_manager

        manager = get_plugin_manager()
        await manager.initialize_agent_plugins(agent)
    """
    global _plugin_manager_instance

    if _plugin_manager_instance is None:
        _plugin_manager_instance = PluginManager()
        logger.info("🔌 Created singleton PluginManager instance")

    return _plugin_manager_instance
