# AGENTS.md - VoxBridge AI Assistant Guide

This document guides AI assistants (like Claude Code) when working with the VoxBridge codebase.

## Project Overview

**VoxBridge** is a Discord voice bot that provides real-time speech-to-text (STT) and text-to-speech (TTS) capabilities with AI agent integration.

### Architecture Summary

```
Discord Voice Channel
    ↓ (Opus audio)
WhisperX STT (Python, GPU-accelerated)
    ↓ (transcript)
n8n AI Agent (via webhook)
    ↓ (streaming response)
Chatterbox TTS (Python)
    ↓ (audio stream)
Discord Voice Channel
```

### Dual-Language Architecture

**Python-based implementation:**
- `src/discord_bot.py` - Main Discord bot with voice handling
- `src/speaker_manager.py` - Single-speaker lock system
- `src/whisper_client.py` - WhisperX WebSocket client
- `src/streaming_handler.py` - n8n streaming response processor
- `src/whisper_server.py` - WhisperX WebSocket server

### Docker Services

1. **whisperx** (port 4901) - WhisperX STT server, GPU-enabled (GPU 1)
2. **voxbridge-discord** (port 4900) - Discord bot, integrates all services

## Critical Architectural Concepts

### Speaker Lock System

**Single-speaker constraint** - Only one user can speak at a time.

**Lock Acquisition Flow:**
1. User starts speaking → `on_speaking_start(user_id)`
2. Check if `active_speaker` is None
3. If locked, ignore new speaker
4. If free, acquire lock and start transcription

**Lock Release Triggers:**
- Silence detected (800ms threshold)
- Timeout (45 seconds max)
- Manual finalization

**Key Files:**
- `src/speaker_manager.py:74-103` - Lock acquisition
- `src/speaker_manager.py:334-358` - Lock release

### Streaming Pipeline

**Low-latency streaming** reduces response time from 8-10s to <1s.

**Pipeline Components:**
1. **WhisperX** - Real-time transcription via WebSocket
2. **n8n webhook** - Streaming HTTP response (chunked transfer encoding)
3. **StreamingResponseHandler** - Sentence extraction and buffering
4. **Chatterbox TTS** - Audio generation and playback

**Key Files:**
- `src/streaming_handler.py` - Response chunk processing
- `src/speaker_manager.py:291-333` - Streaming response handler

### Test Mode

**Environment-based webhook switching** - Allows testing without affecting production.

**Configuration:**
- `N8N_WEBHOOK_URL` - Production webhook
- `N8N_WEBHOOK_TEST_URL` - Test webhook
- `N8N_TEST_MODE=true|false` - Mode selector

**Implementation:**
- `src/speaker_manager.py:52-67` - Webhook selection logic
- Logs full webhook URL on startup (🧪 test mode, 🌐 production mode)
- Requires container restart to switch modes

## File Organization

### Python Core (Primary)
```
/
├── src/                        # Python source code
│   ├── __init__.py
│   ├── discord_bot.py          # Main Discord bot entry point
│   ├── speaker_manager.py      # Speaker lock + n8n integration
│   ├── whisper_client.py       # WhisperX WebSocket client
│   ├── streaming_handler.py    # n8n streaming response handler
│   └── whisper_server.py       # WhisperX server (runs in whisperx container)
├── requirements-bot.txt        # Discord bot dependencies
└── requirements.txt            # WhisperX server dependencies
```

### Configuration
```
/
├── .env                        # Environment configuration (DO NOT COMMIT)
├── docker-compose.yml          # Service orchestration
├── Dockerfile.python           # Discord bot container
└── Dockerfile.whisperx         # WhisperX server container
```

### Testing
```
tests/
├── README.md                          # Test running guide
├── TESTING_FRAMEWORK_SUMMARY.md       # Framework architecture
├── INTEGRATION_TEST_SUMMARY.md        # Integration test results
├── TEST_RESULTS.md                    # Coverage report
├── unit/                              # Unit tests (fully mocked)
├── integration/                       # Integration tests (mock servers)
├── mocks/                             # Mock server implementations
├── fixtures/                          # Test data
└── utils/                             # Test utilities
```

### Documentation
```
/
├── README.md                   # Comprehensive project documentation
├── AGENTS.md                   # This file
└── tests/README.md             # Testing documentation
```

## Code Modification Guidelines

### When Modifying Speaker Lock Logic

**File:** `src/speaker_manager.py`

**Critical sections:**
- `on_speaking_start()` - Lock acquisition (lines 74-103)
- `on_speaking_end()` - Silence detection trigger (lines 105-119)
- `_silence_monitor()` - Silence threshold logic (lines 187-200)
- `_timeout_monitor()` - Max speaking time enforcement (lines 202-212)
- `_unlock()` - Lock release and cleanup (lines 334-358)

