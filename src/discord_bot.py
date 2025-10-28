#!/usr/bin/env python3
"""
============================================================
VoxBridge - Discord Voice Bridge Service (Phase 5.6 Refactored)
Bridges Discord voice channels to STT/LLM/TTS processing:
- Join/leave voice channels
- Speech-to-Text (WhisperX via STTService)
- LLM generation (via LLMService with hybrid routing)
- Text-to-Speech (Chatterbox via TTSService)
- Session-based architecture with ConversationService
============================================================
"""

import asyncio
import logging
import os
import signal
import tempfile
import uuid
from datetime import datetime
from typing import Optional, Dict

import discord
from discord.ext import commands, voice_recv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import httpx
import uvicorn
from dotenv import load_dotenv

# VoxBridge 2.0 Service Layer
from src.services.conversation_service import ConversationService
from src.services.stt_service import get_stt_service, STTService
from src.services.llm_service import get_llm_service, LLMService, LLMConfig, ProviderType
from src.services.tts_service import get_tts_service, TTSService
from src.services.plugin_manager import get_plugin_manager
from src.routes.agent_routes import router as agent_router
from src.routes.session_routes import router as session_router
from src.routes.discord_plugin_routes import router as discord_plugin_router

# LLM exceptions for error handling
from src.llm import LLMError, LLMConnectionError, LLMTimeoutError

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
PORT = int(os.getenv('PORT', '4900'))

if not DISCORD_TOKEN:
    logger.error("❌ DISCORD_TOKEN not set in environment")
    exit(1)

# ============================================================
# METRICS TRACKING (Keep existing implementation)
# ============================================================

import time
import statistics
from collections import deque
from threading import Lock

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

# Global metrics tracker
metrics_tracker = MetricsTracker()

# ============================================================
# DISCORD BOT SETUP
# ============================================================

# Discord bot with necessary intents
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.guild_messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Voice connection state
voice_client: Optional[discord.VoiceClient] = None

# ============================================================
# SERVICE LAYER INITIALIZATION (VoxBridge 2.0)
# ============================================================

# Initialize services
conversation_service = ConversationService()
stt_service = get_stt_service()
llm_service = get_llm_service()
tts_service = get_tts_service()
plugin_manager = get_plugin_manager()

# Active sessions: Discord user_id → session_id
active_discord_sessions: Dict[str, str] = {}

# Session timing tracking for metrics
session_timings: Dict[str, Dict[str, float]] = {}

# ============================================================
# FAST API SETUP
# ============================================================

app = FastAPI(title="VoxBridge API")

# Include agent management routes (VoxBridge 2.0)
app.include_router(agent_router)

# Include session/conversation management routes (VoxBridge 2.0 Phase 4)
app.include_router(session_router)

# Include Discord plugin voice control routes (VoxBridge 2.0 Phase 3)
app.include_router(discord_plugin_router)

# Pydantic models for API
class JoinVoiceRequest(BaseModel):
    channelId: str
    guildId: str

class SpeakRequest(BaseModel):
    output: dict
    options: dict = {}

# ============================================================
# SERVICE STARTUP/SHUTDOWN
# ============================================================

@app.on_event("startup")
async def startup_services():
    """Start background service tasks"""
    await conversation_service.start()
    await plugin_manager.start_resource_monitoring()
    logger.info("✅ Services started")

@app.on_event("shutdown")
async def shutdown_services():
    """Cleanup services on shutdown"""
    logger.info("🛑 Shutting down services...")

    await conversation_service.stop()
    await llm_service.close()
    await tts_service.close()
    await stt_service.shutdown()
    await plugin_manager.shutdown()

    logger.info("✅ Services shutdown complete")

# ============================================================
# DISCORD BOT EVENTS
# ============================================================

@bot.event
async def on_ready():
    """Bot ready event"""
    logger.info("=" * 60)
    logger.info(f"✅ Discord bot logged in as {bot.user.name}")
    logger.info(f"🎙️ Voice service ready with VoxBridge 2.0 service layer")
    logger.info("=" * 60)

