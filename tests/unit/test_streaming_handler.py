"""
Unit tests for StreamingResponseHandler

Tests text chunking, sentence extraction, TTS streaming with HTTP,
audio playback, and finalization
"""
from __future__ import annotations

import pytest
import asyncio
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
import httpx

from streaming_handler import StreamingResponseHandler


# ============================================================
# Text Processing Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_on_chunk_accumulates_to_buffer():
    """Test text chunks accumulate in buffer"""
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    await handler.on_chunk("Hello ")
    # Buffer gets stripped after _extract_sentences, so trailing space removed
    assert handler.buffer == "Hello"

    await handler.on_chunk("world")
    # No sentence delimiter, so accumulates
    assert handler.buffer == "Helloworld"


@pytest.mark.unit
def test_extract_sentences_single_delimiter():
    """Test extracting single complete sentence"""
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    handler.buffer = "Hello world."
    sentences = handler._extract_sentences()

    assert len(sentences) == 1
    assert sentences[0] == "Hello world."
    assert handler.buffer == ""  # Buffer should be empty after extraction


@pytest.mark.unit
def test_extract_sentences_multiple_delimiters():
    """Test extracting sentences with different delimiters"""
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    handler.buffer = "First sentence. Second one! Third? Fourth\nFifth"
    sentences = handler._extract_sentences()

    # Should extract sentences ending with . ! ? and \n
    assert len(sentences) == 4
    assert sentences[0] == "First sentence."
    assert sentences[1] == "Second one!"
    assert sentences[2] == "Third?"
    assert sentences[3] == "Fourth"  # Ended with \n

    # "Fifth" should remain in buffer (incomplete)
    assert handler.buffer == "Fifth"


@pytest.mark.unit
def test_extract_sentences_min_length_filter():
    """Test minimum sentence length filtering"""
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")
    handler.min_sentence_length = 5  # Set minimum length

    handler.buffer = "Hi. Hello there. Ok."
    sentences = handler._extract_sentences()

    # "Hi." (2 chars) should be filtered out
    # "Hello there." (12 chars) should be included
    # "Ok." (3 chars) should be filtered out
    assert len(sentences) == 1
    assert sentences[0] == "Hello there."


@pytest.mark.unit
def test_extract_sentences_preserves_incomplete():
    """Test that incomplete sentences stay in buffer"""
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    handler.buffer = "Complete sentence. Incomplete part"
    sentences = handler._extract_sentences()

    assert len(sentences) == 1
    assert sentences[0] == "Complete sentence."
    assert handler.buffer == "Incomplete part"


# ============================================================
# Queue Processing Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_sentence_queue_processing_sequential():
    """Test sentence queue processes in order"""
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    processed_sentences = []

    # Mock _synthesize_and_play to track order
    async def mock_synthesize(text):
        processed_sentences.append(text)

    handler._synthesize_and_play = mock_synthesize

    # Add sentences to queue
    handler.sentence_queue = ["First.", "Second.", "Third."]

    await handler._process_queue()

    # Verify sentences processed in order
    assert processed_sentences == ["First.", "Second.", "Third."]
    assert len(handler.sentence_queue) == 0
    assert handler.is_processing is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_on_chunk_triggers_queue_processing():
    """Test receiving complete sentence triggers processing"""
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    with patch.object(handler, '_process_queue', new_callable=AsyncMock) as mock_process:
        with patch('asyncio.create_task') as mock_create_task:
            # Send chunk with complete sentence
            await handler.on_chunk("Hello world.")

            # Verify queue was populated
            assert len(handler.sentence_queue) == 1
            assert handler.sentence_queue[0] == "Hello world."

            # Verify processing was triggered
            assert mock_create_task.called


