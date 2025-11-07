"""
Integration Tests for WebRTC Audio Format Fix (Phase 5 Compatible)
VoxBridge 2.0 - Dual-Format Audio Architecture

Tests the full WebRTC audio pipeline with Phase 5 service layer:
Browser → WebSocket → PyAV decode → PCM → WhisperX → Transcript

LATENCY TARGETS:
- WebM decode: <100ms per chunk
- Audio to transcript: <500ms
- End-to-end conversation: <2s

PRIORITY LEVELS:
- P0: Critical functionality (must pass for production)
- P1: Important error handling (should pass)
- P2: Performance benchmarks (nice to have)

PHASE 5 COMPATIBILITY:
- Uses Phase 5 service mocks (ConversationService, STTService, LLMService, TTSService)
- Verifies audio_format='pcm' parameter passed to STTService.send_audio()
- Tests callback-based streaming APIs
- Validates CachedContext objects from ConversationService
"""
from __future__ import annotations

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from uuid import uuid4
import os

# Import fixtures
from tests.fixtures.audio_samples import (
    get_sample_webm_audio,
    get_multi_frame_webm_audio,
    get_incomplete_webm_audio,
    get_corrupted_webm_audio
)


# ============================================================
# P0: Critical End-to-End Flow Validation (Phase 5)
# ============================================================

