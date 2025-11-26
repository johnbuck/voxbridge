"""
Discord Bot Plugin - Phase 2: Complete Audio Pipeline Migration

Phase 2 Changes (2025-10-28):
- Migrated AudioReceiver class from discord_bot.py (lines 427-542)
- Migrated _handle_user_speaking() from on_user_speaking_start (lines 548-710)
- Migrated _on_transcript() callback (lines 650-710)
- Migrated _generate_response() from generate_and_play_response (lines 711-896)
- Migrated _play_tts() from synthesize_and_play_discord (lines 898-989)
- Completed _cleanup_session() implementation (lines 1006-1038)
- Updated on_voice_state_update() to register audio receiver
- Updated on_response() hook to play TTS

Integration Points (Phase 1):
- Uses ConversationService for session/conversation management
- Uses STTService for speech-to-text transcription
- Uses LLMService for AI response generation with hybrid routing
- Uses TTSService for text-to-speech synthesis
- Uses MetricsTracker for latency monitoring
- Uses agent configuration for LLM/TTS settings

Remaining Phases:
- Phase 3: API Endpoints (expose voice operations to HTTP API)
- Phase 4: Multi-Agent Support (agent selection, routing)
- Phase 5: Cleanup discord_bot.py (remove migrated code)

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
"""

import asyncio
import logging
import os
import statistics
import tempfile
import time
import uuid
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Dict, Any, Optional, List, AsyncGenerator

import discord
from discord.ext import commands, voice_recv
import httpx

from src.plugins.base import PluginBase
from src.plugins.registry import plugin

# Phase 1: Import service layer dependencies
from src.services.conversation_service import ConversationService
from src.services.stt_service import get_stt_service
from src.services.llm_service import get_llm_service, get_llm_service_for_agent, LLMConfig, ProviderType
from src.services.tts_service import get_tts_service

# Phase 5: Import sentence-level streaming services
from src.services.sentence_parser import SentenceParser
from src.services.tts_queue_manager import TTSQueueManager
from src.services.audio_playback_queue import AudioPlaybackQueue

# LLM exceptions for error handling
from src.llm import LLMError, LLMConnectionError, LLMTimeoutError

logger = logging.getLogger(__name__)

# Note: MetricsTracker is imported from src.api to ensure
# metrics are shared between the plugin and API endpoints

# ============================================================
# DISCORD PLUGIN
# ============================================================