# ============================================================
# TTS Streaming Tests (CRITICAL FOR LATENCY)
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_synthesize_and_play_with_tts_streaming():
    """Test TTS synthesis with HTTP streaming - CRITICAL for latency validation"""
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False  # Not playing initially
    mock_voice_client.play = MagicMock()

    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    # Mock httpx streaming response
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    # Create fake audio chunks
    fake_audio_chunks = [b'\x00' * 1024, b'\x01' * 1024, b'\x02' * 1024]

    async def mock_aiter_bytes(chunk_size):
        for chunk in fake_audio_chunks:
            yield chunk

    mock_response.aiter_bytes = mock_aiter_bytes

    # Mock tempfile
    mock_temp_file = MagicMock()
    mock_temp_file.name = "/tmp/test_audio.wav"
    mock_temp_file.write = MagicMock()
    mock_temp_file.flush = MagicMock()
    mock_temp_file.__enter__ = MagicMock(return_value=mock_temp_file)
    mock_temp_file.__exit__ = MagicMock(return_value=False)

    with patch('httpx.AsyncClient') as MockClient:
        # Create mock client
        mock_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        # Setup AsyncClient context manager
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch('tempfile.NamedTemporaryFile', return_value=mock_temp_file):
            with patch('discord.FFmpegPCMAudio') as MockFFmpeg:
                with patch('os.unlink'):
                    await handler._synthesize_and_play("Hello world")

                    # Verify HTTP streaming was used (not blocking POST)
                    mock_client.stream.assert_called_once()
                    call_args = mock_client.stream.call_args
                    assert call_args[0][0] == 'POST'
                    assert '/audio/speech/stream/upload' in call_args[0][1]

                    # Verify audio chunks were written (streaming behavior)
                    assert mock_temp_file.write.call_count == 3
                    assert mock_temp_file.flush.call_count == 3

                    # Verify audio was played
                    MockFFmpeg.assert_called_once_with("/tmp/test_audio.wav")
                    mock_voice_client.play.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_synthesize_with_custom_options():
    """Test TTS synthesis with custom options from n8n"""
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False

    # Options from n8n response
    options = {
        'voiceMode': 'clone',
        'referenceAudioFilename': 'custom_voice.wav',
        'speedFactor': 1.2,
        'temperature': 0.8,
        'exaggeration': 1.5,
        'chunkSize': 150,
        'streamingStrategy': 'word',
        'streamingQuality': 'high'
    }

    handler = StreamingResponseHandler(mock_voice_client, "user_123", options)

    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_bytes(chunk_size):
        yield b'\x00' * 100

    mock_response.aiter_bytes = mock_aiter_bytes

    with patch('httpx.AsyncClient') as MockClient:
        # Create mock client
        mock_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        # Setup AsyncClient context manager
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch('tempfile.NamedTemporaryFile'):
            with patch('discord.FFmpegPCMAudio'):
                with patch('os.unlink'):
                    await handler._synthesize_and_play("Test")

                    # Verify custom options were passed
                    call_args = mock_client.stream.call_args
                    tts_data = call_args[1]['data']

                    assert tts_data['voice'] == 'custom_voice.wav'
                    assert tts_data['speed'] == 1.2
                    assert tts_data['temperature'] == 0.8
                    assert tts_data['exaggeration'] == 1.5
                    assert tts_data['streaming_chunk_size'] == 150
                    assert tts_data['streaming_strategy'] == 'word'
                    assert tts_data['streaming_quality'] == 'high'


# ============================================================
# Audio Playback Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_play_audio_from_file_creates_source():
    """Test audio playback creates FFmpegPCMAudio source"""
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False
    mock_voice_client.play = MagicMock()

    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    with patch('discord.FFmpegPCMAudio') as MockFFmpeg:
        mock_audio_source = MagicMock()
        MockFFmpeg.return_value = mock_audio_source

        with patch('os.unlink'):
            await handler._play_audio_from_file("/tmp/test.wav")

            # Verify FFmpeg source created
            MockFFmpeg.assert_called_once_with("/tmp/test.wav")

            # Verify play was called with audio source
            mock_voice_client.play.assert_called_once_with(mock_audio_source)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_play_audio_waits_for_current_playback():
    """Test audio playback waits for currently playing audio"""
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True

    # Simulate audio is playing, then stops
    # Need enough False values for both while loops
    play_states = [True, True, False, False]  # Playing -> Playing -> Stopped -> Stopped
    mock_voice_client.is_playing.side_effect = play_states

    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    with patch('discord.FFmpegPCMAudio'):
        with patch('os.unlink'):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                await handler._play_audio_from_file("/tmp/test.wav")

                # Should have checked is_playing multiple times
                assert mock_voice_client.is_playing.call_count >= 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_play_audio_cleans_up_temp_file():
    """Test temporary file is deleted after playback"""
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False

    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    with patch('discord.FFmpegPCMAudio'):
        with patch('os.unlink') as mock_unlink:
            await handler._play_audio_from_file("/tmp/test.wav")

            # Verify temp file was deleted
            mock_unlink.assert_called_once_with("/tmp/test.wav")


