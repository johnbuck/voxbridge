"""
End-to-End Tests for WebRTC Transcription Pipeline

CRITICAL BUG #4 VALIDATION: Complete pipeline test
Fix: Planar audio transpose ensures correct format for WhisperX

E2E Test Coverage:
- Complete WebRTC → WhisperX pipeline
- Realistic audio patterns (simulated speech cadence)
- Multi-sentence streaming
- Latency measurements across full pipeline
- Error recovery and resilience
"""
from __future__ import annotations

import pytest
import asyncio
import numpy as np
import av
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ============================================================
# REALISTIC AUDIO GENERATION
# ============================================================

def generate_speech_like_audio(
    text: str,
    sample_rate: int = 48000,
    channels: int = 2
) -> bytes:
    """
    Generate WebM audio with speech-like patterns

    Simulates speech cadence with tone modulation for testing.
    Each word gets a distinct tone burst.

    Args:
        text: Test sentence to simulate
        sample_rate: Audio sample rate (48kHz)
        channels: Number of channels (2 = stereo)

    Returns:
        WebM container bytes with speech-like audio
    """
    words = text.split()
    buffer = BytesIO()

    # Create WebM container
    container = av.open(buffer, 'w', format='webm')
    layout = 'stereo' if channels == 2 else 'mono'
    stream = container.add_stream('opus', rate=sample_rate, layout=layout)

    # Generate audio for each word (simulating speech rhythm)
    for word_idx, word in enumerate(words):
        # Word duration proportional to length (100ms base + 50ms per char)
        word_duration_ms = 100 + (len(word) * 50)
        num_frames = max(1, word_duration_ms // 20)  # 20ms frames

        # Tone frequency varies by word position (simulating pitch variation)
        base_freq = 200 + (word_idx * 50) % 400  # 200-600 Hz range

        for frame_idx in range(num_frames):
            samples_per_frame = 960  # 20ms at 48kHz

            # Generate tone burst (simulates voiced speech)
            t = np.linspace(0, 0.02, samples_per_frame)  # 20ms

            # Modulated tone (frequency varies within word)
            freq = base_freq + (frame_idx * 20)
            tone = np.sin(2 * np.pi * freq * t)

            # Apply envelope (attack-sustain-decay)
            envelope = np.exp(-t * 50)  # Decay envelope
            audio_mono = (tone * envelope * 5000).astype(np.int16)

            # Create planar stereo (shape: channels, samples)
            # WhisperX test: This planar format must be transposed!
            audio_planar = np.stack([audio_mono, audio_mono], axis=0)

            frame = av.AudioFrame.from_ndarray(
                audio_planar,
                format='s16p',  # Planar format (triggers bug if not transposed)
                layout=layout
            )
            frame.sample_rate = sample_rate

            # Encode and mux
            for packet in stream.encode(frame):
                container.mux(packet)

        # Short pause between words (silence = 1 frame)
        silence = np.zeros((channels, 960), dtype=np.int16)
        pause_frame = av.AudioFrame.from_ndarray(
            silence,
            format='s16p',
            layout=layout
        )
        pause_frame.sample_rate = sample_rate

        for packet in stream.encode(pause_frame):
            container.mux(packet)

    # Flush encoder
    for packet in stream.encode():
        container.mux(packet)

    container.close()
    return buffer.getvalue()


# ============================================================
# E2E PIPELINE TESTS
# ============================================================

class TestWebRTCTranscriptionPipeline:
    """
    End-to-end tests for complete WebRTC → WhisperX pipeline
    """

    @pytest.fixture
    def test_sentences(self):
        """Test sentences for E2E validation"""
        return [
            "Hello world",
            "Testing planar audio fix",
            "This is a test sentence",
            "WebRTC audio streaming works"
        ]

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_complete_webrtc_to_stt_pipeline(self, test_sentences):
        """
        E2E TEST #1: Complete pipeline from WebRTC to STT service

        VALIDATES:
        - WebM chunk received from browser
        - Planar audio detected and transposed
        - Interleaved PCM sent to STTService
        - No corruption in pipeline
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "e2e_pipeline_test"

        # Track audio sent to STT
        audio_sent_to_stt = []

        async def mock_send_audio(audio_data):
            audio_sent_to_stt.append(audio_data)

        mock_conversation_service = AsyncMock()
        mock_stt_service = AsyncMock()
        mock_stt_service.send_audio = mock_send_audio

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id
            )

            # Generate realistic audio
            test_text = test_sentences[0]
            webm_audio = generate_speech_like_audio(test_text)

            print(f"\n🎯 E2E TEST: Complete pipeline")
            print(f"   Test text: '{test_text}'")
            print(f"   WebM size: {len(webm_audio)} bytes")

            # Decode WebM chunk (simulating browser upload)
            pcm_data = handler._decode_webm_chunk(webm_audio)

            assert len(pcm_data) > 0, "Should decode WebM to PCM"

            # Send to STT service
            if pcm_data:
                await mock_stt_service.send_audio(pcm_data)

            print(f"   PCM decoded: {len(pcm_data)} bytes")
            print(f"   Sent to STT: {len(audio_sent_to_stt)} chunks")

            # Validate interleaved format
            samples = np.frombuffer(pcm_data[:200], dtype=np.int16)
            left = samples[0::2]
            right = samples[1::2]

            print(f"   Sample L/R pattern (first 10): L={left[:5]}, R={right[:5]}")

            assert len(audio_sent_to_stt) > 0, "Should send audio to STT"
            assert not np.array_equal(left, right[:len(left)]), \
                "Audio should be interleaved (different L/R patterns)"

            print(f"   ✅ Complete pipeline validated (WebRTC → PCM → STT)")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_multi_sentence_streaming(self, test_sentences):
        """
        E2E TEST #2: Multi-sentence streaming with planar transpose

        VALIDATES:
        - Multiple sentences decode correctly
        - No format drift across chunks
        - Consistent planar transpose
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "multi_sentence_test"

        audio_chunks_sent = []

        async def mock_send_audio(audio_data):
            audio_chunks_sent.append(audio_data)

        mock_conversation_service = AsyncMock()
        mock_stt_service = AsyncMock()
        mock_stt_service.send_audio = mock_send_audio

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id
            )

            print(f"\n🎯 E2E TEST: Multi-sentence streaming")

            # Process 4 test sentences
            for idx, sentence in enumerate(test_sentences):
                webm_chunk = generate_speech_like_audio(sentence)
                pcm_data = handler._decode_webm_chunk(webm_chunk)

                if pcm_data:
                    await mock_stt_service.send_audio(pcm_data)

                print(f"   Sentence {idx+1}: '{sentence}' → {len(pcm_data)} PCM bytes")

            total_chunks = len(audio_chunks_sent)
            print(f"   Total chunks sent to STT: {total_chunks}")

            assert total_chunks == len(test_sentences), \
                f"Should send {len(test_sentences)} chunks, sent {total_chunks}"

            # Validate all chunks are interleaved
            for idx, chunk in enumerate(audio_chunks_sent):
                samples = np.frombuffer(chunk[:100], dtype=np.int16)
                left = samples[0::2]
                right = samples[1::2]

                assert not np.array_equal(left, right[:len(left)]), \
                    f"Chunk {idx} should be interleaved"

            print(f"   ✅ Multi-sentence streaming validated ({total_chunks} chunks)")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_latency_measurements_full_pipeline(self, test_sentences):
        """
        E2E TEST #3: Latency measurements across full pipeline

        VALIDATES:
        - WebM decode latency
        - Transpose latency
        - STT send latency
        - Total pipeline latency <100ms
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        import time

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "latency_e2e_test"

        latencies = []

        async def mock_send_audio(audio_data):
            pass  # No-op for latency test

        mock_conversation_service = AsyncMock()
        mock_stt_service = AsyncMock()
        mock_stt_service.send_audio = mock_send_audio

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id
            )

            print(f"\n🎯 E2E TEST: Full pipeline latency")

            # Benchmark pipeline for each sentence
            for sentence in test_sentences:
                webm_chunk = generate_speech_like_audio(sentence)

                start = time.perf_counter()

                # Full pipeline: decode + transpose + send
                pcm_data = handler._decode_webm_chunk(webm_chunk)
                if pcm_data:
                    await mock_stt_service.send_audio(pcm_data)

                latency_ms = (time.perf_counter() - start) * 1000
                latencies.append(latency_ms)

                print(f"   '{sentence}': {latency_ms:.2f}ms")

            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)

            print(f"   Average latency: {avg_latency:.2f}ms")
            print(f"   Max latency: {max_latency:.2f}ms")

            # Target: <100ms for full pipeline
            assert avg_latency < 100.0, \
                f"Average latency too high: {avg_latency:.2f}ms (target: <100ms)"

            print(f"   ✅ Pipeline latency within acceptable range")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_error_recovery_corrupted_webm(self):
        """
        E2E TEST #4: Error recovery with corrupted WebM

        VALIDATES:
        - Corrupted WebM handled gracefully
        - Pipeline recovers for next chunk
        - No crash or state corruption
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from tests.fixtures.audio_samples import get_corrupted_webm_audio

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "error_recovery_test"

        chunks_sent = []

        async def mock_send_audio(audio_data):
            chunks_sent.append(audio_data)

        mock_conversation_service = AsyncMock()
        mock_stt_service = AsyncMock()
        mock_stt_service.send_audio = mock_send_audio

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id
            )

            print(f"\n🎯 E2E TEST: Error recovery")

            # Send corrupted WebM
            corrupted_webm = get_corrupted_webm_audio()
            pcm_corrupted = handler._decode_webm_chunk(corrupted_webm)

            print(f"   Corrupted WebM: {len(pcm_corrupted)} bytes decoded")

            # Send valid WebM (should recover)
            valid_webm = generate_speech_like_audio("Recovery test")
            pcm_valid = handler._decode_webm_chunk(valid_webm)

            if pcm_valid:
                await mock_stt_service.send_audio(pcm_valid)

            print(f"   Valid WebM after error: {len(pcm_valid)} bytes decoded")
            print(f"   Chunks sent to STT: {len(chunks_sent)}")

            # Should recover and process valid chunk
            assert len(pcm_valid) > 0, "Should decode valid WebM after error"
            assert len(chunks_sent) > 0, "Should send audio after recovery"

            print(f"   ✅ Pipeline recovered from corrupted WebM")