@plugin("discord")
class DiscordPlugin(PluginBase):
    """
    Discord bot plugin for VoxBridge agents.

    Each instance manages one Discord bot with its own token and connections.
    Multiple agents can have separate Discord bots running concurrently.

    Phase 2 Integration (Complete Audio Pipeline):
    - AudioReceiver class for receiving Discord voice audio
    - _handle_user_speaking() for processing audio streams
    - _on_transcript() callback for STT transcriptions
    - _generate_response() for LLM response generation
    - _play_tts() for Discord voice playback
    - _cleanup_session() for session cleanup

    Phase 1 Integration (Service Layer Foundation):
    - Service layer dependencies initialized after agent binding
    - Session tracking infrastructure for user → session mapping
    - MetricsTracker for performance monitoring
    - Cleanup enhanced in stop() method
    """

    plugin_type = "discord"

    def __init__(self):
        """Initialize Discord plugin with Phase 1 service layer foundation"""
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
        self.agent_id: Optional[uuid.UUID] = None
        self.agent_name: Optional[str] = None

        # Connection state
        self.voice_clients: Dict[int, discord.VoiceClient] = {}  # guild_id -> voice_client

        # Phase 1: Service layer dependencies (initialized in initialize())
        self.conversation_service: Optional[ConversationService] = None
        self.stt_service = None  # STTService singleton
        self.llm_service = None  # LLMService singleton
        self.tts_service = None  # TTSService singleton

        # Phase 1: Session tracking infrastructure
        # Maps Discord user_id to session_id for multi-user support
        self.active_sessions: Dict[str, str] = {}  # user_id → session_id

        # Phase 1: Session timing metadata
        # Tracks per-session timing data for latency metrics
        self.session_timings: Dict[str, Dict[str, float]] = {}  # session_id → {key: timestamp}

        # Phase 1: Metrics tracker for performance monitoring
        # Use global metrics tracker shared with API server (lazy import to avoid circular dependency)
        from src.api import get_metrics_tracker
        self.metrics = get_metrics_tracker()

        # Phase 2: Audio receiver instances (one per voice client)
        self.audio_receivers: Dict[int, 'AudioReceiver'] = {}  # guild_id → AudioReceiver

        # Phase 5: Sentence-level streaming infrastructure
        # These will be initialized in initialize() after agent binding
        self.tts_queue_manager: Optional[TTSQueueManager] = None
        self.audio_playback_queues: Dict[int, AudioPlaybackQueue] = {}  # guild_id → AudioPlaybackQueue
        self.sentence_parsers: Dict[str, SentenceParser] = {}  # session_id → SentenceParser

        # Phase 6: Error handling infrastructure
        self.sentence_retry_counts: Dict[str, int] = {}  # task_id → retry_count
        self.fallback_triggered: Dict[str, bool] = {}  # session_id → fallback_triggered

        # Phase 6.X: Unified Conversation Threading
        # Maps Discord guild_id to web session_id for unified conversations
        # When set, Discord voice input will use the mapped session instead of creating new ones
        self.guild_session_mapping: Dict[int, str] = {}  # guild_id → session_id

        logger.info("🤖 DiscordPlugin instance created")

    # ============================================================
    # PHASE 2: AUDIO RECEIVER CLASS (Migrated from discord_bot.py)
    # ============================================================

    class AudioReceiver(voice_recv.AudioSink):
        """
        Custom audio sink to receive voice data from Discord and route to STTService.

        Phase 2: Nested class inside DiscordPlugin for per-plugin audio handling.

        Original source: discord_bot.py lines 427-542
        """

        def __init__(self, plugin: 'DiscordPlugin', voice_client: discord.VoiceClient):
            """
            Initialize audio receiver.

            Args:
                plugin: Parent DiscordPlugin instance
                voice_client: Discord voice client connection
            """
            super().__init__()
            self.plugin = plugin  # Reference to parent plugin (Phase 2 integration)
            self.vc = voice_client  # Use 'vc' to avoid conflict with parent class property
            self.user_buffers: Dict[str, asyncio.Queue] = {}  # user_id → audio chunk queue
            self.user_tasks: Dict[str, asyncio.Task] = {}    # user_id → processing task
            self.active_sessions: Dict[str, str] = {}  # user_id → session_id (for tracking, not blocking)

        def write(self, user, data: voice_recv.VoiceData):
            """
            Receive audio data from Discord.

            Phase 2: Uses plugin.bot.loop instead of global bot.loop

            Args:
                user: Discord user sending audio
                data: VoiceData object containing Opus packet
            """
            if not user:
                return

            user_id = str(user.id)
            username = user.name if hasattr(user, 'name') else str(user.id)

            # Extract Opus audio bytes from VoiceData object
            opus_packet = data.opus

            if not opus_packet:
                return

            # Create buffer for this user if not exists
            if user_id not in self.user_buffers:
                logger.info(f"📥 New audio stream from user {user_id} ({username})")
                # Bounded queue prevents memory issues - 100 packets @ 20ms = 2 seconds of audio
                max_queue_size = int(os.getenv('DISCORD_AUDIO_QUEUE_SIZE', '100'))
                self.user_buffers[user_id] = asyncio.Queue(maxsize=max_queue_size)

                # Create async generator for this user's audio stream
                async def audio_stream_generator(uid):
                    """Generate audio chunks from queue"""
                    queue = self.user_buffers[uid]
                    try:
                        while True:
                            chunk = await queue.get()
                            if chunk is None:  # Sentinel value to stop
                                break
                            yield chunk
                    except Exception as e:
                        logger.error(f"❌ Error in audio stream generator for {uid}: {e}")

                # Create wrapper coroutine that cleans up after completion
                async def handle_user_speaking_with_cleanup(u, uid, stream, vc):
                    """Wrapper that ensures cleanup after speaking ends"""
                    try:
                        await self.plugin._handle_user_speaking(u, stream, vc)
                    finally:
                        # Always cleanup after speaking completes (success or error)
                        session_id = self.active_sessions.get(uid, 'unknown')
                        logger.info(f"🔄 CLEANUP: Speaking task completed for {u.name} ({uid}, session={session_id[:8]}...)")
                        # Note: Don't delete buffers/tasks here - they'll be reused on next speak

                # Cancel existing task for this user if one is running
                if user_id in self.user_tasks:
                    existing_task = self.user_tasks[user_id]
                    if not existing_task.done():
                        logger.info(f"🔄 User {user.name} ({user_id}) speaking again - cancelling previous task")
                        existing_task.cancel()

                # Start new processing task for this user's audio
                logger.info(f"👤 NEW SPEAKER: {user.name} ({user_id}) - starting audio processing (concurrent users={len(self.user_tasks)})")
                stream_gen = audio_stream_generator(user_id)

                # Phase 2: Use plugin's bot loop and _handle_user_speaking method
                future = asyncio.run_coroutine_threadsafe(
                    handle_user_speaking_with_cleanup(user, user_id, stream_gen, self.vc),
                    self.plugin.bot.loop
                )
                self.user_tasks[user_id] = future

            # Add Opus packet to user's queue
            try:
                # Log audio receipt for debugging
                queue_size = self.user_buffers[user_id].qsize()
                if queue_size > 0 and queue_size % 50 == 0:  # Log every 50 packets (~1 second)
                    logger.debug(f"🎤 Audio streaming for {username} ({user_id}) - queue size: {queue_size}")

                self.user_buffers[user_id].put_nowait(opus_packet)
            except asyncio.QueueFull:
                logger.warning(f"⚠️ Audio buffer full for user {user_id}, dropping packet")

        def wants_opus(self) -> bool:
            """Return True to receive Opus packets (not decoded PCM)"""
            return True

        def cleanup_user(self, user_id: str):
            """
            Cleanup a specific user's audio stream.

            Args:
                user_id: Discord user ID to cleanup
            """
            logger.info(f"🧹 Cleaning up audio stream for user {user_id}")

            # Send sentinel to stop generator
            if user_id in self.user_buffers:
                try:
                    self.user_buffers[user_id].put_nowait(None)
                except:
                    pass
                del self.user_buffers[user_id]

            # Cancel task
            if user_id in self.user_tasks:
                task = self.user_tasks[user_id]
                if not task.done():
                    task.cancel()
                del self.user_tasks[user_id]

            # Remove from active sessions
            self.active_sessions.pop(user_id, None)

        def cleanup(self):
            """Cleanup audio sink (all users)"""
            logger.info("🧹 Cleaning up audio receiver")

            # Send sentinel values to stop all generators
            for user_id, queue in self.user_buffers.items():
                try:
                    queue.put_nowait(None)  # Sentinel to stop generator
                except:
                    pass

            # Cancel all user tasks
            for task in self.user_tasks.values():
                if not task.done():
                    task.cancel()

            # Clear all data
            self.user_buffers.clear()
            self.user_tasks.clear()
            self.active_sessions.clear()

    # ============================================================
    # CONFIGURATION & INITIALIZATION
    # ============================================================

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

        Phase 1 Enhancement: Initialize service layer dependencies after agent binding.

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

        # Phase 4 Batch 3: Register slash commands for agent management
        self._register_slash_commands()

        # Phase 1: Initialize service layer dependencies
        # These are singletons shared across plugins but each plugin maintains its own reference
        try:
            # ConversationService (per-plugin instance with MemoryService support)
            from src.services.factory import create_conversation_service
            self.conversation_service = await create_conversation_service()
            await self.conversation_service.start()

            # STT/LLM/TTS services
            self.stt_service = get_stt_service()

            # LLM service with database provider config (Phase 6.5.4)
            # Priority: database provider (agent.llm_provider_id) > env vars
            self.llm_service = await get_llm_service_for_agent(self.agent)

            self.tts_service = get_tts_service()

            # Phase 5: Initialize TTS queue manager if streaming enabled
            if self.tts_service.streaming_config.enabled:
                logger.info(
                    f"🌊 Initializing response streaming "
                    f"(strategy={self.tts_service.streaming_config.chunking_strategy}, "
                    f"concurrency={self.tts_service.streaming_config.max_concurrent_tts}, "
                    f"min_length={self.tts_service.streaming_config.min_chunk_length})"
                )

                self.tts_queue_manager = TTSQueueManager(
                    max_concurrent=self.tts_service.streaming_config.max_concurrent_tts,
                    tts_service=self.tts_service,
                    on_complete=self._on_tts_sentence_complete,
                    on_error=self._on_tts_sentence_error
                )
            else:
                logger.info("📝 Sentence-level streaming disabled for this agent")

            logger.info(
                f"✅ Initialized services for Discord plugin (agent: {self.agent_name})"
            )
        except Exception as e:
            logger.error(
                f"❌ Failed to initialize services for Discord plugin: {e}",
                exc_info=True
            )
            raise

        logger.info(
            f"✅ Initialized Discord bot for agent '{self.agent_name}' "
            f"(channels: {len(self.channels)}, auto_join: {self.auto_join})"
        )

    def _register_event_handlers(self):
        """Register Discord event handlers for this bot instance"""
        # Import plugin manager for agent routing
        from src.services.plugin_manager import get_plugin_manager

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

            # Sync slash commands with Discord
            try:
                await self.bot.tree.sync()
                logger.info("✅ Discord slash commands synced")
            except Exception as e:
                logger.error(f"❌ Failed to sync Discord commands: {e}", exc_info=True)

        @self.bot.event
        async def on_voice_state_update(member, before, after):
            """
            Handle voice state changes (user joins/leaves voice channel).

            Phase 2: Registers audio receiver when user joins voice channel.
            Phase 4 Batch 3: Routes voice events to default agent only.
            """
            # Skip if bot's own state changed
            if member.id == self.bot.user.id:
                return

            # Phase 4 Batch 3: Check if this plugin belongs to the default agent
            plugin_manager = get_plugin_manager()
            default_agent_id = await plugin_manager.get_default_agent_id()

            if not default_agent_id:
                logger.debug("⚠️  No default agent configured, skipping voice event")
                return

            # Only handle events for this plugin's agent if it's the default
            if default_agent_id != self.agent_id:
                logger.debug(
                    f"🚫 Ignoring voice event - this plugin is for agent {self.agent_name} "
                    f"but default agent is {default_agent_id}"
                )
                return

            # User joined voice channel
            if before.channel is None and after.channel is not None:
                logger.info(
                    f"🎤 {member.name} joined voice channel '{after.channel.name}' "
                    f"in guild '{after.channel.guild.name}' (agent: {self.agent_name})"
                )

                # Auto-join if enabled and not already in a voice channel
                if self.auto_join and after.channel.guild.id not in self.voice_clients:
                    try:
                        # Phase 2: Connect with VoiceRecvClient for audio receiving
                        voice_client = await after.channel.connect(cls=voice_recv.VoiceRecvClient)
                        self.voice_clients[after.channel.guild.id] = voice_client
                        logger.info(
                            f"✅ Bot joined voice channel '{after.channel.name}' "
                            f"(agent: {self.agent_name})"
                        )

                        # Phase 2: Register audio receiver for this voice client
                        receiver = self.AudioReceiver(self, voice_client)
                        voice_client.listen(receiver)
                        self.audio_receivers[after.channel.guild.id] = receiver
                        logger.info(f"🎤 Registered audio receiver for guild {after.channel.guild.id} (auto-join)")

                        # Phase 5: Create audio playback queue if streaming enabled
                        if self.tts_service.streaming_config.enabled and after.channel.guild.id not in self.audio_playback_queues:
                            playback_queue = AudioPlaybackQueue(
                                voice_client=voice_client,
                                on_complete=None,  # Optional callback
                                on_error=None  # Optional callback
                            )
                            await playback_queue.start()
                            self.audio_playback_queues[after.channel.guild.id] = playback_queue
                            logger.info(f"🎵 Created audio playback queue for guild {after.channel.guild.id} (auto-join)")

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
                            # Phase 2: Cleanup audio receiver before disconnecting
                            if guild_id in self.audio_receivers:
                                self.audio_receivers[guild_id].cleanup()
                                del self.audio_receivers[guild_id]

                            await voice_client.disconnect()
                            del self.voice_clients[guild_id]
                            logger.info(
                                f"🚪 Bot left voice channel '{before.channel.name}' (no users remaining)"
                            )

                # Phase 2: Clean up user's session
                user_id = str(member.id)
                if user_id in self.active_sessions:
                    session_id = self.active_sessions[user_id]
                    await self._cleanup_session(user_id, session_id)

        @self.bot.event
        async def on_command_error(ctx, error):
            """Handle command errors"""
            logger.error(f"❌ Command error in agent '{self.agent_name}': {error}", exc_info=error)

    def _register_slash_commands(self):
        """
        Register Discord slash commands for agent management.

        Phase 4 Batch 3: Agent routing and selection commands
        """
        from discord import app_commands
        from src.services.agent_service import AgentService
        from src.services.plugin_manager import get_plugin_manager

        @self.bot.tree.command(name="agent", description="Manage AI agent selection")
        @app_commands.describe(
            action="Action: list (show agents), current (show default), select (switch agent)",
            name="Agent name (required for 'select' action)"
        )
        async def agent_command(
            interaction: discord.Interaction,
            action: str,
            name: str = None
        ):
            """
            Agent management slash command.

            Usage:
                /agent list - Show all available agents
                /agent current - Show current default agent
                /agent select <name> - Switch to a different agent
            """
            try:
                if action == "list":
                    # List all available agents
                    agents = await AgentService.get_all_agents()

                    if not agents:
                        await interaction.response.send_message("❌ No agents available")
                        return

                    # Build agent list message
                    agent_list = "🤖 **Available Agents:**\n\n"
                    for agent in agents:
                        # Mark default agent with star
                        is_default = "⭐ " if agent.is_default else ""
                        # Mark agents with Discord plugin enabled
                        has_discord = "🔌 " if agent.plugins.get('discord', {}).get('enabled') else ""

                        agent_list += f"{is_default}{has_discord}**{agent.name}**\n"
                        # Show truncated system prompt
                        prompt_preview = agent.system_prompt[:100].replace('\n', ' ')
                        agent_list += f"  _{prompt_preview}..._\n"
                        agent_list += f"  Provider: {agent.llm_provider} | Model: {agent.llm_model}\n\n"

                    agent_list += "\n💡 **Tips:**\n"
                    agent_list += "• ⭐ = Default agent\n"
                    agent_list += "• 🔌 = Discord plugin enabled\n"
                    agent_list += "• Use `/agent select <name>` to switch agents\n"

                    await interaction.response.send_message(agent_list)
                    logger.info(f"📋 Listed {len(agents)} agents for user {interaction.user.name}")

                elif action == "select":
                    if not name:
                        await interaction.response.send_message("❌ Please provide an agent name: `/agent select <name>`")
                        return

                    # Find agent by name (case-insensitive)
                    agent = await AgentService.get_agent_by_name(name)

                    if not agent:
                        # Try case-insensitive search
                        all_agents = await AgentService.get_all_agents()
                        for a in all_agents:
                            if a.name.lower() == name.lower():
                                agent = a
                                break

                    if not agent:
                        await interaction.response.send_message(
                            f"❌ Agent '{name}' not found. Use `/agent list` to see available agents."
                        )
                        return

                    # Check if agent has Discord plugin enabled
                    if not agent.plugins.get('discord', {}).get('enabled'):
                        await interaction.response.send_message(
                            f"❌ Agent '{agent.name}' does not have Discord plugin enabled.\n"
                            f"Please enable the Discord plugin for this agent first."
                        )
                        return

                    # Set as default agent
                    updated_agent = await AgentService.set_default_agent(agent.id)

                    if not updated_agent:
                        await interaction.response.send_message(f"❌ Failed to switch to agent '{name}'")
                        return

                    # Invalidate plugin manager cache
                    plugin_manager = get_plugin_manager()
                    plugin_manager.invalidate_agent_cache()

                    # Build success message
                    prompt_preview = updated_agent.system_prompt[:150].replace('\n', ' ')
                    success_msg = (
                        f"✅ **Switched to agent: {updated_agent.name}**\n\n"
                        f"_{prompt_preview}..._\n\n"
                        f"**Configuration:**\n"
                        f"• Provider: {updated_agent.llm_provider}\n"
                        f"• Model: {updated_agent.llm_model}\n"
                        f"• Temperature: {updated_agent.temperature}\n"
                        f"• TTS Voice: {updated_agent.tts_voice or 'default'}\n"
                    )

                    await interaction.response.send_message(success_msg)
                    logger.info(
                        f"🔄 Agent switched to '{updated_agent.name}' by user {interaction.user.name} "
                        f"(ID: {interaction.user.id})"
                    )

                elif action == "current":
                    # Show current default agent
                    default_agent = await AgentService.get_default_agent()

                    if not default_agent:
                        await interaction.response.send_message(
                            "❌ No default agent set. Use `/agent select <name>` to set one."
                        )
                        return

                    # Build current agent message
                    prompt_preview = default_agent.system_prompt[:150].replace('\n', ' ')
                    current_msg = (
                        f"🤖 **Current Default Agent: {default_agent.name}**\n\n"
                        f"_{prompt_preview}..._\n\n"
                        f"**Configuration:**\n"
                        f"• Provider: {default_agent.llm_provider}\n"
                        f"• Model: {default_agent.llm_model}\n"
                        f"• Temperature: {default_agent.temperature}\n"
                        f"• TTS Voice: {default_agent.tts_voice or 'default'}\n\n"
                        f"💡 Use `/agent list` to see all agents or `/agent select <name>` to switch."
                    )

                    await interaction.response.send_message(current_msg)
                    logger.info(f"ℹ️  Showed current agent to user {interaction.user.name}")

                else:
                    await interaction.response.send_message(
                        "❌ Invalid action. Use:\n"
                        "• `/agent list` - Show all agents\n"
                        "• `/agent current` - Show default agent\n"
                        "• `/agent select <name>` - Switch to agent"
                    )

            except Exception as e:
                logger.error(f"❌ Error in agent command: {e}", exc_info=True)
                error_msg = f"❌ Error executing command: {str(e)}"
                try:
                    await interaction.response.send_message(error_msg)
                except:
                    # Interaction already responded, try followup
                    await interaction.followup.send(error_msg)

    # ============================================================
    # LIFECYCLE METHODS
    # ============================================================

    async def start(self) -> None:
        """
        Start Discord bot (connect to Discord).

        This method spawns the bot as a background task and returns immediately.
        """
        if not self.bot:
            raise RuntimeError("Discord bot not initialized. Call initialize() first.")

        if not self.bot_token:
            raise RuntimeError("Discord bot token not configured")

        # Phase 5: Start TTS queue manager if streaming enabled
        if self.tts_queue_manager:
            await self.tts_queue_manager.start()
            logger.info(f"🌊 Started TTS queue manager for agent '{self.agent_name}'")

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

        Phase 2 Enhancement: Clean up audio receivers and active sessions.
        """
        if not self.bot:
            logger.warning(f"⚠️  Discord bot for agent '{self.agent_name}' not initialized")
            return

        logger.info(f"🛑 Stopping Discord bot for agent '{self.agent_name}'")

        # Phase 2: Clean up audio receivers
        for guild_id, receiver in list(self.audio_receivers.items()):
            try:
                receiver.cleanup()
                logger.info(f"✅ Cleaned up audio receiver for guild {guild_id}")
            except Exception as e:
                logger.error(f"❌ Error cleaning up audio receiver for guild {guild_id}: {e}")

        self.audio_receivers.clear()

        # Phase 2: Clean up active sessions before disconnecting voice
        for user_id in list(self.active_sessions.keys()):
            session_id = self.active_sessions.get(user_id)
            if session_id:
                await self._cleanup_session(user_id, session_id)

        # Phase 5: Stop TTS queue manager and audio playback queues
        if self.tts_queue_manager:
            try:
                await self.tts_queue_manager.stop()
                logger.info(f"✅ TTS queue manager stopped for agent '{self.agent_name}'")
            except Exception as e:
                logger.error(f"❌ Error stopping TTS queue manager: {e}")

        for guild_id, playback_queue in list(self.audio_playback_queues.items()):
            try:
                await playback_queue.stop()
                logger.info(f"✅ Audio playback queue stopped for guild {guild_id}")
            except Exception as e:
                logger.error(f"❌ Error stopping audio playback queue for guild {guild_id}: {e}")

        self.audio_playback_queues.clear()
        self.sentence_parsers.clear()

        # Phase 6: Clear error handling state
        self.sentence_retry_counts.clear()
        self.fallback_triggered.clear()

        # Disconnect from all voice channels
        for guild_id, voice_client in list(self.voice_clients.items()):
            try:
                await voice_client.disconnect()
                logger.info(f"🚪 Disconnected from voice channel in guild {guild_id}")
            except Exception as e:
                logger.error(f"❌ Error disconnecting from guild {guild_id}: {e}")

        self.voice_clients.clear()

        # Phase 1: Stop ConversationService (if per-plugin instance)
        if self.conversation_service:
            try:
                await self.conversation_service.stop()
                logger.info(f"✅ ConversationService stopped for agent '{self.agent_name}'")
            except Exception as e:
                logger.error(f"❌ Error stopping ConversationService: {e}")

        # Note: STT/LLM/TTS services are singletons, so we don't close them here
        # They will be closed during application shutdown

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

    # ============================================================
    # PLUGIN HOOKS
    # ============================================================

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

        Phase 2: Implements TTS playback via Discord voice.

        Args:
            session_id: Session UUID
            text: Response text from agent
            metadata: Response metadata (may include guild_id, channel_id)
        """
        # Extract voice channel information from metadata
        guild_id = metadata.get('guild_id')

        if not guild_id or guild_id not in self.voice_clients:
            logger.warning(
                f"⚠️  Cannot play response: not connected to voice channel in guild {guild_id}"
            )
            return

        voice_client = self.voice_clients[guild_id]

        # Phase 2: Play TTS audio via Discord voice
        await self._play_tts(text, voice_client, session_id)

    # ============================================================
    # PHASE 2: AUDIO PIPELINE METHODS (Migrated from discord_bot.py)
    # ============================================================

    async def _handle_user_speaking(
        self,
        user: discord.User,
        audio_stream: AsyncGenerator,
        voice_client: discord.VoiceClient
    ) -> None:
        """
        Handle when a user starts speaking in Discord voice.

        Phase 2: Full audio receiving pipeline
        - Creates session via ConversationService (Phase 1 integration)
        - Connects to STT service (Phase 1 integration)
        - Streams audio to WhisperX
        - Handles silence detection

        Original source: discord_bot.py on_user_speaking_start (lines 548-710)

        Args:
            user: Discord user who is speaking
            audio_stream: Async generator yielding audio chunks
            voice_client: Voice client connection
        """
        user_id = str(user.id)
        username = user.name

        logger.info(f"🎤 {username} ({user_id}) started speaking")

        try:
            # Record pipeline start time
            t_start = time.time()

            # Phase 6.X: Check if this guild is mapped to an existing web session
            # Find guild_id from voice_client
            guild_id = voice_client.guild.id if voice_client and voice_client.guild else None
            mapped_session_id = self.guild_session_mapping.get(guild_id) if guild_id else None

            # Phase 7: Handle user interruption if AI is currently speaking
            if self.tts_service.streaming_config.enabled and guild_id:
                await self._handle_interruption(guild_id, user_id, username)

            if mapped_session_id:
                # Use the mapped session (unified conversation threading)
                session_id = mapped_session_id
                logger.info(
                    f"🔗 Using mapped session {session_id[:8]}... for Discord user {username} "
                    f"(guild {guild_id}, unified conversation)"
                )
            else:
                # Create new session (legacy behavior)
                session_id = str(uuid.uuid4())
                logger.info(f"📝 Created new session {session_id[:8]}... for Discord user {username}")

            self.active_sessions[user_id] = session_id

            # Track session in AudioReceiver for logging (Phase 2 Tests)
            for guild_id, vc in self.voice_clients.items():
                if hasattr(vc, 'recv') and vc.recv:
                    receiver = vc.recv
                    if hasattr(receiver, 'active_sessions'):
                        receiver.active_sessions[user_id] = session_id

            # Initialize session timing tracker (Phase 1 integration)
            self.session_timings[session_id] = {
                't_start': t_start,
                't_utterance_start': t_start,  # Start of current utterance (resets for each turn)
                't_whisper_connected': None,
                't_first_partial': None,
                't_transcription_complete': None
            }

            # TODO Phase 2 Tests: Broadcast speaker_started event via WebSocket
            # await broadcast_speaker_started(user_id, username)

            # Phase 1 integration: Create session in database via ConversationService
            # If using mapped session, this will load existing session from DB
            # If new session, this will create it with the specified session_id
            session = await self.conversation_service.get_or_create_session(
                session_id=session_id,
                user_id=user_id,
                agent_id=str(self.agent_id),
                channel_type="discord",
                user_name=username,
                title=f"Discord conversation with {username}"
            )

            # Phase 1 integration: Connect STT service for this session
            t_before_whisper = time.time()
            whisper_url = os.getenv('WHISPER_SERVER_URL', 'ws://whisperx:4901')
            success = await self.stt_service.connect(session_id, whisper_url)

            if not success:
                logger.error(f"❌ Failed to connect STT for session {session_id[:8]}...")
                await self._cleanup_session(user_id, session_id)
                return

            t_after_whisper = time.time()
            whisper_latency = t_after_whisper - t_before_whisper
            self.session_timings[session_id]['t_whisper_connected'] = t_after_whisper
            logger.info(f"⏱️ LATENCY [speech start → WhisperX connected]: {whisper_latency:.3f}s")
            self.metrics.record_whisper_connection_latency(whisper_latency)

            # Phase 2: Register STT callback (routes to _on_transcript)
            await self.stt_service.register_callback(
                session_id=session_id,
                callback=lambda text, is_final, metadata: self._on_transcript(
                    session_id, user_id, username, text, is_final, metadata
                )
            )

            # Silence detection configuration
            silence_threshold_ms = int(os.getenv('SILENCE_THRESHOLD_MS', '600'))  # 600ms default

            # Per-utterance timeout (configurable per-agent via database, fallback to ENV, then default)
            max_utterance_time_ms = (
                self.agent.max_utterance_time_ms
                if self.agent.max_utterance_time_ms is not None
                else int(os.getenv('MAX_UTTERANCE_TIME_MS', '120000'))
            )  # 2 minutes default per speaking turn

            # Track audio timing for silence detection
            last_audio_time = time.time()
            last_finalization_time = None  # Track when last utterance was finalized
            silence_detection_task = None
            finalized = False

            async def check_silence():
                """Background task to detect silence and trigger finalization with per-utterance timeout"""
                nonlocal finalized, last_finalization_time
                check_interval = 0.1  # Check every 100ms
                iteration_count = 0

                logger.info(f"🔍 [SILENCE] Starting continuous silence detection for {username} (session={session_id[:8]}...)")
                logger.info(f"🔍 [SILENCE] silence_threshold={silence_threshold_ms}ms, max_utterance={max_utterance_time_ms}ms")

                while True:  # Continuous monitoring - runs for entire voice session
                    await asyncio.sleep(check_interval)
                    iteration_count += 1

                    # Calculate elapsed time since last audio
                    elapsed_ms = (time.time() - last_audio_time) * 1000

                    # Calculate per-utterance duration (resets after each finalization)
                    if last_finalization_time is not None:
                        utterance_duration_ms = (time.time() - last_finalization_time) * 1000
                    else:
                        utterance_duration_ms = (time.time() - t_start) * 1000

                    # Log every 10 iterations (1 second)
                    if iteration_count % 10 == 0:
                        logger.debug(f"🔍 [SILENCE] Iter {iteration_count}: elapsed={elapsed_ms:.0f}ms, utterance={utterance_duration_ms:.0f}ms, finalized={finalized}")

                    # Check if new audio arrived after finalization (auto-restart detection)
                    if finalized and elapsed_ms < silence_threshold_ms:
                        logger.info(f"🔄 [SILENCE] New audio after finalization! Starting new utterance...")
                        finalized = False
                        last_finalization_time = time.time()  # Reset utterance timer
                        iteration_count = 0

                        # Reset per-turn timing markers for accurate latency tracking
                        if session_id in self.session_timings:
                            t_now = time.time()
                            self.session_timings[session_id]['t_start'] = t_now
                            self.session_timings[session_id]['t_utterance_start'] = t_now  # Track start of THIS utterance
                            self.session_timings[session_id]['t_first_partial'] = None
                            self.session_timings[session_id]['t_transcription_complete'] = None
                            logger.debug(f"🔄 [METRICS] Reset timing markers for new utterance (session={session_id[:8]}...)")

                    # Check for silence threshold (only if not already finalized)
                    if not finalized and elapsed_ms >= silence_threshold_ms:
                        logger.info(f"🔇 [SILENCE] Silence detected ({elapsed_ms:.0f}ms) - finalizing utterance")
                        self.metrics.record_silence_detection_latency(elapsed_ms)

                        # Finalize transcript
                        finalized = True
                        last_finalization_time = time.time()  # Mark finalization time
                        success = await self.stt_service.finalize_transcript(session_id)

                        if success:
                            logger.info(f"✅ [SILENCE] Utterance finalized (duration: {utterance_duration_ms:.0f}ms)")
                        else:
                            logger.warning(f"⚠️ [SILENCE] Finalization failed")

                        # Continue monitoring for next utterance (don't break!)

                    # Check for max utterance time (safety limit per speaking turn)
                    if not finalized and utterance_duration_ms >= max_utterance_time_ms:
                        logger.warning(f"⏰ [SILENCE] Max utterance time reached ({utterance_duration_ms:.0f}ms) - force finalizing")

                        # Force finalization
                        finalized = True
                        last_finalization_time = time.time()  # Reset for next utterance
                        success = await self.stt_service.finalize_transcript(session_id)

                        if success:
                            logger.info(f"✅ [SILENCE] Long utterance force-finalized")
                        else:
                            logger.warning(f"⚠️ [SILENCE] Force-finalization failed")

                        # Continue monitoring for next utterance (don't break!)

                logger.info(f"🔍 [SILENCE] Silence detection task ending for {username} (finalized={finalized})")

            # Start silence detection task
            logger.info(f"🚀 [STREAM] Starting silence detection task for {username}")
            silence_detection_task = asyncio.create_task(check_silence())

            # Stream audio to STT with silence tracking
            chunk_count = 0
            logger.info(f"🚀 [STREAM] Starting audio stream loop for {username} (session={session_id[:8]}...)")
            try:
                async for audio_chunk in audio_stream:
                    chunk_count += 1
                    # Update last audio timestamp
                    last_audio_time = time.time()

                    # Log every 50 chunks
                    if chunk_count % 50 == 0:
                        logger.info(f"🎤 [STREAM] Chunk #{chunk_count} received, size={len(audio_chunk)} bytes, last_audio_time updated")

                    # Phase 1 integration: Send audio to STTService
                    await self.stt_service.send_audio(session_id, audio_chunk)

                logger.info(f"🔚 [STREAM] Audio stream loop exited naturally for {username}, total chunks={chunk_count}, finalized={finalized}")
            finally:
                logger.info(f"🔚 [STREAM] Entering finally block for {username} (finalized={finalized})")

                # Ensure finalization happens even if stream ends abruptly
                if not finalized:
                    logger.info(f"🔚 [STREAM] Stream ended but not finalized - calling finalize_transcript...")
                    await self.stt_service.finalize_transcript(session_id)
                    finalized = True
                    logger.info(f"🔚 [STREAM] Finalization complete via finally block")
                else:
                    logger.info(f"🔚 [STREAM] Stream ended and already finalized - skipping finalize call")

                # Cancel silence detection task
                logger.info(f"🔚 [STREAM] Cancelling silence detection task (done={silence_detection_task.done() if silence_detection_task else 'None'})")
                if silence_detection_task and not silence_detection_task.done():
                    silence_detection_task.cancel()
                    try:
                        await silence_detection_task
                        logger.info(f"🔚 [STREAM] Silence detection task cancelled successfully")
                    except asyncio.CancelledError:
                        logger.info(f"🔚 [STREAM] Silence detection task cancel acknowledged")
                        pass
                else:
                    logger.info(f"🔚 [STREAM] Silence detection task already done or None")

                logger.info(f"🔚 [STREAM] Finally block complete for {username}")

        except Exception as e:
            logger.error(f"❌ Error in _handle_user_speaking for {username}: {e}", exc_info=True)
            # Cleanup on error
            if user_id in self.active_sessions:
                session_id = self.active_sessions[user_id]
                await self._cleanup_session(user_id, session_id)

    async def _on_transcript(
        self,
        session_id: str,
        user_id: str,
        username: str,
        text: str,
        is_final: bool,
        metadata: Dict
    ) -> None:
        """
        Callback when STT service produces a transcript.

        Phase 2: Complete transcript handling
        - Tracks latency metrics (Phase 1 integration)
        - Saves user message to database (Phase 1 integration)
        - Triggers LLM response generation

        Original source: discord_bot.py on_stt_transcript (embedded in on_user_speaking_start, lines ~650-710)

        Args:
            session_id: Session UUID
            user_id: Discord user ID
            username: Discord username
            text: Transcribed text
            is_final: Whether this is a final transcript
            metadata: STT metadata (confidence, etc.)
        """
        if not is_final:
            # Partial transcript - log and broadcast
            logger.info(f"🔄 Partial (session={session_id[:8]}...): \"{text}\" (user={username})")

            # Record first partial latency (Phase 1 integration)
            if session_id in self.session_timings:
                timings = self.session_timings[session_id]
                if timings['t_first_partial'] is None and timings['t_utterance_start']:
                    t_now = time.time()
                    timings['t_first_partial'] = t_now
                    latency = t_now - timings['t_utterance_start']
                    logger.info(f"⏱️ LATENCY [utterance start → first partial]: {latency:.3f}s")
                    self.metrics.record_first_partial_transcript_latency(latency)

            # Broadcast partial transcript via WebSocket (Phase 2 Tests)
            try:
                # Lazy import to avoid circular dependency
                from src.api import get_ws_manager
                ws_manager = get_ws_manager()
                logger.debug(f"📡 WebSocket: Broadcasting partial transcript to frontend (user={username}, text_len={len(text)})")
                await ws_manager.broadcast({
                    "event": "partial_transcript",
                    "data": {
                        "userId": user_id,
                        "username": username,
                        "text": text,
                        "sessionId": session_id,
                        "timestamp": datetime.now().isoformat()
                    }
                })
            except Exception as e:
                logger.error(f"❌ Failed to broadcast partial transcript: {e}")
            return

        # Final transcript
        logger.info(f"✅ FINAL TRANSCRIPT (session={session_id[:8]}...): \"{text}\" (user={username}, user_id={user_id})")
        logger.info(f"📊 Session info: active_sessions={list(self.active_sessions.keys())}, current_user={user_id}")

        # Record transcription duration (Phase 1 integration)
        if session_id in self.session_timings:
            timings = self.session_timings[session_id]
            t_now = time.time()
            timings['t_transcription_complete'] = t_now

            if timings['t_first_partial']:
                duration = t_now - timings['t_first_partial']
                logger.info(f"⏱️ LATENCY [first partial → transcription complete]: {duration:.3f}s")
                self.metrics.record_transcription_duration(duration)

        # Broadcast final transcript via WebSocket (Phase 2 Tests)
        try:
            # Lazy import to avoid circular dependency
            from src.api import get_ws_manager
            ws_manager = get_ws_manager()
            logger.info(f"📡 WebSocket: Broadcasting final transcript to frontend (user={username}, text=\"{text[:50]}...\")")
            await ws_manager.broadcast({
                "event": "final_transcript",
                "data": {
                    "userId": user_id,
                    "username": username,
                    "text": text,
                    "sessionId": session_id,
                    "timestamp": datetime.now().isoformat()
                }
            })
        except Exception as e:
            logger.error(f"❌ Failed to broadcast final transcript: {e}")

        self.metrics.record_transcript()

        # Phase 1 integration: Add user message to conversation
        await self.conversation_service.add_message(
            session_id=session_id,
            role='user',
            content=text,
            metadata={'stt_confidence': metadata.get('confidence')}
        )

        # Phase 2: Generate LLM response and play TTS
        # Extract guild_id from voice_client for TTS playback
        guild_id = None
        for gid, vc in self.voice_clients.items():
            guild_id = gid
            break  # Get first (only) voice client for this user

        await self._generate_response(session_id, user_id, username, text, guild_id)

    # ============================================================
    # PHASE 5: SENTENCE-LEVEL STREAMING CALLBACKS
    # ============================================================

    async def _on_tts_sentence_complete(self, audio_bytes: bytes, metadata: Dict[str, Any]) -> None:
        """
        Callback when TTS synthesis completes for a sentence.

        Enqueues audio to AudioPlaybackQueue for sequential playback.

        Args:
            audio_bytes: Synthesized audio (WAV format)
            metadata: Sentence metadata (task_id, sentence, session_id, latency, etc.)
        """
        session_id = metadata.get('session_id')
        sentence = metadata.get('sentence', '')
        latency = metadata.get('latency', 0)

        logger.info(
            f"✅ [STREAMING] TTS complete for sentence "
            f"(session={session_id[:8] if session_id else 'unknown'}..., "
            f"sentence_len={len(sentence)} chars, latency={latency:.2f}s)"
        )

        # Phase 8: Record sentence TTS latency
        self.metrics.record_sentence_tts(latency, success=True)

        # Find guild_id for this session
        guild_id = metadata.get('guild_id')

        if not guild_id or guild_id not in self.audio_playback_queues:
            logger.warning(
                f"⚠️ [STREAMING] No audio playback queue for guild {guild_id}, "
                f"cannot enqueue audio"
            )
            return

        # Track timestamp for audio queue wait latency
        t_before_enqueue = time.time()

        # Enqueue audio to playback queue
        playback_queue = self.audio_playback_queues[guild_id]
        await playback_queue.enqueue_audio(audio_bytes, metadata)

        # Phase 8: Calculate and record sentence-to-audio latency
        t_sentence_detected = metadata.get('t_sentence_detected')
        if t_sentence_detected:
            sentence_to_audio_latency = time.time() - t_sentence_detected
            self.metrics.record_sentence_to_audio(sentence_to_audio_latency)
            logger.debug(
                f"⏱️  [STREAMING METRICS] Sentence-to-audio: {sentence_to_audio_latency:.3f}s "
                f"(sentence detected → audio enqueued)"
            )

    async def _on_tts_sentence_error(self, sentence: str, error: Exception, metadata: Dict[str, Any]) -> None:
        """
        Callback when TTS synthesis fails for a sentence.

        Implements error handling strategy from agent config.

        Phase 6: Error handling strategies:
        - skip: Log error, continue with next sentence (audio will have gaps)
        - retry: Retry failed sentence up to 2 times before skipping
        - fallback: On first failure, cancel remaining sentences and use legacy TTS

        Args:
            sentence: Sentence text that failed
            error: Exception that occurred
            metadata: Sentence metadata (task_id, session_id, etc.)
        """
        session_id = metadata.get('session_id')
        task_id = metadata.get('task_id')
        guild_id = metadata.get('guild_id')
        strategy = self.tts_service.streaming_config.error_strategy

        logger.error(
            f"❌ [STREAMING] TTS error for sentence "
            f"(session={session_id[:8] if session_id else 'unknown'}..., "
            f"strategy={strategy}, task={task_id[:8] if task_id else 'unknown'}..., "
            f"sentence=\"{sentence[:50]}...\", error={error})"
        )

        # Phase 8: Record error metric and TTS failure
        self.metrics.record_error()
        self.metrics.record_sentence_tts(0, success=False)

        # Phase 6: Implement error handling strategies
        if strategy == 'skip':
            # Skip failed sentence, continue with next
            logger.warning(
                f"⏭️  [SKIP] Skipping failed sentence (task={task_id[:8] if task_id else 'unknown'}...) - "
                f"audio may have gaps"
            )
            # No action needed - just continue with next sentence

        elif strategy == 'retry':
            # Retry failed sentence up to 2 times
            retry_count = self.sentence_retry_counts.get(task_id, 0)
            max_retries = 2

            if retry_count < max_retries:
                # Retry the sentence
                retry_count += 1
                self.sentence_retry_counts[task_id] = retry_count

                # Phase 8: Record retry
                self.metrics.record_sentence_retry()

                logger.warning(
                    f"🔄 [RETRY] Retrying sentence (attempt {retry_count}/{max_retries}, "
                    f"task={task_id[:8] if task_id else 'unknown'}...)"
                )

                # Re-enqueue the same sentence
                if self.tts_queue_manager:
                    await self.tts_queue_manager.enqueue_sentence(
                        sentence=sentence,
                        session_id=session_id,
                        voice_id=self.agent.tts_voice or os.getenv('CHATTERBOX_VOICE_ID', 'default'),
                        exaggeration=self.agent.tts_exaggeration or 1.0,
                        cfg_weight=self.agent.tts_cfg_weight or 0.7,
                        temperature=self.agent.tts_temperature or 0.3,
                        language=self.agent.tts_language or 'en',
                        metadata={
                            **metadata,
                            'retry_count': retry_count,
                            'is_retry': True
                        }
                    )
            else:
                # Max retries exceeded, skip sentence
                logger.error(
                    f"⏭️  [RETRY] Max retries exceeded (task={task_id[:8] if task_id else 'unknown'}...) - "
                    f"skipping sentence"
                )
                # Clean up retry count
                if task_id in self.sentence_retry_counts:
                    del self.sentence_retry_counts[task_id]

        elif strategy == 'fallback':
            # Cancel remaining sentences and fall back to legacy TTS
            # Only trigger fallback once per session
            if session_id and not self.fallback_triggered.get(session_id, False):
                self.fallback_triggered[session_id] = True

                logger.warning(
                    f"🔙 [FALLBACK] First TTS failure - canceling remaining sentences and "
                    f"falling back to legacy TTS (session={session_id[:8]}...)"
                )

                # Cancel all pending sentences in TTS queue
                if self.tts_queue_manager:
                    await self.tts_queue_manager.cancel_pending()
                    logger.info(f"🚫 [FALLBACK] Cancelled pending TTS sentences")

                # Note: We can't synthesize the remaining text here because we don't
                # have access to the full response. The sentence-level streaming will
                # continue with already-enqueued sentences, but no new ones will be added.
                # This provides graceful degradation.

                logger.info(
                    f"✅ [FALLBACK] Fallback mode active - processing already-enqueued sentences, "
                    f"no new sentences will be added"
                )
            else:
                # Fallback already triggered, just log
                logger.debug(
                    f"⏭️  [FALLBACK] Skipping sentence (fallback already active, "
                    f"task={task_id[:8] if task_id else 'unknown'}...)"
                )

        else:
            logger.error(f"❌ Unknown error strategy: {strategy} - defaulting to skip")

        # Clean up retry count on completion (for skip/fallback strategies)
        if strategy in ('skip', 'fallback') and task_id in self.sentence_retry_counts:
            del self.sentence_retry_counts[task_id]

    # ============================================================
    # PHASE 7: USER INTERRUPTION HANDLING
    # ============================================================

    async def _handle_interruption(self, guild_id: int, user_id: str, username: str) -> None:
        """
        Handle user interruption when they start speaking while AI is responding.

        Phase 7: Interruption strategies:
        - immediate: Cancel all queued TTS and stop current playback immediately
        - graceful: Finish current sentence, cancel queue
        - drain: Process 1-2 more sentences, then stop

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID (for logging)
            username: Discord username (for logging)
        """
        # Check if there's an active TTS queue or playback
        has_queued_tts = (
            self.tts_queue_manager and
            self.tts_queue_manager.queue.qsize() > 0
        )
        has_active_playback = (
            guild_id in self.audio_playback_queues and
            self.audio_playback_queues[guild_id].current_chunk is not None
        )

        if not has_queued_tts and not has_active_playback:
            # No active TTS/playback, no interruption needed
            return

        strategy = self.tts_service.streaming_config.interruption_strategy

        logger.info(
            f"🛑 [INTERRUPTION] User {username} started speaking while AI responding "
            f"(strategy={strategy}, queued={self.tts_queue_manager.queue.qsize() if self.tts_queue_manager else 0}, "
            f"playing={has_active_playback})"
        )

        # Record interruption metric
        self.metrics.record_interruption()

        # Execute interruption strategy
        if strategy == 'immediate':
            # Cancel all queued TTS
            if self.tts_queue_manager:
                await self.tts_queue_manager.cancel_all()
                logger.info(f"🚫 [IMMEDIATE] Cancelled all queued TTS sentences")

            # Stop current audio playback immediately
            if guild_id in self.audio_playback_queues:
                await self.audio_playback_queues[guild_id].stop_playback('immediate')
                logger.info(f"⏹️  [IMMEDIATE] Stopped audio playback immediately")

        elif strategy == 'graceful':
            # Cancel pending TTS (keep active synthesis)
            if self.tts_queue_manager:
                await self.tts_queue_manager.cancel_pending()
                logger.info(
                    f"🚫 [GRACEFUL] Cancelled pending TTS sentences "
                    f"(active synthesis will complete)"
                )

            # Let current audio sentence finish, cancel rest
            if guild_id in self.audio_playback_queues:
                await self.audio_playback_queues[guild_id].stop_playback('graceful')
                logger.info(f"⏸️  [GRACEFUL] Finishing current sentence, cancelling rest")

        elif strategy == 'drain':
            # Keep next 1-2 sentences, cancel rest
            if self.tts_queue_manager:
                await self.tts_queue_manager.cancel_after(num_to_keep=2)
                logger.info(
                    f"🚫 [DRAIN] Kept next 2 TTS sentences, cancelled rest "
                    f"(will complete thought)"
                )

            # Let current + next 1-2 sentences play
            if guild_id in self.audio_playback_queues:
                await self.audio_playback_queues[guild_id].stop_playback('drain')
                logger.info(f"⏸️  [DRAIN] Processing 1-2 more sentences, then stopping")

        else:
            logger.error(f"❌ Unknown interruption strategy: {strategy} - defaulting to immediate")
            # Fallback to immediate
            if self.tts_queue_manager:
                await self.tts_queue_manager.cancel_all()
            if guild_id in self.audio_playback_queues:
                await self.audio_playback_queues[guild_id].stop_playback('immediate')

        # Broadcast interruption event to frontend
        try:
            from src.api import get_ws_manager
            ws_manager = get_ws_manager()
            await ws_manager.broadcast({
                "event": "user_interruption",
                "data": {
                    "userId": user_id,
                    "username": username,
                    "strategy": strategy,
                    "timestamp": datetime.now().isoformat()
                }
            })
        except Exception as e:
            logger.error(f"❌ Failed to broadcast interruption event: {e}")

    async def _generate_response(
        self,
        session_id: str,
        user_id: str,
        username: str,
        user_text: str,
        guild_id: Optional[int]
    ) -> None:
        """
        Generate AI response and play via TTS.

        Phase 2: Complete LLM + TTS pipeline
        - Gets conversation context (Phase 1 integration)
        - Routes to LLM service (OpenRouter → Local → n8n fallback)
        - Streams response chunks
        - Synthesizes and plays TTS

        Original source: discord_bot.py generate_and_play_response (lines 711-896)

        Args:
            session_id: Session UUID
            user_id: Discord user ID
            username: Discord username
            user_text: User's transcribed text
            guild_id: Discord guild ID (for voice playback)
        """
        try:
            t_llm_start = time.time()

            # Phase 1 integration: Get conversation context from ConversationService
            messages = await self.conversation_service.get_conversation_context(
                session_id=session_id,
                limit=10,
                include_system_prompt=True
            )

            # Phase 1 integration: Use agent config from self.agent
            # Convert to LLM format
            llm_messages = [{'role': msg.role, 'content': msg.content} for msg in messages]

            # Build LLM config (Phase 1 integration)
            llm_config = LLMConfig(
                provider=ProviderType(self.agent.llm_provider),
                model=self.agent.llm_model,
                temperature=self.agent.temperature,
                system_prompt=self.agent.system_prompt
            )

            logger.info(f"🤖 Generating LLM response (session={session_id[:8]}..., provider={llm_config.provider.value})")
            logger.debug(f"[DEBUG] Conversation history for LLM ({len(llm_messages)} messages):")
            for i, msg in enumerate(llm_messages):
                content_preview = msg['content'][:100].replace('\n', ' ') if msg['content'] else '(empty)'
                logger.debug(f"  [{i}] {msg['role']}: {content_preview}...")
            logger.debug(f"[DEBUG] LLM config: model={llm_config.model}, temp={llm_config.temperature}, provider={llm_config.provider.value}")

            # Phase 5: Initialize sentence parser if streaming enabled
            sentence_parser = None
            streaming_config = self.tts_service.streaming_config if self.tts_service else None
            if streaming_config and streaming_config.enabled and self.tts_queue_manager:
                sentence_parser = SentenceParser(
                    min_sentence_length=streaming_config.min_chunk_length
                )
                self.sentence_parsers[session_id] = sentence_parser
                logger.info(
                    f"🌊 [STREAMING] Initialized chunk parser "
                    f"(strategy={streaming_config.chunking_strategy}, min_length={streaming_config.min_chunk_length})"
                )

                # Phase 8: Record streaming session start
                self.metrics.record_streaming_session()

            # Stream response from LLM (Phase 1 integration)
            full_response = ""
            first_chunk = True

            async def on_llm_chunk(chunk: str):
                nonlocal full_response, first_chunk
                full_response += chunk

                # Record first chunk latency (Phase 1 integration)
                if first_chunk:
                    t_first_chunk = time.time()
                    latency = t_first_chunk - t_llm_start
                    logger.info(f"⏱️ LATENCY [LLM first chunk]: {latency:.3f}s")
                    self.metrics.record_n8n_first_chunk_latency(latency)
                    first_chunk = False

                # Phase 5: Process chunk through sentence parser if streaming enabled
                if sentence_parser and self.tts_queue_manager:
                    completed_sentences = sentence_parser.add_chunk(chunk)

                    # Enqueue completed sentences to TTS queue
                    for sentence in completed_sentences:
                        t_sentence_detected = time.time()

                        logger.info(
                            f"🌊 [STREAMING] Sentence detected: \"{sentence[:50]}...\" "
                            f"(len={len(sentence)} chars)"
                        )

                        # Phase 8: Record sentence detection (parsing time is negligible, ~0ms)
                        self.metrics.record_sentence_detection(0)

                        # Enqueue to TTS queue manager
                        await self.tts_queue_manager.enqueue_sentence(
                            sentence=sentence,
                            session_id=session_id,
                            voice_id=self.agent.tts_voice or os.getenv('CHATTERBOX_VOICE_ID', 'default'),
                            exaggeration=self.agent.tts_exaggeration or 1.0,
                            cfg_weight=self.agent.tts_cfg_weight or 0.7,
                            temperature=self.agent.tts_temperature or 0.3,
                            language=self.agent.tts_language or 'en',
                            metadata={
                                'guild_id': guild_id,
                                'user_id': user_id,
                                'username': username,
                                'timestamp': time.time(),
                                't_sentence_detected': t_sentence_detected  # Phase 8: for sentence-to-audio latency
                            }
                        )

                # Broadcast AI response chunk to frontend
                try:
                    from src.api import get_ws_manager
                    ws_manager = get_ws_manager()
                    await ws_manager.broadcast({
                        "event": "ai_response_chunk",
                        "data": {
                            "userId": user_id,
                            "username": username,
                            "text": chunk,
                            "sessionId": session_id,
                            "timestamp": datetime.now().isoformat()
                        }
                    })
                except Exception as e:
                    logger.error(f"❌ Failed to broadcast AI response chunk: {e}")

            # Retry logic for empty LLM responses
            max_retries = 2
            retry_count = 0

            try:
                while retry_count <= max_retries:
                    # Phase 1 integration: Use LLMService
                    await self.llm_service.generate_response(
                        session_id=session_id,
                        messages=llm_messages,
                        config=llm_config,
                        stream=True,
                        callback=on_llm_chunk
                    )

                    # Record total LLM latency (Phase 1 integration)
                    t_llm_complete = time.time()
                    llm_duration = t_llm_complete - t_llm_start
                    logger.info(f"⏱️ LATENCY [total LLM generation]: {llm_duration:.3f}s")
                    self.metrics.record_ai_generation_latency(llm_duration)

                    # Store LLM complete time for TTS queue latency metric
                    if session_id in self.session_timings:
                        self.session_timings[session_id]['t_llm_complete'] = t_llm_complete

                    # Check if response is empty
                    if not full_response or not full_response.strip():
                        retry_count += 1
                        if retry_count <= max_retries:
                            logger.warning(f"⚠️ LLM returned empty response (attempt {retry_count}/{max_retries + 1}), retrying...")

                            # Broadcast retry notification to frontend
                            try:
                                from src.api import get_ws_manager
                                ws_manager = get_ws_manager()
                                await ws_manager.broadcast({
                                    "event": "llm_retry",
                                    "data": {
                                        "userId": user_id,
                                        "username": username,
                                        "attempt": retry_count,
                                        "maxAttempts": max_retries + 1,
                                        "message": f"Retrying... (attempt {retry_count}/{max_retries + 1})"
                                    }
                                })
                            except Exception as e:
                                logger.error(f"❌ Failed to broadcast LLM retry notification: {e}")

                            full_response = ""  # Reset for retry
                            first_chunk = True  # Reset first chunk flag
                            t_llm_start = time.time()  # Reset timer for retry
                            continue
                        else:
                            logger.error(f"❌ LLM returned empty response after {max_retries + 1} attempts")
                            full_response = "I apologize, but I'm having trouble generating a response right now. Could you please try again?"

                            # Broadcast fallback notification to frontend
                            try:
                                from src.api import get_ws_manager
                                ws_manager = get_ws_manager()
                                await ws_manager.broadcast({
                                    "event": "llm_fallback",
                                    "data": {
                                        "userId": user_id,
                                        "username": username,
                                        "message": "AI response failed after multiple attempts. Using fallback message.",
                                        "fallbackMessage": full_response
                                    }
                                })
                            except Exception as e:
                                logger.error(f"❌ Failed to broadcast LLM fallback notification: {e}")

                    # Success - break out of retry loop
                    break

            except (LLMError, LLMConnectionError, LLMTimeoutError) as e:
                # LLM providers unavailable - fall back to n8n webhook
                n8n_webhook_url = os.getenv('N8N_WEBHOOK_URL')

                if not n8n_webhook_url:
                    logger.error(f"❌ LLM providers unavailable and no N8N webhook configured: {e}")
                    raise

                logger.warning(f"⚠️ LLM providers unavailable, falling back to n8n webhook: {e}")
                logger.info(f"🌐 Calling n8n webhook: {n8n_webhook_url}")

                try:
                    # Call n8n webhook with conversation context
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        payload = {
                            'sessionId': session_id,
                            'userId': user_id,
                            'username': username,
                            'text': user_text,
                            'conversationHistory': [
                                {'role': msg['role'], 'content': msg['content']}
                                for msg in llm_messages
                            ],
                            'agentConfig': {
                                'name': self.agent.name,
                                'systemPrompt': self.agent.system_prompt,
                                'temperature': self.agent.temperature,
                                'model': self.agent.llm_model
                            }
                        }

                        response = await client.post(n8n_webhook_url, json=payload)
                        response.raise_for_status()

                        t_n8n_complete = time.time()
                        n8n_duration = t_n8n_complete - t_llm_start
                        logger.info(f"⏱️ LATENCY [n8n webhook]: {n8n_duration:.3f}s")
                        self.metrics.record_ai_generation_latency(n8n_duration)

                        # Store LLM complete time for TTS queue latency metric (n8n path)
                        if session_id in self.session_timings:
                            self.session_timings[session_id]['t_llm_complete'] = t_n8n_complete

                        # Parse n8n response
                        t_parse_start = time.time()
                        response_data = response.json()
                        t_parse_end = time.time()
                        parse_latency_ms = (t_parse_end - t_parse_start) * 1000
                        self.metrics.record_response_parsing_latency(parse_latency_ms)
                        logger.info(f"⏱️ LATENCY [response parsing]: {parse_latency_ms:.2f}ms")

                        # Handle various n8n response formats
                        # Format 1: {"response": "text"} or {"output": "text"} or {"text": "text"}
                        # Format 2: [{"output": "text"}] (array of objects with output field)
                        # Format 3: ["text"] (array of strings)
                        # Format 4: "text" (raw string)

                        if isinstance(response_data, dict):
                            # Extract from dict
                            full_response = (
                                response_data.get('response') or
                                response_data.get('output') or
                                response_data.get('text') or
                                str(response_data)
                            )
                        elif isinstance(response_data, list) and response_data:
                            # Extract from array
                            first_item = response_data[0]
                            if isinstance(first_item, dict):
                                # [{"output": "text"}] format
                                full_response = (
                                    first_item.get('output') or
                                    first_item.get('response') or
                                    first_item.get('text') or
                                    str(first_item)
                                )
                            elif isinstance(first_item, str):
                                # ["text"] format
                                full_response = first_item
                            else:
                                full_response = str(first_item)
                        elif isinstance(response_data, str):
                            full_response = response_data
                        else:
                            full_response = str(response_data)

                        logger.info(f"✅ n8n response received: {len(full_response)} chars - preview: '{full_response[:100]}...'")

                except Exception as n8n_error:
                    logger.error(f"❌ n8n webhook fallback failed: {n8n_error}", exc_info=True)
                    raise LLMError(f"Both LLM providers and n8n webhook failed. LLM: {e}, n8n: {n8n_error}") from n8n_error

            # Phase 5: Finalize sentence parser and enqueue remaining text
            if sentence_parser and self.tts_queue_manager:
                remaining_text = sentence_parser.finalize()

                if remaining_text:
                    logger.info(
                        f"🌊 [STREAMING] Finalizing remaining text: \"{remaining_text[:50]}...\" "
                        f"(len={len(remaining_text)} chars)"
                    )

                    # Enqueue remaining text to TTS queue
                    await self.tts_queue_manager.enqueue_sentence(
                        sentence=remaining_text,
                        session_id=session_id,
                        voice_id=self.agent.tts_voice or os.getenv('CHATTERBOX_VOICE_ID', 'default'),
                        exaggeration=self.agent.tts_exaggeration or 1.0,
                        cfg_weight=self.agent.tts_cfg_weight or 0.7,
                        temperature=self.agent.tts_temperature or 0.3,
                        language=self.agent.tts_language or 'en',
                        metadata={
                            'guild_id': guild_id,
                            'user_id': user_id,
                            'username': username,
                            'timestamp': time.time(),
                            'is_final': True  # Mark as final chunk
                        }
                    )

                # Clean up sentence parser
                if session_id in self.sentence_parsers:
                    del self.sentence_parsers[session_id]
                    logger.info(f"🌊 [STREAMING] Cleaned up sentence parser for session {session_id[:8]}...")

            # Phase 1 integration: Add assistant message to conversation
            await self.conversation_service.add_message(
                session_id=session_id,
                role='assistant',
                content=full_response
            )

            # Broadcast AI response complete to frontend (CRITICAL - must always happen)
            try:
                from src.api import get_ws_manager
                ws_manager = get_ws_manager()
                logger.info(f"📡 WebSocket: Broadcasting ai_response_complete to frontend (user={username}, text length={len(full_response)} chars)")
                await ws_manager.broadcast({
                    "event": "ai_response_complete",
                    "data": {
                        "userId": user_id,
                        "username": username,
                        "text": full_response,
                        "sessionId": session_id,
                        "timestamp": datetime.now().isoformat()
                    }
                })
            except Exception as e:
                logger.error(f"❌ Failed to broadcast AI response complete: {e}")

            logger.info(f"🤖 LLM response generated for session {session_id[:8]}... (user={user_id})")

            # Phase 5: Skip TTS if streaming enabled (already handled by AudioPlaybackQueue)
            if self.tts_service.streaming_config.enabled and sentence_parser:
                logger.info(
                    f"🌊 [STREAMING] TTS handled by AudioPlaybackQueue, skipping legacy _play_tts() "
                    f"(session={session_id[:8]}...)"
                )
            # Phase 2: Synthesize and play TTS (legacy non-streaming mode)
            elif guild_id and guild_id in self.voice_clients:
                logger.info(f"📝 [NON-STREAMING] Starting legacy TTS playback (session={session_id[:8]}...)")
                voice_client = self.voice_clients[guild_id]
                await self._play_tts(full_response, voice_client, session_id)
                logger.info(f"🔊 TTS playback completed for session {session_id[:8]}... (user={user_id})")
            else:
                logger.warning(f"⚠️ Cannot play TTS: no voice client for guild {guild_id}")

        except Exception as e:
            logger.error(f"❌ Error generating LLM response (session={session_id[:8]}...): {e}", exc_info=True)
            self.metrics.record_error()

            # Broadcast error to frontend so animation stops
            try:
                from src.api import get_ws_manager
                ws_manager = get_ws_manager()
                error_message = f"Error generating AI response: {str(e)}"
                logger.error(f"📡 WebSocket: Broadcasting ai_response_complete with error to frontend (user={username})")
                await ws_manager.broadcast({
                    "event": "ai_response_complete",
                    "data": {
                        "userId": user_id,
                        "username": username,
                        "text": "",  # Empty response
                        "error": error_message,
                        "sessionId": session_id,
                        "timestamp": datetime.now().isoformat()
                    }
                })
            except Exception as broadcast_error:
                logger.error(f"❌ Failed to broadcast error: {broadcast_error}")

    async def _play_tts(
        self,
        text: str,
        voice_client: discord.VoiceClient,
        session_id: str
    ) -> Optional[str]:
        """
        Synthesize speech and play in Discord voice channel.

        Phase 2: Complete TTS pipeline
        - Synthesizes speech via TTSService (Phase 1 integration)
        - Saves to temp WAV file
        - Plays via discord.FFmpegPCMAudio
        - Tracks TTS and playback latency

        Original source: discord_bot.py synthesize_and_play_discord (lines 898-989)

        Args:
            text: Text to synthesize
            voice_client: Discord voice client
            session_id: Session UUID for metrics tracking

        Returns:
            Path to temp audio file, or None on error
        """
        if not voice_client or not voice_client.is_connected():
            logger.warning("⚠️ Not in voice channel, cannot play TTS")
            return None

        try:
            t_tts_start = time.time()

            # Record TTS queue latency (LLM complete → TTS start)
            if session_id in self.session_timings and 't_llm_complete' in self.session_timings[session_id]:
                t_llm_complete = self.session_timings[session_id]['t_llm_complete']
                tts_queue_latency = t_tts_start - t_llm_complete
                self.metrics.record_tts_queue_latency(tts_queue_latency)
                logger.info(f"⏱️ LATENCY [TTS queue wait]: {tts_queue_latency:.3f}s")

            # Phase 1 integration: Synthesize using TTSService (non-streaming for Discord)
            audio_bytes = await self.tts_service.synthesize_speech(
                session_id=session_id,
                text=text,
                voice_id=self.agent.tts_voice or os.getenv('CHATTERBOX_VOICE_ID', 'default'),
                exaggeration=self.agent.tts_exaggeration,
                cfg_weight=self.agent.tts_cfg_weight,
                temperature=self.agent.tts_temperature,
                language_id=self.agent.tts_language,
                stream=False,  # Discord needs complete audio file
                callback=None,
                filter_actions=self.agent.filter_actions_for_tts
            )

            if not audio_bytes:
                logger.error("❌ TTS synthesis failed, no audio received")
                return None

            t_tts_complete = time.time()
            tts_duration = t_tts_complete - t_tts_start
            logger.info(f"⏱️ LATENCY [TTS generation]: {tts_duration:.3f}s")
            self.metrics.record_tts_generation_latency(tts_duration)

            # Save to temp file and play
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as f:
                f.write(audio_bytes)
                temp_path = f.name

            try:
                t_playback_start = time.time()

                # Record time to first audio (user stops speaking → first audio plays)
                if session_id in self.session_timings and 't_transcription_complete' in self.session_timings[session_id]:
                    # Measure from when user STOPPED speaking (transcription complete), not when they started
                    t_transcription_complete = self.session_timings[session_id]['t_transcription_complete']
                    time_to_first_audio = t_playback_start - t_transcription_complete
                    self.metrics.record_time_to_first_audio(time_to_first_audio)
                    logger.info(f"⏱️ ⭐⭐⭐ LATENCY [time to first audio]: {time_to_first_audio:.3f}s (transcription complete → audio plays)")

                # Wait for current audio to finish if playing
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)

                # Create FFmpeg audio source
                t_ffmpeg_start = time.time()
                before_options = '-loglevel error'
                options = '-vn -ac 2 -ar 48000'
                audio_source = discord.FFmpegPCMAudio(temp_path, before_options=before_options, options=options)
                t_ffmpeg_end = time.time()

                ffmpeg_latency_ms = (t_ffmpeg_end - t_ffmpeg_start) * 1000
                logger.info(f"⏱️ LATENCY [FFmpeg processing]: {ffmpeg_latency_ms:.2f}ms")
                self.metrics.record_ffmpeg_processing_latency(ffmpeg_latency_ms)

                # Play audio
                voice_client.play(audio_source)
                logger.info(f"🔊 Playing TTS audio ({len(audio_bytes):,} bytes)")

                # Wait for playback to complete
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)

                t_playback_complete = time.time()
                playback_duration = t_playback_complete - t_playback_start
                logger.info(f"⏱️ LATENCY [audio playback]: {playback_duration:.3f}s")
                self.metrics.record_audio_playback_latency(playback_duration)

                # Record total pipeline latency (Phase 1 integration)
                if session_id in self.session_timings:
                    t_start = self.session_timings[session_id]['t_start']
                    total_latency = t_playback_complete - t_start
                    logger.info(f"⏱️ ⭐⭐⭐ TOTAL PIPELINE LATENCY: {total_latency:.3f}s")
                    self.metrics.record_total_pipeline_latency(total_latency)

                    # Broadcast metrics update to frontend
                    try:
                        from src.api import get_ws_manager
                        ws_manager = get_ws_manager()
                        metrics_snapshot = self.metrics.get_metrics()
                        await ws_manager.broadcast({
                            "event": "metrics_updated",
                            "data": metrics_snapshot
                        })
                        logger.debug(f"📊 Broadcast metrics update to frontend")
                    except Exception as e:
                        logger.error(f"❌ Failed to broadcast metrics update: {e}")

                return temp_path

            finally:
                # Cleanup temp file
                try:
                    os.unlink(temp_path)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to delete temp file {temp_path}: {e}")

        except Exception as e:
            logger.error(f"❌ Error with TTS playback: {e}", exc_info=True)
            return None

    async def _cleanup_session(self, user_id: str, session_id: str) -> None:
        """
        Clean up session resources when user leaves or session ends.

        Phase 2: Complete cleanup implementation
        - Ends session in ConversationService (Phase 1 integration)
        - Disconnects STT service (Phase 1 integration)
        - Clears session tracking dictionaries
        - Logs metrics summary

        Original source: discord_bot.py cleanup_session (lines 1006-1038)

        Args:
            user_id: Discord user ID
            session_id: Session UUID
        """
        logger.info(
            f"🧹 Cleaning up session for user {user_id} (session: {session_id[:8]}...)"
        )

        try:
            # Phase 1 integration: Disconnect STT
            if self.stt_service:
                await self.stt_service.disconnect(session_id)

            # Phase 1 integration: End session in database (mark inactive)
            if self.conversation_service:
                await self.conversation_service.end_session(session_id, persist=True)

            # Remove from active sessions
            if user_id in self.active_sessions:
                del self.active_sessions[user_id]

            # Remove timing data
            if session_id in self.session_timings:
                del self.session_timings[session_id]

            # Phase 6: Cleanup error handling state
            if session_id in self.fallback_triggered:
                del self.fallback_triggered[session_id]
                logger.debug(f"🧹 Cleaned up fallback state for session {session_id[:8]}...")

            if session_id in self.sentence_parsers:
                del self.sentence_parsers[session_id]
                logger.debug(f"🧹 Cleaned up sentence parser for session {session_id[:8]}...")

            # Note: sentence_retry_counts is keyed by task_id, not session_id,
            # so it's cleaned up when retries complete or max retries reached

            # Phase 2: Cleanup audio receiver for this user
            # Find guild_id for this user's voice connection
            for guild_id, receiver in self.audio_receivers.items():
                if user_id in receiver.active_sessions:
                    receiver.cleanup_user(user_id)
                    break

            # TODO Phase 2 Tests: Broadcast speaker_stopped event
            # await broadcast_speaker_stopped(user_id, username, duration_ms)

            logger.info(f"✅ Session cleanup complete for user {user_id}")

        except Exception as e:
            logger.error(f"❌ Error cleaning up session {session_id[:8]}...: {e}", exc_info=True)

    # ============================================================
    # PHASE 3: HTTP API VOICE CONTROL METHODS
    # ============================================================

    async def join_voice_channel(
        self,
        guild_id: int,
        channel_id: int,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Join a Discord voice channel.

        Phase 3: HTTP API integration
        Phase 6.X: Unified Conversation Threading - accepts optional session_id

        Args:
            guild_id: Discord guild (server) ID
            channel_id: Discord voice channel ID
            session_id: Optional UUID of web session to link Discord voice to

        Returns:
            Dict with connection status

        Raises:
            ValueError: If already connected to voice in this guild
            RuntimeError: If connection fails
        """
        # Check if already connected
        if guild_id in self.voice_clients:
            raise ValueError(f"Already connected to voice channel in guild {guild_id}")

        # Find guild and channel
        guild = self.bot.get_guild(guild_id)
        if not guild:
            raise ValueError(f"Guild {guild_id} not found")

        channel = guild.get_channel(channel_id)
        if not channel:
            raise ValueError(f"Channel {channel_id} not found in guild {guild_id}")

        # Connect to voice channel
        try:
            voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
            self.voice_clients[guild_id] = voice_client

            # Register AudioReceiver (Phase 2 integration)
            receiver = self.AudioReceiver(self, voice_client)
            voice_client.listen(receiver)
            self.audio_receivers[guild_id] = receiver
            logger.info(f"🎤 Registered audio receiver for guild {guild_id}")

            # Phase 5: Create audio playback queue if streaming enabled
            if self.tts_service.streaming_config.enabled and guild_id not in self.audio_playback_queues:
                playback_queue = AudioPlaybackQueue(
                    voice_client=voice_client,
                    on_complete=None,  # Optional callback
                    on_error=None  # Optional callback
                )
                await playback_queue.start()
                self.audio_playback_queues[guild_id] = playback_queue
                logger.info(f"🎵 Created audio playback queue for guild {guild_id} (manual join)")

            # Phase 6.X: Store session mapping if provided
            if session_id:
                self.guild_session_mapping[guild_id] = session_id
                logger.info(
                    f"🔗 Linked guild {guild_id} to session {session_id[:8]}... "
                    f"(unified conversation threading enabled)"
                )

                # Update session in database to track discord_guild_id
                try:
                    from src.database.session import get_db_session
                    from src.database.models import Session
                    from sqlalchemy import update
                    from uuid import UUID

                    async with get_db_session() as db:
                        await db.execute(
                            update(Session)
                            .where(Session.id == UUID(session_id))
                            .values(discord_guild_id=str(guild_id))
                        )
                        await db.commit()
                        logger.debug(f"💾 Updated session {session_id[:8]}... with discord_guild_id={guild_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to update session discord_guild_id: {e}")
                    # Non-fatal - continue with in-memory mapping

            logger.info(
                f"✅ Joined voice channel '{channel.name}' in guild '{guild.name}' "
                f"(agent: {self.agent_name})"
            )

            return {
                'success': True,
                'guild_id': guild_id,
                'guild_name': guild.name,
                'channel_id': channel_id,
                'channel_name': channel.name,
                'agent_id': str(self.agent_id),
                'agent_name': self.agent_name,
                'session_id': session_id,  # Include in response for UI feedback
            }
        except Exception as e:
            logger.error(f"❌ Failed to join voice channel: {e}", exc_info=True)
            raise RuntimeError(f"Failed to join voice channel: {e}")

    async def leave_voice_channel(
        self,
        guild_id: int
    ) -> Dict[str, Any]:
        """
        Leave Discord voice channel in a guild.

        Phase 3: HTTP API integration

        Args:
            guild_id: Discord guild (server) ID

        Returns:
            Dict with disconnection status

        Raises:
            ValueError: If not connected to voice in this guild
        """
        if guild_id not in self.voice_clients:
            raise ValueError(f"Not connected to voice channel in guild {guild_id}")

        voice_client = self.voice_clients[guild_id]

        try:
            # Cleanup active sessions for this guild's users
            sessions_to_cleanup = []
            for user_id, session_id in list(self.active_sessions.items()):
                # For now, cleanup all sessions when leaving voice
                # TODO: Track guild per session for more granular cleanup
                sessions_to_cleanup.append((user_id, session_id))

            for user_id, session_id in sessions_to_cleanup:
                await self._cleanup_session(user_id, session_id)

            # Cleanup audio receiver before disconnecting
            if guild_id in self.audio_receivers:
                self.audio_receivers[guild_id].cleanup()
                del self.audio_receivers[guild_id]

            # Phase 6.X: Clear session mapping and update database
            session_id = self.guild_session_mapping.pop(guild_id, None)
            if session_id:
                logger.info(f"🔓 Unlinked guild {guild_id} from session {session_id[:8]}...")

                # Update session in database to clear discord_guild_id
                try:
                    from src.database.session import get_db_session
                    from src.database.models import Session
                    from sqlalchemy import update
                    from uuid import UUID

                    async with get_db_session() as db:
                        await db.execute(
                            update(Session)
                            .where(Session.id == UUID(session_id))
                            .values(discord_guild_id=None)
                        )
                        await db.commit()
                        logger.debug(f"💾 Cleared discord_guild_id from session {session_id[:8]}...")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to clear session discord_guild_id: {e}")

            # Disconnect voice client
            await voice_client.disconnect()
            del self.voice_clients[guild_id]

            logger.info(f"✅ Left voice channel in guild {guild_id} (agent: {self.agent_name})")

            return {
                'success': True,
                'guild_id': guild_id,
                'agent_id': str(self.agent_id),
                'agent_name': self.agent_name,
            }
        except Exception as e:
            logger.error(f"❌ Failed to leave voice channel: {e}", exc_info=True)
            raise RuntimeError(f"Failed to leave voice channel: {e}")

    def get_voice_status(self) -> Dict[str, Any]:
        """
        Get current voice connection status.

        Phase 3: HTTP API integration

        Returns:
            Dict with voice connection details
        """
        connections = []
        for guild_id, voice_client in self.voice_clients.items():
            guild = voice_client.guild
            channel = voice_client.channel

            connections.append({
                'guild_id': str(guild_id),  # Convert to string to preserve precision in JSON
                'guild_name': guild.name if guild else None,
                'channel_id': str(channel.id) if channel else None,  # Also convert channel_id
                'channel_name': channel.name if channel else None,
                'connected': voice_client.is_connected(),
            })

        return {
            'agent_id': str(self.agent_id),
            'agent_name': self.agent_name,
            'bot': {
                'ready': self.bot.is_ready() if self.bot else False,
                'username': self.bot.user.name if self.bot and self.bot.user else None,
                'id': str(self.bot.user.id) if self.bot and self.bot.user else None,
            },
            'connections': connections,
            'active_sessions': len(self.active_sessions),
        }

    # ============================================================
    # UTILITY METHODS
    # ============================================================

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
                'active_sessions': len(self.active_sessions),  # Phase 1
                'metrics': self.metrics.get_metrics() if self.metrics else {},  # Phase 1
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
            'active_sessions': len(self.active_sessions),  # Phase 1
            'metrics': self.metrics.get_metrics() if self.metrics else {},  # Phase 1
        }


# ============================================================
# TODO: PHASE 2 TESTING TASKS
# ============================================================
#
# TODO Phase 2 Tests:
# - Test audio receiving from multiple users simultaneously
# - Test STT transcript callback flow (partial → final)
# - Test LLM generation with OpenRouter → Local → n8n fallback
# - Test TTS synthesis and Discord voice playback
# - Test session cleanup on user leave
# - Test silence detection triggering finalization
# - Test max speaking time safety limit
# - Test metrics tracking for all pipeline stages
# - Test error handling in audio pipeline
# - Test concurrent sessions (multiple users in same channel)
#
# Test Scenarios:
# 1. Single user speaks → transcription → LLM → TTS playback
# 2. Multiple users speak sequentially
# 3. User leaves mid-transcription (cleanup)
# 4. Silence detection timeout
# 5. Max speaking time reached
# 6. LLM provider failures (test n8n fallback)
# 7. TTS synthesis failures
# 8. Voice client disconnect during playback
# 9. Audio buffer overflow (queue full)
# 10. WebSocket broadcast integration
#
