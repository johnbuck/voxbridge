#!/usr/bin/env python3
"""
============================================================
WebRTC Voice Handler (VoxBridge 2.0 Phase 5.5 + Audio Fix)
Handles browser audio streaming via WebSocket:
- Receive WebM/OGG audio chunks from browser
- Fully decode container to PCM audio with PyAV
- Send PCM audio to WhisperX (format='pcm' path)
- Stream transcriptions back to browser
- Route final transcript to LLM
- Stream AI response chunks to browser

Uses new service layer:
- ConversationService: Session management + context caching
- STTService: WhisperX abstraction with format routing
- LLMService: LLM provider routing
- TTSService: Chatterbox abstraction

Audio Strategy: WebM decode → PCM audio → WhisperX (PCM path)
Note: Discord uses Opus path, WebRTC uses PCM path (dual-format)
============================================================
"""

import asyncio
import os
import time
import numpy as np
from io import BytesIO
from typing import Optional, Dict
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
import av

from src.config.logging_config import get_logger
from src.services.conversation_service import ConversationService
from src.services.stt_service import STTService
from src.services.llm_service import LLMService, LLMConfig, ProviderType
from src.services.tts_service import TTSService
from src.types.error_events import ServiceErrorEvent
from src.api.server import get_metrics_tracker, ws_manager

logger = get_logger(__name__)


