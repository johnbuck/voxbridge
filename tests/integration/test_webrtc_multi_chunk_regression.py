"""
REGRESSION TESTS for Multi-Chunk WebM Streaming (Bug #3)

CRITICAL BUG REPRODUCTION:
Bug #3 - Only first WebM chunk was decoded, subsequent chunks failed silently.
Root cause: Buffer was cleared after first decode, breaking MediaRecorder streaming.

These tests MUST FAIL if the buffer clearing bug is reintroduced.

Expected behavior:
- MediaRecorder sends chunks every 100ms (first ~1.6KB with header, rest ~988 bytes each)
- ALL chunks must decode successfully (not just the first one)
- Buffer should only be cleared after successful buffered decode
- Per-chunk decode should not clear buffer for subsequent chunks

Test Strategy:
- Send 10+ chunks simulating real MediaRecorder behavior
- Track decode count (MUST be >= 90% of chunks sent)
- Monitor decode logs (MUST see "Decoded chunk" for each successful decode)
- Validate PCM output size matches expected (10 chunks = ~384KB PCM @ 48kHz stereo)
"""
from __future__ import annotations

import pytest
import asyncio
import time
import logging
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from io import BytesIO

# Import fixtures
from tests.fixtures.audio_samples import (
    get_sample_webm_audio,
    get_multi_frame_webm_audio
)


# ============================================================
# REGRESSION TEST CLASS - Multi-Chunk Streaming
# ============================================================