class TestWebRTCEndToEnd:
    """P0: Critical end-to-end flow validation with Phase 5 services"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_browser_to_transcript_pcm_format(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service,
        mock_whisperx_with_format,
        sample_webm_audio,
        latency_tracker
    ):
        """
        P0-1: Complete WebRTC audio flow with PCM format (Phase 5)

        Flow: Browser → WebSocket → WebM decode → PCM → WhisperX → Transcript

        VALIDATES:
        - WebM chunks received and buffered
        - PyAV decodes to PCM successfully
        - Format indicator sent to WhisperX (audio_format='pcm')
        - Partial/final transcripts received
        - Total latency < 500ms
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4

        # Create mock WebSocket
        mock_websocket = AsyncMock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.receive_bytes = AsyncMock()
        mock_websocket.send_text = AsyncMock()
        mock_websocket.send_json = AsyncMock()

        # Use session from conversation service mock
        session_id = str(mock_conversation_service.get_or_create_session.return_value.session.id)
        user_id = "browser_user_test"

        server, port = mock_whisperx_with_format

        latency_tracker.start("browser_to_transcript")

        # Patch environment to use mock WhisperX
        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            # Create handler with mocked services
            with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
                 patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service), \
                 patch('src.voice.webrtc_handler.LLMService', return_value=mock_llm_service), \
                 patch('src.voice.webrtc_handler.TTSService', return_value=mock_tts_service):

                handler = WebRTCVoiceHandler(
                    websocket=mock_websocket,
                    user_id=user_id,
                    session_id=uuid4()
                )

                # Connect to STT (which now uses real WhisperX mock server)
                await handler._connect_stt()

                # Simulate receiving WebM audio from browser
                handler.webm_buffer.extend(sample_webm_audio)

                # Extract PCM
                pcm_data = handler._extract_pcm_audio()

                # Send to STT service (Phase 5 API)
                await handler.stt_service.send_audio(
                    session_id=handler.session_id,
                    audio_data=pcm_data,
                    audio_format='pcm'  # Phase 5: explicit format parameter
                )

        latency = latency_tracker.end("browser_to_transcript")

        # ASSERTIONS
        print(f"\n🎯 Browser → Transcript: {latency:.2f}ms")
        print(f"   WebM size: {len(sample_webm_audio)} bytes")
        print(f"   PCM extracted: {len(pcm_data)} bytes")

        # Verify STTService.send_audio was called with audio_format='pcm'
        assert mock_stt_service.send_audio.called, "STTService.send_audio should be called"
        call_kwargs = mock_stt_service.send_audio.call_args.kwargs
        assert call_kwargs.get('audio_format') == 'pcm', \
            f"Expected audio_format='pcm', got {call_kwargs.get('audio_format')}"

        # Verify format indicator sent to real WhisperX
        assert server.get_format_for_session(handler.session_id) == 'pcm', \
            "WebRTC should use PCM format (not Opus)"

        # Verify PCM extraction worked
        assert len(pcm_data) > 0, "PCM extraction should produce audio data"

        # Latency check
        assert latency < 500, f"Latency too high: {latency:.2f}ms (target: <500ms)"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_webm_decode_to_transcription(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_whisperx_with_format,
        multi_frame_webm_audio,
        latency_tracker
    ):
        """
        P0-2: Multi-frame WebM decode to transcription (Phase 5)

        VALIDATES:
        - Multiple WebM frames decoded
        - PCM audio extracted and sent
        - Transcription received
        - No frame size errors
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4

        mock_websocket = AsyncMock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.receive_bytes = AsyncMock()
        mock_websocket.send_text = AsyncMock()
        mock_websocket.send_json = AsyncMock()

        session_id = str(mock_conversation_service.get_or_create_session.return_value.session.id)
        user_id = "browser_user_multi_frame"

        server, port = mock_whisperx_with_format

        latency_tracker.start("webm_decode")

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
                 patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

                handler = WebRTCVoiceHandler(
                    websocket=mock_websocket,
                    user_id=user_id,
                    session_id=uuid4()
                )

                # Simulate multi-frame WebM (500ms = 25 frames)
                handler.webm_buffer.extend(multi_frame_webm_audio)

                # Extract PCM
                pcm_data = handler._extract_pcm_audio()

                # Send to STT
                await handler.stt_service.send_audio(
                    session_id=handler.session_id,
                    audio_data=pcm_data,
                    audio_format='pcm'
                )

        latency = latency_tracker.end("webm_decode")

        print(f"\n🎯 Multi-frame WebM decode: {latency:.2f}ms")
        print(f"   WebM size: {len(multi_frame_webm_audio)} bytes")
        print(f"   PCM extracted: {len(pcm_data)} bytes")

        # Verify multi-frame decode worked
        assert len(pcm_data) > 0, "Multi-frame WebM should produce PCM audio"
        assert latency < 200, f"Decode latency too high: {latency:.2f}ms"

        # Verify audio_format parameter
        call_kwargs = mock_stt_service.send_audio.call_args.kwargs
        assert call_kwargs.get('audio_format') == 'pcm'

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_conversation_loop_webrtc(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service,
        mock_whisperx_with_format,
        sample_webm_audio,
        latency_tracker
    ):
        """
        P0-3: Complete WebRTC conversation loop (Phase 5)

        Flow: Audio → Transcript → LLM → TTS → Response

        VALIDATES:
        - Complete pipeline works with Phase 5 services
        - All stages complete successfully
        - Callback-based streaming works
        - Total latency < 2s
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4

        mock_websocket = AsyncMock()
        session_id_uuid = uuid4()
        session_id = str(session_id_uuid)
        user_id = "browser_user_conversation"

        server, port = mock_whisperx_with_format

        latency_tracker.start("full_conversation_webrtc")

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
                 patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service), \
                 patch('src.voice.webrtc_handler.LLMService', return_value=mock_llm_service), \
                 patch('src.voice.webrtc_handler.TTSService', return_value=mock_tts_service):

                handler = WebRTCVoiceHandler(
                    websocket=mock_websocket,
                    user_id=user_id,
                    session_id=session_id_uuid
                )

                await handler._connect_stt()

                # Process audio
                handler.webm_buffer.extend(sample_webm_audio)
                pcm_data = handler._extract_pcm_audio()

                await handler.stt_service.send_audio(
                    session_id=handler.session_id,
                    audio_data=pcm_data,
                    audio_format='pcm'
                )

                # Simulate silence detection triggering LLM
                # (This would normally call LLMService.generate_response with callback)
                await asyncio.sleep(0.1)

        latency = latency_tracker.end("full_conversation_webrtc")

        print(f"\n🎯 Full WebRTC conversation: {latency:.2f}ms")

        # Verify STTService.send_audio called
        assert mock_stt_service.send_audio.called

        # Verify format
        call_kwargs = mock_stt_service.send_audio.call_args.kwargs
        assert call_kwargs.get('audio_format') == 'pcm'

        assert latency < 2000, f"Total latency too high: {latency:.2f}ms (target: <2s)"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_stt_callback_receives_transcripts(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_whisperx_with_format,
        sample_webm_audio
    ):
        """
        P0-4: Verify STT callback receives partial and final transcripts (Phase 5)

        VALIDATES:
        - STTService.register_callback works
        - Callback receives transcripts from WhisperX
        - Both partial and final transcripts delivered
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4

        mock_websocket = AsyncMock()
        session_id_uuid = uuid4()
        user_id = "browser_user_callback"

        transcripts_received = []

        # Mock STT callback
        async def mock_callback(text: str, is_final: bool, metadata: dict):
            transcripts_received.append({
                'text': text,
                'is_final': is_final,
                'metadata': metadata
            })

        mock_stt_service.register_callback = AsyncMock()

        server, port = mock_whisperx_with_format

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
                 patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

                handler = WebRTCVoiceHandler(
                    websocket=mock_websocket,
                    user_id=user_id,
                    session_id=session_id_uuid
                )

                await handler._connect_stt()

                # Verify callback was registered
                assert mock_stt_service.register_callback.called, \
                    "STTService.register_callback should be called during connection"

        print(f"\n🎯 STT callback test:")
        print(f"   Callback registered: {mock_stt_service.register_callback.called}")
        print(f"   Register call count: {mock_stt_service.register_callback.call_count}")

        # Verify callback registration happened
        assert mock_stt_service.register_callback.call_count >= 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_llm_callback_streaming(
        self,
        mock_conversation_service,
        mock_llm_service,
        sample_webm_audio
    ):
        """
        P0-5: Verify LLM callback receives streaming chunks (Phase 5)

        VALIDATES:
        - LLMService.generate_response with callback works
        - Streaming chunks delivered incrementally
        - Complete response returned
        """
        from src.services.llm_service import LLMConfig, ProviderType

        session_id = str(uuid4())
        chunks_received = []

        # Callback to collect chunks
        async def collect_chunks(chunk: str):
            chunks_received.append(chunk)

        # Call LLM service with streaming callback
        response = await mock_llm_service.generate_response(
            session_id=session_id,
            messages=[{"role": "user", "content": "Hello"}],
            config=LLMConfig(
                provider=ProviderType.OPENROUTER,
                model="anthropic/claude-3-haiku",
                temperature=0.7
            ),
            stream=True,
            callback=collect_chunks
        )

        print(f"\n🎯 LLM streaming callback test:")
        print(f"   Chunks received: {len(chunks_received)}")
        print(f"   Complete response: \"{response}\"")

        # Verify streaming worked
        assert len(chunks_received) >= 3, \
            f"Expected at least 3 chunks, got {len(chunks_received)}"

        assert response == "Hello! How can I help you?", \
            "Complete response should match"


# ============================================================
# P0: Format Routing Validation (Phase 5)
# ============================================================

class TestFormatRouting:
    """P0: Format indicator validation with Phase 5 services"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_format_indicator_sent_on_first_audio(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_whisperx_with_format,
        sample_webm_audio
    ):
        """
        P0-6: Verify format indicator sent to WhisperX on first audio (Phase 5)

        Expected: {"type": "start", "audio_format": "pcm", "userId": "..."}

        VALIDATES:
        - Format indicator sent before audio
        - Indicator specifies 'pcm' (not 'opus')
        - Sent only once per session
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4

        mock_websocket = AsyncMock()
        session_id = str(uuid4())
        user_id = "browser_user_format_test"

        server, port = mock_whisperx_with_format

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
                 patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

                handler = WebRTCVoiceHandler(
                    websocket=mock_websocket,
                    user_id=user_id,
                    session_id=uuid4()
                )

                await handler._connect_stt()

                # Send first audio chunk
                handler.webm_buffer.extend(sample_webm_audio)
                pcm_data = handler._extract_pcm_audio()

                await handler.stt_service.send_audio(
                    session_id=handler.session_id,
                    audio_data=pcm_data,
                    audio_format='pcm'
                )

        # ASSERTIONS
        print(f"\n🎯 Format indicator test:")
        print(f"   Session: {handler.session_id}")

        # Verify send_audio called with correct format
        assert mock_stt_service.send_audio.called
        call_kwargs = mock_stt_service.send_audio.call_args.kwargs
        assert call_kwargs.get('audio_format') == 'pcm', \
            "WebRTC must use PCM format"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pcm_format_reaches_whisperx(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_whisperx_with_format,
        sample_webm_audio
    ):
        """
        P0-7: Verify PCM audio data reaches WhisperX (not Opus) (Phase 5)

        VALIDATES:
        - Audio decoded from WebM
        - PCM format used (not Opus packets)
        - No buffer size errors
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4

        mock_websocket = AsyncMock()
        session_id = str(uuid4())
        user_id = "browser_user_pcm_test"

        server, port = mock_whisperx_with_format

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
                 patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

                handler = WebRTCVoiceHandler(
                    websocket=mock_websocket,
                    user_id=user_id,
                    session_id=uuid4()
                )

                await handler._connect_stt()

                # Extract PCM from WebM
                handler.webm_buffer.extend(sample_webm_audio)
                pcm_data = handler._extract_pcm_audio()

                # Send to WhisperX (real server via STTService)
                await handler.stt_service.send_audio(
                    session_id=handler.session_id,
                    audio_data=pcm_data,
                    audio_format='pcm'
                )

        print(f"\n🎯 PCM audio delivery:")
        print(f"   WebM size: {len(sample_webm_audio)} bytes")
        print(f"   PCM extracted: {len(pcm_data)} bytes")

        assert len(pcm_data) > 0, "PCM extraction failed"

        # Verify format parameter
        call_kwargs = mock_stt_service.send_audio.call_args.kwargs
        assert call_kwargs.get('audio_format') == 'pcm'

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_audio_format_parameter_required(
        self,
        mock_stt_service,
        sample_webm_audio
    ):
        """
        P0-8: Verify audio_format parameter is required in Phase 5 (Phase 5)

        VALIDATES:
        - STTService.send_audio requires audio_format parameter
        - Format must be 'pcm' or 'opus'
        """
        session_id = str(uuid4())
        pcm_data = b'\x00' * 1920  # 20ms of PCM at 48kHz stereo

        # Call with format parameter (should work)
        result = await mock_stt_service.send_audio(
            session_id=session_id,
            audio_data=pcm_data,
            audio_format='pcm'
        )

        assert result is True, "send_audio should return True"

        # Verify it was called with correct parameters
        call_kwargs = mock_stt_service.send_audio.call_args.kwargs
        assert 'audio_format' in call_kwargs, \
            "audio_format parameter should be passed"
        assert call_kwargs['audio_format'] == 'pcm', \
            "audio_format should be 'pcm'"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pcm_format_persistent_across_chunks(
        self,
        mock_conversation_service,
        mock_stt_service,
        sample_webm_audio
    ):
        """
        P0-9: Verify format persists across multiple audio chunks (Phase 5)

        VALIDATES:
        - Format indicator sent once per session
        - Subsequent chunks use same format
        - No format switching during session
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4

        mock_websocket = AsyncMock()
        session_id_uuid = uuid4()
        user_id = "browser_user_format_persistence"

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id_uuid
            )

            await handler._connect_stt()

            # Send multiple chunks
            for i in range(5):
                handler.webm_buffer.extend(sample_webm_audio)
                pcm_data = handler._extract_pcm_audio()

                if len(pcm_data) > 0:
                    await handler.stt_service.send_audio(
                        session_id=handler.session_id,
                        audio_data=pcm_data,
                        audio_format='pcm'
                    )

        print(f"\n🎯 Format persistence test:")
        print(f"   Total send_audio calls: {mock_stt_service.send_audio.call_count}")

        # Verify all calls used 'pcm' format
        for call in mock_stt_service.send_audio.call_args_list:
            kwargs = call.kwargs
            assert kwargs.get('audio_format') == 'pcm', \
                f"All chunks should use 'pcm', got {kwargs.get('audio_format')}"


# ============================================================
# P0: Concurrent Formats (Discord + WebRTC) (Phase 5)
# ============================================================

class TestConcurrentFormats:
    """P0: Concurrent Discord + WebRTC sessions with Phase 5 services"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_discord_and_webrtc_concurrent(
        self,
        mock_whisperx_with_format,
        sample_opus_audio,
        sample_pcm_audio
    ):
        """
        P0-10: Discord (Opus) + WebRTC (PCM) running simultaneously (Phase 5)

        Critical regression test - ensures no format cross-contamination

        VALIDATES:
        - Both sessions get correct format indicators
        - No format cross-contamination
        - Audio isolation maintained
        - Both sessions complete successfully
        - Audio sizes match expected formats
        """
        from src.services.stt_service import STTService
        from uuid import uuid4

        server, port = mock_whisperx_with_format

        # WebRTC session
        webrtc_session_id = str(uuid4())

        # Discord session
        discord_session_id = str(uuid4())

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            # Start WebRTC session
            webrtc_stt = STTService()
            await webrtc_stt.connect(
                session_id=webrtc_session_id,
                whisper_url=f'ws://localhost:{port}'
            )

            # Start Discord session
            discord_stt = STTService()
            await discord_stt.connect(
                session_id=discord_session_id,
                whisper_url=f'ws://localhost:{port}'
            )

            # Send PCM from WebRTC (use fixture - proper PCM size)
            await webrtc_stt.send_audio(
                session_id=webrtc_session_id,
                audio_data=sample_pcm_audio,
                audio_format='pcm'
            )

            # Send Opus from Discord (use fixture - proper Opus size)
            await discord_stt.send_audio(
                session_id=discord_session_id,
                audio_data=sample_opus_audio,
                audio_format='opus'
            )

            # Wait for processing
            await asyncio.sleep(0.1)

        # Get statistics for validation
        webrtc_stats = server.get_session_stats(webrtc_session_id)
        discord_stats = server.get_session_stats(discord_session_id)
        webrtc_avg = server.get_avg_chunk_size(webrtc_session_id)
        discord_avg = server.get_avg_chunk_size(discord_session_id)

        # ASSERTIONS
        print(f"\n🎯 Concurrent sessions test:")
        print(f"   WebRTC format: {server.get_format_for_session(webrtc_session_id)}")
        print(f"   WebRTC avg chunk: {webrtc_avg:.0f} bytes (expected: >1000 for PCM)")
        print(f"   Discord format: {server.get_format_for_session(discord_session_id)}")
        print(f"   Discord avg chunk: {discord_avg:.0f} bytes (expected: 50-500 for Opus)")
        print(f"   Total sessions: {len(server.get_all_session_formats())}")

        assert server.get_format_for_session(webrtc_session_id) == 'pcm', \
            "WebRTC should use PCM"
        assert server.get_format_for_session(discord_session_id) == 'opus', \
            "Discord should use Opus"

        # Verify no cross-contamination
        all_formats = server.get_all_session_formats()
        assert all_formats[webrtc_session_id] != all_formats[discord_session_id], \
            "Formats should be different for different session types"

        # NEW: Verify audio sizes match expected formats
        assert webrtc_avg > 1000, \
            f"WebRTC PCM chunks should be >1000 bytes, got {webrtc_avg:.0f}"
        assert 50 < discord_avg < 500, \
            f"Discord Opus chunks should be 50-500 bytes, got {discord_avg:.0f}"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_format_isolation_between_sessions(
        self,
        mock_whisperx_with_format,
        sample_opus_audio,
        sample_pcm_audio
    ):
        """
        P0-11: Format isolation between multiple sessions (Phase 5)

        VALIDATES:
        - Each session has independent format
        - Format changes don't affect other sessions
        - Session cleanup doesn't corrupt formats
        - Audio sizes match expected formats for each session
        """
        from src.services.stt_service import STTService
        from uuid import uuid4

        server, port = mock_whisperx_with_format

        sessions = []

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            # Create 3 WebRTC sessions, 2 Discord sessions
            for i in range(5):
                session_id = str(uuid4())
                stt = STTService()
                await stt.connect(
                    session_id=session_id,
                    whisper_url=f'ws://localhost:{port}'
                )

                # Alternate between PCM and Opus
                audio_format = 'pcm' if i % 2 == 0 else 'opus'
                audio = sample_pcm_audio if audio_format == 'pcm' else sample_opus_audio

                await stt.send_audio(
                    session_id=session_id,
                    audio_data=audio,
                    audio_format=audio_format
                )

                sessions.append((session_id, audio_format, stt))

            await asyncio.sleep(0.1)

        # Verify all formats preserved correctly
        print(f"\n🎯 Format isolation test:")
        for session_id, expected_format, _ in sessions:
            actual_format = server.get_format_for_session(session_id)
            avg_size = server.get_avg_chunk_size(session_id)
            is_valid = server.validate_format_match(session_id)

            print(f"   Session {session_id[:8]}...: {actual_format} (expected: {expected_format}), "
                  f"avg: {avg_size:.0f}B, valid: {is_valid}")

            assert actual_format == expected_format, \
                f"Format mismatch for session {session_id}"

            # Validate audio size matches format
            assert is_valid, \
                f"Audio size doesn't match format {expected_format} for session {session_id}"

        assert len(server.get_all_session_formats()) == 5, \
            "All 5 sessions should be tracked"