@bot.event
async def on_error(event, *args, **kwargs):
    """Bot error handler"""
    logger.error(f"❌ Discord bot error in {event}: {args} {kwargs}")

# ============================================================
# VOICE AUDIO RECEIVER (Refactored for Service Layer)
# ============================================================

class AudioReceiver(voice_recv.AudioSink):
    """Custom audio sink to receive voice data and route to STTService"""

    def __init__(self, vc, loop):
        super().__init__()
        self.vc = vc
        self.loop = loop  # Event loop for thread-safe task scheduling
        self.user_buffers: Dict[str, asyncio.Queue] = {}  # user_id → audio chunk queue
        self.user_tasks: Dict[str, asyncio.Task] = {}    # user_id → processing task
        self.active_users = set()  # Users currently being processed

    def write(self, user, data: voice_recv.VoiceData):
        """
        Receive audio data from Discord

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
                future = asyncio.run_coroutine_threadsafe(
                    on_user_speaking_start(user_id, username, stream_gen),
                    self.loop
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
        """Cleanup a specific user's audio stream"""
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
        """Cleanup audio sink"""
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

# Global audio receiver instance (set when joining voice)
audio_receiver: Optional[AudioReceiver] = None

# ============================================================
# VOICE PROCESSING (VoxBridge 2.0 Service Integration)
# ============================================================

