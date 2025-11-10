"""
Integration tests for streaming pipeline

Tests the full flow of components working together:
- SentenceParser → TTSQueueManager → AudioPlaybackQueue
- Error handling across components
- Interruption handling during active streaming
- Metrics tracking across pipeline
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from src.services.sentence_parser import SentenceParser
from src.services.tts_queue_manager import TTSQueueManager
from src.services.audio_playback_queue import AudioPlaybackQueue


@pytest.fixture
def mock_tts_service():
    """Mock TTS service for testing"""
    service = Mock()
    service.synthesize_speech = AsyncMock(return_value=b"fake_audio_data")
    return service


@pytest.fixture
def mock_voice_client():
    """Mock Discord VoiceClient for testing"""
    client = Mock()
    client.is_connected = Mock(return_value=True)
    client.is_playing = Mock(return_value=False)
    client.play = Mock()
    client.stop = Mock()
    return client


@pytest.fixture
async def streaming_pipeline(mock_tts_service, mock_voice_client):
    """Create full streaming pipeline for testing"""
    # Create sentence parser
    parser = SentenceParser(min_sentence_length=10)

    # Track pipeline events
    synthesized_sentences = []
    played_audio = []

    async def on_tts_complete(audio_bytes: bytes, metadata: dict):
        """Called when TTS completes"""
        synthesized_sentences.append(metadata.get('sentence', ''))
        # Enqueue to audio playback
        await playback_queue.enqueue_audio(audio_bytes, metadata)

    async def on_audio_complete(metadata: dict):
        """Called when audio playback completes"""
        played_audio.append(metadata.get('sentence', ''))

    # Create TTS queue manager
    tts_manager = TTSQueueManager(
        max_concurrent=2,
        tts_service=mock_tts_service,
        on_complete=on_tts_complete,
        on_error=AsyncMock()
    )

    # Create audio playback queue
    playback_queue = AudioPlaybackQueue(
        voice_client=mock_voice_client,
        on_complete=on_audio_complete,
        on_error=AsyncMock()
    )

    # Start both queues
    await tts_manager.start()
    await playback_queue.start()

    yield {
        'parser': parser,
        'tts_manager': tts_manager,
        'playback_queue': playback_queue,
        'synthesized': synthesized_sentences,
        'played': played_audio
    }

    # Cleanup
    await tts_manager.stop()
    await playback_queue.stop()


class TestFullPipelineFlow:
    """Test complete flow from text chunks to audio playback"""

    @pytest.mark.asyncio
    async def test_single_sentence_flow(self, streaming_pipeline):
        """Test single sentence flows through entire pipeline"""
        parser = streaming_pipeline['parser']
        tts_manager = streaming_pipeline['tts_manager']

        # Add text chunk with complete sentence
        sentences = parser.add_chunk("Hello world! How are you?")

        # Enqueue detected sentences to TTS
        for sentence in sentences:
            await tts_manager.enqueue_sentence(
                sentence=sentence,
                session_id="test_session",
                voice_id="test_voice",
                speed=1.0,
                metadata={'sentence': sentence}
            )

        # Wait for processing
        await asyncio.sleep(0.5)

        # Verify sentence was synthesized
        assert len(streaming_pipeline['synthesized']) >= 1
        assert "Hello world!" in streaming_pipeline['synthesized'][0]

        # Wait for playback
        await asyncio.sleep(0.3)

        # Verify audio was played
        assert len(streaming_pipeline['played']) >= 1

    @pytest.mark.asyncio
    async def test_multiple_sentences_flow(self, streaming_pipeline):
        """Test multiple sentences flow in order"""
        parser = streaming_pipeline['parser']
        tts_manager = streaming_pipeline['tts_manager']

        # Simulate streaming chunks
        chunks = [
            "First sentence here. ",
            "Second sentence now. ",
            "Third and final."
        ]

        for chunk in chunks:
            sentences = parser.add_chunk(chunk)
            for sentence in sentences:
                await tts_manager.enqueue_sentence(
                    sentence=sentence,
                    session_id="test_session",
                    voice_id="test_voice",
                    speed=1.0,
                    metadata={'sentence': sentence}
                )

        # Get final sentence
        final = parser.finalize()
        if final:
            await tts_manager.enqueue_sentence(
                sentence=final,
                session_id="test_session",
                voice_id="test_voice",
                speed=1.0,
                metadata={'sentence': final}
            )

        # Wait for all processing
        await asyncio.sleep(1.0)

        # Should have synthesized all 3 sentences
        assert len(streaming_pipeline['synthesized']) == 3
        assert "First sentence" in streaming_pipeline['synthesized'][0]
        assert "Second sentence" in streaming_pipeline['synthesized'][1]
        assert "Third and final" in streaming_pipeline['synthesized'][2]

    @pytest.mark.asyncio
    async def test_streaming_incremental_chunks(self, streaming_pipeline):
        """Test incremental chunk streaming (like LLM output)"""
        parser = streaming_pipeline['parser']
        tts_manager = streaming_pipeline['tts_manager']

        # Simulate LLM streaming word by word
        word_chunks = ["Hello ", "world! ", "This ", "is ", "streaming. "]

        for chunk in word_chunks:
            sentences = parser.add_chunk(chunk)
            for sentence in sentences:
                await tts_manager.enqueue_sentence(
                    sentence=sentence,
                    session_id="test_session",
                    voice_id="test_voice",
                    speed=1.0,
                    metadata={'sentence': sentence}
                )

        # Wait for processing
        await asyncio.sleep(0.8)

        # Should have detected and synthesized complete sentences
        assert len(streaming_pipeline['synthesized']) >= 2
        assert "Hello world!" in streaming_pipeline['synthesized'][0]


class TestErrorHandling:
    """Test error handling across pipeline"""

    @pytest.mark.asyncio
    async def test_tts_error_doesnt_block_pipeline(self, mock_tts_service, mock_voice_client):
        """Test TTS error doesn't block other sentences"""
        # Make TTS fail on first call, succeed on second
        mock_tts_service.synthesize_speech = AsyncMock(
            side_effect=[Exception("TTS failed"), b"audio_data"]
        )

        parser = SentenceParser(min_sentence_length=10)

        error_count = 0
        async def on_error(sentence: str, error: Exception, metadata: dict):
            nonlocal error_count
            error_count += 1

        tts_manager = TTSQueueManager(
            max_concurrent=2,
            tts_service=mock_tts_service,
            on_complete=AsyncMock(),
            on_error=on_error
        )

        await tts_manager.start()

        # Enqueue two sentences
        await tts_manager.enqueue_sentence(
            sentence="First sentence.",
            session_id="test",
            voice_id="voice1",
            speed=1.0
        )

        await tts_manager.enqueue_sentence(
            sentence="Second sentence.",
            session_id="test",
            voice_id="voice1",
            speed=1.0
        )

        # Wait for processing
        await asyncio.sleep(0.4)

        # Should have one error
        assert error_count == 1

        # Second sentence should still succeed
        assert tts_manager.total_completed >= 1

        await tts_manager.stop()

    @pytest.mark.asyncio
    async def test_playback_error_tracked(self, mock_tts_service, mock_voice_client):
        """Test playback errors are tracked"""
        # Make voice client not connected
        mock_voice_client.is_connected = Mock(return_value=False)

        playback_queue = AudioPlaybackQueue(
            voice_client=mock_voice_client,
            on_complete=AsyncMock(),
            on_error=AsyncMock()
        )

        await playback_queue.start()

        # Enqueue audio
        await playback_queue.enqueue_audio(b"audio_data", {"test": "metadata"})

        # Wait for processing attempt
        await asyncio.sleep(0.3)

        # Should handle gracefully (not crash)
        stats = playback_queue.get_stats()
        assert stats is not None

        await playback_queue.stop()