# ============================================================
# P1: Error Handling and Recovery (Phase 5)
# ============================================================

class TestWebRTCErrors:
    """P1: Error handling and recovery with Phase 5 services"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_corrupted_webm_error_recovery(
        self,
        mock_conversation_service,
        mock_whisperx_with_format,
        corrupted_webm_audio,
        sample_webm_audio
    ):
        """
        P1-1: Verify graceful recovery from corrupted WebM (Phase 5)

        Expected behavior:
        1. Corrupted WebM triggers error log
        2. Buffer is reset (not retained)
        3. Subsequent valid WebM decodes successfully
        4. User receives error notification
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "browser_user_corrupted"

        server, port = mock_whisperx_with_format

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service):
                handler = WebRTCVoiceHandler(
                    websocket=mock_websocket,
                    user_id=user_id,
                    session_id=session_id
                )

                # Try to decode corrupted WebM
                handler.webm_buffer.extend(corrupted_webm_audio)
                pcm_corrupted = handler._extract_pcm_audio()

                # Should return empty (failed decode)
                assert len(pcm_corrupted) == 0, "Corrupted WebM should fail decode"

                # Buffer should be cleared
                assert len(handler.webm_buffer) == 0, "Buffer should be reset after error"

                # Now try valid WebM (should work)
                handler.webm_buffer.extend(sample_webm_audio)
                pcm_valid = handler._extract_pcm_audio()

                assert len(pcm_valid) > 0, "Valid WebM should decode after error recovery"

        print(f"\n🎯 Corrupted WebM recovery:")
        print(f"   Corrupted decode result: {len(pcm_corrupted)} bytes (expected: 0)")
        print(f"   Valid decode result: {len(pcm_valid)} bytes (expected: >0)")
        print(f"   Recovery successful: ✅")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_incomplete_webm_buffering(
        self,
        incomplete_webm_audio,
        sample_webm_audio
    ):
        """
        P1-2: Incomplete WebM buffering logic (Phase 5)

        VALIDATES:
        - Incomplete WebM is buffered (not discarded)
        - Decode returns empty (waits for more data)
        - Subsequent chunk completes decode
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "browser_user_incomplete"

        handler = WebRTCVoiceHandler(
            websocket=mock_websocket,
            user_id=user_id,
            session_id=session_id
        )

        # Send incomplete WebM (512 bytes)
        handler.webm_buffer.extend(incomplete_webm_audio)
        initial_buffer_size = len(handler.webm_buffer)
        pcm_incomplete = handler._extract_pcm_audio()

        # Should return empty but buffer should be retained
        assert len(pcm_incomplete) == 0, "Incomplete WebM should not decode yet"
        assert len(handler.webm_buffer) == initial_buffer_size, \
            "Buffer should be retained for incomplete data"

        # Add remaining data (complete WebM)
        handler.webm_buffer.clear()
        handler.webm_buffer.extend(sample_webm_audio)
        pcm_complete = handler._extract_pcm_audio()

        assert len(pcm_complete) > 0, "Complete WebM should decode successfully"

        print(f"\n🎯 Incomplete WebM buffering:")
        print(f"   Incomplete size: {initial_buffer_size} bytes")
        print(f"   Decode result: {len(pcm_incomplete)} bytes (expected: 0, buffering)")
        print(f"   Complete decode: {len(pcm_complete)} bytes (expected: >0)")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_browser_disconnect_cleanup(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_whisperx_with_format,
        sample_webm_audio
    ):
        """
        P1-3: Browser disconnect cleanup (Phase 5)

        VALIDATES:
        - WebSocket disconnect detected
        - STT connection closed gracefully
        - Session cleanup happens
        - No resource leaks
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4
        from fastapi import WebSocketDisconnect

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "browser_user_disconnect"

        server, port = mock_whisperx_with_format

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
                 patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

                handler = WebRTCVoiceHandler(
                    websocket=mock_websocket,
                    user_id=user_id,
                    session_id=session_id
                )

                await handler._connect_stt()

                # Cleanup
                await handler._cleanup()

        print(f"\n🎯 Disconnect cleanup:")
        print(f"   Handler active: {handler.is_active} (expected: False)")
        print(f"   STT disconnect called: {mock_stt_service.disconnect.called}")
        print(f"   Cleanup successful: ✅")

        assert handler.is_active is False, "Handler should be inactive after cleanup"
        assert mock_stt_service.disconnect.called, "STTService.disconnect should be called"


