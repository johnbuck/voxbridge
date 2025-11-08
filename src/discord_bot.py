#!/usr/bin/env python3
"""
============================================================
VoxBridge - Discord Voice Bridge Service (Phase 6.4.1 Refactored)
Bridges Discord voice channels to STT/LLM/TTS processing:
- Join/leave voice channels
- Speech-to-Text (WhisperX via STTService)
- LLM generation (via LLMService with hybrid routing)
- Text-to-Speech (Chatterbox via TTSService)
- Session-based architecture with ConversationService

Phase 6.4.1: FastAPI decoupled to src/api/server.py
============================================================

⚠️  DEPRECATION NOTICE (Phase 6.4.1 Batch 2a)
============================================================

This Discord bot implementation contains LEGACY HANDLERS that are
DEPRECATED and will be removed in VoxBridge 3.0.

NEW USERS: Set USE_LEGACY_DISCORD_BOT=false (default)
           to use the new plugin-based Discord bot at
           src/plugins/discord_plugin.py

EXISTING USERS: Migrate to plugin-based bot by:
  1. Set USE_LEGACY_DISCORD_BOT=false in .env
  2. Restart container: docker compose restart voxbridge-discord
  3. See docs/MIGRATION_GUIDE.md for complete migration steps

ROLLBACK: Set USE_LEGACY_DISCORD_BOT=true if issues arise

The plugin-based architecture provides:
  - Better separation of concerns (API ↔ Discord bot)
  - Easier testing with bridge pattern
  - Extensibility for new platforms (Telegram, Slack, etc.)
  - Independent deployment (API can run without Discord)

Migration Guide: /home/wiley/Docker/voxbridge/docs/MIGRATION_GUIDE.md

============================================================
"""

import asyncio
import logging
import os
import signal
import tempfile
import time
import uuid
from datetime import datetime
from typing import Optional, Dict

import discord
from discord.ext import commands, voice_recv
import httpx
import uvicorn
from dotenv import load_dotenv

# Tiered logging system
from src.config.logging_config import configure_logging, get_logger

# VoxBridge 2.0 Service Layer
from src.services.conversation_service import ConversationService
from src.services.stt_service import get_stt_service
from src.services.llm_service import get_llm_service, LLMConfig, ProviderType
from src.services.tts_service import get_tts_service
from src.services.agent_service import AgentService

# LLM exceptions for error handling
from src.llm import LLMError, LLMConnectionError, LLMTimeoutError

# Import FastAPI app from decoupled module (Phase 6.4.1)
from src.api.server import app, get_ws_manager, get_metrics_tracker, set_bot_bridge

# Load environment variables
load_dotenv()

# Configure logging with tiered system
configure_logging(default_level="INFO")
logger = get_logger(__name__)

# ============================================================
# PHASE 6.4.1 BATCH 2a: GRACEFUL DEPRECATION TOGGLE
# ============================================================

# Legacy mode toggle - allows rollback to old Discord bot voice handlers
USE_LEGACY_DISCORD_BOT = os.getenv("USE_LEGACY_DISCORD_BOT", "false").lower() == "true"

if USE_LEGACY_DISCORD_BOT:
    logger.warning("=" * 60)
    logger.warning("⚠️  LEGACY MODE: Using old Discord bot voice handlers")
    logger.warning("⚠️  This mode is DEPRECATED and will be removed in VoxBridge 3.0")
    logger.warning("⚠️  Set USE_LEGACY_DISCORD_BOT=false to use new plugin-based bot")
    logger.warning("=" * 60)
else:
    logger.info("=" * 60)
    logger.info("✅ Using new plugin-based Discord bot (recommended)")
    logger.info("💡 Legacy voice handlers are disabled")
    logger.info("=" * 60)

# ============================================================
# CONFIGURATION
# ============================================================

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
PORT = int(os.getenv('PORT', '4900'))

if not DISCORD_TOKEN:
    logger.error("❌ DISCORD_TOKEN not set in environment")
    exit(1)

# ============================================================
# METRICS TRACKING (Imported from API module - Phase 6.4.1)
# ============================================================

# Get metrics tracker from API module
metrics_tracker = get_metrics_tracker()
ws_manager = get_ws_manager()

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

# Initialize services (shared with API module)
conversation_service = ConversationService()
stt_service = get_stt_service()
llm_service = get_llm_service()
tts_service = get_tts_service()

# Active sessions: Discord user_id → session_id
active_discord_sessions: Dict[str, str] = {}

