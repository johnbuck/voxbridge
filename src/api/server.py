"""
FastAPI Server
Main API server for VoxBridge 2.0

Extracted from discord_bot.py as part of Phase 6.4.1 - FastAPI Decoupling.
Provides HTTP/WebSocket API endpoints for voice control, monitoring, and agent management.
"""

import asyncio
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime
from typing import Optional, Dict

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# VoxBridge 2.0 Service Layer
from src.services.conversation_service import ConversationService
from src.services.stt_service import get_stt_service
from src.services.llm_service import get_llm_service, LLMConfig, ProviderType
from src.services.tts_service import get_tts_service
from src.services.plugin_manager import get_plugin_manager
from src.services.memory_service import MemoryService, get_global_embedding_config

# Configuration
from src.config.streaming import get_streaming_config, update_streaming_config, reset_streaming_config

# Route modules
from src.routes.agent_routes import router as agent_router, set_websocket_manager
from src.routes.session_routes import router as session_router
from src.routes.discord_plugin_routes import router as discord_plugin_router
from src.routes.llm_provider_routes import router as llm_provider_router
from src.routes.system_settings_routes import router as system_settings_router
from src.routes.memory_routes import router as memory_router

# LLM exceptions for error handling
from src.llm import LLMError, LLMConnectionError, LLMTimeoutError

logger = logging.getLogger(__name__)