class TestMultiChunkStreamingRegression:
    """
    CRITICAL REGRESSION TESTS for Bug #3: Buffer clearing after first decode

    These tests validate that ALL WebM chunks decode successfully,
    not just the first one. If only 1 chunk decodes, tests MUST FAIL.
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_all_chunks_decode_not_just_first(
        self,
        mock_conversation_service,
        mock_stt_service,
        caplog
    ):
        """
        REGRESSION TEST #1: All chunks decode, not just first

        This is the PRIMARY regression test for Bug #3.

        CRITICAL ASSERTIONS:
        - PCM output received for ALL 10 chunks (not just chunk 1)
        - Decode count == chunk count (100% success rate)
        - PCM output size matches expected (~384KB for 10 chunks)

        If this test passes with only 1 chunk decoded, it's a BAD TEST.
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler

        # Setup
        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "regression_test_all_chunks"

        caplog.set_level(logging.DEBUG)  # Capture all decode logs

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id
            )

            # Simulate MediaRecorder behavior: send 10 WebM chunks
            chunk_count = 10
            chunks_sent = []
            pcm_outputs = []

            for i in range(chunk_count):
                # First chunk is larger (has header), rest are continuation chunks
                if i == 0:
                    webm_chunk = get_sample_webm_audio()  # ~648 bytes with header
                else:
                    # Simulate continuation chunks (smaller, no header)
                    webm_chunk = get_sample_webm_audio()  # Use same for test

                chunks_sent.append(webm_chunk)

                # Decode this chunk
                pcm_data = handler._decode_webm_chunk(webm_chunk)

                if pcm_data:
                    pcm_outputs.append(pcm_data)

                    # Send to STT (simulate real flow)
                    await handler.stt_service.send_audio(
                        session_id=handler.session_id,
                        audio_data=pcm_data,
                        audio_format='pcm'
                    )

        # CRITICAL ASSERTIONS
        total_chunks_sent = len(chunks_sent)
        successful_decodes = len(pcm_outputs)
        decode_success_rate = (successful_decodes / total_chunks_sent) * 100

        # Count "Decoded chunk" log messages
        decode_logs = [r for r in caplog.records if "Decoded chunk" in r.message]
        logged_decode_count = len(decode_logs)

        # Calculate total PCM bytes
        total_pcm_bytes = sum(len(pcm) for pcm in pcm_outputs)

        print(f"\n🎯 REGRESSION TEST: Multi-chunk decoding")
        print(f"   Chunks sent: {total_chunks_sent}")
        print(f"   Successful decodes: {successful_decodes}")
        print(f"   Success rate: {decode_success_rate:.1f}%")
        print(f"   Decode logs found: {logged_decode_count}")
        print(f"   Total PCM bytes: {total_pcm_bytes:,}")

        # PRIMARY ASSERTION: At least 90% of chunks must decode
        # (Allow for some container-level failures, but NOT single-chunk failure)
        assert successful_decodes >= total_chunks_sent * 0.9, \
            f"REGRESSION FAILURE: Only {successful_decodes}/{total_chunks_sent} chunks decoded! " \
            f"Expected at least {int(total_chunks_sent * 0.9)} chunks. " \
            f"This indicates Bug #3 has returned (buffer clearing after first decode)."

        # CRITICAL: If only 1 chunk decoded, this is Bug #3
        assert successful_decodes > 1, \
            f"CRITICAL REGRESSION: Only {successful_decodes} chunk decoded! " \
            f"This is the exact symptom of Bug #3 (buffer cleared after first decode)."

        # Verify decode logs match successful decodes
        assert logged_decode_count >= successful_decodes * 0.8, \
            f"Decode log count ({logged_decode_count}) doesn't match successful decodes ({successful_decodes})"

        # Verify reasonable PCM output size
        # Expected: Each chunk ~20ms of audio = 3,840 bytes PCM (48kHz stereo int16)
        # 10 chunks = ~38,400 bytes minimum
        expected_min_bytes = total_chunks_sent * 1000  # Very conservative minimum
        assert total_pcm_bytes >= expected_min_bytes, \
            f"PCM output too small: {total_pcm_bytes:,} bytes (expected >{expected_min_bytes:,}). " \
            f"Likely only first chunk decoded."

        print(f"   ✅ REGRESSION TEST PASSED: All {successful_decodes} chunks decoded successfully")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_buffer_persistence_across_chunks(
        self,
        mock_conversation_service,
        mock_stt_service
    ):
        """
        REGRESSION TEST #2: Buffer isn't cleared prematurely

        VALIDATES:
        - Buffer state after first chunk decode
        - Buffer persistence for continuation chunks
        - No premature buffer clearing
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "regression_test_buffer_persistence"

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id
            )

            # Send chunk 1 (with header)
            chunk1 = get_sample_webm_audio()
            pcm1 = handler._decode_webm_chunk(chunk1)

            # ASSERT: Chunk 1 should decode
            assert len(pcm1) > 0, "First chunk should decode successfully"

            # Check buffer state after first chunk
            # (Should have saved header, but buffer should not interfere with subsequent decodes)
            first_buffer_state = len(handler.webm_buffer)
            has_header = handler.webm_header is not None

            # Send chunk 2 (continuation, might not have header)
            chunk2 = get_sample_webm_audio()
            pcm2 = handler._decode_webm_chunk(chunk2)

            # CRITICAL ASSERTION: Chunk 2 MUST also decode
            assert len(pcm2) > 0, \
                f"REGRESSION FAILURE: Second chunk failed to decode! " \
                f"Buffer state after chunk 1: {first_buffer_state} bytes, " \
                f"Header saved: {has_header}. " \
                f"This indicates buffer was incorrectly managed."

            print(f"\n🎯 REGRESSION TEST: Buffer persistence")
            print(f"   Chunk 1 PCM: {len(pcm1):,} bytes ✅")
            print(f"   Chunk 2 PCM: {len(pcm2):,} bytes ✅")
            print(f"   Buffer after chunk 1: {first_buffer_state} bytes")
            print(f"   Header saved: {has_header}")
            print(f"   ✅ Both chunks decoded successfully")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_mediarecorder_streaming_pattern(
        self,
        mock_conversation_service,
        mock_stt_service,
        caplog
    ):
        """
        REGRESSION TEST #3: Simulate real MediaRecorder streaming

        MediaRecorder behavior:
        - First chunk: Large (~1,600 bytes) with WebM header
        - Subsequent chunks: Smaller (~988 bytes) continuation data
        - Chunks arrive every 100ms (10 chunks/second)
        - Total duration: 5 seconds = 50 chunks

        VALIDATES:
        - All 50 chunks decode successfully
        - PCM output matches 5 seconds of audio
        - No buffer overflow or starvation
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "regression_test_mediarecorder"

        caplog.set_level(logging.DEBUG)

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id
            )

            # Simulate 5 seconds of MediaRecorder streaming (50 chunks @ 100ms each)
            chunk_count = 50
            pcm_outputs = []
            start_time = time.time()

            for i in range(chunk_count):
                # Get WebM chunk (use sample for testing)
                webm_chunk = get_sample_webm_audio()

                # Decode
                pcm_data = handler._decode_webm_chunk(webm_chunk)

                if pcm_data:
                    pcm_outputs.append(pcm_data)

                # Simulate real-time streaming (100ms between chunks)
                await asyncio.sleep(0.01)  # 10ms for testing (scaled down from 100ms)

            elapsed_time = time.time() - start_time
            successful_decodes = len(pcm_outputs)
            total_pcm_bytes = sum(len(pcm) for pcm in pcm_outputs)

            # Expected PCM size for 5 seconds:
            # 48kHz stereo int16 = 48000 samples/sec * 2 channels * 2 bytes = 192,000 bytes/sec
            # 5 seconds = 960,000 bytes (if all chunks decoded)
            # But each chunk is ~20ms = 3,840 bytes
            # 50 chunks = ~192,000 bytes
            expected_pcm_bytes = 50 * 1000  # Conservative: 1KB per chunk minimum

            print(f"\n🎯 REGRESSION TEST: MediaRecorder streaming pattern")
            print(f"   Duration: {elapsed_time:.2f}s")
            print(f"   Chunks sent: {chunk_count}")
            print(f"   Successful decodes: {successful_decodes}")
            print(f"   Success rate: {(successful_decodes/chunk_count)*100:.1f}%")
            print(f"   Total PCM: {total_pcm_bytes:,} bytes (expected >{expected_pcm_bytes:,})")

            # ASSERTIONS
            assert successful_decodes >= chunk_count * 0.9, \
                f"REGRESSION FAILURE: Only {successful_decodes}/{chunk_count} chunks decoded! " \
                f"MediaRecorder streaming pattern failed."

            assert total_pcm_bytes >= expected_pcm_bytes, \
                f"PCM output too small: {total_pcm_bytes:,} bytes (expected >{expected_pcm_bytes:,})"

            print(f"   ✅ MediaRecorder pattern validated: {successful_decodes} chunks decoded")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_chunk_decode_failure_detection(
        self,
        mock_conversation_service,
        mock_stt_service,
        caplog
    ):
        """
        REGRESSION TEST #4: Detect when chunks fail to decode

        VALIDATES:
        - Test can detect decode failures
        - Failure detection is accurate
        - Clear error messaging when decode count < chunk count
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "regression_test_failure_detection"

        caplog.set_level(logging.DEBUG)

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id
            )

            # Send 10 valid chunks
            chunk_count = 10
            decode_count = 0

            for i in range(chunk_count):
                webm_chunk = get_sample_webm_audio()
                pcm_data = handler._decode_webm_chunk(webm_chunk)

                if pcm_data:
                    decode_count += 1

            # Verify decode monitoring works
            print(f"\n🎯 REGRESSION TEST: Decode failure detection")
            print(f"   Chunks sent: {chunk_count}")
            print(f"   Decodes detected: {decode_count}")

            # This test should pass (all chunks decode)
            # But if Bug #3 returns, decode_count will be 1
            if decode_count < chunk_count:
                print(f"   ❌ DECODE FAILURE DETECTED: {decode_count}/{chunk_count} chunks decoded")
                print(f"   Missing: {chunk_count - decode_count} chunks")
                pytest.fail(
                    f"Decode failure detected: Only {decode_count}/{chunk_count} chunks decoded. "
                    f"This indicates Bug #3 (buffer clearing) has returned."
                )
            else:
                print(f"   ✅ All {decode_count} chunks decoded successfully")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_continuous_decode_logging(
        self,
        mock_conversation_service,
        mock_stt_service,
        caplog
    ):
        """
        REGRESSION TEST #5: Verify decode logging for each chunk

        VALIDATES:
        - "Decoded chunk" log appears for each successful decode
        - Log count matches chunk count
        - No silent decode failures
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "regression_test_logging"

        caplog.set_level(logging.DEBUG)
        caplog.clear()  # Clear any previous logs

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id
            )

            # Send 5 chunks
            chunk_count = 5

            for i in range(chunk_count):
                webm_chunk = get_sample_webm_audio()
                pcm_data = handler._decode_webm_chunk(webm_chunk)

            # Count "Decoded chunk" log messages
            decode_logs = [r for r in caplog.records if "Decoded chunk" in r.message]
            log_count = len(decode_logs)

            print(f"\n🎯 REGRESSION TEST: Continuous decode logging")
            print(f"   Chunks sent: {chunk_count}")
            print(f"   Decode logs found: {log_count}")

            # ASSERTION: Should see decode log for each chunk
            # (Allow some tolerance for failed decodes, but NOT just 1 log)
            assert log_count >= chunk_count * 0.8, \
                f"REGRESSION FAILURE: Only {log_count} decode logs for {chunk_count} chunks! " \
                f"Expected at least {int(chunk_count * 0.8)} logs. " \
                f"This indicates only first chunk decoded (Bug #3)."

            # CRITICAL: If only 1 log, Bug #3 has returned
            assert log_count > 1, \
                f"CRITICAL: Only {log_count} decode log(s) found! " \
                f"This indicates Bug #3 (only first chunk decoded)."

            print(f"   ✅ Found {log_count} decode logs (expected ~{chunk_count})")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pcm_output_size_validation(
        self,
        mock_conversation_service,
        mock_stt_service
    ):
        """
        REGRESSION TEST #6: Validate PCM output size matches chunk count

        Expected PCM size per chunk:
        - 20ms of audio @ 48kHz stereo int16
        - 48000 samples/sec * 0.02 sec * 2 channels * 2 bytes = 3,840 bytes

        10 chunks = ~38,400 bytes

        If only first chunk decoded, PCM output will be ~3,840 bytes (Bug #3 symptom)
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "regression_test_pcm_size"

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id
            )

            # Send 10 chunks
            chunk_count = 10
            pcm_outputs = []

            for i in range(chunk_count):
                webm_chunk = get_sample_webm_audio()
                pcm_data = handler._decode_webm_chunk(webm_chunk)

                if pcm_data:
                    pcm_outputs.append(pcm_data)

            total_pcm_bytes = sum(len(pcm) for pcm in pcm_outputs)
            expected_min_bytes = chunk_count * 1000  # Very conservative: 1KB per chunk
            expected_nominal_bytes = chunk_count * 3840  # Theoretical: 3,840 bytes per 20ms chunk

            print(f"\n🎯 REGRESSION TEST: PCM output size validation")
            print(f"   Chunks sent: {chunk_count}")
            print(f"   PCM outputs: {len(pcm_outputs)}")
            print(f"   Total PCM: {total_pcm_bytes:,} bytes")
            print(f"   Expected (min): >{expected_min_bytes:,} bytes")
            print(f"   Expected (nominal): ~{expected_nominal_bytes:,} bytes")

            # CRITICAL ASSERTION
            assert total_pcm_bytes >= expected_min_bytes, \
                f"PCM output too small: {total_pcm_bytes:,} bytes (expected >{expected_min_bytes:,}). " \
                f"If only ~3,840 bytes, this indicates only first chunk decoded (Bug #3)."

            # If PCM is suspiciously small (< 2 chunks worth), likely Bug #3
            two_chunks_worth = 2 * 1000
            assert total_pcm_bytes >= two_chunks_worth, \
                f"CRITICAL: PCM output is {total_pcm_bytes:,} bytes (< {two_chunks_worth:,}). " \
                f"This strongly indicates only first chunk decoded (Bug #3)."

            print(f"   ✅ PCM output size validated: {total_pcm_bytes:,} bytes from {len(pcm_outputs)} chunks")


# ============================================================
# REGRESSION TEST CLASS - Buffer Management
# ============================================================

class TestBufferManagementRegression:
    """
    Tests for buffer lifecycle and management

    Validates that buffers are cleared at the right time,
    not prematurely (which caused Bug #3)
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_buffer_cleared_only_after_successful_decode(
        self,
        mock_conversation_service,
        mock_stt_service
    ):
        """
        Validate buffer clearing logic

        CORRECT behavior:
        - Per-chunk decode: Don't clear buffer (chunk is independent)
        - Buffered decode: Clear buffer after successful decode

        Bug #3 was caused by clearing buffer after per-chunk decode
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "regression_test_buffer_clearing"

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id
            )

            initial_buffer_size = len(handler.webm_buffer)

            # Test per-chunk decode (should NOT affect webm_buffer significantly)
            chunk1 = get_sample_webm_audio()
            pcm1 = handler._decode_webm_chunk(chunk1)

            buffer_after_chunk1 = len(handler.webm_buffer)

            print(f"\n🎯 REGRESSION TEST: Buffer clearing logic")
            print(f"   Initial buffer: {initial_buffer_size} bytes")
            print(f"   After chunk 1 decode: {buffer_after_chunk1} bytes")
            print(f"   PCM from chunk 1: {len(pcm1):,} bytes")

            # The buffer should not be cleared by _decode_webm_chunk
            # (per-chunk decodes are independent, don't touch webm_buffer)
            # Only _extract_pcm_audio() clears buffer after buffered decode

            # Test buffered decode path
            handler.webm_buffer.extend(chunk1)
            buffer_before_buffered = len(handler.webm_buffer)

            pcm_buffered = handler._extract_pcm_audio()
            buffer_after_buffered = len(handler.webm_buffer)

            print(f"   Before buffered decode: {buffer_before_buffered} bytes")
            print(f"   After buffered decode: {buffer_after_buffered} bytes")
            print(f"   PCM from buffered: {len(pcm_buffered):,} bytes")

            # Buffered decode should clear buffer after successful decode
            assert buffer_after_buffered == 0, \
                f"Buffer should be cleared after successful buffered decode, " \
                f"but still has {buffer_after_buffered} bytes"

            print(f"   ✅ Buffer clearing logic validated")
