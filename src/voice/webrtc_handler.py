#!/usr/bin/env python3
"""
============================================================
WebRTC Voice Handler (VoxBridge 2.0 Phase 5.5)
Handles browser audio streaming via WebSocket:
- Receive Opus/WebM audio chunks from browser
- Decode to PCM for WhisperX
- Stream transcriptions back to browser
- Route final transcript to LLM
- Stream AI response chunks to browser

Uses new service layer:
- ConversationService: Session management + context caching
- STTService: WhisperX abstraction
- LLMService: LLM provider routing
- TTSService: Chatterbox abstraction
============================================================
"""

import asyncio
import logging
import os
import time
from io import BytesIO
from typing import Optional, Dict
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
import opuslib

from src.services.conversation_service import ConversationService
from src.services.stt_service import STTService
from src.services.llm_service import LLMService, LLMConfig, ProviderType
from src.services.tts_service import TTSService
from src.types.error_events import ServiceErrorEvent

logger = logging.getLogger(__name__)


class WebRTCVoiceHandler:
    """
    Handles WebRTC voice streaming from browser (VoxBridge 2.0)

    Architecture:
    1. Browser → WebSocket: Binary Opus chunks (100ms each)
    2. Opus → PCM: Decode with opuslib (16kHz mono)
    3. PCM → STTService: Stream for transcription
    4. STTService → Browser: Partial/final transcripts
    5. LLMService → Browser: Stream AI response chunks
    6. TTSService → Browser: Stream audio chunks
    """

    def __init__(self, websocket: WebSocket, user_id: str, session_id: UUID):
        """
        Initialize WebRTC voice handler

        Args:
            websocket: FastAPI WebSocket connection
            user_id: User identifier (browser session ID)
            session_id: Active session ID for this conversation
        """
        self.websocket = websocket
        self.user_id = user_id
        self.session_id = str(session_id)  # Convert UUID to string for service layer
        self.is_active = True

        # Initialize service instances with error callback
        self.conversation_service = ConversationService()
        self.stt_service = STTService(error_callback=self._handle_service_error)
        self.llm_service = LLMService(error_callback=self._handle_service_error)
        self.tts_service = TTSService(error_callback=self._handle_service_error)

        # Audio processing
        self.audio_buffer = BytesIO()
        self.opus_decoder = opuslib.Decoder(16000, 1)  # 16kHz mono

        # VAD settings (reuse from Discord configuration)
        self.silence_threshold_ms = int(os.getenv('SILENCE_THRESHOLD_MS', '600'))
        self.last_audio_time: Optional[float] = None
        self.silence_task: Optional[asyncio.Task] = None

        # Transcription state
        self.current_transcript = ""
        self.is_finalizing = False

        # Timing metrics
        self.t_start = time.time()
        self.t_first_audio = None
        self.t_first_transcript = None

        logger.info(f"🎙️ WebRTC handler initialized for user={user_id}, session={session_id}")
        logger.info(f"   Silence threshold: {self.silence_threshold_ms}ms")

    async def _handle_service_error(self, error_event: ServiceErrorEvent) -> None:
        """
        Handle service error events and broadcast to frontend via WebSocket.

        This callback is invoked by STTService, TTSService, and LLMService when errors occur.
        Errors are logged and forwarded to the WebSocket client for user-friendly display.

        Args:
            error_event: ServiceErrorEvent from backend service
        """
        logger.warning(
            f"⚠️ Service error: {error_event.service_name} - {error_event.error_type} "
            f"(severity={error_event.severity})"
        )

        # Broadcast error to frontend via WebSocket
        try:
            await self.websocket.send_json({
                "type": "service_error",
                "data": error_event.dict()
            })
        except Exception as e:
            logger.error(f"❌ Failed to broadcast error event to WebSocket: {e}")

    async def start(self):
        """
        Start handling audio stream

        Main loop:
        1. Accept WebSocket connection
        2. Start ConversationService background tasks
        3. Connect to STTService
        4. Receive audio chunks
        5. Process transcripts
        6. Handle disconnection
        """
        try:
            # Start conversation service background tasks
            await self.conversation_service.start()
            logger.info(f"✅ ConversationService started")

            # Validate session exists and user owns it
            # Session should already exist - created by API endpoint before WebSocket connection
            cached = await self.conversation_service._ensure_session_cached(self.session_id)
            session = cached.session

            if session.user_id != self.user_id:
                await self._send_error("Session does not belong to user")
                return

            logger.info(f"✅ Session validated: {session.title} (agent: {session.agent_id})")

            # Connect to STTService
            await self._connect_stt()

            # Start audio streaming loop
            await self._audio_loop()

        except WebSocketDisconnect:
            logger.info(f"🔌 WebSocket disconnected for user {self.user_id}")
        except Exception as e:
            logger.error(f"❌ Error in WebRTC handler: {e}", exc_info=True)
            await self._send_error(f"Server error: {str(e)}")
        finally:
            await self._cleanup()

    async def _connect_stt(self):
        """Connect to STTService and set up callbacks"""
        try:
            logger.info(f"🔌 Connecting to STTService for session {self.session_id}")

            # Define transcription callback
            async def on_transcript(text: str, is_final: bool, metadata: Dict):
                """
                Callback for STT transcription results

                Args:
                    text: Transcription text
                    is_final: Whether this is a final transcript
                    metadata: Additional metadata (confidence, duration, etc.)
                """
                if self.t_first_transcript is None:
                    self.t_first_transcript = time.time()
                    latency_s = self.t_first_transcript - self.t_start
                    logger.info(f"⏱️ LATENCY [connection → first transcript]: {latency_s:.3f}s")

                if not is_final:
                    # Partial transcript
                    self.current_transcript = text
                    await self._send_partial_transcript(text)
                else:
                    # Final transcript - wait for finalize() call from silence detection
                    logger.info(f"✅ Final transcript from STTService: \"{text}\"")

            # Connect to STTService
            whisper_url = os.getenv('WHISPER_SERVER_URL', 'ws://whisperx:4901')
            success = await self.stt_service.connect(
                session_id=self.session_id,
                whisper_url=whisper_url
            )

            if not success:
                raise Exception("Failed to connect to STTService")

            # Register callback
            await self.stt_service.register_callback(
                session_id=self.session_id,
                callback=on_transcript
            )

            logger.info(f"✅ Connected to STTService")

        except Exception as e:
            logger.error(f"❌ Failed to connect to STTService: {e}")
            raise

    async def _audio_loop(self):
        """
        Main audio processing loop

        Receives binary audio chunks from browser and processes them:
        1. Receive Opus/WebM binary data
        2. Decode to PCM
        3. Stream to STTService
        4. Monitor for silence
        """
        logger.info(f"🎙️ Starting audio stream loop")

        # Start silence monitoring
        self.silence_task = asyncio.create_task(self._monitor_silence())

        try:
            while self.is_active:
                # Receive binary audio chunk from browser
                audio_data = await self.websocket.receive_bytes()

                if self.t_first_audio is None:
                    self.t_first_audio = time.time()
                    logger.info(f"🎤 Received first audio chunk ({len(audio_data)} bytes)")

                # Update silence detection
                self.last_audio_time = time.time()

                # Decode Opus to PCM
                try:
                    # Browser sends Opus frames (20ms each)
                    # opuslib expects frame_size parameter matching encoding
                    # For 16kHz: 20ms = 320 samples
                    pcm_data = self.opus_decoder.decode(audio_data, frame_size=320)

                    # Stream PCM to STTService
                    success = await self.stt_service.send_audio(
                        session_id=self.session_id,
                        audio_data=pcm_data
                    )

                    if not success:
                        logger.warning(f"⚠️ Failed to send audio to STTService")

                except opuslib.OpusError as e:
                    logger.warning(f"⚠️ Opus decode error: {e}")
                    # Continue processing - may be partial frame

        except WebSocketDisconnect:
            logger.info(f"🔌 Browser disconnected")
        except Exception as e:
            logger.error(f"❌ Error in audio loop: {e}", exc_info=True)
        finally:
            # Cancel silence monitoring
            if self.silence_task:
                self.silence_task.cancel()

    async def _monitor_silence(self):
        """
        Monitor for silence and trigger finalization

        Continuously checks if audio has stopped for silence_threshold_ms.
        When silence detected, finalizes transcription and calls LLM.
        """
        try:
            while self.is_active:
                await asyncio.sleep(0.1)  # Check every 100ms

                if self.last_audio_time:
                    silence_duration_ms = (time.time() - self.last_audio_time) * 1000

                    if silence_duration_ms >= self.silence_threshold_ms:
                        if not self.is_finalizing:
                            logger.info(f"🤫 Silence detected ({int(silence_duration_ms)}ms) - finalizing")
                            await self._finalize_transcription()
                        break

        except asyncio.CancelledError:
            logger.debug("🛑 Silence monitor cancelled")

    async def _finalize_transcription(self):
        """
        Finalize transcription and route to LLM

        Steps:
        1. Get final transcript (stored in self.current_transcript)
        2. Send final_transcript event to browser
        3. Save user message via ConversationService
        4. Get conversation context
        5. Route to LLMService with streaming
        6. Save AI response via ConversationService
        7. Generate TTS via TTSService
        """
        if self.is_finalizing:
            return

        self.is_finalizing = True

        try:
            # Use current transcript from STT callback
            transcript = self.current_transcript.strip()

            if not transcript:
                logger.info("📝 Empty transcript - skipping LLM processing")
                self.is_finalizing = False
                return

            logger.info(f"📝 Final transcript: \"{transcript}\"")

            # Send final transcript to browser
            await self._send_final_transcript(transcript)

            # Save user message to conversation
            await self.conversation_service.add_message(
                session_id=self.session_id,
                role="user",
                content=transcript,
                metadata={
                    'source': 'webrtc',
                    'user_id': self.user_id
                }
            )
            logger.info(f"💾 Saved user message to database")

            # Get agent configuration
            agent = await self.conversation_service.get_agent_config(self.session_id)
            logger.info(f"🤖 Using agent: {agent.name} (provider: {agent.llm_provider}, model: {agent.llm_model})")

            # Route to LLM
            await self._handle_llm_response(transcript, agent)

            # Reset state for next turn
            self.current_transcript = ""
            self.is_finalizing = False

        except Exception as e:
            logger.error(f"❌ Error finalizing transcription: {e}", exc_info=True)
            await self._send_error(f"Error processing transcript: {str(e)}")
            self.is_finalizing = False

    async def _handle_llm_response(self, transcript: str, agent):
        """
        Handle LLM response generation and streaming

        Args:
            transcript: User's transcribed text
            agent: Agent model instance with LLM configuration
        """
        try:
            t_llm_start = time.time()

            # Get conversation context from ConversationService
            messages = await self.conversation_service.get_conversation_context(
                session_id=self.session_id,
                limit=10,
                include_system_prompt=True
            )

            # Convert to dict format for LLMService
            llm_messages = [
                {'role': msg.role, 'content': msg.content}
                for msg in messages
            ]

            # Build LLM config
            llm_config = LLMConfig(
                provider=ProviderType(agent.llm_provider),
                model=agent.llm_model,
                temperature=agent.temperature,
                system_prompt=agent.system_prompt
            )

            logger.info(f"📤 Sending to LLM ({agent.llm_provider}/{agent.llm_model}): \"{transcript}\"")

            # Stream response via LLMService
            full_response = ""
            first_chunk_received = False

            async def on_chunk(chunk: str):
                nonlocal full_response, first_chunk_received

                # Track first chunk latency
                if not first_chunk_received:
                    t_first_chunk = time.time()
                    latency_s = t_first_chunk - t_llm_start
                    logger.info(f"⏱️ LATENCY [LLM first chunk]: {latency_s:.3f}s")
                    first_chunk_received = True

                # Accumulate response
                full_response += chunk

                # Stream chunk to browser
                await self._send_ai_response_chunk(chunk)

            # Generate response
            await self.llm_service.generate_response(
                session_id=self.session_id,
                messages=llm_messages,
                config=llm_config,
                stream=True,
                callback=on_chunk
            )

            # Send completion event
            await self._send_ai_response_complete(full_response)

            # Record latency
            t_llm_complete = time.time()
            latency_s = t_llm_complete - t_llm_start
            logger.info(f"⏱️ LATENCY [total LLM generation]: {latency_s:.3f}s")

            # Save AI message to conversation
            await self.conversation_service.add_message(
                session_id=self.session_id,
                role="assistant",
                content=full_response,
                metadata={
                    'llm_provider': agent.llm_provider,
                    'llm_model': agent.llm_model,
                    'latency_s': latency_s
                }
            )
            logger.info(f"💾 Saved AI message to database")

            # Generate and stream TTS audio to browser
            await self._generate_tts(full_response, agent)

        except Exception as e:
            logger.error(f"❌ Error handling LLM response: {e}", exc_info=True)
            await self._send_error(f"Error generating AI response: {str(e)}")

    # WebSocket message senders
    async def _send_partial_transcript(self, text: str):
        """Send partial transcript event to browser"""
        try:
            await self.websocket.send_json({
                "event": "partial_transcript",
                "data": {
                    "text": text,
                    "session_id": str(self.session_id)
                }
            })
        except Exception as e:
            logger.error(f"❌ Error sending partial transcript: {e}")

    async def _send_final_transcript(self, text: str):
        """Send final transcript event to browser"""
        try:
            await self.websocket.send_json({
                "event": "final_transcript",
                "data": {
                    "text": text,
                    "session_id": str(self.session_id)
                }
            })
        except Exception as e:
            logger.error(f"❌ Error sending final transcript: {e}")

    async def _send_ai_response_chunk(self, text: str):
        """Send AI response chunk event to browser"""
        try:
            await self.websocket.send_json({
                "event": "ai_response_chunk",
                "data": {
                    "text": text,
                    "session_id": str(self.session_id)
                }
            })
        except Exception as e:
            logger.error(f"❌ Error sending AI response chunk: {e}")

    async def _send_ai_response_complete(self, text: str):
        """Send AI response complete event to browser"""
        try:
            await self.websocket.send_json({
                "event": "ai_response_complete",
                "data": {
                    "text": text,
                    "session_id": str(self.session_id)
                }
            })
        except Exception as e:
            logger.error(f"❌ Error sending AI response complete: {e}")

    async def _generate_tts(self, text: str, agent):
        """
        Generate and stream TTS audio to browser via TTSService

        Args:
            text: AI response text to synthesize
            agent: Agent model instance with TTS configuration
        """
        try:
            t_tts_start = time.time()
            logger.info(f"🔊 Starting TTS synthesis for text: \"{text[:50]}...\"")

            # Check TTS health first
            if not await self.tts_service.test_tts_health():
                logger.warning("⚠️ TTS service unavailable, skipping synthesis")
                await self._send_error("TTS service unavailable")
                return

            # Send TTS start event
            await self.websocket.send_json({
                "event": "tts_start",
                "data": {"session_id": self.session_id}
            })

            # Stream audio callback
            first_byte = True
            total_bytes = 0

            async def on_audio_chunk(chunk: bytes):
                nonlocal first_byte, total_bytes

                # Log first byte latency (critical UX metric)
                if first_byte:
                    t_first_byte = time.time()
                    latency_s = t_first_byte - t_tts_start
                    logger.info(f"⏱️ ⭐ LATENCY [TTS first byte]: {latency_s:.3f}s")
                    first_byte = False

                # Stream chunk to browser as binary WebSocket frame
                await self.websocket.send_bytes(chunk)
                total_bytes += len(chunk)

            # Synthesize with streaming via TTSService
            voice_id = agent.tts_voice or os.getenv('CHATTERBOX_VOICE_ID', 'default')
            speed = agent.tts_rate or 1.0

            audio_bytes = await self.tts_service.synthesize_speech(
                session_id=self.session_id,
                text=text,
                voice_id=voice_id,
                speed=speed,
                stream=True,
                callback=on_audio_chunk
            )

            # Send completion event
            t_complete = time.time()
            total_latency_s = t_complete - t_tts_start
            logger.info(f"✅ TTS complete ({len(audio_bytes):,} bytes, {total_latency_s:.2f}s)")

            await self.websocket.send_json({
                "event": "tts_complete",
                "data": {
                    "session_id": self.session_id,
                    "duration_s": total_latency_s
                }
            })

        except Exception as e:
            logger.error(f"❌ TTS error: {e}", exc_info=True)
            await self._send_error(f"TTS failed: {str(e)}")

    async def _send_error(self, message: str):
        """Send error event to browser"""
        try:
            await self.websocket.send_json({
                "event": "error",
                "data": {
                    "message": message,
                    "session_id": str(self.session_id)
                }
            })
        except Exception as e:
            logger.error(f"❌ Error sending error message: {e}")

    async def _cleanup(self):
        """Clean up resources and disconnect services"""
        logger.info(f"🧹 Cleaning up WebRTC handler for session {self.session_id}")

        self.is_active = False

        # Cancel silence monitoring
        if self.silence_task and not self.silence_task.done():
            self.silence_task.cancel()

        # Disconnect from STTService
        try:
            await self.stt_service.disconnect(self.session_id)
            logger.info(f"✅ Disconnected from STTService")
        except Exception as e:
            logger.error(f"❌ Error disconnecting STTService: {e}")

        # Cancel any active TTS
        try:
            await self.tts_service.cancel_tts(self.session_id)
            logger.info(f"✅ Cancelled active TTS")
        except Exception as e:
            logger.error(f"❌ Error cancelling TTS: {e}")

        # Stop ConversationService background tasks
        try:
            await self.conversation_service.stop()
            logger.info(f"✅ Stopped ConversationService")
        except Exception as e:
            logger.error(f"❌ Error stopping ConversationService: {e}")

        # Close WebSocket
        try:
            await self.websocket.close()
        except Exception as e:
            logger.debug(f"WebSocket already closed: {e}")

        logger.info(f"✅ WebRTC handler cleanup complete")