# ============================================================
# METRICS TRACKING (Imported from discord_bot.py)
# ============================================================

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

        # Phase 8: Sentence-Level Streaming Metrics
        self.sentence_detection_latencies = deque(maxlen=max_samples)  # LLM chunk → sentence detected (ms)
        self.sentence_tts_latencies = deque(maxlen=max_samples)  # per-sentence TTS synthesis time (s)
        self.audio_queue_wait_latencies = deque(maxlen=max_samples)  # TTS complete → playback starts (ms)
        self.sentence_to_audio_latencies = deque(maxlen=max_samples)  # sentence detected → audio plays (s)

        # Counters
        self.transcript_count = 0
        self.error_count = 0
        self.total_requests = 0
        self.start_time = time.time()
        self.lock = Lock()

        # Phase 8: Streaming-specific counters
        self.sentences_detected = 0
        self.sentences_synthesized = 0
        self.sentences_failed = 0
        self.sentences_retried = 0
        self.interruption_count = 0
        self.streaming_sessions = 0

        # Last Turn Metrics (per-turn values, reset each conversation turn)
        self.last_turn_metrics = {
            'total_pipeline_latency': None,
            'time_to_first_audio': None,
            'transcription_duration': None,
            'ai_generation_latency': None,
            'tts_generation_latency': None,
            'tts_first_byte_latency': None,
            'whisper_connection_latency': None,
            'first_partial_transcript_latency': None,
            'silence_detection_latency': None,
            'tts_queue_latency': None,
            'audio_playback_latency': None,
            'thinking_indicator_duration': None
        }

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
            self.last_turn_metrics['tts_first_byte_latency'] = latency_s

    # Phase 1: Speech → Transcription recording methods
    def record_whisper_connection_latency(self, latency_s: float):
        """Record WhisperX connection latency (user starts speaking → connected)"""
        with self.lock:
            self.whisper_connection_latencies.append(latency_s)
            self.last_turn_metrics['whisper_connection_latency'] = latency_s

    def record_first_partial_transcript_latency(self, latency_s: float):
        """Record first partial transcript latency (WhisperX connected → first partial)"""
        with self.lock:
            self.first_partial_transcript_latencies.append(latency_s)
            self.last_turn_metrics['first_partial_transcript_latency'] = latency_s

    def record_transcription_duration(self, latency_s: float):
        """Record transcription duration (first partial → final transcript)"""
        with self.lock:
            self.transcription_duration_latencies.append(latency_s)
            self.last_turn_metrics['transcription_duration'] = latency_s

    def record_silence_detection_latency(self, latency_ms: float):
        """Record silence detection latency (last audio → silence detected) in ms"""
        with self.lock:
            self.silence_detection_latencies.append(latency_ms)
            self.last_turn_metrics['silence_detection_latency'] = latency_ms

    # Phase 2: AI Processing recording methods
    def record_ai_generation_latency(self, latency_s: float):
        """Record AI generation latency (webhook sent → response received)"""
        with self.lock:
            self.ai_generation_latencies.append(latency_s)
            self.last_turn_metrics['ai_generation_latency'] = latency_s

    def record_response_parsing_latency(self, latency_ms: float):
        """Record response parsing latency (response received → text extracted) in ms"""
        with self.lock:
            self.response_parsing_latencies.append(latency_ms)

    # Phase 3: TTS Generation recording methods
    def record_tts_queue_latency(self, latency_s: float):
        """Record TTS queue latency (text ready → TTS request sent)"""
        with self.lock:
            self.tts_queue_latencies.append(latency_s)
            self.last_turn_metrics['tts_queue_latency'] = latency_s

    def record_tts_generation_latency(self, latency_s: float):
        """Record TTS generation latency (TTS sent → all audio downloaded)"""
        with self.lock:
            self.tts_generation_latencies.append(latency_s)
            self.last_turn_metrics['tts_generation_latency'] = latency_s

    # Phase 4: Audio Playback recording methods
    def record_audio_playback_latency(self, latency_s: float):
        """Record audio playback latency (audio ready → playback complete)"""
        with self.lock:
            self.audio_playback_latencies.append(latency_s)
            self.last_turn_metrics['audio_playback_latency'] = latency_s

    def record_ffmpeg_processing_latency(self, latency_ms: float):
        """Record FFmpeg processing latency (conversion time) in ms"""
        with self.lock:
            self.ffmpeg_processing_latencies.append(latency_ms)

    # End-to-End recording methods
    def record_total_pipeline_latency(self, latency_s: float):
        """Record total pipeline latency (user starts speaking → audio playback complete)"""
        with self.lock:
            self.total_pipeline_latencies.append(latency_s)
            self.last_turn_metrics['total_pipeline_latency'] = latency_s

    def record_time_to_first_audio(self, latency_s: float):
        """Record time to first audio (user starts speaking → first audio byte plays)"""
        with self.lock:
            self.time_to_first_audio_latencies.append(latency_s)
            self.last_turn_metrics['time_to_first_audio'] = latency_s

    def record_thinking_indicator_duration(self, duration_s: float):
        """Record thinking indicator duration (gap filled between transcript and TTS)"""
        with self.lock:
            self.thinking_indicator_durations.append(duration_s)
            self.last_turn_metrics['thinking_indicator_duration'] = duration_s

    def record_transcript(self):
        """Record a transcript completion"""
        with self.lock:
            self.transcript_count += 1

    def record_error(self):
        """Record an error"""
        with self.lock:
            self.error_count += 1
            self.total_requests += 1

    # Phase 8: Sentence-Level Streaming recording methods
    def record_sentence_detection(self, latency_ms: float):
        """Record sentence detection latency (LLM chunk → sentence detected) in ms"""
        with self.lock:
            self.sentence_detection_latencies.append(latency_ms)
            self.sentences_detected += 1

    def record_sentence_tts(self, latency_s: float, success: bool = True):
        """Record per-sentence TTS synthesis latency (sentence → audio bytes) in seconds"""
        with self.lock:
            if success:
                self.sentence_tts_latencies.append(latency_s)
                self.sentences_synthesized += 1
            else:
                self.sentences_failed += 1

    def record_sentence_retry(self):
        """Record a sentence TTS retry"""
        with self.lock:
            self.sentences_retried += 1

    def record_audio_queue_wait(self, latency_ms: float):
        """Record audio queue wait latency (TTS complete → playback starts) in ms"""
        with self.lock:
            self.audio_queue_wait_latencies.append(latency_ms)

    def record_sentence_to_audio(self, latency_s: float):
        """Record sentence-to-audio latency (sentence detected → audio plays) in seconds"""
        with self.lock:
            self.sentence_to_audio_latencies.append(latency_s)

    def record_interruption(self):
        """Record a user interruption"""
        with self.lock:
            self.interruption_count += 1

    def record_streaming_session(self):
        """Record start of a streaming session"""
        with self.lock:
            self.streaming_sessions += 1

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

            # Phase 8: Sentence-Level Streaming Metrics
            sentence_detection_stats = self._calc_stats(self.sentence_detection_latencies)
            if sentence_detection_stats["avg"] > 0:
                sentence_detection_stats = {k: int(v) for k, v in sentence_detection_stats.items()}

            sentence_tts_stats = self._calc_stats(self.sentence_tts_latencies)

            audio_queue_wait_stats = self._calc_stats(self.audio_queue_wait_latencies)
            if audio_queue_wait_stats["avg"] > 0:
                audio_queue_wait_stats = {k: int(v) for k, v in audio_queue_wait_stats.items()}

            sentence_to_audio_stats = self._calc_stats(self.sentence_to_audio_latencies)

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

                # Phase 8: Sentence-Level Streaming Metrics
                "sentenceDetectionLatency": sentence_detection_stats,
                "sentenceTtsLatency": sentence_tts_stats,
                "audioQueueWaitLatency": audio_queue_wait_stats,
                "sentenceToAudioLatency": sentence_to_audio_stats,

                # Counters
                "transcriptCount": self.transcript_count,
                "errorRate": error_rate,
                "uptime": uptime,

                # Phase 8: Streaming-specific counters
                "sentencesDetected": self.sentences_detected,
                "sentencesSynthesized": self.sentences_synthesized,
                "sentencesFailed": self.sentences_failed,
                "sentencesRetried": self.sentences_retried,
                "interruptionCount": self.interruption_count,
                "streamingSessions": self.streaming_sessions,

                # Last Turn Metrics (per-turn, resets each conversation)
                "lastTurn": {
                    "totalPipelineLatency": self.last_turn_metrics['total_pipeline_latency'],
                    "timeToFirstAudio": self.last_turn_metrics['time_to_first_audio'],
                    "transcriptionDuration": self.last_turn_metrics['transcription_duration'],
                    "aiGenerationLatency": self.last_turn_metrics['ai_generation_latency'],
                    "ttsGenerationLatency": self.last_turn_metrics['tts_generation_latency'],
                    "ttsFirstByteLatency": self.last_turn_metrics['tts_first_byte_latency'],
                    "whisperConnectionLatency": self.last_turn_metrics['whisper_connection_latency'],
                    "firstPartialTranscriptLatency": self.last_turn_metrics['first_partial_transcript_latency'],
                    "silenceDetectionLatency": self.last_turn_metrics['silence_detection_latency'],
                    "ttsQueueLatency": self.last_turn_metrics['tts_queue_latency'],
                    "audioPlaybackLatency": self.last_turn_metrics['audio_playback_latency'],
                    "thinkingIndicatorDuration": self.last_turn_metrics['thinking_indicator_duration']
                }
            }

