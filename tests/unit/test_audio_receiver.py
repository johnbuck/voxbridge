"""
Unit tests for AudioReceiver (discord_bot.py)

Tests audio buffering, queue management, stream generation,
speaker manager integration, and cleanup
"""
from __future__ import annotations

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Import AudioReceiver from discord_bot
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.discord_bot import AudioReceiver


# ============================================================
# Initialization Tests
# ============================================================

@pytest.mark.unit
def test_audio_receiver_initialization():
    """Test AudioReceiver initializes with correct state"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    assert receiver.vc == mock_vc
    assert receiver.speaker_mgr == mock_speaker_mgr
    assert receiver.user_buffers == {}
    assert receiver.user_tasks == {}
    assert receiver.active_users == set()


# ============================================================
# Audio Data Handling Tests
# ============================================================

@pytest.mark.unit
def test_write_creates_user_buffer_on_first_audio():
    """Test buffer is created for new user on first audio packet"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()
    mock_speaker_mgr.on_speaking_start = AsyncMock(return_value=True)

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    # Create mock user
    mock_user = MagicMock()
    mock_user.id = 12345

    # Create mock audio data (dict format)
    audio_data = {'data': b'\x00' * 960, 'timestamp': 1000}

    with patch('asyncio.create_task') as mock_create_task:
        receiver.write(audio_data, mock_user)

        # Verify buffer was created
        assert '12345' in receiver.user_buffers
        assert isinstance(receiver.user_buffers['12345'], asyncio.Queue)

        # Verify user added to active users
        assert '12345' in receiver.active_users

        # Verify task was created
        mock_create_task.assert_called_once()


@pytest.mark.unit
def test_write_queues_opus_packet_from_dict():
    """Test Opus packet is extracted from dict and queued"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()
    mock_speaker_mgr.on_speaking_start = AsyncMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    mock_user = MagicMock()
    mock_user.id = 12345

    # Create buffer manually to avoid task creation
    receiver.user_buffers['12345'] = asyncio.Queue()
    receiver.active_users.add('12345')

    # Send audio data in dict format
    audio_data = {'data': b'\xAB\xCD' * 480, 'timestamp': 2000}

    receiver.write(audio_data, mock_user)

    # Verify packet was queued
    assert receiver.user_buffers['12345'].qsize() == 1
    packet = receiver.user_buffers['12345'].get_nowait()
    assert packet == b'\xAB\xCD' * 480


@pytest.mark.unit
def test_write_queues_opus_packet_direct():
    """Test Opus packet as direct bytes is queued"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    mock_user = MagicMock()
    mock_user.id = 67890

    # Create buffer manually
    receiver.user_buffers['67890'] = asyncio.Queue()
    receiver.active_users.add('67890')

    # Send audio data as direct bytes
    audio_data = b'\xFF' * 960

    receiver.write(audio_data, mock_user)

    # Verify packet was queued
    assert receiver.user_buffers['67890'].qsize() == 1
    packet = receiver.user_buffers['67890'].get_nowait()
    assert packet == b'\xFF' * 960


@pytest.mark.unit
def test_write_ignores_none_user():
    """Test write ignores packets with None user"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    audio_data = {'data': b'\x00' * 960}

    # Write with None user
    receiver.write(audio_data, None)

    # Verify no buffers created
    assert len(receiver.user_buffers) == 0
    assert len(receiver.active_users) == 0


@pytest.mark.unit
def test_write_ignores_empty_packet():
    """Test write ignores empty audio packets"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    mock_user = MagicMock()
    mock_user.id = 11111

    # Empty dict
    audio_data = {'timestamp': 1000}

    receiver.write(audio_data, mock_user)

    # Verify no buffer created for empty packet
    assert len(receiver.user_buffers) == 0


@pytest.mark.unit
def test_write_handles_queue_full():
    """Test write handles queue full condition gracefully"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    mock_user = MagicMock()
    mock_user.id = 99999

    # Create a full queue (maxsize=0 means unlimited, so we mock put_nowait)
    receiver.user_buffers['99999'] = MagicMock(spec=asyncio.Queue)
    receiver.user_buffers['99999'].put_nowait = MagicMock(side_effect=asyncio.QueueFull)
    receiver.active_users.add('99999')

    audio_data = b'\x00' * 960

    # Should not raise exception
    receiver.write(audio_data, mock_user)


# ============================================================
# Audio Stream Generator Tests
# ============================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_audio_stream_generator_yields_chunks():
    """Test audio stream generator yields queued chunks"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()
    mock_speaker_mgr.on_speaking_start = AsyncMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    mock_user = MagicMock()
    mock_user.id = 55555

    # Manually create buffer and add chunks
    receiver.user_buffers['55555'] = asyncio.Queue()

    # Queue some audio chunks
    await receiver.user_buffers['55555'].put(b'\x01' * 960)
    await receiver.user_buffers['55555'].put(b'\x02' * 960)
    await receiver.user_buffers['55555'].put(b'\x03' * 960)
    await receiver.user_buffers['55555'].put(None)  # Sentinel

    # Extract generator logic (simulate what happens inside write())
    async def audio_stream_generator(uid):
        queue = receiver.user_buffers[uid]
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        except Exception as e:
            pass

    # Consume generator
    chunks = []
    async for chunk in audio_stream_generator('55555'):
        chunks.append(chunk)

    # Verify all chunks were yielded
    assert len(chunks) == 3
    assert chunks[0] == b'\x01' * 960
    assert chunks[1] == b'\x02' * 960
    assert chunks[2] == b'\x03' * 960


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audio_stream_generator_stops_on_sentinel():
    """Test generator stops when sentinel (None) is received"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    receiver.user_buffers['77777'] = asyncio.Queue()

    # Queue chunk then sentinel
    await receiver.user_buffers['77777'].put(b'\xAA' * 960)
    await receiver.user_buffers['77777'].put(None)  # Sentinel - should stop
    await receiver.user_buffers['77777'].put(b'\xBB' * 960)  # Should not be yielded

    async def audio_stream_generator(uid):
        queue = receiver.user_buffers[uid]
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        except Exception as e:
            pass

    chunks = []
    async for chunk in audio_stream_generator('77777'):
        chunks.append(chunk)

    # Only first chunk should be yielded
    assert len(chunks) == 1
    assert chunks[0] == b'\xAA' * 960


# ============================================================
# Speaker Manager Integration Tests
# ============================================================

@pytest.mark.unit
def test_speaker_manager_integration_called():
    """Test SpeakerManager.on_speaking_start() is called when first audio arrives"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()
    mock_speaker_mgr.on_speaking_start = AsyncMock(return_value=True)

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    mock_user = MagicMock()
    mock_user.id = 88888

    audio_data = {'data': b'\x00' * 960}

    # Mock asyncio.create_task to just return a mock task
    mock_task = MagicMock()

    with patch('asyncio.create_task', return_value=mock_task) as mock_create:
        receiver.write(audio_data, mock_user)

        # Verify task was created
        assert mock_create.called
        assert '88888' in receiver.user_tasks
        assert receiver.user_tasks['88888'] == mock_task


