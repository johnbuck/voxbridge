#!/usr/bin/env python3
"""
============================================================
WhisperX WebSocket Server
Handles real-time speech-to-text transcription
- Receives Opus audio streams via WebSocket
- Transcribes using WhisperX (GPU/CPU auto-detect)
- Sends partial and final results back to client
- Optimized for RTX 3080 (10GB VRAM) with CPU fallback
============================================================
"""

import asyncio
import websockets
import json
import tempfile
import os
import torch
import whisperx
import logging
import time
import threading
import traceback
import wave
import opuslib
from aiohttp import web

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
WHISPERX_MODEL = os.getenv('WHISPERX_MODEL', 'small')
WHISPERX_DEVICE = os.getenv('WHISPERX_DEVICE', 'auto')  # auto, cuda, or cpu
WHISPERX_COMPUTE_TYPE = os.getenv('WHISPERX_COMPUTE_TYPE', 'float16')
WHISPERX_BATCH_SIZE = int(os.getenv('WHISPERX_BATCH_SIZE', '16'))
WHISPERX_LANGUAGE = os.getenv('WHISPERX_LANGUAGE', 'en')  # Force English (prevents Korean/auto-detect)
SERVER_PORT = int(os.getenv('WHISPER_SERVER_PORT', '4901'))

# Auto-detect best device
gpu_name = None
if WHISPERX_DEVICE == 'auto':
    if torch.cuda.is_available():
        device = 'cuda'
        compute_type = 'float16'  # Best for GPU
        gpu_name = torch.cuda.get_device_name(0)
        logger.info(f"🎮 GPU detected: {gpu_name}")
        logger.info(f"💾 VRAM available: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    else:
        device = 'cpu'
        compute_type = 'int8'  # Best for CPU
        logger.info("💻 No GPU detected, using CPU")
else:
    device = WHISPERX_DEVICE
    compute_type = WHISPERX_COMPUTE_TYPE
    if device == 'cuda' and torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)

def log_loading_progress(start_time, stop_event):
    """Background thread that provides better progress messages"""
    # Initial message
    logger.info("🔄 Starting model download/processing...")

    # Wait a bit before showing progress
    time.sleep(3)

    # Show progress less frequently
    while not stop_event.is_set():
        elapsed = time.time() - start_time

        # Show different messages at different stages
        if elapsed < 60:
            logger.info(f"📥 Downloading first part of model... ({elapsed:.0f}s)")
        elif elapsed < 300:  # 5 minutes
            # Only log every 30 seconds after 1 minute
            if int(elapsed) % 30 == 0:
                logger.info(f"⚙️ Continuing download/loading... ({elapsed:.0f}s total)")
        else:
            # After 5 minutes, log every minute
            if int(elapsed) % 60 == 0:
                logger.info(f"⏱️ Still working on model... ({elapsed:.0f}s elapsed)")

        time.sleep(10)

logger.info(f"🚀 Loading WhisperX model: {WHISPERX_MODEL}")
logger.info(f"📊 Device: {device}, Compute: {compute_type}, Batch: {WHISPERX_BATCH_SIZE}")
logger.info(f"⏰ First-time model download may take 2-5 minutes...")
logger.info(f"💡 Subsequent starts will be much faster (model is cached)")

# Initialize WhisperX model with progress tracking
start_time = time.time()
stop_event = threading.Event()

# Start progress logger thread
progress_thread = threading.Thread(
    target=log_loading_progress,
    args=(start_time, stop_event),
    daemon=True
)
progress_thread.start()

try:
    logger.info(f"⚙️ Initializing WhisperX model: {WHISPERX_MODEL}")
    logger.info(f"🔧 Using device: {device}, compute type: {compute_type}")

    # Capture WhisperX stdout/stderr
    import sys
    import io
    
    # Create a stream to capture output
    captured_output = io.StringIO()
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    # Redirect stdout/stderr to capture WhisperX messages
    sys.stdout = captured_output
    sys.stderr = captured_output

    model = whisperx.load_model(
        WHISPERX_MODEL,
        device=device,
        compute_type=compute_type
    )

    # Restore stdout/stderr
    sys.stdout = original_stdout
    sys.stderr = original_stderr
    
    # Log any captured output
    captured = captured_output.getvalue()
    if captured.strip():
        logger.info(f"📋 WhisperX output: {captured.strip()}")

    # Stop progress thread
    stop_event.set()
    progress_thread.join(timeout=1)

    elapsed = time.time() - start_time
    logger.info(f"✅ Model loaded and ready for transcription")

    # Log memory usage if GPU
    if device == 'cuda':
        allocated = torch.cuda.memory_allocated(0) / 1024**3
        reserved = torch.cuda.memory_reserved(0) / 1024**3
        logger.info(f"🎮 GPU memory usage: {allocated:.2f}GB allocated, {reserved:.2f}GB reserved")
        
