# Discord Bot Voice Service

Real-time voice transcription service for Discord using WhisperX STT.

## Architecture

```
┌─────────────────────────────────────────┐
│  n8n (existing)                         │
│  - Text chat with Discord               │
│  - Agent node (Auren's brain)           │
│  - RAG knowledge retrieval              │
│  - Decision making                      │
└─────────────┬───────────────────────────┘
              │ HTTP calls
              ▼
┌─────────────────────────────────────────┐
│  discord-bot-voice (Docker container)   │
│  - Join/leave voice channels ✅         │
│  - Listen (Faster Whisper STT) ✅       │
│  - Speak (Chatterbox TTS) ✅            │
│  - Send transcripts to n8n              │
└─────────────────────────────────────────┘
```

## Features

### ✅ Voice Channel Management
- Join/leave Discord voice channels via HTTP API
- Automatic connection handling and reconnection

### ✅ Real-Time Speech-to-Text
- **WhisperX** for high-quality transcription
- **Single-speaker lock** - One person talks at a time
- **Low latency** - 400ms-1.2s response time
- **Automatic silence detection** - 800ms threshold
- **Timeout protection** - 45 second max speaking time
- **Direct Opus processing** - No unnecessary conversion

### ✅ Text-to-Speech
- Chatterbox TTS integration
- Plays audio responses in voice channel

### 🌊 Streaming Response Support (NEW!)
- **90%+ latency reduction** - From 8-10s to <1s first audio
- **Sentence-by-sentence playback** - Start speaking before AI finishes
- **n8n webhook streaming** - Real-time AI response chunks
- **Intelligent buffering** - Complete sentences, not fragments
- See [N8N_STREAMING_SETUP.md](./N8N_STREAMING_SETUP.md) for configuration

### ✅ Multi-Speaker Handling
- First speaker gets priority
- Other speakers ignored until current speaker finishes
- Natural conversation flow

## Quick Start

### WhisperX Benefits
- **Better accuracy** - ~97% vs ~95% (compared to Faster Whisper)
- **Word-level timestamps** - Precise transcription timing
- **GPU support** - Automatic GPU detection with CPU fallback
- **Optimized performance** - For NVIDIA RTX GPUs

### Setup Options

#### Option 1: CPU Mode (5 minutes) ⚡ **RECOMMENDED**

Get the bot working immediately, enable GPU later.

```bash
# Build and start
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Watch logs
docker-compose logs -f
```

**Expected performance:**
- Latency: 500ms-1.2s (acceptable)
- CPU usage: 30-60%
- Works immediately ✅

**To enable GPU later:** Set up NVIDIA Container Toolkit, then restart - automatic GPU detection will use it.

#### Option 2: GPU Mode (30-60 minutes)

Maximum performance from the start (requires NVIDIA GPU + CUDA Toolkit).

**Setup Requirements:**
1. Install NVIDIA Container Toolkit
2. Configure Docker to use NVIDIA runtime

**Build and start:**
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
docker-compose logs -f
```

**Expected performance:**
- Latency: 200-400ms (excellent) 🚀
- GPU usage: 40-60%
- VRAM: ~2GB

### Verify It's Working

**Check Logs - GPU Mode:**
```
🎮 GPU detected: NVIDIA GeForce RTX 3080
💾 VRAM available: 10.0 GB
📊 Device: cuda, Compute: float16
✅ WhisperX model loaded successfully
```

**Check Logs - CPU Mode:**
```
💻 No GPU detected, using CPU
📊 Device: cpu, Compute: int8
✅ WhisperX model loaded successfully
```

**Test Health Endpoint:**
```bash
curl http://localhost:4900/health
# Should return: {"status": "ok", "botReady": true, ...}
```

### Performance Tuning

**For faster response (lower accuracy):**
```env
WHISPERX_MODEL=tiny           # Fastest model
SILENCE_THRESHOLD_MS=500      # Quicker finalization
```

**For better accuracy (slower):**
```env
WHISPERX_MODEL=medium         # More accurate
SILENCE_THRESHOLD_MS=1000     # Wait longer for complete thoughts
```

**For maximum accuracy (GPU only):**
```env
WHISPERX_MODEL=large-v2       # Best accuracy (~99%)
WHISPERX_BATCH_SIZE=8         # Reduce if VRAM issues
```

## How It Works

### Speaker Lock System

```
User A starts speaking
→ 🎤 Lock to User A
→ 📡 Stream Opus audio to Whisper
→ 🔄 Receive partial transcripts (real-time)
→ 🤫 Detect silence (800ms)
→ ✅ Finalize complete transcript
→ 📤 Send to n8n webhook
→ 🔓 Unlock (ready for next speaker)

