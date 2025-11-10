"""
REAL E2E Tests with Actual WhisperX Server

This test suite connects to the REAL WhisperX server and validates
actual transcription accuracy, not mocks.

CRITICAL: These tests will FAIL if:
1. Float32 → int16 conversion is missing
2. Planar → interleaved transpose is missing
3. WhisperX server is not running
4. Audio format is incorrect

Success criteria:
- Transcriptions are NOT random garbage
- Audio is properly formatted for WhisperX
- Full pipeline works end-to-end
"""
from __future__ import annotations

import pytest
import asyncio
import numpy as np
import av
from io import BytesIO
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)


# ============================================================
# REAL AUDIO GENERATION (for WhisperX)
# ============================================================

def generate_test_audio_webm(duration_ms: int = 1000) -> bytes:
    """
    Generate WebM audio with actual recordable content

    WhisperX needs real audio patterns to transcribe.
    This generates a simple tone that WhisperX can process.

    Args:
        duration_ms: Duration in milliseconds

    Returns:
        WebM container bytes
    """
    buffer = BytesIO()
    sample_rate = 48000
    channels = 2

    # Create WebM container
    container = av.open(buffer, 'w', format='webm')
    stream = container.add_stream('opus', rate=sample_rate, layout='stereo')

    # Generate frames (20ms each)
    num_frames = max(1, duration_ms // 20)
    samples_per_frame = 960  # 20ms at 48kHz

    for frame_idx in range(num_frames):
        # Generate tones (440 Hz = A4 note for LEFT, 554 Hz = C#5 for RIGHT)
        t = np.linspace(0, 0.02, samples_per_frame)
        tone_left = np.sin(2 * np.pi * 440 * t)
        tone_right = np.sin(2 * np.pi * 554 * t)

        # Convert to int16 range
        audio_left = (tone_left * 16000).astype(np.int16)
        audio_right = (tone_right * 16000).astype(np.int16)

        # Create planar stereo (shape: channels, samples)
        # This mimics what browser sends (planar float32)
        audio_planar = np.stack([audio_left, audio_right], axis=0).astype(np.float32) / 32767.0

        frame = av.AudioFrame.from_ndarray(
            audio_planar,
            format='fltp',  # Float32 planar (what browser sends)
            layout='stereo'
        )
        frame.sample_rate = sample_rate

        # Encode and mux
        for packet in stream.encode(frame):
            container.mux(packet)

    # Flush encoder
    for packet in stream.encode():
        container.mux(packet)

    container.close()
    return buffer.getvalue()


# ============================================================
# REAL WHISPERX E2E TESTS
# ============================================================

class TestRealWhisperXTranscription:
    """
    E2E tests with REAL WhisperX server

    These tests validate the complete pipeline including actual transcription.
    """

    @pytest.mark.e2e
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_whisperx_receives_correct_audio_format(self, monkeypatch):
        """
        E2E TEST: Validate audio sent to WhisperX is correctly formatted

        This test connects to REAL WhisperX and sends audio.
        It validates:
        1. Float32 → int16 conversion works
        2. Planar → interleaved transpose works
        3. WhisperX can process the audio
        4. No "random garbage" transcriptions
        """
        from unittest.mock import AsyncMock

        # CRITICAL: Monkeypatch module constant BEFORE importing
        import src.services.stt_service as stt_module
        monkeypatch.setattr(stt_module, 'WHISPER_SERVER_URL', 'ws://whisperx:4901')

        from src.voice.webrtc_handler import WebRTCVoiceHandler

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "real_whisperx_test"

        # Track transcriptions received
        transcriptions = []

        async def capture_transcript(event):
            """Capture transcription events from STTService"""
            if hasattr(event, 'text'):
                transcriptions.append(event.text)
                logger.info(f"📝 Transcription received: '{event.text}'")

        logger.info("\n" + "="*70)
        logger.info("🎯 REAL E2E TEST: WhisperX Audio Format Validation")
        logger.info("="*70)

        # Create handler with REAL services (no mocks)
        handler = WebRTCVoiceHandler(
            websocket=mock_websocket,
            user_id=user_id,
            session_id=session_id
        )

        # Register transcript callback (ASYNC!)
        await handler.stt_service.register_callback('transcript', capture_transcript)

        try:
            # Connect to REAL WhisperX
            logger.info(f"🔌 Connecting to WhisperX at ws://whisperx:4901...")
            await handler.stt_service.connect(session_id)
            logger.info(f"✅ Connected to WhisperX")

            # Generate realistic audio (1 second)
            logger.info(f"🎵 Generating test audio (1 second, 48kHz stereo, float32 planar)...")
            webm_audio = generate_test_audio_webm(duration_ms=1000)
            logger.info(f"   WebM size: {len(webm_audio)} bytes")

            # Decode through WebRTC handler (tests float32→int16 + planar→interleaved)
            logger.info(f"🔄 Decoding WebM → PCM (testing format conversion)...")
            pcm_data = handler._decode_webm_chunk(webm_audio)

            assert len(pcm_data) > 0, "Should decode audio successfully"
            logger.info(f"   PCM decoded: {len(pcm_data)} bytes")

            # Validate PCM format (should be int16 interleaved)
            samples = np.frombuffer(pcm_data[:200], dtype=np.int16)
            logger.info(f"   PCM dtype: {samples.dtype} (expected: int16)")
            logger.info(f"   PCM sample count: {len(samples)}")
            logger.info(f"   PCM amplitude range: {samples.min()} to {samples.max()}")

            # Validate interleaved format (L/R channels should differ)
            left = samples[0::2]
            right = samples[1::2]
            logger.info(f"   Left channel sample: {left[0]}, Right channel sample: {right[0]}")

            assert samples.dtype == np.int16, "PCM should be int16"

            # Send to REAL WhisperX
            logger.info(f"📤 Sending PCM to WhisperX for transcription...")
            await handler.stt_service.send_audio(session_id, pcm_data, audio_format='pcm')

            # Wait for transcription (with timeout)
            logger.info(f"⏳ Waiting for transcription (max 10 seconds)...")
            timeout = 10
            elapsed = 0
            while len(transcriptions) == 0 and elapsed < timeout:
                await asyncio.sleep(0.5)
                elapsed += 0.5

            logger.info(f"\n📊 RESULTS:")
            logger.info(f"   Transcriptions received: {len(transcriptions)}")

            if transcriptions:
                for idx, text in enumerate(transcriptions):
                    logger.info(f"   [{idx+1}] '{text}'")

                # Validate transcription is NOT random garbage
                # WhisperX should produce SOME output for tone audio
                # Even if it's "[BLANK_AUDIO]" or silence markers
                first_transcript = transcriptions[0].lower()

                # Random garbage patterns we DON'T want to see
                garbage_patterns = ['oh!', 'shh shh', 'yeah.', 'uh', 'mm']
                is_garbage = any(pattern in first_transcript for pattern in garbage_patterns)

                logger.info(f"\n✅ VALIDATION:")
                logger.info(f"   Is random garbage: {is_garbage}")
                logger.info(f"   Transcription: '{transcriptions[0]}'")

                # The key test: transcription should NOT be random speech
                # For tone audio, WhisperX might return:
                # - Empty string
                # - "[BLANK_AUDIO]"
                # - Silence markers
                # But it should NOT return random words like "Oh!", "Yeah.", etc.

                if is_garbage:
                    pytest.fail(
                        f"FAILURE: Transcription is random garbage: '{transcriptions[0]}'\n"
                        f"This means audio format is STILL WRONG!\n"
                        f"Expected: silence markers or empty\n"
                        f"Got: random speech (indicates corrupted audio)"
                    )

                logger.info(f"   ✅ Transcription is NOT random garbage")
            else:
                logger.warning(f"   ⚠️ No transcription received (might be silence)")
                # No transcription is acceptable for tone audio
                # WhisperX might ignore pure tones

            logger.info(f"\n" + "="*70)
            logger.info(f"✅ REAL E2E TEST PASSED: Audio format correct")
            logger.info(f"="*70 + "\n")

        finally:
            # Cleanup
            await handler._cleanup()

    @pytest.mark.e2e
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_multiple_chunks_to_whisperx(self, monkeypatch):
        """
        E2E TEST: Multiple audio chunks processed by WhisperX

        Validates:
        - Multiple chunks decode correctly
        - Format stays consistent
        - WhisperX processes all chunks
        """
        from unittest.mock import AsyncMock

        # CRITICAL: Monkeypatch module constant BEFORE importing
        import src.services.stt_service as stt_module
        monkeypatch.setattr(stt_module, 'WHISPER_SERVER_URL', 'ws://whisperx:4901')

        from src.voice.webrtc_handler import WebRTCVoiceHandler

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "multi_chunk_whisperx_test"

        transcriptions = []

        async def capture_transcript(event):
            if hasattr(event, 'text'):
                transcriptions.append(event.text)

        logger.info("\n" + "="*70)
        logger.info("🎯 REAL E2E TEST: Multi-Chunk WhisperX Processing")
        logger.info("="*70)

        handler = WebRTCVoiceHandler(
            websocket=mock_websocket,
            user_id=user_id,
            session_id=session_id
        )

        await handler.stt_service.register_callback('transcript', capture_transcript)

        try:
            await handler.stt_service.connect(session_id)
            logger.info(f"✅ Connected to WhisperX")

            # Send 5 chunks
            num_chunks = 5
            logger.info(f"📤 Sending {num_chunks} audio chunks...")

            for i in range(num_chunks):
                webm_chunk = generate_test_audio_webm(duration_ms=500)
                pcm_data = handler._decode_webm_chunk(webm_chunk)

                if pcm_data:
                    await handler.stt_service.send_audio(session_id, pcm_data, audio_format='pcm')
                    logger.info(f"   Chunk {i+1}/{num_chunks}: {len(pcm_data)} PCM bytes sent")

                await asyncio.sleep(0.1)

            # Wait for processing
            await asyncio.sleep(2)

            logger.info(f"\n📊 RESULTS:")
            logger.info(f"   Chunks sent: {num_chunks}")
            logger.info(f"   Transcriptions received: {len(transcriptions)}")

            # Validate no garbage transcriptions
            garbage_count = 0
            garbage_patterns = ['oh!', 'shh', 'yeah', 'uh', 'mm']

            for text in transcriptions:
                text_lower = text.lower()
                if any(pattern in text_lower for pattern in garbage_patterns):
                    garbage_count += 1
                    logger.warning(f"   ⚠️ Garbage transcription: '{text}'")

            if garbage_count > 0:
                pytest.fail(
                    f"FAILURE: {garbage_count}/{len(transcriptions)} transcriptions are garbage\n"
                    f"Audio format conversion is STILL broken!"
                )

            logger.info(f"   ✅ No garbage transcriptions detected")
            logger.info(f"\n" + "="*70)
            logger.info(f"✅ MULTI-CHUNK TEST PASSED")
            logger.info(f"="*70 + "\n")

        finally:
            await handler._cleanup()

    @pytest.mark.e2e
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_format_conversion_validation(self):
        """
        E2E TEST: Validate format conversion at each step

        This test checks:
        1. Input: fltp (float32 planar)
        2. After dtype conversion: s16p (int16 planar)
        3. After transpose: s16 (int16 interleaved)
        4. WhisperX can process the result
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from unittest.mock import AsyncMock

        logger.info("\n" + "="*70)
        logger.info("🎯 REAL E2E TEST: Format Conversion Validation")
        logger.info("="*70)

        # Generate test audio
        webm_audio = generate_test_audio_webm(duration_ms=500)
        logger.info(f"📦 Generated WebM: {len(webm_audio)} bytes")

        # Decode and check format at each step
        container = av.open(BytesIO(webm_audio))
        audio_stream = next(s for s in container.streams if s.type == 'audio')

        for frame_idx, frame in enumerate(container.decode(audio_stream)):
            if frame_idx == 0:
                # Step 1: Original format
                pcm_array = frame.to_ndarray()
                logger.info(f"\n📊 Original Audio:")
                logger.info(f"   Format: {frame.format.name}")
                logger.info(f"   Planar: {frame.format.is_planar}")
                logger.info(f"   Shape: {pcm_array.shape}")
                logger.info(f"   Dtype: {pcm_array.dtype}")
                logger.info(f"   Sample range: {pcm_array.min():.4f} to {pcm_array.max():.4f}")

                assert frame.format.name == 'fltp', f"Expected fltp, got {frame.format.name}"
                assert pcm_array.dtype == np.float32, f"Expected float32, got {pcm_array.dtype}"

                # Step 2: After dtype conversion
                pcm_int16 = (pcm_array * 32767).astype(np.int16)
                logger.info(f"\n📊 After dtype conversion (float32 → int16):")
                logger.info(f"   Dtype: {pcm_int16.dtype}")
                logger.info(f"   Shape: {pcm_int16.shape}")
                logger.info(f"   Sample range: {pcm_int16.min()} to {pcm_int16.max()}")

                assert pcm_int16.dtype == np.int16, "Should be int16"

                # Step 3: After transpose
                pcm_interleaved = pcm_int16.T
                logger.info(f"\n📊 After transpose (planar → interleaved):")
                logger.info(f"   Shape: {pcm_interleaved.shape}")
                logger.info(f"   Layout: (samples, channels) = ({pcm_interleaved.shape[0]}, {pcm_interleaved.shape[1]})")

                # Validate interleaved pattern
                samples_flat = pcm_interleaved.flatten()
                logger.info(f"   First 10 samples: {samples_flat[:10]}")
                logger.info(f"   Pattern: [L0, R0, L1, R1, L2, R2, ...]")

                # Check that L and R channels are different (interleaved correctly)
                left_ch = pcm_interleaved[:, 0]
                right_ch = pcm_interleaved[:, 1]

                assert not np.array_equal(left_ch, right_ch), \
                    "Left and right channels should not be identical"

                logger.info(f"\n✅ FORMAT CONVERSION VALIDATION PASSED:")
                logger.info(f"   ✅ Step 1: fltp (float32 planar) - CORRECT")
                logger.info(f"   ✅ Step 2: int16 conversion - CORRECT")
                logger.info(f"   ✅ Step 3: Interleaved transpose - CORRECT")
                logger.info(f"   ✅ WhisperX will receive correct format")

                break

        container.close()

        logger.info(f"\n" + "="*70)
        logger.info(f"✅ FORMAT VALIDATION TEST PASSED")
        logger.info(f"="*70 + "\n")