except Exception as e:
    stop_event.set()
    elapsed = time.time() - start_time
    logger.error(f"❌ CRITICAL: Failed to load WhisperX model after {elapsed:.1f}s")
    logger.error(f"❌ Error type: {type(e).__name__}")
    logger.error(f"❌ Error message: {str(e)}")
    logger.error(f"❌ Model: {WHISPERX_MODEL}, Device: {device}, Compute: {compute_type}")
    
    # Log full traceback from WhisperX
    logger.error("❌ Full traceback from WhisperX:")
    logger.error(traceback.format_exc())
    
    # Provide helpful troubleshooting tips
    if "CUDA" in str(e) or "GPU" in str(e):
        logger.error("💡 GPU error detected - possible causes:")
        logger.error("   - CUDA drivers not installed")
        logger.error("   - GPU not accessible in container")
        logger.error("   - Insufficient VRAM")
        logger.error("   - Try setting WHISPERX_DEVICE=cpu in .env")
    elif "HTTP" in str(e) or "download" in str(e).lower():
        logger.error("💡 Download error detected - possible causes:")
        logger.error("   - No internet connection")
        logger.error("   - HuggingFace servers down")
        logger.error("   - Firewall blocking downloads")
    elif "memory" in str(e).lower() or "OOM" in str(e):
        logger.error("💡 Memory error detected - possible causes:")
        logger.error("   - Insufficient RAM/VRAM")
        logger.error("   - Try a smaller model (tiny, base)")
        logger.error("   - Try WHISPERX_COMPUTE_TYPE=int8")
    else:
        logger.error("💡 Check the error message above for details")
    
    logger.error("❌ Container will exit - fix the issue and restart")
    raise


