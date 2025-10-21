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
import subprocess
import time
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

        # Parallel processing queue
        self.generation_tasks = []
        self.playback_queue = asyncio.Queue()

        # Configuration
        self.chatterbox_url = os.getenv('CHATTERBOX_URL', 'http://localhost:4800/v1')
        self.chatterbox_voice_id = os.getenv('CHATTERBOX_VOICE_ID')

        # Sentence/clause splitting configuration
        use_clause_splitting = os.getenv('USE_CLAUSE_SPLITTING', 'true').lower() == 'true'
        if use_clause_splitting:
            # Split on sentence endings AND clauses (commas, semicolons)
            self.sentence_delimiters = re.compile(r'[.!?\n;,]+')
            self.min_sentence_length = int(os.getenv('MIN_CLAUSE_LENGTH', '10'))
        else:
            # Split only on sentence endings
            self.sentence_delimiters = re.compile(r'[.!?\n]+')
            self.min_sentence_length = int(os.getenv('MIN_SENTENCE_LENGTH', '3'))

        # Parallel processing configuration
        self.use_parallel_processing = os.getenv('USE_PARALLEL_TTS', 'true').lower() == 'true'
        self.use_ffmpeg_streaming = os.getenv('USE_FFMPEG_STREAMING', 'true').lower() == 'true'

        logger.info(f"📋 StreamingResponseHandler initialized for user {user_id}")
        logger.info(f"   Options: {self.options}")
        logger.info(f"   Clause splitting: {use_clause_splitting}")
        logger.info(f"   Parallel TTS: {self.use_parallel_processing}")
        logger.info(f"   FFmpeg streaming: {self.use_ffmpeg_streaming}")

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
        """Process sentence queue with optional parallel processing"""
        self.is_processing = True

        if self.use_parallel_processing:
            # Parallel mode: Generate and play concurrently
            await self._process_queue_parallel()
        else:
            # Sequential mode: Generate, then play, then next
            await self._process_queue_sequential()

        self.is_processing = False

    async def _process_queue_sequential(self) -> None:
        """Process sentence queue sequentially (legacy behavior)"""
        while self.sentence_queue:
            sentence = self.sentence_queue.pop(0)
            logger.info(f"🎵 Processing (sequential): \"{sentence}\"")

            try:
                await self._synthesize_and_play(sentence)
            except Exception as e:
                logger.error(f"❌ Error processing sentence: {e}")

    async def _process_queue_parallel(self) -> None:
        """Process sentence queue with parallel generation and playback"""
        # Start generation tasks for all sentences
        for sentence in self.sentence_queue:
            logger.info(f"🚀 Queuing generation: \"{sentence}\"")
            task = asyncio.create_task(self._generate_audio(sentence))
            self.generation_tasks.append(task)

        # Clear sentence queue since we've queued all tasks
        self.sentence_queue.clear()

        # Start playback consumer
        playback_task = asyncio.create_task(self._playback_consumer())

        # Wait for all generation tasks to complete
        if self.generation_tasks:
            await asyncio.gather(*self.generation_tasks, return_exceptions=True)
            self.generation_tasks.clear()

        # Signal playback consumer to finish
        await self.playback_queue.put(None)

        # Wait for playback to complete
        await playback_task

    async def _playback_consumer(self) -> None:
        """Consume playback queue and play audio as it becomes available"""
        while True:
            item = await self.playback_queue.get()

            if item is None:  # Sentinel value
                break

            sentence, audio_data = item

            try:
                logger.info(f"🔊 Playing (parallel): \"{sentence}\"")
                await self._play_audio_stream(audio_data)
            except Exception as e:
                logger.error(f"❌ Error playing audio: {e}")

    async def _generate_audio(self, sentence: str) -> None:
        """
        Generate audio for a sentence and add to playback queue

        Args:
            sentence: Text to synthesize
        """
        t_start = time.time()

        try:
            logger.info(f"🎤 Generating: \"{sentence}\"")
            audio_data = await self._synthesize_to_stream(sentence)

            t_gen = time.time() - t_start
            logger.info(f"   ⏱️ Generation time: {t_gen:.2f}s")

            # Add to playback queue
            await self.playback_queue.put((sentence, audio_data))

        except Exception as e:
            logger.error(f"❌ Error generating audio for \"{sentence}\": {e}")

    async def _synthesize_to_stream(self, text: str) -> bytes:
        """
        Synthesize text to audio and return as bytes

        Args:
            text: Text to synthesize

        Returns:
            Audio data as bytes
        """
        t_start = time.time()

        # Build TTS request
        tts_data = self._build_tts_request(text)

        # Stream TTS from Chatterbox server with smaller chunks for faster response
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                'POST',
                f"{self.chatterbox_url}/audio/speech/stream/upload",
                data=tts_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            ) as response:
                response.raise_for_status()

                # Collect audio chunks with smaller chunk size for lower latency
                audio_data = bytearray()
                chunk_size = 2048  # Reduced from 8192 for faster first-byte
                total_bytes = 0

                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    audio_data.extend(chunk)
                    total_bytes += len(chunk)

                t_download = time.time() - t_start
                logger.info(f"   ✅ TTS stream complete ({total_bytes} bytes, {t_download:.2f}s)")

                return bytes(audio_data)

    def _build_tts_request(self, text: str) -> dict:
        """Build TTS request data from text and options"""
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

        # Add streaming parameters optimized for low latency
        tts_data['streaming_chunk_size'] = int(self.options.get('chunkSize', 50))  # Reduced from 100
        tts_data['streaming_strategy'] = self.options.get('streamingStrategy', 'sentence')
        tts_data['streaming_quality'] = self.options.get('streamingQuality', 'fast')

        return tts_data

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True
    )
    async def _synthesize_and_play(self, text: str) -> None:
        """
        Send text to Chatterbox TTS and play audio (sequential mode)

        Args:
            text: Text to synthesize
        """
        try:
            t_start = time.time()
            logger.info(f"🔊 Synthesizing: \"{text}\"")

            audio_data = await self._synthesize_to_stream(text)

            t_total = time.time() - t_start
            logger.info(f"   ⏱️ Total synthesis time: {t_total:.2f}s")

            # Play audio
            await self._play_audio_stream(audio_data)

        except Exception as e:
            logger.error(f"❌ Error with TTS: {e}")
            raise

    async def _play_audio_stream(self, audio_data: bytes) -> None:
        """
        Play audio from in-memory bytes using FFmpeg streaming

        Args:
            audio_data: Audio data as bytes (WAV format)
        """
        if not self.voice_client or not self.voice_client.is_connected():
            logger.warning("⚠️ Not connected to voice channel")
            return

        try:
            t_start = time.time()
            logger.info(f"🔊 Playing audio ({len(audio_data)} bytes)")

            # Wait for current audio to finish if playing
            while self.voice_client.is_playing():
                await asyncio.sleep(0.05)  # Reduced from 0.1 for faster response

            if self.use_ffmpeg_streaming:
                # FFmpeg pipe streaming - plays as soon as first chunks arrive
                await self._play_with_ffmpeg_pipe(audio_data)
            else:
                # Legacy temp file method
                await self._play_with_temp_file(audio_data)

            t_playback = time.time() - t_start
            logger.info(f"✅ Audio playback complete ({t_playback:.2f}s)")

        except Exception as e:
            logger.error(f"❌ Error playing audio: {e}")
            raise

    async def _play_with_ffmpeg_pipe(self, audio_data: bytes) -> None:
        """
        Play audio using FFmpeg subprocess with stdin pipe for lowest latency

        Args:
            audio_data: Audio data as bytes
        """
        # FFmpeg command to read from stdin and output Discord-compatible PCM
        # Discord expects: 48kHz, stereo, s16le (signed 16-bit little-endian)
        ffmpeg_args = [
            'ffmpeg',
            '-i', 'pipe:0',  # Read from stdin
            '-f', 's16le',
            '-ar', '48000',
            '-ac', '2',
            'pipe:1'  # Write to stdout
        ]

        # Create FFmpeg process
        process = subprocess.Popen(
            ffmpeg_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        # Feed audio data to FFmpeg stdin in a separate task
        async def feed_stdin():
            try:
                process.stdin.write(audio_data)
                process.stdin.close()
            except Exception as e:
                logger.warning(f"⚠️ Error feeding stdin: {e}")

        asyncio.create_task(feed_stdin())

        # Create Discord audio source from FFmpeg stdout
        audio_source = discord.FFmpegPCMAudio(process.stdout, pipe=True)

        # Play audio
        self.voice_client.play(audio_source)

        # Wait for playback to finish
        while self.voice_client.is_playing():
            await asyncio.sleep(0.05)

        # Clean up process
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()

    async def _play_with_temp_file(self, audio_data: bytes) -> None:
        """
        Play audio using temporary file (legacy method)

        Args:
            audio_data: Audio data as bytes
        """
        import tempfile

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(audio_data)

        try:
            # Create FFmpeg audio source from file with proper resampling
            ffmpeg_options = {
                'options': '-ar 48000 -ac 2'
            }
            audio_source = discord.FFmpegPCMAudio(temp_path, **ffmpeg_options)

            # Play audio
            self.voice_client.play(audio_source)

            # Wait for playback to finish
            while self.voice_client.is_playing():
                await asyncio.sleep(0.05)

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
