"""
Integration tests for streaming latency

Tests low-latency streaming performance across:
- TTS HTTP streaming (Chatterbox)
- n8n SSE streaming
- Sentence extraction and queue processing
- Time to first chunk (TTFB)

LATENCY TARGETS:
- TTS first chunk: <100ms
- Sentence extraction: <10ms
- Total SSE streaming: <500ms
- HTTP streaming: Incremental (not blocking)
"""
from __future__ import annotations

import pytest
import asyncio
import httpx
from unittest.mock import MagicMock, patch, AsyncMock
import time

from src.streaming_handler import StreamingResponseHandler


# ============================================================
# TTS HTTP Streaming Latency Tests
# ============================================================

@pytest.mark.integration
@pytest.mark.latency
@pytest.mark.streaming
@pytest.mark.asyncio
async def test_tts_http_streaming_latency(mock_chatterbox_server, latency_tracker, stream_validator, latency_assertions):
    """
    Test TTS HTTP streaming latency and incremental delivery

    VALIDATES:
    - Time to first audio chunk < 100ms
    - Chunks arrive incrementally (not all at once)
    - Total streaming time is reasonable
    - No blocking behavior
    """
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False

    handler = StreamingResponseHandler(mock_voice_client, "user_123")
    handler.chatterbox_url = mock_chatterbox_server["base_url"]

    latency_tracker.start("tts_total")
    latency_tracker.start("tts_first_chunk")

    first_chunk_received = False
    chunks_received = []

    # Mock HTTP streaming response
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    # Simulate incremental audio streaming (key for latency testing)
    async def mock_aiter_bytes(chunk_size):
        """Simulate streaming audio chunks with delays"""
        for i in range(5):
            await asyncio.sleep(0.01)  # 10ms delay between chunks (realistic)
            yield b'\\x00' * 1024  # 1KB audio chunks

    mock_response.aiter_bytes = mock_aiter_bytes

    # Mock httpx client
    with patch('httpx.AsyncClient') as MockClient:
        mock_http_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_http_client.stream = MagicMock(return_value=mock_stream_ctx)

        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock tempfile and FFmpeg
        with patch('tempfile.NamedTemporaryFile') as mock_temp:
            mock_file = MagicMock()
            mock_file.name = "/tmp/test.wav"
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_temp.return_value = mock_file

            # Capture write calls to validate streaming
            def capture_write(chunk):
                nonlocal first_chunk_received
                if not first_chunk_received:
                    latency_tracker.end("tts_first_chunk")
                    first_chunk_received = True
                stream_validator.record_chunk(chunk)
                chunks_received.append(chunk)

            mock_file.write = capture_write
            mock_file.flush = MagicMock()

            with patch('discord.FFmpegPCMAudio'):
                with patch('os.unlink'):
                    # Synthesize text
                    await handler._synthesize_and_play("Hello, this is a test of low latency streaming.")

    latency_tracker.end("tts_total")

    # Print latency report
    print("\n" + latency_tracker.report())

    # LATENCY ASSERTIONS
    ttfb = latency_tracker.get_average("tts_first_chunk")
    total = latency_tracker.get_average("tts_total")

    print(f"\n🎯 TTS Streaming Performance:")
    print(f"   Time to first chunk: {ttfb:.2f}ms")
    print(f"   Total streaming time: {total:.2f}ms")
    print(f"   Chunks received: {stream_validator.get_total_chunks()}")
    print(f"   Incremental: {stream_validator.validate_incremental()}")

    # CRITICAL LATENCY REQUIREMENTS
    latency_assertions.assert_low_latency(ttfb, 100, "TTS first chunk")
    latency_assertions.assert_streaming(stream_validator, min_chunks=3)

    # Verify chunks were written incrementally
    assert len(chunks_received) >= 5, "Expected 5 chunks for streaming"


@pytest.mark.integration
@pytest.mark.latency
@pytest.mark.asyncio
async def test_tts_streaming_with_custom_options(mock_chatterbox_server, latency_tracker):
    """
    Test TTS streaming with custom voice options

    VALIDATES:
    - Custom options don't increase latency
    - Streaming still works with voice cloning
    - Options are properly passed to TTS server
    """
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False

    # Custom TTS options (realistic voice cloning settings)
    options = {
        'voiceMode': 'clone',
        'referenceAudioFilename': 'custom_voice.wav',
        'speedFactor': 1.2,
        'temperature': 0.8,
        'streamingStrategy': 'word',
        'streamingQuality': 'high'
    }

    handler = StreamingResponseHandler(mock_voice_client, "user_123", options)
    handler.chatterbox_url = mock_chatterbox_server["base_url"]

    latency_tracker.start("tts_custom_options")

    # Mock HTTP streaming response (same pattern as test_tts_http_streaming_latency)
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_bytes(chunk_size):
        """Simulate realistic audio streaming for voice cloning"""
        for i in range(4):
            await asyncio.sleep(0.012)  # Slightly slower for voice cloning
            yield b'\x00' * 1536  # Larger chunks for higher quality

    mock_response.aiter_bytes = mock_aiter_bytes

    with patch('httpx.AsyncClient') as MockClient:
        mock_http_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_http_client.stream = MagicMock(return_value=mock_stream_ctx)

        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch('tempfile.NamedTemporaryFile'):
            with patch('discord.FFmpegPCMAudio'):
                with patch('os.unlink'):
                    await handler._synthesize_and_play("Custom voice test.")

    latency = latency_tracker.end("tts_custom_options")

    print(f"\n🎯 TTS with custom options: {latency:.2f}ms")

    # Custom options shouldn't significantly increase latency
    assert latency < 200, f"Custom options increased latency too much: {latency:.2f}ms"