class TranscriptionSession:
    """Manages a single transcription session for a user"""

    def __init__(self, websocket, user_id, audio_format='opus'):
        self.websocket = websocket
        self.user_id = user_id
        self.audio_format = audio_format  # 'opus' (Discord) or 'pcm' (WebRTC)

        # Dual buffer system to fix audio clipping
        self.session_buffer = bytearray()    # Keeps ALL audio for final transcription
        self.processing_buffer = bytearray() # For real-time chunks (can be trimmed)

        self.language = WHISPERX_LANGUAGE  # Use global config (defaults to 'en')
        self.is_active = True

        # Initialize Opus decoder only for 'opus' format (Discord)
        # For 'pcm' format (WebRTC), audio is already decoded by PyAV
        if audio_format == 'opus':
            self.opus_decoder = opuslib.Decoder(48000, 2)
            logger.info(f"📝 New transcription session for user {user_id} (format: opus)")
            logger.info(f"🎵 Opus decoder initialized (48kHz stereo, 20ms frames)")
        else:
            self.opus_decoder = None
            logger.info(f"📝 New transcription session for user {user_id} (format: pcm)")
            logger.info(f"🎵 PCM audio path (no Opus decoding, 48kHz stereo)")

        logger.info(f"🔄 Dual buffer system: session_buffer (full) + processing_buffer (chunks)")
    
    async def add_audio(self, audio_chunk):
        """
        Add audio chunk to buffers with format-specific handling

        For 'opus' format (Discord): Decode Opus frames to PCM
        For 'pcm' format (WebRTC): Use audio directly (already PCM from PyAV)
        """
        try:
            if self.audio_format == 'opus':
                # Discord path: Decode Opus to PCM (960 samples per 20ms frame at 48kHz)
                pcm_data = self.opus_decoder.decode(bytes(audio_chunk), frame_size=960)
            else:
                # WebRTC path: Already PCM from PyAV decode
                pcm_data = audio_chunk

            # Add to BOTH buffers (same logic for both formats)
            self.session_buffer.extend(pcm_data)    # Keeps ALL audio for final
            self.processing_buffer.extend(pcm_data) # For real-time chunks

            # Enhanced buffer tracking logging
            logger.info(f"📊 [WHISPERX_BUFFERS] session_buffer: {len(self.session_buffer)} bytes, "
                       f"processing_buffer: {len(self.processing_buffer)} bytes, "
                       f"format: {self.audio_format}")

            # Process in chunks for real-time transcription
            # Every ~2 seconds of PCM audio (48kHz * 2 bytes * 2 channels * 2 sec = 384KB)
            if len(self.processing_buffer) >= 384000:
                await self.process_audio_chunk()

        except opuslib.OpusError as e:
            logger.error(f"❌ Opus decode error: {e}")
        except Exception as e:
            logger.error(f"❌ Error adding audio: {e}")
    
    async def process_audio_chunk(self):
        """Process accumulated PCM audio and send partial results"""
        if len(self.processing_buffer) == 0:
            return
        
        try:
            # Save processing buffer as WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            with wave.open(temp_path, 'wb') as wav_file:
                wav_file.setnchannels(2)  # Stereo
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(48000)  # 48kHz
                wav_file.writeframes(bytes(self.processing_buffer))
            
            # Transcribe with WhisperX (force language to prevent auto-detection)
            audio = whisperx.load_audio(temp_path)
            result = model.transcribe(audio, batch_size=WHISPERX_BATCH_SIZE, language=self.language)
            
            # Extract segments
            segments = result.get("segments", [])
            
            # Collect all text
            transcript_parts = []
            for segment in segments:
                text = segment.get("text", "").strip()
                if text:
                    transcript_parts.append(text)
            
            # Send partial result if we got text
            if transcript_parts:
                partial_text = ' '.join(transcript_parts)
                await self.send_result('partial', partial_text)
            
            # Clean up temp file
            os.unlink(temp_path)
            
            # Trim processing buffer (keep only recent audio for next real-time chunk)
            # 48kHz * 2 bytes * 2 channels * 1 sec = 192KB
            self.processing_buffer = self.processing_buffer[-192000:]
            
        except Exception as e:
            logger.error(f"❌ Error processing audio chunk: {e}")
            await self.send_error(str(e))
    
    async def finalize(self):
        """Process all session audio and send final result"""
        if len(self.session_buffer) == 0:
            await self.send_result('final', '')
            return
        
        try:
            logger.info(f"🏁 Finalizing transcription for user {self.user_id}")
            logger.info(f"📊 Session buffer size: {len(self.session_buffer)} bytes ({len(self.session_buffer)/192000:.1f}s of audio)")
            
            # Save ALL session audio as WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            with wave.open(temp_path, 'wb') as wav_file:
                wav_file.setnchannels(2)  # Stereo
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(48000)  # 48kHz
                wav_file.writeframes(bytes(self.session_buffer))
            
            # Transcribe complete audio with WhisperX (force language to prevent auto-detection)
            audio = whisperx.load_audio(temp_path)
            result = model.transcribe(audio, batch_size=WHISPERX_BATCH_SIZE, language=self.language)
            
            # Extract segments
            segments = result.get("segments", [])
            
            # Collect all text
            transcript_parts = []
            for segment in segments:
                text = segment.get("text", "").strip()
                if text:
                    transcript_parts.append(text)
            
            # Filter non-word sounds before sending
            final_text = ' '.join(transcript_parts)

            # Log language detection and raw transcript for debugging
            detected_language = result.get('language', 'unknown')
            logger.info(f"📝 Raw transcript ({len(transcript_parts)} segments, lang={detected_language}): \"{final_text}\"")

            if self.is_valid_speech(final_text):
                await self.send_result('final', final_text)
                logger.info(f"✅ Final transcript for {self.user_id}: \"{final_text}\"")
            else:
                await self.send_result('final', '')
                logger.warning(f"🚫 Filtered non-speech audio for {self.user_id}: \"{final_text}\" (validation failed)")
            
            # Clean up
            os.unlink(temp_path)
            self.session_buffer.clear()
            
        except Exception as e:
            logger.error(f"❌ Error finalizing transcription: {e}")
            await self.send_error(str(e))
    
    async def send_result(self, result_type, text):
        """Send transcription result to client"""
        try:
            message = json.dumps({
                'type': result_type,
                'text': text,
                'userId': self.user_id
            })
            await self.websocket.send(message)
        except Exception as e:
            logger.error(f"❌ Error sending result: {e}")
    
    async def send_error(self, error_message):
        """Send error message to client"""
        try:
            message = json.dumps({
                'type': 'error',
                'error': error_message,
                'userId': self.user_id
            })
            await self.websocket.send(message)
        except Exception as e:
            logger.error(f"❌ Error sending error message: {e}")
    
    def is_valid_speech(self, text):
        """
        Check if transcript contains valid speech vs non-word sounds/silence.

        Improved version with better logging and less aggressive filtering.
        """
        # Filter blank/empty transcripts
        if not text or len(text.strip()) == 0:
            logger.debug(f"🔍 Validation: Empty transcript")
            return False

        text_clean = text.lower().strip()

        # Remove punctuation for better matching
        import string
        text_clean = text_clean.translate(str.maketrans('', '', string.punctuation))

        # Filter out common non-word sounds and filler words
        # Relaxed: Only filter extremely obvious non-speech
        non_speech_patterns = [
            # Filler sounds (only very short ones)
            'hmm', 'uhm', 'uh', 'um', 'mm', 'mmm', 'hm',

            # Single letter/sounds (only single chars)
            'a', 'i', 'o', 'e', 'u', 'n', 'm',

            # Noise descriptions
            'cough', 'sneeze', 'sigh', 'breath', 'noise', 'sound',
            'music', 'static', 'inaudible', 'silence'
        ]

        words = text_clean.split()

        # Must have at least one word
        if len(words) == 0:
            logger.debug(f"🔍 Validation: No words after cleaning")
            return False

        # For single words: be more lenient
        if len(words) == 1:
            word = words[0]
            # Accept any word >= 2 chars that's not in strict filter list
            if len(word) < 2:
                logger.debug(f"🔍 Validation: Single word too short: \"{word}\"")
                return False
            if word in non_speech_patterns:
                logger.debug(f"🔍 Validation: Single word is non-speech pattern: \"{word}\"")
                return False
            # Accept it (removed aggressive 3-char minimum)
            return True

        # For multi-word: count valid words (not in filter list and 2+ chars)
        valid_words = []
        for word in words:
            if len(word) >= 2 and word not in non_speech_patterns:
                valid_words.append(word)

        # Relaxed threshold: accept if at least 1 valid word (was 2)
        if len(valid_words) >= 1:
            return True

        # Fallback: check validity ratio (60% threshold, was 70%)
        validity_ratio = len(valid_words) / len(words) if len(words) > 0 else 0
        accepted = validity_ratio >= 0.6

        if not accepted:
            logger.debug(f"🔍 Validation: Failed ratio check ({validity_ratio:.0%}): \"{text}\"")

        return accepted
    
    def close(self):
        """Clean up session resources"""
        self.is_active = False
        
        # Clear both buffers
        self.session_buffer.clear()
        self.processing_buffer.clear()
        
        logger.info(f"🔒 Closed transcription session for user {self.user_id}")


