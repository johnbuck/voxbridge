# WebRTC Backend Testing Guide

**Quick reference for testing the `/ws/voice` endpoint**

## 🚀 Quick Start

### 1. Start Services

```bash
cd /home/wiley/Docker/voxbridge
docker compose up -d postgres voxbridge-whisperx voxbridge-api
```

### 2. Verify Services

```bash
# Check all services are healthy
docker compose ps

# Check backend logs
docker logs voxbridge-api --tail 50

# Verify endpoint is listed
# Should see: "WS   /ws/voice - Browser voice streaming (Phase 4)"
```

### 3. Seed Database (if not already done)

```bash
# Run migrations
docker exec voxbridge-api alembic upgrade head

# Seed example agents
docker exec voxbridge-api python -m src.database.seed

# Verify agents exist
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "SELECT id, name, llm_provider FROM agents;"
```

## 🧪 Test 1: Create Session

First, create a test session to use with the WebSocket:

```bash
# Get an agent ID from the database
AGENT_ID=$(docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -t -c "SELECT id FROM agents LIMIT 1;" | tr -d ' ')

# Create a session
curl -X POST http://localhost:4900/api/sessions \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"test-user-123\",
    \"agent_id\": \"$AGENT_ID\",
    \"user_name\": \"Test User\",
    \"title\": \"WebRTC Test\",
    \"session_type\": \"web\"
  }" | python3 -m json.tool

# Save the returned session_id for next step
```

**Expected Response**:
```json
{
  "id": "uuid-here",
  "user_id": "test-user-123",
  "agent_id": "uuid-here",
  "title": "WebRTC Test",
  "active": true,
  "started_at": "2025-10-26T...",
  ...
}
```

## 🧪 Test 2: WebSocket Connection (Browser Console)

Open browser console and run:

```javascript
// Replace with your session_id from Test 1
const sessionId = "SESSION_UUID_HERE";
const userId = "test-user-123";

// Connect to WebSocket
const ws = new WebSocket(`ws://localhost:4900/ws/voice?session_id=${sessionId}&user_id=${userId}`);

ws.onopen = () => {
  console.log('✅ Connected to /ws/voice');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log(`📨 Event: ${message.event}`, message.data);
};

ws.onerror = (error) => {
  console.error('❌ WebSocket error:', error);
};

ws.onclose = (event) => {
  console.log('🔌 WebSocket closed:', event.code, event.reason);
};
```

**Expected**:
- Connection opens successfully
- No immediate errors

## 🧪 Test 3: Send Audio (Browser Console)

After connecting (Test 2), send audio from microphone:

```javascript
// Request microphone access
const stream = await navigator.mediaDevices.getUserMedia({
  audio: {
    sampleRate: 16000,  // 16kHz for WhisperX
    channelCount: 1,    // Mono
    echoCancellation: true,
    noiseSuppression: true
  }
});

// Create MediaRecorder with Opus codec
const mediaRecorder = new MediaRecorder(stream, {
  mimeType: 'audio/webm;codecs=opus',
  audioBitsPerSecond: 16000
});

// Send audio chunks to WebSocket
mediaRecorder.ondataavailable = (event) => {
  if (event.data.size > 0 && ws.readyState === WebSocket.OPEN) {
    console.log(`🎙️ Sending audio chunk: ${event.data.size} bytes`);
    ws.send(event.data);
  }
};

// Start recording with 100ms chunks
mediaRecorder.start(100);

console.log('🎤 Recording started - speak now!');

// To stop:
// mediaRecorder.stop();
// stream.getTracks().forEach(track => track.stop());
```

**Expected Events** (in console):
```
📨 Event: partial_transcript { text: "hello", session_id: "..." }
📨 Event: partial_transcript { text: "hello world", session_id: "..." }
📨 Event: final_transcript { text: "hello world", session_id: "..." }
📨 Event: ai_response_chunk { text: "Hi! ", session_id: "..." }
📨 Event: ai_response_chunk { text: "How can I ", session_id: "..." }
📨 Event: ai_response_chunk { text: "help you?", session_id: "..." }
📨 Event: ai_response_complete { text: "Hi! How can I help you?", session_id: "..." }
```

## 🧪 Test 4: Mock Audio (Python)

For backend-only testing without browser:

```python
#!/usr/bin/env python3
"""
Test /ws/voice endpoint with mock audio
"""
import asyncio
import websockets
import opuslib
import array

