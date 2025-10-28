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
from src.services.llm_service import get_llm_service, LLMConfig, ProviderType
from src.services.tts_service import get_tts_service

# LLM exceptions for error handling
from src.llm import LLMError, LLMConnectionError, LLMTimeoutError

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
        self.metrics = MetricsTracker()

        # Phase 2: Audio receiver instances (one per voice client)
        self.audio_receivers: Dict[int, 'AudioReceiver'] = {}  # guild_id → AudioReceiver

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
            self.active_users = set()  # Users currently being processed

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

                # Start processing this user's audio
                if user_id not in self.active_users:
                    self.active_users.add(user_id)
                    stream_gen = audio_stream_generator(user_id)

                    # Phase 2: Use plugin's bot loop and _handle_user_speaking method
                    future = asyncio.run_coroutine_threadsafe(
                        self.plugin._handle_user_speaking(user, stream_gen, self.vc),
                        self.plugin.bot.loop
                    )
                    self.user_tasks[user_id] = future

            # Add Opus packet to user's queue
            try:
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

            # Remove from active users
            self.active_users.discard(user_id)

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
            self.active_users.clear()

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

            Phase 2: Registers audio receiver when user joins voice channel.
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
                        logger.info(f"🎤 Registered audio receiver for guild {after.channel.guild.id}")

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
            session_id = str(uuid.uuid4())
            self.active_sessions[user_id] = session_id

            # Initialize session timing tracker (Phase 1 integration)
            self.session_timings[session_id] = {
                't_start': t_start,
                't_whisper_connected': None,
                't_first_partial': None,
                't_transcription_complete': None
            }

            logger.info(f"📝 Created session {session_id[:8]}... for Discord user {username}")

            # TODO Phase 2 Tests: Broadcast speaker_started event via WebSocket
            # await broadcast_speaker_started(user_id, username)

            # Phase 1 integration: Create session in database via ConversationService
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
            max_speaking_time_ms = int(os.getenv('MAX_SPEAKING_TIME_MS', '45000'))  # 45s default

            # Track audio timing for silence detection
            last_audio_time = time.time()
            silence_detection_task = None
            finalized = False

            async def check_silence():
                """Background task to detect silence and trigger finalization"""
                nonlocal finalized
                check_interval = 0.1  # Check every 100ms

                while not finalized:
                    await asyncio.sleep(check_interval)

                    # Calculate elapsed time since last audio
                    elapsed_ms = (time.time() - last_audio_time) * 1000
                    speaking_duration_ms = (time.time() - t_start) * 1000

                    # Check for silence threshold
                    if elapsed_ms >= silence_threshold_ms:
                        logger.info(f"🔇 Silence detected after {elapsed_ms:.0f}ms for {username}")
                        self.metrics.record_silence_detection_latency(elapsed_ms)

                        # Finalize transcript
                        finalized = True
                        success = await self.stt_service.finalize_transcript(session_id)
                        if success:
                            logger.info(f"✅ Triggered final transcript for {username}")
                        else:
                            logger.warning(f"⚠️ Failed to finalize transcript for {username}")
                        break

                    # Check for max speaking time (safety limit)
                    if speaking_duration_ms >= max_speaking_time_ms:
                        logger.warning(f"⏰ Max speaking time ({max_speaking_time_ms}ms) reached for {username}")

                        # Force finalization
                        finalized = True
                        success = await self.stt_service.finalize_transcript(session_id)
                        if success:
                            logger.info(f"✅ Triggered final transcript (max time) for {username}")
                        break

            # Start silence detection task
            silence_detection_task = asyncio.create_task(check_silence())

            # Stream audio to STT with silence tracking
            try:
                async for audio_chunk in audio_stream:
                    # Update last audio timestamp
                    last_audio_time = time.time()

                    # Phase 1 integration: Send audio to STTService
                    await self.stt_service.send_audio(session_id, audio_chunk)
            finally:
                # Ensure finalization happens even if stream ends abruptly
                if not finalized:
                    logger.info(f"🔚 Audio stream ended for {username}, finalizing...")
                    await self.stt_service.finalize_transcript(session_id)
                    finalized = True

                # Cancel silence detection task
                if silence_detection_task and not silence_detection_task.done():
                    silence_detection_task.cancel()
                    try:
                        await silence_detection_task
                    except asyncio.CancelledError:
                        pass

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
                if timings['t_first_partial'] is None and timings['t_whisper_connected']:
                    t_now = time.time()
                    timings['t_first_partial'] = t_now
                    latency = t_now - timings['t_whisper_connected']
                    logger.info(f"⏱️ LATENCY [WhisperX connected → first partial]: {latency:.3f}s")
                    self.metrics.record_first_partial_transcript_latency(latency)

            # TODO Phase 2 Tests: Broadcast partial transcript via WebSocket
            # await broadcast_partial_transcript(user_id, username, text)
            return

        # Final transcript
        logger.info(f"✅ Final transcript (session={session_id[:8]}...): \"{text}\" (user={username})")

        # Record transcription duration (Phase 1 integration)
        if session_id in self.session_timings:
            timings = self.session_timings[session_id]
            t_now = time.time()
            timings['t_transcription_complete'] = t_now

            if timings['t_first_partial']:
                duration = t_now - timings['t_first_partial']
                logger.info(f"⏱️ LATENCY [first partial → transcription complete]: {duration:.3f}s")
                self.metrics.record_transcription_duration(duration)

        # TODO Phase 2 Tests: Broadcast final transcript via WebSocket
        # await broadcast_final_transcript(user_id, username, text)
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

            try:
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

                        # Parse n8n response
                        response_data = response.json()

                        # Handle various n8n response formats
                        if isinstance(response_data, dict):
                            full_response = (
                                response_data.get('response') or
                                response_data.get('output') or
                                response_data.get('text') or
                                str(response_data)
                            )
                        elif isinstance(response_data, str):
                            full_response = response_data
                        else:
                            full_response = str(response_data)

                        logger.info(f"✅ n8n response received: {len(full_response)} chars")

                except Exception as n8n_error:
                    logger.error(f"❌ n8n webhook fallback failed: {n8n_error}", exc_info=True)
                    raise LLMError(f"Both LLM providers and n8n webhook failed. LLM: {e}, n8n: {n8n_error}") from n8n_error

            # Phase 1 integration: Add assistant message to conversation
            await self.conversation_service.add_message(
                session_id=session_id,
                role='assistant',
                content=full_response
            )

            # TODO Phase 2 Tests: Broadcast AI response via WebSocket
            # await broadcast_ai_response(full_response, is_final=True)

            # Phase 2: Synthesize and play TTS
            if guild_id and guild_id in self.voice_clients:
                voice_client = self.voice_clients[guild_id]
                await self._play_tts(full_response, voice_client, session_id)
            else:
                logger.warning(f"⚠️ Cannot play TTS: no voice client for guild {guild_id}")

        except Exception as e:
            logger.error(f"❌ Error generating LLM response (session={session_id[:8]}...): {e}", exc_info=True)
            self.metrics.record_error()

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

            # Phase 1 integration: Synthesize using TTSService (non-streaming for Discord)
            audio_bytes = await self.tts_service.synthesize_speech(
                session_id=session_id,
                text=text,
                voice_id=self.agent.tts_voice or os.getenv('CHATTERBOX_VOICE_ID', 'default'),
                speed=self.agent.tts_rate or 1.0,
                stream=False,  # Discord needs complete audio file
                callback=None
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
                if ffmpeg_latency_ms > 1.0:
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

            # Phase 2: Cleanup audio receiver for this user
            # Find guild_id for this user's voice connection
            for guild_id, receiver in self.audio_receivers.items():
                if user_id in receiver.active_users:
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
        channel_id: int
    ) -> Dict[str, Any]:
        """
        Join a Discord voice channel.

        Phase 3: HTTP API integration

        Args:
            guild_id: Discord guild (server) ID
            channel_id: Discord voice channel ID

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
                'guild_id': guild_id,
                'guild_name': guild.name if guild else None,
                'channel_id': channel.id if channel else None,
                'channel_name': channel.name if channel else None,
                'connected': voice_client.is_connected(),
            })

        return {
            'agent_id': str(self.agent_id),
            'agent_name': self.agent_name,
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
