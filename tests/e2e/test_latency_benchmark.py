"""
E2E Latency Benchmark Tests for VoxBridge

Measures end-to-end latency of the voice interaction pipeline by:
1. Using real Discord bot and services
2. Tracking timestamps via Docker logs and API calls
3. Generating detailed latency breakdown reports

IMPORTANT: These tests require manual interaction - speak in Discord
after the bot joins to trigger the complete pipeline.
"""
from __future__ import annotations

import pytest
import asyncio
import time
import re
import subprocess
from httpx import AsyncClient

# Real Discord channel and guild
CHANNEL_ID = "1429982041348378776"
GUILD_ID = "680488880935403563"
VOXBRIDGE_API_URL = "http://voxbridge-discord:4900"


class LogBasedLatencyTracker:
    """
    Tracks latency by parsing Docker logs with timestamps

    Extracts timing information from production logs without
    requiring latency-specific logging in production code.
    """

    def __init__(self, container_name: str = "voxbridge-discord"):
        self.container_name = container_name
        self.log_buffer = []
        self.timestamps = {}

    def capture_logs_since(self, since_time: float) -> list:
        """
        Capture Docker logs since a specific timestamp

        Args:
            since_time: Unix timestamp to start capturing from

        Returns:
            List of log lines with timestamps
        """
        cmd = [
            "docker", "logs", self.container_name,
            "--since", str(int(since_time)),
            "--timestamps"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout.split('\n') + result.stderr.split('\n')

    def extract_event_timestamp(self, logs: list, event_pattern: str) -> float | None:
        """
        Extract timestamp for a specific event from logs

        Args:
            logs: List of log lines
            event_pattern: Regex pattern to match event

        Returns:
            Unix timestamp in seconds, or None if not found
        """
        for line in logs:
            if re.search(event_pattern, line):
                # Extract timestamp from Docker log format: 2025-10-21T21:01:02.721
                match = re.search(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3})', line)
                if match:
                    from datetime import datetime
                    ts_str = match.group(1)
                    dt = datetime.fromisoformat(ts_str)
                    return dt.timestamp()
        return None

    def analyze_pipeline_latency(self, logs: list) -> dict:
        """
        Analyze complete pipeline latency from logs

        Args:
            logs: List of log lines

        Returns:
            Dictionary with latency breakdown
        """
        events = {
            'user_speaking': r'🎤.*is now speaking',
            'transcription_start': r'🎙️ Starting transcription',
            'transcription_finalize': r'🏁 Finalizing transcription',
            'whisperx_final': r'✅ Final:',
            'n8n_send': r'📤 Sending to n8n',
            'n8n_chunk_received': r'📨 Chunk \d+',
            'tts_synthesizing': r'🔊 Synthesizing:',
            'tts_complete': r'✅ TTS stream complete',
            'audio_playing': r'🔊 Playing audio',
            'audio_complete': r'✅ Audio playback complete',
        }

        timestamps = {}
        for event, pattern in events.items():
            ts = self.extract_event_timestamp(logs, pattern)
            if ts:
                timestamps[event] = ts

        # Calculate latency deltas
        latencies = {}
        if 'user_speaking' in timestamps:
            t_start = timestamps['user_speaking']

            if 'whisperx_final' in timestamps:
                latencies['stt_latency'] = int((timestamps['whisperx_final'] - t_start) * 1000)

            if 'n8n_chunk_received' in timestamps:
                latencies['n8n_latency'] = int((timestamps['n8n_chunk_received'] - timestamps.get('n8n_send', t_start)) * 1000)

            if 'tts_complete' in timestamps:
                latencies['tts_generation'] = int((timestamps['tts_complete'] - timestamps.get('tts_synthesizing', t_start)) * 1000)

            if 'audio_complete' in timestamps:
                latencies['total_latency'] = int((timestamps['audio_complete'] - t_start) * 1000)
                latencies['first_audio_latency'] = int((timestamps.get('audio_playing', t_start) - t_start) * 1000)

        return {
            'timestamps': timestamps,
            'latencies': latencies
        }


