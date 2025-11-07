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


# ============================================================
# Phase 5 Service Mock Fixtures
# ============================================================

@pytest.fixture
def mock_conversation_service(mocker):
    """Mock ConversationService with Phase 5 API"""
    from src.services.conversation_service import ConversationService, CachedContext, Message
    from src.database.models import Session, Agent
    from unittest.mock import Mock, AsyncMock
    from uuid import uuid4
    from datetime import datetime, timedelta

    service = mocker.Mock(spec=ConversationService)

    # Create mock Session
    mock_session = Mock(spec=Session)
    mock_session.id = uuid4()
    mock_session.user_id = "test_user"
    mock_session.agent_id = uuid4()
    mock_session.active = True
    mock_session.title = "Test Session"
    mock_session.channel_type = "webrtc"
    mock_session.created_at = datetime.now()
    mock_session.updated_at = datetime.now()

    # Create mock Agent
    mock_agent = Mock(spec=Agent)
    mock_agent.id = mock_session.agent_id
    mock_agent.name = "TestAgent"
    mock_agent.system_prompt = "You are a test assistant"
    mock_agent.llm_provider = "openrouter"
    mock_agent.llm_model = "anthropic/claude-3-haiku"
    mock_agent.temperature = 0.7
    mock_agent.tts_voice = "default"
    mock_agent.tts_exaggeration = 1.0
    mock_agent.tts_cfg_weight = 1.0
    mock_agent.tts_temperature = 0.7
    mock_agent.tts_language = "en"

    # Mock CachedContext (Phase 5 return type)
    cached_context = Mock(spec=CachedContext)
    cached_context.session = mock_session
    cached_context.agent = mock_agent
    cached_context.messages = []
    cached_context.last_activity = datetime.now()
    cached_context.expires_at = datetime.now() + timedelta(minutes=15)
    cached_context.lock = asyncio.Lock()

    # Phase 5 API: get_or_create_session returns CachedContext
    service.get_or_create_session = AsyncMock(return_value=cached_context)
    service._ensure_session_cached = AsyncMock(return_value=cached_context)
    service.get_conversation_context = AsyncMock(return_value=[])
    service.add_message = AsyncMock()
    service.end_session = AsyncMock()
    service.start = AsyncMock()
    service.stop = AsyncMock()

    return service


@pytest.fixture
def mock_stt_service(mocker):
    """Mock STTService with Phase 5 API"""
    from src.services.stt_service import STTService
    from unittest.mock import AsyncMock

    service = mocker.Mock(spec=STTService)

    # Phase 5 API: send_audio takes audio_format parameter
    service.connect = AsyncMock(return_value=True)
    service.disconnect = AsyncMock()
    service.register_callback = AsyncMock()
    service.send_audio = AsyncMock(return_value=True)  # Accepts audio_format parameter
    service.get_connection_status = AsyncMock(return_value="connected")

    return service


@pytest.fixture
def mock_llm_service(mocker):
    """Mock LLMService with Phase 5 API"""
    from src.services.llm_service import LLMService
    from unittest.mock import AsyncMock

    service = mocker.Mock(spec=LLMService)

    # Phase 5 API: generate_response takes callback, returns complete text
    async def mock_generate_response(session_id, messages, config, stream=True, callback=None):
        response_text = "Hello! How can I help you?"
        if callback and stream:
            # Simulate streaming chunks
            for chunk in ["Hello! ", "How can ", "I help you?"]:
                await callback(chunk)
                await asyncio.sleep(0.01)
        return response_text

    service.generate_response = AsyncMock(side_effect=mock_generate_response)
    service.health_check = AsyncMock(return_value=True)

    return service


@pytest.fixture
def mock_tts_service(mocker):
    """Mock TTSService with Phase 5 API"""
    from src.services.tts_service import TTSService
    from unittest.mock import AsyncMock

    service = mocker.Mock(spec=TTSService)

    # Phase 5 API: synthesize_speech with streaming callback
    async def mock_synthesize(session_id, text, voice_id=None, exaggeration=None,
                             cfg_weight=None, temperature=None, language_id="en",
                             stream=True, callback=None):
        fake_audio = b'fake_audio_data' * 100  # 1.5KB fake audio

        if callback and stream:
            # Simulate streaming chunks
            chunk_size = 512
            for i in range(0, len(fake_audio), chunk_size):
                await callback(fake_audio[i:i+chunk_size])
                await asyncio.sleep(0.01)

        return fake_audio

    service.synthesize_speech = AsyncMock(side_effect=mock_synthesize)
    service.test_tts_health = AsyncMock(return_value=True)
    service.cancel_tts = AsyncMock()

    return service