async def on_user_speaking_start(user_id: str, username: str, audio_stream):
    """
    Handle user starting to speak (VoxBridge 2.0 service integration)

    This replaces SpeakerManager.on_speaking_start with service-based routing.

    Args:
        user_id: Discord user ID
        username: Discord username
        audio_stream: Async generator of audio chunks
    """
    logger.info(f"🎤 {username} ({user_id}) started speaking")

    try:
        # Record pipeline start time
        t_start = time.time()
        session_id = str(uuid.uuid4())
        active_discord_sessions[user_id] = session_id

        # Initialize session timing tracker
        session_timings[session_id] = {
            't_start': t_start,
            't_whisper_connected': None,
            't_first_partial': None,
            't_transcription_complete': None
        }

        logger.info(f"📝 Created session {session_id[:8]}... for Discord user {username}")

        # Broadcast speaker started event
        await broadcast_speaker_started(user_id, username)

        # Get default agent for this user
        # TODO: Implement per-user agent selection from database
        # For now, use environment variable or first available agent
        from src.services.agent_service import AgentService

        default_agent_id = os.getenv('DEFAULT_AGENT_ID')
        if default_agent_id:
            agent = await AgentService.get_agent(default_agent_id)
        else:
            agent = await AgentService.get_default_agent()
            if not agent:
                # Fallback: Get first available agent
                agents = await AgentService.get_all_agents()
                agent = agents[0] if agents else None

        if not agent:
            logger.error(f"❌ No agent available for user {username}")
            return

        logger.info(f"🤖 Using agent: {agent.name} for Discord user {username}")

        # Create session in database via ConversationService
        session = await conversation_service.get_or_create_session(
            session_id=session_id,
            user_id=user_id,
            agent_id=str(agent.id),
            channel_type="discord",
            user_name=username,
            title=f"Discord conversation with {username}"
        )

        # Connect STT service for this session
        t_before_whisper = time.time()
        success = await stt_service.connect(session_id, os.getenv('WHISPER_SERVER_URL'))

        if not success:
            logger.error(f"❌ Failed to connect STT for session {session_id[:8]}...")
            await cleanup_session(user_id, session_id)
            return

        t_after_whisper = time.time()
        whisper_latency = t_after_whisper - t_before_whisper
        session_timings[session_id]['t_whisper_connected'] = t_after_whisper
        logger.info(f"⏱️ LATENCY [speech start → WhisperX connected]: {whisper_latency:.3f}s")
        metrics_tracker.record_whisper_connection_latency(whisper_latency)

        # Register STT callback
        await stt_service.register_callback(
            session_id=session_id,
            callback=lambda text, is_final, metadata: on_stt_transcript(session_id, user_id, username, text, is_final, metadata)
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
                    metrics_tracker.record_silence_detection_latency(elapsed_ms)

                    # Finalize transcript
                    finalized = True
                    success = await stt_service.finalize_transcript(session_id)
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
                    success = await stt_service.finalize_transcript(session_id)
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

                # Send audio to STTService
                await stt_service.send_audio(session_id, audio_chunk)
        finally:
            # Ensure finalization happens even if stream ends abruptly
            if not finalized:
                logger.info(f"🔚 Audio stream ended for {username}, finalizing...")
                await stt_service.finalize_transcript(session_id)
                finalized = True

            # Cancel silence detection task
            if silence_detection_task and not silence_detection_task.done():
                silence_detection_task.cancel()
                try:
                    await silence_detection_task
                except asyncio.CancelledError:
                    pass

    except Exception as e:
        logger.error(f"❌ Error in on_user_speaking_start for {username}: {e}", exc_info=True)
        # Cleanup on error
        if user_id in active_discord_sessions:
            session_id = active_discord_sessions[user_id]
            await cleanup_session(user_id, session_id)

async def on_stt_transcript(session_id: str, user_id: str, username: str, text: str, is_final: bool, metadata: Dict):
    """
    Callback for STT transcriptions (VoxBridge 2.0)

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

        # Record first partial latency
        if session_id in session_timings:
            timings = session_timings[session_id]
            if timings['t_first_partial'] is None and timings['t_whisper_connected']:
                t_now = time.time()
                timings['t_first_partial'] = t_now
                latency = t_now - timings['t_whisper_connected']
                logger.info(f"⏱️ LATENCY [WhisperX connected → first partial]: {latency:.3f}s")
                metrics_tracker.record_first_partial_transcript_latency(latency)

        # Broadcast partial transcript
        await broadcast_partial_transcript(user_id, username, text)
        return

    # Final transcript
    logger.info(f"✅ Final transcript (session={session_id[:8]}...): \"{text}\" (user={username})")

    # Record transcription duration
    if session_id in session_timings:
        timings = session_timings[session_id]
        t_now = time.time()
        timings['t_transcription_complete'] = t_now

        if timings['t_first_partial']:
            duration = t_now - timings['t_first_partial']
            logger.info(f"⏱️ LATENCY [first partial → transcription complete]: {duration:.3f}s")
            metrics_tracker.record_transcription_duration(duration)

    # Broadcast final transcript
    await broadcast_final_transcript(user_id, username, text)
    metrics_tracker.record_transcript()

    # Add user message to conversation
    await conversation_service.add_message(
        session_id=session_id,
        role='user',
        content=text,
        metadata={'stt_confidence': metadata.get('confidence')}
    )

    # Generate LLM response
    await generate_and_play_response(session_id, user_id, username, text)

async def generate_and_play_response(session_id: str, user_id: str, username: str, user_text: str):
    """
    Generate LLM response and play via TTS (VoxBridge 2.0)

    Args:
        session_id: Session UUID
        user_id: Discord user ID
        username: Discord username
        user_text: User's transcribed text
    """
    try:
        t_llm_start = time.time()

        # Get conversation context from ConversationService
        messages = await conversation_service.get_conversation_context(
            session_id=session_id,
            limit=10,
            include_system_prompt=True
        )

        # Get agent config
        agent = await conversation_service.get_agent_config(session_id)

        # Convert to LLM format
        llm_messages = [{'role': msg.role, 'content': msg.content} for msg in messages]

        # Build LLM config
        llm_config = LLMConfig(
            provider=ProviderType(agent.llm_provider),
            model=agent.llm_model,
            temperature=agent.temperature,
            system_prompt=agent.system_prompt
        )

        logger.info(f"🤖 Generating LLM response (session={session_id[:8]}..., provider={llm_config.provider.value})")

        # Stream response from LLM
        full_response = ""
        first_chunk = True

        async def on_llm_chunk(chunk: str):
            nonlocal full_response, first_chunk
            full_response += chunk

            # Record first chunk latency
            if first_chunk:
                t_first_chunk = time.time()
                latency = t_first_chunk - t_llm_start
                logger.info(f"⏱️ LATENCY [LLM first chunk]: {latency:.3f}s")
                metrics_tracker.record_n8n_first_chunk_latency(latency)
                first_chunk = False

        try:
            await llm_service.generate_response(
                session_id=session_id,
                messages=llm_messages,
                config=llm_config,
                stream=True,
                callback=on_llm_chunk
            )

            # Record total LLM latency
            t_llm_complete = time.time()
            llm_duration = t_llm_complete - t_llm_start
            logger.info(f"⏱️ LATENCY [total LLM generation]: {llm_duration:.3f}s")
            metrics_tracker.record_ai_generation_latency(llm_duration)

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
                            'name': agent.name,
                            'systemPrompt': agent.system_prompt,
                            'temperature': agent.temperature,
                            'model': agent.llm_model
                        }
                    }

                    response = await client.post(n8n_webhook_url, json=payload)
                    response.raise_for_status()

                    t_n8n_complete = time.time()
                    n8n_duration = t_n8n_complete - t_llm_start
                    logger.info(f"⏱️ LATENCY [n8n webhook]: {n8n_duration:.3f}s")
                    metrics_tracker.record_ai_generation_latency(n8n_duration)

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

        # Add assistant message to conversation
        await conversation_service.add_message(
            session_id=session_id,
            role='assistant',
            content=full_response
        )

        # Broadcast AI response
        await broadcast_ai_response(full_response, is_final=True)

        # Synthesize and play TTS
        await synthesize_and_play_discord(session_id, user_id, username, full_response, agent)

    except Exception as e:
        logger.error(f"❌ Error generating LLM response (session={session_id[:8]}...): {e}", exc_info=True)
        metrics_tracker.record_error()

async def synthesize_and_play_discord(session_id: str, user_id: str, username: str, text: str, agent):
    """
    Synthesize speech and play in Discord voice channel (VoxBridge 2.0)

    Args:
        session_id: Session UUID
        user_id: Discord user ID
        username: Discord username
        text: Text to synthesize
        agent: Agent model with TTS settings
    """
    if not voice_client or not voice_client.is_connected():
        logger.warning("⚠️ Not in voice channel, cannot play TTS")
        return

    try:
        t_tts_start = time.time()

        # Synthesize (non-streaming for Discord playback - need complete file)
        audio_bytes = await tts_service.synthesize_speech(
            session_id=session_id,
            text=text,
            voice_id=agent.tts_voice or os.getenv('CHATTERBOX_VOICE_ID', 'default'),
            speed=agent.tts_rate or 1.0,
            stream=False,  # Discord needs complete audio file
            callback=None
        )

        if not audio_bytes:
            logger.error("❌ TTS synthesis failed, no audio received")
            return

        t_tts_complete = time.time()
        tts_duration = t_tts_complete - t_tts_start
        logger.info(f"⏱️ LATENCY [TTS generation]: {tts_duration:.3f}s")
        metrics_tracker.record_tts_generation_latency(tts_duration)

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
                metrics_tracker.record_ffmpeg_processing_latency(ffmpeg_latency_ms)

            # Play audio
            voice_client.play(audio_source)
            logger.info(f"🔊 Playing TTS audio ({len(audio_bytes):,} bytes)")

            # Wait for playback to complete
            while voice_client.is_playing():
                await asyncio.sleep(0.1)

            t_playback_complete = time.time()
            playback_duration = t_playback_complete - t_playback_start
            logger.info(f"⏱️ LATENCY [audio playback]: {playback_duration:.3f}s")
            metrics_tracker.record_audio_playback_latency(playback_duration)

            # Record total pipeline latency
            if session_id in session_timings:
                t_start = session_timings[session_id]['t_start']
                total_latency = t_playback_complete - t_start
                logger.info(f"⏱️ ⭐⭐⭐ TOTAL PIPELINE LATENCY: {total_latency:.3f}s")
                metrics_tracker.record_total_pipeline_latency(total_latency)

        finally:
            # Cleanup temp file
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"⚠️ Failed to delete temp file {temp_path}: {e}")

    except Exception as e:
        logger.error(f"❌ Error with TTS playback: {e}", exc_info=True)

async def cleanup_session(user_id: str, session_id: str):
    """
    Cleanup session when user stops speaking

    Args:
        user_id: Discord user ID
        session_id: Session UUID
    """
    logger.info(f"🧹 Cleaning up session {session_id[:8]}... for user {user_id}")

    try:
        # Disconnect STT
        await stt_service.disconnect(session_id)

        # End session in database (mark inactive)
        await conversation_service.end_session(session_id, persist=True)

        # Remove from active sessions
        if user_id in active_discord_sessions:
            del active_discord_sessions[user_id]

        # Remove timing data
        if session_id in session_timings:
            del session_timings[session_id]

        # Cleanup audio receiver
        if audio_receiver:
            audio_receiver.cleanup_user(user_id)

        logger.info(f"✅ Session {session_id[:8]}... cleaned up")

    except Exception as e:
        logger.error(f"❌ Error cleaning up session {session_id[:8]}...: {e}", exc_info=True)

# ============================================================
# VOICE CHANNEL OPERATIONS
# ============================================================

@app.post("/voice/join")
async def join_voice(request: JoinVoiceRequest):
    """
    Join a Discord voice channel

    Args:
        request: Join voice channel request

    Returns:
        Success response with channel info
    """
    global voice_client, audio_receiver

    logger.info(f"📞 JOIN request - Channel: {request.channelId}, Guild: {request.guildId}")

    try:
        # Fetch the voice channel
        logger.info("   🔍 Fetching channel from Discord...")
        channel = bot.get_channel(int(request.channelId))

        if not channel:
            channel = await bot.fetch_channel(int(request.channelId))

        if not isinstance(channel, discord.VoiceChannel):
            raise HTTPException(status_code=400, detail="Invalid voice channel")

        logger.info(f"   ✅ Channel found: {channel.name}")

        # Join voice channel
        logger.info("   🔌 Joining voice channel...")
        voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)

        logger.info("   👂 Setting up voice listeners...")

        # Set up voice receiving
        loop = asyncio.get_running_loop()
        audio_receiver = AudioReceiver(voice_client, loop)
        voice_client.listen(audio_receiver)

        logger.info(f"✅ JOIN complete - Now listening in {channel.name}\n")

        return {
            "success": True,
            "message": f"Joined voice channel: {channel.name}",
            "channelId": request.channelId
        }

    except Exception as e:
        logger.error(f"❌ Error joining voice channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/voice/leave")
async def leave_voice():
    """
    Leave the current voice channel

    Returns:
        Success response
    """
    global voice_client, audio_receiver

    logger.info("📞 LEAVE request received")

    if not voice_client:
        raise HTTPException(status_code=400, detail="Not currently in a voice channel")

    try:
        # Cleanup all active sessions
        for user_id in list(active_discord_sessions.keys()):
            session_id = active_discord_sessions[user_id]
            await cleanup_session(user_id, session_id)

        # Cleanup audio receiver
        if audio_receiver:
            audio_receiver.cleanup()
            audio_receiver = None

        # Disconnect from voice
        await voice_client.disconnect()
        voice_client = None

        logger.info("✅ Left voice channel\n")
        return {"success": True, "message": "Left voice channel"}

    except Exception as e:
        logger.error(f"❌ Error leaving voice channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# HEALTH & STATUS ENDPOINTS
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "botReady": bot.is_ready(),
        "inVoiceChannel": voice_client is not None and voice_client.is_connected(),
        "activeSessions": len(active_discord_sessions),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/status")
async def get_status():
    """Detailed status information"""
    # Get channel info if connected
    channel_info = {
        "connected": False,
        "channelId": None,
        "channelName": None,
        "guildId": None,
        "guildName": None
    }

    if voice_client and voice_client.is_connected():
        channel = voice_client.channel
        channel_info = {
            "connected": True,
            "channelId": str(channel.id) if channel else None,
            "channelName": channel.name if channel else None,
            "guildId": str(channel.guild.id) if channel and channel.guild else None,
            "guildName": channel.guild.name if channel and channel.guild else None
        }

    # Get service health
    llm_provider_status = await llm_service.get_provider_status()
    tts_health = await tts_service.test_tts_health()
    stt_metrics = await stt_service.get_metrics()

    # Query GPU device information from actual services
    whisperx_device = "Unknown"
    chatterbox_device = "Unknown"

    # Query Chatterbox TTS for GPU info
    try:
        chatterbox_base = tts_service.chatterbox_url.replace('/v1', '')
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{chatterbox_base}/health")
            if response.status_code == 200:
                health_data = response.json()
                device = health_data.get('device', 'cpu')

                if device == 'cuda':
                    # Try to get GPU memory info from health response
                    memory_info = health_data.get('memory_info', {})
                    gpu_mem_mb = memory_info.get('gpu_memory_allocated_mb', 0)

                    # If we have GPU memory, we know it's CUDA
                    if gpu_mem_mb > 0:
                        # Chatterbox doesn't expose gpu_name, so use generic label
                        chatterbox_device = "CUDA GPU"
                    else:
                        chatterbox_device = "CUDA"
                else:
                    chatterbox_device = device.upper()

                logger.info(f"✅ Chatterbox device: {chatterbox_device}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to query Chatterbox device info: {e}")
        chatterbox_device = "Unknown"

    # Query WhisperX for GPU info
    try:
        whisperx_url = "http://whisperx:4902"
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{whisperx_url}/health")
            if response.status_code == 200:
                health_data = response.json()
                device = health_data.get('device')
                if device:
                    if device == 'cuda':
                        gpu_name = health_data.get('gpu_name', 'CUDA GPU')
                        if "RTX" in gpu_name:
                            whisperx_device = gpu_name.split("NVIDIA")[-1].strip().split("GeForce")[-1].strip()
                        else:
                            whisperx_device = gpu_name
                    else:
                        whisperx_device = device.upper()

                    logger.info(f"✅ WhisperX device: {whisperx_device}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to query WhisperX device info: {e}")
        whisperx_device = "Unknown"

    return {
        "bot": {
            "username": bot.user.name if bot.user else "Not ready",
            "id": str(bot.user.id) if bot.user else None,
            "ready": bot.is_ready()
        },
        "voice": channel_info,
        "speaker": {
            "locked": False,  # No longer applicable with session-based routing
            "activeSpeaker": None,
            "speakingDuration": 0,
            "silenceDuration": 0
        },
        "whisperx": {
            "serverConfigured": bool(os.getenv('WHISPER_SERVER_URL')),
            "serverUrl": os.getenv('WHISPER_SERVER_URL', '')
        },
        "services": {
            "chatterbox": tts_health,
            "chatterboxUrl": tts_service.chatterbox_url,
            "n8nWebhook": bool(os.getenv('N8N_WEBHOOK_URL')),
            "n8nWebhookUrl": os.getenv('N8N_WEBHOOK_URL', '')
        },
        "devices": {
            "whisperx": whisperx_device,
            "chatterbox": chatterbox_device
        },
        "sessions": {
            "active": len(active_discord_sessions),
            "total_cache": len(await conversation_service.get_active_sessions())
        },
        "serviceHealth": {
            "stt": {
                "active_connections": stt_metrics['active_connections'],
                "total_transcriptions": stt_metrics['total_transcriptions']
            },
            "llm": llm_provider_status,
            "tts": {
                "healthy": tts_health,
                "url": tts_service.chatterbox_url
            },
            "conversation": {
                "cache_size": len(await conversation_service.get_active_sessions())
            }
        }
    }

@app.get("/api/channels")
async def get_channels():
    """
    Get list of available voice channels across all guilds

    Returns:
        List of guilds with their voice channels
    """
    if not bot.is_ready():
        raise HTTPException(status_code=503, detail="Bot not ready")

    guilds_data = []
    for guild in bot.guilds:
        voice_channels = []
        for channel in guild.voice_channels:
            voice_channels.append({
                "id": str(channel.id),
                "name": channel.name,
                "userCount": len(channel.members)
            })

        guilds_data.append({
            "id": str(guild.id),
            "name": guild.name,
            "channels": voice_channels
        })

    return {"guilds": guilds_data}

@app.get("/api/metrics")
async def get_metrics():
    """
    Get performance metrics

    Returns:
        Performance metrics including latency, counts, error rate
    """
    return metrics_tracker.get_metrics()

@app.get("/api/plugins/stats")
async def get_plugin_stats():
    """
    Get plugin system statistics including resource usage

    Returns:
        Plugin manager stats with resource monitoring data
    """
    return plugin_manager.get_stats()

# ============================================================
# WEBSOCKET CONNECTION MANAGER
# ============================================================

class ConnectionManager:
    """Manage WebSocket connections for real-time updates"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"🔌 WebSocket client connected (total: {len(self.active_connections)})")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"🔌 WebSocket client disconnected (total: {len(self.active_connections)})")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        event_type = message.get('event', 'unknown')
        num_clients = len(self.active_connections)
        logger.info(f"📤 Broadcasting {event_type} to {num_clients} client(s)")

        dead_connections = []
        success_count = 0
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
                success_count += 1
            except Exception as e:
                logger.error(f"❌ Error sending to WebSocket client: {e}")
                dead_connections.append(connection)

        # Log results
        if success_count > 0:
            logger.info(f"✅ Sent {event_type} to {success_count}/{num_clients} client(s)")
        if dead_connections:
            logger.warning(f"⚠️ Removed {len(dead_connections)} dead connection(s)")

        # Remove dead connections
        for connection in dead_connections:
            self.disconnect(connection)

# Initialize connection manager
ws_manager = ConnectionManager()

# Set WebSocket manager for agent routes (VoxBridge 2.0)
from src.routes.agent_routes import set_websocket_manager
set_websocket_manager(ws_manager)

@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time event streaming

    Events emitted:
    - speaker_started: User begins speaking
    - speaker_stopped: User stops speaking
    - partial_transcript: Partial transcription update
    - final_transcript: Final transcription result
    - ai_response: AI response text
    - status_update: General status update
    """
    await ws_manager.connect(websocket)

    try:
        # Send initial status
        await websocket.send_json({
            "event": "status_update",
            "data": {
                "connected": True,
                "timestamp": datetime.now().isoformat()
            }
        })

        # Keep connection alive
        while True:
            try:
                # Wait for any client messages (ping/pong)
                data = await websocket.receive_text()

                # Echo back for ping/pong
                if data == "ping":
                    await websocket.send_json({"type": "pong"})

            except WebSocketDisconnect:
                break

    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
    finally:
        ws_manager.disconnect(websocket)

@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for browser voice streaming (VoxBridge 2.0 Phase 4)

    Protocol:
    - Client Query Params: ?session_id={uuid}&user_id={string}
    - Client → Server: Binary audio chunks (Opus, 100ms intervals)
    - Server → Client: JSON events

    Events emitted:
    - partial_transcript: Real-time transcription updates
    - final_transcript: Complete transcription
    - ai_response_chunk: AI response text chunks
    - ai_response_complete: AI response completion
    - error: Error messages
    """
    from src.voice.webrtc_handler import WebRTCVoiceHandler
    from uuid import UUID

    try:
        # Accept connection
        await websocket.accept()
        logger.info("🔌 WebSocket voice connection request received")

        # Parse query parameters
        query_params = websocket.query_params
        session_id_str = query_params.get('session_id')
        user_id = query_params.get('user_id')

        if not session_id_str or not user_id:
            await websocket.send_json({
                "event": "error",
                "data": {"message": "Missing session_id or user_id query parameters"}
            })
            await websocket.close()
            return

        # Parse UUID
        try:
            session_id = UUID(session_id_str)
        except ValueError:
            await websocket.send_json({
                "event": "error",
                "data": {"message": "Invalid session_id format (must be UUID)"}
            })
            await websocket.close()
            return

        logger.info(f"✅ WebSocket voice connection established: user={user_id}, session={session_id}")

        # Create handler and start processing
        handler = WebRTCVoiceHandler(websocket, user_id, session_id)
        await handler.start()

    except WebSocketDisconnect:
        logger.info("🔌 WebSocket voice connection closed")
    except Exception as e:
        logger.error(f"❌ WebSocket voice error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "event": "error",
                "data": {"message": f"Server error: {str(e)}"}
            })
        except:
            pass