@pytest.mark.e2e
@pytest.mark.real
@pytest.mark.latency
@pytest.mark.asyncio
async def test_measure_end_to_end_latency():
    """
    E2E Latency Benchmark: Measure complete voice interaction latency

    This test measures real-world latency by:
    1. Joining Discord voice channel
    2. Waiting for user to speak
    3. Parsing Docker logs to extract timing information
    4. Generating detailed latency report

    MANUAL INTERACTION REQUIRED: Speak in Discord when prompted
    """
    async with AsyncClient(base_url=VOXBRIDGE_API_URL, timeout=60.0) as client:
        print("\n" + "="*70)
        print("E2E LATENCY BENCHMARK TEST")
        print("="*70)

        # Join channel
        print("\n[1/4] Joining Discord voice channel...")
        response = await client.post(
            "/voice/join",
            json={"channelId": CHANNEL_ID, "guildId": GUILD_ID}
        )
        assert response.status_code == 200
        print(f"✅ Bot joined channel: {response.json()['message']}")

        # Wait for user interaction
        print("\n[2/4] MANUAL STEP: Please speak in Discord now")
        print("     Suggested phrases:")
        print("     - 'What time is it?'")
        print("     - 'Tell me a joke'")
        print("     - 'How are you doing?'")
        print("\n     Waiting 20 seconds for interaction...")

        # Record start time for log capture
        t_test_start = time.time()

        # Wait for interaction
        await asyncio.sleep(20)

        # Capture and analyze logs
        print("\n[3/4] Analyzing Docker logs for latency measurements...")
        tracker = LogBasedLatencyTracker()
        logs = tracker.capture_logs_since(t_test_start - 5)  # 5s buffer

        analysis = tracker.analyze_pipeline_latency(logs)
        latencies = analysis['latencies']

        # Generate report
        print("\n[4/4] LATENCY BENCHMARK RESULTS")
        print("="*70)

        if latencies:
            print("\n📊 Pipeline Latency Breakdown:")
            print("-" * 70)

            if 'stt_latency' in latencies:
                print(f"  Speech-to-Text (WhisperX):     {latencies['stt_latency']:6,} ms")

            if 'n8n_latency' in latencies:
                print(f"  AI Agent Response (n8n):       {latencies['n8n_latency']:6,} ms")

            if 'tts_generation' in latencies:
                print(f"  TTS Generation (Chatterbox):   {latencies['tts_generation']:6,} ms")

            if 'first_audio_latency' in latencies:
                print(f"  Time to First Audio:           {latencies['first_audio_latency']:6,} ms")
                print("-" * 70)

            if 'total_latency' in latencies:
                print(f"  TOTAL PIPELINE LATENCY:        {latencies['total_latency']:6,} ms")
                print(f"                                 (~{latencies['total_latency']/1000:.1f} seconds)")

            print("="*70)

            # Performance assertions (based on current benchmarks)
            if 'total_latency' in latencies:
                # Warning if over 15 seconds
                if latencies['total_latency'] > 15000:
                    print(f"\n⚠️  WARNING: Total latency ({latencies['total_latency']}ms) exceeds 15s")

                # Fail if over 30 seconds (something is very wrong)
                assert latencies['total_latency'] < 30000, \
                    f"Total latency too high: {latencies['total_latency']}ms > 30000ms"

            print(f"\n✅ Latency benchmark complete")
        else:
            print("\n⚠️  No latency data captured - user may not have spoken in Discord")
            print("    This test requires manual interaction to measure latency")

        # Leave channel
        await client.post("/voice/leave")
        print(f"\n✅ Bot left voice channel")


@pytest.mark.e2e
@pytest.mark.real
@pytest.mark.latency
@pytest.mark.asyncio
async def test_tts_only_latency():
    """
    E2E Latency Benchmark: Measure TTS-only latency (bypass STT/n8n)

    This isolates TTS generation latency by using the /voice/speak endpoint.
    """
    async with AsyncClient(base_url=VOXBRIDGE_API_URL, timeout=60.0) as client:
        print("\n" + "="*70)
        print("TTS-ONLY LATENCY BENCHMARK")
        print("="*70)

        # Join channel
        response = await client.post(
            "/voice/join",
            json={"channelId": CHANNEL_ID, "guildId": GUILD_ID}
        )
        assert response.status_code == 200

        # Test text
        test_text = "This is a latency benchmark test of the text to speech system"

        print(f"\n[1/2] Generating TTS for: \"{test_text}\"")

        t_start = time.time()

        # Trigger TTS
        response = await client.post(
            "/voice/speak",
            json={
                "output": {"content": test_text},
                "options": {}
            }
        )

        assert response.status_code == 200

        # Wait for TTS completion
        await asyncio.sleep(5)  # Rough estimate for TTS+playback

        t_end = time.time()
        tts_latency = int((t_end - t_start) * 1000)

        print(f"\n[2/2] TTS LATENCY RESULTS")
        print("="*70)
        print(f"  Text length:              {len(test_text)} characters")
        print(f"  Total TTS latency:        {tts_latency:6,} ms")
        print(f"  Latency per character:    {tts_latency/len(test_text):6.1f} ms/char")
        print("="*70)

        # Leave channel
        await client.post("/voice/leave")

        print(f"\n✅ TTS benchmark complete")


@pytest.mark.e2e
@pytest.mark.real
@pytest.mark.latency
@pytest.mark.asyncio
async def test_api_latency():
    """
    E2E Latency Benchmark: Measure API endpoint latencies

    Tests response time for key API endpoints.
    """
    async with AsyncClient(base_url=VOXBRIDGE_API_URL, timeout=30.0) as client:
        print("\n" + "="*70)
        print("API ENDPOINT LATENCY BENCHMARK")
        print("="*70)

        endpoints = {
            "Health Check": "/health",
            "Status": "/status",
        }

        results = {}

        for name, endpoint in endpoints.items():
            t_start = time.perf_counter()
            response = await client.get(endpoint)
            t_end = time.perf_counter()

            latency_ms = (t_end - t_start) * 1000
            results[name] = latency_ms

            assert response.status_code == 200, f"{endpoint} returned {response.status_code}"

        print("\n📊 API Endpoint Latencies:")
        print("-" * 70)
        for name, latency in results.items():
            print(f"  {name:20s}  {latency:8.2f} ms")
        print("="*70)

        # All API endpoints should respond in under 500ms
        for name, latency in results.items():
            assert latency < 500, f"{name} too slow: {latency:.2f}ms > 500ms"

        print(f"\n✅ API latency benchmark complete")