User B tries to speak while User A is active
→ 🔇 IGNORED (no queue, no buffering)
→ User B can try again after User A finishes
```

### Audio Pipeline

```
Discord Voice Channel
↓
Opus audio stream (48kHz)
↓
WebSocket → WhisperX Server (Python)
↓
WhisperX transcription
↓
Partial results (buffered)
↓
Final result on silence/timeout
↓
n8n webhook
```

## Installation

### Prerequisites
- Docker & Docker Compose
- Discord Bot Token
- n8n webhook URL
- Chatterbox TTS server (optional)

### Environment Variables

Create a `.env` file:

```env
# Discord Bot Token
DISCORD_TOKEN=your_discord_bot_token

# WhisperX Configuration
WHISPERX_MODEL=small                  # tiny, base, small, medium, large-v2
WHISPERX_DEVICE=auto                  # auto (GPU if available), cuda, or cpu
WHISPERX_COMPUTE_TYPE=float16         # float16 (GPU), int8 (CPU)
WHISPERX_BATCH_SIZE=16                # Batch size for processing
WHISPER_SERVER_URL=ws://whisperx:4901 # WebSocket URL for WhisperX server
WHISPER_SERVER_PORT=4901

# Speaker Management
SILENCE_THRESHOLD_MS=800              # Silence detection threshold (ms)
MAX_SPEAKING_TIME_MS=45000            # Max speaking time (45 seconds)

# Chatterbox TTS Configuration
CHATTERBOX_URL=http://host.docker.internal:4800/v1
CHATTERBOX_VOICE_ID=your_voice_id

# n8n Integration
N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/voice-transcript

# Streaming Configuration
USE_STREAMING=true                    # Enable n8n response streaming (default: true)

# Server Port
PORT=4900
```

### Build & Run

```bash
# Build the Docker image
docker-compose build

# Start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

## API Endpoints

### POST /voice/join
Join a Discord voice channel.

**Request:**
```json
{
  "channelId": "1234567890",
  "guildId": "0987654321"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Joined voice channel: General",
  "channelId": "1234567890"
}
```

### POST /voice/leave
Leave the current voice channel.

**Response:**
```json
{
  "success": true,
  "message": "Left voice channel"
}
```

### POST /voice/speak
Speak text in the voice channel using TTS.

**Request:**
```json
{
  "text": "Hello, how can I help you?"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Speaking text"
}
```

### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "botReady": true,
  "inVoiceChannel": true,
  "speakerLocked": false,
  "activeSpeaker": null,
  "timestamp": "2025-10-03T10:00:00.000Z"
}
```

### GET /status
Detailed status information.

**Response:**
```json
{
  "bot": {
    "username": "Auren",
    "id": "123456789",
    "ready": true
  },
  "voice": {
    "connected": true,
    "state": "ready",
    "speakerLocked": true,
    "activeSpeaker": "987654321",
    "speakingDuration": 5000,
    "silenceDuration": 200
  },
  "whisper": {
    "serverConfigured": true,
    "model": "base",
    "language": "en"
  },
  "services": {
    "chatterbox": true,
    "n8nWebhook": true
  }
}
```

## Whisper Models

| Model | Size | RAM | Speed | Accuracy |
|-------|------|-----|-------|----------|
| tiny  | 39M  | ~1GB | Fastest | ~85% |
| base  | 74M  | ~1GB | Fast | ~95% | ⭐ **Recommended**
| small | 244M | ~2GB | Medium | ~97% |
| medium| 769M | ~5GB | Slow | ~98% |
| large | 1550M| ~10GB| Slowest | ~99% |

## Performance

### Latency Breakdown
- Audio buffering: 100-500ms
- Whisper inference: 200-800ms (base model, CPU)
- Network overhead: 10-50ms
- **Total: 400ms-1.2s**

### Optimization Tips
1. **Use GPU** - Set `WHISPER_DEVICE=cuda` for 5-10x speedup
2. **Smaller model** - Use `tiny` for faster responses
3. **Adjust silence threshold** - Lower for quicker finalization
4. **Compute type** - Use `float16` on GPU for better accuracy

## Troubleshooting

### Bot not responding to voice
1. Check WhisperX server is running: `docker-compose logs whisperx`
2. Verify WebSocket connection in logs
3. Ensure `WHISPER_SERVER_URL` is correct

### High latency
1. Try smaller WhisperX model (`tiny` or `small`)
2. Enable GPU if available (`WHISPERX_DEVICE=cuda`)
3. Check CPU usage - may need more resources

### Transcription accuracy issues
1. Use larger model (`small` or `medium`)
2. Ensure good audio quality in Discord
3. Check language setting matches speaker

### Multiple speakers not working
1. This is expected - only one speaker at a time
2. Users must wait their turn
3. Check speaker lock status in `/status` endpoint

## Development

### Project Structure
```
discord-bot-voice/
├── server.js                      # Main Node.js server
├── speaker-manager.js             # Speaker lock logic with streaming
├── streaming-response-handler.js  # n8n streaming response handler
├── whisper-client.js              # WebSocket client for WhisperX
├── whisper-server.py              # Python WhisperX server
├── package.json                   # Node dependencies
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container definition
├── Dockerfile.whisperx            # WhisperX container definition
├── docker-compose.yml             # Docker orchestration
├── N8N_STREAMING_SETUP.md         # n8n streaming configuration guide
└── .env                           # Configuration
```

### Running Locally (without Docker)

**Terminal 1 - WhisperX Server:**
```bash
pip install -r requirements.txt
python3 whisper-server.py
```

**Terminal 2 - Node Server:**
```bash
npm install
node server.js
```

## Docker Build Optimization

This project uses a multi-stage Docker build approach, reducing the final image size by **60-80%** (from ~8-12 GB to ~2-3 GB).

### Multi-Stage Build Architecture

The Dockerfile uses 4 distinct stages:

- **Stage 1: Python Builder** - Compiles Python dependencies into wheels
- **Stage 2: Node.js Builder** - Installs Node.js dependencies
- **Stage 3: Runtime Base** - Conditional GPU/CPU base image selection
- **Stage 4: Final Image** - Minimal runtime with only necessary artifacts

### Build Options

**Standard Build (GPU Support):**
```bash
docker-compose build
docker-compose up -d
```

**CPU-Only Build (Smaller Image ~1.5-2 GB):**
```bash
# Set environment variable
export ENABLE_GPU=cpu
# Or add to .env file
echo "ENABLE_GPU=cpu" >> .env