**Testing requirements:**
- Add unit test in `tests/unit/test_speaker_manager.py`
- Add integration test in `tests/integration/test_streaming_latency.py` if latency-related

**Common modifications:**
- Changing thresholds: Update `.env` defaults, not hardcoded values
- Adding new finalization triggers: Follow `_silence_monitor()` pattern
- Modifying unlock behavior: Update `_unlock()` and test task cancellation

### When Adding n8n Integration Features

**File:** `src/speaker_manager.py`

**Key methods:**
- `_send_to_n8n()` - Webhook POST with retry (lines 248-289)
- `_handle_streaming_response()` - Streaming chunk processor (lines 291-333)

**Payload format:**
```python
{
    'text': transcript,
    'userId': user_id,
    'timestamp': datetime.now().isoformat(),
    'useStreaming': bool
}
```

**Testing requirements:**
- Use `tests/mocks/mock_n8n_server.py` for integration tests
- Test both streaming and non-streaming modes
- Verify retry logic with network errors

### When Modifying WhisperX Integration

**Files:** `src/whisper_client.py`, `src/whisper_server.py`

**WebSocket protocol:**
1. Client connects → sends `{"type": "start", "userId": "..."}`
2. Server responds → `{"type": "ready"}`
3. Client streams → `{"type": "audio", "data": base64_encoded_opus}`
4. Server sends → `{"type": "partial", "text": "..."}`
5. Client finalizes → `{"type": "finalize"}`
6. Server responds → `{"type": "final", "text": "..."}`

**Testing requirements:**
- Use `tests/mocks/mock_whisperx_server.py` for integration tests
- Test connection handling, audio streaming, finalization
- Verify reconnection logic

### When Updating Docker Configuration

**Files:** `docker-compose.yml`, `Dockerfile.python`, `Dockerfile.whisperx`

**Important considerations:**
- GPU allocation: WhisperX uses GPU 1 (`device_ids: ['1']`)
- Volume mounts for live code updates during development
- Environment variable defaults with `${VAR:-default}` syntax
- Network: `bot-network` and `pinkleberry_bridge` (both external)

**Testing requirements:**
- Rebuild containers: `docker compose build --no-cache`
- Verify environment variables: `docker compose config`
- Test GPU allocation: Check logs for "GPU detected"

## Testing Framework

### Test Categories

**Unit Tests** (`tests/unit/`)
- Fully mocked, no I/O
- Fast (<100ms per test)
- Run with: `pytest tests/unit -v`

**Integration Tests** (`tests/integration/`)
- Mock servers (WhisperX, n8n, Chatterbox)
- Moderate speed (100ms-1s per test)
- Run with: `pytest tests/integration -v`

**E2E Tests** (`tests/e2e/`)
- Real services required
- Slow (>1s per test)
- Run with: `pytest tests/e2e -v` (requires Docker services running)

### Running Tests

```bash
# Quick validation (unit tests only)
./scripts/test.sh tests/unit -v

# Full test suite with coverage
./scripts/test.sh tests/unit --cov=. --cov-report=term-missing

# Specific integration test
./scripts/test.sh tests/integration/test_streaming_latency.py -v

# Watch mode for development
./scripts/test.sh tests/unit -v --looponfail
```

### Test File Naming

- `test_<component>.py` - Unit tests for component
- `test_<component>_integration.py` - Integration tests
- `test_<feature>_e2e.py` - End-to-end tests

## Common Tasks

### Adding a New Feature

1. **Plan first** - Create todo list with TodoWrite tool
2. **Read relevant files** - Use Read tool for context
3. **Modify code** - Use Edit tool (prefer editing over Write)
4. **Add tests** - Unit test minimum, integration test for critical paths
5. **Update documentation** - README.md if user-facing, AGENTS.md if architectural
6. **Test locally** - Run relevant test suite
7. **Mark todos complete** - Update TodoWrite as you go

### Debugging a Test Failure

1. **Run specific test** - `./scripts/test.sh tests/unit/test_file.py::test_name -v`
2. **Add print statements** - Run with `-s` flag to see prints
3. **Check logs** - Look for emoji indicators (🎤 🔇 🤫 🏁 etc.)
4. **Use debugger** - Run with `--pdb` flag
5. **Check mocks** - Verify mock servers are running correctly
6. **Timing issues** - Use `wait_for_condition()` helper for async operations

### Updating Environment Configuration

1. **Edit `.env`** - Add new variable
2. **Update `docker-compose.yml`** - Pass variable to service
3. **Update code** - Read with `os.getenv('VAR_NAME', 'default')`
4. **Document in README.md** - Add to "Environment Variables" section
5. **Restart container** - `docker compose restart voxbridge-discord`

### Investigating Performance Issues

