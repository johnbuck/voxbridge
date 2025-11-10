"""
TTS Queue Manager for Sentence-Level Streaming

Manages concurrent TTS synthesis without interfering with Chatterbox's native
parallelization. Queues sentences and processes them with configurable concurrency.

Key Design Principles:
- FIFO queue (preserves sentence order)
- Semaphore-based concurrency control
- Graceful cancellation support
- Per-sentence error handling
- Works alongside Chatterbox's streaming_strategy parameter
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Callable, Awaitable, Any
from enum import Enum
import time
import uuid

logger = logging.getLogger(__name__)


class SynthesisStatus(Enum):
    """Status of a sentence synthesis task"""
    QUEUED = "queued"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SynthesisTask:
    """
    Represents a single sentence TTS synthesis task.

    Attributes:
        task_id: Unique identifier for this synthesis task
        sentence: Text to synthesize
        session_id: Voice session identifier
        voice_id: Chatterbox voice ID
        speed: Speech rate (0.5-2.0)
        metadata: Additional metadata (timestamps, etc.)
        status: Current synthesis status
        audio_bytes: Synthesized audio (populated on completion)
        error: Error message if synthesis failed
        created_at: Task creation timestamp
        started_at: Synthesis start timestamp
        completed_at: Synthesis completion timestamp
    """
    task_id: str
    sentence: str
    session_id: str
    voice_id: str
    speed: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: SynthesisStatus = SynthesisStatus.QUEUED
    audio_bytes: Optional[bytes] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class TTSQueueManager:
    """
    Manages concurrent TTS synthesis for sentence-level streaming.

    Example usage:
        manager = TTSQueueManager(
            max_concurrent=3,
            tts_service=tts_service,
            on_complete=handle_audio_chunk
        )

        await manager.start()

        # Enqueue sentences as LLM generates them
        await manager.enqueue_sentence("Hello!", {...})
        await manager.enqueue_sentence("How are you?", {...})

        # Stop and cleanup
        await manager.stop()
    """

    def __init__(
        self,
        max_concurrent: int,
        tts_service: Any,  # TTSService instance
        on_complete: Callable[[bytes, Dict], Awaitable[None]],
        on_error: Optional[Callable[[str, Exception, Dict], Awaitable[None]]] = None,
    ):
        """
        Initialize TTS queue manager.

        Args:
            max_concurrent: Maximum number of concurrent TTS synthesis requests
            tts_service: TTSService instance for synthesis
            on_complete: Async callback when sentence synthesis completes
                        Args: (audio_bytes, metadata)
            on_error: Optional async callback when synthesis fails
                     Args: (sentence, error, metadata)
        """
        self.max_concurrent = max_concurrent
        self.tts_service = tts_service
        self.on_complete = on_complete
        self.on_error = on_error

        # Queue and task management
        self.queue: asyncio.Queue[SynthesisTask] = asyncio.Queue()
        self.active_tasks: Dict[str, SynthesisTask] = {}
        self.completed_tasks: Dict[str, SynthesisTask] = {}

        # Concurrency control
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Worker management
        self.workers: list[asyncio.Task] = []
        self.running = False
        self.stop_event = asyncio.Event()

        # Metrics
        self.total_enqueued = 0
        self.total_completed = 0
        self.total_failed = 0
        self.total_cancelled = 0

    async def start(self, num_workers: Optional[int] = None):
        """
        Start worker coroutines for processing TTS queue.

        Args:
            num_workers: Number of worker coroutines (defaults to max_concurrent)
        """
        if self.running:
            logger.warning("⚠️ TTS Queue Manager already running")
            return

        num_workers = num_workers or self.max_concurrent
        self.running = True
        self.stop_event.clear()

        logger.info(f"🚀 Starting TTS Queue Manager (workers={num_workers}, max_concurrent={self.max_concurrent})")

        # Start worker coroutines
        for i in range(num_workers):
            worker = asyncio.create_task(self._worker(worker_id=i))
            self.workers.append(worker)

    async def enqueue_sentence(
        self,
        sentence: str,
        session_id: str,
        voice_id: str,
        speed: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add sentence to TTS synthesis queue.

        Args:
            sentence: Text to synthesize
            session_id: Voice session identifier
            voice_id: Chatterbox voice ID
            speed: Speech rate (0.5-2.0)
            metadata: Additional metadata

        Returns:
            Task ID for tracking this synthesis request
        """
        task = SynthesisTask(
            task_id=str(uuid.uuid4()),
            sentence=sentence,
            session_id=session_id,
            voice_id=voice_id,
            speed=speed,
            metadata=metadata or {},
        )

        await self.queue.put(task)
        self.total_enqueued += 1

        logger.debug(
            f"📝 Enqueued sentence for TTS (task={task.task_id[:8]}..., "
            f"length={len(sentence)} chars, queue_size={self.queue.qsize()})"
        )

        return task.task_id

    async def _worker(self, worker_id: int):
        """
        Worker coroutine that processes TTS synthesis queue.

        Args:
            worker_id: Unique identifier for this worker
        """
        logger.debug(f"👷 TTS Worker {worker_id} started")

        while self.running:
            try:
                # Wait for task or stop signal
                try:
                    task = await asyncio.wait_for(self.queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    # Check stop signal
                    if self.stop_event.is_set():
                        break
                    continue

                # Acquire semaphore (blocks if max concurrent reached)
                async with self.semaphore:
                    await self._synthesize_task(task)

            except asyncio.CancelledError:
                logger.debug(f"👷 TTS Worker {worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"❌ TTS Worker {worker_id} error: {e}", exc_info=True)

        logger.debug(f"👷 TTS Worker {worker_id} stopped")

    async def _synthesize_task(self, task: SynthesisTask):
        """
        Synthesize audio for a single task.

        Args:
            task: Synthesis task to process
        """
        task.status = SynthesisStatus.SYNTHESIZING
        task.started_at = time.time()
        self.active_tasks[task.task_id] = task

        try:
            logger.debug(
                f"🔊 Synthesizing sentence (task={task.task_id[:8]}..., "
                f"length={len(task.sentence)} chars, active={len(self.active_tasks)})"
            )

            # Call TTS service (uses Chatterbox with native streaming)
            audio_bytes = await self.tts_service.synthesize_speech(
                session_id=task.session_id,
                text=task.sentence,
                voice_id=task.voice_id,
                speed=task.speed,
                stream=False,  # Get complete audio for this sentence
                callback=None,  # No streaming callback for individual sentences
            )

            task.audio_bytes = audio_bytes
            task.status = SynthesisStatus.COMPLETED
            task.completed_at = time.time()

            # Move to completed tasks
            self.active_tasks.pop(task.task_id, None)
            self.completed_tasks[task.task_id] = task
            self.total_completed += 1

            # Calculate latency
            latency = task.completed_at - task.started_at
            logger.debug(
                f"✅ Synthesis complete (task={task.task_id[:8]}..., "
                f"audio_size={len(audio_bytes)} bytes, latency={latency:.2f}s)"
            )

            # Call completion callback
            if self.on_complete:
                await self.on_complete(audio_bytes, {
                    'task_id': task.task_id,
                    'sentence': task.sentence,
                    'session_id': task.session_id,
                    'latency': latency,
                    **task.metadata,
                })

        except Exception as e:
            task.status = SynthesisStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            self.active_tasks.pop(task.task_id, None)
            self.total_failed += 1

            logger.error(
                f"❌ Synthesis failed (task={task.task_id[:8]}..., "
                f"sentence={task.sentence[:50]}..., error={e})"
            )

            # Call error callback
            if self.on_error:
                await self.on_error(task.sentence, e, {
                    'task_id': task.task_id,
                    'session_id': task.session_id,
                    **task.metadata,
                })

    async def cancel_all(self):
        """
        Cancel all pending and active synthesis tasks.

        Used when user interrupts or session ends.
        """
        # Cancel all pending tasks in queue
        pending_count = self.queue.qsize()
        while not self.queue.empty():
            try:
                task = self.queue.get_nowait()
                task.status = SynthesisStatus.CANCELLED
                self.total_cancelled += 1
            except asyncio.QueueEmpty:
                break

        logger.info(
            f"🚫 Cancelled all TTS tasks (pending={pending_count}, "
            f"active={len(self.active_tasks)})"
        )

    async def cancel_pending(self):
        """
        Cancel only pending tasks in queue (keep active tasks running).

        Used for graceful interruption strategy.
        """
        pending_count = self.queue.qsize()
        while not self.queue.empty():
            try:
                task = self.queue.get_nowait()
                task.status = SynthesisStatus.CANCELLED
                self.total_cancelled += 1
            except asyncio.QueueEmpty:
                break

        logger.info(f"🚫 Cancelled pending TTS tasks (count={pending_count})")

    async def cancel_after(self, num_to_keep: int):
        """
        Cancel all but the next N tasks in queue.

        Used for drain interruption strategy.

        Args:
            num_to_keep: Number of tasks to keep in queue
        """
        if self.queue.qsize() <= num_to_keep:
            return  # Nothing to cancel

        # Drain queue to list
        tasks = []
        while not self.queue.empty():
            try:
                tasks.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        # Keep first N, cancel rest
        for task in tasks[:num_to_keep]:
            await self.queue.put(task)

        for task in tasks[num_to_keep:]:
            task.status = SynthesisStatus.CANCELLED
            self.total_cancelled += 1

        logger.info(
            f"🚫 Cancelled TTS tasks (kept={num_to_keep}, "
            f"cancelled={len(tasks) - num_to_keep})"
        )

    async def stop(self):
        """
        Stop all workers and cleanup resources.

        Waits for active tasks to complete.
        """
        if not self.running:
            return

        logger.info("⏹️ Stopping TTS Queue Manager...")

        self.running = False
        self.stop_event.set()

        # Wait for workers to finish
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)

        self.workers.clear()

        logger.info(
            f"✅ TTS Queue Manager stopped (completed={self.total_completed}, "
            f"failed={self.total_failed}, cancelled={self.total_cancelled})"
        )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get current queue statistics.

        Returns:
            Dictionary with queue metrics
        """
        return {
            'running': self.running,
            'queue_size': self.queue.qsize(),
            'active_tasks': len(self.active_tasks),
            'completed_tasks': len(self.completed_tasks),
            'total_enqueued': self.total_enqueued,
            'total_completed': self.total_completed,
            'total_failed': self.total_failed,
            'total_cancelled': self.total_cancelled,
            'max_concurrent': self.max_concurrent,
        }