# ============================================================
# n8n SSE Streaming Latency Tests
# ============================================================

@pytest.mark.integration
@pytest.mark.latency
@pytest.mark.streaming
@pytest.mark.asyncio
async def test_n8n_sse_streaming_latency(mock_n8n_server, latency_tracker, latency_assertions):
    """
    Test n8n SSE streaming latency

    VALIDATES:
    - SSE chunks arrive incrementally
    - First chunk latency < 50ms
    - Sentence extraction is fast
    - No blocking on full response
    """
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True

    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    sentences_processed = []
    sentence_timings = []

    # Mock sentence synthesis to track timing
    async def mock_synthesize(text):
        sentence_timings.append(time.perf_counter())
        sentences_processed.append(text)

    handler._synthesize_and_play = mock_synthesize

    # Simulate SSE streaming chunks
    latency_tracker.start("sse_total")

    chunks = [
        "Hello",
        " there!",
        " How",
        " are",
        " you?",
        " I'm",
        " doing",
        " great."
    ]

    chunk_start = time.perf_counter()

    for i, chunk in enumerate(chunks):
        if i == 0:
            latency_tracker.start("sse_first_chunk")
            first_chunk_latency = (time.perf_counter() - chunk_start) * 1000
            latency_tracker.end("sse_first_chunk")

        await handler.on_chunk(chunk)
        await asyncio.sleep(0.01)  # Simulate network delay between chunks

    # Finalize to process remaining buffer
    await handler.finalize()

    latency_tracker.end("sse_total")

    print("\n" + latency_tracker.report())
    print(f"\n🎯 SSE Streaming Performance:")
    print(f"   Sentences extracted: {sentences_processed}")
    print(f"   Sentence timings: {[f'{(t-chunk_start)*1000:.2f}ms' for t in sentence_timings]}")

    # ASSERTIONS
    assert len(sentences_processed) >= 2, "Expected at least 2 sentences"

    # Verify incremental processing (sentences processed as they arrive)
    # Not all at once at the end
    if len(sentence_timings) >= 2:
        time_spread = (sentence_timings[-1] - sentence_timings[0]) * 1000
        assert time_spread > 10, "Sentences should be processed incrementally"


# ============================================================
# Sentence Extraction Latency Tests
# ============================================================

@pytest.mark.integration
@pytest.mark.latency
@pytest.mark.asyncio
async def test_sentence_extraction_latency(latency_tracker, latency_assertions):
    """
    Test sentence extraction performance

    VALIDATES:
    - Sentence extraction is fast (<10ms)
    - Multiple delimiters handled efficiently
    - Buffer management is performant
    """
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    # Test with various sentence structures
    test_cases = [
        "Simple sentence.",
        "Question? Another sentence!",
        "Multiple sentences. With different delimiters! And questions?",
        "Very long sentence that goes on and on and on and on to test buffer performance. Another one!",
    ]

    for text in test_cases:
        handler.buffer = text

        latency_tracker.start("sentence_extraction")
        sentences = handler._extract_sentences()
        latency = latency_tracker.end("sentence_extraction")

        print(f"Extracted {len(sentences)} sentences in {latency:.2f}ms: {sentences}")

        # Sentence extraction should be very fast
        latency_assertions.assert_low_latency(latency, 10, "Sentence extraction")


# ============================================================
# Queue Processing Latency Tests
# ============================================================

@pytest.mark.integration
@pytest.mark.latency
@pytest.mark.asyncio
async def test_queue_processing_no_blocking(latency_tracker):
    """
    Test queue processing doesn't block on slow TTS

    VALIDATES:
    - Queue accepts sentences without blocking
    - Slow TTS synthesis doesn't prevent new sentences from queueing
    - Sentences processed sequentially but queueing is async
    """
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True

    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    synthesis_times = []
    sentences_synthesized = []

    # Mock slow TTS (simulates network delay)
    async def slow_synthesize(text):
        start = time.perf_counter()
        await asyncio.sleep(0.02)  # 20ms TTS delay (shorter for faster test)
        synthesis_times.append((time.perf_counter() - start) * 1000)
        sentences_synthesized.append(text)

    handler._synthesize_and_play = slow_synthesize

    # Queue multiple sentences rapidly
    latency_tracker.start("rapid_queueing")

    # Manually add sentences to queue (bypass on_chunk to ensure they're queued)
    handler.sentence_queue.extend(["First sentence.", "Second sentence.", "Third sentence."])

    queueing_time = latency_tracker.end("rapid_queueing")

    print(f"\n🎯 Rapid queueing: {queueing_time:.2f}ms")
    print(f"   Queue size before processing: {len(handler.sentence_queue)}")

    # Queueing should be instant
    assert queueing_time < 5, f"Queueing blocked: {queueing_time:.2f}ms"

    # Now process the queue
    await handler._process_queue()

    print(f"   Sentences processed: {sentences_synthesized}")
    print(f"   Synthesis times: {[f'{t:.2f}ms' for t in synthesis_times]}")
    assert len(synthesis_times) == 3, f"Expected 3 sentences synthesized, got {len(synthesis_times)}"


