"""
Audio sample data for testing

Provides sample Opus, PCM, and WebM audio data for test cases
"""
import struct
import wave
import io

# Optional dependencies for WebM fixtures
try:
    import numpy as np
except ImportError:
    np = None  # NumPy not installed, will use Python arrays

try:
    import av
except ImportError:
    av = None  # PyAV not installed, WebM fixtures will raise ImportError


def get_sample_opus_audio() -> bytes:
    """
    Get sample Opus encoded audio packet

    Returns:
        Opus packet bytes (20ms at 48kHz)
    """
    # Simple Opus packet structure for testing
    # In real scenario, this would be actual Opus encoded data
    # For testing, we just need valid-looking bytes

    # Opus frame: TOC byte + compressed data
    toc_byte = 0xFC  # Stereo, 20ms frame, SILK-only
    compressed_data = b'\x00' * 120  # Fake compressed data

    return bytes([toc_byte]) + compressed_data


def get_sample_opus_packets(count: int = 10) -> list[bytes]:
    """
    Get multiple Opus packets for testing streaming

    Args:
        count: Number of packets to generate

    Returns:
        List of Opus packet bytes
    """
    return [get_sample_opus_audio() for _ in range(count)]


def get_sample_wav_audio(duration_ms: int = 1000, sample_rate: int = 48000) -> bytes:
    """
    Generate a simple WAV audio file for testing

    Args:
        duration_ms: Duration in milliseconds
        sample_rate: Sample rate in Hz (default 48000)

    Returns:
        WAV file bytes
    """
    # Calculate number of samples
    num_samples = int(sample_rate * duration_ms / 1000)

    # Generate simple sine wave tone (440 Hz = A4 note)
    import math
    frequency = 440.0
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Simple sine wave
        value = int(32767 * 0.5 * math.sin(2 * math.pi * frequency * t))
        samples.append(value)

    # Create WAV file in memory
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        # Set parameters: 1 channel (mono), 2 bytes per sample, sample rate
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        # Write samples
        for sample in samples:
            wav_file.writeframes(struct.pack('<h', sample))

    return wav_buffer.getvalue()


def get_sample_pcm_audio(duration_ms: int = 20, sample_rate: int = 48000) -> bytes:
    """
    Get raw PCM audio data (no WAV header) - MONO

    NOTE: This is the old mono version. For WebRTC use generate_pcm_audio() which is stereo.

    Args:
        duration_ms: Duration in milliseconds
        sample_rate: Sample rate in Hz

    Returns:
        Raw PCM bytes (16-bit signed, mono)
    """
    num_samples = int(sample_rate * duration_ms / 1000)

    # Generate silence
    samples = [0] * num_samples

    # Pack as 16-bit signed integers
    pcm_data = struct.pack(f'<{len(samples)}h', *samples)

    return pcm_data


def generate_pcm_audio(
    duration_ms: int = 20,
    sample_rate: int = 48000,
    channels: int = 2,
    sample_format: str = 'int16'
) -> bytes:
    """
    Generate raw PCM audio (simulates PyAV decoded output)

    This is what WebRTC handler produces after decoding WebM → PCM.
    WhisperX receives this directly (no Opus decoding needed).

    Args:
        duration_ms: Duration in milliseconds
        sample_rate: Sample rate (48kHz default)
        channels: Number of channels (2 = stereo)
        sample_format: Sample format ('int16' = 16-bit signed)

    Returns:
        Raw PCM bytes (interleaved stereo int16)
    """
    # Calculate number of samples needed
    samples_per_ms = sample_rate / 1000
    total_samples = int(duration_ms * samples_per_ms)

    if np is not None:
        # Use NumPy (faster, preferred)
        # Generate silent audio: shape (samples, channels)
        audio_data = np.zeros((total_samples, channels), dtype=np.int16)

        # Optional: Add slight noise for realism (not pure silence)
        noise_level = 10  # Very quiet
        audio_data += np.random.randint(
            -noise_level, noise_level,
            size=(total_samples, channels),
            dtype=np.int16
        )

        return audio_data.tobytes()
    else:
        # Fallback: Use Python array (slower)
        import array
        # Interleaved stereo: L R L R L R ...
        audio_data = array.array('h', [0] * (total_samples * channels))
        return audio_data.tobytes()


def generate_pcm_frames(num_frames: int = 25) -> bytes:
    """
    Generate multiple PCM frames (for streaming tests)

    Simulates continuous PCM audio from WebRTC decode pipeline.
    Each frame is 20ms of PCM audio.

    Args:
        num_frames: Number of 20ms frames to generate

    Returns:
        Concatenated PCM bytes (num_frames × 3,840 bytes)
    """
    frames = []
    for _ in range(num_frames):
        frames.append(generate_pcm_audio(duration_ms=20))

    return b''.join(frames)


def get_pcm_frame_size(sample_rate: int = 48000, channels: int = 2) -> int:
    """
    Calculate expected PCM frame size for validation

    Used in tests to verify correct PCM audio size.

    Args:
        sample_rate: Sample rate (48kHz default)
        channels: Number of channels (2 = stereo)

    Returns:
        Bytes per 20ms frame (e.g., 3,840 for 48kHz stereo int16)
    """
    samples_per_frame = int((sample_rate * 20) / 1000)  # 960 for 48kHz, 20ms
    bytes_per_sample = 2  # int16 = 2 bytes
    return samples_per_frame * channels * bytes_per_sample