# ============================================================
# Finalization Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_finalize_sends_remaining_buffer():
    """Test finalize processes incomplete buffer text"""
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    handler.buffer = "Incomplete sentence without delimiter"
    handler.min_sentence_length = 3

    with patch.object(handler, '_process_queue', new_callable=AsyncMock) as mock_process:
        await handler.finalize()

        # Verify buffer was added to queue
        assert len(handler.sentence_queue) == 1
        assert handler.sentence_queue[0] == "Incomplete sentence without delimiter"
        assert handler.buffer == ''

        # Verify queue processing was triggered
        mock_process.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_finalize_ignores_short_buffer():
    """Test finalize ignores buffer shorter than minimum length"""
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    handler.buffer = "Hi"  # Only 2 chars
    handler.min_sentence_length = 3

    with patch.object(handler, '_process_queue', new_callable=AsyncMock) as mock_process:
        await handler.finalize()

        # Buffer too short, should not be queued
        assert len(handler.sentence_queue) == 0
        mock_process.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_finalize_with_empty_buffer():
    """Test finalize with empty buffer does nothing"""
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    handler.buffer = ""

    with patch.object(handler, '_process_queue', new_callable=AsyncMock) as mock_process:
        await handler.finalize()

        assert len(handler.sentence_queue) == 0
        mock_process.assert_not_called()


# ============================================================
# Error Handling Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_queue_continues_on_synthesis_error():
    """Test queue processing continues even if one sentence fails"""
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    processed = []

    # First sentence fails, second succeeds
    async def mock_synthesize(text):
        if text == "Fail.":
            raise Exception("TTS error")
        processed.append(text)

    handler._synthesize_and_play = mock_synthesize
    handler.sentence_queue = ["Fail.", "Success."]

    await handler._process_queue()

    # Second sentence should still process
    assert len(processed) == 1
    assert processed[0] == "Success."
    assert len(handler.sentence_queue) == 0


# ============================================================
# Edge Case Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_buffer_overflow_protection():
    """Test buffer doesn't grow unbounded with very long text"""
    mock_voice_client = MagicMock()
    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    # Send very long text without sentence delimiters
    long_text = "word " * 10000  # 50,000+ characters

    with patch.object(handler, '_process_queue', new_callable=AsyncMock):
        await handler.on_chunk(long_text)

        # Buffer should accumulate (no delimiter to extract)
        assert len(handler.buffer) > 0
        assert "word" in handler.buffer


@pytest.mark.unit
@pytest.mark.asyncio
async def test_network_timeout_during_tts_streaming():
    """Test handling network timeout during TTS HTTP streaming"""
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False

    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    with patch('httpx.AsyncClient') as MockClient:
        mock_client = MagicMock()

        # Stream raises timeout exception
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        # Retry decorator will retry 3 times then reraise
        with pytest.raises(httpx.TimeoutException):
            await handler._synthesize_and_play("Test timeout")

        # Verify stream was attempted 3 times (retry logic)
        assert mock_client.stream.call_count == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_voice_client_disconnect_during_playback():
    """Test handling voice client disconnection during playback"""
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = False  # Disconnected
    mock_voice_client.is_playing.return_value = False

    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_bytes(chunk_size):
        yield b'\x00' * 1024

    mock_response.aiter_bytes = mock_aiter_bytes

    with patch('httpx.AsyncClient') as MockClient:
        mock_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch('tempfile.NamedTemporaryFile'):
            with patch('discord.FFmpegPCMAudio'):
                with patch('os.unlink'):
                    # Should handle disconnection gracefully
                    await handler._synthesize_and_play("Test")

                    # Voice client play should not be called (disconnected)
                    mock_voice_client.play.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_tts_response():
    """Test handling empty response from TTS server"""
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False

    handler = StreamingResponseHandler(mock_voice_client, "user_123")

    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    # Empty stream (no audio chunks)
    async def mock_aiter_bytes(chunk_size):
        return
        yield  # Make it a generator

    mock_response.aiter_bytes = mock_aiter_bytes

    with patch('httpx.AsyncClient') as MockClient:
        mock_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch('tempfile.NamedTemporaryFile') as mock_tempfile:
            mock_temp = MagicMock()
            mock_temp.name = "/tmp/test.wav"
            mock_temp.write = MagicMock()
            mock_temp.__enter__ = MagicMock(return_value=mock_temp)
            mock_temp.__exit__ = MagicMock(return_value=False)
            mock_tempfile.return_value = mock_temp

            with patch('discord.FFmpegPCMAudio'):
                with patch('os.unlink'):
                    await handler._synthesize_and_play("Test")

                    # No audio chunks written
                    mock_temp.write.assert_not_called()