class TestInterruption:
    """Test interruption handling across pipeline"""

    @pytest.mark.asyncio
    async def test_immediate_interruption_stops_all(self, streaming_pipeline):
        """Test immediate interruption stops TTS and playback"""
        tts_manager = streaming_pipeline['tts_manager']
        playback_queue = streaming_pipeline['playback_queue']

        # Enqueue multiple sentences
        for i in range(5):
            await tts_manager.enqueue_sentence(
                sentence=f"Sentence {i} here.",
                session_id="test",
                voice_id="voice1",
                speed=1.0
            )

        # Let some processing start
        await asyncio.sleep(0.1)

        # Trigger immediate interruption
        await tts_manager.cancel_all()
        await playback_queue.stop_playback('immediate')

        # Wait a bit
        await asyncio.sleep(0.2)

        # Both queues should be empty
        assert tts_manager.queue.qsize() == 0
        assert playback_queue.queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_graceful_interruption_finishes_current(self, streaming_pipeline):
        """Test graceful interruption finishes current sentence"""
        tts_manager = streaming_pipeline['tts_manager']
        playback_queue = streaming_pipeline['playback_queue']

        # Enqueue sentences
        for i in range(5):
            await tts_manager.enqueue_sentence(
                sentence=f"Sentence {i} here.",
                session_id="test",
                voice_id="voice1",
                speed=1.0,
                metadata={'index': i}
            )

        # Let some processing start
        await asyncio.sleep(0.1)

        # Trigger graceful interruption
        await tts_manager.cancel_pending()
        await playback_queue.stop_playback('graceful')

        # Wait for current to finish
        await asyncio.sleep(0.3)

        # Should have completed at least one sentence
        assert len(streaming_pipeline['played']) >= 1

        # Remaining should be cleared
        assert tts_manager.queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_drain_interruption_processes_few_more(self, streaming_pipeline):
        """Test drain interruption processes 1-2 more sentences"""
        tts_manager = streaming_pipeline['tts_manager']
        playback_queue = streaming_pipeline['playback_queue']

        # Enqueue many sentences
        for i in range(10):
            await tts_manager.enqueue_sentence(
                sentence=f"Sentence {i} here.",
                session_id="test",
                voice_id="voice1",
                speed=1.0
            )

        initial_size = tts_manager.queue.qsize()

        # Trigger drain interruption
        await tts_manager.cancel_after(num_to_keep=2)
        await playback_queue.stop_playback('drain')

        # Should have kept 1-2 tasks
        assert tts_manager.queue.qsize() <= 2
        assert tts_manager.queue.qsize() < initial_size


