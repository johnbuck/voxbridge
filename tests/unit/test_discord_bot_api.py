"""
Unit tests for Discord Bot FastAPI endpoints

Tests HTTP endpoints for voice control, TTS, health checks, and status
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

# Import the FastAPI app and global state
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import src.discord_bot as discord_bot


# ============================================================
# Test Setup
# ============================================================

@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(discord_bot.app)


@pytest.fixture
def mock_bot():
    """Mock Discord bot"""
    mock = MagicMock()
    mock.user = MagicMock()
    mock.user.name = "VoxBridge"
    mock.user.id = 123456789
    mock.is_ready.return_value = True
    return mock


@pytest.fixture
def mock_voice_channel():
    """Mock Discord voice channel"""
    channel = MagicMock(spec=discord_bot.discord.VoiceChannel)
    channel.id = 987654321
    channel.name = "General Voice"
    channel.connect = AsyncMock()
    return channel


@pytest.fixture
def mock_voice_client():
    """Mock Discord voice client"""
    client = MagicMock()
    client.is_connected.return_value = True
    client.is_playing.return_value = False
    client.disconnect = AsyncMock()
    client.listen = MagicMock()
    client.play = MagicMock()
    return client


# ============================================================
# Voice Join Endpoint Tests
# ============================================================

@pytest.mark.unit
def test_join_voice_success(client, mock_bot, mock_voice_channel, mock_voice_client):
    """Test successful voice channel join"""
    # Mock bot and channel
    discord_bot.bot = mock_bot
    mock_bot.get_channel.return_value = mock_voice_channel
    mock_voice_channel.connect.return_value = mock_voice_client

    # Make request
    response = client.post("/voice/join", json={
        "channelId": "987654321",
        "guildId": "111222333"
    })

    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "Joined voice channel" in data["message"]
    assert data["channelId"] == "987654321"

    # Verify channel connection was attempted
    mock_voice_channel.connect.assert_called_once()


@pytest.mark.unit
def test_join_voice_invalid_channel(client, mock_bot):
    """Test joining invalid channel type"""
    # Mock bot
    discord_bot.bot = mock_bot

    # Mock text channel instead of voice channel
    mock_text_channel = MagicMock()
    mock_bot.get_channel.return_value = mock_text_channel

    # Make request
    response = client.post("/voice/join", json={
        "channelId": "987654321",
        "guildId": "111222333"
    })

    # HTTPException gets caught and re-raised as 500 by outer exception handler
    assert response.status_code == 500
    assert "Invalid voice channel" in response.json()["detail"]


@pytest.mark.unit
def test_join_voice_channel_not_found(client, mock_bot):
    """Test joining non-existent channel"""
    # Mock bot
    discord_bot.bot = mock_bot
    mock_bot.get_channel.return_value = None

    # Mock fetch_channel to also fail
    async def fetch_error(channel_id):
        raise Exception("Channel not found")

    mock_bot.fetch_channel = fetch_error

    # Make request
    response = client.post("/voice/join", json={
        "channelId": "999999999",
        "guildId": "111222333"
    })

    # Should return 500 error
    assert response.status_code == 500


# ============================================================
# Voice Leave Endpoint Tests
# ============================================================

@pytest.mark.unit
def test_leave_voice_success(client, mock_voice_client):
    """Test successful voice channel leave"""
    # Set global voice_client
    discord_bot.voice_client = mock_voice_client

    # Mock speaker manager
    discord_bot.speaker_manager.force_unlock = MagicMock()

    # Make request
    response = client.post("/voice/leave")

    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "Left voice channel" in data["message"]

    # Verify disconnect was called
    mock_voice_client.disconnect.assert_called_once()

    # Verify speaker manager was unlocked
    discord_bot.speaker_manager.force_unlock.assert_called_once()


@pytest.mark.unit
def test_leave_voice_not_in_channel(client):
    """Test leaving when not in a channel"""
    # Set voice_client to None
    discord_bot.voice_client = None

    # Make request
    response = client.post("/voice/leave")

    # Should return 400 error
    assert response.status_code == 400
    assert "Not currently in a voice channel" in response.json()["detail"]


# ============================================================
# Voice Speak Endpoint Tests
# ============================================================

@pytest.mark.unit
def test_speak_text_success(client, mock_voice_client):
    """Test successful text-to-speech"""
    # Set global voice_client
    discord_bot.voice_client = mock_voice_client

    # Mock httpx streaming response
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_bytes(chunk_size):
        yield b'\\x00' * 1024
        yield b'\\x01' * 1024

    mock_response.aiter_bytes = mock_aiter_bytes

    with patch('httpx.AsyncClient') as MockClient:
        mock_http_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_http_client.stream = MagicMock(return_value=mock_stream_ctx)

        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch('tempfile.NamedTemporaryFile'):
            with patch('discord.FFmpegPCMAudio'):
                with patch('os.unlink'):
                    # Make request
                    response = client.post("/voice/speak", json={
                        "output": {"content": "Hello world"},
                        "options": {
                            "speedFactor": 1.0,
                            "outputFormat": "wav"
                        }
                    })

                    # Assertions
                    assert response.status_code == 200
                    data = response.json()
                    assert data["success"] is True
                    assert "Speaking text" in data["message"]


@pytest.mark.unit
def test_speak_text_missing_content(client, mock_voice_client):
    """Test speak endpoint with missing text content"""
    # Set global voice_client
    discord_bot.voice_client = mock_voice_client

    # Make request with empty content
    response = client.post("/voice/speak", json={
        "output": {},
        "options": {}
    })

    # Should return 400 error
    assert response.status_code == 400
    assert "Missing required parameter" in response.json()["detail"]


@pytest.mark.unit
def test_speak_text_not_in_channel(client):
    """Test speak endpoint when not in voice channel"""
    # Set voice_client to None
    discord_bot.voice_client = None

    # Make request
    response = client.post("/voice/speak", json={
        "output": {"content": "Hello"},
        "options": {}
    })

    # Should return 400 error
    assert response.status_code == 400
    assert "Not in a voice channel" in response.json()["detail"]


# ============================================================
# Health & Status Endpoint Tests
# ============================================================

@pytest.mark.unit
def test_health_check(client, mock_bot):
    """Test health check endpoint"""
    # Mock bot
    discord_bot.bot = mock_bot
    discord_bot.voice_client = None

    # Mock speaker manager
    discord_bot.speaker_manager.get_status = MagicMock(return_value={
        'locked': False,
        'activeSpeaker': None
    })

    # Make request
    response = client.get("/health")

    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["botReady"] is True
    assert data["inVoiceChannel"] is False
    assert data["speakerLocked"] is False
    assert data["activeSpeaker"] is None
    assert "timestamp" in data


@pytest.mark.unit
def test_health_check_with_active_speaker(client, mock_bot, mock_voice_client):
    """Test health check with active speaker"""
    # Mock bot and voice client
    discord_bot.bot = mock_bot
    discord_bot.voice_client = mock_voice_client

    # Mock speaker manager with active speaker
    discord_bot.speaker_manager.get_status = MagicMock(return_value={
        'locked': True,
        'activeSpeaker': 'user_123'
    })

    # Make request
    response = client.get("/health")

    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["inVoiceChannel"] is True
    assert data["speakerLocked"] is True
    assert data["activeSpeaker"] == "user_123"


@pytest.mark.unit
def test_status_endpoint(client, mock_bot):
    """Test detailed status endpoint"""
    # Mock bot
    discord_bot.bot = mock_bot
    discord_bot.voice_client = None

    # Mock speaker manager
    discord_bot.speaker_manager.get_status = MagicMock(return_value={
        'locked': False,
        'activeSpeaker': None,
        'speakingDuration': None,
        'silenceDuration': None
    })

    # Make request
    response = client.get("/status")

    # Assertions
    assert response.status_code == 200
    data = response.json()

    # Verify bot info
    assert "bot" in data
    assert data["bot"]["username"] == "VoxBridge"
    assert data["bot"]["id"] == "123456789"
    assert data["bot"]["ready"] is True

    # Verify voice info
    assert "voice" in data
