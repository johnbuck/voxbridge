"""
Audio sample data for testing

Provides sample Opus and PCM audio data for test cases
"""
import struct
import wave
import io


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
    Get raw PCM audio data (no WAV header)

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