# Session timing tracking for metrics
session_timings: Dict[str, Dict[str, float]] = {}

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

    # Register bridge functions for API module (Phase 6.4.1)
    set_bot_bridge({
        'handle_join_voice': handle_join_voice,
        'handle_leave_voice': handle_leave_voice,
        'get_bot_status': get_bot_status,
        'get_detailed_status': get_detailed_status,
        'get_discord_channels': get_discord_channels
    })
    logger.info("✅ Bot bridge functions registered with API module")

@bot.event
async def on_error(event, *args, **kwargs):
    """Bot error handler"""
    logger.error(f"❌ Discord bot error in {event}: {args} {kwargs}")

# ============================================================
# VOICE AUDIO RECEIVER (Refactored for Service Layer)
# ============================================================

# ⚠️ DEPRECATED (Phase 6.4.1 Batch 2a)
# This legacy AudioReceiver class is deprecated and will be removed in VoxBridge 3.0
# Use the new plugin-based Discord bot instead (set USE_LEGACY_DISCORD_BOT=false)
#
# Rollback path: Set USE_LEGACY_DISCORD_BOT=true to re-enable legacy handlers
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
        # Phase 6.4.1 Batch 2a: Disable in new mode
        if not USE_LEGACY_DISCORD_BOT:
            logger.debug("🚫 Legacy AudioReceiver.write() disabled - using plugin system")
            return

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

# ⚠️ DEPRECATED (Phase 6.4.1 Batch 2a)
# This legacy voice processing function is deprecated and will be removed in VoxBridge 3.0
# Use the new plugin-based Discord bot instead (set USE_LEGACY_DISCORD_BOT=false)
#
# Rollback path: Set USE_LEGACY_DISCORD_BOT=true to re-enable legacy handlers
async def on_user_speaking_start(user_id: str, username: str, audio_stream):
    """
    Handle user starting to speak (VoxBridge 2.0 service integration)

    This replaces SpeakerManager.on_speaking_start with service-based routing.

    Args:
        user_id: Discord user ID
        username: Discord username
        audio_stream: Async generator of audio chunks
    """
    # Phase 6.4.1 Batch 2a: Disable in new mode
    if not USE_LEGACY_DISCORD_BOT:
        logger.debug(f"🚫 Legacy on_user_speaking_start() disabled for {username} - using plugin system")
        return

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

# ⚠️ DEPRECATED (Phase 6.4.1 Batch 2a)
# This legacy STT callback is deprecated and will be removed in VoxBridge 3.0
# Use the new plugin-based Discord bot instead (set USE_LEGACY_DISCORD_BOT=false)
#
# Rollback path: Set USE_LEGACY_DISCORD_BOT=true to re-enable legacy handlers
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
    # Phase 6.4.1 Batch 2a: Disable in new mode
    if not USE_LEGACY_DISCORD_BOT:
        logger.debug(f"🚫 Legacy on_stt_transcript() disabled for {username} - using plugin system")
        return

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

# ⚠️ DEPRECATED (Phase 6.4.1 Batch 2a)
# This legacy LLM generation function is deprecated and will be removed in VoxBridge 3.0
# Use the new plugin-based Discord bot instead (set USE_LEGACY_DISCORD_BOT=false)
#
# Rollback path: Set USE_LEGACY_DISCORD_BOT=true to re-enable legacy handlers
async def generate_and_play_response(session_id: str, user_id: str, username: str, user_text: str):
    """
    Generate LLM response and play via TTS (VoxBridge 2.0)

    Args:
        session_id: Session UUID
        user_id: Discord user ID
        username: Discord username
        user_text: User's transcribed text
    """
    # Phase 6.4.1 Batch 2a: Disable in new mode
    if not USE_LEGACY_DISCORD_BOT:
        logger.debug(f"🚫 Legacy generate_and_play_response() disabled for {username} - using plugin system")
        return

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

# ⚠️ DEPRECATED (Phase 6.4.1 Batch 2a)
# This legacy TTS playback function is deprecated and will be removed in VoxBridge 3.0
# Use the new plugin-based Discord bot instead (set USE_LEGACY_DISCORD_BOT=false)
#
# Rollback path: Set USE_LEGACY_DISCORD_BOT=true to re-enable legacy handlers
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
    # Phase 6.4.1 Batch 2a: Disable in new mode
    if not USE_LEGACY_DISCORD_BOT:
        logger.debug(f"🚫 Legacy synthesize_and_play_discord() disabled for {username} - using plugin system")
        return

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
            exaggeration=agent.tts_exaggeration or 1.0,
            cfg_weight=agent.tts_cfg_weight or 0.7,
            temperature=agent.tts_temperature or 0.3,
            language=agent.tts_language or 'en',
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