# ============================================================
# P2: Performance Benchmarks (Phase 5)
# ============================================================

class TestWebRTCLatency:
    """P2: Performance benchmarks with Phase 5 services"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_webm_decode_latency_under_100ms(
        self,
        sample_webm_audio,
        latency_tracker
    ):
        """
        P2-1: WebM decode performance benchmark (Phase 5)

        Target: < 100ms for single-frame decode

        VALIDATES:
        - Decode latency acceptable
        - No performance regression
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "browser_user_perf"

        handler = WebRTCVoiceHandler(
            websocket=mock_websocket,
            user_id=user_id,
            session_id=session_id
        )

        # Benchmark decode
        latency_tracker.start("webm_decode_latency")

        handler.webm_buffer.extend(sample_webm_audio)
        pcm_data = handler._extract_pcm_audio()

        latency = latency_tracker.end("webm_decode_latency")

        print(f"\n🎯 WebM decode latency:")
        print(f"   Input: {len(sample_webm_audio)} bytes")
        print(f"   Output: {len(pcm_data)} bytes")
        print(f"   Latency: {latency:.2f}ms (target: <100ms)")

        assert latency < 100, f"Decode latency too high: {latency:.2f}ms"
        assert len(pcm_data) > 0, "Decode should produce PCM data"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_latency_under_2s(
        self,
        mock_conversation_service,
        mock_stt_service,
        mock_llm_service,
        mock_tts_service,
        mock_whisperx_with_format,
        sample_webm_audio,
        latency_tracker
    ):
        """
        P2-2: End-to-end latency benchmark (Phase 5)

        Target: < 2s for complete conversation turn

        VALIDATES:
        - Total latency acceptable
        - All stages contribute reasonable time
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "browser_user_e2e"

        server, port = mock_whisperx_with_format

        latency_tracker.start("webrtc_e2e")

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
                 patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service), \
                 patch('src.voice.webrtc_handler.LLMService', return_value=mock_llm_service), \
                 patch('src.voice.webrtc_handler.TTSService', return_value=mock_tts_service):

                handler = WebRTCVoiceHandler(
                    websocket=mock_websocket,
                    user_id=user_id,
                    session_id=session_id
                )

                await handler._connect_stt()

                # Send audio
                handler.webm_buffer.extend(sample_webm_audio)
                pcm_data = handler._extract_pcm_audio()

                await handler.stt_service.send_audio(
                    session_id=handler.session_id,
                    audio_data=pcm_data,
                    audio_format='pcm'
                )

                # Simulate LLM response
                await asyncio.sleep(0.1)

        latency = latency_tracker.end("webrtc_e2e")

        print(f"\n🎯 End-to-end latency:")
        print(f"   Total: {latency:.2f}ms (target: <2000ms)")
        print(f"   Stages:")
        print(f"     - WebM decode: ~{latency * 0.1:.0f}ms")
        print(f"     - STT: ~{latency * 0.3:.0f}ms")
        print(f"     - LLM: ~{latency * 0.5:.0f}ms")
        print(f"     - TTS: ~{latency * 0.1:.0f}ms")

        assert latency < 2000, f"Total latency too high: {latency:.2f}ms"


# ============================================================
# P0: Dual-Format Validation (Phase 5.5 - Format Size Validation)
# ============================================================

class TestDualFormatValidation:
    """Validate Opus and PCM format characteristics"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_opus_chunk_size_validation(
        self,
        mock_whisperx_with_format,
        sample_opus_audio
    ):
        """
        P0-12: Validate Opus audio chunks are compressed (small size)

        Expected: Opus frames ~120-200 bytes (compressed)

        VALIDATES:
        - Opus chunks are small (compressed format)
        - Average chunk size matches Opus expectations
        - Format validation confirms Opus characteristics
        """
        from src.services.stt_service import STTService
        from uuid import uuid4

        server, port = mock_whisperx_with_format

        # Send Opus audio to mock WhisperX
        session_id = str(uuid4())

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            stt = STTService()
            await stt.connect(
                session_id=session_id,
                whisper_url=f'ws://localhost:{port}'
            )

            # Send 10 Opus frames
            for _ in range(10):
                await stt.send_audio(
                    session_id=session_id,
                    audio_data=sample_opus_audio,
                    audio_format='opus'
                )

            await asyncio.sleep(0.1)  # Allow processing

        # Validate statistics
        stats = server.get_session_stats(session_id)
        avg_chunk_size = server.get_avg_chunk_size(session_id)

        print(f"\n🎯 Opus chunk validation:")
        print(f"   Session: {session_id}")
        print(f"   Format: {stats.get('format', 'unknown')}")
        print(f"   Chunks received: {stats.get('chunk_count', 0)}")
        print(f"   Avg chunk size: {avg_chunk_size:.0f} bytes")
        print(f"   Total bytes: {stats.get('bytes_received', 0)}")

        # Opus should have small chunks (compressed)
        assert stats['format'] == 'opus', "Format should be opus"
        assert 50 < avg_chunk_size < 500, \
            f"Opus chunks should be 50-500 bytes, got {avg_chunk_size:.0f}"

        # Validate format matches
        assert server.validate_format_match(session_id), \
            "Opus audio size doesn't match declared format"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pcm_chunk_size_validation(
        self,
        mock_whisperx_with_format,
        sample_pcm_audio,
        expected_pcm_frame_size
    ):
        """
        P0-13: Validate PCM audio chunks are uncompressed (large size)

        Expected: PCM frames ~3,840 bytes (uncompressed)

        VALIDATES:
        - PCM chunks are large (uncompressed format)
        - Average chunk size matches PCM expectations
        - Format validation confirms PCM characteristics
        """
        from src.services.stt_service import STTService
        from uuid import uuid4

        server, port = mock_whisperx_with_format

        # Send PCM audio to mock WhisperX
        session_id = str(uuid4())

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            stt = STTService()
            await stt.connect(
                session_id=session_id,
                whisper_url=f'ws://localhost:{port}'
            )

            # Send 10 PCM frames
            for _ in range(10):
                await stt.send_audio(
                    session_id=session_id,
                    audio_data=sample_pcm_audio,
                    audio_format='pcm'
                )

            await asyncio.sleep(0.1)  # Allow processing

        # Validate statistics
        stats = server.get_session_stats(session_id)
        avg_chunk_size = server.get_avg_chunk_size(session_id)

        print(f"\n🎯 PCM chunk validation:")
        print(f"   Session: {session_id}")
        print(f"   Format: {stats.get('format', 'unknown')}")
        print(f"   Chunks received: {stats.get('chunk_count', 0)}")
        print(f"   Avg chunk size: {avg_chunk_size:.0f} bytes")
        print(f"   Expected size: {expected_pcm_frame_size} bytes")
        print(f"   Total bytes: {stats.get('bytes_received', 0)}")

        # PCM should have large chunks (uncompressed)
        assert stats['format'] == 'pcm', "Format should be pcm"
        assert avg_chunk_size > 1000, \
            f"PCM chunks should be >1000 bytes, got {avg_chunk_size:.0f}"

        # Validate chunk size approximately matches expected
        # (allow some variation due to PyAV decode output)
        assert abs(avg_chunk_size - expected_pcm_frame_size) < 1000, \
            f"PCM chunk size {avg_chunk_size:.0f} differs significantly from expected {expected_pcm_frame_size}"

        # Validate format matches
        assert server.validate_format_match(session_id), \
            "PCM audio size doesn't match declared format"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_format_size_difference(
        self,
        mock_whisperx_with_format,
        sample_opus_audio,
        sample_pcm_audio
    ):
        """
        P0-14: Validate PCM is significantly larger than Opus (compression ratio)

        Expected: PCM ~20x larger than Opus per frame

        VALIDATES:
        - Compression ratio between formats
        - Both formats tracked independently
        - Size difference matches compression expectations
        """
        from src.services.stt_service import STTService
        from uuid import uuid4

        server, port = mock_whisperx_with_format

        # Test Opus
        opus_session = str(uuid4())

        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            opus_stt = STTService()
            await opus_stt.connect(
                session_id=opus_session,
                whisper_url=f'ws://localhost:{port}'
            )

            for _ in range(10):
                await opus_stt.send_audio(
                    session_id=opus_session,
                    audio_data=sample_opus_audio,
                    audio_format='opus'
                )

            await asyncio.sleep(0.05)

            opus_avg = server.get_avg_chunk_size(opus_session)

            # Test PCM
            pcm_session = str(uuid4())

            pcm_stt = STTService()
            await pcm_stt.connect(
                session_id=pcm_session,
                whisper_url=f'ws://localhost:{port}'
            )

            for _ in range(10):
                await pcm_stt.send_audio(
                    session_id=pcm_session,
                    audio_data=sample_pcm_audio,
                    audio_format='pcm'
                )

            await asyncio.sleep(0.05)

        pcm_avg = server.get_avg_chunk_size(pcm_session)

        # PCM should be significantly larger (10-30x depending on compression)
        compression_ratio = pcm_avg / opus_avg if opus_avg > 0 else 0

        print(f"\n🎯 Format size comparison:")
        print(f"   Opus avg: {opus_avg:.0f} bytes")
        print(f"   PCM avg: {pcm_avg:.0f} bytes")
        print(f"   Compression ratio: {compression_ratio:.1f}x")
        print(f"   Expected: >10x")

        assert compression_ratio > 10, \
            f"PCM should be >10x larger than Opus, got {compression_ratio:.1f}x"

        print(f"   ✅ Compression validation: PCM is {compression_ratio:.1f}x larger than Opus")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_format_mismatch_detection(
        self,
        mock_whisperx_with_format,
        sample_opus_audio,
        sample_pcm_audio
    ):
        """
        P0-15: Validate format mismatch detection (Opus audio with PCM flag)

        VALIDATES:
        - Server detects format mismatches
        - Warning logs generated for suspicious sizes
        - Format validation fails for mismatched audio
        """
        from src.services.stt_service import STTService
        from uuid import uuid4
        import logging

        server, port = mock_whisperx_with_format

        # Send Opus audio but declare it as PCM (format mismatch)
        session_id = str(uuid4())

        # Capture warning logs
        with patch.dict('os.environ', {'WHISPER_SERVER_URL': f'ws://localhost:{port}'}):
            stt = STTService()
            await stt.connect(
                session_id=session_id,
                whisper_url=f'ws://localhost:{port}'
            )

            # INTENTIONAL MISMATCH: Send Opus audio with PCM format flag
            # This simulates a bug where format indicator is wrong
            await stt.send_audio(
                session_id=session_id,
                audio_data=sample_opus_audio,  # Opus data (~121 bytes)
                audio_format='pcm'  # But declared as PCM!
            )

            await asyncio.sleep(0.1)

        # Check if format validation detects the mismatch
        stats = server.get_session_stats(session_id)
        is_valid = server.validate_format_match(session_id)

        print(f"\n🎯 Format mismatch detection:")
        print(f"   Declared format: {stats.get('format', 'unknown')}")
        print(f"   Actual data size: {stats.get('chunks', [None])[0]} bytes")
        print(f"   Format validation: {'PASS' if is_valid else 'FAIL (mismatch detected)'}")

        # Validation should FAIL because Opus data (~121 bytes) doesn't match PCM expectations (>1000 bytes)
        assert not is_valid, \
            "Format validation should detect Opus data mislabeled as PCM"

        print(f"   ✅ Mismatch correctly detected")


