"""
TTS Audio Generator for E2E Testing

Provides utilities to generate realistic audio samples using Chatterbox TTS
for transcription accuracy testing. These samples have known text content
which can be validated against WhisperX transcriptions.

Usage:
    # Generate audio for testing
    generator = TTSAudioGenerator()
    webm_audio = await generator.generate_webm("Hello world")

    # Save for manual inspection
    generator.save_webm_file(webm_audio, "test_hello.webm")

Note: Requires Chatterbox TTS server running at CHATTERBOX_URL
"""
from __future__ import annotations

import asyncio
import logging
import os
import io
from typing import Optional
from pathlib import Path

import httpx

try:
    import av
except ImportError:
    av = None  # PyAV not installed

try:
    import numpy as np
except ImportError:
    np = None  # NumPy not installed

logger = logging.getLogger(__name__)


class TTSAudioGenerator:
    """
    Generate audio samples using Chatterbox TTS for E2E testing

    Converts TTS-generated audio to WebM format for WebRTC testing.
    """

    def __init__(
        self,
        chatterbox_url: Optional[str] = None,
        voice_id: str = "default",
        timeout: float = 30.0
    ):
        """
        Initialize TTS audio generator

        Args:
            chatterbox_url: Chatterbox TTS API URL (default: from env or localhost:4123)
            voice_id: Voice ID to use for TTS
            timeout: HTTP request timeout in seconds
        """
        self.chatterbox_url = chatterbox_url or os.getenv(
            'CHATTERBOX_URL',
            'http://localhost:4123'
        )
        self.voice_id = voice_id
        self.timeout = timeout

    async def generate_wav(self, text: str) -> bytes:
        """
        Generate WAV audio using Chatterbox TTS

        Args:
            text: Text to synthesize

        Returns:
            WAV audio bytes

        Raises:
            Exception: If TTS generation fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Use Chatterbox streaming endpoint
                url = f"{self.chatterbox_url}/audio/speech/stream/upload"

                response = await client.post(
                    url,
                    data={
                        "input": text,
                        "voice": self.voice_id,
                        "response_format": "wav",  # Request WAV format
                        "speed": 1.0
                    }
                )

                if response.status_code != 200:
                    raise Exception(
                        f"TTS failed: {response.status_code} - {response.text}"
                    )

                # Collect audio chunks
                audio_bytes = response.content

                logger.info(
                    f"Generated TTS audio: {len(audio_bytes):,} bytes "
                    f"for text \"{text[:50]}...\""
                )

                return audio_bytes

        except Exception as e:
            logger.error(f"Failed to generate TTS audio: {e}")
            raise

    async def generate_webm(self, text: str) -> bytes:
        """
        Generate WebM audio using Chatterbox TTS

        Converts TTS WAV output to WebM/Opus format for WebRTC testing.

        Args:
            text: Text to synthesize

        Returns:
            WebM container bytes with Opus audio

        Raises:
            ImportError: If PyAV is not installed
            Exception: If TTS or conversion fails
        """
        if av is None:
            raise ImportError(
                "PyAV is required for WebM generation. "
                "Install with: pip install av"
            )

        # Generate WAV from TTS
        wav_bytes = await self.generate_wav(text)

        # Convert WAV to WebM/Opus
        webm_bytes = self._convert_wav_to_webm(wav_bytes)

        logger.info(
            f"Converted to WebM: {len(webm_bytes):,} bytes "
            f"for text \"{text[:50]}...\""
        )

        return webm_bytes

    def _convert_wav_to_webm(self, wav_bytes: bytes) -> bytes:
        """
        Convert WAV to WebM/Opus format

        Args:
            wav_bytes: WAV audio bytes

        Returns:
            WebM container bytes
        """
        # Read WAV
        input_buffer = io.BytesIO(wav_bytes)
        input_container = av.open(input_buffer, 'r')
        input_stream = input_container.streams.audio[0]

        # Create WebM output
        output_buffer = io.BytesIO()
        output_container = av.open(output_buffer, 'w', format='webm')

        # Add Opus audio stream (WebRTC standard)
        # Match expected format: 48kHz stereo
        output_stream = output_container.add_stream(
            'opus',
            rate=48000,
            layout='stereo'
        )

        # Transcode
        for frame in input_container.decode(input_stream):
            # Resample to 48kHz stereo if needed
            if frame.sample_rate != 48000:
                frame = frame.resampler(48000, 'stereo')

            # Encode to Opus and mux
            for packet in output_stream.encode(frame):
                output_container.mux(packet)

        # Flush
        for packet in output_stream.encode():
            output_container.mux(packet)

        input_container.close()
        output_container.close()

        return output_buffer.getvalue()

    def save_webm_file(self, webm_bytes: bytes, filename: str) -> Path:
        """
        Save WebM audio to file for manual inspection

        Args:
            webm_bytes: WebM container bytes
            filename: Output filename (will be saved to tests/fixtures/audio/)

        Returns:
            Path to saved file
        """
        # Save to fixtures directory
        fixtures_dir = Path(__file__).parent / "audio"
        fixtures_dir.mkdir(exist_ok=True)

        output_path = fixtures_dir / filename

        with open(output_path, 'wb') as f:
            f.write(webm_bytes)

        logger.info(f"Saved WebM audio: {output_path} ({len(webm_bytes):,} bytes)")

        return output_path

    async def is_available(self) -> bool:
        """
        Check if Chatterbox TTS service is available

        Returns:
            True if service is reachable and healthy
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.chatterbox_url}/health")
                return response.status_code == 200
        except Exception:
            return False