# Helper functions to broadcast events from other parts of the code
async def broadcast_speaker_started(user_id: str, username: str):
    """Broadcast when a user starts speaking"""
    await ws_manager.broadcast({
        "event": "speaker_started",
        "data": {
            "userId": user_id,
            "username": username,
            "timestamp": datetime.now().isoformat()
        }
    })

async def broadcast_speaker_stopped(user_id: str, username: str, duration_ms: int):
    """Broadcast when a user stops speaking"""
    await ws_manager.broadcast({
        "event": "speaker_stopped",
        "data": {
            "userId": user_id,
            "username": username,
            "durationMs": duration_ms,
            "timestamp": datetime.now().isoformat()
        }
    })

async def broadcast_partial_transcript(user_id: str, username: str, text: str):
    """Broadcast partial transcription"""
    await ws_manager.broadcast({
        "event": "partial_transcript",
        "data": {
            "userId": user_id,
            "username": username,
            "text": text,
            "timestamp": datetime.now().isoformat()
        }
    })

async def broadcast_final_transcript(user_id: str, username: str, text: str):
    """Broadcast final transcription"""
    await ws_manager.broadcast({
        "event": "final_transcript",
        "data": {
            "userId": user_id,
            "username": username,
            "text": text,
            "timestamp": datetime.now().isoformat()
        }
    })

