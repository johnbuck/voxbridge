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

    def __init__(self):
        self.active_speaker: Optional[str] = None
        self.lock_start_time: Optional[float] = None
        self.whisper_client: Optional[WhisperClient] = None
        self.timeout_task: Optional[asyncio.Task] = None
        self.silence_task: Optional[asyncio.Task] = None
        self.last_audio_time: Optional[float] = None
        self.voice_connection = None
        self.streaming_handler = None
        self.audio_receiver = None

        # Configuration
        self.silence_threshold_ms = int(os.getenv('SILENCE_THRESHOLD_MS', '800'))
        self.max_speaking_time_ms = int(os.getenv('MAX_SPEAKING_TIME_MS', '45000'))
        self.use_streaming = os.getenv('USE_STREAMING', 'true').lower() != 'false'

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

    async def on_speaking_start(self, user_id: str, audio_stream) -> bool:
        """
        Handle user starting to speak

        Args:
            user_id: Discord user ID
            audio_stream: Audio stream from Discord

        Returns:
            True if this speaker is now active, False if ignored
        """
        # Someone already talking? Ignore this speaker
        if self.active_speaker:
            logger.info(f"🔇 Ignoring {user_id} - {self.active_speaker} is currently speaking")
            return False

        # Lock to this speaker
        self.active_speaker = user_id
        self.lock_start_time = time.time()
        self.last_audio_time = time.time()

        logger.info(f"🎤 {user_id} is now speaking (locked)")

        # Start Whisper transcription stream
        await self._start_transcription(user_id, audio_stream)

        # Start timeout timer (max speaking time)
        self.timeout_task = asyncio.create_task(self._timeout_monitor())

        # Start silence detection immediately (no await needed - just creates task)
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

        self.last_audio_time = time.time()

        # Reset silence timer if it's running (no await needed - just creates task)
        if self.silence_task and not self.silence_task.done():
            self.silence_task.cancel()
            self._start_silence_detection()

    async def _start_transcription(self, user_id: str, audio_stream) -> None:
        """Start WhisperX transcription for this speaker"""
        try:
            logger.info(f"🎙️ Starting transcription for {user_id}")

            # Create new WhisperClient
            self.whisper_client = WhisperClient()
            await self.whisper_client.connect(user_id)

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

        except asyncio.CancelledError:
            logger.info("🛑 Audio streaming cancelled")
        except Exception as e:
            logger.error(f"❌ Error streaming audio: {e}")

    def _start_silence_detection(self) -> None:
        """Start silence detection timer (not async - just creates a task)"""
        if self.silence_task and not self.silence_task.done():
            self.silence_task.cancel()

        self.silence_task = asyncio.create_task(self._silence_monitor())

    async def _silence_monitor(self) -> None:
        """Monitor for silence and finalize transcription"""
        try:
            # Wait for silence threshold
            await asyncio.sleep(self.silence_threshold_ms / 1000.0)

            # Check if still silent
            time_since_audio = (time.time() - self.last_audio_time) * 1000
            if time_since_audio >= self.silence_threshold_ms:
                logger.info(f"🤫 Silence detected ({int(time_since_audio)}ms) - finalizing")
                await self._finalize_transcription('silence')

        except asyncio.CancelledError:
            logger.debug("🛑 Silence monitor cancelled")

    async def _timeout_monitor(self) -> None:
        """Monitor for max speaking time and force finalize"""
        try:
            # Wait for max speaking time
            await asyncio.sleep(self.max_speaking_time_ms / 1000.0)

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
        if not self.whisper_client:
            logger.warning("⚠️ No WhisperClient to finalize")
            await self._unlock()
            return

        try:
            logger.info(f"🏁 Finalizing transcription (reason: {reason})")

            # Request finalization from WhisperX
            transcript = await self.whisper_client.finalize()

            # Close WhisperX connection
            await self.whisper_client.close()

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
                    await self._handle_streaming_response(client, payload)
                else:
                    # Non-streaming mode - simple POST
                    logger.info("📨 Sending non-streaming request")
                    response = await client.post(self.n8n_webhook_url, json=payload)
                    response.raise_for_status()
                    logger.info(f"✅ n8n response: {response.status_code}")

        except Exception as e:
            logger.error(f"❌ Error sending to n8n: {e}")
            raise  # Re-raise to allow retry decorator to work

    async def _handle_streaming_response(self, client: httpx.AsyncClient, payload: dict) -> None:
        """
        Handle streaming response from n8n webhook
        Supports both SSE (Server-Sent Events) and JSON responses

        Args:
            client: HTTP client
            payload: Request payload
        """
        try:
            # Import here to avoid circular dependency
            from src.streaming_handler import StreamingResponseHandler
            import json

            logger.info("🌊 Starting streaming response handler")

            # Send request with streaming
            async with client.stream('POST', self.n8n_webhook_url, json=payload) as response:
                response.raise_for_status()

                # Check Content-Type to determine response format
                content_type = response.headers.get('content-type', '')
                logger.info(f"📋 Response Content-Type: {content_type}")

                # SSE streaming format (text/event-stream)
                if 'text/event-stream' in content_type:
                    logger.info("🌊 Processing SSE streaming response")

                    # Create streaming handler
                    if self.voice_connection and self.streaming_handler:
                        handler = self.streaming_handler
                    elif self.voice_connection:
                        handler = StreamingResponseHandler(
                            self.voice_connection,
                            self.active_speaker
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

                    # Create streaming handler
                    if not self.voice_connection:
                        logger.warning("⚠️ No voice connection for response playback")
                        return

                    handler = StreamingResponseHandler(
                        self.voice_connection,
                        self.active_speaker,
                        {}  # No options in plain text format
                    )

                    # Process text chunks as they arrive (supports true streaming)
                    chunks_received = 0
                    total_text = ""

                    try:
                        async for chunk in response.aiter_text():
                            if chunk.strip():
                                chunks_received += 1
                                total_text += chunk
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

                    try:
                        data = json.loads(body)
                        logger.info(f"📋 Parsed JSON: {data}")

                        # Extract response text and options
                        output = data.get('output', {})
                        content = output.get('content', '')
                        options = data.get('options', {})

                        if content:
                            logger.info(f"💬 Got response text: \"{content}\"")
                            logger.info(f"⚙️ Options: {options}")

                            # Create handler and process as single chunk
                            if self.voice_connection:
                                handler = StreamingResponseHandler(
                                    self.voice_connection,
                                    self.active_speaker,
                                    options
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

        # Store speaker ID before cleanup
        speaker_to_cleanup = self.active_speaker

        # Reset state FIRST to ensure lock is released even if cleanup fails
        self.active_speaker = None
        self.lock_start_time = None
        self.last_audio_time = None
        self.whisper_client = None

        # Cancel pending tasks (best effort - don't block unlock)
        tasks_to_cancel = []

        # Cancel timeout task with RecursionError protection
        if self.timeout_task and not self.timeout_task.done():
            try:
                self.timeout_task.cancel()
                tasks_to_cancel.append(self.timeout_task)
            except (RecursionError, Exception) as e:
                logger.warning(f"⚠️ Error cancelling timeout task: {type(e).__name__}")

        # Cancel silence task with RecursionError protection
        if self.silence_task and not self.silence_task.done():
            try:
                self.silence_task.cancel()
                tasks_to_cancel.append(self.silence_task)
            except (RecursionError, Exception) as e:
                logger.warning(f"⚠️ Error cancelling silence task: {type(e).__name__}")

        # Clear task references
        self.timeout_task = None
        self.silence_task = None

        # Note: We don't wait for cancellation to complete because it can cause RecursionError
        # The tasks will be cancelled asynchronously in the background
        logger.info(f"✅ Cancelled {len(tasks_to_cancel)} task(s) - continuing without waiting")

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
