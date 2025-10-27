#!/usr/bin/env python3
"""
============================================================
WebRTC Voice Handler
Handles browser audio streaming via WebSocket:
- Receive Opus/WebM audio chunks from browser
- Decode to PCM for WhisperX
- Stream transcriptions back to browser
- Route final transcript to LLM
- Stream AI response chunks to browser
============================================================
"""

import asyncio
import logging
import os
import time
from io import BytesIO
from typing import Optional
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
import opuslib

from src.whisper_client import WhisperClient
from src.services.session_service import SessionService
from src.services.agent_service import AgentService
from src.llm.factory import LLMProviderFactory
from src.llm.types import LLMMessage, LLMRequest, LLMError

logger = logging.getLogger(__name__)


class WebRTCVoiceHandler:
    """
    Handles WebRTC voice streaming from browser

    Architecture:
    1. Browser → WebSocket: Binary Opus chunks (100ms each)
    2. Opus → PCM: Decode with opuslib (16kHz mono)
    3. PCM → WhisperX: Stream for transcription
    4. WhisperX → Browser: Partial/final transcripts
    5. LLM → Browser: Stream AI response chunks
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
        self.session_id = session_id
        self.is_active = True

        # WhisperX client for transcription
        self.whisper_client: Optional[WhisperClient] = None

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

    async def start(self):
        """
        Start handling audio stream

        Main loop:
        1. Accept WebSocket connection
        2. Connect to WhisperX
        3. Receive audio chunks
        4. Process transcripts
        5. Handle disconnection
        """
        try:
            # Validate session exists and user owns it
            session = await SessionService.get_session(self.session_id)
            if not session:
                await self._send_error("Session not found")
                return

            if session.user_id != self.user_id:
                await self._send_error("Session does not belong to user")
                return

            logger.info(f"✅ Session validated: {session.title} (agent: {session.agent_id})")

            # Connect to WhisperX
            await self._connect_whisperx()

            # Start audio streaming loop
            await self._audio_loop()

        except WebSocketDisconnect:
            logger.info(f"🔌 WebSocket disconnected for user {self.user_id}")
        except Exception as e:
            logger.error(f"❌ Error in WebRTC handler: {e}", exc_info=True)
            await self._send_error(f"Server error: {str(e)}")
        finally:
            await self._cleanup()

    async def _connect_whisperx(self):
        """Connect to WhisperX server and set up callbacks"""
        try:
            logger.info(f"🔌 Connecting to WhisperX for user {self.user_id}")

            self.whisper_client = WhisperClient()

            # Set partial transcript callback
            async def on_partial(text: str):
                if self.t_first_transcript is None:
                    self.t_first_transcript = time.time()
                    latency_s = self.t_first_transcript - self.t_start
                    logger.info(f"⏱️ LATENCY [connection → first transcript]: {latency_s:.3f}s")

                self.current_transcript = text
                await self._send_partial_transcript(text)

            # Set final transcript callback
            async def on_final(text: str):
                logger.info(f"✅ Final transcript from WhisperX: \"{text}\"")
                # Don't process here - wait for finalize() call

            self.whisper_client.on_partial_callback = on_partial
            self.whisper_client.on_final_callback = on_final

            # Connect
            await self.whisper_client.connect(self.user_id)
            logger.info(f"✅ Connected to WhisperX")

        except Exception as e:
            logger.error(f"❌ Failed to connect to WhisperX: {e}")
            raise

    async def _audio_loop(self):
        """
        Main audio processing loop

        Receives binary audio chunks from browser and processes them:
        1. Receive Opus/WebM binary data
        2. Decode to PCM
        3. Stream to WhisperX
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

                    # Stream PCM to WhisperX
                    if self.whisper_client and self.whisper_client.is_connected:
                        await self.whisper_client.send_audio(pcm_data)

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
        1. Request final transcript from WhisperX
        2. Send final_transcript event to browser
        3. Save user message to database
        4. Route to LLM (based on agent config)
        5. Stream AI response back to browser
        6. Save AI message to database
        """
        if self.is_finalizing:
            return

        self.is_finalizing = True

        try:
            # Get final transcript from WhisperX
            if not self.whisper_client:
                logger.warning("⚠️ No WhisperX client for finalization")
                return

            transcript = await self.whisper_client.finalize()

            if not transcript or not transcript.strip():
                logger.info("📝 Empty transcript - skipping LLM processing")
                return

            logger.info(f"📝 Final transcript: \"{transcript}\"")

            # Send final transcript to browser
            await self._send_final_transcript(transcript)

            # Load session to get agent
            session = await SessionService.get_session(self.session_id)
            if not session:
                logger.error("❌ Session not found during finalization")
                return

            # Save user message to database
            await SessionService.add_message(
                session_id=self.session_id,
                role="user",
                content=transcript
            )
            logger.info(f"💾 Saved user message to database")

            # Load agent configuration
            agent = await AgentService.get_agent(session.agent_id)
            if not agent:
                logger.error(f"❌ Agent not found: {session.agent_id}")
                return

            logger.info(f"🤖 Using agent: {agent.name} (provider: {agent.llm_provider}, model: {agent.llm_model})")

            # Route to LLM
            await self._handle_llm_response(transcript, agent)

        except Exception as e:
            logger.error(f"❌ Error finalizing transcription: {e}", exc_info=True)
            await self._send_error(f"Error processing transcript: {str(e)}")

    async def _handle_llm_response(self, transcript: str, agent):
        """
        Handle LLM response generation and streaming

        Args:
            transcript: User's transcribed text
            agent: Agent model instance with LLM configuration
        """
        try:
            t_llm_start = time.time()

            # Create LLM provider from agent configuration
            provider, model = LLMProviderFactory.create_from_agent_config(
                llm_provider=agent.llm_provider,
                llm_model=agent.llm_model
            )

            # Build conversation messages
            # TODO: Load conversation history from database
            messages = [
                LLMMessage(role="system", content=agent.system_prompt),
                LLMMessage(role="user", content=transcript)
            ]

            # Build LLM request
            request = LLMRequest(
                messages=messages,
                temperature=agent.temperature,
                model=model,
                max_tokens=None
            )

            logger.info(f"📤 Sending to LLM ({agent.llm_provider}/{model}): \"{transcript}\"")

            # Stream response
            full_response = ""
            first_chunk_received = False

            async for chunk in provider.generate_stream(request):
                # Track first chunk latency
                if not first_chunk_received:
                    t_first_chunk = time.time()
                    latency_s = t_first_chunk - t_llm_start
                    logger.info(f"⏱️ LATENCY [LLM first chunk]: {latency_s:.3f}s")
                    first_chunk_received = True

                # Accumulate response (chunks are plain strings)
                full_response += chunk

                # Stream chunk to browser
                await self._send_ai_response_chunk(chunk)

            # Send completion event
            await self._send_ai_response_complete(full_response)

            # Record latency
            t_llm_complete = time.time()
            latency_s = t_llm_complete - t_llm_start
            logger.info(f"⏱️ LATENCY [total LLM generation]: {latency_s:.3f}s")

            # Save AI message to database
            await SessionService.add_message(
                session_id=self.session_id,
                role="assistant",
                content=full_response
            )
            logger.info(f"💾 Saved AI message to database")

            # Close provider
            await provider.close()

        except LLMError as e:
            logger.error(f"❌ LLM Error: {e}", exc_info=True)
            await self._send_error(f"AI error: {str(e)}")
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
        """Clean up resources"""
        logger.info(f"🧹 Cleaning up WebRTC handler for user {self.user_id}")

        self.is_active = False

        # Cancel silence monitoring
        if self.silence_task and not self.silence_task.done():
            self.silence_task.cancel()

        # Close WhisperX connection
        if self.whisper_client:
            try:
                await self.whisper_client.close()
            except Exception as e:
                logger.error(f"❌ Error closing WhisperX: {e}")

        # Close WebSocket
        try:
            await self.websocket.close()
        except Exception as e:
            logger.debug(f"WebSocket already closed: {e}")

        logger.info(f"✅ WebRTC handler cleanup complete")
