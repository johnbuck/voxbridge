#!/usr/bin/env python3
"""
============================================================
VoxBridge - Discord Voice Bridge Service
Bridges Discord voice channels to STT/TTS processing:
- Join/leave voice channels
- Speech-to-Text (WhisperX)
- Text-to-Speech (Chatterbox TTS)
- Send transcripts back to n8n for agent processing
============================================================
"""

import asyncio
import logging
import os
import signal
import tempfile
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import uvicorn
from dotenv import load_dotenv

# Mock discord.sinks if not available (not in all discord.py versions)
if not hasattr(discord, 'sinks'):
    from unittest.mock import MagicMock
    discord.sinks = MagicMock()
    discord.sinks.Sink = type('Sink', (), {})

from src.speaker_manager import SpeakerManager
from src.streaming_handler import StreamingResponseHandler

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
CHATTERBOX_URL = os.getenv('CHATTERBOX_URL', 'http://localhost:4800/v1')
CHATTERBOX_VOICE_ID = os.getenv('CHATTERBOX_VOICE_ID')

if not DISCORD_TOKEN:
    logger.error("❌ DISCORD_TOKEN not set in environment")
    exit(1)

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
speaker_manager = SpeakerManager()

# ============================================================
# FAST API SETUP
# ============================================================

app = FastAPI(title="VoxBridge API")

# Pydantic models for API
class JoinVoiceRequest(BaseModel):
    channelId: str
    guildId: str

class SpeakRequest(BaseModel):
    output: dict
    options: dict = {}

# ============================================================
# DISCORD BOT EVENTS
# ============================================================

@bot.event
async def on_ready():
    """Bot ready event"""
    logger.info("=" * 60)
    logger.info(f"✅ Discord bot logged in as {bot.user.name}")
    logger.info(f"🎙️ Voice service ready with WhisperX STT")
    logger.info("=" * 60)

@bot.event
async def on_error(event, *args, **kwargs):
    """Bot error handler"""
    logger.error(f"❌ Discord bot error in {event}: {args} {kwargs}")

# ============================================================
# VOICE CHANNEL OPERATIONS
# ============================================================

class AudioReceiver(discord.sinks.Sink):
    """Custom audio sink to receive voice data"""

    def __init__(self, vc, speaker_mgr):
        super().__init__()
        self.vc = vc
        self.speaker_mgr = speaker_mgr
        self.user_buffers = {}  # user_id -> asyncio.Queue of audio chunks
        self.user_tasks = {}    # user_id -> streaming task
        self.active_users = set()  # Users currently being processed

    def write(self, data, user):
        """
        Receive audio data from Discord

        Args:
            data: Audio data dictionary with 'data' key containing Opus packet
            user: Discord user sending audio
        """
        if not user:
            return

        user_id = str(user.id)

        # Extract Opus packet from data
        # discord.py sends data as {'data': bytes, 'timestamp': int}
        if isinstance(data, dict):
            opus_packet = data.get('data')
        else:
            opus_packet = data

        if not opus_packet:
            return

        # Create buffer for this user if not exists
        if user_id not in self.user_buffers:
            logger.info(f"📥 New audio stream from user {user_id}")
            self.user_buffers[user_id] = asyncio.Queue()

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
                task = asyncio.create_task(
                    self.speaker_mgr.on_speaking_start(user_id, stream_gen)
                )
                self.user_tasks[user_id] = task

        # Add Opus packet to user's queue
        try:
            self.user_buffers[user_id].put_nowait(opus_packet)
        except asyncio.QueueFull:
            logger.warning(f"⚠️ Audio buffer full for user {user_id}, dropping packet")

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

@app.post("/voice/join")
async def join_voice(request: JoinVoiceRequest):
    """
    Join a Discord voice channel

    Args:
        request: Join voice channel request

    Returns:
        Success response with channel info
    """
    global voice_client

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
        voice_client = await channel.connect()

        logger.info("   👂 Setting up voice listeners...")

        # Set up voice receiving
        voice_client.listen(AudioReceiver(voice_client, speaker_manager))

        # Pass voice connection to speaker manager
        speaker_manager.set_voice_connection(voice_client)
        logger.info("   🌊 Voice connection passed to speaker manager")

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
    global voice_client

    logger.info("📞 LEAVE request received")

    if not voice_client:
        raise HTTPException(status_code=400, detail="Not currently in a voice channel")

    try:
        # Force unlock any active speaker
        speaker_manager.force_unlock()

        # Disconnect from voice
        await voice_client.disconnect()
        voice_client = None

        logger.info("✅ Left voice channel\n")
        return {"success": True, "message": "Left voice channel"}

    except Exception as e:
        logger.error(f"❌ Error leaving voice channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/voice/speak")
