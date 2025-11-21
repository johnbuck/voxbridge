# WebRTC Backend Integration Guide

**VoxBridge 2.0 Phase 4: Web Voice Interface - Backend Implementation**

This document describes the backend WebSocket handler for browser audio streaming.

## 📋 Overview

The backend now supports browser-based voice input via WebSocket at `/ws/voice`. The implementation:

- ✅ Receives Opus audio chunks from browser MediaRecorder API
- ✅ Decodes Opus → PCM (16kHz mono) using opuslib
- ✅ Streams audio to WhisperX for transcription
- ✅ Detects silence using server-side VAD (600ms threshold)
- ✅ Routes final transcript to LLM (OpenRouter, Local, or n8n)
- ✅ Streams AI response chunks back to browser
- ✅ Saves conversation to PostgreSQL sessions/conversations tables

## 🏗️ Architecture

```
Browser MediaRecorder (Opus)
    ↓ (WebSocket binary frames)
/ws/voice endpoint
    ↓
WebRTCVoiceHandler
    ↓ (decode Opus → PCM)
WhisperClient
    ↓ (transcription)
LLM Provider (via LLMProviderFactory)
    ↓ (streaming response)
Browser (WebSocket JSON events)
```

## 📁 Files Implemented

### 1. `src/voice/webrtc_handler.py` (NEW)

**WebRTCVoiceHandler** class:
- Manages WebSocket connection lifecycle
- Decodes Opus audio to PCM using opuslib
- Streams audio to WhisperX
- Monitors for silence (600ms threshold)
- Routes to LLM provider
- Streams AI response back to browser

**Key methods**:
- `start()` - Main entry point, validates session and starts audio loop
- `_audio_loop()` - Receives binary audio chunks and decodes
- `_monitor_silence()` - Detects silence and triggers finalization
- `_finalize_transcription()` - Finalizes transcript and routes to LLM
- `_handle_llm_response()` - Streams LLM response back to browser

### 2. `src/discord_bot.py` (UPDATED)

**New WebSocket endpoint**: `/ws/voice`

```python
@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for browser voice streaming

    Query params: ?session_id={uuid}&user_id={string}

    Protocol:
    - Client → Server: Binary Opus audio chunks (100ms intervals)
    - Server → Client: JSON events (transcripts, AI responses, errors)
    """
```

**Query Parameters**:
- `session_id` (UUID, required) - Active session ID from sessions table
- `user_id` (string, required) - User identifier (browser session ID)

**Events emitted** (JSON):
```json
// Partial transcript (every ~500ms during speech)
{
  "event": "partial_transcript",
  "data": {
    "text": "hello world",
    "session_id": "uuid-here"
  }
}

// Final transcript (when silence detected)
{
  "event": "final_transcript",
  "data": {
    "text": "hello world",
    "session_id": "uuid-here"
  }
}

// AI response chunk (streaming)
{
  "event": "ai_response_chunk",
  "data": {
    "text": "Hi! ",
    "session_id": "uuid-here"
  }
}

// AI response complete
{
  "event": "ai_response_complete",
  "data": {
    "text": "Hi! How can I help you today?",
    "session_id": "uuid-here"
  }
}

// Error
{
  "event": "error",
  "data": {
    "message": "Error message here",
    "session_id": "uuid-here"
  }
}
```

### 3. `src/voice/__init__.py` (NEW)

Module initialization for voice handlers.

## 🔧 Configuration

All configuration is via environment variables (already in `.env.example`):

```bash
# WhisperX (reused from Discord setup)
WHISPER_SERVER_URL=ws://whisperx:4901
WHISPER_LANGUAGE=en

# Voice Activity Detection
SILENCE_THRESHOLD_MS=600  # Silence duration to trigger finalization
MAX_SPEAKING_TIME_MS=45000  # Max speaking time (safety timeout)

# LLM Providers (at least one required)
OPENROUTER_API_KEY=your_key_here  # For OpenRouter provider
LOCAL_LLM_BASE_URL=http://localhost:11434/v1  # For local Ollama
N8N_WEBHOOK_URL=http://n8n:5678/webhook/voice  # For n8n routing

# Database (already configured in Phase 1)
POSTGRES_USER=voxbridge
POSTGRES_PASSWORD=voxbridge_dev_password
POSTGRES_DB=voxbridge
DATABASE_URL=postgresql+asyncpg://voxbridge:voxbridge_dev_password@postgres:5432/voxbridge
```