# Global metrics tracker
metrics_tracker = MetricsTracker()

# Global memory service singleton (initialized in startup)
_global_memory_service = None


def get_metrics_tracker() -> MetricsTracker:
    """
    Get the global metrics tracker instance.

    Used by plugins to share the same metrics instance with the API server,
    ensuring all recorded metrics are accessible via /api/metrics endpoint.

    Returns:
        MetricsTracker: The global metrics tracker instance
    """
    return metrics_tracker


# ============================================================
# SERVICE LAYER INITIALIZATION (VoxBridge 2.0)
# ============================================================

# Initialize services
# ConversationService initialized in startup event (requires async factory for MemoryService support)
conversation_service = None
stt_service = get_stt_service()
llm_service = get_llm_service()
tts_service = get_tts_service()
plugin_manager = get_plugin_manager()

# VoxBridge 2.0 Phase 2: Memory System with database embedding config
# Initialized in startup_event() to avoid asyncio event loop conflicts
memory_service: Optional[MemoryService] = None

# ============================================================
# FAST API SETUP
# ============================================================

app = FastAPI(
    title="VoxBridge API",
    description="Multi-agent voice platform with plugin support",
    version="2.0.0"
)

# CORS middleware for cross-origin WebSocket and HTTP requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4903", "http://localhost:4900"],  # Frontend and backend
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Include agent management routes (VoxBridge 2.0)
app.include_router(agent_router)

# Include session/conversation management routes (VoxBridge 2.0 Phase 4)
app.include_router(session_router)

# Include Discord plugin voice control routes (VoxBridge 2.0 Phase 3)
app.include_router(discord_plugin_router)

# Include LLM provider management routes (VoxBridge 2.0 Phase 6.5.4)
app.include_router(llm_provider_router)

# Include system settings routes (VoxBridge 2.0 Phase 2 - Memory System)
app.include_router(system_settings_router)

# Include memory management routes (VoxBridge 2.0 Phase 2 - User-Facing Features)
app.include_router(memory_router)

# Pydantic models for API
class JoinVoiceRequest(BaseModel):
    channelId: str
    guildId: str

class SpeakRequest(BaseModel):
    output: dict
    options: dict = {}

# ============================================================
# DEPENDENCY INJECTION PROVIDERS
# ============================================================

def get_conversation_service() -> ConversationService:
    """
    Dependency injection provider for ConversationService singleton.

    Returns the global ConversationService instance initialized at startup.
    Ensures all WebSocket connections share the same conversation cache,
    enabling multi-turn conversations.

    Returns:
        ConversationService: The global singleton instance

    Raises:
        RuntimeError: If accessed before startup_services() completes

    Usage:
        @app.websocket("/ws/voice")
        async def endpoint(
            websocket: WebSocket,
            service: ConversationService = Depends(get_conversation_service)
        ):
            # service is the global singleton
    """
    if conversation_service is None:
        raise RuntimeError(
            "ConversationService not initialized. "
            "This indicates startup_services() was not called or failed. "
            "Check startup logs for initialization errors."
        )
    return conversation_service

# ============================================================
# BACKGROUND WORKERS
# ============================================================

async def _run_summarization_worker(memory_service):
    """
    Background worker that runs memory summarization periodically.

    Phase 3: Memory Summarization
    - Runs every summarization_interval_hours (default: 24)
    - Finds clusters of related old memories
    - Summarizes clusters into single facts
    """
    from src.services.memory_service import MemoryService

    interval_hours = memory_service.summarization_interval_hours
    interval_seconds = interval_hours * 3600

    # Wait a bit on startup to let things settle
    await asyncio.sleep(60)

    logger.info(f"📦 Summarization worker running every {interval_hours}h")

    while True:
        try:
            stats = await memory_service.run_summarization_cycle()
            if not stats.get("skipped"):
                logger.info(f"📦 Summarization cycle stats: {stats}")
        except Exception as e:
            logger.error(f"❌ Summarization worker error: {e}")

        # Wait for next cycle
        await asyncio.sleep(interval_seconds)


# ============================================================
# SERVICE STARTUP/SHUTDOWN
# ============================================================