# ⚠️ DEPRECATED (Phase 6.4.1 Batch 2a)
# This legacy session cleanup function is deprecated and will be removed in VoxBridge 3.0
# Use the new plugin-based Discord bot instead (set USE_LEGACY_DISCORD_BOT=false)
#
# Rollback path: Set USE_LEGACY_DISCORD_BOT=true to re-enable legacy handlers
async def cleanup_session(user_id: str, session_id: str):
    """
    Cleanup session when user stops speaking

    Args:
        user_id: Discord user ID
        session_id: Session UUID
    """
    # Phase 6.4.1 Batch 2a: Disable in new mode
    if not USE_LEGACY_DISCORD_BOT:
        logger.debug(f"🚫 Legacy cleanup_session() disabled for user {user_id} - using plugin system")
        return

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
# VOICE CHANNEL OPERATIONS (Bridge functions for API module)
# ============================================================

# ⚠️ DEPRECATED (Phase 6.4.1 Batch 2a)
# This legacy voice join handler is deprecated and will be removed in VoxBridge 3.0
# Use the new plugin-based Discord bot instead (set USE_LEGACY_DISCORD_BOT=false)
#
# Rollback path: Set USE_LEGACY_DISCORD_BOT=true to re-enable legacy handlers
async def handle_join_voice(request):
    """
    Join a Discord voice channel

    Args:
        request: Join voice channel request

    Returns:
        Success response with channel info
    """
    # Phase 6.4.1 Batch 2a: Disable in new mode
    if not USE_LEGACY_DISCORD_BOT:
        logger.warning("🚫 Legacy handle_join_voice() disabled - using plugin system")
        raise RuntimeError("Legacy voice handlers disabled. Set USE_LEGACY_DISCORD_BOT=true to re-enable.")

    global voice_client, audio_receiver

    logger.info(f"📞 JOIN request - Channel: {request.channelId}, Guild: {request.guildId}")

    try:
        # Fetch the voice channel
        logger.info("   🔍 Fetching channel from Discord...")
        channel = bot.get_channel(int(request.channelId))

        if not channel:
            channel = await bot.fetch_channel(int(request.channelId))

        if not isinstance(channel, discord.VoiceChannel):
            raise ValueError("Invalid voice channel")

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
        raise

# ⚠️ DEPRECATED (Phase 6.4.1 Batch 2a)
# This legacy voice leave handler is deprecated and will be removed in VoxBridge 3.0
# Use the new plugin-based Discord bot instead (set USE_LEGACY_DISCORD_BOT=false)
#
# Rollback path: Set USE_LEGACY_DISCORD_BOT=true to re-enable legacy handlers
async def handle_leave_voice():
    """
    Leave the current voice channel

    Returns:
        Success response
    """
    # Phase 6.4.1 Batch 2a: Disable in new mode
    if not USE_LEGACY_DISCORD_BOT:
        logger.warning("🚫 Legacy handle_leave_voice() disabled - using plugin system")
        raise RuntimeError("Legacy voice handlers disabled. Set USE_LEGACY_DISCORD_BOT=true to re-enable.")

    global voice_client, audio_receiver

    logger.info("📞 LEAVE request received")

    if not voice_client:
        raise ValueError("Not currently in a voice channel")

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
        raise

# ============================================================
# STATUS BRIDGE FUNCTIONS (For API module)
# ============================================================

def get_bot_status():
    """Get basic bot status for health check"""
    return {
        "ready": bot.is_ready(),
        "in_voice": voice_client is not None and voice_client.is_connected(),
        "active_sessions": len(active_discord_sessions)
    }

async def get_detailed_status(llm_service, tts_service, stt_service, conversation_service):
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
    # Import here to avoid circular dependency
    from src.services.llm_service import get_global_provider_status
    llm_provider_status = await get_global_provider_status()  # Check both database AND env vars
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

async def get_discord_channels():
    """
    Get list of available voice channels across all guilds

    Returns:
        List of guilds with their voice channels
    """
    if not bot.is_ready():
        raise RuntimeError("Bot not ready")

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

# ============================================================
# WEBSOCKET BROADCAST HELPERS
# ============================================================

# Helper functions to broadcast events via API module WebSocket manager
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
    """Start FastAPI server (from API module)"""
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        ws_ping_interval=300,  # Send keepalive ping every 5 minutes
        ws_ping_timeout=60,    # Wait up to 60 seconds for pong response
    )
    server = uvicorn.Server(config)

    logger.info("=" * 60)
    logger.info(f"🚀 VoxBridge API listening on port {PORT}")
    logger.info(f"📍 API module: src/api/server.py")
    logger.info(f"📍 Bot module: src/discord_bot.py")
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
