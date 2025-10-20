"""
Integration test fixtures and configuration

Provides mock server fixtures, timing utilities, and helpers
for testing low-latency streaming workflows
"""
from __future__ import annotations

import pytest
import asyncio
import time
from typing import AsyncGenerator, Dict, List
from contextlib import asynccontextmanager
import httpx

# Import for path setup
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


# ============================================================
# Latency Measurement Utilities
# ============================================================

class LatencyTracker:
    """Track latency for different stages of the pipeline"""

    def __init__(self):
        self.timings: Dict[str, List[float]] = {}
        self.start_times: Dict[str, float] = {}

    def start(self, stage: str):
        """Start timing a stage"""
        self.start_times[stage] = time.perf_counter()

    def end(self, stage: str) -> float:
        """End timing a stage and return duration in ms"""
        if stage not in self.start_times:
            raise ValueError(f"Stage '{stage}' was never started")

        duration_ms = (time.perf_counter() - self.start_times[stage]) * 1000

        if stage not in self.timings:
            self.timings[stage] = []
        self.timings[stage].append(duration_ms)

        del self.start_times[stage]
        return duration_ms

    def get_average(self, stage: str) -> float:
        """Get average latency for a stage in ms"""
        if stage not in self.timings or not self.timings[stage]:
            return 0.0
        return sum(self.timings[stage]) / len(self.timings[stage])

    def get_p95(self, stage: str) -> float:
        """Get 95th percentile latency for a stage in ms"""
        if stage not in self.timings or not self.timings[stage]:
            return 0.0
        sorted_timings = sorted(self.timings[stage])
        idx = int(len(sorted_timings) * 0.95)
        return sorted_timings[min(idx, len(sorted_timings) - 1)]

    def get_total(self) -> float:
        """Get total latency across all stages in ms"""
        total = 0.0
        for stage_timings in self.timings.values():
            if stage_timings:
                total += stage_timings[-1]  # Last timing for each stage
        return total

    def report(self) -> str:
        """Generate a latency report"""
        lines = ["Latency Report:", "=" * 50]
        for stage, timings in self.timings.items():
            if timings:
                avg = self.get_average(stage)
                p95 = self.get_p95(stage)
                lines.append(f"{stage:30s} avg: {avg:6.2f}ms  p95: {p95:6.2f}ms")
        lines.append("=" * 50)
        lines.append(f"{'TOTAL':30s}     {self.get_total():6.2f}ms")
        return "\n".join(lines)


@pytest.fixture
def latency_tracker():
    """Provides a latency tracker for measuring pipeline timings"""
    return LatencyTracker()


# ============================================================
# Streaming Validation Utilities
# ============================================================

class StreamValidator:
    """Validate streaming behavior (incremental data, no blocking)"""

    def __init__(self):
        self.chunks_received = []
        self.chunk_timestamps = []

    def record_chunk(self, chunk: bytes):
        """Record a chunk and its timestamp"""
        self.chunks_received.append(chunk)
        self.chunk_timestamps.append(time.perf_counter())

    def validate_incremental(self, max_delay_ms: float = 100) -> bool:
        """
        Validate chunks arrived incrementally (not all at once)

        Args:
            max_delay_ms: Maximum acceptable delay between chunks

        Returns:
            True if streaming was incremental
        """
        if len(self.chunk_timestamps) < 2:
            return True  # Can't validate with < 2 chunks

        delays = []
        for i in range(1, len(self.chunk_timestamps)):
            delay_ms = (self.chunk_timestamps[i] - self.chunk_timestamps[i-1]) * 1000
            delays.append(delay_ms)

        # Check that chunks didn't all arrive at once
        avg_delay = sum(delays) / len(delays)
        return avg_delay > 0.1  # At least 0.1ms between chunks means streaming

    def get_first_chunk_latency(self) -> float:
        """Get time to first chunk in ms (TTFB equivalent)"""
        if not self.chunk_timestamps:
            return 0.0
        return self.chunk_timestamps[0] * 1000

    def get_total_chunks(self) -> int:
        """Get total number of chunks received"""
        return len(self.chunks_received)


@pytest.fixture
def stream_validator():
    """Provides a stream validator for testing incremental streaming"""
    return StreamValidator()


# ============================================================
# Mock Server Fixtures
# ============================================================

@pytest.fixture
async def mock_whisperx_server():
    """
    Mock WhisperX WebSocket server info

    Returns:
        Server configuration dict
    """
    yield {
        "base_url": "http://localhost:14901",
        "ws_url": "ws://localhost:14901/transcribe"
    }


@pytest.fixture
async def mock_n8n_server():
    """
    Mock n8n webhook server info

    Returns:
        Server configuration dict
    """
    yield {
        "base_url": "http://localhost:8888",
        "webhook_url": "http://localhost:8888/webhook/test",
        "streaming_url": "http://localhost:8888/webhook/test-streaming"
    }


@pytest.fixture
async def mock_chatterbox_server():
    """
    Mock Chatterbox TTS server info

    Returns:
        Server configuration dict
    """
    yield {
        "base_url": "http://localhost:4123",
        "stream_url": "http://localhost:4123/audio/speech/stream/upload"
    }


# ============================================================
# Component Fixtures
# ============================================================

@pytest.fixture
def mock_voice_client():
    """Mock Discord voice client for testing"""
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.is_connected.return_value = True
    mock.is_playing.return_value = False
    mock.play = MagicMock()

    return mock


@pytest.fixture
def speaker_manager_with_mocks(mock_voice_client):
    """SpeakerManager with mocked dependencies"""
    from speaker_manager import SpeakerManager

    manager = SpeakerManager()
    manager.set_voice_connection(mock_voice_client)

    return manager


# ============================================================
# Integration Test Markers
# ============================================================

def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers", "integration: integration tests using mock servers"
    )
    config.addinivalue_line(
        "markers", "latency: tests that measure latency/performance"
    )
    config.addinivalue_line(
        "markers", "streaming: tests that validate streaming behavior"
    )


# ============================================================
# Latency Assertions
# ============================================================

class LatencyAssertions:
    """Helper for asserting latency requirements"""

    @staticmethod
    def assert_low_latency(latency_ms: float, max_ms: float, stage: str):
        """Assert latency is below threshold"""
        assert latency_ms <= max_ms, (
            f"{stage} latency {latency_ms:.2f}ms exceeds threshold {max_ms}ms"
        )

    @staticmethod
    def assert_streaming(validator: StreamValidator, min_chunks: int = 2):
        """Assert streaming behavior was incremental"""
        assert validator.get_total_chunks() >= min_chunks, (
            f"Expected at least {min_chunks} chunks, got {validator.get_total_chunks()}"
        )
        assert validator.validate_incremental(), (
            "Streaming was not incremental (all chunks arrived at once)"
        )


@pytest.fixture
def latency_assertions():
    """Provides latency assertion helpers"""
    return LatencyAssertions()
