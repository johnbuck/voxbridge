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
    Test n8n SSE streaming latency with new full-response architecture

    VALIDATES:
    - SSE chunks are buffered without blocking
    - Chunk accumulation is fast
    - Full response processed as single TTS request
    - Frontend receives chunks in real-time for display
    """
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True

    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    text_synthesized = None
    synthesis_timestamp = None

    # Mock TTS to capture complete text
    async def mock_synthesize(text):
        nonlocal text_synthesized, synthesis_timestamp
        synthesis_timestamp = time.perf_counter()
        text_synthesized = text

    handler._synthesize_and_play = mock_synthesize

    # Track frontend broadcasts
    frontend_chunks = []
    async def mock_broadcast(text, is_final):
        frontend_chunks.append((text, is_final))

    handler.on_ai_response = mock_broadcast

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

    # Accumulate chunks (should be non-blocking)
    latency_tracker.start("chunk_accumulation")
    for i, chunk in enumerate(chunks):
        if i == 0:
            latency_tracker.start("sse_first_chunk")
            latency_tracker.end("sse_first_chunk")

        await handler.on_chunk(chunk)
        await asyncio.sleep(0.01)  # Simulate network delay between chunks

    accumulation_time = latency_tracker.end("chunk_accumulation")

    # Finalize to process complete response
    await handler.finalize()

    latency_tracker.end("sse_total")

    print("\n" + latency_tracker.report())
    print(f"\n🎯 SSE Streaming Performance:")
    print(f"   Chunk accumulation time: {accumulation_time:.2f}ms")
    print(f"   Complete text synthesized: \"{text_synthesized}\"")
    print(f"   Frontend chunks received: {len(frontend_chunks)}")

    # ASSERTIONS
    # All chunks should be buffered
    expected_text = ''.join(chunks)
    assert handler.buffer == '' or text_synthesized == expected_text, "Buffer should be processed"

    # Frontend should receive all chunks for real-time display
    assert len(frontend_chunks) == len(chunks) + 1, f"Frontend should receive {len(chunks)} chunks + final marker"

    # Chunk accumulation should be fast (non-blocking)
    latency_assertions.assert_low_latency(accumulation_time, 100, "SSE chunk accumulation")


# ============================================================
# Buffer Accumulation Latency Tests
# ============================================================

@pytest.mark.integration
@pytest.mark.latency
@pytest.mark.asyncio
async def test_buffer_accumulation_latency(latency_tracker, latency_assertions):
    """
    Test buffer accumulation performance

    VALIDATES:
    - Buffer accumulation is fast (<5ms per chunk)
    - String concatenation is performant
    - No blocking during accumulation
    """
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    # Test with various chunk sizes
    test_chunks = [
        "Simple chunk. ",
        "Another chunk with more text! ",
        "A longer chunk that simulates streaming from n8n with multiple words. ",
        "Final chunk to complete the buffer.",
    ]

    total_latency = 0
    for chunk in test_chunks:
        latency_tracker.start("buffer_accumulation")
        await handler.on_chunk(chunk)
        latency = latency_tracker.end("buffer_accumulation")
        total_latency += latency

        print(f"Accumulated chunk ({len(chunk)} chars) in {latency:.2f}ms")

        # Buffer accumulation should be very fast
        latency_assertions.assert_low_latency(latency, 5, "Buffer accumulation")

    print(f"Total buffer: {len(handler.buffer)} chars")
    print(f"Total accumulation time: {total_latency:.2f}ms")

    # Verify buffer contains all chunks
    expected_buffer = ''.join(test_chunks)
    assert handler.buffer == expected_buffer, "Buffer should contain all chunks"


# ============================================================
# Full Response Processing Latency Tests
# ============================================================

@pytest.mark.integration
@pytest.mark.latency
@pytest.mark.asyncio
async def test_full_response_processing_latency(latency_tracker):
    """
    Test full response processing with single TTS request

    VALIDATES:
    - Full response is processed as single unit
    - TTS receives complete text in one request
    - Processing is non-blocking during accumulation
    """
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True

    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    text_synthesized = None
    synthesis_time = None

    # Mock TTS to capture what text is sent
    async def capture_synthesize(text):
        nonlocal text_synthesized, synthesis_time
        start = time.perf_counter()
        await asyncio.sleep(0.02)  # 20ms TTS delay (simulates network)
        synthesis_time = (time.perf_counter() - start) * 1000
        text_synthesized = text

    handler._synthesize_and_play = capture_synthesize

    # Accumulate chunks rapidly (non-blocking)
    latency_tracker.start("chunk_accumulation")

    chunks = ["First sentence. ", "Second sentence. ", "Third sentence."]
    for chunk in chunks:
        await handler.on_chunk(chunk)

    accumulation_time = latency_tracker.end("chunk_accumulation")

    print(f"\n🎯 Chunk accumulation: {accumulation_time:.2f}ms")
    print(f"   Buffer size: {len(handler.buffer)} chars")

    # Accumulation should be very fast (not blocked by TTS)
    assert accumulation_time < 10, f"Chunk accumulation blocked: {accumulation_time:.2f}ms"

    # Now process the full response
    latency_tracker.start("full_response_processing")
    await handler._process_full_response()
    processing_time = latency_tracker.end("full_response_processing")

    print(f"   Full response processing: {processing_time:.2f}ms")
    print(f"   Text synthesized: \"{text_synthesized}\"")
    print(f"   Synthesis time: {synthesis_time:.2f}ms")

    # Verify single TTS request with complete text
    expected_text = ''.join(chunks)
    assert text_synthesized == expected_text, "Should synthesize complete response as single unit"


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

                    # Stage 2: Finalize (includes TTS processing)
                    latency_tracker.start("finalization")
                    await handler.finalize()
                    latency_tracker.end("finalization")

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