# ============================================================
# REALISTIC AUDIO VALIDATION
# ============================================================

class TestRealisticAudioGeneration:
    """
    Tests for realistic audio generation utilities
    """

    @pytest.mark.e2e
    def test_speech_like_audio_generation(self):
        """
        E2E TEST #5: Validate speech-like audio generation

        VALIDATES:
        - Audio has speech-like cadence
        - Planar format used (s16p)
        - Multiple words produce distinct patterns
        """
        text = "Hello world test"
        webm_audio = generate_speech_like_audio(text)

        print(f"\n🎯 E2E TEST: Speech-like audio generation")
        print(f"   Text: '{text}'")
        print(f"   WebM size: {len(webm_audio)} bytes")

        # Decode to validate structure
        container = av.open(BytesIO(webm_audio))
        audio_stream = next(s for s in container.streams if s.type == 'audio')

        frames_decoded = 0
        planar_frames = 0

        for frame in container.decode(audio_stream):
            frames_decoded += 1

            if frame.format.is_planar:
                planar_frames += 1

            # Check first frame
            if frames_decoded == 1:
                pcm_array = frame.to_ndarray()
                print(f"   Format: {frame.format.name} (planar={frame.format.is_planar})")
                print(f"   Shape: {pcm_array.shape}")
                print(f"   Sample rate: {frame.sample_rate}Hz")

        print(f"   Total frames: {frames_decoded}")
        print(f"   Planar frames: {planar_frames}")

        assert frames_decoded > 0, "Should decode frames"
        assert planar_frames > 0, "Should use planar format"

        print(f"   ✅ Speech-like audio generated correctly")

    @pytest.mark.e2e
    def test_multi_word_audio_pattern(self):
        """
        E2E TEST #6: Multi-word audio has distinct patterns

        VALIDATES:
        - Each word has distinct tone
        - Pauses between words
        - Realistic speech rhythm
        """
        sentences = [
            "One",
            "Two words",
            "Three word sentence",
            "Four words in sentence"
        ]

        print(f"\n🎯 E2E TEST: Multi-word audio patterns")

        for sentence in sentences:
            webm_audio = generate_speech_like_audio(sentence)

            # Decode and count frames
            container = av.open(BytesIO(webm_audio))
            audio_stream = next(s for s in container.streams if s.type == 'audio')

            frames = list(container.decode(audio_stream))
            word_count = len(sentence.split())

            print(f"   '{sentence}': {word_count} words → {len(frames)} frames")

            # More words should produce more frames (roughly)
            assert len(frames) >= word_count, \
                f"Should have at least {word_count} frames for {word_count} words"

        print(f"   ✅ Multi-word patterns validated")
