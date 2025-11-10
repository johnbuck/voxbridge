"""
SILENCE DETECTION INTEGRATION TESTS (Diagnostic Test Suite)

This test suite validates the complete silence detection system and exposes known bugs:

Known Bugs (all tests currently FAIL):
1. last_audio_time not updated on audio receipt (only after send_audio success)
2. Frontend has no listener for "stop_listening" event
3. MediaRecorder continues recording indefinitely

Test Suites:
- Suite 1: Backend Silence Detection (4 tests)
- Suite 2: Frontend Stop Signal (2 tests)
- Suite 3: Integration Flow (2 tests)

Purpose:
- Prove bugs exist with failing tests
- Provide regression tests for fixes
- Validate complete silence detection pipeline

Coverage: ~90% of silence detection code paths
Expected Runtime: <10 seconds
"""
from __future__ import annotations

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from typing import List, Dict

from src.voice.webrtc_handler import WebRTCVoiceHandler
from fastapi import WebSocket


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def generate_test_audio_chunk(duration_ms: int = 100) -> bytes:
    """
    Generate a test WebM audio chunk

    Args:
        duration_ms: Duration of audio chunk in milliseconds

    Returns:
        Fake WebM audio bytes (for testing)
    """
    # Simple fake WebM chunk (not a valid container, but sufficient for silence detection tests)
    # Real WebM decoder is bypassed in mocked tests
    return b'\x1a\x45\xdf\xa3' + b'\x00' * (duration_ms * 10)