async def handle_client(websocket, path):
    """Handle WebSocket client connection"""
    session = None
    
    try:
        remote_addr = websocket.remote_address if hasattr(websocket, 'remote_address') else 'unknown'
        logger.info(f"🔌 New WebSocket connection from {remote_addr}")
        logger.info(f"   Path: {path}")
        
        async for message in websocket:
            # Handle JSON control messages
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    if msg_type == 'start':
                        # Initialize new session with format support
                        user_id = data.get('userId', 'unknown')
                        language = data.get('language', 'en')
                        audio_format = data.get('audio_format', 'opus')  # Default to 'opus' for backward compatibility
                        session = TranscriptionSession(websocket, user_id, audio_format=audio_format)
                        session.language = language
                        logger.info(f"🎤 Started session for user {user_id} (language: {language}, format: {audio_format})")
                    
                    elif msg_type == 'finalize':
                        # Finalize transcription
                        if session:
                            await session.finalize()
                    
                    elif msg_type == 'close':
                        # Close session
                        if session:
                            session.close()
                        break
                    
                except json.JSONDecodeError:
                    logger.error("❌ Invalid JSON message received")
            
            # Handle binary audio data
            elif isinstance(message, bytes):
                if session and session.is_active:
                    await session.add_audio(message)
    
    except websockets.exceptions.ConnectionClosed:
        logger.info("🔌 WebSocket connection closed")
    
    except Exception as e:
        logger.error(f"❌ Error handling client: {e}")
    
    finally:
        if session:
            session.close()


async def health_check(request):
    """Health check endpoint - returns 200 when model is loaded"""
    response_data = {
        "status": "ready",
        "model": WHISPERX_MODEL,
        "device": device,
        "gpu_name": gpu_name
    }
    return web.Response(text=json.dumps(response_data), content_type='application/json')


async def start_http_server():
    """Start HTTP server for health checks"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Run HTTP server on port 4902 (next to WebSocket port 4901)
    site = web.TCPSite(runner, '0.0.0.0', 4902)
    await site.start()
    logger.info(f"✅ Health check server listening on http://0.0.0.0:4902/health")


async def main():
    """Start both WebSocket and HTTP servers"""
    logger.info(f"🚀 Starting WhisperX WebSocket server on port {SERVER_PORT}")
    logger.info(f"📊 Model: {WHISPERX_MODEL}, Device: {device}, Compute: {compute_type}")
    
    # Start HTTP health check server
    await start_http_server()
    
    # Start WebSocket server
    async with websockets.serve(handle_client, "0.0.0.0", SERVER_PORT):
        logger.info(f"✅ WhisperX WebSocket server listening on ws://0.0.0.0:{SERVER_PORT}")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Shutting down WhisperX server")