## 🧪 Testing

### Prerequisites

1. **Services running**:
   ```bash
   docker compose up -d postgres voxbridge-whisperx voxbridge-api
   ```

2. **Database migrated**:
   ```bash
   docker exec voxbridge-api alembic upgrade head
   ```

3. **Seed agents** (if not already done):
   ```bash
   docker exec voxbridge-api python -m src.database.seed
   ```

### Test with Frontend

The frontend is **100% complete** and ready to test. See `frontend/WEBRTC_README.md` for details.

1. **Create a session**:
   ```bash
   curl -X POST http://localhost:4900/api/sessions \
     -H "Content-Type: application/json" \
     -d '{
       "user_id": "test-user-123",
       "agent_id": "uuid-from-database",
       "user_name": "Test User",
       "title": "Test Conversation",
       "session_type": "web"
     }'
   ```

2. **Connect to WebSocket**:
   ```javascript
   const ws = new WebSocket('ws://localhost:4900/ws/voice?session_id=SESSION_UUID&user_id=test-user-123');

   ws.onopen = () => {
     console.log('✅ Connected to /ws/voice');
   };

   ws.onmessage = (event) => {
     const message = JSON.parse(event.data);
     console.log('📨 Event:', message.event, message.data);
   };
   ```

3. **Send audio chunks**:
   ```javascript
   // Browser MediaRecorder setup (Opus codec)
   const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
   const mediaRecorder = new MediaRecorder(stream, {
     mimeType: 'audio/webm;codecs=opus',
     audioBitsPerSecond: 16000
   });

   mediaRecorder.ondataavailable = (event) => {
     if (event.data.size > 0 && ws.readyState === WebSocket.OPEN) {
       ws.send(event.data);  // Send binary audio chunk
     }
   };

   mediaRecorder.start(100);  // 100ms chunks
   ```

### Test with Mock Audio

For backend-only testing without browser:

```python
# tests/integration/test_webrtc_handler.py
import asyncio
import websockets
import opuslib

async def test_voice_websocket():
    # Connect to WebSocket
    uri = "ws://localhost:4900/ws/voice?session_id=UUID_HERE&user_id=test-user"
    async with websockets.connect(uri) as ws:
        print("✅ Connected")

        # Create mock Opus encoder
        encoder = opuslib.Encoder(16000, 1, opuslib.APPLICATION_VOIP)

        # Generate silent PCM audio (16kHz mono, 20ms frames = 320 samples)
        import array
        pcm = array.array('h', [0] * 320)  # Silent frame

        # Encode to Opus and send 10 frames
        for i in range(10):
            opus_data = encoder.encode(pcm.tobytes(), 320)
            await ws.send(opus_data)
            await asyncio.sleep(0.02)  # 20ms per frame

        # Wait for responses
        while True:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                print(f"📨 {message}")
            except asyncio.TimeoutError:
                break

# Run test
asyncio.run(test_voice_websocket())
```

## 🔍 Monitoring

### Logs

```bash
# Follow WebSocket voice logs
docker logs voxbridge-api --tail 200 --follow | grep -E "(🎙️|🔌|WebRTC|/ws/voice)"

# Follow transcription logs
docker logs voxbridge-api --tail 200 --follow | grep -E "(WhisperX|partial|final|transcript)"

# Follow LLM logs
docker logs voxbridge-api --tail 200 --follow | grep -E "(🤖|LLM|ai_response)"
```

### Metrics

The handler logs latency metrics at each stage:

```
⏱️ LATENCY [connection → first transcript]: 0.234s
⏱️ LATENCY [LLM first chunk]: 0.512s
⏱️ LATENCY [total LLM generation]: 2.341s
```

## 🐛 Troubleshooting

### "Session not found"

**Symptom**: Error event: `{"event": "error", "data": {"message": "Session not found"}}`

**Solution**: Create a session first via `/api/sessions` endpoint (see Testing section).

### "WhisperX connection failed"

**Symptom**: `❌ Failed to connect to WhisperX`

