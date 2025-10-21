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
from discord.ext import voice_recv


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
    """Mock VoiceRecvClient"""
    client = MagicMock(spec=voice_recv.VoiceRecvClient)
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


# ============================================================
# Voice Receiving Tests
# ============================================================

@pytest.mark.unit
def test_audio_receiver_wants_opus():
    """Test AudioReceiver requests Opus packets"""
    from src.discord_bot import AudioReceiver

    mock_loop = MagicMock()
    receiver = AudioReceiver(MagicMock(), MagicMock(), mock_loop)

    # Verify wants_opus() returns True
    assert receiver.wants_opus() is True


@pytest.mark.unit
def test_audio_receiver_inherits_from_audio_sink():
    """Test AudioReceiver is a voice_recv.AudioSink"""
    from src.discord_bot import AudioReceiver

    mock_loop = MagicMock()
    receiver = AudioReceiver(MagicMock(), MagicMock(), mock_loop)

    # Verify it's an instance of AudioSink
    assert isinstance(receiver, voice_recv.AudioSink)


@pytest.mark.unit
def test_join_voice_uses_voice_recv_client(client, mock_bot, mock_voice_channel, mock_voice_client):
    """Test that join uses VoiceRecvClient for voice receiving"""
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

    # Verify connect was called with cls parameter
    mock_voice_channel.connect.assert_called_once()
    call_kwargs = mock_voice_channel.connect.call_args[1]
    assert 'cls' in call_kwargs
    assert call_kwargs['cls'] == voice_recv.VoiceRecvClient

    # Verify listen() was called
    mock_voice_client.listen.assert_called_once()


@pytest.mark.unit
def test_audio_receiver_write_extracts_opus_packet():
    """Test AudioReceiver.write() extracts Opus packet from VoiceData"""
    from src.discord_bot import AudioReceiver

    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()
    mock_speaker_mgr.on_speaking_start = AsyncMock()
    mock_speaker_mgr.on_audio_data = AsyncMock()  # Added for new silence detection
    mock_loop = MagicMock()

    # Mock run_coroutine_threadsafe to handle coroutines
    def mock_run_coroutine(coro, loop):
        coro.close()
        return MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr, mock_loop)

    # Create mock user
    mock_user = MagicMock()
    mock_user.id = 123456789

    # Create mock VoiceData
    mock_voice_data = MagicMock(spec=voice_recv.VoiceData)
    mock_voice_data.opus = b'\x00' * 960  # Opus audio bytes

    with patch('asyncio.run_coroutine_threadsafe', side_effect=mock_run_coroutine):
        # Call write()
        receiver.write(mock_user, mock_voice_data)

    # Verify user buffer was created
    assert str(mock_user.id) in receiver.user_buffers


@pytest.mark.unit
def test_audio_receiver_calls_on_audio_data():
    """Test AudioReceiver.write() calls on_audio_data() for silence detection"""
    from src.discord_bot import AudioReceiver

    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()
    mock_speaker_mgr.on_speaking_start = AsyncMock()
    mock_speaker_mgr.on_audio_data = AsyncMock()
    mock_loop = MagicMock()

    # Mock run_coroutine_threadsafe to track calls
    call_tracker = []
    def mock_run_coroutine(coro, loop):
        call_tracker.append(coro)
        # Close coroutine to prevent warnings
        coro.close()
        return MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr, mock_loop)

    # Create mock user
    mock_user = MagicMock()
    mock_user.id = 123456789

    # Create mock VoiceData
    mock_voice_data = MagicMock(spec=voice_recv.VoiceData)
    mock_voice_data.opus = b'\x00' * 960

    with patch('asyncio.run_coroutine_threadsafe', side_effect=mock_run_coroutine):
        # First call - creates buffer and starts speaking
        receiver.write(mock_user, mock_voice_data)

        # Second call - should call on_audio_data
        receiver.write(mock_user, mock_voice_data)

        # Third call - should also call on_audio_data
        receiver.write(mock_user, mock_voice_data)

    # Verify on_audio_data was scheduled at least twice (after first packet)
    # First call schedules on_speaking_start, subsequent calls schedule on_audio_data
    assert len(call_tracker) >= 3  # 1 on_speaking_start + 2 on_audio_data


@pytest.mark.unit
def test_audio_receiver_updates_silence_detection_on_each_packet():
    """Test that each audio packet resets silence detection timer"""
    from src.discord_bot import AudioReceiver

    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()
    mock_speaker_mgr.on_speaking_start = AsyncMock()
    mock_speaker_mgr.on_audio_data = AsyncMock()
    mock_loop = MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr, mock_loop)

    # Create mock user
    mock_user = MagicMock()
    mock_user.id = 123456789

    # Create mock VoiceData
    mock_voice_data = MagicMock(spec=voice_recv.VoiceData)
    mock_voice_data.opus = b'\x00' * 960

    # Mock run_coroutine_threadsafe
    coroutines_scheduled = []
    def track_coro(coro, loop):
        coroutines_scheduled.append(coro)
        coro.close()
        return MagicMock()

    with patch('asyncio.run_coroutine_threadsafe', side_effect=track_coro):
        # First packet - starts speaking AND calls on_audio_data
        receiver.write(mock_user, mock_voice_data)

        # Simulate 5 more audio packets arriving
        for i in range(5):
            receiver.write(mock_user, mock_voice_data)

    # Should have scheduled: 1 on_speaking_start + 6 on_audio_data calls (including first packet)
    assert len(coroutines_scheduled) == 7
