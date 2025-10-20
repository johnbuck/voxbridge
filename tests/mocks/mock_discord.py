"""
Mock Discord objects for testing VoxBridge

Based on patterns from:
- dpytest library
- Python Discord bot testing helpers
- discord.py specifications
"""
from __future__ import annotations

from typing import Optional, Any, Callable
from unittest.mock import MagicMock, AsyncMock
import asyncio


# ============================================================
# Mock User
# ============================================================

class MockUser:
    """Mock Discord User object"""

    def __init__(self, id: int = 123456789, name: str = "TestUser", bot: bool = False):
        self.id = id
        self.name = name
        self.display_name = name
        self.discriminator = "0001"
        self.bot = bot
        self.avatar = None
        self.mention = f"<@{id}>"

    def __str__(self):
        return f"{self.name}#{self.discriminator}"

    def __repr__(self):
        return f"<MockUser id={self.id} name='{self.name}'>"


# ============================================================
# Mock Guild
# ============================================================

class MockGuild:
    """Mock Discord Guild (Server) object"""

    def __init__(self, id: int = 987654321, name: str = "TestGuild"):
        self.id = id
        self.name = name
        self.owner_id = 111111111
        self.member_count = 10
        self.channels = []
        self.members = []
        self.roles = []

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<MockGuild id={self.id} name='{self.name}'>"


# ============================================================
# Mock Voice Channel
# ============================================================

class MockVoiceChannel:
    """Mock Discord VoiceChannel object"""

    def __init__(
        self,
        id: int = 555555555,
        name: str = "TestVoiceChannel",
        guild: Optional[MockGuild] = None
    ):
        self.id = id
        self.name = name
        self.guild = guild or MockGuild()
        self.members = []
        self.bitrate = 64000
        self.user_limit = 0

    async def connect(self, **kwargs) -> MockVoiceClient:
        """Mock connect to voice channel"""
        return MockVoiceClient(channel=self)

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<MockVoiceChannel id={self.id} name='{self.name}'>"


# ============================================================
# Mock Voice Client
# ============================================================

class MockVoiceClient:
    """
    Mock Discord VoiceClient for audio playback testing

    Simulates discord.VoiceClient behavior for testing
    without requiring a real Discord connection
    """

    def __init__(self, channel: Optional[MockVoiceChannel] = None):
        self.channel = channel or MockVoiceChannel()
        self._connected = True
        self._playing = False
        self._paused = False
        self._current_source = None
        self._after_callback = None

        # Track play/stop calls for testing
        self.play_called = False
        self.stop_called = False
        self.pause_called = False
        self.resume_called = False
        self.disconnect_called = False

        # Playback simulation
        self._playback_task: Optional[asyncio.Task] = None

    def is_connected(self) -> bool:
        """Check if voice client is connected"""
        return self._connected

    def is_playing(self) -> bool:
        """Check if audio is currently playing"""
        return self._playing

    def is_paused(self) -> bool:
        """Check if audio is paused"""
        return self._paused

    def play(
        self,
        source: Any,
        *,
        after: Optional[Callable] = None
    ) -> None:
        """
        Play an audio source

        Args:
            source: Audio source to play (FFmpegPCMAudio, etc.)
            after: Optional callback to call when playback finishes
        """
        self.play_called = True
        self._current_source = source
        self._after_callback = after
        self._playing = True
        self._paused = False

        # Simulate playback duration
        self._playback_task = asyncio.create_task(self._simulate_playback())

    async def _simulate_playback(self):
        """Simulate audio playback for testing"""
        try:
            # Simulate playing for 0.1 seconds (configurable)
            await asyncio.sleep(0.1)
        finally:
            self._playing = False
            if self._after_callback:
                self._after_callback(None)

    def stop(self) -> None:
        """Stop audio playback"""
        self.stop_called = True
        self._playing = False
        self._paused = False
        if self._playback_task and not self._playback_task.done():
            self._playback_task.cancel()

    def pause(self) -> None:
        """Pause audio playback"""
        if self._playing:
            self.pause_called = True
            self._paused = True

    def resume(self) -> None:
        """Resume audio playback"""
        if self._paused:
            self.resume_called = True
            self._paused = False

    async def disconnect(self, *, force: bool = False) -> None:
        """Disconnect from voice channel"""
        self.disconnect_called = True
        self.stop()
        self._connected = False

    def listen(self, sink: Any) -> None:
        """
        Start listening to voice channel (for receiving audio)

        Args:
            sink: Audio sink to receive audio data
        """
        self.sink = sink

    def __repr__(self):
        return f"<MockVoiceClient connected={self._connected} playing={self._playing}>"