**Solution**:
1. Check WhisperX is running: `docker logs voxbridge-whisperx`
2. Verify `WHISPER_SERVER_URL=ws://whisperx:4901` in `.env`
3. Check network connectivity between containers

### "Opus decode error"

**Symptom**: `⚠️ Opus decode error: ...`

**Possible causes**:
1. Browser not using Opus codec (check MediaRecorder mimeType)
2. Partial/corrupted frame (non-fatal, handler continues)
3. Sample rate mismatch (ensure 16kHz audio from browser)

**Solution**: Verify browser MediaRecorder configuration:
```javascript
const mediaRecorder = new MediaRecorder(stream, {
  mimeType: 'audio/webm;codecs=opus',
  audioBitsPerSecond: 16000
});
```

### "LLM provider error"

**Symptom**: `❌ LLM Error: ...`

**Solution**:
1. Check agent's `llm_provider` is configured correctly
2. Verify API keys in environment variables
3. Check LLM service is accessible (OpenRouter, Ollama, n8n)

### No partial transcripts

**Symptom**: Only final transcripts, no partial updates

**Possible causes**:
1. WhisperX not configured for streaming mode
2. Audio chunks too small/infrequent

**Solution**: Check WhisperX server configuration in `src/whisper_server.py`

## 🎯 Integration Points

### Session Management

- Uses `SessionService.get_session()` to validate session ownership
- Uses `SessionService.add_message()` to save user/assistant messages
- Associates all messages with session_id for conversation history

### LLM Routing

- Uses `AgentService.get_agent()` to load agent configuration
- Uses `LLMProviderFactory.create_provider()` to instantiate provider
- Supports OpenRouter, Local LLM, and n8n webhook routing
- Streams response chunks back to browser in real-time

### WhisperX Integration

- Reuses existing `WhisperClient` class (same as Discord voice)
- Supports partial transcript callbacks
- Handles finalization with silence detection
- Connection retry logic included

## 📊 Database Schema

Messages are saved to the `conversations` table:

```sql
-- User message
INSERT INTO conversations (session_id, role, content, created_at)
VALUES (session_id, 'user', transcript, NOW());

-- AI message
INSERT INTO conversations (session_id, role, content, created_at)
VALUES (session_id, 'assistant', llm_response, NOW());
```

## 🚀 Deployment Notes

### Production Considerations

1. **Session Validation**: Handler validates session exists and user owns it
2. **Concurrent Sessions**: Each WebSocket connection is independent
3. **Resource Cleanup**: Handler cleans up WhisperX client and WebSocket on disconnect
4. **Error Handling**: All errors sent to browser via error events
5. **Latency Tracking**: Comprehensive logging for performance monitoring

### Security

- Session ownership verified before processing audio
- No PII in WebSocket messages (only session UUIDs)
- Binary audio data not logged (privacy)
- Database queries use SQLAlchemy ORM (SQL injection protection)

## 🔗 Related Documentation

- **Frontend**: `frontend/WEBRTC_README.md` - Complete frontend implementation
- **Architecture**: `docs/architecture/voxbridge-2.0-transformation-plan.md` - Phase 4 overview
- **Database**: `src/database/models.py` - Session/Conversation models
- **LLM Providers**: `src/llm/` - Provider abstraction layer
- **WhisperX**: `src/whisper_client.py` - Transcription client

## ✅ Implementation Checklist

- [x] Create `src/voice/webrtc_handler.py` with WebSocket handler
- [x] Add `/ws/voice` endpoint to `src/discord_bot.py`
- [x] Verify `opuslib` in `requirements-bot.txt`
- [x] Update startup logs to show new endpoint
- [x] Session validation (check ownership)
- [x] Opus audio decoding (16kHz mono PCM)
- [x] WhisperX streaming integration
- [x] Server-side VAD (silence detection)
- [x] LLM routing (OpenRouter/Local/n8n)
- [x] AI response streaming
- [x] Database persistence (conversations table)
- [x] Error handling and logging
- [x] Cleanup on disconnect

## 🎉 Status

**Backend implementation: COMPLETE**

The backend is ready to receive audio from the frontend and handle the complete voice interaction pipeline.

**Next Steps**:
1. Test with frontend mock audio
2. Verify end-to-end latency
3. Load test with concurrent sessions
4. Monitor database performance