docker-compose build
docker-compose up -d
```

**Build from Scratch (No Cache):**
```bash
docker-compose build --no-cache
```

### Size Comparison

| Configuration | Before | After | Reduction |
|--------------|--------|-------|-----------|
| GPU Support  | ~8-12 GB | ~2-3 GB | ~70-75% |
| CPU Only     | ~8-12 GB | ~1.5-2 GB | ~80-85% |

### Key Optimizations

- **Combined RUN commands** - Reduced layer count
- **Removed duplicate FFmpeg** - Using system FFmpeg instead of npm package
- **Production-only Node modules** - No dev dependencies
- **Pre-built Python wheels** - Faster installation, no compilation in final image
- **Non-root user** - Security improvement
- **Proper .dockerignore** - Prevents copying unnecessary files

## n8n Streaming Configuration

Configure your n8n workflow to support streaming responses for minimal latency voice bot interactions.

### Streaming Architecture

1. **Discord Bot** → Sends transcript to n8n webhook
2. **n8n AI Agent** → Generates response in chunks
3. **n8n Respond to Webhook** → Streams chunks back to Discord Bot
4. **Discord Bot** → Extracts sentences and sends to Chatterbox TTS
5. **Chatterbox** → Streams audio back to Discord voice channel

**Result:** First audio response in ~300-800ms instead of 8-10 seconds! (90%+ latency reduction)

### n8n Workflow Setup

#### 1. Webhook Trigger Node

Configure your webhook to accept the Discord Bot request:

```json
{
  "httpMethod": "POST",
  "path": "your-webhook-path",
  "responseMode": "responseNode"
}
```

**Important:** Set `responseMode` to `"responseNode"` to enable streaming with the "Respond to Webhook" node.

#### 2. AI Agent Node

Configure your AI agent node to process the transcript:

**Input:**
```json
{
  "userId": "{{ $json.userId }}",
  "transcript": "{{ $json.transcript }}",
  "timestamp": "{{ $json.timestamp }}"
}
```

#### 3. Respond to Webhook Node (CRITICAL)

**Settings:**
- **Respond With:** `Text`
- **Response Body:** Your response (see formats below)
- **Options → Response Headers:**
  ```
  Content-Type: text/plain; charset=utf-8
  Transfer-Encoding: chunked
  ```

**Response Format Options:**

There are two ways to pass TTS options to VoxBridge:

##### Option A: HTTP Headers (RECOMMENDED for streaming)
Pass TTS options via `X-TTS-Options` header while keeping response body as plain text for true streaming:

**Headers:**
```json
{
  "Content-Type": "text/plain; charset=utf-8",
  "Transfer-Encoding": "chunked",
  "X-TTS-Options": "{\"voiceMode\":\"clone\",\"referenceAudioFilename\":\"voice.wav\",\"temperature\":0.8,\"exaggeration\":1.2,\"cfgWeight\":3.0,\"seed\":42}"
}
```

**Response Body:**
```
{{ $json.output }}
```

**Advantages:**
- ✅ True streaming - chunks flow immediately
- ✅ Per-request voice options - different agents use different voices
- ✅ Clean separation - metadata in headers, content in body
- ✅ Backward compatible - works without header (uses defaults)

**Available TTS Options:**
- `voiceMode`: `"clone"` or `"preset"`
- `referenceAudioFilename`: Voice file to clone (e.g., `"voice.wav"`)
- `temperature`: Speech variation (0.0-1.0, default 0.7)
- `exaggeration`: Emotion intensity (0.0-2.0, default 1.0)
- `cfgWeight`: Classifier-free guidance (1.0-10.0, default 3.0)
- `seed`: Random seed for reproducibility (integer)
- `outputFormat`: `"wav"`, `"mp3"`, `"flac"` (default `"wav"`)
- `chunkSize`: Streaming chunk size (default 50)
- `streamingStrategy`: `"sentence"`, `"clause"`, `"word"` (default `"sentence"`)

**Example - Setting X-TTS-Options in n8n:**
In the "Respond to Webhook" node, add to "Response Headers":
```
X-TTS-Options
```
Value:
```
{{ JSON.stringify({
  "voiceMode": "clone",
  "referenceAudioFilename": "auren_voice.wav",
  "temperature": 0.75,
  "exaggeration": 1.1,
  "cfgWeight": 3.5
}) }}
```

##### Option B: JSON Format (Legacy, non-streaming)
Pass TTS options in the response body as JSON:

**Headers:**
```json
{
  "Content-Type": "application/json; charset=utf-8"
}
```

**Response Body:**
```json
{
  "output": {
    "content": "{{ $json.output.content }}",
    "userID": "{{ $json.output.userID }}",
    "userName": "{{ $json.output.userName }}"
  },
  "options": {
    "voiceMode": "{{ $json.options.voiceMode }}",
    "speedFactor": "{{ $json.options.speedFactor }}",
    "temperature": "{{ $json.options.temperature }}",
    "streamingStrategy": "{{ $json.options.streamingStrategy }}"
  }
}
```

**Note:** This format buffers the entire response before processing, losing streaming benefits.

**Simplified Format (Plain Text without options):**

If you don't need TTS options:
```
{{ $json.output }}
```

The bot automatically detects which format you're using.

### Testing Streaming Setup

**Verify with cURL:**
```bash
curl -N -X POST \
  -H "Content-Type: application/json" \
  -d '{"userId":"test","transcript":"Hello","streaming":true}' \
  https://your-n8n-webhook-url
```

Expected: Text chunks arriving progressively (not all at once)

**Check Response Headers:**
Look for `Transfer-Encoding: chunked`

### Performance Metrics

**Before Streaming:**
- First audio: 8-10 seconds
- Total latency: 8-11 seconds

**After Streaming:**
- First audio: 300-800ms ⚡
- Continuous playback: ~100-200ms per sentence
- **Total latency reduction: 90%+**

### Troubleshooting Streaming

**No streaming, all text arrives at once:**
- Ensure n8n "Respond to Webhook" has streaming enabled
- Check response headers include `Transfer-Encoding: chunked`
- Verify AI agent node supports streaming output

**High latency still present:**
- ✅ n8n webhook has `responseMode: "responseNode"`
- ✅ Response headers include chunked transfer encoding
- ✅ `USE_STREAMING=true` in Discord bot `.env`
- ✅ Chatterbox TTS is running and accessible

## Documentation

### Testing
- **[Test Running Guide](tests/README.md)** - How to run tests
- **[Testing Framework Summary](tests/TESTING_FRAMEWORK_SUMMARY.md)** - Testing framework implementation details
- **[Integration Test Results](tests/INTEGRATION_TEST_SUMMARY.md)** - Integration test results & latency benchmarks
- **[Test Results & Coverage](tests/TEST_RESULTS.md)** - Comprehensive test results (61% coverage, 86 unit tests)

## License

MIT