async def test_voice_websocket():
    # Configuration
    session_id = "SESSION_UUID_HERE"  # From Test 1
    user_id = "test-user-123"
    uri = f"ws://localhost:4900/ws/voice?session_id={session_id}&user_id={user_id}"

    print(f"🔌 Connecting to {uri}")

    try:
        async with websockets.connect(uri) as ws:
            print("✅ Connected to /ws/voice")

            # Create Opus encoder (16kHz mono)
            encoder = opuslib.Encoder(16000, 1, opuslib.APPLICATION_VOIP)

            # Generate silent PCM audio
            # 20ms frame at 16kHz = 320 samples
            silent_pcm = array.array('h', [0] * 320).tobytes()

            # Send 50 frames (1 second of audio)
            print("🎙️ Sending 50 audio frames (1 second)")
            for i in range(50):
                opus_data = encoder.encode(silent_pcm, 320)
                await ws.send(opus_data)
                await asyncio.sleep(0.02)  # 20ms per frame

            print("⏸️ Waiting for silence detection (600ms)...")
            await asyncio.sleep(1.0)

            # Receive responses
            print("📨 Waiting for server responses...")
            while True:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    print(f"📨 {message}")
                except asyncio.TimeoutError:
                    print("⏱️ No more messages (timeout)")
                    break

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_voice_websocket())
```

**Save as**: `test_webrtc.py`

**Run**:
```bash
# Install dependencies
pip install websockets opuslib

# Run test
python test_webrtc.py
```

**Expected Output**:
```
🔌 Connecting to ws://localhost:4900/ws/voice?...
✅ Connected to /ws/voice
🎙️ Sending 50 audio frames (1 second)
⏸️ Waiting for silence detection (600ms)...
📨 Waiting for server responses...
📨 {"event":"final_transcript","data":{"text":"","session_id":"..."}}
📨 {"event":"ai_response_chunk","data":{"text":"...","session_id":"..."}}
📨 {"event":"ai_response_complete","data":{"text":"...","session_id":"..."}}
⏱️ No more messages (timeout)
```

## 🧪 Test 5: TTS Audio Playback ⭐ **NEW**

After AI response completes, the backend should automatically synthesize and stream TTS audio.

### Browser Console Test

```javascript
// After Test 3 (sending audio), listen for TTS events
ws.onmessage = (event) => {
  // Check if binary (audio) or text (JSON)
  if (event.data instanceof ArrayBuffer || event.data instanceof Blob) {
    console.log(`🎵 Received TTS audio chunk: ${event.data.byteLength || event.data.size} bytes`);

    // Convert to audio and play
    const audioData = event.data instanceof Blob ? event.data : new Blob([event.data], { type: 'audio/wav' });
    const audioUrl = URL.createObjectURL(audioData);
    const audio = new Audio(audioUrl);
    audio.play();
  } else {
    // JSON event
    const message = JSON.parse(event.data);
    console.log(`📨 Event: ${message.event}`, message.data);

    if (message.event === 'tts_start') {
      console.log('🔊 TTS synthesis started');
    } else if (message.event === 'tts_complete') {
      console.log(`✅ TTS complete (${message.data.duration_s}s)`);
    }
  }
};
```

### Expected Flow

1. **After `ai_response_complete` event**:
   ```
   📨 Event: ai_response_complete { text: "Hi! How can I help you?", ... }
   ```

2. **TTS Start Event**:
   ```
   📨 Event: tts_start { session_id: "..." }
   🔊 TTS synthesis started
   ```

3. **Binary Audio Chunks** (multiple):
   ```
   🎵 Received TTS audio chunk: 8192 bytes
   🎵 Received TTS audio chunk: 8192 bytes
   🎵 Received TTS audio chunk: 4096 bytes
   ```

4. **TTS Complete Event**:
   ```
   📨 Event: tts_complete { session_id: "...", duration_s: 1.23 }
   ✅ TTS complete (1.23s)
   ```

### Backend Logs

Watch for TTS processing:

```bash
docker logs voxbridge-api --tail 100 --follow | grep -E "(🔊|TTS|audio)"
```

**Expected Output**:
```
🔊 Starting TTS synthesis for text: "Hi! How can I help you?"
⏱️ ⭐ LATENCY [TTS first byte]: 0.342s
✅ TTS complete (145,280 bytes, 1.23s)
```

### Performance Metrics

- **TTS First Byte**: < 500ms (target: 300-400ms)
- **TTS Total Duration**: 1-3s (depends on response length)
- **Audio Chunk Size**: 8192 bytes (configurable)

### Verify Chatterbox Integration

Check Chatterbox is healthy:

```bash
# Health check
curl http://localhost:4123/health | python3 -m json.tool