class TestMetrics:
    """Test metrics tracking across pipeline"""

    @pytest.mark.asyncio
    async def test_end_to_end_latency_tracking(self, streaming_pipeline):
        """Test latency is tracked from sentence detection to playback"""
        parser = streaming_pipeline['parser']
        tts_manager = streaming_pipeline['tts_manager']

        import time
        t_start = time.time()

        # Detect sentence
        sentences = parser.add_chunk("Hello world! How are you?")

        # Enqueue to TTS
        for sentence in sentences:
            await tts_manager.enqueue_sentence(
                sentence=sentence,
                session_id="test",
                voice_id="voice1",
                speed=1.0,
                metadata={
                    'sentence': sentence,
                    't_detected': t_start
                }
            )

        # Wait for full pipeline
        await asyncio.sleep(0.8)

        # Calculate end-to-end time
        t_end = time.time()
        latency_ms = (t_end - t_start) * 1000

        # Should complete in reasonable time
        assert latency_ms < 1000  # Less than 1 second

        # Should have completed processing
        assert len(streaming_pipeline['synthesized']) >= 1
        assert len(streaming_pipeline['played']) >= 1


class TestConcurrency:
    """Test concurrent processing across pipeline"""

    @pytest.mark.asyncio
    async def test_concurrent_tts_with_sequential_playback(self, mock_tts_service, mock_voice_client):
        """Test TTS runs concurrently but playback is sequential"""
        # Track TTS concurrency
        concurrent_tts = 0
        max_concurrent_tts = 0

        async def slow_tts(*args, **kwargs):
            nonlocal concurrent_tts, max_concurrent_tts
            concurrent_tts += 1
            max_concurrent_tts = max(max_concurrent_tts, concurrent_tts)
            await asyncio.sleep(0.1)
            concurrent_tts -= 1
            return b"audio_data"

        mock_tts_service.synthesize_speech = slow_tts

        # Track playback sequencing
        playback_order = []

        def track_playback(audio_source):
            playback_order.append(audio_source)

        mock_voice_client.play = track_playback
        mock_voice_client.is_playing = Mock(side_effect=[False] * 20)

        # Create pipeline
        async def on_tts_complete(audio_bytes: bytes, metadata: dict):
            await playback_queue.enqueue_audio(audio_bytes, metadata)

        tts_manager = TTSQueueManager(
            max_concurrent=3,  # Allow 3 concurrent TTS
            tts_service=mock_tts_service,
            on_complete=on_tts_complete,
            on_error=AsyncMock()
        )

        playback_queue = AudioPlaybackQueue(
            voice_client=mock_voice_client,
            on_complete=AsyncMock(),
            on_error=AsyncMock()
        )

        await tts_manager.start()
        await playback_queue.start()

        # Enqueue 5 sentences
        for i in range(5):
            await tts_manager.enqueue_sentence(
                sentence=f"Sentence {i}",
                session_id="test",
                voice_id="voice1",
                speed=1.0
            )

        # Wait for processing
        await asyncio.sleep(1.0)

        # TTS should have run concurrently (max 3)
        assert 2 <= max_concurrent_tts <= 3

        # Playback should have happened (sequentially)
        assert len(playback_order) >= 3

        await tts_manager.stop()
        await playback_queue.stop()


class TestEdgeCases:
    """Test edge cases in pipeline"""

    @pytest.mark.asyncio
    async def test_empty_sentence_handling(self, streaming_pipeline):
        """Test empty sentences are handled gracefully"""
        parser = streaming_pipeline['parser']
        tts_manager = streaming_pipeline['tts_manager']

        # Add empty and whitespace chunks
        sentences = parser.add_chunk("   \n\t  ")

        # Should detect no sentences
        assert len(sentences) == 0

        # Pipeline should handle gracefully
        stats = tts_manager.get_stats()
        assert stats['total_enqueued'] == 0

    @pytest.mark.asyncio
    async def test_rapid_chunk_arrival(self, streaming_pipeline):
        """Test pipeline handles rapid chunk arrival"""
        parser = streaming_pipeline['parser']
        tts_manager = streaming_pipeline['tts_manager']

        # Simulate rapid LLM output
        chunks = ["Hello! ", "How ", "are ", "you? ", "I'm ", "fine."]

        for chunk in chunks:
            sentences = parser.add_chunk(chunk)
            for sentence in sentences:
                await tts_manager.enqueue_sentence(
                    sentence=sentence,
                    session_id="test",
                    voice_id="voice1",
                    speed=1.0
                )
            # No delay between chunks

        # Get final sentence
        final = parser.finalize()
        if final:
            await tts_manager.enqueue_sentence(
                sentence=final,
                session_id="test",
                voice_id="voice1",
                speed=1.0
            )

        # Wait for processing
        await asyncio.sleep(0.8)

        # Should have processed all sentences (1 from chunks + 1 from finalize)
        assert len(streaming_pipeline['synthesized']) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