# ============================================================
# Pre-Generated Audio Samples
# ============================================================

class PreGeneratedAudioSamples:
    """
    Pre-generated audio samples for offline testing

    These samples were generated using TTSAudioGenerator and saved
    to the fixtures directory. Use these when Chatterbox is not available.
    """

    AUDIO_DIR = Path(__file__).parent / "audio"

    @classmethod
    def get_hello_world(cls) -> Optional[bytes]:
        """Load pre-generated "Hello world" audio"""
        return cls._load_audio("hello_world.webm")

    @classmethod
    def get_short_question(cls) -> Optional[bytes]:
        """Load pre-generated "What time is it?" audio"""
        return cls._load_audio("what_time_is_it.webm")

    @classmethod
    def get_long_sentence(cls) -> Optional[bytes]:
        """Load pre-generated long sentence audio"""
        return cls._load_audio("long_sentence.webm")

    @classmethod
    def _load_audio(cls, filename: str) -> Optional[bytes]:
        """Load audio file from fixtures directory"""
        filepath = cls.AUDIO_DIR / filename

        if not filepath.exists():
            logger.warning(
                f"Audio fixture not found: {filepath}. "
                f"Generate with TTSAudioGenerator first."
            )
            return None

        with open(filepath, 'rb') as f:
            return f.read()

    @classmethod
    def list_available(cls) -> list[str]:
        """List all available pre-generated audio files"""
        if not cls.AUDIO_DIR.exists():
            return []

        return [
            f.name for f in cls.AUDIO_DIR.glob("*.webm")
        ]


# ============================================================
# CLI Tool for Generating Test Fixtures
# ============================================================

async def generate_test_fixtures():
    """
    CLI tool to generate audio fixtures for testing

    Run with:
        python -m tests.fixtures.tts_audio_generator
    """
    print("🎤 TTS Audio Fixture Generator")
    print("=" * 60)

    generator = TTSAudioGenerator()

    # Check if Chatterbox is available
    print("\n1. Checking Chatterbox availability...")
    is_available = await generator.is_available()

    if not is_available:
        print(f"   ❌ Chatterbox not available at {generator.chatterbox_url}")
        print(f"   Start Chatterbox TTS server first:")
        print(f"   cd ../chatterbox-tts-api && docker compose up -d")
        return

    print(f"   ✅ Chatterbox available at {generator.chatterbox_url}")

    # Generate test fixtures
    fixtures = [
        ("hello_world.webm", "Hello world"),
        ("what_time_is_it.webm", "What time is it?"),
        ("long_sentence.webm", "This is a longer sentence to test multi-chunk streaming and transcription accuracy."),
        ("test_phrase.webm", "The quick brown fox jumps over the lazy dog"),
    ]

    print(f"\n2. Generating {len(fixtures)} audio fixtures...")

    for filename, text in fixtures:
        print(f"\n   Generating: {filename}")
        print(f"   Text: \"{text}\"")

        try:
            # Generate WebM audio
            webm_audio = await generator.generate_webm(text)

            # Save to fixtures directory
            output_path = generator.save_webm_file(webm_audio, filename)

            print(f"   ✅ Saved: {output_path} ({len(webm_audio):,} bytes)")

        except Exception as e:
            print(f"   ❌ Failed: {e}")

    print("\n" + "=" * 60)
    print("✅ Fixture generation complete!")
    print("\nGenerated files:")

    for available in PreGeneratedAudioSamples.list_available():
        print(f"   - {available}")

    print("\nUsage in tests:")
    print("   from tests.fixtures.tts_audio_generator import PreGeneratedAudioSamples")
    print("   audio = PreGeneratedAudioSamples.get_hello_world()")


if __name__ == "__main__":
    # Run fixture generator
    asyncio.run(generate_test_fixtures())