def get_empty_audio() -> bytes:
    """
    Get empty/silent audio data for testing edge cases

    Returns:
        Empty bytes
    """
    return b''


def get_corrupted_audio() -> bytes:
    """
    Get intentionally corrupted audio data for error testing

    Returns:
        Invalid audio bytes
    """
    return b'\xFF\xFF\xFF\xFF' * 10


def get_sample_discord_audio_packet() -> dict:
    """
    Get sample Discord audio packet format

    Discord sends audio in dict format: {'data': bytes, 'timestamp': int}

    Returns:
        Dict with audio data and timestamp
    """
    return {
        'data': get_sample_opus_audio(),
        'timestamp': 1234567890
    }


def get_sample_audio_stream(packet_count: int = 50) -> list[dict]:
    """
    Get a stream of Discord audio packets for testing

    Args:
        packet_count: Number of packets in stream

    Returns:
        List of Discord audio packet dicts
    """
    packets = []
    base_timestamp = 1000000

    for i in range(packet_count):
        packets.append({
            'data': get_sample_opus_audio(),
            'timestamp': base_timestamp + (i * 960)  # 20ms increments
        })

    return packets


# ============================================================
# WebM/OGG Container Fixtures (WebRTC Audio)
# ============================================================

def generate_webm_container(
    duration_ms: int = 20,
    sample_rate: int = 48000,
    channels: int = 2,
    codec: str = 'opus'
) -> bytes:
    """
    Generate minimal WebM container with Opus audio

    Args:
        duration_ms: Duration in milliseconds (20ms = 1 frame)
        sample_rate: Audio sample rate (48kHz default)
        channels: Number of channels (2 = stereo)
        codec: Audio codec to use ('opus' for WebRTC)

    Returns:
        Raw WebM container bytes

    Raises:
        ImportError: If PyAV is not installed
    """
    if av is None:
        raise ImportError("PyAV (av) is required for WebM fixtures. Install with: pip install av")

    buffer = io.BytesIO()

    # Create in-memory WebM container
    container = av.open(buffer, 'w', format='webm')
    # Configure audio layout (channels) when creating stream
    layout = 'stereo' if channels == 2 else 'mono'
    stream = container.add_stream(codec, rate=sample_rate, layout=layout)

    # Calculate number of frames needed
    samples_per_frame = 960  # 20ms at 48kHz
    num_frames = max(1, duration_ms // 20)

    # Generate PCM audio with slight noise (not pure silence)
    for _ in range(num_frames):
        # Create audio frame with slight noise for testing
        if np is not None:
            # Use NumPy (faster, preferred)
            # PyAV planar audio: shape (num_channels, num_samples)
            # Add slight noise to distinguish planar vs interleaved
            noise_level = 100  # Low-level noise for testing
            audio_data = np.random.randint(
                -noise_level, noise_level,
                size=(channels, samples_per_frame),
                dtype=np.int16
            )

            frame = av.AudioFrame.from_ndarray(
                audio_data,
                format='s16p',  # Use planar format (s16p not s16)
                layout='stereo' if channels == 2 else 'mono'
            )
        else:
            # Fallback: Use Python array (slower but works without NumPy)
            import array
            audio_data = array.array('h', [0] * (samples_per_frame * channels))
            frame = av.AudioFrame(format='s16', layout='stereo' if channels == 2 else 'mono', samples=samples_per_frame)
            frame.planes[0].update(audio_data.tobytes())

        frame.sample_rate = sample_rate

        # Encode to Opus and mux
        for packet in stream.encode(frame):
            container.mux(packet)

    # Flush remaining packets
    for packet in stream.encode():
        container.mux(packet)

    container.close()
    return buffer.getvalue()


def generate_incomplete_webm(complete_size: int = 1024) -> bytes:
    """
    Generate incomplete WebM (truncated for buffering tests)

    Args:
        complete_size: Size to truncate to (bytes)

    Returns:
        Incomplete WebM bytes (for testing buffering logic)
    """
    complete_webm = generate_webm_container(duration_ms=100)  # Large enough
    return complete_webm[:complete_size]


def generate_corrupted_webm() -> bytes:
    """
    Generate WebM with corrupted cluster data

    Returns:
        Corrupted WebM bytes (for error handling tests)
    """
    valid_webm = generate_webm_container(duration_ms=20)

    # Corrupt the middle section (cluster data)
    corrupted = bytearray(valid_webm)
    mid_point = len(corrupted) // 2
    corrupted[mid_point:mid_point+100] = b'\xFF' * 100

    return bytes(corrupted)


def generate_multi_frame_webm(num_frames: int = 25) -> bytes:
    """
    Generate WebM with multiple frames (for chunking tests)

    Args:
        num_frames: Number of 20ms frames to generate

    Returns:
        Multi-frame WebM bytes
    """
    return generate_webm_container(duration_ms=num_frames * 20)


# ============================================================
# Pytest Fixtures (add to conftest.py or import in tests)
# ============================================================

def get_sample_webm_audio() -> bytes:
    """Single-frame valid WebM (20ms)"""
    return generate_webm_container(duration_ms=20)


def get_multi_frame_webm_audio() -> bytes:
    """Multi-frame WebM (500ms)"""
    return generate_webm_container(duration_ms=500)


def get_incomplete_webm_audio() -> bytes:
    """Incomplete WebM for buffering tests (512 bytes)"""
    return generate_incomplete_webm(complete_size=512)


def get_corrupted_webm_audio() -> bytes:
    """Corrupted WebM for error handling tests"""
    return generate_corrupted_webm()