@app.on_event("startup")
async def startup_services():
    """Start background service tasks"""
    global memory_service, conversation_service
    logger.info("🚀 Starting VoxBridge services...")

    # VoxBridge 2.0 Phase 2: Initialize MemoryService FIRST (singleton pattern)
    # Dispose any old database connections to prevent event loop conflicts
    from src.database.session import engine
    await engine.dispose()
    logger.info("🔄 Database engine disposed (preparing for fresh connections)")

    global _global_memory_service
    db_embedding_config = await get_global_embedding_config()
    memory_service = MemoryService(db_embedding_config=db_embedding_config, ws_manager=ws_manager)
    _global_memory_service = memory_service  # Store for metrics endpoint access
    logger.info("🧠 Global MemoryService singleton initialized")

    # Start memory extraction queue processor
    asyncio.create_task(memory_service.process_extraction_queue())
    logger.info("🧠 Memory extraction queue processor started")

    # Start memory summarization worker (Phase 3)
    asyncio.create_task(_run_summarization_worker(memory_service))
    logger.info("📦 Memory summarization worker started")

    # Initialize ConversationService with global MemoryService singleton (dependency injection)
    from src.services.factory import create_conversation_service
    conversation_service = await create_conversation_service(memory_service=memory_service)
    logger.info("✅ ConversationService created with injected MemoryService singleton")

    # Start existing services
    await conversation_service.start()
    await plugin_manager.start_resource_monitoring()

    # NEW Phase 4 Batch 1: Initialize plugins for all agents
    try:
        from src.services.agent_service import AgentService

        logger.info("🔌 Initializing plugins for all agents...")
        agents = await AgentService.get_all_agents()

        if not agents:
            logger.info("  ℹ️  No agents found - plugins will be initialized when agents are created")

        initialized_count = 0
        failed_count = 0

        for agent in agents:
            if agent.plugins:
                logger.info(f"  🔌 Initializing plugins for agent '{agent.name}'...")
                try:
                    # Phase 4: Add 30-second timeout per agent plugin initialization
                    results = await asyncio.wait_for(
                        plugin_manager.initialize_agent_plugins(agent),
                        timeout=30.0
                    )

                    for plugin_type, success in results.items():
                        if success:
                            status = "✅"
                            initialized_count += 1
                            logger.info(f"    {status} {plugin_type} plugin initialized")
                        else:
                            status = "❌"
                            failed_count += 1
                            logger.error(f"    {status} {plugin_type} plugin failed to initialize")
                except asyncio.TimeoutError:
                    logger.error(f"    ⏱️ Plugin initialization timeout for agent '{agent.name}' (30s)")
                    failed_count += 1

        if initialized_count > 0:
            logger.info(f"✅ Initialized {initialized_count} plugins across {len(agents)} agents")
        if failed_count > 0:
            logger.warning(f"⚠️  {failed_count} plugins failed to initialize")

    except Exception as e:
        logger.error(f"❌ Error during plugin initialization: {e}", exc_info=True)
        # Don't crash app - continue startup even if plugins fail

    logger.info("✅ VoxBridge services started")

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
# VOICE CHANNEL OPERATIONS
# ============================================================

# Bridge functions will be set by discord_bot module at runtime
_bot_bridge = None

def set_bot_bridge(bridge):
    """Set the bot bridge functions (called by discord_bot module)"""
    global _bot_bridge
    _bot_bridge = bridge