async def speak_text(request: SpeakRequest):
    """
    Speak text in the voice channel using TTS

    Args:
        request: Speak request with text and options

    Returns:
        Success response
    """
    text = request.output.get('content')
    options = request.options

    logger.info(f"🔊 SPEAK request: \"{text}\"")
    logger.info(f"📋 Options: {options}")

    if not text:
        raise HTTPException(status_code=400, detail="Missing required parameter: output.content")

    if not voice_client or not voice_client.is_connected():
        raise HTTPException(status_code=400, detail="Not in a voice channel")

    try:
        logger.info("   📞 Requesting TTS from Chatterbox...")

        # Build Chatterbox TTS request
        tts_data = {
            'input': text,
            'response_format': options.get('outputFormat', 'wav'),
            'speed': float(options.get('speedFactor', 1.0))
        }

        # Add voice parameter
        if options.get('voiceMode') == 'clone' and options.get('referenceAudioFilename'):
            tts_data['voice'] = options['referenceAudioFilename']
        elif CHATTERBOX_VOICE_ID:
            tts_data['voice'] = CHATTERBOX_VOICE_ID
        else:
            tts_data['voice'] = 'default'

        # Add generation parameters
        if 'temperature' in options:
            tts_data['temperature'] = float(options['temperature'])
        if 'exaggeration' in options:
            tts_data['exaggeration'] = float(options['exaggeration'])
        if 'cfgWeight' in options:
            tts_data['cfg_weight'] = float(options['cfgWeight'])

        # Add streaming parameters with optimal defaults
        tts_data['streaming_chunk_size'] = int(options.get('chunkSize', 100))
        tts_data['streaming_strategy'] = options.get('streamingStrategy', 'sentence')
        tts_data['streaming_quality'] = options.get('streamingQuality', 'fast')

        logger.info(f"   📋 TTS Request: {tts_data}")

        # Stream TTS from Chatterbox - TRUE STREAMING
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                'POST',
                f"{CHATTERBOX_URL}/audio/speech/stream/upload",
                data=tts_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            ) as response:
                response.raise_for_status()

                # Save streaming audio to temp file
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                    temp_path = temp_file.name
                    total_bytes = 0

                    # Stream chunks as they arrive
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        temp_file.write(chunk)
                        temp_file.flush()
                        total_bytes += len(chunk)

                logger.info(f"   ✅ TTS stream complete ({total_bytes} bytes)")

                # Play audio in voice channel
                await play_audio_in_voice(temp_path)

        logger.info("✅ Playing audio in voice channel\n")
        return {"success": True, "message": "Speaking text"}

    except Exception as e:
        logger.error(f"❌ Error with TTS: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def play_audio_in_voice(temp_path: str):
    """
    Play audio from file in Discord voice channel

    Args:
        temp_path: Path to temporary audio file (WAV format)
    """
    if not voice_client or not voice_client.is_connected():
        logger.warning("⚠️ Not connected to voice channel")
        return

    try:
        # Create FFmpeg audio source from file
        audio_source = discord.FFmpegPCMAudio(temp_path)

        # Wait for current audio to finish if playing
        while voice_client.is_playing():
            await asyncio.sleep(0.1)

        # Play audio
        voice_client.play(audio_source)

        # Wait for playback to finish
        while voice_client.is_playing():
            await asyncio.sleep(0.1)

    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_path)
        except Exception as e:
            logger.warning(f"⚠️ Failed to delete temp file {temp_path}: {e}")

# ============================================================
# HEALTH & STATUS ENDPOINTS
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    speaker_status = speaker_manager.get_status()
    return {
        "status": "ok",
        "botReady": bot.is_ready(),
        "inVoiceChannel": voice_client is not None and voice_client.is_connected(),
        "speakerLocked": speaker_status['locked'],
        "activeSpeaker": speaker_status['activeSpeaker'],
        "timestamp": datetime.now().isoformat()
    }

@app.get("/status")
async def get_status():
    """Detailed status information"""
    speaker_status = speaker_manager.get_status()
    return {
        "bot": {
            "username": bot.user.name if bot.user else "Not ready",
            "id": str(bot.user.id) if bot.user else None,
            "ready": bot.is_ready()
        },
        "voice": {
            "connected": voice_client is not None and voice_client.is_connected(),
            "speakerLocked": speaker_status['locked'],
            "activeSpeaker": speaker_status['activeSpeaker'],
            "speakingDuration": speaker_status['speakingDuration'],
            "silenceDuration": speaker_status['silenceDuration']
        },
        "whisperx": {
            "serverConfigured": bool(os.getenv('WHISPER_SERVER_URL')),
            "model": os.getenv('WHISPERX_MODEL', 'small'),
            "device": os.getenv('WHISPERX_DEVICE', 'auto'),
            "computeType": os.getenv('WHISPERX_COMPUTE_TYPE', 'float16'),
            "batchSize": os.getenv('WHISPERX_BATCH_SIZE', '16')
        },
        "services": {
            "chatterbox": bool(CHATTERBOX_URL),
            "n8nWebhook": bool(os.getenv('N8N_WEBHOOK_URL'))
        }
    }

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
    logger.info(f"   POST /voice/speak - Speak text via TTS")
    logger.info(f"   GET  /health - Health check")
    logger.info(f"   GET  /status - Detailed status")
    logger.info("=" * 60)

    await server.serve()

async def shutdown():
    """Graceful shutdown"""
    logger.info("\n⚠️ Shutting down gracefully...")

    # Force unlock speaker
    speaker_manager.force_unlock()

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
