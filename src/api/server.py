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
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

# VoxBridge 2.0 Service Layer
from src.services.conversation_service import ConversationService
from src.services.stt_service import get_stt_service
from src.services.llm_service import get_llm_service, LLMConfig, ProviderType
from src.services.tts_service import get_tts_service
from src.services.plugin_manager import get_plugin_manager

# Route modules
from src.routes.agent_routes import router as agent_router, set_websocket_manager
from src.routes.session_routes import router as session_router
from src.routes.discord_plugin_routes import router as discord_plugin_router

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
# SERVICE LAYER INITIALIZATION (VoxBridge 2.0)
# ============================================================

# Initialize services
conversation_service = ConversationService()
stt_service = get_stt_service()
llm_service = get_llm_service()
tts_service = get_tts_service()
plugin_manager = get_plugin_manager()

# ============================================================
# FAST API SETUP
# ============================================================

app = FastAPI(
    title="VoxBridge API",
    description="Multi-agent voice platform with plugin support",
    version="2.0.0"
)

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
    logger.info("🚀 Starting VoxBridge services...")

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
    """Health check endpoint"""
    if not _bot_bridge:
        return {
            "status": "starting",
            "botReady": False,
            "inVoiceChannel": False,
            "activeSessions": 0,
            "timestamp": datetime.now().isoformat()
        }

    # Get bot status from bot module
    bot_status = _bot_bridge['get_bot_status']()

    return {
        "status": "ok",
        "botReady": bot_status['ready'],
        "inVoiceChannel": bot_status['in_voice'],
        "activeSessions": bot_status['active_sessions'],
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

# Export WebSocket manager for use by discord_bot module
def get_ws_manager():
    """Get the WebSocket manager instance"""
    return ws_manager

# Export metrics tracker for use by discord_bot module
def get_metrics_tracker():
    """Get the metrics tracker instance"""
    return metrics_tracker