@app.post("/voice/join")
async def join_voice(request: JoinVoiceRequest):
    """
    Join a Discord voice channel

    Args:
        request: Join voice channel request

    Returns:
        Success response with channel info
    """
    if not _bot_bridge:
        raise HTTPException(status_code=503, detail="Bot bridge not initialized")

    try:
        return await _bot_bridge['handle_join_voice'](request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/voice/leave")
async def leave_voice():
    """
    Leave the current voice channel

    Returns:
        Success response
    """
    if not _bot_bridge:
        raise HTTPException(status_code=503, detail="Bot bridge not initialized")

    try:
        return await _bot_bridge['handle_leave_voice']()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# HEALTH & STATUS ENDPOINTS
# ============================================================

@app.get("/health")
async def health_check():
    """
    Generic health check endpoint.

    Returns basic server health status. For Discord-specific status,
    use /api/plugins/discord/voice/status/{agent_id} endpoint.
    """
    if not _bot_bridge:
        return {
            "status": "starting",
            "timestamp": datetime.now().isoformat()
        }

    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/status")
async def get_status():
    """Detailed status information"""
    if not _bot_bridge:
        raise HTTPException(status_code=503, detail="Bot bridge not initialized")

    # Get detailed status from bot module
    return await _bot_bridge['get_detailed_status'](
        llm_service=llm_service,
        tts_service=tts_service,
        stt_service=stt_service,
        conversation_service=conversation_service
    )

@app.get("/api/channels")
async def get_channels():
    """
    Get list of available voice channels across all guilds

    Returns:
        List of guilds with their voice channels
    """
    if not _bot_bridge:
        raise HTTPException(status_code=503, detail="Bot bridge not initialized")

    try:
        return await _bot_bridge['get_discord_channels']()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/metrics")
async def get_metrics():
    """
    Get performance metrics

    Returns:
        Performance metrics including latency, counts, error rate
    """
    return metrics_tracker.get_metrics()

@app.get("/api/metrics/extraction-queue")
async def get_extraction_queue_metrics():
    """
    Get memory extraction queue metrics (VoxBridge 2.0 Phase 2)

    Returns:
        Queue statistics including pending, processing, completed, failed counts
        and average processing duration
    """
    from sqlalchemy import select, func
    from src.database.models import ExtractionTask
    from src.database.session import get_db_session

    async with get_db_session() as db:
        # Get counts by status
        status_counts = await db.execute(
            select(
                ExtractionTask.status,
                func.count(ExtractionTask.id).label('count')
            ).group_by(ExtractionTask.status)
        )

        counts = {row.status: row.count for row in status_counts}

        # Get average processing duration for completed tasks
        avg_duration_query = await db.execute(
            select(
                func.avg(
                    func.extract('epoch', ExtractionTask.completed_at - ExtractionTask.created_at)
                ).label('avg_duration_sec')
            ).where(ExtractionTask.status == 'completed')
        )
        avg_duration_result = avg_duration_query.scalar()

        # Get oldest pending task age
        oldest_pending_query = await db.execute(
            select(
                func.min(ExtractionTask.created_at).label('oldest_created_at')
            ).where(ExtractionTask.status == 'pending')
        )
        oldest_pending = oldest_pending_query.scalar()

        # Calculate age in seconds if there is a pending task
        oldest_pending_age_sec = None
        if oldest_pending:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            oldest_pending_age_sec = (now - oldest_pending).total_seconds()

        return {
            "pending": counts.get("pending", 0),
            "processing": counts.get("processing", 0),
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
            "avg_duration_sec": round(avg_duration_result, 2) if avg_duration_result else None,
            "oldest_pending_age_sec": round(oldest_pending_age_sec, 2) if oldest_pending_age_sec else None
        }


@app.get("/api/metrics/llm-optimization")
async def get_llm_optimization_metrics():
    """
    Get LLM optimization metrics (Phase 5 + Phase 7)

    Returns:
        Optimization statistics including retrieval filtering, extraction shortcuts, and deduplication
    """
    global _global_memory_service

    try:
        if _global_memory_service is None:
            return {
                "error": "MemoryService not initialized yet",
                "retrieval": {"total": 0, "filtered_low_confidence": 0, "filter_percentage": 0},
                "extraction": {"total": 0, "shortcuts_used": 0, "full_llm_used": 0, "shortcut_percentage": 0},
                "deduplication": {"total_detected": 0, "by_embedding": 0, "by_text": 0},
                "config": {}
            }

        metrics = _global_memory_service.metrics

        # Calculate percentages
        retrieval_total = metrics["retrieval_total"]
        extraction_total = metrics["extraction_total"]

        retrieval_filter_pct = (
            (metrics["retrieval_filtered"] / retrieval_total * 100)
            if retrieval_total > 0 else 0
        )

        shortcut_pct = (
            (metrics["extraction_shortcuts"] / extraction_total * 100)
            if extraction_total > 0 else 0
        )

        return {
            "retrieval": {
                "total": retrieval_total,
                "filtered_low_confidence": metrics["retrieval_filtered"],
                "filter_percentage": round(retrieval_filter_pct, 1),
            },
            "extraction": {
                "total": extraction_total,
                "shortcuts_used": metrics["extraction_shortcuts"],
                "full_llm_used": metrics["extraction_full"],
                "shortcut_percentage": round(shortcut_pct, 1),
            },
            "deduplication": {
                "total_detected": metrics.get("duplicates_detected", 0),
                "by_embedding": metrics.get("duplicates_embedding", 0),
                "by_text": metrics.get("duplicates_text", 0),
            },
            "config": {
                "vector_similarity_threshold": _global_memory_service.vector_similarity_threshold,
                "high_confidence_threshold": _global_memory_service.high_confidence_threshold,
                "extraction_shortcuts_enabled": _global_memory_service.enable_extraction_shortcuts,
                "shortcut_max_length": _global_memory_service.shortcut_max_length,
                "deduplication_enabled": _global_memory_service.enable_deduplication,
                "dedup_embedding_threshold": _global_memory_service.embedding_similarity_threshold,
                "dedup_text_threshold": _global_memory_service.text_similarity_threshold,
            }
        }

    except Exception as e:
        logger.error(f"Failed to get LLM optimization metrics: {e}")
        return {
            "error": str(e),
            "retrieval": {"total": 0, "filtered_low_confidence": 0, "filter_percentage": 0},
            "extraction": {"total": 0, "shortcuts_used": 0, "full_llm_used": 0, "shortcut_percentage": 0},
            "deduplication": {"total_detected": 0, "by_embedding": 0, "by_text": 0},
            "config": {}
        }


@app.get("/api/metrics/summarization")
async def get_summarization_metrics():
    """
    Get memory summarization metrics (Phase 3)

    Returns:
        Summarization statistics including clusters found, summaries created, and config
    """
    global _global_memory_service

    try:
        if _global_memory_service is None:
            return {
                "error": "MemoryService not initialized yet",
                "stats": {"summaries_created": 0, "facts_summarized": 0, "clusters_found": 0},
                "config": {}
            }

        metrics = _global_memory_service.metrics

        return {
            "stats": {
                "summaries_created": metrics.get("summaries_created", 0),
                "facts_summarized": metrics.get("facts_summarized", 0),
                "clusters_found": metrics.get("clusters_found", 0),
            },
            "config": {
                "enabled": _global_memory_service.enable_summarization,
                "interval_hours": _global_memory_service.summarization_interval_hours,
                "min_age_days": _global_memory_service.summarization_min_age_days,
                "min_cluster_size": _global_memory_service.summarization_min_cluster_size,
                "max_cluster_size": _global_memory_service.summarization_max_cluster_size,
                "similarity_threshold": _global_memory_service.summarization_similarity_threshold,
                "llm_provider": _global_memory_service.summarization_llm_provider,
                "llm_model": _global_memory_service.summarization_llm_model,
            }
        }

    except Exception as e:
        logger.error(f"Failed to get summarization metrics: {e}")
        return {
            "error": str(e),
            "stats": {"summaries_created": 0, "facts_summarized": 0, "clusters_found": 0},
            "config": {}
        }


@app.post("/api/summarization/run")
async def run_summarization_now():
    """
    Manually trigger a summarization cycle (Phase 3)

    Useful for testing or forcing immediate summarization.

    Returns:
        Summarization cycle statistics
    """
    global _global_memory_service

    if _global_memory_service is None:
        return {"error": "MemoryService not initialized yet"}

    try:
        stats = await _global_memory_service.run_summarization_cycle()
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"Manual summarization failed: {e}")
        return {"error": str(e)}


