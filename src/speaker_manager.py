#!/usr/bin/env python3
"""
============================================================
Speaker Manager
Handles single-speaker lock for voice transcription
- Only one speaker can be transcribed at a time
- Other speakers are ignored until current speaker finishes
- Automatic timeout after configurable max time
- Silence detection to finalize transcription
- Integrated streaming response support
============================================================
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional
from datetime import datetime

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from src.whisper_client import WhisperClient

logger = logging.getLogger(__name__)


class SpeakerManager:
    """Manages single-speaker lock and transcription workflow"""

    def __init__(self,
                 on_speaker_started=None,
                 on_speaker_stopped=None,
                 on_partial_transcript=None,
                 on_final_transcript=None,
                 on_ai_response=None,
                 metrics_tracker=None):
        self.active_speaker: Optional[str] = None
        self.active_speaker_username: Optional[str] = None
        self.lock_start_time: Optional[float] = None
        self.whisper_client: Optional[WhisperClient] = None
        self.timeout_task: Optional[asyncio.Task] = None
        self.silence_task: Optional[asyncio.Task] = None
        self.monitor_task: Optional[asyncio.Task] = None  # Main monitor task running TaskGroup
        self._stop_monitor = asyncio.Event()  # Signal to stop monitoring
        self.last_audio_time: Optional[float] = None
        self.is_finalizing: bool = False  # Guard against double-finalization
        self.voice_connection = None
        self.streaming_handler = None
        self.audio_receiver = None
        self.metrics_tracker = metrics_tracker
        self.thinking_indicator_source = None  # Track looping thinking indicator audio

        # Pipeline timing timestamps
        self.t_speech_start: Optional[float] = None  # User starts speaking
        self.t_whisper_connected: Optional[float] = None  # WhisperX connected
        self.t_first_partial: Optional[float] = None  # First partial transcript received
        self.t_transcription_complete: Optional[float] = None  # Final transcript ready
        self.t_silence_detected: Optional[float] = None  # Silence detected
        self.t_last_audio: Optional[float] = None  # Last audio received (for silence detection)
        self.t_thinking_indicator_start: Optional[float] = None  # Thinking indicator started
        self.t_thinking_indicator_stop: Optional[float] = None  # Thinking indicator stopped

        # WebSocket broadcast callbacks
        self.on_speaker_started = on_speaker_started
        self.on_speaker_stopped = on_speaker_stopped
        self.on_partial_transcript = on_partial_transcript
        self.on_final_transcript = on_final_transcript
        self.on_ai_response = on_ai_response

        # Configuration
        self.silence_threshold_ms = int(os.getenv('SILENCE_THRESHOLD_MS', '800'))
        self.max_speaking_time_ms = int(os.getenv('MAX_SPEAKING_TIME_MS', '45000'))
        self.use_streaming = os.getenv('USE_STREAMING', 'true').lower() != 'false'
        self.use_thinking_indicators = os.getenv('USE_THINKING_INDICATORS', 'true').lower() == 'true'
        self.thinking_indicator_probability = float(os.getenv('THINKING_INDICATOR_PROBABILITY', '0.8'))

        # Thinking indicators pool (weighted for personality mix: minimal/subtle + casual/friendly + playful/quirky)
        self.thinking_indicators = [
            # Minimal/Subtle (40% - brief, unobtrusive)
            {"text": "Mm", "weight": 3},
            {"text": "Hmm", "weight": 3},
            {"text": "Uh", "weight": 2},
            {"text": "Ah", "weight": 2},

            # Casual/Friendly (40% - natural, conversational)
            {"text": "Let me think", "weight": 2},
            {"text": "Interesting", "weight": 2},
            {"text": "Oh", "weight": 2},
            {"text": "Hmm, let's see", "weight": 2},

            # Playful/Quirky (20% - adds character)
            {"text": "Ooh, good question", "weight": 1},
            {"text": "Processing", "weight": 1},
            {"text": "*thinking noises*", "weight": 1},
        ]

        # Webhook configuration with test mode support
        n8n_webhook_prod = os.getenv('N8N_WEBHOOK_URL')
        n8n_webhook_test = os.getenv('N8N_WEBHOOK_TEST_URL')
        test_mode = os.getenv('N8N_TEST_MODE', 'false').lower() == 'true'

        # Select webhook based on test mode
        if test_mode and n8n_webhook_test:
            self.n8n_webhook_url = n8n_webhook_test
            logger.info(f"🧪 TEST MODE: Using test webhook: {self.n8n_webhook_url}")
        elif test_mode and not n8n_webhook_test:
            logger.warning("⚠️ TEST MODE enabled but N8N_WEBHOOK_TEST_URL not configured, using production webhook")
            self.n8n_webhook_url = n8n_webhook_prod
        else:
            self.n8n_webhook_url = n8n_webhook_prod
            if n8n_webhook_prod:
                logger.info(f"🌐 PRODUCTION MODE: Using webhook: {self.n8n_webhook_url}")

        logger.info(f"📋 SpeakerManager initialized:")
        logger.info(f"   Silence threshold: {self.silence_threshold_ms}ms")
        logger.info(f"   Max speaking time: {self.max_speaking_time_ms}ms")
        logger.info(f"   Streaming mode: {self.use_streaming}")

    def _get_tts_options(self, response_headers: dict) -> dict:
        """
        Get TTS options with priority logic:
        1. n8n webhook headers (X-TTS-Options) - highest priority
        2. Frontend dashboard settings - middle priority
        3. Environment defaults - lowest priority (handled by StreamingResponseHandler)

        Args:
            response_headers: HTTP response headers from n8n webhook

        Returns:
            dict: TTS options to use
        """
        # Priority 1: n8n webhook header
        if 'x-tts-options' in response_headers:
            try:
                options = json.loads(response_headers['x-tts-options'])
                logger.info(f"⚙️ Using TTS options from n8n webhook header: {options}")
                return options
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ Failed to parse X-TTS-Options header: {e}")
                logger.warning(f"   Header value: {response_headers.get('x-tts-options', 'N/A')}")
                # Fall through to next priority

        # Priority 2: Frontend dashboard settings
        try:
            # Access live module via sys.modules to avoid import caching
            # Use __main__ since discord_bot.py is the entry point
            import sys
            discord_bot_module = sys.modules.get('__main__') or sys.modules.get('src.discord_bot')
            if discord_bot_module:
                options_data = getattr(discord_bot_module, 'frontend_tts_options', None)
                if options_data and options_data.get('enabled'):
                    options = options_data.get('options', {})
                    logger.info(f"⚙️ Using TTS options from frontend dashboard: {options}")
                    return options
        except Exception as e:
            logger.warning(f"⚠️ Could not access frontend_tts_options: {e}")

        # Priority 3: Environment defaults (empty dict, defaults handled in StreamingResponseHandler)
        logger.info("⚙️ Using default TTS options from environment variables")
        return {}

    async def on_speaking_start(self, user_id: str, username: str, audio_stream) -> bool:
        """
        Handle user starting to speak

        Args:
            user_id: Discord user ID
            username: Discord username
            audio_stream: Audio stream from Discord

        Returns:
            True if this speaker is now active, False if ignored
        """
        # Someone already talking? Ignore this speaker
        if self.active_speaker:
            logger.info(f"🔇 Ignoring {username} ({user_id}) - {self.active_speaker_username} is currently speaking")
            return False

        # Lock to this speaker
        self.active_speaker = user_id
        self.active_speaker_username = username
        self.lock_start_time = time.time()
        self.last_audio_time = time.time()

        # Record pipeline start timestamp
        self.t_speech_start = time.time()
        self.t_whisper_connected = None
        self.t_first_partial = None
        self.t_transcription_complete = None
        self.t_silence_detected = None
        self.t_last_audio = self.t_speech_start

        logger.info(f"🎤 {username} ({user_id}) is now speaking (locked)")
        logger.info(f"⏱️ PIPELINE START at t={self.t_speech_start:.3f}")

        # Broadcast speaker started event
        if self.on_speaker_started:
            try:
                await self.on_speaker_started(user_id, username)
            except Exception as e:
                logger.error(f"❌ Error broadcasting speaker_started: {e}")

        # Start Whisper transcription stream
        await self._start_transcription(user_id, audio_stream)

        # Clear stop signal and start monitoring with TaskGroup
        self._stop_monitor.clear()
        self.monitor_task = asyncio.create_task(self._monitor_with_taskgroup())

        # Initialize silence detection timestamp
        self._start_silence_detection()

        return True

    async def on_speaking_end(self, user_id: str) -> None:
        """
        Handle user stopping speaking

        Args:
            user_id: Discord user ID
        """
        # Only process if this is the active speaker
        if self.active_speaker != user_id:
            return

        logger.info(f"🔇 {user_id} stopped speaking - waiting for silence confirmation")

        # Start silence detection timer (no await needed - just creates task)
        self._start_silence_detection()

    async def on_audio_data(self, user_id: str) -> None:
        """
        Handle incoming audio data (updates silence detection)

        Args:
            user_id: Discord user ID
        """
        if self.active_speaker != user_id:
            return

        # Simply update timestamp - the silence monitor loop will see this
        # No need to cancel/recreate tasks, eliminating recursion risk
        self.last_audio_time = time.time()

    async def _start_transcription(self, user_id: str, audio_stream) -> None:
        """Start WhisperX transcription for this speaker"""
        try:
            logger.info(f"🎙️ Starting transcription for {user_id}")

            # Create new WhisperClient with partial transcript callback
            self.whisper_client = WhisperClient()

            # Set callback for partial transcripts
            if self.on_partial_transcript:
                async def on_partial(text: str):
                    # Record first partial timestamp and latency
                    if self.t_first_partial is None and self.t_whisper_connected:
                        self.t_first_partial = time.time()
                        latency_s = self.t_first_partial - self.t_whisper_connected
                        logger.info(f"⏱️ LATENCY [WhisperX connected → first partial]: {latency_s:.3f}s")
                        if self.metrics_tracker:
                            self.metrics_tracker.record_first_partial_transcript_latency(latency_s)

                    if self.active_speaker and self.active_speaker_username:
                        try:
                            await self.on_partial_transcript(self.active_speaker, self.active_speaker_username, text)
                        except Exception as e:
                            logger.error(f"❌ Error broadcasting partial_transcript: {e}")

                self.whisper_client.on_partial_callback = on_partial

            # Connect to WhisperX and record timestamp
            await self.whisper_client.connect(user_id)
            self.t_whisper_connected = time.time()

            # Record WhisperX connection latency
            if self.t_speech_start and self.metrics_tracker:
                latency_s = self.t_whisper_connected - self.t_speech_start
                logger.info(f"⏱️ LATENCY [speech start → WhisperX connected]: {latency_s:.3f}s")
                self.metrics_tracker.record_whisper_connection_latency(latency_s)

            # Stream audio data to WhisperX
            asyncio.create_task(self._stream_audio(audio_stream))

        except Exception as e:
            logger.error(f"❌ Error starting transcription: {e}")
            await self._unlock()

    async def _stream_audio(self, audio_stream) -> None:
        """
        Stream audio chunks to WhisperX

        Args:
            audio_stream: Discord audio stream
        """
        try:
            logger.info("📡 Streaming audio to WhisperX")

            async for chunk in audio_stream:
                if not self.whisper_client or not self.whisper_client.is_connected:
                    logger.warning("⚠️ WhisperX disconnected, stopping audio stream")
                    break

                # Send Opus audio chunk to WhisperX
                await self.whisper_client.send_audio(chunk)

                # Update last audio time for silence detection
                self.last_audio_time = time.time()
                self.t_last_audio = time.time()

        except asyncio.CancelledError:
            logger.info("🛑 Audio streaming cancelled")
        except Exception as e:
            logger.error(f"❌ Error streaming audio: {e}")

    def _start_silence_detection(self) -> None:
        """
        Start or restart silence detection

        This is a lightweight operation that just updates last_audio_time.
        The actual monitoring is done by _monitor_with_taskgroup() which
        continuously checks for silence without creating new tasks.
        """
        self.last_audio_time = time.time()

    async def _monitor_with_taskgroup(self) -> None:
        """
        Monitor for silence and timeout using TaskGroup

        This method runs in a single long-lived task and uses asyncio.TaskGroup
        to manage monitoring subtasks safely without recursion issues.
        """
        try:
            async with asyncio.TaskGroup() as tg:
                # Create monitoring tasks within the TaskGroup
                self.timeout_task = tg.create_task(self._timeout_monitor())
                self.silence_task = tg.create_task(self._silence_monitor_loop())

                # Wait for stop signal or task completion
                logger.debug("📊 TaskGroup waiting on _stop_monitor Event")
                await self._stop_monitor.wait()
                logger.info("🏁 TaskGroup _stop_monitor Event received, exiting TaskGroup")

        except* asyncio.CancelledError:
            # TaskGroup propagates cancellation - this is expected during cleanup
            logger.debug("🛑 Monitor TaskGroup cancelled")
        except* Exception as e:
            # TaskGroup collects exceptions - log them
            logger.error(f"❌ Error in monitor TaskGroup: {e}")

    async def _silence_monitor_loop(self) -> None:
        """
        Continuous silence monitoring loop

        Instead of cancelling and recreating tasks, this loop continuously
        checks for silence. This eliminates recursion from rapid task creation.
        """
        try:
            while not self._stop_monitor.is_set():
                # Wait for silence threshold
                await asyncio.sleep(self.silence_threshold_ms / 1000.0)

                # Check if we should stop monitoring
                if self._stop_monitor.is_set():
                    break

                # Check if still silent
                if self.last_audio_time:
                    time_since_audio = (time.time() - self.last_audio_time) * 1000
                    if time_since_audio >= self.silence_threshold_ms:
                        # Record silence detection timestamp and latency
                        self.t_silence_detected = time.time()
                        silence_latency_ms = time_since_audio
                        logger.info(f"🤫 Silence detected ({int(silence_latency_ms)}ms) - finalizing")

                        # Record silence detection latency
                        if self.t_last_audio and self.metrics_tracker:
                            logger.info(f"⏱️ LATENCY [last audio → silence detected]: {silence_latency_ms:.1f}ms")
                            self.metrics_tracker.record_silence_detection_latency(silence_latency_ms)

                        await self._finalize_transcription('silence')
                        break  # Exit loop after finalizing

        except asyncio.CancelledError:
            logger.debug("🛑 Silence monitor loop cancelled")

    async def _timeout_monitor(self) -> None:
        """Monitor for max speaking time and force finalize"""
        try:
            # Wait for max speaking time or stop signal
            await asyncio.wait_for(
                self._stop_monitor.wait(),
                timeout=self.max_speaking_time_ms / 1000.0
            )
            # If we get here, stop was signaled before timeout
            logger.debug("🛑 Timeout monitor stopped before timeout")

        except asyncio.TimeoutError:
            # Timeout reached - force finalize
            logger.warning(f"⏱️ Timeout ({self.max_speaking_time_ms}ms) - forcing finalize")
            await self._finalize_transcription('timeout')

        except asyncio.CancelledError:
            logger.debug("🛑 Timeout monitor cancelled")

    async def _finalize_transcription(self, reason: str) -> None:
        """
        Finalize transcription and send to n8n

        Args:
            reason: Reason for finalization (silence/timeout)
        """
        # Guard against double-finalization (race between silence and timeout monitors)
        if self.is_finalizing:
            logger.debug(f"⚠️ Already finalizing, skipping duplicate finalization call (reason: {reason})")
            return

        self.is_finalizing = True

        # Signal timeout monitor to stop IMMEDIATELY (before blocking operations)
        # This prevents timeout from firing while we're processing TTS audio
        logger.info(f"🛑 Setting _stop_monitor Event (from finalize, reason: {reason})")
        self._stop_monitor.set()
        logger.info(f"✅ _stop_monitor.set() completed (timeout monitor should exit now)")

        if not self.whisper_client:
            logger.warning("⚠️ No WhisperClient to finalize")
            await self._unlock()
            return

        try:
            logger.info(f"🏁 Finalizing transcription (reason: {reason})")

            # Request finalization from WhisperX
            transcript = await self.whisper_client.finalize()
            self.t_transcription_complete = time.time()

            # Record transcription duration (first partial → final transcript)
            if self.t_first_partial and self.metrics_tracker:
                transcription_duration_s = self.t_transcription_complete - self.t_first_partial
                logger.info(f"⏱️ LATENCY [first partial → transcription complete]: {transcription_duration_s:.3f}s")
                self.metrics_tracker.record_transcription_duration(transcription_duration_s)

            # Close WhisperX connection
            await self.whisper_client.close()

            # Calculate and record legacy latency (overall transcript latency)
            if self.lock_start_time and self.metrics_tracker:
                latency_ms = (time.time() - self.lock_start_time) * 1000
                self.metrics_tracker.record_latency(latency_ms)
                logger.info(f"📊 Overall transcript latency: {latency_ms:.0f}ms")

            # Broadcast final transcript
            if transcript and self.on_final_transcript and self.active_speaker and self.active_speaker_username:
                try:
                    await self.on_final_transcript(self.active_speaker, self.active_speaker_username, transcript)
                except Exception as e:
                    logger.error(f"❌ Error broadcasting final_transcript: {e}")

            # Play thinking indicator while AI generates response (reduces perceived latency)
            if transcript:
                try:
                    await self._play_thinking_indicator()

                    # Log time from thinking indicator to n8n call (proves non-blocking)
                    if self.t_thinking_indicator_start:
                        t_before_n8n = time.time()
                        latency_to_n8n_ms = (t_before_n8n - self.t_thinking_indicator_start) * 1000
                        logger.info(f"⏱️ LATENCY [thinking indicator → n8n webhook]: {latency_to_n8n_ms:.2f}ms")
                except Exception as e:
                    logger.error(f"❌ Error playing thinking indicator: {e}")

            # Send to n8n webhook
            if transcript and self.n8n_webhook_url:
                await self._send_to_n8n(transcript)
            elif transcript:
                logger.info(f"📝 Transcript (no webhook): \"{transcript}\"")
            else:
                logger.info("📝 Empty transcript - skipping webhook")

        except Exception as e:
            logger.error(f"❌ Error finalizing transcription: {e}")
        finally:
            await self._unlock()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True
    )
    async def _send_to_n8n(self, transcript: str) -> None:
        """
        Send transcript to n8n webhook with automatic retry

        Args:
            transcript: Transcribed text
        """
        if not self.n8n_webhook_url:
            logger.warning("⚠️ No N8N_WEBHOOK_URL configured")
            return

        try:
            t_n8n_start = time.time()
            logger.info(f"📤 Sending to n8n: \"{transcript}\"")

            payload = {
                'text': transcript,
                'userId': self.active_speaker,
                'timestamp': datetime.now().isoformat(),
                'useStreaming': self.use_streaming
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                if self.use_streaming:
                    # Streaming mode - handle Server-Sent Events
                    logger.info("🌊 Sending with streaming enabled")
                    await self._handle_streaming_response(client, payload, t_n8n_start)
                else:
                    # Non-streaming mode - simple POST
                    logger.info("📨 Sending non-streaming request")
                    response = await client.post(self.n8n_webhook_url, json=payload)
                    response.raise_for_status()
                    logger.info(f"✅ n8n response: {response.status_code}")

        except Exception as e:
            logger.error(f"❌ Error sending to n8n: {e}")
            raise  # Re-raise to allow retry decorator to work

    async def _play_thinking_indicator(self) -> None:
        """
        Play a thinking indicator sound effect to give user feedback while AI generates response
        Helps reduce perceived latency by providing immediate acknowledgment

        Uses pre-recorded sound effect (gentle UI notification tone) that loops continuously
        until stopped by _stop_thinking_indicator() when TTS broadcast begins
        """
        import random
        import discord

        # Check if feature is enabled
        if not self.use_thinking_indicators:
            return

        # Check probability (allows for randomness - not every interaction gets indicator)
        if random.random() > self.thinking_indicator_probability:
            logger.debug("🎲 Skipping thinking indicator (probability check)")
            return

        # Check if voice connection is available
        if not self.voice_connection or not self.voice_connection.is_connected():
            logger.warning("⚠️ Cannot play thinking indicator - no voice connection")
            return

        # Stop any existing thinking indicator first
        self._stop_thinking_indicator()

        try:
            # Use pre-recorded thinking indicator sound effect
            sound_path = '/app/assets/thinking_indicator.wav'

            if not os.path.exists(sound_path):
                logger.warning(f"⚠️ Thinking indicator sound file not found: {sound_path}")
                return

            logger.info("💭 Playing looping thinking indicator sound")

            # Play the thinking indicator sound with infinite loop
            # -stream_loop -1 means loop infinitely
            before_options = '-loglevel error -stream_loop -1'
            options = '-vn -ac 2 -ar 48000'
            self.thinking_indicator_source = discord.FFmpegPCMAudio(
                sound_path,
                before_options=before_options,
                options=options
            )

            # Timestamp BEFORE play() call
            t_before_play = time.time()

            # Start playing (non-blocking - will loop until stopped)
            self.voice_connection.play(self.thinking_indicator_source)

            # Timestamp IMMEDIATELY AFTER play() call (proves non-blocking)
            t_after_play = time.time()

            # Store start time for duration tracking
            self.t_thinking_indicator_start = t_before_play

            # Log the play() overhead (should be ~1-3ms for non-blocking call)
            play_overhead_ms = (t_after_play - t_before_play) * 1000
            logger.info(f"⏱️ LATENCY [thinking indicator play() overhead]: {play_overhead_ms:.2f}ms")
            logger.info("✅ Thinking indicator loop started (non-blocking)")

        except Exception as e:
            logger.warning(f"⚠️ Failed to play thinking indicator: {e}")
            self.thinking_indicator_source = None
            self.t_thinking_indicator_start = None
            # Non-critical - continue without indicator

    def _stop_thinking_indicator(self) -> None:
        """
        Stop the looping thinking indicator sound
        Called when TTS broadcast begins
        """
        if self.thinking_indicator_source and self.voice_connection:
            try:
                if self.voice_connection.is_playing():
                    # Capture stop time
                    self.t_thinking_indicator_stop = time.time()

                    # Stop playback
                    self.voice_connection.stop()

                    # Calculate and log duration (gap filled by thinking indicator)
                    if self.t_thinking_indicator_start:
                        duration_s = self.t_thinking_indicator_stop - self.t_thinking_indicator_start
                        logger.info(f"🛑 Stopped thinking indicator loop")
                        logger.info(f"⏱️ LATENCY [thinking indicator duration]: {duration_s:.3f}s")

                        # Record to metrics if available
                        if self.metrics_tracker:
                            self.metrics_tracker.record_thinking_indicator_duration(duration_s)
                    else:
                        logger.info("🛑 Stopped thinking indicator loop")
            except Exception as e:
                logger.warning(f"⚠️ Error stopping thinking indicator: {e}")
            finally:
                self.thinking_indicator_source = None

    async def _handle_streaming_response(self, client: httpx.AsyncClient, payload: dict, t_n8n_start: float) -> None:
        """
        Handle streaming response from n8n webhook
        Supports both SSE (Server-Sent Events) and JSON responses

        Args:
            client: HTTP client
            payload: Request payload
            t_n8n_start: Timestamp when n8n request was sent
        """
        try:
            # Import here to avoid circular dependency
            from src.streaming_handler import StreamingResponseHandler

            logger.info("🌊 Starting streaming response handler")

            # Send request with streaming
            async with client.stream('POST', self.n8n_webhook_url, json=payload) as response:
                response.raise_for_status()

                # Log and record AI generation latency (n8n → first response)
                t_n8n_response = time.time() - t_n8n_start
                logger.info(f"⏱️ LATENCY [AI generation - n8n webhook → first response]: {t_n8n_response:.3f}s")
                if self.metrics_tracker:
                    self.metrics_tracker.record_n8n_response_latency(t_n8n_response)  # Legacy
                    self.metrics_tracker.record_ai_generation_latency(t_n8n_response)  # New granular metric

                # Check Content-Type to determine response format
                content_type = response.headers.get('content-type', '')
                logger.info(f"📋 Response Content-Type: {content_type}")

                # SSE streaming format (text/event-stream)
                if 'text/event-stream' in content_type:
                    logger.info("🌊 Processing SSE streaming response")

                    # Get TTS options with priority logic
                    options = self._get_tts_options(response.headers)

                    # Create streaming handler
                    if self.voice_connection and self.streaming_handler:
                        handler = self.streaming_handler
                    elif self.voice_connection:
                        handler = StreamingResponseHandler(
                            self.voice_connection,
                            self.active_speaker,
                            options,
                            on_ai_response=self.on_ai_response,
                            metrics_tracker=self.metrics_tracker,
                            t_speech_start=self.t_speech_start,
                            t_transcription_complete=self.t_transcription_complete,
                            speaker_manager=self
                        )
                    else:
                        logger.warning("⚠️ No voice connection for streaming response")
                        return

                    # Process SSE streaming chunks
                    async for line in response.aiter_lines():
                        if line.startswith('data: '):
                            chunk_data = line[6:].strip()  # Remove 'data: ' prefix
                            if chunk_data and chunk_data != '[DONE]':
                                await handler.on_chunk(chunk_data)

                    # Finalize any remaining buffered text
                    await handler.finalize()

                # Plain text response (text/plain) - n8n with streaming enabled
                elif 'text/plain' in content_type:
                    logger.info("📝 Processing text/plain response (chunked streaming)")

                    # Get TTS options with priority logic
                    options = self._get_tts_options(response.headers)

                    # Create streaming handler
                    if not self.voice_connection:
                        logger.warning("⚠️ No voice connection for response playback")
                        return

                    handler = StreamingResponseHandler(
                        self.voice_connection,
                        self.active_speaker,
                        options,
                        on_ai_response=self.on_ai_response,
                        metrics_tracker=self.metrics_tracker,
                        t_speech_start=self.t_speech_start,
                        t_transcription_complete=self.t_transcription_complete,
                        speaker_manager=self
                    )

                    # Process text chunks as they arrive (supports true streaming)
                    chunks_received = 0
                    total_text = ""
                    t_first_chunk = None

                    try:
                        async for chunk in response.aiter_text():
                            if chunk.strip():
                                chunks_received += 1
                                total_text += chunk

                                # Log and record latency for first chunk
                                if chunks_received == 1:
                                    t_first_chunk = time.time()
                                    t_to_first_chunk = t_first_chunk - t_n8n_start
                                    logger.info(f"⏱️ LATENCY [n8n call → first chunk]: {t_to_first_chunk:.3f}s")
                                    if self.metrics_tracker:
                                        self.metrics_tracker.record_n8n_first_chunk_latency(t_to_first_chunk)

                                logger.info(f"📨 Chunk {chunks_received} ({len(chunk)} chars): {chunk[:100]}...")
                                # Send chunk immediately to TTS
                                await handler.on_chunk(chunk)

                        logger.info(f"✅ Received {chunks_received} chunk(s), total {len(total_text)} chars")

                        # Finalize any remaining buffered text
                        await handler.finalize()

                    except Exception as e:
                        logger.error(f"❌ Error processing text/plain chunks: {e}")

                # JSON response format (application/json) - FALLBACK
                else:
                    logger.info("📦 Processing JSON response (non-streaming)")

                    # Read full response body
                    body = await response.aread()
                    logger.info(f"📨 Response body (first 200 chars): {body[:200]}")

                    # Parse JSON and record parsing latency
                    t_parse_start = time.time()
                    try:
                        data = json.loads(body)
                        t_parse_end = time.time()
                        parse_latency_ms = (t_parse_end - t_parse_start) * 1000

                        logger.info(f"📋 Parsed JSON: {data}")
                        logger.info(f"⏱️ LATENCY [response parsing]: {parse_latency_ms:.2f}ms")

                        # Record response parsing latency
                        if self.metrics_tracker:
                            self.metrics_tracker.record_response_parsing_latency(parse_latency_ms)

                        # Handle both array and object responses
                        if isinstance(data, list):
                            # n8n "All Incoming Items" sends an array
                            if len(data) > 0:
                                data = data[0]  # Use first item
                                logger.info(f"📋 Extracted first item from array: {data}")
                            else:
                                logger.warning("⚠️ Empty array response")
                                return

                        # Extract response text and options
                        # Handle both formats: {"output": "text"} and {"output": {"content": "text"}}
                        output = data.get('output', {})
                        if isinstance(output, str):
                            # Simple format: {"output": "text"}
                            content = output
                        else:
                            # Nested format: {"output": {"content": "text"}}
                            content = output.get('content', '')
                        body_options = data.get('options', {})

                        # Get TTS options with priority logic (merge body options if present)
                        options = self._get_tts_options(response.headers)
                        # If body has options, they take precedence over frontend settings but not n8n headers
                        if body_options and not response.headers.get('x-tts-options'):
                            options = {**options, **body_options}

                        if content:
                            logger.info(f"💬 Got response text: \"{content}\"")
                            logger.info(f"⚙️ Options: {options}")

                            # Create handler and process as single chunk
                            if self.voice_connection:
                                handler = StreamingResponseHandler(
                                    self.voice_connection,
                                    self.active_speaker,
                                    options,
                                    on_ai_response=self.on_ai_response,
                                    metrics_tracker=self.metrics_tracker,
                                    t_speech_start=self.t_speech_start,
                                    t_transcription_complete=self.t_transcription_complete,
                                    speaker_manager=self
                                )
                                # Send entire response as one chunk
                                await handler.on_chunk(content)
                                await handler.finalize()
                            else:
                                logger.warning("⚠️ No voice connection for response playback")
                        else:
                            logger.warning("⚠️ No content in response")

                    except json.JSONDecodeError as e:
                        logger.error(f"❌ Failed to parse JSON response: {e}")
                        logger.error(f"   Raw body: {body}")

        except Exception as e:
            logger.error(f"❌ Error handling streaming response: {e}")

    async def _unlock(self) -> None:
        """Release speaker lock and clean up"""
        logger.info(f"🔓 Unlocking speaker: {self.active_speaker}")

        # Store speaker info before cleanup
        speaker_to_cleanup = self.active_speaker
        username_to_cleanup = self.active_speaker_username
        duration_ms = 0
        if self.lock_start_time:
            duration_ms = int((time.time() - self.lock_start_time) * 1000)

        # Broadcast speaker stopped event
        if self.on_speaker_stopped and speaker_to_cleanup and username_to_cleanup:
            try:
                await self.on_speaker_stopped(speaker_to_cleanup, username_to_cleanup, duration_ms)
            except Exception as e:
                logger.error(f"❌ Error broadcasting speaker_stopped: {e}")

        # Reset state FIRST to ensure lock is released even if cleanup fails
        self.active_speaker = None
        self.active_speaker_username = None
        self.lock_start_time = None
        self.last_audio_time = None
        self.whisper_client = None
        self.is_finalizing = False  # Reset finalization guard

        # Signal monitor to stop (TaskGroup will handle cleanup automatically)
        logger.info(f"🛑 Setting _stop_monitor Event to wake up timeout monitor")
        self._stop_monitor.set()
        logger.info(f"✅ _stop_monitor.set() completed")

        # Wait briefly for monitor task to finish (non-blocking)
        if self.monitor_task and not self.monitor_task.done():
            try:
                # Give the TaskGroup a moment to clean up gracefully
                await asyncio.wait_for(asyncio.shield(self.monitor_task), timeout=0.1)
                logger.debug("✅ Monitor task stopped gracefully")
            except asyncio.TimeoutError:
                # If it takes too long, cancel it (TaskGroup handles this safely)
                self.monitor_task.cancel()
                logger.debug("⏱️ Monitor task cancelled after timeout")
            except Exception as e:
                logger.debug(f"Monitor task cleanup: {type(e).__name__}")

        # Clear task references
        self.timeout_task = None
        self.silence_task = None
        self.monitor_task = None

        # Cleanup audio receiver for this user
        logger.info(f"🔍 Cleanup check - audio_receiver: {self.audio_receiver is not None}, speaker_to_cleanup: {speaker_to_cleanup}")

        if self.audio_receiver and speaker_to_cleanup:
            try:
                logger.info(f"🧹 Calling cleanup_user for {speaker_to_cleanup}")
                self.audio_receiver.cleanup_user(speaker_to_cleanup)
                logger.info(f"✅ cleanup_user completed for {speaker_to_cleanup}")
            except Exception as e:
                logger.error(f"❌ Error cleaning up audio receiver: {e}", exc_info=True)
        else:
            if not self.audio_receiver:
                logger.warning(f"⚠️ Cannot cleanup: audio_receiver is None")
            if not speaker_to_cleanup:
                logger.warning(f"⚠️ Cannot cleanup: speaker_to_cleanup is None")

    def force_unlock(self) -> None:
        """Force unlock speaker (for shutdown) - sync wrapper"""
        if self.active_speaker:
            logger.warning(f"⚠️ Force unlocking {self.active_speaker}")
            # Get running loop if available
            try:
                loop = asyncio.get_running_loop()
                # Signal monitor to stop
                self._stop_monitor.set()
                # Create and schedule unlock task
                task = loop.create_task(self._unlock())
                # Don't wait for completion during shutdown - it will complete on its own
                logger.debug("🔓 Unlock task scheduled for background completion")
            except RuntimeError:
                # No running loop - just reset state directly
                logger.warning("⚠️ No running loop, resetting state directly")
                self.active_speaker = None
                self.lock_start_time = None
                self.last_audio_time = None
                self.whisper_client = None
                self.timeout_task = None
                self.silence_task = None
                self.monitor_task = None
                self._stop_monitor.set()

    def set_voice_connection(self, voice_connection) -> None:
        """Set Discord voice connection for streaming support"""
        self.voice_connection = voice_connection
        logger.info("🔌 Voice connection set for streaming support")

    def set_streaming_handler(self, handler) -> None:
        """Set streaming response handler"""
        self.streaming_handler = handler
        logger.info("🌊 Streaming handler configured")

    def set_audio_receiver(self, audio_receiver) -> None:
        """Set audio receiver for cleanup callbacks"""
        self.audio_receiver = audio_receiver
        logger.info("🎙️ Audio receiver configured for cleanup")

    def get_status(self) -> dict:
        """Get current speaker manager status"""
        speaking_duration = None
        silence_duration = None

        if self.lock_start_time:
            speaking_duration = int((time.time() - self.lock_start_time) * 1000)

        if self.last_audio_time:
            silence_duration = int((time.time() - self.last_audio_time) * 1000)

        return {
            'locked': self.active_speaker is not None,
            'activeSpeaker': self.active_speaker,
            'speakingDuration': speaking_duration,
            'silenceDuration': silence_duration
        }