async def broadcast_ai_response(text: str, is_final: bool = False):
    """Broadcast AI agent response"""
    message_id = str(uuid.uuid4())
    logger.info(f"📡 Broadcasting AI response: \"{text[:50]}...\" (id={message_id}, isFinal={is_final})")
    await ws_manager.broadcast({
        "event": "ai_response",
        "data": {
            "id": message_id,
            "text": text,
            "isFinal": is_final,
            "timestamp": datetime.now().isoformat()
        }
    })

# ============================================================
# APPLICATION LIFECYCLE
# ============================================================

async def start_bot():
    """Start Discord bot"""
    logger.info("🔐 Logging in to Discord...")
    await bot.start(DISCORD_TOKEN)

async def start_api():
    """Start FastAPI server"""
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)

    logger.info("=" * 60)
    logger.info(f"🚀 Voice bot API listening on port {PORT}")
    logger.info(f"📍 Endpoints available:")
    logger.info(f"   POST /voice/join - Join voice channel")
    logger.info(f"   POST /voice/leave - Leave voice channel")
    logger.info(f"   GET  /health - Health check")
    logger.info(f"   GET  /status - Detailed status")
    logger.info(f"   WS   /ws/events - Real-time event stream (Discord)")
    logger.info(f"   WS   /ws/voice - Browser voice streaming (Phase 4)")
    logger.info("=" * 60)

    await server.serve()

async def shutdown():
    """Graceful shutdown"""
    logger.info("\n⚠️ Shutting down gracefully...")

    # Cleanup all active sessions
    for user_id in list(active_discord_sessions.keys()):
        session_id = active_discord_sessions[user_id]
        await cleanup_session(user_id, session_id)

    # Disconnect from voice
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()

    # Close bot
    await bot.close()

    logger.info("👋 Shutdown complete")

async def main():
    """Main application entry point"""
    # Get event loop
    loop = asyncio.get_running_loop()

    # Register signal handlers for graceful shutdown
    def handle_signal_sync(signum):
        """Handle shutdown signals (sync wrapper)"""
        logger.info(f"\n⚠️ Received signal {signum}")
        # Create shutdown task in the running loop
        asyncio.ensure_future(shutdown(), loop=loop)

    # Register handlers
    loop.add_signal_handler(signal.SIGTERM, lambda: handle_signal_sync(signal.SIGTERM))
    loop.add_signal_handler(signal.SIGINT, lambda: handle_signal_sync(signal.SIGINT))

    # Run bot and API concurrently
    try:
        await asyncio.gather(
            start_bot(),
            start_api()
        )
    except KeyboardInterrupt:
        await shutdown()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        await shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Interrupted by user")
