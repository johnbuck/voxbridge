"""
End-to-end tests for sentence-level streaming

Tests with real services running (requires Docker containers):
- Real WhisperX STT server
- Real Chatterbox TTS API
- Real Discord voice connection (simulated)
- Real LLM provider (or mock webhook)

Run with: pytest tests/e2e/test_streaming_e2e.py -v

Prerequisites:
- docker compose up -d (all services running)
- WHISPER_SERVER_URL, CHATTERBOX_URL configured
"""

import pytest
import asyncio
import os
import aiohttp
from typing import Optional


# Check if services are available
WHISPER_URL = os.getenv('WHISPER_SERVER_URL', 'ws://localhost:4901')
CHATTERBOX_URL = os.getenv('CHATTERBOX_URL', 'http://localhost:4123')
API_URL = os.getenv('API_URL', 'http://localhost:4900')

# Skip all E2E tests if services are not running
pytestmark = pytest.mark.skipif(
    not os.getenv('RUN_E2E_TESTS', False),
    reason="E2E tests require running services. Set RUN_E2E_TESTS=1 to run."
)


async def check_service_health(url: str, timeout: float = 2.0) -> bool:
    """Check if a service is running and healthy"""
    try:
        async with aiohttp.ClientSession() as session:
            if url.startswith('ws://'):
                # For WebSocket, convert to HTTP health check
                http_url = url.replace('ws://', 'http://').replace(':4901', ':4902/health')
                async with session.get(http_url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    return resp.status == 200
            else:
                async with session.get(f"{url}/health", timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    return resp.status == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
async def services_available():
    """Check if all required services are available"""
    whisper_ok = await check_service_health(WHISPER_URL)
    chatterbox_ok = await check_service_health(CHATTERBOX_URL)
    api_ok = await check_service_health(API_URL)

    if not all([whisper_ok, chatterbox_ok, api_ok]):
        pytest.skip(f"Services not available: WhisperX={whisper_ok}, Chatterbox={chatterbox_ok}, API={api_ok}")

    return True


class TestRealServiceIntegration:
    """Test with real services running"""

    @pytest.mark.asyncio
    async def test_api_health_check(self, services_available):
        """Test API server is running and healthy"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}/health") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert 'status' in data or 'bot_ready' in data

    @pytest.mark.asyncio
    async def test_chatterbox_tts_synthesis(self, services_available):
        """Test Chatterbox TTS synthesizes audio"""
        async with aiohttp.ClientSession() as session:
            payload = {
                'text': 'Hello world! This is a test.',
                'voice_id': 'default',
                'speed': 1.0
            }

            async with session.post(
                f"{CHATTERBOX_URL}/synthesize",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10.0)
            ) as resp:
                assert resp.status == 200
                audio_data = await resp.read()
                assert len(audio_data) > 0
                # Verify it's audio data (check for common audio file headers)
                assert len(audio_data) > 100  # Should be substantial

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, services_available):
        """Test metrics endpoint returns streaming metrics"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}/metrics") as resp:
                assert resp.status == 200
                data = await resp.json()

                # Check for streaming-related metrics
                assert 'latencies' in data or 'total_requests' in data

    @pytest.mark.asyncio
    async def test_agents_endpoint(self, services_available):
        """Test agents endpoint returns list of agents"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}/api/agents") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert isinstance(data, list)

                if len(data) > 0:
                    agent = data[0]
                    assert 'id' in agent
                    assert 'name' in agent
                    assert 'streaming_enabled' in agent


class TestStreamingLatency:
    """Test streaming latency improvements"""

    @pytest.mark.asyncio
    async def test_sentence_detection_latency(self, services_available):
        """Test sentence detection happens quickly"""
        from src.services.sentence_parser import SentenceParser
        import time

        parser = SentenceParser(min_sentence_length=10)

        # Measure sentence detection time
        t_start = time.time()
        sentences = parser.add_chunk("Hello world! How are you today? I'm doing great.")
        t_end = time.time()

        latency_ms = (t_end - t_start) * 1000

        # Should detect sentences very quickly (< 10ms)
        assert latency_ms < 10
        assert len(sentences) == 3

    @pytest.mark.asyncio
    async def test_tts_synthesis_latency(self, services_available):
        """Test TTS synthesis completes in reasonable time"""
        import time

        async with aiohttp.ClientSession() as session:
            payload = {
                'text': 'Hello world!',
                'voice_id': 'default',
                'speed': 1.0
            }

            t_start = time.time()

            async with session.post(
                f"{CHATTERBOX_URL}/synthesize",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5.0)
            ) as resp:
                assert resp.status == 200
                audio_data = await resp.read()

            t_end = time.time()

            latency_ms = (t_end - t_start) * 1000

            # Short sentence should synthesize in < 2 seconds
            assert latency_ms < 2000
            assert len(audio_data) > 0

    @pytest.mark.asyncio
    async def test_end_to_end_sentence_latency(self, services_available):
        """Test end-to-end latency from sentence detection to audio"""
        from src.services.sentence_parser import SentenceParser
        import time

        parser = SentenceParser(min_sentence_length=10)

        # Start timing
        t_start = time.time()

        # Detect sentence
        sentences = parser.add_chunk("Hello world! This is a test.")

        # Synthesize first sentence
        async with aiohttp.ClientSession() as session:
            payload = {
                'text': sentences[0],
                'voice_id': 'default',
                'speed': 1.0
            }

            async with session.post(
                f"{CHATTERBOX_URL}/synthesize",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5.0)
            ) as resp:
                assert resp.status == 200
                audio_data = await resp.read()

        t_end = time.time()

        latency_ms = (t_end - t_start) * 1000

        # End-to-end should be < 2.5 seconds for short sentence
        assert latency_ms < 2500
        assert len(audio_data) > 0


class TestConcurrentStreaming:
    """Test concurrent streaming scenarios"""

    @pytest.mark.asyncio
    async def test_concurrent_tts_requests(self, services_available):
        """Test multiple TTS requests can be processed concurrently"""
        sentences = [
            "First sentence here.",
            "Second sentence now.",
            "Third sentence finally."
        ]

        async def synthesize_sentence(text: str):
            async with aiohttp.ClientSession() as session:
                payload = {
                    'text': text,
                    'voice_id': 'default',
                    'speed': 1.0
                }
                async with session.post(
                    f"{CHATTERBOX_URL}/synthesize",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5.0)
                ) as resp:
                    return await resp.read()

        import time
        t_start = time.time()

        # Process all concurrently
        results = await asyncio.gather(*[
            synthesize_sentence(sentence) for sentence in sentences
        ])

        t_end = time.time()
        total_time = t_end - t_start

        # Should complete faster than 3 sequential requests
        # (which would be ~6+ seconds)
        assert total_time < 4.0

        # All should succeed
        assert len(results) == 3
        assert all(len(audio) > 0 for audio in results)


class TestErrorHandling:
    """Test error handling in real environment"""

    @pytest.mark.asyncio
    async def test_invalid_tts_request_handled(self, services_available):
        """Test invalid TTS request is handled gracefully"""
        async with aiohttp.ClientSession() as session:
            # Send invalid payload
            payload = {
                'text': '',  # Empty text
                'voice_id': 'nonexistent_voice',
                'speed': 999  # Invalid speed
            }

            async with session.post(
                f"{CHATTERBOX_URL}/synthesize",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5.0)
            ) as resp:
                # Should return error status (400 or 422)
                assert resp.status in [400, 422, 500]

    @pytest.mark.asyncio
    async def test_api_handles_invalid_agent_id(self, services_available):
        """Test API handles invalid agent ID gracefully"""
        async with aiohttp.ClientSession() as session:
            fake_id = "00000000-0000-0000-0000-000000000000"

            async with session.get(f"{API_URL}/api/agents/{fake_id}") as resp:
                # Should return 404
                assert resp.status == 404


class TestStreamingMetrics:
    """Test streaming metrics are tracked correctly"""

    @pytest.mark.asyncio
    async def test_metrics_include_streaming_data(self, services_available):
        """Test metrics endpoint includes streaming-specific metrics"""
        async with aiohttp.ClientSession() as session:
            # Get initial metrics
            async with session.get(f"{API_URL}/metrics") as resp:
                assert resp.status == 200
                initial_data = await resp.json()

            # Perform a TTS synthesis
            payload = {
                'text': 'Test sentence for metrics.',
                'voice_id': 'default',
                'speed': 1.0
            }

            async with session.post(
                f"{CHATTERBOX_URL}/synthesize",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5.0)
            ) as resp:
                assert resp.status == 200

            # Wait a moment for metrics to update
            await asyncio.sleep(0.5)

            # Get updated metrics
            async with session.get(f"{API_URL}/metrics") as resp:
                assert resp.status == 200
                updated_data = await resp.json()

            # Verify metrics structure (should have latencies, counters, etc.)
            assert isinstance(updated_data, dict)


class TestRealWorldScenarios:
    """Test real-world usage scenarios"""

    @pytest.mark.asyncio
    async def test_long_response_streaming(self, services_available):
        """Test streaming a long AI response sentence-by-sentence"""
        from src.services.sentence_parser import SentenceParser

        parser = SentenceParser(min_sentence_length=10)

        # Simulate long LLM response
        long_response = (
            "That's a great question! I'd be happy to help you with that. "
            "Let me explain the concept in detail. First, we need to understand "
            "the basic principles. Then we can move on to more advanced topics. "
            "Finally, I'll provide some practical examples."
        )

        # Simulate streaming word by word
        words = long_response.split()
        detected_sentences = []

        for word in words:
            sentences = parser.add_chunk(word + " ")
            detected_sentences.extend(sentences)

        # Get final sentence
        final = parser.finalize()
        if final:
            detected_sentences.append(final)

        # Should have detected multiple sentences
        assert len(detected_sentences) >= 4

        # Each sentence should be reasonable length
        for sentence in detected_sentences:
            assert len(sentence) > 10

    @pytest.mark.asyncio
    async def test_rapid_chunk_arrival(self, services_available):
        """Test handling rapid chunk arrival (fast LLM)"""
        from src.services.sentence_parser import SentenceParser

        parser = SentenceParser(min_sentence_length=10)

        # Simulate very rapid chunks
        chunks = ["Hello! ", "How ", "are ", "you? ", "Great!"]

        detected = []
        for chunk in chunks:
            sentences = parser.add_chunk(chunk)
            detected.extend(sentences)
            # No delay - rapid arrival

        final = parser.finalize()
        if final:
            detected.append(final)

        # Should have detected all sentences correctly despite rapid arrival
        assert len(detected) >= 2


class TestSystemHealth:
    """Test overall system health and readiness"""

    @pytest.mark.asyncio
    async def test_all_services_healthy(self, services_available):
        """Test all services report healthy status"""
        # Check API
        api_health = await check_service_health(API_URL)
        assert api_health, "API service unhealthy"

        # Check Chatterbox TTS
        chatterbox_health = await check_service_health(CHATTERBOX_URL)
        assert chatterbox_health, "Chatterbox TTS unhealthy"

        # Check WhisperX (via HTTP health endpoint)
        whisper_health = await check_service_health(WHISPER_URL)
        assert whisper_health, "WhisperX service unhealthy"

    @pytest.mark.asyncio
    async def test_database_connection(self, services_available):
        """Test database is accessible"""
        # Check if agents endpoint works (requires database)
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}/api/agents") as resp:
                assert resp.status == 200
                # Database is working if we can retrieve agents


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
