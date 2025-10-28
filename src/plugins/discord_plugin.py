"""
Discord Bot Plugin - Phase 1: Service Layer Foundation

Phase 1 Changes (2025-10-28):
- Added service layer dependencies (ConversationService, STTService, LLMService, TTSService)
- Added session tracking infrastructure (active_sessions, session_timings)
- Integrated MetricsTracker for performance monitoring
- Enhanced cleanup in stop() method
- Added stub methods for Phase 2 audio pipeline
- Service initialization after agent binding in initialize()

Remaining Phases:
- Phase 2: Audio Pipeline Integration (STT callbacks, TTS playback)
- Phase 3: Session Management (user → session mapping)
- Phase 4: Voice State Integration (Discord voice events → audio pipeline)

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
import statistics
import time
from collections import deque
from threading import Lock
from typing import Dict, Any, Optional, List
from uuid import UUID

import discord
from discord.ext import commands

from src.plugins.base import PluginBase
from src.plugins.registry import plugin

# Phase 1: Import service layer dependencies
from src.services.conversation_service import ConversationService
from src.services.stt_service import get_stt_service
from src.services.llm_service import get_llm_service
from src.services.tts_service import get_tts_service

logger = logging.getLogger(__name__)


# ============================================================
# METRICS TRACKER (from discord_bot.py)
# ============================================================

class MetricsTracker:
    """Track performance metrics for the application"""

    def __init__(self, max_samples=100):
        self.max_samples = max_samples

        # Legacy metrics
        self.latencies = deque(maxlen=max_samples)
        self.n8n_response_latencies = deque(maxlen=max_samples)  # LLM → first response
        self.n8n_first_chunk_latencies = deque(maxlen=max_samples)  # LLM → first chunk
        self.tts_first_byte_latencies = deque(maxlen=max_samples)  # response complete → first audio byte

        # Phase 1: Speech → Transcription
        self.whisper_connection_latencies = deque(maxlen=max_samples)  # user starts speaking → WhisperX connected
        self.first_partial_transcript_latencies = deque(maxlen=max_samples)  # WhisperX connected → first partial
        self.transcription_duration_latencies = deque(maxlen=max_samples)  # first partial → final transcript
        self.silence_detection_latencies = deque(maxlen=max_samples)  # last audio → silence detected (ms)

        # Phase 2: AI Processing
        self.ai_generation_latencies = deque(maxlen=max_samples)  # webhook sent → response received
        self.response_parsing_latencies = deque(maxlen=max_samples)  # response received → text extracted (ms)

        # Phase 3: TTS Generation
        self.tts_queue_latencies = deque(maxlen=max_samples)  # text ready → TTS request sent
        self.tts_generation_latencies = deque(maxlen=max_samples)  # TTS sent → all audio downloaded

        # Phase 4: Audio Playback
        self.audio_playback_latencies = deque(maxlen=max_samples)  # audio ready → playback complete
        self.ffmpeg_processing_latencies = deque(maxlen=max_samples)  # FFmpeg conversion time (ms)

        # End-to-End
        self.total_pipeline_latencies = deque(maxlen=max_samples)  # user starts speaking → audio playback complete
        self.time_to_first_audio_latencies = deque(maxlen=max_samples)  # user starts speaking → first audio byte plays

        # UX Enhancement
        self.thinking_indicator_durations = deque(maxlen=max_samples)  # thinking sound duration (gap filled)

        # Counters
        self.transcript_count = 0
        self.error_count = 0
        self.total_requests = 0
        self.start_time = time.time()
        self.lock = Lock()

    def record_latency(self, latency_ms: float):
        """Record a latency measurement (overall transcript latency)"""
        with self.lock:
            self.latencies.append(latency_ms)
            self.total_requests += 1

    def record_n8n_response_latency(self, latency_s: float):
        """Record LLM response latency (time to first response)"""
        with self.lock:
            self.n8n_response_latencies.append(latency_s)

    def record_n8n_first_chunk_latency(self, latency_s: float):
        """Record LLM first chunk latency (time to first text chunk)"""
        with self.lock:
            self.n8n_first_chunk_latencies.append(latency_s)

    def record_tts_first_byte_latency(self, latency_s: float):
        """Record TTS first byte latency (time to first audio byte from Chatterbox)"""
        with self.lock:
            self.tts_first_byte_latencies.append(latency_s)

    # Phase 1: Speech → Transcription recording methods
    def record_whisper_connection_latency(self, latency_s: float):
        """Record WhisperX connection latency (user starts speaking → connected)"""
        with self.lock:
            self.whisper_connection_latencies.append(latency_s)

    def record_first_partial_transcript_latency(self, latency_s: float):
        """Record first partial transcript latency (WhisperX connected → first partial)"""
        with self.lock:
            self.first_partial_transcript_latencies.append(latency_s)

    def record_transcription_duration(self, latency_s: float):
        """Record transcription duration (first partial → final transcript)"""
        with self.lock:
            self.transcription_duration_latencies.append(latency_s)

    def record_silence_detection_latency(self, latency_ms: float):
        """Record silence detection latency (last audio → silence detected) in ms"""
        with self.lock:
            self.silence_detection_latencies.append(latency_ms)

    # Phase 2: AI Processing recording methods
    def record_ai_generation_latency(self, latency_s: float):
        """Record AI generation latency (webhook sent → response received)"""
        with self.lock:
            self.ai_generation_latencies.append(latency_s)

    def record_response_parsing_latency(self, latency_ms: float):
        """Record response parsing latency (response received → text extracted) in ms"""
        with self.lock:
            self.response_parsing_latencies.append(latency_ms)

    # Phase 3: TTS Generation recording methods
    def record_tts_queue_latency(self, latency_s: float):
        """Record TTS queue latency (text ready → TTS request sent)"""
        with self.lock:
            self.tts_queue_latencies.append(latency_s)

    def record_tts_generation_latency(self, latency_s: float):
        """Record TTS generation latency (TTS sent → all audio downloaded)"""
        with self.lock:
            self.tts_generation_latencies.append(latency_s)

    # Phase 4: Audio Playback recording methods
    def record_audio_playback_latency(self, latency_s: float):
        """Record audio playback latency (audio ready → playback complete)"""
        with self.lock:
            self.audio_playback_latencies.append(latency_s)

    def record_ffmpeg_processing_latency(self, latency_ms: float):
        """Record FFmpeg processing latency (conversion time) in ms"""
        with self.lock:
            self.ffmpeg_processing_latencies.append(latency_ms)

    # End-to-End recording methods
    def record_total_pipeline_latency(self, latency_s: float):
        """Record total pipeline latency (user starts speaking → audio playback complete)"""
        with self.lock:
            self.total_pipeline_latencies.append(latency_s)

    def record_time_to_first_audio(self, latency_s: float):
        """Record time to first audio (user starts speaking → first audio byte plays)"""
        with self.lock:
            self.time_to_first_audio_latencies.append(latency_s)

    def record_thinking_indicator_duration(self, duration_s: float):
        """Record thinking indicator duration (gap filled between transcript and TTS)"""
        with self.lock:
            self.thinking_indicator_durations.append(duration_s)

    def record_transcript(self):
        """Record a transcript completion"""
        with self.lock:
            self.transcript_count += 1

    def record_error(self):
        """Record an error"""
        with self.lock:
            self.error_count += 1
            self.total_requests += 1

    def _calc_stats(self, latencies_deque) -> dict:
        """Calculate statistics for a latency deque"""
        if not latencies_deque:
            return {"avg": 0, "p50": 0, "p95": 0, "p99": 0}

        sorted_latencies = sorted(latencies_deque)
        return {
            "avg": round(statistics.mean(sorted_latencies), 3),
            "p50": round(statistics.median(sorted_latencies), 3),
            "p95": round(sorted_latencies[int(len(sorted_latencies) * 0.95)], 3) if len(sorted_latencies) > 1 else round(sorted_latencies[0], 3),
            "p99": round(sorted_latencies[int(len(sorted_latencies) * 0.99)], 3) if len(sorted_latencies) > 1 else round(sorted_latencies[0], 3)
        }

    def get_metrics(self) -> dict:
        """Get current metrics snapshot"""
        with self.lock:
            # Overall transcript latency (ms) - legacy
            if not self.latencies:
                latency_stats = {"avg": 0, "p50": 0, "p95": 0, "p99": 0}
            else:
                sorted_latencies = sorted(self.latencies)
                latency_stats = {
                    "avg": int(statistics.mean(sorted_latencies)),
                    "p50": int(statistics.median(sorted_latencies)),
                    "p95": int(sorted_latencies[int(len(sorted_latencies) * 0.95)]) if len(sorted_latencies) > 1 else int(sorted_latencies[0]),
                    "p99": int(sorted_latencies[int(len(sorted_latencies) * 0.99)]) if len(sorted_latencies) > 1 else int(sorted_latencies[0])
                }

            # Legacy detailed latencies (seconds)
            n8n_response_stats = self._calc_stats(self.n8n_response_latencies)
            n8n_first_chunk_stats = self._calc_stats(self.n8n_first_chunk_latencies)
            tts_first_byte_stats = self._calc_stats(self.tts_first_byte_latencies)

            # Phase 1: Speech → Transcription (seconds)
            whisper_connection_stats = self._calc_stats(self.whisper_connection_latencies)
            first_partial_stats = self._calc_stats(self.first_partial_transcript_latencies)
            transcription_duration_stats = self._calc_stats(self.transcription_duration_latencies)

            # Silence detection in ms - convert to int stats
            silence_detection_stats = self._calc_stats(self.silence_detection_latencies)
            if silence_detection_stats["avg"] > 0:
                silence_detection_stats = {k: int(v) for k, v in silence_detection_stats.items()}

            # Phase 2: AI Processing
            ai_generation_stats = self._calc_stats(self.ai_generation_latencies)
            response_parsing_stats = self._calc_stats(self.response_parsing_latencies)
            if response_parsing_stats["avg"] > 0:
                response_parsing_stats = {k: int(v) for k, v in response_parsing_stats.items()}

            # Phase 3: TTS Generation (seconds)
            tts_queue_stats = self._calc_stats(self.tts_queue_latencies)
            tts_generation_stats = self._calc_stats(self.tts_generation_latencies)

            # Phase 4: Audio Playback (seconds)
            audio_playback_stats = self._calc_stats(self.audio_playback_latencies)
            ffmpeg_processing_stats = self._calc_stats(self.ffmpeg_processing_latencies)
            if ffmpeg_processing_stats["avg"] > 0:
                ffmpeg_processing_stats = {k: int(v) for k, v in ffmpeg_processing_stats.items()}

            # End-to-End (seconds)
            total_pipeline_stats = self._calc_stats(self.total_pipeline_latencies)
            time_to_first_audio_stats = self._calc_stats(self.time_to_first_audio_latencies)

            # UX Enhancement (seconds)
            thinking_indicator_stats = self._calc_stats(self.thinking_indicator_durations)

            error_rate = self.error_count / self.total_requests if self.total_requests > 0 else 0.0
            uptime = int(time.time() - self.start_time)

            return {
                # Legacy metrics
                "latency": latency_stats,
                "n8nResponseLatency": n8n_response_stats,
                "n8nFirstChunkLatency": n8n_first_chunk_stats,
                "ttsFirstByteLatency": tts_first_byte_stats,

                # Phase 1: Speech → Transcription
                "whisperConnectionLatency": whisper_connection_stats,
                "firstPartialTranscriptLatency": first_partial_stats,
                "transcriptionDuration": transcription_duration_stats,
                "silenceDetectionLatency": silence_detection_stats,

                # Phase 2: AI Processing
                "aiGenerationLatency": ai_generation_stats,
                "responseParsingLatency": response_parsing_stats,

                # Phase 3: TTS Generation
                "ttsQueueLatency": tts_queue_stats,
                "ttsGenerationLatency": tts_generation_stats,

                # Phase 4: Audio Playback
                "audioPlaybackLatency": audio_playback_stats,
                "ffmpegProcessingLatency": ffmpeg_processing_stats,

                # End-to-End
                "totalPipelineLatency": total_pipeline_stats,
                "timeToFirstAudio": time_to_first_audio_stats,

                # UX Enhancement
                "thinkingIndicatorDuration": thinking_indicator_stats,

                # Counters
                "transcriptCount": self.transcript_count,
                "errorRate": error_rate,
                "uptime": uptime
            }


# ============================================================
# DISCORD PLUGIN
# ============================================================

@plugin("discord")
class DiscordPlugin(PluginBase):
    """
    Discord bot plugin for VoxBridge agents.

    Each instance manages one Discord bot with its own token and connections.
    Multiple agents can have separate Discord bots running concurrently.

    Phase 1 Integration (Service Layer Foundation):
    - Service layer dependencies initialized after agent binding
    - Session tracking infrastructure for user → session mapping
    - MetricsTracker for performance monitoring
    - Cleanup enhanced in stop() method
    - Stub methods prepared for Phase 2 audio pipeline
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
        self.agent_id: Optional[UUID] = None
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
        self.metrics = MetricsTracker()

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

        # Phase 1: Initialize service layer dependencies
        # These are singletons shared across plugins but each plugin maintains its own reference
        try:
            # ConversationService (per-plugin instance for now, may change to singleton later)
            self.conversation_service = ConversationService()
            await self.conversation_service.start()

            # STT/LLM/TTS services (singletons for connection pooling)
            self.stt_service = get_stt_service()
            self.llm_service = get_llm_service()
            self.tts_service = get_tts_service()

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
            """
            Handle voice state changes (user joins/leaves voice channel).

            Phase 1: Basic logging only. Phase 2 will add audio pipeline integration.
            """
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

                        # Phase 2 TODO: Start audio receiving for this user
                        # await self._start_audio_receiving(member, voice_client)

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

                # Phase 1: Clean up user's session
                user_id = str(member.id)
                if user_id in self.active_sessions:
                    session_id = self.active_sessions[user_id]
                    await self._cleanup_session(user_id, session_id)

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

        Phase 1 Enhancement: Clean up all active sessions and service connections.
        """
        if not self.bot:
            logger.warning(f"⚠️  Discord bot for agent '{self.agent_name}' not initialized")
            return

        logger.info(f"🛑 Stopping Discord bot for agent '{self.agent_name}'")

        # Phase 1: Clean up active sessions before disconnecting voice
        for user_id in list(self.active_sessions.keys()):
            session_id = self.active_sessions.get(user_id)
            if session_id:
                await self._cleanup_session(user_id, session_id)

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

        Phase 1: Logging only. Phase 2 will implement TTS playback.

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

        # Phase 2 TODO: Implement TTS audio playback via Discord voice
        # This will use tts_service.synthesize_speech() and play via voice_client
        logger.info(
            f"🔊 [TODO Phase 2] Play TTS audio in Discord voice channel "
            f"(guild: {guild_id}, channel: {channel_id}, agent: {self.agent_name})"
        )

    # ============================================================
    # PHASE 1: STUB METHODS FOR PHASE 2
    # ============================================================

    async def _cleanup_session(self, user_id: str, session_id: str) -> None:
        """
        Clean up session resources when user leaves or session ends.

        Phase 1: Stub implementation (basic session removal).
        Phase 2: Will add STT disconnection, conversation finalization.

        Args:
            user_id: Discord user ID
            session_id: Session UUID
        """
        logger.info(
            f"🔄 Cleaning up session for user {user_id} (session: {session_id[:8]}...)"
        )

        # Remove from active sessions
        if user_id in self.active_sessions:
            del self.active_sessions[user_id]

        # Remove timing metadata
        if session_id in self.session_timings:
            del self.session_timings[session_id]

        # Phase 2 TODO: Disconnect STT service
        # if self.stt_service and await self.stt_service.is_connected(session_id):
        #     await self.stt_service.disconnect(session_id)

        # Phase 2 TODO: End conversation session
        # if self.conversation_service:
        #     await self.conversation_service.end_session(session_id, persist=True)

        logger.info(f"✅ Session cleanup complete for user {user_id}")

    async def _handle_user_speaking(
        self,
        user: discord.User,
        audio_data: bytes,
        voice_client: discord.VoiceClient
    ) -> None:
        """
        Handle audio data from user speaking in voice channel.

        Phase 1: Stub implementation (logging only).
        Phase 2: Will implement full STT → LLM → TTS pipeline.

        Args:
            user: Discord user who is speaking
            audio_data: Raw audio bytes from Discord
            voice_client: Voice client connection
        """
        user_id = str(user.id)

        # Phase 2 TODO: Get or create session
        # session_id = self.active_sessions.get(user_id)
        # if not session_id:
        #     session_id = str(uuid.uuid4())
        #     session = await self.conversation_service.get_or_create_session(
        #         session_id=session_id,
        #         user_id=user_id,
        #         agent_id=str(self.agent_id),
        #         channel_type="discord",
        #         user_name=user.name
        #     )
        #     self.active_sessions[user_id] = session_id

        # Phase 2 TODO: Send audio to STT service
        # if self.stt_service:
        #     if not await self.stt_service.is_connected(session_id):
        #         await self.stt_service.connect(session_id)
        #         await self.stt_service.register_callback(session_id, self._on_transcript)
        #     await self.stt_service.send_audio(session_id, audio_data)

        logger.debug(
            f"🎤 [TODO Phase 2] Audio received from {user.name} "
            f"({len(audio_data)} bytes)"
        )

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
