#!/usr/bin/env python3
"""
============================================================
WhisperX WebSocket Client
Handles streaming audio to WhisperX server for transcription
- Connects to WhisperX WebSocket server
- Streams Opus audio chunks
- Receives partial and final transcription results
============================================================
"""

import asyncio
import websockets
import json
import logging
import os
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class WhisperClient:
    """WebSocket client for streaming audio to WhisperX server with auto-reconnect"""

    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.transcript_buffer: str = ''
        self.is_connected: bool = False
        self.user_id: Optional[str] = None
        self.finalize_future: Optional[asyncio.Future] = None
        self.reconnect_attempts: int = 0
        self.max_reconnect_attempts: int = 5
        self.reconnect_delay: float = 1.0  # Initial delay in seconds
        self.should_reconnect: bool = True

        # Configuration
        self.whisper_server_url = os.getenv('WHISPER_SERVER_URL', 'ws://localhost:4901')
        self.whisper_language = os.getenv('WHISPER_LANGUAGE', 'en')

        # Message handler callbacks
        self.on_partial_callback: Optional[Callable] = None
        self.on_final_callback: Optional[Callable] = None
        self.on_error_callback: Optional[Callable] = None

    async def connect(self, user_id: str, retry: bool = True) -> None:
        """
        Connect to WhisperX WebSocket server with auto-retry

        Args:
            user_id: User ID for this transcription session
            retry: Whether to retry on failure
        """
        self.user_id = user_id
        self.should_reconnect = retry

        while self.reconnect_attempts <= self.max_reconnect_attempts:
            try:
                logger.info(f"🔌 Connecting to WhisperX server at {self.whisper_server_url} (attempt {self.reconnect_attempts + 1})")
                self.ws = await websockets.connect(
                    self.whisper_server_url,
                    ping_interval=20,
                    ping_timeout=10
                )
                self.is_connected = True
                self.reconnect_attempts = 0  # Reset on successful connection
                logger.info(f"✅ Connected to WhisperX for user {user_id}")

                # Send initial metadata
                start_message = json.dumps({
                    'type': 'start',
                    'userId': user_id,
                    'language': self.whisper_language
                })
                await self.ws.send(start_message)
                logger.info(f"📤 Sent start message for user {user_id}")

                # Start message listener task
                asyncio.create_task(self._listen_for_messages())
                return

            except Exception as e:
                self.reconnect_attempts += 1
                logger.error(f"❌ Failed to connect to WhisperX (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}): {e}")

                if not retry or self.reconnect_attempts > self.max_reconnect_attempts:
                    logger.error(f"❌ Max reconnection attempts reached for WhisperX")
                    raise

                # Exponential backoff
                delay = self.reconnect_delay * (2 ** (self.reconnect_attempts - 1))
                delay = min(delay, 30.0)  # Cap at 30 seconds
                logger.info(f"⏳ Retrying connection in {delay:.1f} seconds...")
                await asyncio.sleep(delay)

    async def _listen_for_messages(self) -> None:
        """Listen for incoming messages from WhisperX server"""
        try:
            async for message in self.ws:
                await self._handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"🔌 WhisperX connection closed for user {self.user_id}")
            self.is_connected = False
        except Exception as e:
            logger.error(f"❌ Error in message listener: {e}")
            self.is_connected = False

    async def _handle_message(self, message: str) -> None:
        """
        Handle incoming message from WhisperX server

        Args:
            message: JSON message from server
        """
        try:
            data = json.loads(message)
            msg_type = data.get('type')

            if msg_type == 'partial':
                # Partial transcription result (real-time)
                text = data.get('text', '')
                if text:
                    logger.info(f"🔄 Partial: \"{text}\"")
                    self.transcript_buffer = text
                    if self.on_partial_callback:
                        await self.on_partial_callback(text)

            elif msg_type == 'final':
                # Final transcription result
                text = data.get('text', '')
                if text:
                    logger.info(f"✅ Final: \"{text}\"")
                    self.transcript_buffer = text
                else:
                    logger.info(f"✅ Final: (empty)")

                if self.on_final_callback:
                    await self.on_final_callback(text)

                # Resolve pending finalize future
                if self.finalize_future and not self.finalize_future.done():
                    self.finalize_future.set_result(self.transcript_buffer)

            elif msg_type == 'error':
                error_msg = data.get('error', 'Unknown error')
                logger.error(f"❌ WhisperX error: {error_msg}")
                if self.on_error_callback:
                    await self.on_error_callback(error_msg)

        except json.JSONDecodeError:
            logger.error(f"❌ Invalid JSON from WhisperX: {message}")
        except Exception as e:
            logger.error(f"❌ Error handling WhisperX message: {e}")

    async def send_audio(self, audio_chunk: bytes) -> None:
        """
        Send audio chunk to WhisperX server

        Args:
            audio_chunk: Binary Opus audio data
        """
        if not self.is_connected or not self.ws:
            logger.warning("⚠️ Cannot send audio - not connected to WhisperX")
            return

        try:
            await self.ws.send(audio_chunk)
        except Exception as e:
            logger.error(f"❌ Error sending audio: {e}")
            self.is_connected = False

    async def finalize(self) -> str:
        """
        Request finalization of transcription and wait for result

        Returns:
            Final transcription text
        """
        if not self.is_connected or not self.ws:
            logger.warning("⚠️ Cannot finalize - not connected to WhisperX")
            return self.transcript_buffer

        try:
            logger.info(f"🏁 Requesting finalization for user {self.user_id}")

            # Create future to wait for final result
            self.finalize_future = asyncio.Future()

            # Send finalize message
            finalize_message = json.dumps({'type': 'finalize'})
            await self.ws.send(finalize_message)

            # Wait for final result (with timeout)
            try:
                result = await asyncio.wait_for(self.finalize_future, timeout=10.0)
                return result
            except asyncio.TimeoutError:
                logger.warning("⏱️ Finalize timeout - returning buffered transcript")
                return self.transcript_buffer

        except Exception as e:
            logger.error(f"❌ Error finalizing transcription: {e}")
            return self.transcript_buffer

    async def close(self) -> None:
        """Close WebSocket connection"""
        if self.ws and self.is_connected:
            try:
                logger.info(f"🔒 Closing WhisperX connection for user {self.user_id}")
                close_message = json.dumps({'type': 'close'})
                await self.ws.send(close_message)
                await self.ws.close()
            except Exception as e:
                logger.error(f"❌ Error closing WhisperX connection: {e}")
            finally:
                self.is_connected = False
                self.ws = None

    def get_transcript(self) -> str:
        """Get current transcript buffer"""
        return self.transcript_buffer