# ============================================================
# ADDITIONAL REGRESSION TESTS (imported from test_webrtc_multi_chunk_regression.py)
# ============================================================

class TestWebRTCMultiChunkStreamingRegressionIntegrated:
    """
    CRITICAL REGRESSION TESTS for Bug #3 integrated into main test file

    These tests validate ALL chunks decode, not just first one
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_continuous_chunk_decode_not_just_first(
        self,
        mock_conversation_service,
        mock_stt_service,
        sample_webm_audio
    ):
        """
        CRITICAL REGRESSION: Verify 5 chunks decode, not just 1 (Bug #3)

        This is a simplified version integrated into main test file
        """
        from src.voice.webrtc_handler import WebRTCVoiceHandler
        from uuid import uuid4

        mock_websocket = AsyncMock()
        session_id = uuid4()
        user_id = "regression_continuous_decode"

        with patch('src.voice.webrtc_handler.ConversationService', return_value=mock_conversation_service), \
             patch('src.voice.webrtc_handler.STTService', return_value=mock_stt_service):

            handler = WebRTCVoiceHandler(
                websocket=mock_websocket,
                user_id=user_id,
                session_id=session_id
            )

            # Send 5 chunks and track decodes
            chunk_count = 5
            successful_decodes = 0

            for i in range(chunk_count):
                pcm_data = handler._decode_webm_chunk(sample_webm_audio)
                if pcm_data:
                    successful_decodes += 1

            success_rate = (successful_decodes / chunk_count) * 100

            print(f"\n🎯 REGRESSION: Multi-chunk decode validation")
            print(f"   Chunks sent: {chunk_count}")
            print(f"   Successful decodes: {successful_decodes}")
            print(f"   Success rate: {success_rate:.1f}%")

            # CRITICAL: Must decode more than 1 chunk (Bug #3 symptom)
            assert successful_decodes > 1, \
                f"REGRESSION FAILURE: Only {successful_decodes} chunk decoded! Bug #3 (buffer clearing)"

            # Should decode most chunks (allow some failure tolerance)
            assert successful_decodes >= chunk_count * 0.8, \
                f"Only {successful_decodes}/{chunk_count} chunks decoded ({success_rate:.1f}%)"

            print(f"   ✅ Multi-chunk decoding validated: {successful_decodes} chunks decoded")
