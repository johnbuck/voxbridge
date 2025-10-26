#!/usr/bin/env python3
"""
============================================================
Streaming Response Handler
Handles streaming AI responses from n8n webhook
- Receives text chunks as they arrive from AI
- Buffers and extracts complete sentences
- Sends sentences to Chatterbox TTS streaming endpoint
- Plays audio immediately as it's generated
============================================================
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import time
from typing import Optional, TYPE_CHECKING
from io import BytesIO

import httpx
import discord
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

if TYPE_CHECKING:
    from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


class StreamingResponseHandler:
    """Handles streaming text-to-speech responses from n8n"""

    def __init__(self, voice_client, user_id: str, options: dict = None,
                 on_ai_response: Optional[Callable[[str, bool], Awaitable[None]]] = None,
                 metrics_tracker = None,
                 t_speech_start: Optional[float] = None,
                 t_transcription_complete: Optional[float] = None,
                 speaker_manager = None):
        """
        Initialize streaming response handler

        Args:
            voice_client: Discord voice client for audio playback
            user_id: Discord user ID
            options: TTS options from n8n (optional)
            on_ai_response: Callback for broadcasting AI responses (optional)
            metrics_tracker: Optional metrics tracker for recording latencies
            t_speech_start: Timestamp when user started speaking (for total pipeline metric)
            t_transcription_complete: Timestamp when transcript was finalized (for UX metrics)
            speaker_manager: Optional speaker manager to stop thinking indicator when TTS starts
        """
        self.voice_client = voice_client
        self.user_id = user_id
        self.buffer = ''
        self.is_processing = False
        self.options = options or {}
        self.on_ai_response = on_ai_response
        self.metrics_tracker = metrics_tracker
        self.t_speech_start = t_speech_start
        self.t_transcription_complete = t_transcription_complete
        self.speaker_manager = speaker_manager

        # Track TTS failure
        self.tts_failed = False

        # Track time to first audio byte (for critical UX metric)
        self.t_first_audio_byte = None

        # Track if we've stopped the thinking indicator already
        self.thinking_indicator_stopped = False

        # Configuration
        self.chatterbox_url = os.getenv('CHATTERBOX_URL', 'http://localhost:4800/v1')
        self.chatterbox_voice_id = os.getenv('CHATTERBOX_VOICE_ID')
        self.use_progressive_playback = os.getenv('USE_PROGRESSIVE_TTS_PLAYBACK', 'false').lower() == 'true'

        logger.info(f"📋 StreamingResponseHandler initialized for user {user_id}")
        logger.info(f"   Options: {self.options}")
        logger.info(f"   Strategy: Collect full response, single TTS request")
        logger.info(f"   TTS Playback Mode: {'Progressive Streaming' if self.use_progressive_playback else 'Buffered Download'}")

    def _stop_thinking_indicator(self) -> None:
        """
        Stop the looping thinking indicator sound if it's playing
        Called once when TTS playback begins
        """
        if self.speaker_manager and not self.thinking_indicator_stopped:
            logger.info("🎵 TTS playback starting - stopping thinking indicator")
            self.speaker_manager._stop_thinking_indicator()
            self.thinking_indicator_stopped = True

    async def on_chunk(self, text_chunk: str) -> None:
        """
        Handle incoming text chunk from n8n streaming webhook
        Accumulates text without processing until finalize()

        Args:
            text_chunk: Text chunk from n8n
        """
        if not text_chunk:
            return

        logger.info(f"📨 Received chunk: \"{text_chunk}\"")
        self.buffer += text_chunk
        # Note: Chunks are NOT broadcast to frontend - only complete response at finalize()

    async def _process_full_response(self) -> None:
        """Process complete AI response with single TTS request"""

        # Check Chatterbox health before processing
        if not await self._check_chatterbox_health():
            logger.error("❌ Chatterbox TTS is not responding, skipping TTS processing")
            self.tts_failed = True
            return

        if not self.buffer.strip():
            logger.warning("⚠️ No text to synthesize")
            return

        try:
            # Record TTS queue latency (text ready → TTS request sent)
            t_text_ready = time.time()
            t_start_tts = time.time()

            # TTS queue latency is minimal here since we process immediately
            # In a true queuing system, this would measure queue wait time
            tts_queue_latency_s = t_start_tts - t_text_ready
            if self.metrics_tracker and tts_queue_latency_s > 0.001:  # Only log if > 1ms
                logger.info(f"⏱️ LATENCY [TTS queue]: {tts_queue_latency_s:.3f}s")
                self.metrics_tracker.record_tts_queue_latency(tts_queue_latency_s)

            logger.info(f"🎵 Processing full response ({len(self.buffer)} chars)")
            await self._synthesize_and_play(self.buffer.strip(), t_start_tts)
        except Exception as e:
            logger.error(f"❌ TTS failed for complete response: {type(e).__name__}: {e}")
            self.tts_failed = True

    async def _check_chatterbox_health(self) -> bool:
        """
        Check if Chatterbox TTS server is responding

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Health endpoint is at root level, not under /v1
            # If base URL ends with /v1, strip it for health check
            if self.chatterbox_url.endswith('/v1'):
                base_url = self.chatterbox_url[:-3]  # Remove /v1
            else:
                base_url = self.chatterbox_url

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"⚠️ Chatterbox health check failed: {e}")
            return False

    def _validate_and_repair_wav(self, audio_data: bytes) -> bytes:
        """
        Validate and repair WAV file headers

        Args:
            audio_data: Raw WAV data

        Returns:
            Repaired WAV data with corrected headers
        """
        # Check minimum size for valid WAV (44 bytes for header)
        if len(audio_data) < 44:
            logger.warning(f"⚠️ WAV data too small ({len(audio_data)} bytes), using as-is")
            return audio_data

        # Check RIFF header
        if audio_data[:4] != b'RIFF':
            logger.warning("⚠️ Invalid WAV header (missing RIFF), using as-is")
            return audio_data

        # Read current file size from header
        current_file_size = int.from_bytes(audio_data[4:8], 'little')
        logger.debug(f"🔍 WAV validation - Total: {len(audio_data)} bytes, Header file size: {current_file_size}")

        # Make mutable copy
        audio_data = bytearray(audio_data)

        # Fix file size field (bytes 4-7) - should be file_size - 8
        actual_file_size = len(audio_data) - 8
        if current_file_size != actual_file_size:
            logger.debug(f"   🔧 Fixing file size: {current_file_size} -> {actual_file_size}")
            audio_data[4:8] = actual_file_size.to_bytes(4, 'little')

        # Check for 'data' chunk and fix its size
        try:
            # Find 'data' chunk (usually at offset 36 but can vary)
            data_pos = audio_data.find(b'data')
            if data_pos != -1 and data_pos + 8 <= len(audio_data):
                # Read current data chunk size
                current_data_size = int.from_bytes(audio_data[data_pos+4:data_pos+8], 'little')

                # Size of data chunk = total size - (data chunk start + 8)
                actual_data_size = len(audio_data) - (data_pos + 8)

                if current_data_size != actual_data_size:
                    logger.debug(f"   🔧 Fixing data chunk size at offset {data_pos}: {current_data_size} -> {actual_data_size}")
                    audio_data[data_pos+4:data_pos+8] = actual_data_size.to_bytes(4, 'little')

                # Read channel count from fmt chunk (at offset 22)
                if len(audio_data) >= 24:
                    channels = int.from_bytes(audio_data[22:24], 'little')
                    logger.debug(f"   📊 Audio format: {channels} channel(s)")

                logger.debug(f"   ✅ WAV headers repaired")
        except Exception as e:
            logger.warning(f"⚠️ Could not repair data chunk: {e}")

        return bytes(audio_data)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((
            httpx.HTTPStatusError,
            httpx.RemoteProtocolError,
            httpx.ReadTimeout,
            httpx.TimeoutException,
            httpx.NetworkError
        )),
        reraise=True
    )
    async def _synthesize_to_stream(self, text: str, t_start_tts: float = None) -> bytes:
        """
        Synthesize text to audio and return as bytes with retry logic

        Args:
            text: Text to synthesize
            t_start_tts: Optional timestamp when TTS processing started

        Returns:
            Audio data as bytes

        Raises:
            httpx.HTTPStatusError: After 3 failed attempts (500 errors, etc)
            httpx.RemoteProtocolError: After 3 failed attempts (connection drops)
            httpx.ReadTimeout: After 3 failed attempts (timeouts)
        """
        t_start = time.time()

        # Build TTS request
        tts_data = self._build_tts_request(text)

        try:
            # Stream TTS from Chatterbox server with smaller chunks for faster response
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    'POST',
                    f"{self.chatterbox_url}/audio/speech/stream/upload",
                    data=tts_data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                ) as response:
                    response.raise_for_status()

                    # Collect audio chunks with smaller chunk size for lower latency
                    audio_data = bytearray()
                    chunk_size = 2048  # Reduced from 8192 for faster first-byte
                    total_bytes = 0
                    first_byte_received = False

                    async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                        # Log and record latency for first audio byte
                        if not first_byte_received and t_start_tts:
                            self.t_first_audio_byte = time.time()
                            t_to_first_byte = self.t_first_audio_byte - t_start_tts
                            logger.info(f"⏱️ LATENCY [response complete → Chatterbox first byte]: {t_to_first_byte:.3f}s")
                            if self.metrics_tracker:
                                self.metrics_tracker.record_tts_first_byte_latency(t_to_first_byte)

                            # Record time to first audio (CRITICAL UX METRIC - perceived latency)
                            if self.t_transcription_complete and self.metrics_tracker:
                                time_to_first_audio = self.t_first_audio_byte - self.t_transcription_complete
                                logger.info(f"⏱️ ⭐ CRITICAL UX [transcript complete → first audio byte]: {time_to_first_audio:.3f}s")
                                self.metrics_tracker.record_time_to_first_audio(time_to_first_audio)

                            first_byte_received = True

                        audio_data.extend(chunk)
                        total_bytes += len(chunk)

                    t_download = time.time() - t_start
                    logger.info(f"   ✅ TTS stream complete ({total_bytes} bytes, {t_download:.2f}s)")

                    # Record TTS generation latency (TTS sent → all audio downloaded)
                    if self.metrics_tracker:
                        logger.info(f"⏱️ LATENCY [TTS generation - request → download complete]: {t_download:.3f}s")
                        self.metrics_tracker.record_tts_generation_latency(t_download)

                    # Validate and repair WAV headers to prevent FFmpeg warnings
                    audio_data = self._validate_and_repair_wav(bytes(audio_data))

                    return audio_data

        except httpx.HTTPStatusError as e:
            logger.error(f"   ❌ Chatterbox HTTP error {e.response.status_code}: {e.response.text[:200]}")
            logger.error(f"   📝 Failed text: \"{text[:100]}...\"")
            raise
        except httpx.RemoteProtocolError as e:
            logger.error(f"   ❌ Connection error: {e}")
            logger.error(f"   📝 Failed text: \"{text[:100]}...\"")
            raise
        except Exception as e:
            logger.error(f"   ❌ Unexpected TTS error: {type(e).__name__}: {e}")
            logger.error(f"   📝 Failed text: \"{text[:100]}...\"")
            raise

    def _build_tts_request(self, text: str) -> dict:
        """Build TTS request data with Chatterbox streaming parameters"""
        tts_data = {
            'input': text,  # Complete AI response text
            'response_format': self.options.get('outputFormat', 'wav'),
            'speed': float(self.options.get('speedFactor', 1.0))
        }

        # Add voice parameter
        voice_mode = self.options.get('voiceMode')
        reference_audio = self.options.get('referenceAudioFilename')

        if voice_mode == 'clone' and reference_audio:
            tts_data['voice'] = reference_audio
        elif self.chatterbox_voice_id:
            tts_data['voice'] = self.chatterbox_voice_id
        else:
            tts_data['voice'] = 'default'

        # Add generation parameters
        if 'temperature' in self.options:
            tts_data['temperature'] = float(self.options['temperature'])
        if 'exaggeration' in self.options:
            tts_data['exaggeration'] = float(self.options['exaggeration'])
        if 'cfgWeight' in self.options:
            tts_data['cfg_weight'] = float(self.options['cfgWeight'])

        # Chatterbox streaming parameters (let Chatterbox handle internal chunking)
        # Using "fast" defaults for lowest latency (optimized for chat/voice applications)
        tts_data['streaming_strategy'] = self.options.get('streamingStrategy', 'word')
        tts_data['streaming_chunk_size'] = int(self.options.get('streamingChunkSize', 100))
        tts_data['streaming_buffer_size'] = int(self.options.get('streamingBufferSize', 3))
        tts_data['streaming_quality'] = self.options.get('streamingQuality', 'fast')

        return tts_data

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True
    )
    async def _synthesize_and_play(self, text: str, t_start_tts: float = None) -> None:
        """
        Send text to Chatterbox TTS and play audio
        Routes to progressive or buffered mode based on configuration

        Args:
            text: Text to synthesize
            t_start_tts: Optional timestamp when TTS processing started
        """
        try:
            # Route to progressive streaming playback if enabled
            if self.use_progressive_playback:
                await self._synthesize_and_play_progressive(text, t_start_tts)
            else:
                # Use buffered mode (download complete file before playback)
                t_start = time.time()
                logger.info(f"🔊 Synthesizing: \"{text}\"")

                audio_data = await self._synthesize_to_stream(text, t_start_tts)

                t_total = time.time() - t_start
                logger.info(f"   ⏱️ Total synthesis time: {t_total:.2f}s")

                # Play audio
                await self._play_audio_stream(audio_data)

        except Exception as e:
            logger.error(f"❌ Error with TTS: {e}")
            raise

    async def _play_audio_stream(self, audio_data: bytes) -> None:
        """
        Play audio from in-memory bytes using temporary file

        Args:
            audio_data: Audio data as bytes (WAV format)
        """
        if not self.voice_client or not self.voice_client.is_connected():
            logger.warning("⚠️ Not connected to voice channel")
            return

        try:
            t_start = time.time()
            logger.info(f"🔊 Playing audio ({len(audio_data)} bytes)")

            # Wait for current audio to finish if playing
            while self.voice_client.is_playing():
                await asyncio.sleep(0.05)

            # Use temp file method (reliable, minimal latency cost)
            await self._play_with_temp_file(audio_data)

            t_playback = time.time() - t_start
            logger.info(f"✅ Audio playback complete ({t_playback:.2f}s)")

            # Record audio playback latency
            if self.metrics_tracker:
                logger.info(f"⏱️ LATENCY [audio playback - ready → complete]: {t_playback:.3f}s")
                self.metrics_tracker.record_audio_playback_latency(t_playback)

        except Exception as e:
            logger.error(f"❌ Error playing audio: {e}")
            raise

    async def _play_with_temp_file(self, audio_data: bytes) -> None:
        """
        Play audio using temporary file (legacy method)

        Args:
            audio_data: Audio data as bytes
        """
        import tempfile

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(audio_data)

        try:
            # Create FFmpeg audio source from file
            # Explicitly handle mono/stereo conversion to avoid FFmpeg warnings
            # -loglevel error: suppress warnings from input processing
            # -ac 2: explicitly convert mono to stereo (simpler than aformat)
            # -ar 48000: resample to 48kHz (Discord requirement)
            t_ffmpeg_start = time.time()
            before_options = '-loglevel error'
            options = '-vn -ac 2 -ar 48000'
            audio_source = discord.FFmpegPCMAudio(temp_path, before_options=before_options, options=options)
            t_ffmpeg_end = time.time()

            # Record FFmpeg processing latency
            ffmpeg_latency_ms = (t_ffmpeg_end - t_ffmpeg_start) * 1000
            if self.metrics_tracker and ffmpeg_latency_ms > 1.0:  # Only log if > 1ms
                logger.info(f"⏱️ LATENCY [FFmpeg processing]: {ffmpeg_latency_ms:.2f}ms")
                self.metrics_tracker.record_ffmpeg_processing_latency(ffmpeg_latency_ms)

            # Stop thinking indicator before playing TTS audio
            self._stop_thinking_indicator()

            # Play audio
            self.voice_client.play(audio_source)

            # Wait for playback to finish
            while self.voice_client.is_playing():
                await asyncio.sleep(0.05)

        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"⚠️ Failed to delete temp file {temp_path}: {e}")

    async def _synthesize_and_play_progressive(self, text: str, t_start_tts: float = None) -> None:
        """
        Progressive audio playback - stream audio bytes to FFmpeg as they arrive
        Reduces latency by starting playback before full download completes

        Uses raw PCM format (WAV header stripped) to avoid FFmpeg corruption warnings
        when streaming incomplete files.

        Args:
            text: Text to synthesize
            t_start_tts: Optional timestamp when TTS processing started
        """
        try:
            import tempfile
            import wave
            import io

            t_start = time.time()
            logger.info(f"🔊 Progressive synthesis: \"{text}\"")

            # Build TTS request
            tts_data = self._build_tts_request(text)

            # Create temp file for raw PCM data (not WAV)
            temp_file = tempfile.NamedTemporaryFile(suffix='.pcm', delete=False)
            temp_path = temp_file.name

            try:
                # Stream TTS from Chatterbox
                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream(
                        'POST',
                        f"{self.chatterbox_url}/audio/speech/stream/upload",
                        data=tts_data,
                        headers={'Content-Type': 'application/x-www-form-urlencoded'}
                    ) as response:
                        response.raise_for_status()

                        # Buffer configuration
                        MIN_BUFFER_SIZE = 100 * 1024  # 100KB minimum buffer before playback starts
                        WAV_HEADER_SIZE = 44

                        # Audio properties (extracted from WAV header)
                        sample_rate = None
                        channels = None
                        sampwidth = None

                        # Tracking
                        pcm_bytes = 0
                        total_bytes_received = 0
                        first_byte_received = False
                        playback_started = False
                        wav_header_buffer = bytearray()

                        chunk_size = 8192

                        async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                            total_bytes_received += len(chunk)

                            # Log and record latency for first audio byte
                            if not first_byte_received and t_start_tts:
                                self.t_first_audio_byte = time.time()
                                t_to_first_byte = self.t_first_audio_byte - t_start_tts
                                logger.info(f"⏱️ LATENCY [response complete → Chatterbox first byte]: {t_to_first_byte:.3f}s")
                                if self.metrics_tracker:
                                    self.metrics_tracker.record_tts_first_byte_latency(t_to_first_byte)

                                # Record time to first audio (CRITICAL UX METRIC)
                                if self.t_transcription_complete and self.metrics_tracker:
                                    time_to_first_audio = self.t_first_audio_byte - self.t_transcription_complete
                                    logger.info(f"⏱️ ⭐ CRITICAL UX [transcript complete → first audio byte]: {time_to_first_audio:.3f}s")
                                    self.metrics_tracker.record_time_to_first_audio(time_to_first_audio)

                                first_byte_received = True

                            # If we haven't parsed the WAV header yet
                            if sample_rate is None:
                                wav_header_buffer.extend(chunk)

                                # Once we have at least 44 bytes, parse WAV header
                                if len(wav_header_buffer) >= WAV_HEADER_SIZE:
                                    # Parse WAV header to get audio properties
                                    try:
                                        with wave.open(io.BytesIO(bytes(wav_header_buffer[:WAV_HEADER_SIZE])), 'rb') as wf:
                                            sample_rate = wf.getframerate()
                                            channels = wf.getnchannels()
                                            sampwidth = wf.getsampwidth()

                                        logger.info(f"📊 Parsed WAV header: {sample_rate}Hz, {channels}ch, {sampwidth*8}bit")

                                        # Write any PCM data beyond the header
                                        if len(wav_header_buffer) > WAV_HEADER_SIZE:
                                            pcm_data = wav_header_buffer[WAV_HEADER_SIZE:]
                                            temp_file.write(pcm_data)
                                            temp_file.flush()
                                            pcm_bytes += len(pcm_data)

                                        # Clear header buffer, we don't need it anymore
                                        wav_header_buffer.clear()

                                    except Exception as e:
                                        logger.error(f"❌ Failed to parse WAV header: {e}")
                                        raise
                            else:
                                # Header already parsed, write raw PCM data
                                temp_file.write(chunk)
                                temp_file.flush()
                                pcm_bytes += len(chunk)

                                # Start playback once we have enough PCM buffered
                                if not playback_started and pcm_bytes >= MIN_BUFFER_SIZE:
                                    logger.info(f"🎵 Starting progressive playback with {pcm_bytes} bytes PCM buffered")

                                    # Close temp file for writing, will be reopened by FFmpeg
                                    temp_file.close()

                                    # Start FFmpeg playback with raw PCM format
                                    t_ffmpeg_start = time.time()

                                    # Map sample width to PCM format
                                    if sampwidth == 2:
                                        pcm_format = 's16le'  # 16-bit signed little-endian
                                    elif sampwidth == 1:
                                        pcm_format = 'u8'     # 8-bit unsigned
                                    elif sampwidth == 3:
                                        pcm_format = 's24le'  # 24-bit signed little-endian
                                    elif sampwidth == 4:
                                        pcm_format = 's32le'  # 32-bit signed little-endian
                                    else:
                                        logger.warning(f"⚠️ Unknown sample width {sampwidth}, defaulting to s16le")
                                        pcm_format = 's16le'

                                    # Tell FFmpeg this is raw PCM, not WAV
                                    before_options = f'-f {pcm_format} -ar {sample_rate} -ac {channels}'
                                    options = '-vn -ac 2 -ar 48000'  # Output format for Discord

                                    audio_source = discord.FFmpegPCMAudio(
                                        temp_path,
                                        before_options=before_options,
                                        options=options
                                    )

                                    ffmpeg_latency_ms = (time.time() - t_ffmpeg_start) * 1000
                                    if self.metrics_tracker and ffmpeg_latency_ms > 1.0:
                                        logger.info(f"⏱️ LATENCY [FFmpeg processing]: {ffmpeg_latency_ms:.2f}ms")
                                        self.metrics_tracker.record_ffmpeg_processing_latency(ffmpeg_latency_ms)

                                    # Stop thinking indicator before playing TTS audio
                                    self._stop_thinking_indicator()

                                    # Start playing audio
                                    self.voice_client.play(audio_source)
                                    playback_started = True
                                    logger.info(f"▶️ Playback started (raw PCM), continuing download in background...")

                                    # Reopen temp file for continued writing
                                    temp_file = open(temp_path, 'ab')

                        # Close file after full download
                        if not temp_file.closed:
                            temp_file.close()

                        t_download = time.time() - t_start
                        logger.info(f"   ✅ TTS stream complete ({total_bytes_received} bytes total, {pcm_bytes} bytes PCM, {t_download:.2f}s)")

                        # Record TTS generation latency
                        if self.metrics_tracker:
                            logger.info(f"⏱️ LATENCY [TTS generation - request → download complete]: {t_download:.3f}s")
                            self.metrics_tracker.record_tts_generation_latency(t_download)

                        # Wait for playback to complete if it started
                        if playback_started:
                            while self.voice_client.is_playing():
                                await asyncio.sleep(0.05)
                        else:
                            # If playback never started (file too small), play now
                            if sample_rate:
                                logger.warning("⚠️ File smaller than buffer threshold, playing complete file")

                                # Map sample width to PCM format
                                if sampwidth == 2:
                                    pcm_format = 's16le'
                                elif sampwidth == 1:
                                    pcm_format = 'u8'
                                elif sampwidth == 3:
                                    pcm_format = 's24le'
                                elif sampwidth == 4:
                                    pcm_format = 's32le'
                                else:
                                    pcm_format = 's16le'

                                t_ffmpeg_start = time.time()
                                before_options = f'-f {pcm_format} -ar {sample_rate} -ac {channels}'
                                options = '-vn -ac 2 -ar 48000'
                                audio_source = discord.FFmpegPCMAudio(
                                    temp_path,
                                    before_options=before_options,
                                    options=options
                                )

                                ffmpeg_latency_ms = (time.time() - t_ffmpeg_start) * 1000
                                if self.metrics_tracker and ffmpeg_latency_ms > 1.0:
                                    self.metrics_tracker.record_ffmpeg_processing_latency(ffmpeg_latency_ms)

                                # Stop thinking indicator before playing TTS audio
                                self._stop_thinking_indicator()

                                self.voice_client.play(audio_source)
                                while self.voice_client.is_playing():
                                    await asyncio.sleep(0.05)

                        t_playback = time.time() - t_start
                        logger.info(f"✅ Progressive playback complete ({t_playback:.2f}s total)")

                        # Record audio playback latency
                        if self.metrics_tracker:
                            logger.info(f"⏱️ LATENCY [audio playback - ready → complete]: {t_playback:.3f}s")
                            self.metrics_tracker.record_audio_playback_latency(t_playback)

            finally:
                # Clean up temporary file
                try:
                    if not temp_file.closed:
                        temp_file.close()
                    os.unlink(temp_path)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to clean up temp file {temp_path}: {e}")

        except httpx.HTTPStatusError as e:
            logger.error(f"   ❌ Chatterbox HTTP error {e.response.status_code}: {e.response.text[:200]}")
            logger.error(f"   📝 Failed text: \"{text[:100]}...\"")
            raise
        except Exception as e:
            logger.error(f"❌ Progressive TTS failed: {type(e).__name__}: {e}")
            raise

    async def finalize(self) -> None:
        """Finalize streaming - process complete buffered AI response"""
        if self.buffer.strip():
            logger.info(f"🏁 Finalizing with complete response ({len(self.buffer)} chars)")

            # Broadcast complete AI response to frontend (single message)
            if self.on_ai_response:
                logger.info(f"📤 Broadcasting complete response to frontend: \"{self.buffer.strip()[:100]}...\"")
                await self.on_ai_response(self.buffer.strip(), True)

            # Process complete AI response with single TTS request
            await self._process_full_response()

            # Record total response latency (CRITICAL UX METRIC - perceived total time)
            if self.t_transcription_complete and self.metrics_tracker:
                t_pipeline_complete = time.time()
                total_response_latency = t_pipeline_complete - self.t_transcription_complete
                logger.info(f"⏱️ ⭐⭐⭐ CRITICAL UX [transcript complete → audio playback complete]: {total_response_latency:.3f}s")
                self.metrics_tracker.record_total_pipeline_latency(total_response_latency)

            # Clear buffer
            self.buffer = ''
        else:
            logger.info("🏁 Finalize called with empty buffer")

        # Log TTS status
        if self.tts_failed:
            logger.warning(f"⚠️ TTS Summary: Failed to process complete response")
        else:
            logger.info(f"✅ TTS Summary: Response processed successfully")
