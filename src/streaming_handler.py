#!/usr/bin/env python3
"""
============================================================
Streaming Response Handler
Handles streaming AI responses from n8n webhook
- Receives text chunks as they arrive from AI
- Buffers and extracts complete sentences
- Sends sentences to Chatterbox TTS streaming endpoint
- Plays audio immediately as it's generated
============================================================
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from typing import Optional
from io import BytesIO

import httpx
import discord
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

logger = logging.getLogger(__name__)


class StreamingResponseHandler:
    """Handles streaming text-to-speech responses from n8n"""

    def __init__(self, voice_client, user_id: str, options: dict = None):
        """
        Initialize streaming response handler

        Args:
            voice_client: Discord voice client for audio playback
            user_id: Discord user ID
            options: TTS options from n8n (optional)
        """
        self.voice_client = voice_client
        self.user_id = user_id
        self.buffer = ''
        self.sentence_queue = []
        self.is_processing = False
        self.options = options or {}

        # Configuration
        self.chatterbox_url = os.getenv('CHATTERBOX_URL', 'http://localhost:4800/v1')
        self.chatterbox_voice_id = os.getenv('CHATTERBOX_VOICE_ID')
        self.sentence_delimiters = re.compile(r'[.!?\n]+')
        self.min_sentence_length = 3  # Ignore very short fragments

        logger.info(f"📋 StreamingResponseHandler initialized for user {user_id}")
        logger.info(f"   Options: {self.options}")

    async def on_chunk(self, text_chunk: str) -> None:
        """
        Handle incoming text chunk from n8n streaming webhook

        Args:
            text_chunk: Text chunk from n8n
        """
        if not text_chunk:
            return

        logger.info(f"📨 Received chunk: \"{text_chunk}\"")
        self.buffer += text_chunk

        # Extract complete sentences
        sentences = self._extract_sentences()

        if sentences:
            logger.info(f"✂️ Extracted {len(sentences)} sentence(s)")
            self.sentence_queue.extend(sentences)

            # Start processing queue if not already processing
            if not self.is_processing:
                asyncio.create_task(self._process_queue())

    def _extract_sentences(self) -> list[str]:
        """
        Extract complete sentences from buffer

        Returns:
            List of complete sentences
        """
        sentences = []
        last_index = 0

        # Find all sentence delimiters
        for match in self.sentence_delimiters.finditer(self.buffer):
            end_index = match.end()
            sentence = self.buffer[last_index:end_index].strip()

            # Only add if sentence is long enough
            if len(sentence) >= self.min_sentence_length:
                sentences.append(sentence)

            last_index = end_index

        # Update buffer to keep incomplete sentence
        self.buffer = self.buffer[last_index:].strip()

        return sentences

    async def _process_queue(self) -> None:
        """Process sentence queue sequentially"""
        self.is_processing = True

        while self.sentence_queue:
            sentence = self.sentence_queue.pop(0)
            logger.info(f"🎵 Processing: \"{sentence}\"")

            try:
                await self._synthesize_and_play(sentence)
            except Exception as e:
                logger.error(f"❌ Error processing sentence: {e}")
                # Continue with next sentence even if this one fails

        self.is_processing = False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True
    )
    async def _synthesize_and_play(self, text: str) -> None:
        """
        Send text to Chatterbox TTS streaming endpoint and play audio with retry

        Args:
            text: Text to synthesize
        """
        try:
            logger.info(f"🔊 Synthesizing: \"{text}\"")

            # Build TTS request with options from n8n (or defaults)
            tts_data = {
                'input': text,
                'response_format': self.options.get('outputFormat', 'wav'),
                'speed': float(self.options.get('speedFactor', 1.0))
            }

            # Add voice parameter
            voice_mode = self.options.get('voiceMode')
            reference_audio = self.options.get('referenceAudioFilename')

            if voice_mode == 'clone' and reference_audio:
                tts_data['voice'] = reference_audio
            elif self.chatterbox_voice_id:
                tts_data['voice'] = self.chatterbox_voice_id
            else:
                tts_data['voice'] = 'default'

            # Add generation parameters
            if 'temperature' in self.options:
                tts_data['temperature'] = float(self.options['temperature'])
            if 'exaggeration' in self.options:
                tts_data['exaggeration'] = float(self.options['exaggeration'])
            if 'cfgWeight' in self.options:
                tts_data['cfg_weight'] = float(self.options['cfgWeight'])

            # Add streaming parameters with optimal defaults
            tts_data['streaming_chunk_size'] = int(self.options.get('chunkSize', 100))
            tts_data['streaming_strategy'] = self.options.get('streamingStrategy', 'sentence')
            tts_data['streaming_quality'] = self.options.get('streamingQuality', 'fast')

            logger.debug(f"   📋 TTS Request: {tts_data}")

            # Stream TTS from Chatterbox server - TRUE STREAMING
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    'POST',
                    f"{self.chatterbox_url}/audio/speech/stream/upload",
                    data=tts_data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                ) as response:
                    response.raise_for_status()

                    # Save streaming audio to temp file
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                        temp_path = temp_file.name
                        total_bytes = 0

                        # Stream chunks as they arrive
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            temp_file.write(chunk)
                            temp_file.flush()
                            total_bytes += len(chunk)

                    logger.info(f"   ✅ TTS stream complete ({total_bytes} bytes)")

                    # Play audio in voice channel
                    await self._play_audio_from_file(temp_path)

        except Exception as e:
            logger.error(f"❌ Error with TTS: {e}")
            raise

    async def _play_audio_from_file(self, temp_path: str) -> None:
        """
        Play audio from file in Discord voice channel

        Args:
            temp_path: Path to temporary audio file (WAV format)
        """
        try:
            logger.info("🔊 Playing audio in voice channel")

            # Create FFmpeg audio source from file with proper resampling
            # Discord expects 48kHz stereo or mono, Chatterbox outputs 24kHz
            ffmpeg_options = {
                'options': '-ar 48000 -ac 2'  # Resample to 48kHz stereo
            }
            audio_source = discord.FFmpegPCMAudio(temp_path, **ffmpeg_options)

            # Play audio
            if self.voice_client and self.voice_client.is_connected():
                # Wait for current audio to finish if playing
                while self.voice_client.is_playing():
                    await asyncio.sleep(0.1)

                self.voice_client.play(audio_source)

                # Wait for playback to finish
                while self.voice_client.is_playing():
                    await asyncio.sleep(0.1)

                logger.info("✅ Audio playback complete")
            else:
                logger.warning("⚠️ Not connected to voice channel")

        except Exception as e:
            logger.error(f"❌ Error playing audio: {e}")
            raise
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"⚠️ Failed to delete temp file {temp_path}: {e}")

    async def finalize(self) -> None:
        """Finalize streaming - process any remaining buffered text"""
        if self.buffer.strip():
            logger.info(f"🏁 Finalizing with remaining buffer: \"{self.buffer}\"")
            # Treat remaining buffer as final sentence
            if len(self.buffer.strip()) >= self.min_sentence_length:
                self.sentence_queue.append(self.buffer.strip())
                self.buffer = ''

                # Process final queue if not already processing
                if not self.is_processing:
                    await self._process_queue()