**Target latencies:**
- WhisperX transcription: 200-800ms (base model, CPU)
- n8n webhook response: 300-800ms (first chunk)
- Chatterbox TTS TTFB: <50ms
- Total conversation loop: <1s

**Profiling approach:**
1. Check `tests/INTEGRATION_TEST_SUMMARY.md` for baseline metrics
2. Run `tests/integration/test_streaming_latency.py` for current measurements
3. Add timing logs with `time.time()` in critical paths
4. Look for blocking operations in async code
5. Verify GPU usage for WhisperX

## Performance Constraints

### Latency Targets

- **Silence detection**: 800ms threshold (configurable)
- **Max speaking time**: 45s timeout (configurable)
- **WhisperX response**: <1s for base model (CPU)
- **n8n streaming TTFB**: <500ms
- **TTS playback start**: <100ms after first chunk

### Resource Constraints

- **VRAM**: ~2GB for WhisperX (small model)
- **CPU**: 30-60% during active transcription
- **Network**: <10KB/s for audio streaming
- **Memory**: <500MB per container

## Docker Deployment Patterns

### Development (Live Code Updates)

```yaml
volumes:
  - ./src/discord_bot.py:/app/src/discord_bot.py
  - ./src/speaker_manager.py:/app/src/speaker_manager.py
```

**Restart after code changes:**
```bash
docker compose restart voxbridge-discord
```

### Production (Embedded Code)

Remove volume mounts, rebuild image:
```bash
docker compose build --no-cache
docker compose up -d
```

### GPU Configuration

WhisperX requires NVIDIA GPU:
```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          device_ids: ['1']  # Use GPU 1
          capabilities: [gpu]
```

**Verify GPU detection:**
```bash
docker logs voxbridge-whisperx | grep "GPU detected"
```

## Documentation Updates

### When to Update README.md

- New user-facing features
- API endpoint changes
- Environment variable additions
- Setup/installation procedure changes
- Performance characteristic changes

### When to Update AGENTS.md

- New architectural patterns
- Code organization changes
- Critical file structure modifications
- Common task additions
- Testing framework changes

### When to Update tests/README.md

- New test categories or markers
- Test running procedure changes
- Mock server additions
- Testing framework pattern changes

## Key Patterns and Conventions

### Logging with Emojis

```python
logger.info("🎤 {user_id} is now speaking (locked)")
logger.info("🔇 {user_id} stopped speaking")
logger.info("🤫 Silence detected - finalizing")
logger.info("🏁 Finalizing transcription")
logger.info("📤 Sending to n8n")
logger.info("🌊 Streaming response")
logger.error("❌ Error: {e}")
logger.warning("⚠️ Warning message")
logger.info("✅ Success")
logger.info("🧪 TEST MODE")
logger.info("🌐 PRODUCTION MODE")
```

**Benefits:**
- Quick visual scanning of logs
- Easier debugging in production
- Clear state transitions

### Async/Await Patterns

**Task creation:**
```python
# Background task
self.task = asyncio.create_task(self._monitor())

# Await completion
await self.task
```

**Task cancellation:**
```python
if self.task and not self.task.done():
    self.task.cancel()
    await asyncio.gather(self.task, return_exceptions=True)
```

**Timeout pattern:**
```python
try:
    await asyncio.wait_for(operation(), timeout=5.0)
except asyncio.TimeoutError:
    logger.warning("Operation timed out")
```

### Error Handling with Retry

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True
)
async def _send_to_n8n(self, transcript: str) -> None:
    # Implementation
```

**When to use:**
- Network operations (n8n webhook, Chatterbox TTS)
- External service calls
- Non-critical operations that can be retried

### Configuration Loading

```python
# Environment variable with default
self.silence_threshold_ms = int(os.getenv('SILENCE_THRESHOLD_MS', '800'))

# Boolean from string
self.use_streaming = os.getenv('USE_STREAMING', 'true').lower() != 'false'

# Optional configuration
self.webhook_url = os.getenv('N8N_WEBHOOK_URL')
if not self.webhook_url:
    logger.warning("⚠️ No webhook configured")