@pytest.fixture
def mock_services(mock_conversation_service, mock_stt_service, mock_llm_service, mock_tts_service):
    """Bundle all Phase 5 service mocks"""
    return {
        'conversation': mock_conversation_service,
        'stt': mock_stt_service,
        'llm': mock_llm_service,
        'tts': mock_tts_service
    }


# ============================================================
# WebRTC-Specific Fixtures (VoxBridge 2.0 Phase 5.5)
# ============================================================

@pytest.fixture
async def webrtc_session():
    """
    Create WebRTC session in test database

    Returns:
        Session object with agent assigned
    """
    from src.database.session import get_db_session
    from src.database.models import Session, Agent
    from uuid import uuid4

    async with get_db_session() as db_session:
        # Find or create test agent
        agent = await db_session.execute(
            "SELECT * FROM agents WHERE name = 'WebRTC Test Agent' LIMIT 1"
        )
        agent = agent.first()

        if not agent:
            # Create test agent if doesn't exist
            from src.database.models import Agent
            agent = Agent(
                id=uuid4(),
                name="WebRTC Test Agent",
                system_prompt="You are a test assistant for WebRTC integration tests",
                llm_provider="openrouter",
                llm_model="anthropic/claude-3-haiku",
                tts_voice="default",
                temperature=0.7
            )
            db_session.add(agent)
            await db_session.commit()
            await db_session.refresh(agent)

        # Create WebRTC session
        session = Session(
            id=uuid4(),
            user_id="browser_user_test",
            agent_id=agent.id,
            title="WebRTC Integration Test Session",
            active=True
        )
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        yield session

        # Cleanup
        await db_session.delete(session)
        await db_session.commit()


@pytest.fixture
def webrtc_ws_url(webrtc_session):
    """
    Generate WebSocket URL for WebRTC testing

    Args:
        webrtc_session: Session fixture

    Returns:
        WebSocket URL string
    """
    session_id = str(webrtc_session.id)
    user_id = webrtc_session.user_id
    return f"/ws/voice?session_id={session_id}&user_id={user_id}"


@pytest.fixture
async def mock_whisperx_with_format():
    """
    Mock WhisperX server with format tracking enabled

    Returns:
        Tuple of (server instance, port)
    """
    from tests.mocks.mock_whisperx_server import MockWhisperXServer

    server = MockWhisperXServer(
        port=14901,
        auto_respond=True,
        latency_ms=50  # Fast for integration tests
    )

    await server.start()

    try:
        yield (server, server.port)
    finally:
        await server.stop()


# ============================================================
# WebM Audio Fixtures
# ============================================================

@pytest.fixture
def sample_webm_audio():
    """Single-frame valid WebM (20ms)"""
    from tests.fixtures.audio_samples import get_sample_webm_audio
    return get_sample_webm_audio()


@pytest.fixture
def multi_frame_webm_audio():
    """Multi-frame WebM (500ms)"""
    from tests.fixtures.audio_samples import get_multi_frame_webm_audio
    return get_multi_frame_webm_audio()


@pytest.fixture
def incomplete_webm_audio():
    """Incomplete WebM for buffering tests (512 bytes)"""
    from tests.fixtures.audio_samples import get_incomplete_webm_audio
    return get_incomplete_webm_audio()


@pytest.fixture
def corrupted_webm_audio():
    """Corrupted WebM for error handling tests"""
    from tests.fixtures.audio_samples import get_corrupted_webm_audio
    return get_corrupted_webm_audio()


# ============================================================
# PCM Audio Fixtures (Phase 5.5 - Dual Format Support)
# ============================================================

@pytest.fixture
def sample_pcm_audio():
    """Single PCM frame (20ms, 48kHz stereo, ~3,840 bytes)"""
    from tests.fixtures.audio_samples import generate_pcm_audio
    return generate_pcm_audio(duration_ms=20)


@pytest.fixture
def multi_frame_pcm_audio():
    """Multiple PCM frames (500ms, 25 frames, ~96,000 bytes)"""
    from tests.fixtures.audio_samples import generate_pcm_frames
    return generate_pcm_frames(num_frames=25)


@pytest.fixture
def expected_pcm_frame_size():
    """Expected PCM frame size for validation (3,840 bytes for 48kHz stereo)"""
    from tests.fixtures.audio_samples import get_pcm_frame_size
    return get_pcm_frame_size()


@pytest.fixture
def sample_opus_audio():
    """Single Opus frame (20ms, ~121 bytes compressed)"""
    from tests.fixtures.audio_samples import get_sample_opus_audio
    return get_sample_opus_audio()