# Expected: {"status": "ok", ...}
```

Check backend can reach Chatterbox:

```bash
docker logs voxbridge-api --tail 50 | grep -i chatterbox
```

**Expected**:
```
HTTP Request: GET http://chatterbox-tts:4123/health "HTTP/1.1 200 OK"
```

### Test Speaker Mute

Frontend should allow muting TTS playback while keeping STT active. This is implemented via `isSpeakerMuted` state.

**When muted**:
- Text responses still appear
- Binary audio chunks are discarded
- Console shows: `🔇 Speaker muted, discarding audio chunk`

## 🧪 Test 6: Error Cases

### Invalid Session ID
```bash
# Connect with non-existent session
curl -i -N -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: test123" \
  "http://localhost:4900/ws/voice?session_id=invalid-uuid&user_id=test"
```

**Expected**: Error event with "Invalid session_id format"

### Missing Query Params
```bash
# Connect without session_id
curl -i -N -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: test123" \
  "http://localhost:4900/ws/voice?user_id=test"
```

**Expected**: Error event with "Missing session_id or user_id"

### Wrong User ID
```javascript
// In browser console
const ws = new WebSocket(`ws://localhost:4900/ws/voice?session_id=${sessionId}&user_id=WRONG_USER`);

ws.onmessage = (event) => {
  console.log(JSON.parse(event.data));
};
```

**Expected**: Error event with "Session does not belong to user"

## 🔍 Monitoring During Tests

### Backend Logs
```bash
# Follow WebSocket logs
docker logs voxbridge-api --tail 100 --follow | grep -E "(🔌|🎙️|WebRTC|/ws/voice)"

# Follow transcription logs
docker logs voxbridge-api --tail 100 --follow | grep -E "(partial|final)_transcript"

# Follow LLM logs
docker logs voxbridge-api --tail 100 --follow | grep -E "(🤖|LLM|ai_response)"

# Follow latency logs
docker logs voxbridge-api --tail 100 --follow | grep "⏱️ LATENCY"
```

### Database Check
```bash
# View sessions
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT id, user_id, title, active FROM sessions ORDER BY started_at DESC LIMIT 5;"

# View conversations
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT session_id, role, substring(content, 1, 50) as content FROM conversations ORDER BY created_at DESC LIMIT 10;"
```

### WhisperX Health
```bash
# Check WhisperX is responding
docker logs voxbridge-whisperx --tail 50

# Test WhisperX directly (if needed)
# Note: This is for debugging only, normal flow goes through handler
```

## 🐛 Troubleshooting

### No TTS Audio Plays ⭐ **NEW**
**Problem**: Text response appears, but no audio plays in browser

**Check**:
1. Verify Chatterbox is running:
   ```bash
   curl http://localhost:4123/health | python3 -m json.tool
   ```

2. Check backend logs for TTS errors:
   ```bash
   docker logs voxbridge-api --tail 50 | grep -E "(TTS|Chatterbox|ERROR)"
   ```

3. Verify binary chunks are being sent:
   ```bash
   docker logs voxbridge-api --tail 50 | grep "binary audio chunk"
   ```

4. Check browser console for audio playback errors

**Solutions**:
- Start Chatterbox: `cd ../chatterbox-tts-api && docker compose -f docker/docker-compose.yml up -d`
- Verify `CHATTERBOX_URL` in `.env` (should be `http://chatterbox-tts:4123`)
- Check browser audio is not muted
- Verify speaker mute button is not enabled in UI

### TTS Latency Too High ⭐ **NEW**
**Problem**: TTS first byte takes > 1 second

**Check**:
```bash
docker logs voxbridge-api --tail 100 | grep "LATENCY \[TTS first byte\]"
```

**Solutions**:
1. Verify Chatterbox is using GPU (not CPU):
   ```bash
   docker logs chatterbox-tts-api | grep -i "gpu\|cuda"
   ```