```

## TTS Latency Optimization

### Progressive Audio Playback (Option B - Implemented)

**Problem**: Chatterbox generates audio progressively, but VoxBridge buffers the entire response before playback (4-5s latency for long responses).

**Solution**: Stream audio bytes directly to FFmpeg stdin as they arrive, start playback after minimal buffer.

**Configuration**:
```python
USE_PROGRESSIVE_TTS_PLAYBACK=true  # Enable progressive playback
USE_PROGRESSIVE_TTS_PLAYBACK=false # Use buffered mode (default, more stable)
```

**Implementation** (`streaming_handler.py`):
- `_synthesize_and_play()` checks `self.use_progressive_playback`
- If true: Uses `_synthesize_and_play_progressive()` with FFmpeg stdin pipe
- If false: Uses existing `_synthesize_to_stream()` → `_play_audio_stream()` (buffered)

**Benefits**:
- 50-60% reduction in perceived latency
- Start playback after ~50-100KB instead of waiting for full download
- Maintains stable fallback option

### ❌ Sentence-by-Sentence TTS (Option A - DO NOT USE)

**Attempted approach**: Split AI response into sentences, send each to TTS separately, play sequentially.

**Why it doesn't work**:
- Breaks Chatterbox's internal audio coherence
- Causes pacing/intonation issues across sentence boundaries
- Introduced audio glitches and unnatural pauses
- Significantly more complex error handling

**Key learning**: Let Chatterbox handle text chunking internally. VoxBridge should stream the audio bytes progressively, not split the text.

## Anti-Patterns to Avoid

### ❌ Blocking Operations in Async Code

```python
# BAD
async def process():
    time.sleep(1)  # Blocks entire event loop

# GOOD
async def process():
    await asyncio.sleep(1)  # Yields to other tasks
```

### ❌ Ignoring Task Cancellation

```python
# BAD
async def monitor():
    while True:
        await asyncio.sleep(1)
        # No cancellation handling

# GOOD
async def monitor():
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Monitor cancelled")
        raise  # Re-raise to propagate cancellation
```

### ❌ Hardcoded Configuration

```python
# BAD
SILENCE_THRESHOLD = 800  # Hardcoded

# GOOD
self.silence_threshold_ms = int(os.getenv('SILENCE_THRESHOLD_MS', '800'))
```

### ❌ Missing Cleanup in _unlock()

```python
# BAD
async def _unlock():
    self.active_speaker = None
    # Forgot to cancel tasks → memory leak

# GOOD
async def _unlock():
    if self.timeout_task:
        self.timeout_task.cancel()
        await asyncio.gather(self.timeout_task, return_exceptions=True)
    self.active_speaker = None
```

### ❌ Creating New Files Instead of Editing

```python
# BAD - Creating new implementation file
Write(file_path="src/speaker_manager_v2.py", content="...")

# GOOD - Editing existing file
Edit(file_path="src/speaker_manager.py", old_string="...", new_string="...")
```

## Quick Reference

### File Modification Priority

1. **Edit existing files** (preferred)
2. **Create new files** (only if necessary)
3. **Delete files** (only if explicitly requested)

### Common File Paths

- Discord bot: `/home/wiley/Docker/voxbridge/src/discord_bot.py`
- Speaker manager: `/home/wiley/Docker/voxbridge/src/speaker_manager.py`
- WhisperX client: `/home/wiley/Docker/voxbridge/src/whisper_client.py`
- Streaming handler: `/home/wiley/Docker/voxbridge/src/streaming_handler.py`
- WhisperX server: `/home/wiley/Docker/voxbridge/src/whisper_server.py`
- Environment: `/home/wiley/Docker/voxbridge/.env`
- Compose: `/home/wiley/Docker/voxbridge/docker-compose.yml`

### Common Commands

```bash
# Restart bot
docker compose restart voxbridge-discord

# View logs
docker logs voxbridge-discord -f

# Rebuild containers
docker compose build --no-cache

# Run unit tests
./scripts/test.sh tests/unit -v

# Run integration tests
./scripts/test.sh tests/integration -v

# Check coverage
./scripts/test.sh tests/unit --cov=. --cov-report=term-missing
```

### Environment Variables to Know

- `DISCORD_TOKEN` - Discord bot authentication
- `WHISPER_SERVER_URL` - WhisperX WebSocket URL (ws://whisperx:4901)
- `N8N_WEBHOOK_URL` - Production webhook
- `N8N_WEBHOOK_TEST_URL` - Test webhook
- `N8N_TEST_MODE` - Switch to test mode (true/false)
- `CHATTERBOX_URL` - TTS service URL
- `SILENCE_THRESHOLD_MS` - Silence detection (default: 800)
- `MAX_SPEAKING_TIME_MS` - Max speaking duration (default: 45000)
- `USE_STREAMING` - Enable streaming responses (default: true)
- `USE_PROGRESSIVE_TTS_PLAYBACK` - Enable progressive audio playback (default: false)

### Test Markers

```bash
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m e2e          # End-to-end tests only
pytest -m "not slow"   # Skip slow tests
```

## Getting Help

- **README.md** - User-facing documentation, setup, API reference
- **tests/README.md** - Testing framework guide
- **tests/TESTING_FRAMEWORK_SUMMARY.md** - Detailed testing architecture
- **tests/INTEGRATION_TEST_SUMMARY.md** - Latency benchmarks and integration results
- **tests/TEST_RESULTS.md** - Coverage reports and test results
- **AGENTS.md** - This file (architectural guidance)