class FrontendLogEntry(BaseModel):
    """Frontend log entry for remote logging"""
    level: str  # debug, info, warn, error
    module: str  # Logger module name (e.g., "VoxbridgePage")
    message: str  # Log message
    data: Optional[Dict] = None  # Additional structured data
    timestamp: float  # Client timestamp (ms since epoch)

@app.post("/api/frontend-logs")
async def receive_frontend_logs(logs: list[FrontendLogEntry]):
    """
    Receive frontend logs from browser and write to backend logger

    This endpoint allows frontend JavaScript logs to be visible in Docker logs
    for debugging purposes. All frontend logs are prefixed with [FRONTEND].

    Args:
        logs: List of log entries from frontend

    Returns:
        Success status
    """
    for log in logs:
        # Map frontend log level to Python logging level
        level_map = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warn': logging.WARNING,
            'error': logging.ERROR,
        }
        level = level_map.get(log.level, logging.INFO)

        # Format log message with frontend prefix
        msg_parts = [f"[FRONTEND:{log.module}]", log.message]
        if log.data:
            msg_parts.append(f"Data: {log.data}")
        msg = " ".join(msg_parts)

        # Write to backend logger
        logger.log(level, msg)

    return {"status": "ok", "received": len(logs)}

@app.get("/api/voices")
async def get_voices():
    """
    Get available TTS voices from Chatterbox

    Returns:
        List of available voice names from Chatterbox TTS API
    """
    try:
        chatterbox_url = os.getenv('CHATTERBOX_URL', 'http://chatterbox-tts:4123')
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{chatterbox_url}/voices", timeout=5.0)
            response.raise_for_status()
            data = response.json()
            return data
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch voices from Chatterbox: {e}")
        raise HTTPException(status_code=503, detail="Failed to fetch voices from Chatterbox TTS")
    except Exception as e:
        logger.error(f"Unexpected error fetching voices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/streaming-config")
async def get_streaming_config_endpoint():
    """
    Get global streaming configuration

    Returns:
        Current streaming configuration (runtime overrides or environment defaults)

    Example response:
        {
            "enabled": true,
            "chunking_strategy": "sentence",
            "min_chunk_length": 10,
            "max_concurrent_tts": 3,
            "error_strategy": "retry",
            "interruption_strategy": "graceful"
        }
    """
    config = get_streaming_config()
    return {
        "enabled": config.enabled,
        "chunking_strategy": config.chunking_strategy,
        "min_chunk_length": config.min_chunk_length,
        "max_concurrent_tts": config.max_concurrent_tts,
        "error_strategy": config.error_strategy,
        "interruption_strategy": config.interruption_strategy,
    }

class StreamingConfigUpdate(BaseModel):
    """Streaming configuration update request"""
    enabled: bool | None = None
    chunking_strategy: str | None = None
    min_chunk_length: int | None = None
    max_concurrent_tts: int | None = None
    error_strategy: str | None = None
    interruption_strategy: str | None = None

@app.put("/api/streaming-config")
async def update_streaming_config_endpoint(config_update: StreamingConfigUpdate):
    """
    Update global streaming configuration at runtime

    Request body:
        {
            "enabled": true,
            "chunking_strategy": "sentence",
            "min_chunk_length": 15,
            "max_concurrent_tts": 5,
            "error_strategy": "skip",
            "interruption_strategy": "immediate"
        }

    Returns:
        Updated configuration

    Note:
        Changes persist until container restart. Environment variables
        provide defaults that are restored on restart.
    """
    try:
        updated_config = update_streaming_config(
            enabled=config_update.enabled,
            chunking_strategy=config_update.chunking_strategy,
            min_chunk_length=config_update.min_chunk_length,
            max_concurrent_tts=config_update.max_concurrent_tts,
            error_strategy=config_update.error_strategy,
            interruption_strategy=config_update.interruption_strategy,
        )

        logger.info(
            f"✅ Updated streaming config: enabled={updated_config.enabled}, "
            f"strategy={updated_config.chunking_strategy}, "
            f"min_length={updated_config.min_chunk_length}, "
            f"max_concurrent={updated_config.max_concurrent_tts}, "
            f"error={updated_config.error_strategy}, "
            f"interruption={updated_config.interruption_strategy}"
        )

        return {
            "enabled": updated_config.enabled,
            "chunking_strategy": updated_config.chunking_strategy,
            "min_chunk_length": updated_config.min_chunk_length,
            "max_concurrent_tts": updated_config.max_concurrent_tts,
            "error_strategy": updated_config.error_strategy,
            "interruption_strategy": updated_config.interruption_strategy,
        }
    except ValueError as e:
        logger.error(f"❌ Invalid streaming config update: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/streaming-config/reset")
async def reset_streaming_config_endpoint():
    """
    Reset streaming configuration to environment variable defaults

    Returns:
        Default configuration from environment variables
    """
    config = reset_streaming_config()

    logger.info("🔄 Reset streaming config to environment defaults")

    return {
        "enabled": config.enabled,
        "chunking_strategy": config.chunking_strategy,
        "min_chunk_length": config.min_chunk_length,
        "max_concurrent_tts": config.max_concurrent_tts,
        "error_strategy": config.error_strategy,
        "interruption_strategy": config.interruption_strategy,
    }

