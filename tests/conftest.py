"""
Pytest configuration and shared fixtures for VoxBridge tests
"""
import pytest
import asyncio
import os
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, Mock, MagicMock

# Import the FastAPI app
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import discord and voice_recv extension
import discord
from discord.ext import voice_recv

from src.discord_bot import app

# ============================================================
# Event Loop Configuration
# ============================================================

@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for all async tests"""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="function")
def event_loop(event_loop_policy):
    """Create event loop for each test function"""
    loop = event_loop_policy.new_event_loop()
    yield loop
    loop.close()


# ============================================================
# FastAPI Test Client
# ============================================================

@pytest.fixture
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    """
    FastAPI test client using httpx AsyncClient

    Usage:
        async def test_endpoint(test_client):
            response = await test_client.get("/health")
            assert response.status_code == 200
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


# ============================================================
# Mock Services
# ============================================================

@pytest.fixture
async def mock_whisperx_server():
    """
    Start mock WhisperX WebSocket server for testing

    Returns port number of the mock server
    """
    from tests.mocks.mock_whisperx_server import create_mock_whisperx_server

    async with create_mock_whisperx_server() as port:
        yield port


@pytest.fixture
async def mock_n8n_server():
    """
    Start mock n8n webhook HTTP server

    Returns base URL of the mock server
    """
    from tests.mocks.mock_n8n_server import create_mock_n8n_server

    async with create_mock_n8n_server() as base_url:
        yield base_url


@pytest.fixture
async def mock_chatterbox_server():
    """
    Start mock Chatterbox TTS server

    Returns base URL of the mock server
    """
    from tests.mocks.mock_chatterbox_server import create_mock_chatterbox_server

    async with create_mock_chatterbox_server() as base_url:
        yield base_url


# ============================================================
# Discord Mocks
# ============================================================

@pytest.fixture
def mock_discord_voice_client():
    """
    Mock Discord VoiceClient for testing audio playback

    Usage:
        def test_play_audio(mock_discord_voice_client):
            mock_discord_voice_client.play(audio_source)
            assert mock_discord_voice_client.is_playing()
    """
    from tests.mocks.mock_discord import MockVoiceClient
    return MockVoiceClient()


@pytest.fixture
def mock_discord_channel():
    """
    Mock Discord VoiceChannel for testing join/leave
    """
    from tests.mocks.mock_discord import MockVoiceChannel
    return MockVoiceChannel()


@pytest.fixture
def mock_discord_user():
    """
    Mock Discord User for testing
    """
    from tests.mocks.mock_discord import MockUser
    return MockUser(id=123456789, name="TestUser")


@pytest.fixture
def mock_discord_guild():
    """
    Mock Discord Guild for testing
    """
    from tests.mocks.mock_discord import MockGuild
    return MockGuild(id=987654321, name="TestGuild")


# ============================================================
# Component Fixtures
# ============================================================

@pytest.fixture
def whisper_client():
    """Create WhisperClient instance for testing"""
    from whisper_client import WhisperClient
    return WhisperClient()


@pytest.fixture
def speaker_manager():
    """Create SpeakerManager instance for testing"""
    from speaker_manager import SpeakerManager
    return SpeakerManager()


@pytest.fixture
def streaming_handler(mock_discord_voice_client, mock_discord_user):
    """Create StreamingResponseHandler instance for testing"""
    from streaming_handler import StreamingResponseHandler
    return StreamingResponseHandler(
        voice_client=mock_discord_voice_client,
        user_id=str(mock_discord_user.id)
    )


# ============================================================
# Test Data Fixtures
# ============================================================

@pytest.fixture
def sample_audio_opus():
    """
    Load sample Opus audio data for testing

    Returns bytes of Opus encoded audio
    """
    from tests.fixtures.audio_samples import get_sample_opus_audio
    return get_sample_opus_audio()


@pytest.fixture
def sample_transcript():
    """Sample transcript text for testing"""
    return "This is a test transcript from VoxBridge testing framework"


@pytest.fixture
def sample_tts_response():
    """Sample TTS response data"""
    from tests.fixtures.tts_samples import get_sample_wav_audio
    return get_sample_wav_audio()


@pytest.fixture
def sample_n8n_payload():
    """Sample n8n webhook payload"""
    return {
        "text": "Hello from VoxBridge",
        "userId": "123456789",
        "timestamp": "2024-01-01T00:00:00",
        "useStreaming": True
    }


@pytest.fixture
def sample_n8n_response():
    """Sample n8n response"""
    return {
        "output": {
            "content": "Hello! I heard you say: Hello from VoxBridge"
        },
        "options": {
            "voiceMode": "default",
            "speedFactor": 1.0,
            "outputFormat": "wav",
            "streamingStrategy": "sentence",
            "streamingQuality": "fast",
            "chunkSize": 100
        }
    }


