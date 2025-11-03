"""
Unit tests for TTSQueueManager

Tests TTS queue management with concurrency control:
- Enqueue and process sentences
- Concurrent synthesis with semaphore
- Cancellation strategies (all, pending, after N)
- Error handling callbacks
- Worker pool management
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from src.services.tts_queue_manager import TTSQueueManager, SynthesisStatus


@pytest.fixture
def mock_tts_service():
    """Mock TTS service for testing"""
    service = Mock()
    service.synthesize_speech = AsyncMock(return_value=b"fake_audio_data")
    return service


@pytest.fixture
async def queue_manager(mock_tts_service):
    """Create TTSQueueManager instance for testing"""
    on_complete = AsyncMock()
    on_error = AsyncMock()

    manager = TTSQueueManager(
        max_concurrent=3,
        tts_service=mock_tts_service,
        on_complete=on_complete,
        on_error=on_error
    )

    yield manager

    # Cleanup
    if manager.running:
        await manager.stop()


class TestInitialization:
    """Test TTSQueueManager initialization"""

    @pytest.mark.asyncio
    async def test_init_creates_empty_queue(self, mock_tts_service):
        """Test initialization creates empty queue"""
        manager = TTSQueueManager(
            max_concurrent=3,
            tts_service=mock_tts_service,
            on_complete=AsyncMock(),
            on_error=AsyncMock()
        )

        assert manager.queue.qsize() == 0
        assert manager.max_concurrent == 3
        assert not manager.running

    @pytest.mark.asyncio
    async def test_init_sets_callbacks(self, mock_tts_service):
        """Test callbacks are set correctly"""
        on_complete = AsyncMock()
        on_error = AsyncMock()

        manager = TTSQueueManager(
            max_concurrent=5,
            tts_service=mock_tts_service,
            on_complete=on_complete,
            on_error=on_error
        )

        assert manager.on_complete == on_complete
        assert manager.on_error == on_error


class TestStartStop:
    """Test start/stop lifecycle"""

    @pytest.mark.asyncio
    async def test_start_creates_workers(self, queue_manager):
        """Test start() creates worker tasks"""
        await queue_manager.start(num_workers=3)

        assert queue_manager.running
        assert len(queue_manager.workers) == 3

        await queue_manager.stop()

    @pytest.mark.asyncio
    async def test_start_default_worker_count(self, queue_manager):
        """Test start() uses max_concurrent as default worker count"""
        await queue_manager.start()

        assert len(queue_manager.workers) == queue_manager.max_concurrent

        await queue_manager.stop()

    @pytest.mark.asyncio
    async def test_start_when_already_running(self, queue_manager):
        """Test start() when already running does nothing"""
        await queue_manager.start()

        initial_workers = len(queue_manager.workers)
        await queue_manager.start()  # Second call

        # Should still have same number of workers
        assert len(queue_manager.workers) == initial_workers

        await queue_manager.stop()

    @pytest.mark.asyncio
    async def test_stop_waits_for_workers(self, queue_manager):
        """Test stop() waits for workers to finish"""
        await queue_manager.start()
        assert queue_manager.running

        await queue_manager.stop()

        assert not queue_manager.running
        assert len(queue_manager.workers) == 0


class TestEnqueue:
    """Test sentence enqueueing"""

    @pytest.mark.asyncio
    async def test_enqueue_sentence(self, queue_manager):
        """Test enqueuing a single sentence"""
        task_id = await queue_manager.enqueue_sentence(
            sentence="Hello world",
            session_id="session123",
            voice_id="voice1",
            speed=1.0,
            metadata={"test": "data"}
        )

        assert task_id is not None
        assert queue_manager.queue.qsize() == 1
        assert queue_manager.total_enqueued == 1

    @pytest.mark.asyncio
    async def test_enqueue_multiple_sentences(self, queue_manager):
        """Test enqueuing multiple sentences"""
        for i in range(5):
            await queue_manager.enqueue_sentence(
                sentence=f"Sentence {i}",
                session_id="session123",
                voice_id="voice1",
                speed=1.0
            )

        assert queue_manager.queue.qsize() == 5
        assert queue_manager.total_enqueued == 5

    @pytest.mark.asyncio
    async def test_enqueue_with_metadata(self, queue_manager):
        """Test metadata is preserved"""
        metadata = {"user_id": "123", "guild_id": 456}

        await queue_manager.enqueue_sentence(
            sentence="Test",
            session_id="session123",
            voice_id="voice1",
            speed=1.0,
            metadata=metadata
        )

        task = await queue_manager.queue.get()
        assert task.metadata == metadata


class TestProcessing:
    """Test sentence processing and synthesis"""

    @pytest.mark.asyncio
    async def test_process_single_sentence(self, queue_manager, mock_tts_service):
        """Test processing a single sentence"""
        await queue_manager.start()

        await queue_manager.enqueue_sentence(
            sentence="Hello world",
            session_id="session123",
            voice_id="voice1",
            speed=1.0
        )

        # Wait for processing
        await asyncio.sleep(0.2)

        # Should have called TTS service
        mock_tts_service.synthesize_speech.assert_called_once()
        assert queue_manager.total_completed == 1

        await queue_manager.stop()

    @pytest.mark.asyncio
    async def test_on_complete_callback_called(self, queue_manager, mock_tts_service):
        """Test on_complete callback is called after synthesis"""
        await queue_manager.start()

        await queue_manager.enqueue_sentence(
            sentence="Test sentence",
            session_id="session123",
            voice_id="voice1",
            speed=1.0,
            metadata={"key": "value"}
        )

        # Wait for processing
        await asyncio.sleep(0.2)

        # Callback should have been called with audio bytes and metadata
        queue_manager.on_complete.assert_called_once()
        call_args = queue_manager.on_complete.call_args
        audio_bytes = call_args[0][0]
        metadata = call_args[0][1]

        assert audio_bytes == b"fake_audio_data"
        assert "key" in metadata
        assert metadata["key"] == "value"

        await queue_manager.stop()

    @pytest.mark.asyncio
    async def test_synthesis_error_calls_error_callback(self, queue_manager, mock_tts_service):
        """Test on_error callback is called on synthesis failure"""
        # Make TTS service raise exception
        mock_tts_service.synthesize_speech.side_effect = Exception("TTS failed")

        await queue_manager.start()

        await queue_manager.enqueue_sentence(
            sentence="Test",
            session_id="session123",
            voice_id="voice1",
            speed=1.0
        )

        # Wait for processing
        await asyncio.sleep(0.2)

        # Error callback should have been called
        queue_manager.on_error.assert_called_once()
        assert queue_manager.total_failed == 1

        await queue_manager.stop()


class TestConcurrency:
    """Test concurrent processing with semaphore"""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_synthesis(self, mock_tts_service):
        """Test semaphore limits concurrent synthesis"""
        # Track concurrent synthesis calls
        concurrent_count = 0
        max_concurrent = 0

        async def slow_synthesis(*args, **kwargs):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)

            await asyncio.sleep(0.1)  # Simulate slow synthesis

            concurrent_count -= 1
            return b"fake_audio"

        mock_tts_service.synthesize_speech = slow_synthesis

        manager = TTSQueueManager(
            max_concurrent=2,  # Limit to 2 concurrent
            tts_service=mock_tts_service,
            on_complete=AsyncMock(),
            on_error=AsyncMock()
        )

        await manager.start()

        # Enqueue 5 sentences
        for i in range(5):
            await manager.enqueue_sentence(
                sentence=f"Sentence {i}",
                session_id="session123",
                voice_id="voice1",
                speed=1.0
            )

        # Wait for all to complete
        await asyncio.sleep(0.5)

        # Should never exceed max_concurrent
        assert max_concurrent <= 2

        await manager.stop()


class TestCancellation:
    """Test cancellation strategies"""

    @pytest.mark.asyncio
    async def test_cancel_all(self, queue_manager):
        """Test cancel_all() cancels all pending tasks"""
        # Enqueue multiple sentences
        for i in range(5):
            await queue_manager.enqueue_sentence(
                sentence=f"Sentence {i}",
                session_id="session123",
                voice_id="voice1",
                speed=1.0
            )

        assert queue_manager.queue.qsize() == 5

        # Cancel all
        await queue_manager.cancel_all()

        assert queue_manager.queue.qsize() == 0
        assert queue_manager.total_cancelled == 5

    @pytest.mark.asyncio
    async def test_cancel_pending(self, queue_manager):
        """Test cancel_pending() cancels only pending (not active)"""
        # Enqueue sentences
        for i in range(3):
            await queue_manager.enqueue_sentence(
                sentence=f"Sentence {i}",
                session_id="session123",
                voice_id="voice1",
                speed=1.0
            )

        pending_count = queue_manager.queue.qsize()

        # Cancel pending
        await queue_manager.cancel_pending()

        assert queue_manager.queue.qsize() == 0
        assert queue_manager.total_cancelled == pending_count

    @pytest.mark.asyncio
    async def test_cancel_after(self, queue_manager):
        """Test cancel_after() keeps N tasks, cancels rest"""
        # Enqueue 10 sentences
        for i in range(10):
            await queue_manager.enqueue_sentence(
                sentence=f"Sentence {i}",
                session_id="session123",
                voice_id="voice1",
                speed=1.0
            )

        assert queue_manager.queue.qsize() == 10

        # Keep first 3, cancel rest
        await queue_manager.cancel_after(num_to_keep=3)

        assert queue_manager.queue.qsize() == 3
        assert queue_manager.total_cancelled == 7

    @pytest.mark.asyncio
    async def test_cancel_after_with_fewer_than_keep(self, queue_manager):
        """Test cancel_after() when queue has fewer than num_to_keep"""
        # Enqueue only 2 sentences
        for i in range(2):
            await queue_manager.enqueue_sentence(
                sentence=f"Sentence {i}",
                session_id="session123",
                voice_id="voice1",
                speed=1.0
            )

        # Try to keep 5 (more than queued)
        await queue_manager.cancel_after(num_to_keep=5)

        # Should keep all 2
        assert queue_manager.queue.qsize() == 2
        assert queue_manager.total_cancelled == 0


class TestMetrics:
    """Test metrics and counters"""

    @pytest.mark.asyncio
    async def test_get_stats(self, queue_manager):
        """Test get_stats() returns correct metrics"""
        stats = queue_manager.get_stats()

        assert "running" in stats
        assert "queue_size" in stats
        assert "total_enqueued" in stats
        assert "total_completed" in stats
        assert "total_failed" in stats
        assert "total_cancelled" in stats
        assert "max_concurrent" in stats

    @pytest.mark.asyncio
    async def test_stats_track_completion(self, queue_manager, mock_tts_service):
        """Test stats correctly track completed tasks"""
        await queue_manager.start()

        # Enqueue and process 3 sentences
        for i in range(3):
            await queue_manager.enqueue_sentence(
                sentence=f"Sentence {i}",
                session_id="session123",
                voice_id="voice1",
                speed=1.0
            )

        # Wait for processing
        await asyncio.sleep(0.3)

        stats = queue_manager.get_stats()
        assert stats["total_enqueued"] == 3
        assert stats["total_completed"] == 3

        await queue_manager.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
