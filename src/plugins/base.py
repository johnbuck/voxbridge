"""
VoxBridge Plugin Base Class

Abstract base class for all VoxBridge plugins.
Plugins extend agent capabilities (Discord bots, n8n webhooks, Slack, etc.)

Design Philosophy:
- Lightweight: Minimal interface, easy to implement
- Extensible: Third parties can add plugins without modifying core
- Self-contained: Each plugin manages its own lifecycle
- Validated: Plugins validate their own configuration
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


class PluginBase(ABC):
    """
    Abstract base class for VoxBridge plugins.

    Plugins extend agent capabilities and can be enabled/disabled per agent.
    Each plugin type implements its own configuration validation and lifecycle management.

    Lifecycle:
    1. validate_config() - Validate plugin configuration from agent.plugins JSONB
    2. initialize() - Initialize plugin with validated config
    3. start() - Start plugin (connect to services, spawn bot instances, etc.)
    4. stop() - Stop plugin (disconnect, cleanup resources)

    Example Plugin Types:
    - Discord: Spawn Discord bot instance for agent
    - n8n: Configure webhook URL for LLM integration
    - Slack: Connect Slack bot to workspace
    - API: Provide REST API endpoints for agent
    - DataSource: Connect to databases or vector stores
    """

    plugin_type: str  # Must be set by subclass (e.g., "discord", "n8n", "slack")

    def __init__(self):
        """Initialize plugin instance (before configuration)"""
        self.agent = None
        self.config: Dict[str, Any] = {}
        self.running = False

    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and normalize plugin configuration.

        This method should:
        1. Check for required fields
        2. Apply defaults for optional fields
        3. Validate field types and values
        4. Return normalized config dict

        Args:
            config: Raw plugin config from agent.plugins[plugin_type]

        Returns:
            Dict[str, Any]: Validated and normalized config

        Raises:
            ValueError: If config is invalid

        Example:
            def validate_config(self, config):
                required = ['bot_token', 'workspace_id']
                if not all(k in config for k in required):
                    raise ValueError(f"Missing required fields: {required}")

                return {
                    'bot_token': config['bot_token'],
                    'workspace_id': config['workspace_id'],
                    'enabled': config.get('enabled', True),
                    'auto_connect': config.get('auto_connect', False)
                }
        """
        pass

    @abstractmethod
    async def initialize(self, agent: Any, config: Dict[str, Any]) -> None:
        """
        Initialize plugin with validated configuration.

        This method should:
        1. Store agent reference
        2. Store validated config
        3. Set up internal state
        4. Prepare resources (but don't start yet)

        Args:
            agent: Agent model instance (src.database.models.Agent)
            config: Validated config from validate_config()

        Example:
            async def initialize(self, agent, config):
                self.agent = agent
                self.config = config
                self.bot = create_bot_client(config['bot_token'])
        """
        pass

    @abstractmethod
    async def start(self) -> None:
        """
        Start the plugin.

        This method should:
        1. Connect to external services
        2. Spawn background tasks/threads
        3. Start listening for events
        4. Set self.running = True

        Called after initialize() when agent is activated.

        Example:
            async def start(self):
                await self.bot.login(self.config['bot_token'])
                asyncio.create_task(self.bot.connect())
                self.running = True
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the plugin and cleanup resources.

        This method should:
        1. Disconnect from external services
        2. Cancel background tasks
        3. Close connections
        4. Set self.running = False

        Called when agent is deactivated or on shutdown.

        Example:
            async def stop(self):
                if self.bot and not self.bot.is_closed():
                    await self.bot.close()
                self.running = False
        """
        pass

    async def on_message(self, session_id: str, text: str, metadata: Dict[str, Any]) -> None:
        """
        Handle incoming message event (optional hook).

        Called when a user sends a message to the agent.
        Plugins can use this to forward messages to external platforms.

        Args:
            session_id: Session UUID
            text: Message text
            metadata: Additional message metadata (user_id, channel_id, etc.)

        Example:
            async def on_message(self, session_id, text, metadata):
                # Forward to Slack channel
                await self.slack_client.chat_postMessage(
                    channel=metadata['channel_id'],
                    text=text
                )
        """
        pass

    async def on_response(self, session_id: str, text: str, metadata: Dict[str, Any]) -> None:
        """
        Handle agent response event (optional hook).

        Called when the agent generates a response.
        Plugins can use this to send responses to external platforms.

        Args:
            session_id: Session UUID
            text: Response text from agent
            metadata: Additional response metadata (latency, tokens, etc.)

        Example:
            async def on_response(self, session_id, text, metadata):
                # Send TTS response to Discord voice channel
                await self.play_tts_in_voice_channel(text)
        """
        pass

    def __repr__(self) -> str:
        """String representation of plugin"""
        return f"<{self.__class__.__name__}(type='{self.plugin_type}', running={self.running})>"