class WebRTCVoiceHandler:
    """
    Handles WebRTC voice streaming from browser (VoxBridge 2.0 + Audio Fix)

    Architecture:
    1. Browser → WebSocket: WebM/OGG Opus chunks (100ms each)
    2. Buffer → Accumulate chunks until container is parseable
    3. PyAV Decode → Fully decode to PCM audio (48kHz stereo int16)
    4. PCM Audio → STTService: Send to WhisperX (format='pcm' path)
    5. STTService → Browser: Partial/final transcripts
    6. LLMService → Browser: Stream AI response chunks
    7. TTSService → Browser: Stream audio chunks

    Note: Uses PCM path (not Opus) to avoid frame size mismatch with WhisperX
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

        # Get global metrics tracker (shared with Discord plugin)
        self.metrics = get_metrics_tracker()

        # Audio processing (WebM demuxing to extract raw Opus packets)
        self.webm_buffer = bytearray()  # Accumulate WebM chunks until parseable
        self.chunks_received = 0
        self.webm_header: Optional[bytes] = None  # Saved WebM header for continuation chunks
        self.header_frame_count: int = 0  # Number of frames in header
        self.header_validated: bool = False  # Flag: WebM header captured and validated
        self.turn_number: int = 0  # Track conversation turns for logging

        # VAD settings (reuse from Discord configuration)
        self.silence_threshold_ms = int(os.getenv('SILENCE_THRESHOLD_MS', '600'))
        self.max_utterance_time_ms = int(os.getenv('MAX_UTTERANCE_TIME_MS', '45000'))  # 45s default
        self.last_audio_time: Optional[float] = None
        self.utterance_start_time: Optional[float] = None  # Track utterance start for max timeout
        self.silence_task: Optional[asyncio.Task] = None

        # Option B: VAD enhancement settings (minimum speech duration filtering)
        self.min_speech_duration_ms = int(os.getenv('MIN_SPEECH_DURATION_MS', '500'))
        self.speech_energy_threshold = int(os.getenv('SPEECH_ENERGY_THRESHOLD', '300'))
        self.audio_energy_buffer: list[int] = []  # Track recent energy levels

        # LLM task tracking (Phase 3: Prevent orphaned tasks)
        self.llm_task: Optional[asyncio.Task] = None

        # WebM continuous stream decoding (maintains Opus codec state)
        self.frames_sent_to_whisperx: int = 0  # Track frames already sent (to skip on next decode)

        # Bot speaking discard tracking (Batch 2.1)
        self.discarded_chunks_count: int = 0  # Track chunks discarded while bot speaks

        # Transcription state
        self.current_transcript = ""
        self.is_finalizing = False

        # Final transcript tracking (fix for transcript duplication issue)
        self.final_transcript_ready = False  # Flag: WhisperX sent final transcript
        self.final_transcript = ""  # Stores final transcript from WhisperX

        # Bot speaking state (blocks input during TTS playback)
        self.is_bot_speaking = False

        # Timing metrics (expanded for full metrics parity with Discord)
        self.t_start = time.time()
        self.t_first_audio = None
        self.t_first_transcript = None

        # Phase 1: Speech → Transcription
        self.t_whisper_connected = None     # WhisperX connection time
        self.t_first_partial = None         # First partial transcript received
        self.t_transcription_complete = None # Final transcript ready

        # Phase 2: AI Processing
        self.t_ai_start = None              # LLM generation start
        self.t_ai_complete = None           # LLM generation complete (same as t_llm_complete)
        self.t_llm_complete = None          # Track LLM completion for TTS queue metric (legacy, remove after migration)

        # Phase 3+: TTS & Pipeline
        self.t_audio_complete = None        # TTS audio streaming complete

        logger.info(f"🎙️ WebRTC handler initialized for user={user_id}, session={session_id}")
        logger.info(f"   Silence threshold: {self.silence_threshold_ms}ms")
        logger.info(f"   Max utterance time: {self.max_utterance_time_ms}ms")

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

        # Broadcast error to frontend via WebSocket (only if still connected)
        if not self.is_active:
            logger.debug(f"⏭️ Skipping service error broadcast (connection closed)")
            return

        try:
            await self.websocket.send_json({
                "type": "service_error",
                "data": error_event.dict()
            })
        except Exception as e:
            logger.debug(f"⏭️ Could not broadcast service error (connection likely closed): {e}")

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
            logger.info(f"[START] Step 1: Starting conversation service...")
            # Start conversation service background tasks
            await self.conversation_service.start()
            logger.info(f"[START] ✅ Step 1 complete: ConversationService started")

            logger.info(f"[START] Step 2: Validating session...")
            # Validate session exists and user owns it
            # Session should already exist - created by API endpoint before WebSocket connection
            cached = await self.conversation_service._ensure_session_cached(self.session_id)
            session = cached.session

            if session.user_id != self.user_id:
                logger.error(f"[START] ❌ Step 2 failed: Session {self.session_id} does not belong to user {self.user_id}")
                await self._send_error("Session does not belong to user")
                return

            logger.info(f"[START] ✅ Step 2 complete: Session validated: {session.title} (agent: {session.agent_id})")

            logger.info(f"[START] Step 3: Connecting to STTService...")
            # Connect to STTService
            await self._connect_stt()
            logger.info(f"[START] ✅ Step 3 complete: STTService connected")

            logger.info(f"[START] Step 4: Starting audio streaming loop...")
            # Start audio streaming loop
            await self._audio_loop()
            logger.info(f"[START] ✅ Step 4 complete: Audio loop finished")

        except WebSocketDisconnect:
            logger.info(f"[START] 🔌 WebSocket disconnected for user {self.user_id}")
        except Exception as e:
            logger.error(f"[START] ❌ Error in WebRTC handler at unknown step: {e}", exc_info=True)
            # ⏱️ METRIC 11: Error Count
            self.metrics.record_error()
            await self._send_error(f"Server error: {str(e)}")
        finally:
            logger.info(f"[START] Step 5: Cleanup...")
            await self._cleanup()
            logger.info(f"[START] ✅ Step 5 complete: Cleanup finished")

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
                # DIAGNOSTIC: Log transcript type and content
                transcript_type = "FINAL" if is_final else "PARTIAL"
                logger.info(f"📝 [TRANSCRIPT] Received {transcript_type}: length={len(text)} chars, text=\"{text[:100]}{'...' if len(text) > 100 else ''}\"")

                if self.t_first_transcript is None:
                    self.t_first_transcript = time.time()
                    latency_s = self.t_first_transcript - self.t_start
                    logger.info(f"⏱️ LATENCY [connection → first transcript]: {latency_s:.3f}s")

                if not is_final:
                    # WhisperX sends FULL transcript so far in each partial (not delta)
                    # Just use latest partial directly - no accumulation needed
                    logger.info(f"📝 [TRANSCRIPT] Received PARTIAL: \"{text}\"")
                    self.current_transcript = text

                    # ⏱️ METRIC 2: First Partial Transcript Latency
                    # Measures: User starts speaking (first audio) → First partial transcript received
                    # This reflects actual STT processing speed (not connection time)
                    if self.t_first_partial is None and self.utterance_start_time:
                        self.t_first_partial = time.time()
                        latency_s = self.t_first_partial - self.utterance_start_time
                        self.metrics.record_first_partial_transcript_latency(latency_s)
                        logger.info(f"⏱️ LATENCY [WebRTC - First Partial]: {latency_s * 1000:.2f}ms (utterance start → first partial)")

                    await self._send_partial_transcript(text)
                else:
                    # ✅ FIX: Store WhisperX final transcript and set flag
                    # This is the REAL final transcript from WhisperX's full session_buffer
                    logger.info(f"✅ [TRANSCRIPT] Received FINAL from WhisperX: \"{text}\" (length={len(text)} chars)")
                    self.final_transcript = text
                    self.final_transcript_ready = True

                    # ⏱️ METRIC 3: Transcription Duration
                    self.t_transcription_complete = time.time()
                    if self.t_first_partial:
                        duration_s = self.t_transcription_complete - self.t_first_partial
                        self.metrics.record_transcription_duration(duration_s)
                        logger.info(f"⏱️ LATENCY [WebRTC - Transcription Duration]: {duration_s * 1000:.2f}ms")

                    # Note: _finalize_transcription() waits for this flag before proceeding

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

            # ⏱️ METRIC 1: WhisperX Connection Latency
            self.t_whisper_connected = time.time()
            latency_s = self.t_whisper_connected - self.t_start
            self.metrics.record_whisper_connection_latency(latency_s)
            logger.info(f"⏱️ LATENCY [WebRTC - WhisperX Connection]: {latency_s * 1000:.2f}ms")
            logger.info(f"✅ Connected to STTService")

        except Exception as e:
            logger.error(f"❌ Failed to connect to STTService: {e}")
            raise

    async def _audio_loop(self):
        """
        Main audio processing loop with WebM decoding

        Receives binary audio chunks from browser and processes them:
        1. Receive WebM/OGG binary chunks from MediaRecorder (100ms each)
        2. Buffer chunks until container is parseable by PyAV
        3. Fully decode container to PCM audio (48kHz stereo int16)
        4. Send PCM audio to WhisperX (format='pcm' path, no Opus decode)
        5. Monitor for silence

        Strategy: Buffered decoding - accumulate WebM chunks, decode periodically,
                  extract PCM audio, send to WhisperX (bypasses Opus frame issues)
        """
        logger.info(f"[AUDIO_LOOP] 🎙️ Starting audio stream loop (WebM/OGG → PCM decoding)")
        logger.info(f"[AUDIO_LOOP] Silence threshold: {self.silence_threshold_ms}ms, Max utterance: {self.max_utterance_time_ms}ms")

        # Start silence monitoring
        logger.info(f"[AUDIO_LOOP] Creating silence monitor task...")
        self.silence_task = asyncio.create_task(self._monitor_silence())
        logger.info(f"[AUDIO_LOOP] ✅ Silence monitor task created: {self.silence_task}")

        # ✅ CHECKPOINT: Audio loop entry
        logger.info(f"🎙️ [AUDIO_LOOP] Entering main loop (session={self.session_id}, is_active={self.is_active})")

        try:
            while self.is_active:
                # Receive WebM/OGG chunk from browser MediaRecorder
                webm_chunk = await self.websocket.receive_bytes()
                self.chunks_received += 1

                # ✅ CHECKPOINT 2: WebSocket Receipt
                logger.info(f"🔌 [WS_RECV] Received {len(webm_chunk)} bytes (chunk #{self.chunks_received}), session={self.session_id}")

                # Block audio input while bot is speaking (prevent crosstalk)
                if self.is_bot_speaking:
                    self.discarded_chunks_count += 1
                    logger.debug(f"🤖 [AUDIO_LOOP] Bot is speaking - discarding user audio chunk #{self.chunks_received} (total discarded: {self.discarded_chunks_count})")

                    # ⚠️ CHECKPOINT: Warn if bot speaking for extended period (Batch 2.1)
                    if self.discarded_chunks_count == 50:
                        logger.warn(f"⚠️ [STATE] Bot speaking for extended period - {self.discarded_chunks_count} chunks discarded (~5 seconds)")
                    elif self.discarded_chunks_count % 100 == 0:  # Warn every 10 seconds after first warning
                        logger.warn(f"⚠️ [STATE] Bot still speaking - {self.discarded_chunks_count} chunks discarded (~{self.discarded_chunks_count // 10} seconds)")

                    continue  # Skip this chunk, wait for next one

                if self.t_first_audio is None:
                    self.t_first_audio = time.time()
                    self.utterance_start_time = time.time()  # Track start for max utterance timeout
                    logger.info(f"🎤 Received first audio chunk ({len(webm_chunk)} bytes)")
                    # Log WebM structure on first chunk
                    has_ebml = webm_chunk[:4] == b'\x1a\x45\xdf\xa3'
                    has_segment = b'\x18\x53\x80\x67' in webm_chunk[:100]
                    has_cluster = b'\x1f\x43\xb6\x75' in webm_chunk
                    logger.info(f"📦 WebM structure: EBML={has_ebml}, Segment={has_segment}, Cluster={has_cluster}")
                else:
                    # Enhanced chunk logging: Detect header presence for Turn 2+ diagnosis
                    has_ebml = webm_chunk[:4] == b'\x1a\x45\xdf\xa3'
                    logger.info(f"🎤 Received audio chunk #{self.chunks_received} ({len(webm_chunk)} bytes, "
                               f"Turn {self.turn_number}, has_EBML={has_ebml})")

                # Accumulate all chunks to maintain Opus codec state across the entire stream
                # Opus is stateful - each frame depends on previous frames' decoder state
                chunk_start_time = time.time()
                self.webm_buffer.extend(webm_chunk)
                processing_ms = (time.time() - chunk_start_time) * 1000

                # Enhanced audio chunk metrics logging
                logger.info(f"📊 [AUDIO_METRICS] Chunk #{self.chunks_received}, WebM size: {len(webm_chunk)} bytes, "
                           f"Buffer total: {len(self.webm_buffer)} bytes, "
                           f"Frames sent: {self.frames_sent_to_whisperx}, "
                           f"Processing time: {processing_ms:.2f}ms, "
                           f"header_validated={self.header_validated}")

                # Buffer management: Prevent memory leak from unbounded growth
                # Max ~60 seconds of continuous audio before finalizing
                MAX_BUFFER_SIZE = 500000  # 500KB (~60s at 48kHz stereo)
                if len(self.webm_buffer) > MAX_BUFFER_SIZE:
                    # Batch 3.2: Enhanced buffer limit warning with diagnostics
                    estimated_duration_s = len(self.webm_buffer) / 8000  # Rough estimate: 8KB/sec for 48kHz stereo Opus
                    logger.warn(f"⚠️ [BUFFER_LIMIT] Forced finalization - buffer size {len(self.webm_buffer)} bytes ({estimated_duration_s:.1f}s estimated), chunks_received={self.chunks_received}, frames_sent={self.frames_sent_to_whisperx}")

                    # Finalize current utterance (this will trigger transcription)
                    await self.stt_service.finalize_transcript(self.session_id)

                    # Clear buffer and reset to start fresh
                    # Batch 3.2: Enhanced buffer clear logging
                    cleared_size = len(self.webm_buffer)
                    cleared_frames = self.frames_sent_to_whisperx
                    self.webm_buffer = bytearray()
                    self.frames_sent_to_whisperx = 0
                    logger.info(f"✅ [BUFFER_CLEAR] Buffer cleared (was {cleared_size} bytes, {cleared_frames} frames) - frame counter reset to 0")

                    # Skip processing this chunk since we just finalized
                    continue

                # Decode entire accumulated buffer to maintain codec state
                # Skip frames we've already sent to avoid duplicates
                pcm_data = self._extract_new_pcm_audio()

                # Update silence detection timer ONLY if audio is NOT silent
                # Check audio amplitude to determine if user is speaking
                if pcm_data:
                    import struct
                    # Parse PCM samples to detect silence
                    if len(pcm_data) >= 200:
                        samples = struct.unpack(f'<{min(100, len(pcm_data)//2)}h', pcm_data[:200])
                        max_amp = max(abs(s) for s in samples)
                        is_silent = max_amp < 100

                        # Only update timer if NOT silent - this allows silence detection to work
                        if not is_silent:
                            self.last_audio_time = time.time()
                            # Batch 2.2: Enhanced amplitude logging
                            logger.debug(f"🔊 [AMPLITUDE] Non-silent audio (max_amp={max_amp}/32767, {max_amp/32767*100:.1f}%), updating last_audio_time")
                        else:
                            # Batch 2.2: Log silent audio to help diagnose silence detection
                            logger.debug(f"🤫 [AMPLITUDE] Silent audio (max_amp={max_amp}/32767, {max_amp/32767*100:.1f}%), NOT updating timer - silence detection active")
                    else:
                        # Short PCM data - treat as non-silent to avoid false positives
                        self.last_audio_time = time.time()

                # Send new PCM data to WhisperX (if extraction successful)
                if pcm_data:
                    # Option B: Check if audio has sufficient speech energy (filter echoes/noise)
                    if not self._has_sufficient_speech_energy(pcm_data):
                        # Not enough energy - likely silence, echo, or brief noise
                        logger.debug(f"⏭️ [ENERGY_FILTER] Skipping low-energy audio chunk")
                        continue

                    # ✅ CHECKPOINT 4: WhisperX Send
                    logger.info(f"🎤 [WHISPER_SEND] Sending {len(pcm_data)} bytes PCM to WhisperX, session={self.session_id}")

                    success = await self.stt_service.send_audio(
                        session_id=self.session_id,
                        audio_data=pcm_data,
                        audio_format='pcm'  # WebRTC uses PCM format
                    )

                    if not success:
                        logger.warning(f"⚠️ [WHISPER_SEND] Failed to send PCM audio to STTService")
                    else:
                        logger.debug(f"✅ [WHISPER_SEND] Successfully sent to STTService")

        except WebSocketDisconnect:
            logger.info(f"🔌 Browser disconnected")
            logger.warn(f"⚠️ [AUDIO_LOOP] WebSocket disconnected at chunk #{self.chunks_received}, is_active={self.is_active}, session={self.session_id}")
        except Exception as e:
            logger.error(f"❌ Error in audio loop: {e}", exc_info=True)
            logger.error(f"🚨 [AUDIO_LOOP] FATAL ERROR after {self.chunks_received} chunks, is_active={self.is_active}, session={self.session_id}")
            # ⏱️ METRIC 11: Error Count
            self.metrics.record_error()
        finally:
            # ✅ CHECKPOINT: Audio loop exit
            logger.warn(f"🛑 [AUDIO_LOOP] Exited main loop (is_active={self.is_active}, chunks_received={self.chunks_received}, session={self.session_id})")

            # Cancel silence monitoring
            if self.silence_task:
                self.silence_task.cancel()

    def _extract_new_pcm_audio(self) -> bytes:
        """
        Decode entire accumulated WebM buffer and extract only NEW frames

        This maintains Opus codec state across the entire stream by decoding
        from the beginning each time. We skip frames already sent to avoid
        duplicates.

        Returns:
            PCM audio bytes for new frames only, or empty bytes if decode fails
        """
        if not self.webm_buffer:
            return b''

        # Enhanced buffer state logging
        logger.debug(f"🎬 [BUFFER_STATE] webm_buffer: {len(self.webm_buffer)} bytes, "
                    f"frames_sent: {self.frames_sent_to_whisperx}, "
                    f"utterance_active: {self.utterance_start_time is not None}")

        # ✅ CRITICAL FIX: WebM Header Preservation for Multi-Turn Conversations
        # Detect if buffer has WebM EBML header (required for PyAV to parse)
        has_ebml = self.webm_buffer[:4] == b'\x1a\x45\xdf\xa3'

        # Turn 2+: If buffer lacks header but we have saved one, prepend it
        if not has_ebml and self.webm_header and self.header_validated:
            logger.info(f"🔧 [HEADER_FIX] Turn {self.turn_number} buffer lacks EBML header - "
                       f"prepending saved header ({len(self.webm_header)} bytes)")
            decode_buffer = bytearray(self.webm_header)
            decode_buffer.extend(self.webm_buffer)
            logger.info(f"📦 [HEADER_FIX] Decode buffer: {len(decode_buffer)} bytes "
                       f"(header: {len(self.webm_header)}, clusters: {len(self.webm_buffer)})")
        else:
            decode_buffer = self.webm_buffer
            if has_ebml:
                logger.debug(f"✅ [HEADER] Buffer has EBML header - decoding normally")
            elif not self.header_validated:
                logger.debug(f"⏳ [HEADER] Waiting for first complete WebM container to capture header")

        # ✅ CHECKPOINT 3: PyAV Decode Attempt
        logger.debug(f"🎵 [DECODE] Attempting PyAV decode, buffer={len(decode_buffer)} bytes, "
                    f"has_header={has_ebml or (self.header_validated and self.webm_header is not None)}")

        try:
            # Decode buffer (with prepended header if needed)
            buffer = BytesIO(bytes(decode_buffer))
            container = av.open(buffer, 'r')
            audio_stream = container.streams.audio[0]

            # Decode all frames from the beginning
            all_pcm_chunks = []
            for frame_idx, frame in enumerate(container.decode(audio_stream)):
                # FIX: Convert planar audio to interleaved format for WhisperX
                pcm_array = frame.to_ndarray()

                # Log format detection on first frame
                if frame_idx == 0:
                    is_planar = frame.format.is_planar
                    logger.info(f"🎵 Audio format: {frame.format.name}, planar={is_planar}, shape={pcm_array.shape}, dtype={pcm_array.dtype}")

                # Convert float32 to int16 if needed (WhisperX expects int16)
                if pcm_array.dtype == np.float32:
                    pcm_array = (pcm_array * 32767).astype(np.int16)

                # Transpose if planar: (channels, samples) → (samples, channels)
                if frame.format.is_planar:
                    pcm_array = pcm_array.T

                pcm_bytes = pcm_array.tobytes()
                all_pcm_chunks.append(pcm_bytes)

            container.close()

            # ✅ CRITICAL FIX: Save WebM header on first successful decode (Turn 1)
            # This header will be prepended to Turn 2+ buffers that lack it
            if not self.header_validated and has_ebml:
                # Find first Cluster block (marks end of header)
                cluster_offset = bytes(self.webm_buffer).find(b'\x1f\x43\xb6\x75')
                if cluster_offset > 0:
                    self.webm_header = bytes(self.webm_buffer[:cluster_offset])
                    self.header_validated = True
                    logger.info(f"✅ [HEADER_CAPTURE] Saved WebM header for Turn 2+ reuse: "
                               f"{len(self.webm_header)} bytes (EBML + Segment)")
                    logger.debug(f"📦 [HEADER_CAPTURE] Cluster starts at byte {cluster_offset}")
                else:
                    logger.warning(f"⚠️ [HEADER_CAPTURE] Could not find Cluster block in buffer "
                                 f"({len(self.webm_buffer)} bytes) - will retry next decode")

            # Skip frames we've already sent, extract only NEW frames
            new_pcm_chunks = all_pcm_chunks[self.frames_sent_to_whisperx:]

            if new_pcm_chunks:
                # Update counter for next iteration
                self.frames_sent_to_whisperx = len(all_pcm_chunks)

                pcm_data = b''.join(new_pcm_chunks)

                # PCM content validation logging
                import struct
                if len(pcm_data) >= 200:
                    # Parse first 100 samples as int16
                    samples = struct.unpack(f'<{min(100, len(pcm_data)//2)}h', pcm_data[:200])
                    max_amp = max(abs(s) for s in samples)
                    avg_amp = sum(abs(s) for s in samples) / len(samples)
                    logger.info(f"🔊 PCM quality: max_amp={max_amp}/32767 ({max_amp/32767*100:.1f}%), "
                               f"avg_amp={avg_amp:.0f}, silent={max_amp < 100}")

                logger.info(f"✅ [DECODE] Decoded {len(new_pcm_chunks)} new frames from {len(self.webm_buffer)} bytes "
                           f"(total {len(all_pcm_chunks)} frames, skipped {len(all_pcm_chunks) - len(new_pcm_chunks)}) → {len(pcm_data)} bytes PCM")

                # Note: Buffer management now handled in main audio loop (see line 319-334)
                # This ensures we finalize utterances gracefully instead of breaking WebM decode

                return pcm_data

            return b''

        except (av.error.InvalidDataError, av.error.ValueError) as e:
            # Incomplete container data - keep buffering
            # Note: This should be rare after buffer management fix
            logger.warning(f"⏳ [DECODE] Incomplete WebM data ({type(e).__name__}), buffering... ({len(self.webm_buffer)} bytes)")
            return b''

        except Exception as e:
            logger.error(f"❌ [DECODE] PyAV decode failed: {type(e).__name__}: {e}, buffer={len(self.webm_buffer)} bytes")
            return b''

    def _has_sufficient_speech_energy(self, pcm_data: bytes) -> bool:
        """
        Option B: Check if audio has sustained speech-level energy
        Requires 500ms of continuous speech before accepting (reduces echo/noise)
        """
        import numpy as np

        samples = np.frombuffer(pcm_data, dtype=np.int16)
        energy = int(np.abs(samples).mean())

        self.audio_energy_buffer.append(energy)

        # Require 500ms of sustained energy (5 chunks * 100ms approx)
        if len(self.audio_energy_buffer) < 5:
            return False

        # Check average energy over last 500ms
        avg_energy = int(np.mean(self.audio_energy_buffer[-5:]))

        if avg_energy > self.speech_energy_threshold:
            logger.debug(f"✅ Sufficient speech energy: {avg_energy} (threshold: {self.speech_energy_threshold})")
            return True
        else:
            logger.debug(f"❌ Insufficient energy: {avg_energy} < {self.speech_energy_threshold}")
            return False

    def _decode_webm_chunk(self, chunk: bytes) -> bytes:
        """
        Try to decode a single WebM chunk independently

        MediaRecorder with timeslice should produce independently playable chunks,
        but first chunk contains header while subsequent chunks may not.
        Save header from first successful decode and try to reuse for later chunks.

        Args:
            chunk: Single WebM chunk from MediaRecorder

        Returns:
            PCM audio bytes if successful, empty bytes otherwise
        """
        try:
            buffer = BytesIO(chunk)
            container = av.open(buffer, 'r')
            audio_stream = container.streams.audio[0]

            # Save header from first successful decode
            if self.webm_header is None:
                self.webm_header = chunk[:min(len(chunk), 4096)]  # Save first 4KB as header

            pcm_chunks = []
            for frame in container.decode(audio_stream):
                # FIX: Convert planar audio to interleaved format for WhisperX
                pcm_array = frame.to_ndarray()

                # Convert float32 to int16 if needed (WhisperX expects int16)
                if pcm_array.dtype == np.float32:
                    pcm_array = (pcm_array * 32767).astype(np.int16)

                if frame.format.is_planar:
                    pcm_array = pcm_array.T  # Transpose (channels, samples) → (samples, channels)
                pcm_bytes = pcm_array.tobytes()
                pcm_chunks.append(pcm_bytes)

            container.close()

            if pcm_chunks:
                # Count frames in header (first chunk only)
                if self.header_frame_count == 0:
                    self.header_frame_count = len(pcm_chunks)
                    logger.info(f"📦 Header contains {self.header_frame_count} frames")

                pcm_data = b''.join(pcm_chunks)
                logger.info(f"✅ Decoded chunk: {len(chunk)} bytes → {len(pcm_data)} PCM bytes")
                return pcm_data

            return b''

        except (av.error.InvalidDataError, av.error.ValueError) as e:
            # Chunk not independently decodable - try with saved header
            if self.webm_header is not None:
                try:
                    # Prepend saved header to continuation chunk
                    chunk_with_header = self.webm_header + chunk
                    buffer = BytesIO(chunk_with_header)
                    container = av.open(buffer, 'r')
                    audio_stream = container.streams.audio[0]

                    pcm_chunks = []
                    frame_index = 0
                    for frame in container.decode(audio_stream):
                        # Skip header frames to avoid duplication
                        if frame_index >= self.header_frame_count:
                            # FIX: Convert planar audio to interleaved format for WhisperX
                            pcm_array = frame.to_ndarray()

                            # Convert float32 to int16 if needed (WhisperX expects int16)
                            if pcm_array.dtype == np.float32:
                                pcm_array = (pcm_array * 32767).astype(np.int16)

                            if frame.format.is_planar:
                                pcm_array = pcm_array.T  # Transpose (channels, samples) → (samples, channels)
                            pcm_bytes = pcm_array.tobytes()
                            pcm_chunks.append(pcm_bytes)
                        frame_index += 1

                    container.close()

                    if pcm_chunks:
                        pcm_data = b''.join(pcm_chunks)
                        logger.info(f"✅ Decoded chunk with header (skipped {self.header_frame_count} frames): {len(chunk)} bytes → {len(pcm_data)} PCM bytes")
                        return pcm_data
                except Exception as header_err:
                    logger.debug(f"⏩ Header prepend failed: {type(header_err).__name__}")

            # Will try buffered decode
            logger.debug(f"⏩ Chunk decode failed ({type(e).__name__}), will buffer")
            return b''
        except Exception as e:
            logger.warning(f"⚠️ Chunk decode error: {type(e).__name__}: {e}")
            return b''

    def _extract_pcm_audio(self) -> bytes:
        """
        Fully decode WebM/OGG to PCM audio (48kHz stereo, 16-bit)

        Uses PyAV to decode containers to raw PCM, bypassing Opus frame issues.
        This produces the exact PCM format WhisperX expects (no Opus decoding needed).

        Returns:
            Raw PCM bytes (48kHz stereo int16) ready for WhisperX, or empty bytes if incomplete
        """
        if not self.webm_buffer:
            return b''

        try:
            # Wrap buffer in BytesIO for PyAV
            buffer = BytesIO(bytes(self.webm_buffer))

            # Open container (auto-detects WebM or OGG format)
            container = av.open(buffer, 'r')
            audio_stream = container.streams.audio[0]

            logger.info(f"✅ WebM container opened: codec={audio_stream.codec_context.name}, "
                       f"rate={audio_stream.codec_context.sample_rate}Hz, "
                       f"channels={audio_stream.codec_context.channels}")

            # Format validation warnings
            if audio_stream.codec_context.sample_rate != 48000:
                logger.warning(f"⚠️ Unexpected sample rate: {audio_stream.codec_context.sample_rate}Hz (expected 48000Hz)")
            if audio_stream.codec_context.channels != 2:
                logger.warning(f"⚠️ Unexpected channels: {audio_stream.codec_context.channels} (expected 2 for stereo)")

            pcm_chunks = []

            # DECODE packets to PCM frames (not just demux)
            for frame in container.decode(audio_stream):
                # Convert AudioFrame to raw PCM bytes (48kHz stereo int16)
                # FIX: Convert planar audio to interleaved format for WhisperX
                pcm_array = frame.to_ndarray()

                # Convert float32 to int16 if needed (WhisperX expects int16)
                if pcm_array.dtype == np.float32:
                    pcm_array = (pcm_array * 32767).astype(np.int16)

                if frame.format.is_planar:
                    pcm_array = pcm_array.T  # Transpose (channels, samples) → (samples, channels)
                pcm_bytes = pcm_array.tobytes()
                pcm_chunks.append(pcm_bytes)

            container.close()

            # Combine all PCM chunks
            pcm_data = b''.join(pcm_chunks)

            logger.info(f"🎵 Decoded {len(pcm_chunks)} PCM frames from {len(self.webm_buffer)} bytes "
                       f"({len(pcm_data)} PCM bytes)")

            # Clear buffer after successful decode (this is fallback buffered decode)
            self.webm_buffer.clear()

            return pcm_data

        except av.error.InvalidDataError:
            # Incomplete container data - keep buffering
            logger.debug(f"⏳ Incomplete WebM data, buffering... ({len(self.webm_buffer)} bytes)")
            return b''

        except Exception as e:
            # Other PyAV error - log and reset buffer
            logger.warning(f"⚠️ WebM decode error: {type(e).__name__}: {e}")
            self.webm_buffer.clear()  # Reset to avoid perpetual errors
            return b''

    async def _send_stop_listening(self, reason: str, **metadata):
        """
        Send stop_listening event to frontend to halt MediaRecorder

        Args:
            reason: Why listening stopped ("silence_detected", "max_utterance_timeout", "manual_stop")
            **metadata: Additional metadata (silence_duration_ms, etc.)
        """
        if not self.is_active:
            logger.debug(f"⏭️ Skipping stop_listening event (connection closed)")
            return

        try:
            event_data = {
                "session_id": str(self.session_id),
                "reason": reason,
                **metadata
            }

            await self.websocket.send_json({
                "event": "stop_listening",
                "data": event_data
            })

            logger.info(f"📡 Sent stop_listening event (reason: {reason}, metadata: {metadata})")

        except Exception as e:
            logger.debug(f"⏭️ Could not send stop_listening event (connection likely closed): {e}")

    async def _monitor_silence(self):
        """
        Monitor for silence and trigger finalization (MULTI-TURN MODE)

        Continuously checks if audio has stopped for silence_threshold_ms.
        Also enforces max_utterance_time_ms as absolute timeout.
        When silence detected, finalizes transcription and calls LLM.

        After finalization, continues monitoring for new audio (auto-restart detection).
        This enables multi-turn conversations without reconnecting WebSocket.
        """
        logger.info(f"[SILENCE_MONITOR] 🎬 Started in MULTI-TURN mode (checking every 100ms)")
        iteration = 0
        finalized = False
        last_finalization_time = None
        finalize_start_time = None  # Watchdog: Track finalization duration

        try:
            while self.is_active:
                await asyncio.sleep(0.1)  # Check every 100ms
                iteration += 1

                # Watchdog: Reset stuck finalization after 30s
                if self.is_finalizing:
                    if finalize_start_time is None:
                        finalize_start_time = time.time()
                    elif (time.time() - finalize_start_time) > 30.0:
                        logger.warning("⚠️ [WATCHDOG] Resetting stuck finalization state after 30s")
                        logger.warning(f"   - Session: {self.session_id}")
                        logger.warning(f"   - Current transcript: \"{self.current_transcript[:50]}...\"")
                        logger.warning(f"   - LLM task: {self.llm_task}")
                        self.is_finalizing = False
                        self.final_transcript_ready = False
                        self.final_transcript = ""
                        finalize_start_time = None
                else:
                    finalize_start_time = None

                # Watchdog: Reset stale t_first_audio (stuck utterance_start_time)
                if self.t_first_audio and self.utterance_start_time:
                    utterance_age_s = time.time() - self.utterance_start_time
                    if utterance_age_s > 300.0:  # 5 minutes - clearly stale
                        logger.warning(f"⚠️ [WATCHDOG] Stale utterance_start_time detected ({utterance_age_s:.1f}s old) - resetting t_first_audio")
                        logger.warning(f"   - Session: {self.session_id}")
                        logger.warning(f"   - Current transcript: \"{self.current_transcript[:50]}...\"")
                        self.t_first_audio = None
                        self.utterance_start_time = None

                # Heartbeat log every 50 iterations (5 seconds)
                if iteration % 50 == 0:
                    logger.debug(f"[SILENCE_MONITOR] ❤️ Heartbeat #{iteration} (last_audio={self.last_audio_time}, "
                               f"utterance_start={self.utterance_start_time}, finalized={finalized}, is_finalizing={self.is_finalizing})")

                # Auto-restart detection: Check if new audio arrived after finalization
                if finalized and self.last_audio_time:
                    elapsed_ms = (time.time() - self.last_audio_time) * 1000

                    # If audio is recent (less than silence threshold), user started speaking again
                    if elapsed_ms < self.silence_threshold_ms:
                        # ✅ CHECKPOINT 5: State Transition (Auto-Restart)
                        self.turn_number += 1  # Increment turn counter
                        logger.info(f"🔄 [STATE] New audio detected after finalization ({elapsed_ms:.0f}ms ago) - "
                                   f"auto-restarting for Turn {self.turn_number}!")

                        # Reset state for new turn
                        finalized = False
                        last_finalization_time = time.time()
                        self.current_transcript = ""
                        self.is_finalizing = False
                        # ✅ FIX: Reset final transcript flags for new turn
                        self.final_transcript_ready = False
                        self.final_transcript = ""
                        # Batch 2.2: Track utterance start time reset
                        old_utterance_start = self.utterance_start_time
                        self.utterance_start_time = self.last_audio_time  # New utterance start

                        # ✅ FIX: Reset per-turn timing metrics for accurate latency tracking
                        # These timestamps must be reset between conversation turns, not just on connection
                        self.t_first_audio = None  # ← FIX: Reset to allow Turn 2+ utterance_start_time update
                        self.t_first_partial = None
                        self.t_transcription_complete = None
                        self.t_ai_start = None
                        self.t_ai_complete = None
                        self.t_llm_complete = None
                        self.t_audio_complete = None
                        logger.debug(f"🔄 [TIMING] Reset per-turn timing metrics for new conversation")

                        # ✅ CRITICAL FIX: Clear WebM buffer BUT preserve header for Turn 2+
                        # SAFE LOCATION: Turn 2 audio already detected (elapsed_ms < silence_threshold_ms)
                        # WebM header is preserved in self.webm_header (captured on Turn 1)
                        logger.info(f"🧹 [BUFFER_CLEAR] Pre-clear state: buffer={len(self.webm_buffer)} bytes, "
                                   f"frames={self.frames_sent_to_whisperx}, header_validated={self.header_validated}")
                        self.webm_buffer = bytearray()
                        self.frames_sent_to_whisperx = 0
                        # NOTE: Removed self.av_container = None (was NO-OP - variable never used)
                        # Header preservation happens in _extract_new_pcm_audio() via self.webm_header
                        logger.info(f"✅ [BUFFER_CLEAR] Cleared WebM buffer for Turn {self.turn_number} "
                                   f"(header preserved: {len(self.webm_header) if self.webm_header else 0} bytes)")

                        logger.debug(f"🔄 [STATE] Utterance start time reset: {old_utterance_start} → {self.utterance_start_time}")
                        iteration = 0

                        logger.info(f"✅ [STATE] Auto-restart complete - ready for Turn {self.turn_number} (monitoring active)")

                # Check max utterance timeout (absolute limit) - only if not finalized
                if not finalized and self.utterance_start_time:
                    elapsed_ms = (time.time() - self.utterance_start_time) * 1000

                    # ✅ FIX: Only finalize if we have actual speech (non-empty partial transcript)
                    if elapsed_ms >= self.max_utterance_time_ms and self.current_transcript.strip():
                        if not self.is_finalizing:
                            logger.warning(f"[SILENCE_MONITOR] ⏱️ Max utterance time ({self.max_utterance_time_ms}ms) exceeded - forcing finalization")

                            # DIAGNOSTIC: Log current partial transcript
                            logger.info(f"📝 [SILENCE_MONITOR] Current partial transcript: \"{self.current_transcript[:100]}{'...' if len(self.current_transcript) > 100 else ''}\" (length={len(self.current_transcript)} chars)")

                            # ✅ FIX: Tell WhisperX to finalize (process full session_buffer)
                            logger.info(f"🏁 [FINALIZE] Requesting final transcript from WhisperX (max utterance timeout, session={self.session_id})")
                            success = await self.stt_service.finalize_transcript(self.session_id)
                            if not success:
                                logger.warning(f"⚠️ [FINALIZE] Failed to trigger WhisperX finalize")

                            # MULTI-TURN MODE: Don't send stop_listening - keep MediaRecorder running!
                            # Frontend will show "Ready for next question" automatically
                            # await self._send_stop_listening(
                            #     reason="max_utterance_timeout",
                            #     elapsed_ms=int(elapsed_ms),
                            #     max_ms=self.max_utterance_time_ms
                            # )

                            await self._finalize_transcription()
                            finalized = True
                            last_finalization_time = time.time()
                            # ✅ Continue monitoring for next turn - don't break!

                # Check silence threshold - only if not finalized
                if not finalized and self.last_audio_time:
                    silence_duration_ms = (time.time() - self.last_audio_time) * 1000

                    # Batch 2.2: Log silence duration every ~1 second to help diagnose detection issues
                    if iteration % 10 == 0:  # Every 1 second (10 iterations * 100ms)
                        has_transcript = bool(self.current_transcript.strip())
                        logger.debug(f"🤫 [SILENCE_CHECK] Duration: {silence_duration_ms:.0f}ms / {self.silence_threshold_ms}ms, has_transcript={has_transcript}, will_finalize={silence_duration_ms >= self.silence_threshold_ms and has_transcript}")

                    # ✅ FIX: Only finalize if we have actual speech (non-empty partial transcript)
                    # This prevents spurious finalizations from background noise before user speaks
                    if silence_duration_ms >= self.silence_threshold_ms and self.current_transcript.strip():
                        if not self.is_finalizing:
                            logger.info(f"[SILENCE_MONITOR] 🤫 Silence detected ({int(silence_duration_ms)}ms) - finalizing")

                            # ⏱️ METRIC 4: Silence Detection Latency (in milliseconds)
                            self.metrics.record_silence_detection_latency(silence_duration_ms)
                            logger.info(f"⏱️ LATENCY [WebRTC - Silence Detection]: {silence_duration_ms:.2f}ms")

                            # DIAGNOSTIC: Log current partial transcript
                            logger.info(f"📝 [SILENCE_MONITOR] Current partial transcript: \"{self.current_transcript[:100]}{'...' if len(self.current_transcript) > 100 else ''}\" (length={len(self.current_transcript)} chars)")

                            # ✅ FIX: Tell WhisperX to finalize (process full session_buffer)
                            logger.info(f"🏁 [FINALIZE] Requesting final transcript from WhisperX (session={self.session_id})")
                            success = await self.stt_service.finalize_transcript(self.session_id)
                            if not success:
                                logger.warning(f"⚠️ [FINALIZE] Failed to trigger WhisperX finalize")

                            # MULTI-TURN MODE: Don't send stop_listening - keep MediaRecorder running!
                            # Frontend will show "Ready for next question" automatically
                            # await self._send_stop_listening(
                            #     reason="silence_detected",
                            #     silence_duration_ms=int(silence_duration_ms)
                            # )

                            await self._finalize_transcription()
                            finalized = True
                            last_finalization_time = time.time()
                            # ✅ Continue monitoring for next turn - don't break!

        except asyncio.CancelledError:
            logger.info(f"[SILENCE_MONITOR] 🛑 Cancelled after {iteration} iterations")
        except Exception as e:
            logger.error(f"[SILENCE_MONITOR] ❌ Unexpected error: {e}", exc_info=True)

    async def _finalize_transcription(self):
        """
        Finalize transcription and route to LLM

        IMPORTANT: Wait for WhisperX final transcript pattern (matches Discord)
        - Silence monitor calls stt_service.finalize_transcript() when silence detected
        - WhisperX processes full session_buffer and sends final transcript
        - STT callback sets self.final_transcript_ready flag
        - This method waits for flag (with timeout), then uses final transcript

        Steps:
        1. Wait for WhisperX final transcript (with 2s timeout)
        2. Use final transcript from WhisperX (NOT current_transcript)
        3. Send final_transcript event to browser
        4. Save user message via ConversationService
        5. Get conversation context
        6. Route to LLMService with streaming
        7. Save AI response via ConversationService
        8. Generate TTS via TTSService
        """
        if self.is_finalizing:
            return

        self.is_finalizing = True

        # Option B: Clear energy buffer after finalization
        self.audio_energy_buffer.clear()
        logger.debug("🧹 [ENERGY_BUFFER] Cleared energy buffer for next turn")

        try:
            # ✅ FIX: Wait for WhisperX final transcript (with timeout)
            MAX_WAIT_TIME = 2.0  # 2 seconds timeout
            wait_start = time.time()

            logger.info(f"⏳ [FINALIZE] Waiting for WhisperX final transcript (timeout={MAX_WAIT_TIME}s)...")

            while not self.final_transcript_ready and (time.time() - wait_start) < MAX_WAIT_TIME:
                await asyncio.sleep(0.05)  # Check every 50ms

            # Check if we got the final transcript
            if self.final_transcript_ready:
                wait_duration = time.time() - wait_start
                logger.info(f"✅ [FINALIZE] Final transcript received after {wait_duration:.3f}s")
                transcript = self.final_transcript.strip()
            else:
                # Timeout - fall back to last partial
                wait_duration = time.time() - wait_start
                logger.warning(f"⏱️ [FINALIZE] Timeout waiting for final transcript ({wait_duration:.3f}s) - using last partial")
                transcript = self.current_transcript.strip()

            # DIAGNOSTIC: Log the transcript being finalized
            logger.info(f"📝 [FINALIZE] Using transcript: \"{transcript[:100]}{'...' if len(transcript) > 100 else ''}\" (length={len(transcript)} chars, from_final={self.final_transcript_ready})")

            if not transcript:
                logger.info("📝 Empty transcript - skipping LLM processing")
                self.is_finalizing = False
                # Reset flags for next turn
                self.final_transcript_ready = False
                self.final_transcript = ""
                return

            # DIAGNOSTIC: Warn if transcript seems suspiciously short
            if len(transcript) < 10:
                logger.warning(f"⚠️ [FINALIZE] Transcript is very short ({len(transcript)} chars) - possible truncation?")

            logger.info(f"📝 Final transcript: \"{transcript}\"")

            # Send final transcript to browser
            await self._send_final_transcript(transcript)

            # Notify frontend that AI response generation is starting (TTS will follow)
            # This must happen early, right after final transcript, so frontend knows to defer disconnect if user clicks mic OFF
            await self.websocket.send_json({
                "event": "ai_response_start",
                "data": {
                    "session_id": str(self.session_id)
                }
            })
            logger.info("🤖 Sent ai_response_start event to frontend (TTS pipeline starting)")

            # Save user message to conversation
            import uuid
            user_correlation_id = str(uuid.uuid4())

            logger.info(f"💾 [DB_SAVE] Saving user message to database: session={self.session_id}, role=user, length={len(transcript)} chars, correlation_id={user_correlation_id[:8]}...")
            user_message = await self.conversation_service.add_message(
                session_id=self.session_id,
                role="user",
                content=transcript,
                metadata={
                    'source': 'webrtc',
                    'user_id': self.user_id
                },
                correlation_id=user_correlation_id
            )
            logger.info(f"✅ [DB_SAVE] Saved user message to database")

            # Emit message_saved confirmation event
            await ws_manager.broadcast({
                "event": "message_saved",
                "data": {
                    "message_id": str(user_message.metadata.get('id')) if hasattr(user_message, 'metadata') else None,
                    "session_id": self.session_id,
                    "role": "user",
                    "correlation_id": user_correlation_id,
                    "timestamp": user_message.timestamp.isoformat()
                }
            })
            logger.info(f"📡 [WS_EVENT] Sent message_saved event (role=user, correlation_id={user_correlation_id[:8]}...)")

            # Get agent configuration
            agent = await self.conversation_service.get_agent_config(self.session_id)
            logger.info(f"🤖 Using agent: {agent.name} (provider: {agent.llm_provider}, model: {agent.llm_model})")

            # Route to LLM (Phase 3: Track as task for cancellation)
            self.llm_task = asyncio.create_task(self._handle_llm_response(transcript, agent))

            try:
                await self.llm_task
            except asyncio.CancelledError:
                logger.info(f"🛑 LLM task cancelled during generation")
                raise
            finally:
                self.llm_task = None  # Clear task reference
                # Always reset finalization flags (even on cancellation/error)
                self.is_finalizing = False

            # Reset state for next turn
            self.current_transcript = ""
            # ✅ FIX: Reset final transcript flags for next turn
            self.final_transcript_ready = False
            self.final_transcript = ""

        except Exception as e:
            logger.error(f"❌ Error finalizing transcription: {e}", exc_info=True)
            # ⏱️ METRIC 11: Error Count
            self.metrics.record_error()
            await self._send_error(f"Error processing transcript: {str(e)}")
            self.is_finalizing = False
            # Reset flags even on error
            self.final_transcript_ready = False
            self.final_transcript = ""

    async def _handle_llm_response(self, transcript: str, agent):
        """
        Handle LLM response generation and streaming

        Args:
            transcript: User's transcribed text
            agent: Agent model instance with LLM configuration
        """
        try:
            t_llm_start = time.time()
            self.t_ai_start = t_llm_start  # Store for metrics tracking

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

            # DIAGNOSTIC: Log the full conversation context being sent to LLM
            logger.info(f"📋 [LLM_CONTEXT] Building LLM request with {len(llm_messages)} messages:")
            for idx, msg in enumerate(llm_messages):
                content_preview = msg['content'][:80] + '...' if len(msg['content']) > 80 else msg['content']
                logger.info(f"   [{idx}] {msg['role']}: \"{content_preview}\"")

            # Build LLM config
            llm_config = LLMConfig(
                provider=ProviderType(agent.llm_provider),
                model=agent.llm_model,
                temperature=agent.temperature,
                system_prompt=agent.system_prompt
            )

            logger.info(f"📤 Sending to LLM ({agent.llm_provider}/{agent.llm_model}): \"{transcript}\"")

            # Create LLM service with agent-specific database config (includes decrypted API key)
            from src.services.llm_service import get_llm_service_for_agent
            llm_service = await get_llm_service_for_agent(agent)

            # Retry logic for empty LLM responses
            max_retries = 2
            retry_count = 0
            full_response = ""

            while retry_count <= max_retries:
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

                        # ⏱️ METRIC 7: First LLM Chunk Latency (n8n webhook path - also applies to direct LLM)
                        self.metrics.record_n8n_first_chunk_latency(latency_s)
                        logger.info(f"⏱️ LATENCY [WebRTC - First LLM Chunk]: {latency_s * 1000:.2f}ms")

                        # DIAGNOSTIC: Log first chunk content
                        logger.info(f"📤 [AI_CHUNK] First chunk received: \"{chunk[:50]}{'...' if len(chunk) > 50 else ''}\" (length={len(chunk)} chars)")

                        # Batch 2.4: Detect suspiciously short first chunks
                        if len(chunk) < 3:
                            logger.warn(f"⚠️ [LLM_QUALITY] First chunk is suspiciously short ({len(chunk)} chars) - possible truncation or streaming issue")

                        first_chunk_received = True

                    # Accumulate response
                    prev_length = len(full_response)
                    full_response += chunk
                    # DIAGNOSTIC: Log accumulation (debug level to avoid spam)
                    logger.debug(f"📤 [AI_CHUNK] Accumulated response: {prev_length} → {len(full_response)} chars")

                    # Stream chunk to browser
                    await self._send_ai_response_chunk(chunk)

                # Generate response
                await llm_service.generate_response(
                    session_id=self.session_id,
                    messages=llm_messages,
                    config=llm_config,
                    stream=True,
                    callback=on_chunk
                )

                # Check if response is empty
                if not full_response or not full_response.strip():
                    retry_count += 1
                    if retry_count <= max_retries:
                        logger.warning(f"⚠️ LLM returned empty response (attempt {retry_count}/{max_retries + 1}), retrying...")

                        # Broadcast retry notification to frontend
                        await ws_manager.broadcast({
                            "event": "llm_retry",
                            "data": {
                                "session_id": str(self.session_id),
                                "attempt": retry_count,
                                "maxAttempts": max_retries + 1,
                                "message": f"Retrying... (attempt {retry_count}/{max_retries + 1})"
                            }
                        })

                        # Reset for retry
                        full_response = ""
                        t_llm_start = time.time()  # Reset timer for retry
                        continue
                    else:
                        logger.error(f"❌ LLM returned empty response after {max_retries + 1} attempts")
                        full_response = "I apologize, but I'm having trouble generating a response right now. Could you please try again?"

                        # Broadcast fallback notification to frontend
                        await ws_manager.broadcast({
                            "event": "llm_fallback",
                            "data": {
                                "session_id": str(self.session_id),
                                "message": "AI response failed after multiple attempts. Using fallback message.",
                                "fallbackMessage": full_response
                            }
                        })

                # Success - break out of retry loop
                break

            # Generate correlation ID for this AI response (used for both event and database)
            import uuid
            ai_correlation_id = str(uuid.uuid4())

            # Send completion event
            # DIAGNOSTIC: Log complete response before saving
            logger.info(f"💾 [AI_COMPLETE] AI response complete: \"{full_response[:100]}{'...' if len(full_response) > 100 else ''}\" (length={len(full_response)} chars, correlation_id={ai_correlation_id[:8]}...)")
            await self._send_ai_response_complete(full_response, ai_correlation_id)

            # Record latency
            t_llm_complete = time.time()
            self.t_llm_complete = t_llm_complete  # Store for TTS queue metric
            self.t_ai_complete = t_llm_complete   # Store for metrics tracking
            latency_s = t_llm_complete - t_llm_start
            logger.info(f"⏱️ LATENCY [total LLM generation]: {latency_s:.3f}s")

            # ⏱️ METRIC 5: AI Generation Latency
            self.metrics.record_ai_generation_latency(latency_s)
            logger.info(f"⏱️ LATENCY [WebRTC - AI Generation]: {latency_s * 1000:.2f}ms")

            # ✅ FIX: Validate response is non-empty before saving
            if not full_response.strip():
                logger.warning(f"🚫 [DB_SAVE] Skipping save of empty AI response (session={self.session_id})")
            else:
                # Save AI message to conversation (using same correlation ID as event)
                logger.info(f"💾 [DB_SAVE] Saving AI response to database: session={self.session_id}, role=assistant, length={len(full_response)} chars, correlation_id={ai_correlation_id[:8]}...")
                ai_message = await self.conversation_service.add_message(
                    session_id=self.session_id,
                    role="assistant",
                    content=full_response,
                    metadata={
                        'llm_provider': agent.llm_provider,
                        'llm_model': agent.llm_model,
                        'latency_s': latency_s
                    },
                    correlation_id=ai_correlation_id
                )
                logger.info(f"✅ [DB_SAVE] Saved AI message to database (ID will be assigned by DB)")

                # Emit message_saved confirmation event
                await ws_manager.broadcast({
                    "event": "message_saved",
                    "data": {
                        "message_id": str(ai_message.metadata.get('id')) if hasattr(ai_message, 'metadata') else None,
                        "session_id": self.session_id,
                        "role": "assistant",
                        "correlation_id": ai_correlation_id,
                        "timestamp": ai_message.timestamp.isoformat()
                    }
                })
                logger.info(f"📡 [WS_EVENT] Sent message_saved event (role=assistant, correlation_id={ai_correlation_id[:8]}...)")

            # Note: Full metrics snapshot broadcast moved to end of _generate_tts() after total_pipeline_latency
            # This ensures all metrics (including TTS) are included in the broadcast

            # Generate and stream TTS audio to browser
            await self._generate_tts(full_response, agent)

        except Exception as e:
            logger.error(f"❌ Error handling LLM response: {e}", exc_info=True)
            # ⏱️ METRIC 11: Error Count
            self.metrics.record_error()
            await self._send_error(f"Error generating AI response: {str(e)}")

    # WebSocket message senders
    async def _send_partial_transcript(self, text: str):
        """Send partial transcript event to browser"""
        if not self.is_active:
            logger.debug(f"⏭️ Skipping partial transcript send (connection closed)")
            return

        try:
            message = {
                "event": "partial_transcript",
                "data": {
                    "text": text,
                    "session_id": str(self.session_id)
                }
            }
            # Send to active voice WebSocket
            await self.websocket.send_json(message)
            # Broadcast to global event stream (for conversation history UI)
            await ws_manager.broadcast(message)
        except Exception as e:
            logger.debug(f"⏭️ Could not send partial transcript (connection likely closed): {e}")

    async def _send_final_transcript(self, text: str):
        """Send final transcript event to browser"""
        if not self.is_active:
            logger.debug(f"⏭️ Skipping final transcript send (connection closed)")
            return

        try:
            message = {
                "event": "final_transcript",
                "data": {
                    "text": text,
                    "session_id": str(self.session_id)
                }
            }
            # Send to active voice WebSocket
            await self.websocket.send_json(message)
            # Broadcast to global event stream (for conversation history UI)
            await ws_manager.broadcast(message)
        except Exception as e:
            logger.debug(f"⏭️ Could not send final transcript (connection likely closed): {e}")

    async def _send_ai_response_chunk(self, text: str):
        """Send AI response chunk event to browser"""
        if not self.is_active:
            logger.debug(f"⏭️ Skipping AI response chunk send (connection closed)")
            return

        try:
            message = {
                "event": "ai_response_chunk",
                "data": {
                    "text": text,
                    "session_id": str(self.session_id)
                }
            }
            # Send to active voice WebSocket
            await self.websocket.send_json(message)
            # Broadcast to global event stream (for conversation history UI)
            await ws_manager.broadcast(message)
        except Exception as e:
            logger.debug(f"⏭️ Could not send AI response chunk (connection likely closed): {e}")

    async def _send_ai_response_complete(self, text: str, correlation_id: str):
        """Send AI response complete event to browser with correlation ID"""
        if not self.is_active:
            logger.debug(f"⏭️ Skipping AI response complete send (connection closed)")
            return

        try:
            import time
            message = {
                "event": "ai_response_complete",
                "data": {
                    "text": text,
                    "session_id": str(self.session_id),
                    "correlation_id": correlation_id,
                    "timestamp": time.time()
                }
            }
            # Send to active voice WebSocket
            await self.websocket.send_json(message)
            # Broadcast to global event stream (for conversation history UI)
            await ws_manager.broadcast(message)
        except Exception as e:
            logger.debug(f"⏭️ Could not send AI response complete (connection likely closed): {e}")

    async def _generate_tts(self, text: str, agent):
        """
        Generate and stream TTS audio to browser via TTSService

        Args:
            text: AI response text to synthesize
            agent: Agent model instance with TTS configuration
        """
        try:
            t_tts_start = time.time()

            # Record TTS queue latency (LLM complete → TTS start)
            if self.t_llm_complete:
                tts_queue_latency = t_tts_start - self.t_llm_complete
                self.metrics.record_tts_queue_latency(tts_queue_latency)
                logger.info(f"⏱️ LATENCY [TTS queue wait]: {tts_queue_latency:.3f}s")

            # ⏱️ Response Parsing Latency (AI complete → TTS start)
            # For WebRTC: Measures time to process LLM response text before TTS synthesis
            # For Discord (n8n): Measures time to parse JSON webhook response
            if self.t_ai_complete:
                response_parsing_latency_s = t_tts_start - self.t_ai_complete
                response_parsing_latency_ms = response_parsing_latency_s * 1000
                self.metrics.record_response_parsing_latency(response_parsing_latency_ms)
                logger.info(f"⏱️ LATENCY [WebRTC - Response Parsing]: {response_parsing_latency_ms:.2f}ms")

            logger.info(f"🔊 Starting TTS synthesis for text: \"{text[:50]}...\"")

            # Check TTS health first
            if not await self.tts_service.test_tts_health():
                logger.warning("⚠️ TTS service unavailable, skipping synthesis")
                await self._send_error("TTS service unavailable")
                return

            # Block audio input while bot is speaking
            self.is_bot_speaking = True
            logger.info("🤖 Bot speaking state: ENABLED (blocking user audio input)")

            # Send TTS start event (only if still connected)
            if self.is_active:
                await self.websocket.send_json({
                    "event": "tts_start",
                    "data": {"session_id": self.session_id}
                })

            # Send bot_speaking state change event (only if still connected)
            if self.is_active:
                await self.websocket.send_json({
                    "event": "bot_speaking_state_changed",
                    "data": {
                        "session_id": self.session_id,
                        "is_speaking": True
                    }
                })

            # Stream audio callback
            first_byte = True
            total_bytes = 0
            t_first_chunk_sent = None
            t_last_chunk_sent = None

            async def on_audio_chunk(chunk: bytes):
                nonlocal first_byte, total_bytes, t_first_chunk_sent, t_last_chunk_sent

                # Log first byte latency (critical UX metric)
                if first_byte:
                    t_first_byte = time.time()
                    latency_s = t_first_byte - t_tts_start
                    logger.info(f"⏱️ ⭐ LATENCY [TTS first byte]: {latency_s:.3f}s")
                    self.metrics.record_tts_first_byte_latency(latency_s)

                    # Record time to first audio (user finished speaking → first audio byte)
                    # Measure from transcription complete (user stopped speaking), not connection start
                    if self.t_transcription_complete:
                        time_to_first_audio = t_first_byte - self.t_transcription_complete
                        self.metrics.record_time_to_first_audio(time_to_first_audio)
                        logger.info(f"⏱️ ⭐⭐⭐ LATENCY [time to first audio]: {time_to_first_audio:.3f}s (transcription complete → audio plays)")

                    first_byte = False

                # Stream chunk to browser as binary WebSocket frame (only if still connected)
                if self.is_active:
                    await self.websocket.send_bytes(chunk)
                    total_bytes += len(chunk)

                    # Track streaming timing (for audio delivery metric)
                    if t_first_chunk_sent is None:
                        t_first_chunk_sent = time.time()
                    t_last_chunk_sent = time.time()

            # Synthesize with streaming via TTSService
            voice_id = agent.tts_voice or os.getenv('CHATTERBOX_VOICE_ID', 'default')

            audio_bytes = await self.tts_service.synthesize_speech(
                session_id=self.session_id,
                text=text,
                voice_id=voice_id,
                exaggeration=agent.tts_exaggeration,
                cfg_weight=agent.tts_cfg_weight,
                temperature=agent.tts_temperature,
                language_id=agent.tts_language,
                stream=True,
                callback=on_audio_chunk,
                filter_actions=agent.filter_actions_for_tts
            )

            # Send completion event (only if still connected)
            t_complete = time.time()
            total_latency_s = t_complete - t_tts_start
            logger.info(f"✅ TTS complete ({len(audio_bytes):,} bytes, {total_latency_s:.2f}s)")

            # ⏱️ METRIC 8: TTS Generation Latency
            self.metrics.record_tts_generation_latency(total_latency_s)
            logger.info(f"⏱️ LATENCY [WebRTC - TTS Generation]: {total_latency_s * 1000:.2f}ms")

            # ⏱️ Audio Streaming Duration (WebRTC audio delivery metric, analogous to Discord playback)
            # Discord: Measures playback duration (server-side audio playing through voice channel)
            # WebRTC: Measures streaming duration (time to deliver all chunks to browser)
            if t_first_chunk_sent and t_last_chunk_sent:
                streaming_duration = t_last_chunk_sent - t_first_chunk_sent
                self.metrics.record_audio_playback_latency(streaming_duration)
                logger.info(f"⏱️ LATENCY [WebRTC - Audio Streaming Duration]: {streaming_duration * 1000:.2f}ms (first chunk → last chunk delivered to browser)")

            # ⏱️ METRIC 9: Total Pipeline Latency (end-to-end: user speaks → audio complete)
            self.t_audio_complete = time.time()
            total_pipeline = self.t_audio_complete - self.t_start
            self.metrics.record_total_pipeline_latency(total_pipeline)
            logger.info(f"⏱️ LATENCY [WebRTC - Total Pipeline]: {total_pipeline * 1000:.2f}ms")

            # ⏱️ METRIC 10: Transcript Count (increment counter for each conversation turn)
            self.metrics.record_transcript()

            # 📊 Broadcast full metrics snapshot to frontend (matches Discord pattern)
            metrics_snapshot = self.metrics.get_metrics()
            await ws_manager.broadcast({
                "event": "metrics_updated",  # Match Discord event name (not "metrics_update")
                "data": metrics_snapshot     # Full snapshot with all 21 metrics
            })
            logger.info("📊 Broadcast full metrics snapshot to frontend")

            if self.is_active:
                await self.websocket.send_json({
                    "event": "tts_complete",
                    "data": {
                        "session_id": self.session_id,
                        "duration_s": total_latency_s
                    }
                })

            # Re-enable audio input after bot finishes speaking
            self.is_bot_speaking = False
            # ✅ CHECKPOINT 5: State Transition (TTS Complete → Listening)
            logger.info(f"✅ [STATE] TTS complete → LISTENING state, user audio input re-enabled, ready for next utterance (total discarded during TTS: {self.discarded_chunks_count} chunks)")

            # Reset discard counter (Batch 2.1)
            self.discarded_chunks_count = 0

            # Send bot_speaking state change event (only if still connected)
            if self.is_active:
                await self.websocket.send_json({
                    "event": "bot_speaking_state_changed",
                    "data": {
                        "session_id": self.session_id,
                        "is_speaking": False
                    }
                })

        except Exception as e:
            logger.error(f"❌ TTS error: {e}", exc_info=True)
            # ⏱️ METRIC 11: Error Count
            self.metrics.record_error()
            # Ensure is_bot_speaking is reset even on error
            self.is_bot_speaking = False
            # Reset discard counter even on error (Batch 2.1)
            logger.info(f"⚠️ [STATE] TTS error - resetting bot speaking state (discarded {self.discarded_chunks_count} chunks before error)")
            self.discarded_chunks_count = 0
            await self._send_error(f"TTS failed: {str(e)}")

    async def _send_error(self, message: str):
        """Send error event to browser (only if WebSocket is still active)"""
        if not self.is_active:
            logger.debug(f"⏭️ Skipping error message send (connection closed): {message}")
            return

        try:
            await self.websocket.send_json({
                "event": "error",
                "data": {
                    "message": message,
                    "session_id": str(self.session_id)
                }
            })
        except Exception as e:
            logger.debug(f"⏭️ Could not send error message (connection likely closed): {e}")

    async def _cleanup(self):
        """Clean up resources and disconnect services"""
        logger.info(f"🧹 Cleaning up WebRTC handler for session {self.session_id}")

        self.is_active = False

        # Cancel active LLM task (Phase 3: Prevent orphaned tasks)
        if self.llm_task and not self.llm_task.done():
            logger.info(f"🛑 Cancelling active LLM task")
            self.llm_task.cancel()
            try:
                await self.llm_task
            except asyncio.CancelledError:
                logger.info(f"✅ LLM task cancelled successfully")
            except Exception as e:
                logger.warning(f"⚠️ Error awaiting cancelled LLM task: {e}")
            # Reset finalization flags to prevent state machine deadlock
            self.is_finalizing = False
            self.final_transcript_ready = False
            self.final_transcript = ""
            logger.debug(f"✅ Reset finalization flags after task cancellation")

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