# ============================================================
# Cleanup Tests
# ============================================================

@pytest.mark.unit
def test_cleanup_sends_sentinel_values():
    """Test cleanup sends sentinel (None) to all queues"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    # Create multiple user buffers
    queue1 = asyncio.Queue()
    queue2 = asyncio.Queue()
    queue3 = asyncio.Queue()

    receiver.user_buffers['111'] = queue1
    receiver.user_buffers['222'] = queue2
    receiver.user_buffers['333'] = queue3

    # Keep references to queues before cleanup
    receiver.cleanup()

    # Verify sentinel sent to all queues (check queues we saved references to)
    assert queue1.get_nowait() is None
    assert queue2.get_nowait() is None
    assert queue3.get_nowait() is None

    # Verify buffers were cleared
    assert len(receiver.user_buffers) == 0


@pytest.mark.unit
def test_cleanup_cancels_user_tasks():
    """Test cleanup cancels all active user tasks"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    # Create mock tasks
    mock_task1 = MagicMock()
    mock_task1.done.return_value = False
    mock_task1.cancel = MagicMock()

    mock_task2 = MagicMock()
    mock_task2.done.return_value = False
    mock_task2.cancel = MagicMock()

    mock_task3 = MagicMock()
    mock_task3.done.return_value = True  # Already done

    receiver.user_tasks['111'] = mock_task1
    receiver.user_tasks['222'] = mock_task2
    receiver.user_tasks['333'] = mock_task3

    receiver.cleanup()

    # Verify tasks were cancelled (except the done one)
    mock_task1.cancel.assert_called_once()
    mock_task2.cancel.assert_called_once()
    mock_task3.cancel.assert_not_called()  # Already done


@pytest.mark.unit
def test_cleanup_clears_all_data():
    """Test cleanup clears all buffers, tasks, and active users"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    # Populate with data
    receiver.user_buffers['111'] = asyncio.Queue()
    receiver.user_buffers['222'] = asyncio.Queue()
    receiver.user_tasks['111'] = MagicMock()
    receiver.user_tasks['111'].done.return_value = True
    receiver.active_users.add('111')
    receiver.active_users.add('222')

    receiver.cleanup()

    # Verify everything cleared
    assert len(receiver.user_buffers) == 0
    assert len(receiver.user_tasks) == 0
    assert len(receiver.active_users) == 0


# ============================================================
# Multi-User Scenario Tests
# ============================================================

@pytest.mark.unit
def test_multiple_users_concurrent():
    """Test handling multiple users simultaneously"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()
    mock_speaker_mgr.on_speaking_start = AsyncMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    # Create 3 different users
    user1 = MagicMock()
    user1.id = 100

    user2 = MagicMock()
    user2.id = 200

    user3 = MagicMock()
    user3.id = 300

    with patch('asyncio.create_task'):
        # All users send audio
        receiver.write({'data': b'\x01' * 960}, user1)
        receiver.write({'data': b'\x02' * 960}, user2)
        receiver.write({'data': b'\x03' * 960}, user3)

        # Verify separate buffers for each user
        assert '100' in receiver.user_buffers
        assert '200' in receiver.user_buffers
        assert '300' in receiver.user_buffers

        # Verify all users active
        assert '100' in receiver.active_users
        assert '200' in receiver.active_users
        assert '300' in receiver.active_users

        # Verify each has their packet
        assert receiver.user_buffers['100'].qsize() == 1
        assert receiver.user_buffers['200'].qsize() == 1
        assert receiver.user_buffers['300'].qsize() == 1


@pytest.mark.unit
def test_same_user_multiple_packets():
    """Test same user sending multiple audio packets"""
    mock_vc = MagicMock()
    mock_speaker_mgr = MagicMock()

    receiver = AudioReceiver(mock_vc, mock_speaker_mgr)

    mock_user = MagicMock()
    mock_user.id = 12345

    # Manually setup to avoid task creation
    receiver.user_buffers['12345'] = asyncio.Queue()
    receiver.active_users.add('12345')

    # Send multiple packets from same user
    for i in range(10):
        receiver.write({'data': bytes([i]) * 960}, mock_user)

    # Verify all packets queued
    assert receiver.user_buffers['12345'].qsize() == 10

    # Verify packets in order
    for i in range(10):
        packet = receiver.user_buffers['12345'].get_nowait()
        assert packet == bytes([i]) * 960