@app.get("/api/plugins")
async def get_plugins():
    """
    Get list of all active plugins with status and resource usage

    Returns:
        Dict with list of active plugins

    Example response:
        {
            "plugins": [
                {
                    "plugin_type": "discord",
                    "agent_id": "uuid",
                    "agent_name": "Auren",
                    "status": "running",
                    "enabled": true,
                    "resource_usage": {
                        "cpu_percent": 2.5,
                        "memory_mb": 45.3
                    }
                }
            ]
        }
    """
    from src.services.agent_service import AgentService

    plugins = []

    # Iterate through all active plugins
    for agent_id, agent_plugins in plugin_manager.active_plugins.items():
        for plugin_type, plugin_instance in agent_plugins.items():
            # Get agent details
            try:
                agent = await AgentService.get_agent(agent_id)
                agent_name = agent.name if agent else "Unknown"
            except Exception as e:
                logger.error(f"❌ Error getting agent {agent_id}: {e}")
                agent_name = "Unknown"

            # Get resource usage from monitor
            resource_usage = None
            if plugin_manager.resource_monitor:
                stats = plugin_manager.resource_monitor.get_plugin_stats(agent_id, plugin_type)
                if stats:
                    resource_usage = {
                        "cpu_percent": round(stats.get("cpu_percent", 0), 2),
                        "memory_mb": round(stats.get("memory_mb", 0), 2)
                    }
                    if stats.get("gpu_memory_mb") is not None:
                        resource_usage["gpu_memory_mb"] = round(stats["gpu_memory_mb"], 2)

            plugins.append({
                "plugin_type": plugin_type,
                "agent_id": str(agent_id),
                "agent_name": agent_name,
                "status": "running",  # If in active_plugins, it's running
                "enabled": True,
                "resource_usage": resource_usage,
                "uptime_seconds": getattr(plugin_instance, 'uptime_seconds', None)
            })

    return {"plugins": plugins}

@app.get("/api/plugins/stats")
async def get_plugin_stats():
    """
    Get plugin system statistics including resource usage

    Returns:
        Plugin manager stats transformed for frontend consumption

    Example response:
        {
            "total_plugins": 5,
            "active_plugins": 5,
            "failed_plugins": 0,
            "plugins_by_type": {"discord": 3, "n8n": 2},
            "resource_usage": {
                "total_cpu_percent": 12.5,
                "total_memory_mb": 128.4
            }
        }
    """
    # Get raw stats from plugin manager
    raw_stats = plugin_manager.get_stats()

    # Transform to frontend format
    resource_monitoring = raw_stats.get('resource_monitoring', {})

    return {
        "total_plugins": raw_stats.get('total_plugins', 0),
        "active_plugins": raw_stats.get('total_plugins', 0),  # All plugins in active_plugins are active
        "failed_plugins": sum(raw_stats.get('error_counts', {}).values()),
        "plugins_by_type": raw_stats.get('plugins_by_type', {}),
        "resource_usage": {
            "total_cpu_percent": resource_monitoring.get('total_cpu_percent', 0),
            "total_memory_mb": resource_monitoring.get('total_memory_mb', 0),
            "total_gpu_memory_mb": resource_monitoring.get('total_gpu_memory_mb')
        }
    }

@app.post("/api/plugins/{plugin_type}/start")
async def start_plugin(plugin_type: str, request: dict):
    """
    Start a plugin for a specific agent

    Args:
        plugin_type: Type of plugin (discord, n8n, etc.)
        request: JSON body with agent_id

    Returns:
        Success message or error

    Example request:
        POST /api/plugins/discord/start
        {"agent_id": "uuid-here"}
    """
    from src.services.agent_service import AgentService

    try:
        agent_id_str = request.get("agent_id")
        if not agent_id_str:
            return {"error": "Missing agent_id in request body"}, 400

        # Get agent
        from uuid import UUID
        agent_id = UUID(agent_id_str)
        agent = await AgentService.get_agent(agent_id)

        if not agent:
            return {"error": f"Agent {agent_id} not found"}, 404

        # Check if plugin is configured for this agent
        if not agent.plugins or plugin_type not in agent.plugins:
            return {"error": f"Plugin {plugin_type} not configured for agent {agent.name}"}, 400

        # Initialize the plugin
        results = await plugin_manager.initialize_agent_plugins(agent)

        if plugin_type in results and results[plugin_type]:
            logger.info(f"✅ Started {plugin_type} plugin for agent {agent.name}")
            return {
                "success": True,
                "message": f"Started {plugin_type} plugin for {agent.name}"
            }
        else:
            logger.error(f"❌ Failed to start {plugin_type} plugin for agent {agent.name}")
            return {"error": f"Failed to start {plugin_type} plugin"}, 500

    except Exception as e:
        logger.error(f"❌ Error starting plugin: {e}", exc_info=True)
        return {"error": str(e)}, 500

@app.post("/api/plugins/{plugin_type}/stop")
async def stop_plugin(plugin_type: str, request: dict):
    """
    Stop a plugin for a specific agent

    Args:
        plugin_type: Type of plugin (discord, n8n, etc.)
        request: JSON body with agent_id

    Returns:
        Success message or error
    """
    from uuid import UUID

    try:
        agent_id_str = request.get("agent_id")
        if not agent_id_str:
            return {"error": "Missing agent_id in request body"}, 400

        agent_id = UUID(agent_id_str)

        # Stop the plugin
        results = await plugin_manager.stop_agent_plugins(agent_id)

        if plugin_type in results and results[plugin_type]:
            logger.info(f"✅ Stopped {plugin_type} plugin for agent {agent_id}")
            return {
                "success": True,
                "message": f"Stopped {plugin_type} plugin"
            }
        else:
            logger.warning(f"⚠️ Plugin {plugin_type} was not running for agent {agent_id}")
            return {
                "success": True,
                "message": f"Plugin {plugin_type} was not running"
            }

    except Exception as e:
        logger.error(f"❌ Error stopping plugin: {e}", exc_info=True)
        return {"error": str(e)}, 500