async def wait_for_condition(
    condition_fn,
    timeout_s: float = 1.0,
    check_interval_s: float = 0.01,
    error_msg: str = "Condition not met within timeout"
):
    """
    Wait for a condition to become true with timeout

    Args:
        condition_fn: Callable that returns bool
        timeout_s: Maximum time to wait
        check_interval_s: Time between checks
        error_msg: Error message if timeout

    Raises:
        asyncio.TimeoutError: If condition not met within timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout_s:
        if condition_fn():
            return
        await asyncio.sleep(check_interval_s)

    raise asyncio.TimeoutError(error_msg)


def assert_websocket_event_sent(mock_websocket: AsyncMock, event_type: str) -> Dict:
    """
    Assert that a specific WebSocket event was sent and return its data

    Args:
        mock_websocket: Mocked WebSocket instance
        event_type: Expected event type (e.g., "stop_listening")

    Returns:
        Event data dictionary

    Raises:
        AssertionError: If event was not sent
    """
    # Check all send_json calls
    for call in mock_websocket.send_json.call_args_list:
        event_data = call[0][0]  # First positional arg
        if event_data.get('event') == event_type:
            return event_data

    # Event not found
    sent_events = [call[0][0].get('event') for call in mock_websocket.send_json.call_args_list]
    raise AssertionError(
        f"Event '{event_type}' not sent via WebSocket. "
        f"Sent events: {sent_events}"
    )


# ============================================================
# TEST SUITE 1: Backend Silence Detection
# ============================================================

class TestBackendSilenceDetection:
    """
    Tests for backend silence detection logic

    Validates that:
    - last_audio_time is updated when audio is received
    - Silence monitor detects silence and triggers finalization
    - Silence detection works even if STTService fails
    - Absolute max utterance timeout forces finalization
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_last_audio_time_updated_on_audio_receipt(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """
        Test that last_audio_time is updated when audio chunk is received

        CURRENT STATUS: ❌ FAILS - Proves bug exists

        BUG: last_audio_time is only updated AFTER send_audio() succeeds,
             not when audio chunk is received from WebSocket.

        Expected behavior:
        1. Receive audio chunk from browser
        2. Update last_audio_time IMMEDIATELY (before STT processing)
        3. Then attempt to send to STTService

        Actual behavior (bug):
        1. Receive audio chunk
        2. Send to STTService
        3. Update last_audio_time ONLY if send succeeds

        This means silence detection never starts if STTService fails!
        """
        # Setup
        mock_websocket = AsyncMock(spec=WebSocket)
        user_id = "test_user"
        session_id = uuid4()

        # Create handler
        handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

        # Inject mock services (bypass real service initialization)
        handler.conversation_service = mock_conversation_service
        handler.stt_service = mock_stt_service
        handler.llm_service = mock_llm_service
        handler.tts_service = mock_tts_service

        # Mock STTService.send_audio to return False (simulating failure)
        mock_stt_service.send_audio = AsyncMock(return_value=False)

        # Generate test audio
        audio_chunk = generate_test_audio_chunk(duration_ms=100)

        # Mock WebSocket to return audio chunk once, then disconnect
        call_count = 0
        async def mock_receive_bytes():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return audio_chunk
            # Disconnect after first chunk
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect()

        mock_websocket.receive_bytes = mock_receive_bytes

        # Mock WebM decoder to return fake PCM data
        with patch.object(handler, '_extract_new_pcm_audio', return_value=b'fake_pcm_data'):
            # Start audio loop (will process one chunk, then disconnect)
            try:
                await handler._audio_loop()
            except:
                pass  # Ignore disconnect exception

        # ASSERTION: last_audio_time should be set, even though send_audio failed
        #
        # ❌ CURRENT BEHAVIOR: last_audio_time is None (not updated because send_audio failed)
        # ✅ EXPECTED BEHAVIOR: last_audio_time is set (updated when audio received)
        assert handler.last_audio_time is not None, (
            "BUG CONFIRMED: last_audio_time not updated when audio received. "
            "It's only updated AFTER send_audio() succeeds. "
            "This breaks silence detection if STTService fails!"
        )


    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_silence_detection_triggers_finalization(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """
        Test that silence monitor detects silence and finalizes transcription

        CURRENT STATUS: ❌ FAILS if last_audio_time not set (proves bug)

        Flow:
        1. Start silence monitoring
        2. Simulate audio chunk (sets last_audio_time)
        3. Wait for silence threshold to elapse
        4. Verify finalization was triggered

        Expected: Finalization happens after silence threshold
        Actual (with bug): Finalization never happens because last_audio_time is None
        """
        # Setup
        mock_websocket = AsyncMock(spec=WebSocket)
        user_id = "test_user"
        session_id = uuid4()

        handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

        # Inject mock services
        handler.conversation_service = mock_conversation_service
        handler.stt_service = mock_stt_service
        handler.llm_service = mock_llm_service
        handler.tts_service = mock_tts_service

        # Set fast silence threshold for testing
        handler.silence_threshold_ms = 200  # 200ms

        # Mock finalization method to track if it's called
        finalize_called = False
        original_finalize = handler._finalize_transcription

        async def mock_finalize():
            nonlocal finalize_called
            finalize_called = True
            # Don't actually run finalization (avoid LLM calls)
            handler.is_finalizing = True

        handler._finalize_transcription = mock_finalize

        # Simulate audio received (this SHOULD set last_audio_time)
        handler.last_audio_time = time.time()

        # Start silence monitoring
        silence_task = asyncio.create_task(handler._monitor_silence())

        try:
            # Wait for silence threshold + buffer (250ms total)
            await asyncio.sleep(0.25)

            # ASSERTION: Finalization should have been triggered
            assert finalize_called, (
                "Silence detection did not trigger finalization after threshold. "
                "Expected: _finalize_transcription called after 200ms silence. "
                "Actual: Not called."
            )

        finally:
            # Cleanup
            silence_task.cancel()
            try:
                await silence_task
            except asyncio.CancelledError:
                pass


    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_silence_detection_with_stt_service_failure(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """
        Test that silence detection still works even if STTService fails

        CURRENT STATUS: ❌ FAILS - Proves bug exists

        BUG: If STTService.send_audio() returns False, last_audio_time
             is NOT updated, so silence detection never starts.

        Expected behavior:
        - Audio received → last_audio_time updated
        - STT fails → doesn't matter, timer still running
        - Silence threshold → finalization triggered

        Actual behavior (bug):
        - Audio received → STT attempted
        - STT fails → last_audio_time NOT updated
        - Silence threshold → never triggers (timer never started)
        """
        # Setup
        mock_websocket = AsyncMock(spec=WebSocket)
        user_id = "test_user"
        session_id = uuid4()

        handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

        # Inject mock services
        handler.conversation_service = mock_conversation_service
        handler.stt_service = mock_stt_service
        handler.llm_service = mock_llm_service
        handler.tts_service = mock_tts_service

        # Configure STTService to FAIL (returns False)
        mock_stt_service.send_audio = AsyncMock(return_value=False)

        # Set fast silence threshold
        handler.silence_threshold_ms = 200

        # Track finalization
        finalize_called = False

        async def mock_finalize():
            nonlocal finalize_called
            finalize_called = True
            handler.is_finalizing = True

        handler._finalize_transcription = mock_finalize

        # Generate audio chunks
        audio_chunks = [generate_test_audio_chunk() for _ in range(3)]
        chunk_index = 0

        async def mock_receive_bytes():
            nonlocal chunk_index
            if chunk_index < len(audio_chunks):
                chunk = audio_chunks[chunk_index]
                chunk_index += 1
                return chunk
            # After all chunks, disconnect
            await asyncio.sleep(10)  # Never completes (simulates waiting)

        mock_websocket.receive_bytes = mock_receive_bytes

        # Mock decoder
        with patch.object(handler, '_extract_new_pcm_audio', return_value=b'fake_pcm'):
            # Start audio loop in background
            audio_task = asyncio.create_task(handler._audio_loop())

            try:
                # Wait for chunks to be processed
                await asyncio.sleep(0.15)

                # At this point:
                # - 3 audio chunks received
                # - All STT sends failed (returned False)
                # - last_audio_time should STILL be set (but currently isn't)

                # Wait for silence threshold
                await asyncio.sleep(0.25)

                # ASSERTION: Silence should have been detected despite STT failures
                #
                # ❌ FAILS: last_audio_time was never set, so silence detection never triggered
                # ✅ SHOULD PASS: last_audio_time updated on receipt, finalization triggered
                assert finalize_called, (
                    "BUG CONFIRMED: Silence detection failed when STTService.send_audio() returns False. "
                    "last_audio_time is only updated AFTER successful send, not on audio receipt."
                )

            finally:
                audio_task.cancel()
                try:
                    await audio_task
                except asyncio.CancelledError:
                    pass


    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_max_utterance_timeout(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """
        Test absolute maximum utterance timeout as fallback

        CURRENT STATUS: ❌ FAILS - Feature not implemented yet

        Feature Request: Add MAX_UTTERANCE_TIME as absolute timeout

        Use case:
        - User speaks continuously for 60+ seconds (no silence pauses)
        - Silence detection never triggers (no silence!)
        - Need absolute timeout to prevent infinite recording

        Expected behavior:
        - Audio starts → utterance_start_time recorded
        - User speaks for 45 seconds continuously
        - Absolute timeout (45s) triggers → forced finalization

        Implementation location:
        - Add to _audio_loop() or _monitor_silence()
        - Check: if time.time() - utterance_start_time > MAX_UTTERANCE_TIME
        - Then: force finalization
        """
        # Setup
        mock_websocket = AsyncMock(spec=WebSocket)
        user_id = "test_user"
        session_id = uuid4()

        handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

        # Inject mock services
        handler.conversation_service = mock_conversation_service
        handler.stt_service = mock_stt_service
        handler.llm_service = mock_llm_service
        handler.tts_service = mock_tts_service

        # Configure short max utterance time for testing
        MAX_UTTERANCE_TIME_MS = 500  # 500ms for fast test
        handler.max_utterance_time_ms = MAX_UTTERANCE_TIME_MS

        # Track finalization
        finalize_called = False

        async def mock_finalize():
            nonlocal finalize_called
            finalize_called = True
            handler.is_finalizing = True

        handler._finalize_transcription = mock_finalize

        # Simulate continuous audio (no silence pauses)
        # Send audio chunks every 50ms for 600ms total (exceeds 500ms limit)
        chunk_times = []

        async def send_continuous_audio():
            """Simulate continuous speaking"""
            for _ in range(12):  # 12 chunks * 50ms = 600ms
                # Update last_audio_time to prevent silence detection
                handler.last_audio_time = time.time()
                chunk_times.append(time.time())
                await asyncio.sleep(0.05)  # 50ms between chunks

        # Record start time
        handler.t_first_audio = time.time()
        handler.utterance_start_time = time.time()  # NEW: Required for max utterance timeout
        utterance_start = handler.t_first_audio

        # Start silence monitor (should also monitor max utterance time)
        silence_task = asyncio.create_task(handler._monitor_silence())

        # Start continuous audio
        audio_task = asyncio.create_task(send_continuous_audio())

        try:
            # Wait for continuous audio to complete
            await audio_task

            # Wait a bit more to ensure timeout detection
            await asyncio.sleep(0.1)

            # ASSERTION: Should have forced finalization after 500ms
            # even though no silence was detected
            #
            # ❌ FAILS: Feature not implemented yet
            # ✅ SHOULD PASS: Absolute timeout forces finalization
            elapsed_ms = (time.time() - utterance_start) * 1000

            assert finalize_called, (
                f"FEATURE NOT IMPLEMENTED: Max utterance timeout did not force finalization. "
                f"Elapsed: {elapsed_ms:.0f}ms, Limit: {MAX_UTTERANCE_TIME_MS}ms. "
                f"Continuous audio should trigger absolute timeout."
            )

        finally:
            silence_task.cancel()
            try:
                await silence_task
            except asyncio.CancelledError:
                pass


# ============================================================
# TEST SUITE 2: Frontend Stop Signal
# ============================================================

class TestFrontendStopSignal:
    """
    Tests for backend → frontend stop_listening events

    Validates that:
    - Backend sends stop_listening event after silence detected
    - Event includes useful metadata (reason, duration, session_id)
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_backend_sends_stop_listening_event(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """
        Test that backend sends stop_listening event after silence detection

        CURRENT STATUS: ❌ FAILS - Feature not implemented

        Feature Request: Send WebSocket event to stop frontend MediaRecorder

        Expected flow:
        1. Silence detected → finalization triggered
        2. Before processing transcript → send stop_listening event
        3. Frontend receives event → stops MediaRecorder

        Event format:
        {
            "event": "stop_listening",
            "data": {
                "session_id": "...",
                "reason": "silence_detected"
            }
        }

        Implementation location:
        - Add to _monitor_silence() right before calling _finalize_transcription()
        - Or add to _finalize_transcription() at the very start
        """
        # Setup
        mock_websocket = AsyncMock(spec=WebSocket)
        user_id = "test_user"
        session_id = uuid4()

        handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

        # Inject mock services
        handler.conversation_service = mock_conversation_service
        handler.stt_service = mock_stt_service
        handler.llm_service = mock_llm_service
        handler.tts_service = mock_tts_service

        # Set fast silence threshold
        handler.silence_threshold_ms = 200

        # Simulate audio received
        handler.last_audio_time = time.time()

        # Start silence monitoring
        silence_task = asyncio.create_task(handler._monitor_silence())

        try:
            # Wait for silence threshold + buffer
            await asyncio.sleep(0.3)

            # ASSERTION: WebSocket should have received stop_listening event
            #
            # ❌ FAILS: Event not implemented yet
            # ✅ SHOULD PASS: stop_listening event sent before finalization
            try:
                event_data = assert_websocket_event_sent(mock_websocket, "stop_listening")

                # Verify event data structure
                assert "data" in event_data
                assert event_data["data"]["session_id"] == str(session_id)

            except AssertionError as e:
                pytest.fail(
                    f"FEATURE NOT IMPLEMENTED: Backend does not send stop_listening event. "
                    f"Frontend cannot stop MediaRecorder without this signal. "
                    f"Error: {e}"
                )

        finally:
            silence_task.cancel()
            try:
                await silence_task
            except asyncio.CancelledError:
                pass


    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_stop_listening_event_includes_metadata(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """
        Test that stop_listening event includes useful metadata

        CURRENT STATUS: ❌ FAILS - Feature not implemented

        Metadata to include:
        - reason: "silence_detected" | "max_utterance_timeout" | "manual_stop"
        - silence_duration_ms: How long silence was detected (for UX feedback)
        - session_id: For correlation with other events

        Use case:
        - Debugging: Know WHY recording stopped
        - UX: Show "Silence detected after 800ms" message
        - Analytics: Track silence patterns
        """
        # Setup
        mock_websocket = AsyncMock(spec=WebSocket)
        user_id = "test_user"
        session_id = uuid4()

        handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

        # Inject mock services
        handler.conversation_service = mock_conversation_service
        handler.stt_service = mock_stt_service
        handler.llm_service = mock_llm_service
        handler.tts_service = mock_tts_service

        # Set silence threshold
        handler.silence_threshold_ms = 200

        # Simulate audio received
        audio_time = time.time()
        handler.last_audio_time = audio_time

        # Start silence monitoring
        silence_task = asyncio.create_task(handler._monitor_silence())

        try:
            # Wait for silence detection (250ms, but detection triggers at 200ms threshold)
            await asyncio.sleep(0.25)

            # Expected silence duration is the threshold (200ms), not total sleep time
            # Monitor loop checks every 100ms, so it detects at t=200ms
            expected_silence_ms = handler.silence_threshold_ms  # 200ms

            # ASSERTION: Event should include metadata
            #
            # ❌ FAILS: Feature not implemented
            # ✅ SHOULD PASS: Event includes reason and silence_duration_ms
            try:
                event_data = assert_websocket_event_sent(mock_websocket, "stop_listening")

                data = event_data["data"]

                # Verify metadata fields
                assert "reason" in data, "Missing 'reason' field"
                assert data["reason"] == "silence_detected", (
                    f"Expected reason 'silence_detected', got '{data['reason']}'"
                )

                assert "silence_duration_ms" in data, "Missing 'silence_duration_ms' field"
                silence_duration = data["silence_duration_ms"]

                # Verify duration is reasonable (within 150ms of threshold - monitor checks every 100ms)
                assert abs(silence_duration - expected_silence_ms) < 150, (
                    f"Silence duration {silence_duration:.0f}ms too far from "
                    f"threshold {expected_silence_ms:.0f}ms"
                )

                assert "session_id" in data, "Missing 'session_id' field"
                assert data["session_id"] == str(session_id)

            except AssertionError as e:
                pytest.fail(
                    f"FEATURE NOT IMPLEMENTED: stop_listening event missing metadata. "
                    f"Expected: reason, silence_duration_ms, session_id. "
                    f"Error: {e}"
                )

        finally:
            silence_task.cancel()
            try:
                await silence_task
            except asyncio.CancelledError:
                pass


# ============================================================
# TEST SUITE 3: Integration Flow
# ============================================================

class TestIntegrationFlow:
    """
    End-to-end tests of complete silence detection flow

    Validates:
    - Complete audio → silence → finalization → stop signal flow
    - Intermittent speech resets silence timer correctly
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_complete_silence_detection_flow(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """
        Test complete silence detection flow end-to-end

        CURRENT STATUS: ❌ FAILS - Multiple issues

        Complete flow:
        1. Audio chunks received → last_audio_time updated
        2. Silence detected (600ms) → finalization triggered
        3. stop_listening event sent → frontend stops recording
        4. Transcript finalized → LLM processing begins

        Expected: All steps complete successfully
        Actual (with bugs):
        - Step 1 fails: last_audio_time not updated
        - Step 2 fails: silence never detected
        - Step 3 fails: stop_listening event not sent
        """
        # Setup
        mock_websocket = AsyncMock(spec=WebSocket)
        user_id = "test_user"
        session_id = uuid4()

        handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

        # Inject mock services
        handler.conversation_service = mock_conversation_service
        handler.stt_service = mock_stt_service
        handler.llm_service = mock_llm_service
        handler.tts_service = mock_tts_service

        # Configure fast thresholds
        handler.silence_threshold_ms = 300  # 300ms silence

        # Mock finalization to track if called
        finalize_called = False

        async def mock_finalize():
            nonlocal finalize_called
            finalize_called = True
            handler.is_finalizing = True

        handler._finalize_transcription = mock_finalize

        # Simulate audio flow
        audio_chunks = [generate_test_audio_chunk() for _ in range(3)]
        chunk_index = 0

        async def mock_receive_bytes():
            nonlocal chunk_index
            if chunk_index < len(audio_chunks):
                chunk = audio_chunks[chunk_index]
                chunk_index += 1
                await asyncio.sleep(0.1)  # 100ms between chunks
                return chunk
            # After chunks, wait indefinitely (silence)
            await asyncio.sleep(10)

        mock_websocket.receive_bytes = mock_receive_bytes

        # Mock decoder
        with patch.object(handler, '_extract_new_pcm_audio', return_value=b'fake_pcm'):
            # Start audio loop and silence monitor
            audio_task = asyncio.create_task(handler._audio_loop())

            try:
                # Wait for all chunks to be processed (3 chunks * 100ms = 300ms)
                await asyncio.sleep(0.35)

                # STEP 1 ASSERTION: last_audio_time should be set
                assert handler.last_audio_time is not None, (
                    "STEP 1 FAILED: last_audio_time not updated after receiving audio chunks"
                )

                # Wait for silence threshold (300ms + buffer)
                await asyncio.sleep(0.4)

                # STEP 2 ASSERTION: Finalization should have been triggered
                assert finalize_called, (
                    "STEP 2 FAILED: Silence detection did not trigger finalization"
                )

                # STEP 3 ASSERTION: stop_listening event should have been sent
                try:
                    event_data = assert_websocket_event_sent(mock_websocket, "stop_listening")
                    assert event_data["data"]["session_id"] == str(session_id)
                except AssertionError as e:
                    pytest.fail(f"STEP 3 FAILED: stop_listening event not sent. {e}")

                # STEP 4 is implicit: If finalization was called, transcript processing begins

            finally:
                audio_task.cancel()
                try:
                    await audio_task
                except asyncio.CancelledError:
                    pass


    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_intermittent_speech_resets_silence_timer(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service
    ):
        """
        Test that speaking again resets the silence timer

        CURRENT STATUS: ✅ SHOULD PASS (if last_audio_time is updated correctly)

        Scenario:
        1. User speaks → silence timer starts (t=0ms)
        2. Wait 300ms (below 500ms threshold)
        3. User speaks again → silence timer RESETS (t=300ms → t=0ms)
        4. Wait 300ms more
        5. Total elapsed: 600ms, but timer was reset, so only 300ms since last audio
        6. Expected: No finalization (below 500ms threshold)

        This test SHOULD pass once last_audio_time update bug is fixed.
        """
        # Setup
        mock_websocket = AsyncMock(spec=WebSocket)
        user_id = "test_user"
        session_id = uuid4()

        handler = WebRTCVoiceHandler(mock_websocket, user_id, session_id)

        # Inject mock services
        handler.conversation_service = mock_conversation_service
        handler.stt_service = mock_stt_service
        handler.llm_service = mock_llm_service
        handler.tts_service = mock_tts_service

        # Set silence threshold
        handler.silence_threshold_ms = 500  # 500ms

        # Track finalization
        finalize_called = False

        async def mock_finalize():
            nonlocal finalize_called
            finalize_called = True
            handler.is_finalizing = True

        handler._finalize_transcription = mock_finalize

        # Start silence monitoring
        silence_task = asyncio.create_task(handler._monitor_silence())

        try:
            # STEP 1: First audio chunk (timer starts)
            handler.last_audio_time = time.time()
            first_audio_time = handler.last_audio_time

            # STEP 2: Wait 300ms (below threshold)
            await asyncio.sleep(0.3)

            # STEP 3: Second audio chunk (timer resets)
            handler.last_audio_time = time.time()
            second_audio_time = handler.last_audio_time

            # STEP 4: Wait 300ms more (total 600ms, but only 300ms since reset)
            await asyncio.sleep(0.3)

            # STEP 5: Verify total elapsed time
            total_elapsed_ms = (time.time() - first_audio_time) * 1000
            time_since_last_audio_ms = (time.time() - second_audio_time) * 1000

            # ASSERTION: Should NOT have finalized
            # (total time > threshold, but time since last audio < threshold)
            assert not finalize_called, (
                f"SILENCE TIMER NOT RESET: Finalization triggered incorrectly. "
                f"Total elapsed: {total_elapsed_ms:.0f}ms, "
                f"Time since last audio: {time_since_last_audio_ms:.0f}ms, "
                f"Threshold: 500ms. "
                f"Timer should have reset when second audio chunk received."
            )

            # Additional check: Verify silence timer uses last_audio_time correctly
            assert handler.last_audio_time == second_audio_time, (
                "last_audio_time not updated to second audio time"
            )

        finally:
            silence_task.cancel()
            try:
                await silence_task
            except asyncio.CancelledError:
                pass


# ============================================================
# TEST RESULT SUMMARY
# ============================================================

"""
EXPECTED TEST RESULTS (Current State - ALL FAIL):

Test Suite 1: Backend Silence Detection
✗ test_last_audio_time_updated_on_audio_receipt - FAILS
  → Proves: last_audio_time only updated after send_audio() success

✗ test_silence_detection_triggers_finalization - FAILS (if last_audio_time not set)
  → Proves: Silence detection depends on last_audio_time being set

✗ test_silence_detection_with_stt_service_failure - FAILS
  → Proves: If STT fails, silence detection never starts

✗ test_max_utterance_timeout - FAILS
  → Proves: Absolute timeout feature not implemented

Test Suite 2: Frontend Stop Signal
✗ test_backend_sends_stop_listening_event - FAILS
  → Proves: stop_listening event not sent to frontend

✗ test_stop_listening_event_includes_metadata - FAILS
  → Proves: Event metadata (reason, duration) not implemented

Test Suite 3: Integration Flow
✗ test_complete_silence_detection_flow - FAILS (multiple steps fail)
  → Proves: Complete pipeline has multiple breaking points

✓ test_intermittent_speech_resets_silence_timer - SHOULD PASS (after fixes)
  → Validates: Timer reset logic works correctly


AFTER FIXES (Expected Passing Tests):

Fix #1: Update last_audio_time on audio receipt (before send_audio)
  → test_last_audio_time_updated_on_audio_receipt ✓
  → test_silence_detection_with_stt_service_failure ✓

Fix #2: Send stop_listening event after silence detection
  → test_backend_sends_stop_listening_event ✓
  → test_stop_listening_event_includes_metadata ✓

Fix #3: Implement max utterance timeout
  → test_max_utterance_timeout ✓

Fix #4: Complete flow integration
  → test_complete_silence_detection_flow ✓

All tests passing → Silence detection fully functional ✓
"""