# ============================================================
# Environment Configuration
# ============================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Setup test environment variables
    Runs once per test session
    """
    # Set test environment variables
    os.environ["DISCORD_TOKEN"] = "test_discord_token_12345"
    os.environ["WHISPER_SERVER_URL"] = "ws://localhost:4901"
    os.environ["N8N_WEBHOOK_URL"] = "http://localhost:8888/webhook/test"
    os.environ["CHATTERBOX_URL"] = "http://localhost:4123/v1"
    os.environ["CHATTERBOX_VOICE_ID"] = "test_voice"
    os.environ["SILENCE_THRESHOLD_MS"] = "500"  # Faster for tests
    os.environ["MAX_SPEAKING_TIME_MS"] = "10000"  # Shorter for tests

    yield

    # Cleanup is automatic with pytest


# ============================================================
# Async Helper Utilities
# ============================================================

@pytest.fixture
def async_mock():
    """
    Helper to create AsyncMock objects

    Usage:
        async def test_something(async_mock):
            mock_func = async_mock(return_value="test")
            result = await mock_func()
            assert result == "test"
    """
    def _create_async_mock(**kwargs):
        return AsyncMock(**kwargs)
    return _create_async_mock


# ============================================================
# Cleanup Fixtures
# ============================================================

@pytest.fixture(autouse=True)
async def cleanup_tasks():
    """
    Automatically cleanup any running tasks after each test
    to prevent task leakage
    """
    yield

    # Cancel any pending tasks
    tasks = [task for task in asyncio.all_tasks()
             if not task.done() and task != asyncio.current_task()]

    for task in tasks:
        task.cancel()

    # Wait for cancellation
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


# ============================================================
# Service Fixtures (VoxBridge 2.0)
# ============================================================

@pytest.fixture
def mock_db_session():
    """
    Mock database session for service tests

    Usage:
        async def test_something(mock_db_session):
            with patch('src.services.conversation_service.get_db_session') as mock_db:
                mock_db.return_value.__aenter__.return_value = mock_db_session
                # Test code here
    """
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    return mock_session


@pytest.fixture
def mock_agent():
    """
    Mock Agent model for testing

    Usage:
        def test_something(mock_agent):
            assert mock_agent.name == "TestAgent"
    """
    from src.database.models import Agent
    from uuid import uuid4

    return Agent(
        id=uuid4(),
        name="TestAgent",
        system_prompt="You are a helpful assistant",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4",
        tts_voice="default",
        tts_rate=1.0,
        tts_pitch=1.0
    )


@pytest.fixture
def mock_session_model(mock_agent):
    """
    Mock Session model for testing

    Usage:
        def test_something(mock_session_model):
            assert mock_session_model.active is True
    """
    from src.database.models import Session
    from uuid import uuid4
    from datetime import datetime

    session = Session(
        id=uuid4(),
        user_id="test_user_123",
        user_name="TestUser",
        agent_id=mock_agent.id,
        session_type="webrtc",
        title="Test Session",
        active=True,
        started_at=datetime.utcnow()
    )
    session.agent = mock_agent
    return session


@pytest.fixture
def mock_conversation():
    """
    Mock Conversation model for testing

    Usage:
        def test_something(mock_conversation):
            assert mock_conversation.role == "user"
    """
    from src.database.models import Conversation
    from uuid import uuid4
    from datetime import datetime

    return Conversation(
        id=uuid4(),
        session_id=uuid4(),
        role="user",
        content="Hello, AI!",
        timestamp=datetime.utcnow(),
        audio_duration_ms=1500,
        tts_duration_ms=None,
        llm_latency_ms=None,
        total_latency_ms=None
    )


@pytest.fixture
def mock_llm_provider():
    """
    Mock LLM provider for testing

    Usage:
        async def test_something(mock_llm_provider):
            async for chunk in mock_llm_provider.generate_stream(request):
                print(chunk)
    """
    from src.llm import LLMProvider

    mock_provider = AsyncMock(spec=LLMProvider)

    async def mock_stream(*args, **kwargs):
        yield "Test"
        yield " response"

    mock_provider.generate_stream = mock_stream
    mock_provider.health_check = AsyncMock(return_value=True)
    mock_provider.close = AsyncMock()

    return mock_provider


@pytest.fixture
def mock_whisperx_connection():
    """
    Mock WhisperX WebSocket connection

    Usage:
        def test_something(mock_whisperx_connection):
            await mock_whisperx_connection.send(audio_data)
    """
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.close = AsyncMock()
    return mock_ws


@pytest.fixture
def mock_httpx_client():
    """
    Mock httpx AsyncClient for HTTP requests

    Usage:
        async def test_something(mock_httpx_client):
            response = await mock_httpx_client.get("/health")
    """
    mock_client = AsyncMock()
    mock_client.get = AsyncMock()
    mock_client.post = AsyncMock()
    mock_client.stream = MagicMock()
    mock_client.aclose = AsyncMock()
    return mock_client