2. Reduce Chatterbox streaming chunk size in `webrtc_handler.py`:
   ```python
   'streaming_chunk_size': 50,  # Lower = faster first byte
   ```

3. Check GPU utilization:
   ```bash
   docker exec chatterbox-tts nvidia-smi
   ```

### Audio Glitches/Stuttering ⭐ **NEW**
**Problem**: TTS audio plays but with clicks, pops, or stuttering

**Solutions**:
1. Increase audio chunk size in `webrtc_handler.py`:
   ```python
   async for chunk in response.aiter_bytes(chunk_size=16384):  # Increase from 8192
   ```

2. Reduce Chatterbox streaming quality:
   ```python
   'streaming_quality': 'draft',  # Lower quality but faster
   ```

3. Check network latency between containers:
   ```bash
   docker exec voxbridge-api ping -c 5 chatterbox-tts
   ```

### Connection Refused
**Problem**: Cannot connect to WebSocket

**Check**:
```bash
# Verify service is running
docker compose ps voxbridge-api

# Check port is listening
netstat -an | grep 4900

# Check logs for startup errors
docker logs voxbridge-api --tail 50
```

### No Partial Transcripts
**Problem**: Only see final transcript

**Check**:
```bash
# Verify WhisperX is running
docker compose ps voxbridge-whisperx

# Check WhisperX logs
docker logs voxbridge-whisperx --tail 50

# Test with longer audio (>2 seconds of speech)
```

### LLM Error
**Problem**: AI response fails

**Check**:
```bash
# Verify agent configuration
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT name, llm_provider, llm_model FROM agents;"

# Check environment variables
docker exec voxbridge-api env | grep -E "(OPENROUTER|LOCAL_LLM|N8N)"

# Test LLM provider directly
curl http://localhost:11434/v1/models  # For local Ollama
```

### Opus Decode Error
**Problem**: `⚠️ Opus decode error` in logs

**Solutions**:
1. Verify browser is using Opus codec:
   ```javascript
   console.log(mediaRecorder.mimeType);  // Should be "audio/webm;codecs=opus"
   ```

2. Check audio constraints:
   ```javascript
   const stream = await navigator.mediaDevices.getUserMedia({
     audio: { sampleRate: 16000, channelCount: 1 }
   });
   ```

3. Try different frame size (if persistent):
   ```python
   # In webrtc_handler.py
   pcm_data = self.opus_decoder.decode(audio_data, frame_size=960)  # Try 60ms
   ```

## ✅ Success Criteria

After running tests, you should see:

1. **WebSocket Connection**: ✅ Opens successfully
2. **Session Validation**: ✅ Accepts valid session, rejects invalid
3. **Audio Processing**: ✅ Receives and decodes Opus chunks
4. **Transcription**: ✅ Partial and final transcripts received
5. **Silence Detection**: ✅ Finalizes after 600ms silence
6. **LLM Integration**: ✅ AI response chunks stream back
7. **TTS Synthesis**: ✅ Chatterbox generates audio after AI response ⭐ **NEW**
8. **TTS Streaming**: ✅ Binary audio chunks streamed to browser ⭐ **NEW**
9. **TTS Events**: ✅ `tts_start` and `tts_complete` events received ⭐ **NEW**
10. **Audio Playback**: ✅ TTS audio plays in browser (Web Audio API) ⭐ **NEW**
11. **Database Persistence**: ✅ Messages saved to conversations table
12. **Error Handling**: ✅ Errors sent to client, graceful cleanup
13. **Logging**: ✅ Comprehensive logs with emojis
14. **Cleanup**: ✅ No resource leaks on disconnect

## 📚 Related Documentation

- **Integration Guide**: `docs/WEBRTC_BACKEND_INTEGRATION.md`
- **Implementation Summary**: `docs/WEBRTC_IMPLEMENTATION_SUMMARY.md`
- **Frontend Spec**: `frontend/WEBRTC_README.md`

## 🎯 Next Steps

After successful testing:

1. **Integration Tests**: Add automated tests to `tests/integration/`
2. **Load Testing**: Test with multiple concurrent sessions
3. **Latency Optimization**: Profile and optimize bottlenecks
4. **Production Deployment**: Deploy to staging environment
5. **Frontend Integration**: Connect real frontend dashboard
