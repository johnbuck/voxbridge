"""
E2E Test Fixtures for VoxBridge

Provides fixtures specific to end-to-end testing:
- Configured Discord bot with all mock services
- Mock voice connections with audio injection
- Latency tracking and assertions
"""
from __future__ import annotations

import pytest
import asyncio
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

# Add project root to path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.discord_bot import app, speaker_manager, bot
from tests.mocks.mock_discord import MockVoiceClient, MockVoiceChannel, MockUser, MockBot
from tests.utils.audio_injection import AudioInjector, AudioSamples


# ============================================================
# E2E-Specific Fixtures
# ============================================================

@pytest.fixture
async def e2e_test_client() -> AsyncClient:
    """
    FastAPI test client for E2E tests

    Returns httpx AsyncClient configured for testing
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def mock_discord_bot():
    """
    Mock Discord bot instance with proper configuration

    Returns a MockBot with all necessary attributes
    """
    mock_bot = MockBot()
    mock_bot._ready = True
    return mock_bot


@pytest.fixture
def mock_voice_channel():
    """Create a mock voice channel for testing"""
    return MockVoiceChannel(
        id=555555555,
        name="TestVoiceChannel"
    )


@pytest.fixture
def mock_voice_client(mock_voice_channel):
    """
    Create a mock voice client with audio sink support

    This simulates a Discord voice connection with the ability
    to receive and play audio
    """
    voice_client = MockVoiceClient(channel=mock_voice_channel)

    # Add audio sink for receiving audio
    voice_client.sink = AsyncMock()
    voice_client.sink.write = AsyncMock()

    return voice_client


@pytest.fixture
def mock_user():
    """Create a mock Discord user"""
    return MockUser(
        id=123456789,
        name="TestUser",
        bot=False
    )


@pytest.fixture
def audio_injector():
    """
    Provide AudioInjector instance for tests

    Use this to generate realistic audio packets
    """
    return AudioInjector()


@pytest.fixture
def audio_samples():
    """
    Provide pre-defined audio samples for common scenarios

    Usage:
        def test_something(audio_samples):
            packets = audio_samples.short_question()
    """
    return AudioSamples()


@pytest.fixture
async def mock_whisperx_transcription():
    """
    Mock WhisperX to return a specific transcription

    Usage:
        @pytest.mark.asyncio
        async def test_transcript(mock_whisperx_transcription):
            mock_whisperx_transcription.set_response("Hello world")
    """
    class MockWhisperX:
        def __init__(self):
            self.response = "Test transcription"
            self.partial_responses = []
            self.call_count = 0

        def set_response(self, text: str):
            self.response = text

        def set_partial_responses(self, responses: list):
            self.partial_responses = responses

        async def transcribe(self, audio_packets):
            self.call_count += 1

            # Simulate partial transcripts
            for partial in self.partial_responses:
                await asyncio.sleep(0.05)
                yield {'type': 'partial', 'text': partial}

            # Final transcript
            await asyncio.sleep(0.05)
            yield {'type': 'final', 'text': self.response}

    return MockWhisperX()


@pytest.fixture
async def mock_n8n_response():
    """
    Mock n8n webhook to return a specific response

    Usage:
        @pytest.mark.asyncio
        async def test_n8n(mock_n8n_response):
            mock_n8n_response.set_text("AI response")
            mock_n8n_response.set_tts_options({"temperature": 0.8})
    """
    class MockN8nResponse:
        def __init__(self):
            self.text = "Default AI response"
            self.tts_options = {}
            self.chunks = []
            self.call_count = 0
            self.streaming = True

        def set_text(self, text: str):
            self.text = text

        def set_tts_options(self, options: dict):
            self.tts_options = options

        def set_chunks(self, chunks: list):
            """Set text chunks for streaming response"""
            self.chunks = chunks

        def set_streaming(self, enabled: bool):
            self.streaming = enabled

        async def get_response(self):
            """Generate response with optional streaming"""
            self.call_count += 1

            if self.streaming and self.chunks:
                # Streaming response with chunks
                for chunk in self.chunks:
                    yield chunk
                    await asyncio.sleep(0.01)
            else:
                # Non-streaming response
                yield self.text

    return MockN8nResponse()


@pytest.fixture
async def mock_chatterbox_tts():
    """
    Mock Chatterbox TTS server

    Tracks calls and returns fake audio data
    """
    class MockChatterboxTTS:
        def __init__(self):
            self.calls = []
            self.audio_response = b'\x00' * 1000  # Fake WAV data

        def get_call_count(self) -> int:
            return len(self.calls)

        def get_latest_call(self) -> Dict[str, Any]:
            return self.calls[-1] if self.calls else None

        def get_tts_options(self) -> Dict[str, Any]:
            """Extract TTS options from latest call"""
            if not self.calls:
                return {}
            return self.calls[-1].get('options', {})

        async def generate_tts(self, text: str, options: dict = None):
            """Mock TTS generation"""
            self.calls.append({
                'text': text,
                'options': options or {},
                'timestamp': asyncio.get_event_loop().time()
            })

            # Simulate TTS processing delay
            await asyncio.sleep(0.05)

            return self.audio_response

    return MockChatterboxTTS()


@pytest.fixture
def latency_tracker():
    """
    Latency tracking for E2E tests

    Tracks timing for different stages of the pipeline
    """
    import time

    class LatencyTracker:
        def __init__(self):
            self.timings = {}
            self.start_times = {}

        def start(self, stage: str):
            self.start_times[stage] = time.perf_counter()

        def end(self, stage: str) -> float:
            if stage not in self.start_times:
                return 0.0
            duration_ms = (time.perf_counter() - self.start_times[stage]) * 1000
            self.timings[stage] = duration_ms
            del self.start_times[stage]
            return duration_ms

        def get(self, stage: str) -> float:
            return self.timings.get(stage, 0.0)

        def total(self) -> float:
            return sum(self.timings.values())

        def report(self) -> str:
            lines = ["Latency Report:"]
            for stage, ms in self.timings.items():
                lines.append(f"  {stage}: {ms:.1f}ms")
            lines.append(f"  TOTAL: {self.total():.1f}ms")
            return "\n".join(lines)

    return LatencyTracker()


# ============================================================
# Assertion Helpers
# ============================================================

def assert_bot_in_channel(voice_client, channel_id: int):
    """Assert bot is connected to specified channel"""
    assert voice_client is not None, "Voice client is None"
    assert voice_client.is_connected(), "Bot not connected to voice channel"
    assert voice_client.channel.id == channel_id, f"Bot in wrong channel: {voice_client.channel.id} != {channel_id}"


def assert_speaker_locked(speaker_manager, user_id: str):
    """Assert speaker lock is held by specific user"""
    assert speaker_manager.active_speaker == user_id, f"Speaker lock not held by {user_id}"
    assert speaker_manager.lock_start_time is not None, "Lock start time not set"


def assert_speaker_unlocked(speaker_manager):
    """Assert speaker lock is released"""
    assert speaker_manager.active_speaker is None, "Speaker lock not released"
    assert speaker_manager.lock_start_time is None, "Lock start time not cleared"


def assert_tts_called_with_options(mock_chatterbox, expected_options: dict):
    """Assert Chatterbox TTS was called with expected options"""
    latest_call = mock_chatterbox.get_latest_call()
    assert latest_call is not None, "Chatterbox TTS not called"

    call_options = latest_call.get('options', {})
    for key, value in expected_options.items():
        assert key in call_options, f"Option '{key}' not found in TTS call"
        assert call_options[key] == value, f"Option '{key}' mismatch: {call_options[key]} != {value}"


def assert_latency_below(latency_tracker, stage: str, max_ms: float):
    """Assert latency for a stage is below threshold"""
    actual_ms = latency_tracker.get(stage)
    assert actual_ms > 0, f"No timing recorded for stage '{stage}'"
    assert actual_ms < max_ms, f"{stage} latency too high: {actual_ms:.1f}ms > {max_ms}ms"
