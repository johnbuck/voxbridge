"""
Discord Bot Plugin

Integrates Discord voice bot functionality as a VoxBridge plugin.
Each agent can have its own Discord bot with unique token.

Design:
- One Discord bot instance per DiscordPlugin instance
- Bot connects to Discord with agent-specific token
- Handles voice connections and audio streaming
- Integrates with STT/LLM/TTS services

Configuration:
    {
        "enabled": true,
        "bot_token": "MTIzNDU2...",  # Encrypted in database
        "channels": ["channel_id_1"],  # Optional: whitelist specific channels
        "auto_join": true,             # Auto-join first available voice channel
        "command_prefix": "!"          # Command prefix (default: "!")
    }

Usage:
    # In agent.plugins JSONB column:
    {
        "discord": {
            "enabled": true,
            "bot_token": "your_discord_bot_token",
            "channels": [],
            "auto_join": false
        }
    }

    # Plugin manager will:
    # 1. Decrypt bot_token
    # 2. Initialize DiscordPlugin with agent and config
    # 3. Start the bot (connect to Discord)
    # 4. Handle voice connections and events

Note:
    This is a Phase 6.4 implementation demonstrating the plugin pattern.
    Full Discord functionality migration is planned for future phases.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from uuid import UUID

import discord
from discord.ext import commands

from src.plugins.base import PluginBase
from src.plugins.registry import plugin

logger = logging.getLogger(__name__)


@plugin("discord")
class DiscordPlugin(PluginBase):
    """
    Discord bot plugin for VoxBridge agents.

    Each instance manages one Discord bot with its own token and connections.
    Multiple agents can have separate Discord bots running concurrently.
    """

    plugin_type = "discord"

    def __init__(self):
        """Initialize Discord plugin"""
        super().__init__()

        # Discord bot instance (created in initialize)
        self.bot: Optional[commands.Bot] = None

        # Plugin configuration
        self.bot_token: Optional[str] = None
        self.channels: List[str] = []
        self.auto_join: bool = False
        self.command_prefix: str = "!"

        # Agent reference
        self.agent = None
        self.agent_id: Optional[UUID] = None
        self.agent_name: Optional[str] = None

        # Connection state
        self.voice_clients: Dict[int, discord.VoiceClient] = {}  # guild_id -> voice_client

        logger.info("🤖 DiscordPlugin instance created")

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate Discord plugin configuration.

        Args:
            config: Plugin configuration dict

        Returns:
            Validated configuration dict

        Raises:
            ValueError: If configuration is invalid
        """
        if not isinstance(config, dict):
            raise ValueError("Discord plugin config must be a dictionary")

        # Required fields
        if not config.get('enabled', False):
            return config  # Plugin disabled, no validation needed

        bot_token = config.get('bot_token')
        if not bot_token or not isinstance(bot_token, str):
            raise ValueError("Discord plugin requires 'bot_token' (string)")

        # Optional fields with defaults
        validated = {
            'enabled': True,
            'bot_token': bot_token,
            'channels': config.get('channels', []),
            'auto_join': config.get('auto_join', False),
            'command_prefix': config.get('command_prefix', '!'),
        }

        # Validate channels (list of strings)
        if not isinstance(validated['channels'], list):
            raise ValueError("Discord 'channels' must be a list of channel IDs")

        for channel in validated['channels']:
            if not isinstance(channel, str):
                raise ValueError(f"Discord channel ID must be string, got {type(channel)}")

        # Validate auto_join (boolean)
        if not isinstance(validated['auto_join'], bool):
            raise ValueError(f"Discord 'auto_join' must be boolean, got {type(validated['auto_join'])}")

        logger.info(f"✅ Validated Discord plugin config (channels: {len(validated['channels'])})")
        return validated

    async def initialize(self, agent: Any, config: Dict[str, Any]) -> None:
        """
        Initialize Discord bot with agent configuration.

        Args:
            agent: Agent model instance
            config: Validated plugin configuration
        """
        self.agent = agent
        self.agent_id = agent.id
        self.agent_name = agent.name

        # Extract configuration
        self.bot_token = config['bot_token']
        self.channels = config.get('channels', [])
        self.auto_join = config.get('auto_join', False)
        self.command_prefix = config.get('command_prefix', '!')

        # Create Discord bot instance
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        intents.members = True

        self.bot = commands.Bot(
            command_prefix=self.command_prefix,
            intents=intents,
            help_command=None  # Disable default help command
        )

        # Register event handlers
        self._register_event_handlers()

        logger.info(
            f"✅ Initialized Discord bot for agent '{self.agent_name}' "
            f"(channels: {len(self.channels)}, auto_join: {self.auto_join})"
        )

    def _register_event_handlers(self):
        """Register Discord event handlers for this bot instance"""

        @self.bot.event
        async def on_ready():
            """Called when bot successfully connects to Discord"""
            logger.info(
                f"🤖 Discord bot for agent '{self.agent_name}' connected: "
                f"{self.bot.user.name}#{self.bot.user.discriminator} (ID: {self.bot.user.id})"
            )

            # Log guild information
            for guild in self.bot.guilds:
                logger.info(f"  📍 Connected to guild: {guild.name} (ID: {guild.id})")

        @self.bot.event
        async def on_voice_state_update(member, before, after):
            """Handle voice state changes (user joins/leaves voice channel)"""
            # Skip if bot's own state changed
            if member.id == self.bot.user.id:
                return

            # User joined voice channel
            if before.channel is None and after.channel is not None:
                logger.info(
                    f"🎤 {member.name} joined voice channel '{after.channel.name}' "
                    f"in guild '{after.channel.guild.name}'"
                )

                # Auto-join if enabled and not already in a voice channel
                if self.auto_join and after.channel.guild.id not in self.voice_clients:
                    try:
                        voice_client = await after.channel.connect()
                        self.voice_clients[after.channel.guild.id] = voice_client
                        logger.info(
                            f"✅ Bot joined voice channel '{after.channel.name}' "
                            f"(agent: {self.agent_name})"
                        )
                    except Exception as e:
                        logger.error(
                            f"❌ Failed to join voice channel '{after.channel.name}': {e}",
                            exc_info=True
                        )

            # User left voice channel
            elif before.channel is not None and after.channel is None:
                logger.info(
                    f"👋 {member.name} left voice channel '{before.channel.name}' "
                    f"in guild '{before.channel.guild.name}'"
                )

                # Disconnect if bot is alone in channel
                guild_id = before.channel.guild.id
                if guild_id in self.voice_clients:
                    voice_client = self.voice_clients[guild_id]
                    if voice_client.channel == before.channel:
                        # Check if bot is alone
                        members_in_channel = [m for m in before.channel.members if not m.bot]
                        if len(members_in_channel) == 0:
                            await voice_client.disconnect()
                            del self.voice_clients[guild_id]
                            logger.info(
                                f"🚪 Bot left voice channel '{before.channel.name}' (no users remaining)"
                            )

        @self.bot.event
        async def on_command_error(ctx, error):
            """Handle command errors"""
            logger.error(f"❌ Command error in agent '{self.agent_name}': {error}", exc_info=error)

    async def start(self) -> None:
        """
        Start Discord bot (connect to Discord).

        This method spawns the bot as a background task and returns immediately.
        """
        if not self.bot:
            raise RuntimeError("Discord bot not initialized. Call initialize() first.")

        if not self.bot_token:
            raise RuntimeError("Discord bot token not configured")

        # Start bot in background task
        self._bot_task = asyncio.create_task(self._run_bot())

        logger.info(f"🚀 Starting Discord bot for agent '{self.agent_name}'")

        # Wait a moment for bot to connect
        await asyncio.sleep(2)

        if self.bot.is_ready():
            logger.info(f"✅ Discord bot for agent '{self.agent_name}' is ready")
            self.running = True
        else:
            logger.warning(f"⚠️  Discord bot for agent '{self.agent_name}' still connecting...")
            self.running = True  # Mark as running anyway

    async def _run_bot(self):
        """Run Discord bot (blocking task)"""
        try:
            await self.bot.start(self.bot_token)
        except Exception as e:
            logger.error(
                f"❌ Discord bot for agent '{self.agent_name}' crashed: {e}",
                exc_info=True
            )
            self.running = False

    async def stop(self) -> None:
        """
        Stop Discord bot (disconnect from Discord).

        Disconnects all voice clients and closes the bot connection.
        """
        if not self.bot:
            logger.warning(f"⚠️  Discord bot for agent '{self.agent_name}' not initialized")
            return

        logger.info(f"🛑 Stopping Discord bot for agent '{self.agent_name}'")

        # Disconnect from all voice channels
        for guild_id, voice_client in list(self.voice_clients.items()):
            try:
                await voice_client.disconnect()
                logger.info(f"🚪 Disconnected from voice channel in guild {guild_id}")
            except Exception as e:
                logger.error(f"❌ Error disconnecting from guild {guild_id}: {e}")

        self.voice_clients.clear()

        # Close bot connection
        try:
            await self.bot.close()
            logger.info(f"✅ Discord bot for agent '{self.agent_name}' stopped")
        except Exception as e:
            logger.error(f"❌ Error closing Discord bot: {e}", exc_info=True)

        # Cancel background task
        if hasattr(self, '_bot_task') and self._bot_task:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass

        self.running = False

    async def on_message(self, session_id: str, text: str, metadata: Dict[str, Any]) -> None:
        """
        Handle incoming message event.

        Note: Discord plugin doesn't use text messages for voice interactions.
        This hook is provided for completeness.

        Args:
            session_id: Session UUID
            text: Message text
            metadata: Message metadata
        """
        # Discord voice bot doesn't handle text messages
        # Voice audio is streamed directly to STT service
        pass

    async def on_response(self, session_id: str, text: str, metadata: Dict[str, Any]) -> None:
        """
        Handle agent response event (play TTS audio in Discord voice).

        Args:
            session_id: Session UUID
            text: Response text from agent
            metadata: Response metadata (may include audio_url, guild_id, channel_id)
        """
        # Extract voice channel information from metadata
        guild_id = metadata.get('guild_id')
        channel_id = metadata.get('channel_id')
        audio_url = metadata.get('audio_url')

        if not guild_id or guild_id not in self.voice_clients:
            logger.warning(
                f"⚠️  Cannot play response: not connected to voice channel in guild {guild_id}"
            )
            return

        voice_client = self.voice_clients[guild_id]

        # TODO: Implement TTS audio playback via Discord voice
        # This will be implemented in Phase 6.4.5 (full voice integration)
        logger.info(
            f"🔊 [TODO] Play TTS audio in Discord voice channel "
            f"(guild: {guild_id}, channel: {channel_id}, agent: {self.agent_name})"
        )

    def get_bot_info(self) -> Dict[str, Any]:
        """
        Get Discord bot information.

        Returns:
            Dict with bot status and connection info
        """
        if not self.bot:
            return {
                'connected': False,
                'ready': False,
                'guilds': 0,
                'voice_connections': 0,
            }

        return {
            'connected': self.bot.is_closed() == False,
            'ready': self.bot.is_ready(),
            'user': {
                'name': self.bot.user.name if self.bot.user else None,
                'id': self.bot.user.id if self.bot.user else None,
            } if self.bot.user else None,
            'guilds': len(self.bot.guilds),
            'guild_names': [g.name for g in self.bot.guilds],
            'voice_connections': len(self.voice_clients),
            'channels': self.channels,
            'auto_join': self.auto_join,
        }