# ============================================================
# Mock Audio Source
# ============================================================

class MockAudioSource:
    """Mock audio source for testing (FFmpegPCMAudio, etc.)"""

    def __init__(self, file_path: str = "/fake/path/audio.wav"):
        self.source = file_path
        self.is_opus = False

    def read(self) -> bytes:
        """Read audio data"""
        return b'\x00' * 3840  # Simulate Opus frame

    def cleanup(self) -> None:
        """Cleanup audio source"""
        pass

    def __repr__(self):
        return f"<MockAudioSource source='{self.source}'>"


# ============================================================
# Mock Audio Sink
# ============================================================

class MockAudioSink:
    """
    Mock audio sink for testing audio receiving

    Simulates discord.sinks.Sink for testing AudioReceiver
    """

    def __init__(self):
        self.written_data = []
        self.users = {}

    def write(self, data: Any, user: MockUser) -> None:
        """
        Receive audio data from user

        Args:
            data: Audio data (dict or bytes)
            user: User sending audio
        """
        self.written_data.append({
            'data': data,
            'user': user
        })

        if user.id not in self.users:
            self.users[user.id] = []
        self.users[user.id].append(data)

    def cleanup(self) -> None:
        """Cleanup sink"""
        self.written_data.clear()
        self.users.clear()

    def __repr__(self):
        return f"<MockAudioSink data_count={len(self.written_data)}>"


# ============================================================
# Mock Bot
# ============================================================

class MockBot:
    """Mock Discord Bot for testing"""

    def __init__(self):
        self.user = MockUser(id=999999999, name="VoxBridge", bot=True)
        self._ready = True
        self._closed = False
        self.latency = 0.05
        self.guilds = []

    def is_ready(self) -> bool:
        """Check if bot is ready"""
        return self._ready

    def is_closed(self) -> bool:
        """Check if bot is closed"""
        return self._closed

    def get_channel(self, channel_id: int) -> Optional[MockVoiceChannel]:
        """Get channel by ID"""
        # Return a mock channel for testing
        return MockVoiceChannel(id=channel_id)

    async def fetch_channel(self, channel_id: int) -> MockVoiceChannel:
        """Fetch channel by ID (async)"""
        return MockVoiceChannel(id=channel_id)

    async def close(self) -> None:
        """Close bot connection"""
        self._closed = True

    def __repr__(self):
        return f"<MockBot user={self.user}>"


# ============================================================
# Helper Functions
# ============================================================

def create_mock_opus_packet(size: int = 960) -> bytes:
    """
    Create a mock Opus audio packet for testing

    Args:
        size: Size of packet in samples (default 960 = 20ms at 48kHz)

    Returns:
        Fake Opus packet bytes
    """
    # Opus packet header + random data
    return b'\xf8\xff\xfe' + (b'\x00' * size)


def create_mock_pcm_audio(duration_ms: int = 20) -> bytes:
    """
    Create mock PCM audio data

    Args:
        duration_ms: Duration in milliseconds

    Returns:
        Fake PCM audio bytes (48kHz, 16-bit, stereo)
    """
    samples = int(48000 * duration_ms / 1000)
    return b'\x00' * (samples * 2 * 2)  # 2 bytes per sample, stereo
