"""
Audio Playback Queue for Sentence-Level Streaming

Manages sequential FIFO playback of synthesized audio chunks to ensure
sentences play in the correct order without gaps or overlaps.

Key Design Principles:
- FIFO queue (preserves sentence order)
- Sequential playback (one audio chunk at a time)
- Gap-free transitions between sentences
- Configurable interruption strategies (immediate, graceful, drain)
- Discord voice client integration
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, Awaitable
from enum import Enum
import time
import tempfile
import os

logger = logging.getLogger(__name__)


class PlaybackStatus(Enum):
    """Status of audio playback"""
    QUEUED = "queued"
    PLAYING = "playing"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


@dataclass
class AudioChunk:
    """
    Represents a single audio chunk for playback.

    Attributes:
        chunk_id: Unique identifier
        audio_bytes: WAV audio data
        metadata: Associated metadata (sentence, task_id, etc.)
        status: Current playback status
        queued_at: Timestamp when added to queue
        started_at: Timestamp when playback started
        completed_at: Timestamp when playback completed
    """
    chunk_id: str
    audio_bytes: bytes
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: PlaybackStatus = PlaybackStatus.QUEUED
    queued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class AudioPlaybackQueue:
    """
    Manages sequential playback of audio chunks for Discord voice.

    Example usage:
        queue = AudioPlaybackQueue(
            voice_client=voice_client,
            on_complete=handle_playback_complete
        )

        await queue.start()

        # Enqueue audio as TTS completes
        await queue.enqueue_audio(audio_bytes, {"sentence": "Hello!"})
        await queue.enqueue_audio(audio_bytes, {"sentence": "How are you?"})

        # Stop playback
        await queue.stop_playback('graceful')
    """

    def __init__(
        self,
        voice_client: Any,  # discord.VoiceClient
        on_complete: Optional[Callable[[Dict], Awaitable[None]]] = None,
        on_error: Optional[Callable[[Exception, Dict], Awaitable[None]]] = None,
    ):
        """
        Initialize audio playback queue.

        Args:
            voice_client: Discord VoiceClient for audio playback
            on_complete: Optional async callback when audio chunk completes
                        Args: (metadata)
            on_error: Optional async callback when playback fails
                     Args: (error, metadata)
        """
        self.voice_client = voice_client
        self.on_complete = on_complete
        self.on_error = on_error

        # Queue management
        self.queue: asyncio.Queue[AudioChunk] = asyncio.Queue()
        self.current_chunk: Optional[AudioChunk] = None

        # Playback control
        self.playing = False
        self.stop_requested = False
        self.interruption_strategy: Optional[str] = None
        self.playback_worker: Optional[asyncio.Task] = None

        # Metrics
        self.total_queued = 0
        self.total_played = 0
        self.total_interrupted = 0
        self.total_failed = 0

    async def start(self):
        """Start playback worker"""
        if self.playing:
            logger.warning("⚠️ Audio Playback Queue already running")
            return

        self.playing = True
        self.stop_requested = False

        logger.info("🎵 Starting Audio Playback Queue")

        # Start playback worker
        self.playback_worker = asyncio.create_task(self._playback_worker())

    async def enqueue_audio(
        self,
        audio_bytes: bytes,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add audio chunk to playback queue.

        Args:
            audio_bytes: WAV audio data
            metadata: Associated metadata (sentence, task_id, latency, etc.)

        Returns:
            Chunk ID for tracking
        """
        import uuid

        chunk = AudioChunk(
            chunk_id=str(uuid.uuid4()),
            audio_bytes=audio_bytes,
            metadata=metadata or {},
        )

        await self.queue.put(chunk)
        self.total_queued += 1

        logger.debug(
            f"📥 Enqueued audio chunk (chunk={chunk.chunk_id[:8]}..., "
            f"size={len(audio_bytes)} bytes, queue_size={self.queue.qsize()})"
        )

        return chunk.chunk_id

    async def _playback_worker(self):
        """
        Worker coroutine that plays audio chunks sequentially.

        Ensures gap-free playback by immediately starting next chunk
        when current chunk completes.
        """
        logger.debug("🎵 Playback worker started")

        while self.playing:
            try:
                # Check for stop signal
                if self.stop_requested:
                    await self._handle_interruption()
                    break

                # Wait for next audio chunk
                try:
                    chunk = await asyncio.wait_for(self.queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                # Play the chunk
                await self._play_chunk(chunk)

            except asyncio.CancelledError:
                logger.debug("🎵 Playback worker cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Playback worker error: {e}", exc_info=True)

        logger.debug("🎵 Playback worker stopped")

    async def _play_chunk(self, chunk: AudioChunk):
        """
        Play a single audio chunk through Discord voice client.

        Args:
            chunk: Audio chunk to play
        """
        if not self.voice_client or not self.voice_client.is_connected():
            logger.error("❌ Voice client not connected, cannot play audio")
            chunk.status = PlaybackStatus.FAILED
            self.total_failed += 1
            return

        chunk.status = PlaybackStatus.PLAYING
        chunk.started_at = time.time()
        self.current_chunk = chunk

        try:
            logger.debug(
                f"🔊 Playing audio chunk (chunk={chunk.chunk_id[:8]}..., "
                f"size={len(chunk.audio_bytes)} bytes)"
            )

            # Save audio to temporary file (Discord.py requires file path)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                temp_path = temp_file.name
                temp_file.write(chunk.audio_bytes)

            try:
                # Create FFmpeg audio source
                import discord
                audio_source = discord.FFmpegPCMAudio(temp_path)

                # Play audio (blocking until complete)
                self.voice_client.play(audio_source)

                # Wait for playback to complete
                while self.voice_client.is_playing():
                    await asyncio.sleep(0.1)

                    # Check for interruption
                    if self.stop_requested:
                        self.voice_client.stop()
                        chunk.status = PlaybackStatus.INTERRUPTED
                        self.total_interrupted += 1
                        logger.debug(f"⏹️ Playback interrupted (chunk={chunk.chunk_id[:8]}...)")
                        return

                # Playback completed successfully
                chunk.status = PlaybackStatus.COMPLETED
                chunk.completed_at = time.time()
                self.total_played += 1

                # Calculate latency
                latency = chunk.completed_at - chunk.started_at if chunk.started_at else 0
                logger.debug(
                    f"✅ Playback complete (chunk={chunk.chunk_id[:8]}..., "
                    f"latency={latency:.2f}s)"
                )

                # Call completion callback
                if self.on_complete:
                    await self.on_complete({
                        'chunk_id': chunk.chunk_id,
                        'latency': latency,
                        **chunk.metadata,
                    })

            finally:
                # Cleanup temp file
                try:
                    os.unlink(temp_path)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to delete temp file {temp_path}: {e}")

        except Exception as e:
            chunk.status = PlaybackStatus.FAILED
            chunk.completed_at = time.time()
            self.total_failed += 1

            logger.error(
                f"❌ Playback failed (chunk={chunk.chunk_id[:8]}..., error={e})",
                exc_info=True
            )

            # Call error callback
            if self.on_error:
                await self.on_error(e, {
                    'chunk_id': chunk.chunk_id,
                    **chunk.metadata,
                })

        finally:
            self.current_chunk = None

    async def stop_playback(self, strategy: str = 'immediate'):
        """
        Stop audio playback with specified strategy.

        Args:
            strategy: Interruption strategy
                - 'immediate': Stop current playback, cancel queue
                - 'graceful': Finish current chunk, cancel queue
                - 'drain': Finish current + 1-2 more chunks, then stop
        """
        self.interruption_strategy = strategy
        self.stop_requested = True

        logger.info(f"⏹️ Stopping playback (strategy={strategy})")

    async def _handle_interruption(self):
        """Handle interruption based on configured strategy"""
        strategy = self.interruption_strategy or 'immediate'

        if strategy == 'immediate':
            # Stop current playback immediately
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop()

            # Cancel all queued chunks
            cancelled_count = self.queue.qsize()
            while not self.queue.empty():
                try:
                    chunk = self.queue.get_nowait()
                    chunk.status = PlaybackStatus.INTERRUPTED
                    self.total_interrupted += 1
                except asyncio.QueueEmpty:
                    break

            logger.info(
                f"🚫 Immediate interruption (current stopped, "
                f"queue cancelled={cancelled_count})"
            )

        elif strategy == 'graceful':
            # Let current chunk finish (already handled by _play_chunk)
            # Cancel remaining queue
            cancelled_count = self.queue.qsize()
            while not self.queue.empty():
                try:
                    chunk = self.queue.get_nowait()
                    chunk.status = PlaybackStatus.INTERRUPTED
                    self.total_interrupted += 1
                except asyncio.QueueEmpty:
                    break

            logger.info(
                f"🚫 Graceful interruption (current finishing, "
                f"queue cancelled={cancelled_count})"
            )

        elif strategy == 'drain':
            # Let current chunk finish + process up to 2 more
            drain_count = min(2, self.queue.qsize())

            # Put remaining chunks back temporarily
            chunks_to_keep = []
            chunks_to_cancel = []

            while not self.queue.empty():
                try:
                    chunk = self.queue.get_nowait()
                    if len(chunks_to_keep) < drain_count:
                        chunks_to_keep.append(chunk)
                    else:
                        chunks_to_cancel.append(chunk)
                except asyncio.QueueEmpty:
                    break

            # Re-enqueue chunks to keep
            for chunk in chunks_to_keep:
                await self.queue.put(chunk)

            # Cancel remaining
            for chunk in chunks_to_cancel:
                chunk.status = PlaybackStatus.INTERRUPTED
                self.total_interrupted += 1

            logger.info(
                f"🚫 Drain interruption (keeping={len(chunks_to_keep)}, "
                f"cancelled={len(chunks_to_cancel)})"
            )

            # Don't stop immediately, let drain complete
            self.stop_requested = False

    async def stop(self):
        """
        Stop playback queue and cleanup resources.

        Alias for stop_playback('immediate') + worker cleanup.
        """
        if not self.playing:
            return

        logger.info("⏹️ Stopping Audio Playback Queue...")

        self.stop_requested = True
        self.playing = False

        # Stop current playback
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

        # Wait for worker to finish
        if self.playback_worker:
            try:
                await asyncio.wait_for(self.playback_worker, timeout=2.0)
            except asyncio.TimeoutError:
                self.playback_worker.cancel()

        logger.info(
            f"✅ Audio Playback Queue stopped (played={self.total_played}, "
            f"interrupted={self.total_interrupted}, failed={self.total_failed})"
        )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get current playback statistics.

        Returns:
            Dictionary with playback metrics
        """
        return {
            'playing': self.playing,
            'queue_size': self.queue.qsize(),
            'current_chunk': self.current_chunk.chunk_id[:8] if self.current_chunk else None,
            'total_queued': self.total_queued,
            'total_played': self.total_played,
            'total_interrupted': self.total_interrupted,
            'total_failed': self.total_failed,
        }
