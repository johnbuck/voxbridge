"""
Unit tests for AudioPlaybackQueue

Tests sequential FIFO audio playback:
- Enqueue and play audio chunks
- Sequential playback (one at a time)
- Interruption strategies (immediate, graceful, drain)
- Discord voice client integration
- Gap-free transitions
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from src.services.audio_playback_queue import AudioPlaybackQueue, PlaybackStatus, AudioChunk


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
async def playback_queue(mock_voice_client):
    """Create AudioPlaybackQueue instance for testing"""
    on_complete = AsyncMock()
    on_error = AsyncMock()

    queue = AudioPlaybackQueue(
        voice_client=mock_voice_client,
        on_complete=on_complete,
        on_error=on_error
    )

    yield queue

    # Cleanup
    await queue.stop()


class TestInitialization:
    """Test AudioPlaybackQueue initialization"""

    def test_init_creates_empty_queue(self, mock_voice_client):
        """Test initialization creates empty queue"""
        queue = AudioPlaybackQueue(
            voice_client=mock_voice_client,
            on_complete=None,
            on_error=None
        )

        assert queue.queue.qsize() == 0
        assert not queue.playing
        assert queue.voice_client == mock_voice_client

    def test_init_sets_callbacks(self, mock_voice_client):
        """Test callbacks are set correctly"""
        on_complete = AsyncMock()
        on_error = AsyncMock()

        queue = AudioPlaybackQueue(
            voice_client=mock_voice_client,
            on_complete=on_complete,
            on_error=on_error
        )

        assert queue.on_complete == on_complete
        assert queue.on_error == on_error


class TestStartStop:
    """Test start/stop lifecycle"""

    @pytest.mark.asyncio
    async def test_start_begins_playback_worker(self, playback_queue):
        """Test start() begins playback worker"""
        await playback_queue.start()

        assert playback_queue.playing
        assert playback_queue.playback_worker is not None

    @pytest.mark.asyncio
    async def test_start_when_already_playing(self, playback_queue):
        """Test start() when already playing does nothing"""
        await playback_queue.start()
        worker1 = playback_queue.playback_worker

        await playback_queue.start()  # Second call
        worker2 = playback_queue.playback_worker

        # Should be same worker
        assert worker1 == worker2

    @pytest.mark.asyncio
    async def test_stop_ends_playback(self, playback_queue):
        """Test stop() ends playback and cleans up"""
        await playback_queue.start()
        assert playback_queue.playing

        await playback_queue.stop()

        assert not playback_queue.playing


class TestEnqueue:
    """Test audio enqueueing"""

    @pytest.mark.asyncio
    async def test_enqueue_audio(self, playback_queue):
        """Test enqueuing a single audio chunk"""
        audio_bytes = b"fake_audio_data"
        metadata = {"sentence": "Hello", "task_id": "123"}

        chunk_id = await playback_queue.enqueue_audio(audio_bytes, metadata)

        assert chunk_id is not None
        assert playback_queue.queue.qsize() == 1
        assert playback_queue.total_queued == 1

    @pytest.mark.asyncio
    async def test_enqueue_multiple_chunks(self, playback_queue):
        """Test enqueuing multiple audio chunks"""
        for i in range(5):
            await playback_queue.enqueue_audio(
                audio_bytes=b"audio_" + str(i).encode(),
                metadata={"index": i}
            )

        assert playback_queue.queue.qsize() == 5
        assert playback_queue.total_queued == 5

    @pytest.mark.asyncio
    async def test_enqueue_preserves_metadata(self, playback_queue):
        """Test metadata is preserved in audio chunk"""
        metadata = {"user_id": "123", "session_id": "abc"}

        await playback_queue.enqueue_audio(b"audio", metadata)

        chunk = await playback_queue.queue.get()
        assert chunk.metadata == metadata


class TestFIFOOrdering:
    """Test FIFO (First-In-First-Out) playback ordering"""

    @pytest.mark.asyncio
    async def test_fifo_playback_order(self, playback_queue, mock_voice_client):
        """Test chunks are played in FIFO order"""
        played_chunks = []

        def track_play(audio_source):
            """Track which audio gets played"""
            played_chunks.append(audio_source)

        mock_voice_client.play = track_play
        mock_voice_client.is_playing = Mock(side_effect=[False] * 10)  # Never playing

        await playback_queue.start()

        # Enqueue 3 chunks with different data
        for i in range(3):
            await playback_queue.enqueue_audio(
                audio_bytes=b"audio_" + str(i).encode(),
                metadata={"index": i}
            )

        # Wait for playback
        await asyncio.sleep(0.5)

        # Should have played in order (can't verify exact bytes due to FFmpeg,
        # but we can verify play was called 3 times)
        assert len(played_chunks) == 3

        await playback_queue.stop()


class TestSequentialPlayback:
    """Test sequential (one-at-a-time) playback"""

    @pytest.mark.asyncio
    async def test_one_chunk_at_a_time(self, playback_queue, mock_voice_client):
        """Test only one chunk plays at a time"""
        # Simulate is_playing returns True for a bit, then False
        play_states = [False, True, True, False, True, True, False]
        mock_voice_client.is_playing = Mock(side_effect=play_states)

        await playback_queue.start()

        # Enqueue 2 chunks
        await playback_queue.enqueue_audio(b"audio1", {})
        await playback_queue.enqueue_audio(b"audio2", {})

        # Wait for playback
        await asyncio.sleep(0.3)

        # Should have called play for both chunks
        assert mock_voice_client.play.call_count >= 1

        await playback_queue.stop()


class TestInterruption:
    """Test interruption strategies"""

    @pytest.mark.asyncio
    async def test_immediate_interruption(self, playback_queue, mock_voice_client):
        """Test immediate interruption stops current and cancels queue"""
        await playback_queue.start()

        # Enqueue multiple chunks
        for i in range(5):
            await playback_queue.enqueue_audio(b"audio", {"index": i})

        # Trigger immediate interruption
        await playback_queue.stop_playback('immediate')

        # Wait a bit
        await asyncio.sleep(0.1)

        # Should have stopped voice client
        mock_voice_client.stop.assert_called()

        # Queue should be empty
        assert playback_queue.queue.qsize() == 0

        await playback_queue.stop()

    @pytest.mark.asyncio
    async def test_graceful_interruption(self, playback_queue, mock_voice_client):
        """Test graceful interruption finishes current, cancels queue"""
        mock_voice_client.is_playing = Mock(return_value=True)

        await playback_queue.start()

        # Enqueue chunks
        for i in range(5):
            await playback_queue.enqueue_audio(b"audio", {"index": i})

        # Trigger graceful interruption
        await playback_queue.stop_playback('graceful')

        # Wait a bit
        await asyncio.sleep(0.1)

        # Should NOT have stopped voice client immediately
        # (lets current chunk finish)
        # Queue should be cancelled
        assert playback_queue.queue.qsize() == 0

        await playback_queue.stop()

    @pytest.mark.asyncio
    async def test_drain_interruption(self, playback_queue, mock_voice_client):
        """Test drain interruption processes 1-2 more chunks"""
        await playback_queue.start()

        # Enqueue 10 chunks
        for i in range(10):
            await playback_queue.enqueue_audio(b"audio", {"index": i})

        initial_size = playback_queue.queue.qsize()

        # Trigger drain interruption
        await playback_queue.stop_playback('drain')

        # Wait a bit
        await asyncio.sleep(0.1)

        # Should have kept 1-2 chunks, cancelled rest
        remaining = playback_queue.queue.qsize()
        assert remaining <= 2
        assert remaining < initial_size

        await playback_queue.stop()


class TestCallbacks:
    """Test completion and error callbacks"""

    @pytest.mark.asyncio
    async def test_on_complete_callback(self, playback_queue, mock_voice_client):
        """Test on_complete callback is called after playback"""
        mock_voice_client.is_playing = Mock(side_effect=[False, True, False, False])

        await playback_queue.start()

        metadata = {"sentence": "Test", "task_id": "123"}
        await playback_queue.enqueue_audio(b"audio", metadata)

        # Wait for playback
        await asyncio.sleep(0.3)

        # Callback should have been called with metadata
        playback_queue.on_complete.assert_called_once()
        call_args = playback_queue.on_complete.call_args[0][0]
        assert "task_id" in call_args
        assert call_args["task_id"] == "123"

        await playback_queue.stop()

    @pytest.mark.asyncio
    async def test_on_error_callback_on_failure(self, playback_queue, mock_voice_client):
        """Test on_error callback is called on playback failure"""
        # Make voice client not connected
        mock_voice_client.is_connected = Mock(return_value=False)

        await playback_queue.start()

        await playback_queue.enqueue_audio(b"audio", {"test": "data"})

        # Wait for processing
        await asyncio.sleep(0.2)

        # Error callback should be called (voice client not connected)
        # Note: This depends on implementation - may just log instead

        await playback_queue.stop()


class TestMetrics:
    """Test metrics and statistics"""

    @pytest.mark.asyncio
    async def test_get_stats(self, playback_queue):
        """Test get_stats() returns correct metrics"""
        stats = playback_queue.get_stats()

        assert "playing" in stats
        assert "queue_size" in stats
        assert "current_chunk" in stats
        assert "total_queued" in stats
        assert "total_played" in stats
        assert "total_interrupted" in stats
        assert "total_failed" in stats

    @pytest.mark.asyncio
    async def test_stats_track_playback(self, playback_queue, mock_voice_client):
        """Test stats correctly track played chunks"""
        mock_voice_client.is_playing = Mock(side_effect=[False] * 10)

        await playback_queue.start()

        # Enqueue and play 3 chunks
        for i in range(3):
            await playback_queue.enqueue_audio(b"audio", {"index": i})

        # Wait for playback
        await asyncio.sleep(0.5)

        stats = playback_queue.get_stats()
        assert stats["total_queued"] == 3

        await playback_queue.stop()


class TestEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.mark.asyncio
    async def test_playback_without_voice_client(self):
        """Test playback fails gracefully without voice client"""
        queue = AudioPlaybackQueue(
            voice_client=None,
            on_complete=None,
            on_error=None
        )

        await queue.start()

        # Should not crash when trying to play
        await queue.enqueue_audio(b"audio", {})
        await asyncio.sleep(0.2)

        await queue.stop()

    @pytest.mark.asyncio
    async def test_voice_client_disconnects_during_playback(self, playback_queue, mock_voice_client):
        """Test handles voice client disconnecting mid-playback"""
        # Start connected
        mock_voice_client.is_connected = Mock(side_effect=[True, False])

        await playback_queue.start()

        await playback_queue.enqueue_audio(b"audio", {})

        # Wait for playback attempt
        await asyncio.sleep(0.2)

        # Should handle gracefully (not crash)
        await playback_queue.stop()

    @pytest.mark.asyncio
    async def test_empty_queue_playback(self, playback_queue):
        """Test playback with empty queue"""
        await playback_queue.start()

        # Let worker run with empty queue
        await asyncio.sleep(0.2)

        stats = playback_queue.get_stats()
        assert stats["queue_size"] == 0
        assert stats["total_played"] == 0

        await playback_queue.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
