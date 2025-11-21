"""
Real E2E Integration Tests for VoxBridge

Tests using REAL running services:
- Real Discord bot "Auren" (already running)
- Real WhisperX STT (ws://localhost:4901)
- Real Chatterbox TTS (http://localhost:4123)
- Real n8n webhook (production)
- Real Discord channel (1429982041348378776)

No mocks - true end-to-end validation!
"""
from __future__ import annotations

import pytest
import asyncio
from httpx import AsyncClient

# Real Discord channel and guild
REAL_DISCORD_CHANNEL_ID = "1429982041348378776"
REAL_DISCORD_GUILD_ID = "680488880935403563"

# VoxBridge API URL - use container name when running in Docker
# Tests running in Docker can access voxbridge-api container directly
VOXBRIDGE_API_URL = "http://voxbridge-api:4900"


# ============================================================
# Test 1: Join and Leave Real Discord Channel
# ============================================================

@pytest.mark.e2e
@pytest.mark.real
@pytest.mark.asyncio
async def test_join_and_leave_real_discord_channel():
    """
    E2E Test: Bot joins and leaves actual Discord channel
    
    Uses real bot, real channel - validates Discord integration
    """
    async with AsyncClient(base_url=VOXBRIDGE_API_URL, timeout=30.0) as client:
        # Join real Discord channel
        print(f"\n🎤 Joining Discord channel {REAL_DISCORD_CHANNEL_ID}...")
        response = await client.post(
            "/voice/join",
            json={
                "channelId": REAL_DISCORD_CHANNEL_ID,
                "guildId": REAL_DISCORD_GUILD_ID
            }
        )
        
        assert response.status_code == 200, f"Failed to join: {response.text}"
        data = response.json()
        assert data["success"] is True
        print(f"✅ {data['message']}")
        
        # Wait a bit to ensure connection is established
        await asyncio.sleep(2)
        
        # Verify bot is in channel via health check
        response = await client.get("/health")
        assert response.status_code == 200
        health_data = response.json()
        assert health_data["inVoiceChannel"] is True
        print(f"✅ Bot confirmed in voice channel")
        
        # Leave channel
        print(f"\n👋 Leaving Discord channel...")
        response = await client.post("/voice/leave")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        print(f"✅ {data['message']}")
        
        # Verify bot left channel
        await asyncio.sleep(1)
        response = await client.get("/health")
        health_data = response.json()
        assert health_data["inVoiceChannel"] is False
        print(f"✅ Bot confirmed left voice channel")


# ============================================================
# Test 2: Complete Voice Interaction with Real Services
# ============================================================

@pytest.mark.e2e
@pytest.mark.real
@pytest.mark.slow
@pytest.mark.asyncio
async def test_complete_voice_interaction_real_services():
    """
    E2E Test: Complete voice interaction with all real services
    
    Flow:
    1. Join real Discord channel
    2. Wait for user to speak in Discord (manual trigger for now)
    3. Real WhisperX transcribes
    4. Real n8n processes
    5. Real Chatterbox generates TTS
    6. Real bot plays audio in Discord
    7. Leave channel
    
    NOTE: This test requires manual interaction - speak in Discord
    after bot joins to trigger the pipeline.
    """
    async with AsyncClient(base_url=VOXBRIDGE_API_URL, timeout=60.0) as client:
        # Join channel
        print(f"\n🎤 Joining Discord channel {REAL_DISCORD_CHANNEL_ID}...")
        response = await client.post(
            "/voice/join",
            json={
                "channelId": REAL_DISCORD_CHANNEL_ID,
                "guildId": REAL_DISCORD_GUILD_ID
            }
        )
        assert response.status_code == 200
        print(f"✅ Bot joined channel")
        
        # Instructions for manual testing
        print("\n" + "="*60)
        print("🎙️  MANUAL TEST STEP:")
        print("   Join Discord voice channel and speak")
        print("   The bot will:")
        print("   1. Transcribe your speech (WhisperX)")
        print("   2. Send to n8n for AI response")
        print("   3. Generate TTS (Chatterbox)")
        print("   4. Play audio response")
        print("="*60)
        
        # Wait for interaction (30 seconds)
        print("\n⏳ Waiting 30 seconds for voice interaction...")
        await asyncio.sleep(30)
        
        # Check status
        response = await client.get("/status")
        status_data = response.json()
        print(f"\n📊 Final status: {status_data}")
        
        # Leave channel
        print(f"\n👋 Leaving channel...")
        response = await client.post("/voice/leave")
        assert response.status_code == 200
        print(f"✅ Test complete")


# ============================================================
# Test 3: Health and Status Checks
# ============================================================

@pytest.mark.e2e
@pytest.mark.real
@pytest.mark.asyncio
async def test_real_service_health_checks():
    """
    E2E Test: Verify all services are healthy
    
    Checks:
    - VoxBridge API responds
    - Bot is ready
    - WhisperX configured
    - Chatterbox configured
    - n8n webhook configured
    """
    async with AsyncClient(base_url=VOXBRIDGE_API_URL, timeout=10.0) as client:
        # Health check
        print(f"\n🏥 Checking VoxBridge health...")
        response = await client.get("/health")
        assert response.status_code == 200
        health_data = response.json()
        
        assert health_data["status"] == "ok"
        assert health_data["botReady"] is True
        print(f"✅ VoxBridge healthy")
        print(f"   Bot ready: {health_data['botReady']}")
        print(f"   In voice: {health_data['inVoiceChannel']}")
        
        # Detailed status
        print(f"\n📊 Checking detailed status...")
        response = await client.get("/status")
        assert response.status_code == 200
        status_data = response.json()
        
        # Verify bot info
        assert status_data["bot"]["ready"] is True
        assert status_data["bot"]["username"] == "Auren"
        print(f"✅ Bot: {status_data['bot']['username']} (ID: {status_data['bot']['id']})")
        
        # Verify WhisperX
        assert status_data["whisperx"]["serverConfigured"] is True
        print(f"✅ WhisperX: model={status_data['whisperx']['model']}, device={status_data['whisperx']['device']}")
        
        # Verify services
        assert status_data["services"]["chatterbox"] is True
        assert status_data["services"]["n8nWebhook"] is True
        print(f"✅ Services: Chatterbox={status_data['services']['chatterbox']}, n8n={status_data['services']['n8nWebhook']}")
        
        print(f"\n✅ All services healthy and configured")
