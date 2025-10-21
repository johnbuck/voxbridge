"""
Audio Injection Utilities for E2E Testing

Provides tools to generate realistic audio packets for testing
Discord voice bot functionality without actual voice connections.
"""
from __future__ import annotations

import asyncio
import struct
from typing import List, AsyncGenerator
import random


class AudioInjector:
    """Generate and inject realistic audio packets for testing"""

    # Discord voice uses Opus codec: 48kHz, 20ms frames
    SAMPLE_RATE = 48000
    FRAME_DURATION_MS = 20
    SAMPLES_PER_FRAME = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 960 samples
    CHANNELS = 2  # Stereo
    BYTES_PER_SAMPLE = 2  # 16-bit PCM

    @staticmethod
    def generate_opus_packet(duration_ms: int = 20) -> bytes:
        """
        Generate a single Opus audio packet

        Args:
            duration_ms: Duration in milliseconds (default 20ms = Discord standard)

        Returns:
            Fake Opus packet bytes (3-byte header + payload)
        """
        # Opus packet structure:
        # - Header: 3 bytes (TOC + optional frame count + optional padding)
        # - Payload: Variable length compressed audio

        # TOC byte: Configuration, stereo, frame count
        toc_byte = 0xF8  # Typical Opus TOC for voice

        # Generate random compressed payload (realistic size: 60-120 bytes)
        payload_size = random.randint(60, 120)
        payload = bytes([random.randint(0, 255) for _ in range(payload_size)])

        return bytes([toc_byte, 0xFF, 0xFE]) + payload

    @staticmethod
    def generate_opus_stream(duration_ms: int) -> List[bytes]:
        """
        Generate a stream of Opus packets for specified duration

        Args:
            duration_ms: Total duration in milliseconds

        Returns:
            List of Opus packets (one per 20ms)
        """
        num_packets = duration_ms // AudioInjector.FRAME_DURATION_MS
        return [AudioInjector.generate_opus_packet() for _ in range(num_packets)]

    @staticmethod
    def generate_pcm_audio(duration_ms: int, silence: bool = False) -> bytes:
        """
        Generate PCM audio data

        Args:
            duration_ms: Duration in milliseconds
            silence: If True, generate silence; otherwise generate noise

        Returns:
            PCM audio bytes (48kHz, 16-bit, stereo)
        """
        samples = int(AudioInjector.SAMPLE_RATE * duration_ms / 1000)
        pcm_data = bytearray()

        for _ in range(samples):
            if silence:
                # Silence = zero amplitude
                left = right = 0
            else:
                # Simple noise for testing (low amplitude)
                left = random.randint(-1000, 1000)
                right = random.randint(-1000, 1000)

            # Pack as signed 16-bit little-endian (s16le)
            pcm_data += struct.pack('<h', left)
            pcm_data += struct.pack('<h', right)

        return bytes(pcm_data)

    @staticmethod
    async def stream_to_voice_client(
        voice_client,
        packets: List[bytes],
        realtime: bool = True
    ):
        """
        Stream audio packets to a voice client

        Args:
            voice_client: Discord voice client (or mock)
            packets: List of Opus packets to send
            realtime: If True, send packets at 20ms intervals (realistic)
                     If False, send as fast as possible (faster tests)
        """
        for packet in packets:
            # In real Discord, this would be sent via UDP to voice server
            # For testing, we simulate this by calling the audio receiver
            if hasattr(voice_client, 'sink') and voice_client.sink:
                await voice_client.sink.write(packet)

            if realtime:
                await asyncio.sleep(0.02)  # 20ms delay between packets

    @staticmethod
    async def stream_audio_generator(
        duration_ms: int,
        realtime: bool = True
    ) -> AsyncGenerator[bytes, None]:
        """
        Generate audio packets as an async generator

        Args:
            duration_ms: Total duration in milliseconds
            realtime: If True, yield packets at 20ms intervals

        Yields:
            Opus audio packets
        """
        packets = AudioInjector.generate_opus_stream(duration_ms)

        for packet in packets:
            yield packet
            if realtime:
                await asyncio.sleep(0.02)

    @staticmethod
    def create_audio_profile(text: str) -> dict:
        """
        Create an audio profile matching spoken text

        Estimates realistic audio duration based on text length

        Args:
            text: Text that would be spoken

        Returns:
            Dict with audio parameters (duration_ms, num_packets, etc.)
        """
        # Rough estimate: ~150 words per minute
        # Average word length: ~5 characters
        words = len(text.split())
        chars = len(text)

        # Calculate duration (ms)
        # ~150 words/min = ~2.5 words/sec = ~400ms per word
        duration_ms = max(500, words * 400)  # Minimum 500ms

        # Adjust for punctuation (pauses)
        pauses = text.count('.') + text.count('!') + text.count('?')
        duration_ms += pauses * 300  # 300ms pause per sentence

        num_packets = duration_ms // AudioInjector.FRAME_DURATION_MS

        return {
            'text': text,
            'duration_ms': duration_ms,
            'num_packets': num_packets,
            'words': words,
            'chars': chars
        }


# ============================================================
# Pre-defined Audio Samples for Testing
# ============================================================

class AudioSamples:
    """Pre-defined audio samples for common test scenarios"""

    @staticmethod
    def short_question() -> List[bytes]:
        """Short question: 'What time is it?' (~1 second)"""
        return AudioInjector.generate_opus_stream(1000)

    @staticmethod
    def long_question() -> List[bytes]:
        """Long question: 'Can you tell me about the weather forecast for tomorrow?' (~3 seconds)"""
        return AudioInjector.generate_opus_stream(3000)

    @staticmethod
    def sentence() -> List[bytes]:
        """Single sentence: 'This is a test sentence.' (~2 seconds)"""
        return AudioInjector.generate_opus_stream(2000)

    @staticmethod
    def paragraph() -> List[bytes]:
        """Paragraph-length speech (~10 seconds)"""
        return AudioInjector.generate_opus_stream(10000)

    @staticmethod
    def silence(duration_ms: int = 800) -> List[bytes]:
        """Silence packets (for testing silence detection)"""
        # Opus packets with minimal payload for silence
        num_packets = duration_ms // AudioInjector.FRAME_DURATION_MS
        return [bytes([0xF8, 0x00, 0x00]) + b'\x00' * 10 for _ in range(num_packets)]