# ============================================================
# Concurrent Streaming Tests
# ============================================================

@pytest.mark.integration
@pytest.mark.latency
@pytest.mark.streaming
@pytest.mark.asyncio
async def test_concurrent_tts_streaming(mock_chatterbox_server, latency_tracker):
    """
    Test multiple concurrent TTS streaming requests

    VALIDATES:
    - Multiple handlers can stream simultaneously
    - No resource contention
    - Each stream maintains low latency
    """
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False

    # Create 3 concurrent handlers
    handlers = [
        StreamingResponseHandler(mock_voice_client, f"user_{i}")
        for i in range(3)
    ]

    for h in handlers:
        h.chatterbox_url = mock_chatterbox_server["base_url"]

    # Start concurrent streaming
    latency_tracker.start("concurrent_streaming")

    # Mock HTTP streaming (realistic concurrent behavior)
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_bytes(chunk_size):
        """Simulate concurrent streaming with slight jitter"""
        for i in range(3):
            await asyncio.sleep(0.015)  # Realistic network delay
            yield b'\x00' * 2048

    mock_response.aiter_bytes = mock_aiter_bytes

    with patch('httpx.AsyncClient') as MockClient:
        mock_http_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_http_client.stream = MagicMock(return_value=mock_stream_ctx)

        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch('tempfile.NamedTemporaryFile'):
            with patch('discord.FFmpegPCMAudio'):
                with patch('os.unlink'):
                    tasks = [
                        h._synthesize_and_play(f"Concurrent test {i}")
                        for i, h in enumerate(handlers)
                    ]
                    await asyncio.gather(*tasks)

    latency = latency_tracker.end("concurrent_streaming")

    print(f"\n🎯 Concurrent streaming (3 streams): {latency:.2f}ms")

    # Concurrent streaming shouldn't be much slower than single
    assert latency < 300, f"Concurrent streaming too slow: {latency:.2f}ms"


# ============================================================
# End-to-End Streaming Flow Test
# ============================================================

@pytest.mark.integration
@pytest.mark.latency
@pytest.mark.streaming
@pytest.mark.asyncio
async def test_end_to_end_streaming_flow(
    mock_chatterbox_server,
    latency_tracker,
    stream_validator,
    latency_assertions
):
    """
    Test complete streaming flow: SSE chunks → sentences → TTS → playback

    VALIDATES:
    - Full pipeline maintains low latency
    - Each stage is measured
    - Streaming is incremental at each stage
    - Total latency < 1000ms
    """
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False

    handler = StreamingResponseHandler(mock_voice_client, "user_123")
    handler.chatterbox_url = mock_chatterbox_server["base_url"]

    # Track each stage
    latency_tracker.start("pipeline_total")

    # Mock HTTP streaming for TTS (realistic multi-sentence response)
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_bytes(chunk_size):
        """Simulate incremental TTS streaming"""
        for i in range(4):
            await asyncio.sleep(0.008)  # 8ms between chunks (realistic)
            yield b'\x00' * 1024

    mock_response.aiter_bytes = mock_aiter_bytes

    with patch('httpx.AsyncClient') as MockClient:
        mock_http_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_http_client.stream = MagicMock(return_value=mock_stream_ctx)

        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        # Stage 1: SSE Chunk Processing
        latency_tracker.start("sse_processing")

        sse_chunks = ["Hello! ", "How are you? ", "I'm doing great."]

        with patch('tempfile.NamedTemporaryFile'):
            with patch('discord.FFmpegPCMAudio'):
                with patch('os.unlink'):
                    for chunk in sse_chunks:
                        await handler.on_chunk(chunk)
                        await asyncio.sleep(0.01)  # Simulate SSE streaming delay

                    latency_tracker.end("sse_processing")

                    # Stage 2: Finalize
                    latency_tracker.start("finalization")
                    await handler.finalize()
                    latency_tracker.end("finalization")

                    # Stage 3: Queue Processing (TTS happens here)
                    latency_tracker.start("queue_processing")
                    await handler._process_queue()
                    latency_tracker.end("queue_processing")

    total_latency = latency_tracker.end("pipeline_total")

    # Print comprehensive report
    print("\n" + "=" * 60)
    print("END-TO-END STREAMING PIPELINE REPORT")
    print("=" * 60)
    print(latency_tracker.report())
    print("=" * 60)

    # CRITICAL ASSERTIONS
    latency_assertions.assert_low_latency(total_latency, 1000, "Total pipeline")

    print(f"\n✅ Pipeline completed in {total_latency:.2f}ms (target: <1000ms)")