@app.post("/api/plugins/{plugin_type}/restart")
async def restart_plugin(plugin_type: str, request: dict):
    """
    Restart a plugin for a specific agent

    Args:
        plugin_type: Type of plugin (discord, n8n, etc.)
        request: JSON body with agent_id

    Returns:
        Success message or error
    """
    from src.services.agent_service import AgentService
    from uuid import UUID

    try:
        agent_id_str = request.get("agent_id")
        if not agent_id_str:
            return {"error": "Missing agent_id in request body"}, 400

        agent_id = UUID(agent_id_str)
        agent = await AgentService.get_agent(agent_id)

        if not agent:
            return {"error": f"Agent {agent_id} not found"}, 404

        # Stop the plugin
        stop_results = await plugin_manager.stop_agent_plugins(agent_id)
        logger.info(f"🛑 Stopped {plugin_type} plugin for agent {agent.name}")

        # Start the plugin
        start_results = await plugin_manager.initialize_agent_plugins(agent)

        if plugin_type in start_results and start_results[plugin_type]:
            logger.info(f"✅ Restarted {plugin_type} plugin for agent {agent.name}")
            return {
                "success": True,
                "message": f"Restarted {plugin_type} plugin for {agent.name}"
            }
        else:
            logger.error(f"❌ Failed to restart {plugin_type} plugin for agent {agent.name}")
            return {"error": f"Failed to restart {plugin_type} plugin"}, 500

    except Exception as e:
        logger.error(f"❌ Error restarting plugin: {e}", exc_info=True)
        return {"error": str(e)}, 500

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
        """Broadcast message to all connected clients with detailed delivery logging"""
        import json
        import time

        event_type = message.get('event', 'unknown')
        num_clients = len(self.active_connections)
        correlation_id = message.get('data', {}).get('correlation_id', None) if isinstance(message.get('data'), dict) else None

        # Calculate message size
        message_json = json.dumps(message)
        message_size = len(message_json.encode('utf-8'))

        t_start = time.time()

        logger.info(
            f"📤 [WS_BROADCAST_START] Broadcasting {event_type} to {num_clients} client(s) "
            f"(size={message_size} bytes, correlation_id={correlation_id[:8] + '...' if correlation_id else 'none'})"
        )

        dead_connections = []
        success_count = 0
        client_index = 0

        for connection in self.active_connections:
            client_index += 1
            t_send_start = time.time()

            try:
                logger.debug(
                    f"📤 [WS_SEND_START] Sending {event_type} to client #{client_index} "
                    f"(correlation_id={correlation_id[:8] + '...' if correlation_id else 'none'})"
                )

                await connection.send_json(message)

                t_send_end = time.time()
                send_duration_ms = (t_send_end - t_send_start) * 1000

                logger.debug(
                    f"✅ [WS_SEND_SUCCESS] Client #{client_index} received {event_type} "
                    f"(duration={send_duration_ms:.2f}ms, correlation_id={correlation_id[:8] + '...' if correlation_id else 'none'})"
                )

                success_count += 1
            except Exception as e:
                logger.error(
                    f"❌ [WS_SEND_ERROR] Failed to send to client #{client_index}: {e} "
                    f"(event={event_type}, correlation_id={correlation_id[:8] + '...' if correlation_id else 'none'})"
                )
                dead_connections.append(connection)

        # Calculate total broadcast duration
        t_end = time.time()
        total_duration_ms = (t_end - t_start) * 1000

        # Log results
        if success_count > 0:
            logger.info(
                f"✅ [WS_BROADCAST_COMPLETE] Sent {event_type} to {success_count}/{num_clients} client(s) "
                f"(total_duration={total_duration_ms:.2f}ms, correlation_id={correlation_id[:8] + '...' if correlation_id else 'none'})"
            )
        if dead_connections:
            logger.warning(f"⚠️ [WS_CLEANUP] Removed {len(dead_connections)} dead connection(s)")

        # Remove dead connections
        for connection in dead_connections:
            self.disconnect(connection)

# Initialize connection manager
ws_manager = ConnectionManager()

# Set WebSocket manager for agent routes (VoxBridge 2.0)
set_websocket_manager(ws_manager)

# Note: memory_service.ws_manager is set in startup_services() when MemoryService is initialized

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
async def websocket_voice_endpoint(
    websocket: WebSocket,
    conv_service: ConversationService = Depends(get_conversation_service)
):
    """
    WebSocket endpoint for browser voice streaming (VoxBridge 2.0 Phase 4)

    CRITICAL: Uses dependency injection to receive the global ConversationService
    singleton. This ensures all WebSocket connections share the same conversation
    cache, enabling multi-turn conversations.

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

        # Create handler with injected ConversationService singleton
        handler = WebRTCVoiceHandler(websocket, user_id, session_id, conv_service)
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

# Export WebSocket manager for use by discord_bot module
def get_ws_manager():
    """Get the WebSocket manager instance"""
    return ws_manager

# Export metrics tracker for use by discord_bot module
def get_metrics_tracker():
    """Get the metrics tracker instance"""
    return metrics_tracker
