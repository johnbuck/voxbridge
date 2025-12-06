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

### Service Layer Architecture (VoxBridge 2.0)

**Core Services:**
- `src/discord_bot.py` - Main entry point + Discord bot
- `src/api/server.py` - FastAPI application (decoupled from bot)
- `src/services/conversation_service.py` - Session management + caching
- `src/services/stt_service.py` - WhisperX abstraction
- `src/services/llm_service.py` - LLM provider routing
- `src/services/tts_service.py` - Chatterbox abstraction
- `src/services/memory_service.py` - Mem0 fact extraction
- `src/plugins/discord_plugin.py` - Plugin-based Discord voice
- `src/whisper_server.py` - WhisperX WebSocket server (GPU)

### Docker Services

1. **whisperx** (port 4901) - WhisperX STT server, GPU-enabled (GPU 1)
2. **voxbridge-api** (port 4900) - Discord bot, integrates all services

## Architecture Documentation

**Comprehensive architectural plans and implementation guides** are organized in `docs/`.

### Navigation Index

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for complete documentation map and quick navigation.

### Implementation Plans

#### Multi-Agent System Implementation
**Document**: [docs/architecture/multi-agent-implementation-plan.md](docs/architecture/multi-agent-implementation-plan.md) (70KB, 2223 lines)

**Summary**: 7-phase architectural refactor to transform VoxBridge from single-speaker to multi-agent concurrent system.

**Key Features**:
- Session management (PostgreSQL + Redis)
- Queue-based concurrency (replace speaker lock)
- Agent routing service (multi-agent support)
- Enhanced webhook payload (conversation context)
- User agent selection (Discord slash commands)
- Runtime configuration (agent management)
- Infrastructure updates (Docker Compose)

**Status**: 🔴 **NOT STARTED** (Future Work)
**Effort**: 8-12 development days

**Before**: Single speaker, single agent, no sessions
**After**: Concurrent users, multiple agents, full conversation context

---

#### Frontend + LangGraph Agent System
**Document**: [docs/planning/frontend-langgraph-plan.md](docs/planning/frontend-langgraph-plan.md) (31KB)

**Summary**: Web frontend for VoxBridge with Chatterbox-inspired styling, plus LangChain/LangGraph-based agent system as alternative to n8n webhooks.

**Tech Stack**:
- React 19 + TypeScript + Vite ✅ **DEPLOYED**
- Tailwind CSS v4 + shadcn/ui (New York style) ✅
- WebSocket + Server-Sent Events ✅
- LangChain/LangGraph (Python) 🔴 **Not Started**

**Status**: ✅ **Frontend COMPLETE** (port 4903) | 🔴 LangGraph NOT STARTED

---

### Progress Tracking

#### Frontend Development Progress
**Document**: [docs/progress/frontend-progress.md](docs/progress/frontend-progress.md) (9.4KB)

**Latest Status**: ✅ **COMPLETE** - Frontend + Backend fully deployed

**Completed**:
- ✅ Production deployment on port 4903
- ✅ React 19 + Vite + TypeScript (4 pages, 1500+ LOC)
- ✅ Chatterbox theme integration (OKLCH color system)
- ✅ 11 UI components (shadcn/ui)
- ✅ Backend API fully implemented (all 11+ endpoints)
- ✅ WebSocket real-time events operational
- ✅ Docker deployment with nginx

**Not Started**:
- 🔴 LangGraph agent system integration

---

### Analysis Documents

#### n8n Webhooks & Sessions Analysis
**Document**: [ANALYSIS_n8n_WEBHOOKS_SESSIONS.md](ANALYSIS_n8n_WEBHOOKS_SESSIONS.md) (30KB)

**Summary**: Detailed analysis of current VoxBridge architecture constraints and blockers for multi-agent support.

**Key Findings**:
- Single-speaker, single-agent system by architectural design
- Global speaker lock prevents concurrent processing
- No session management or conversation history
- Static webhook URL limits routing capabilities
- Singleton architecture prevents horizontal scaling

**Conclusion**: Multi-agent support requires core architectural changes (detailed in multi-agent implementation plan).

---

## 🎯 Current Implementation Status

**Last Updated**: October 26, 2025

### ✅ Production Features

**Deployed Services**:
- ✅ `voxbridge-whisperx` (ports 4901, 4902) - WhisperX STT with GPU acceleration
- ✅ `voxbridge-api` (port 4900) - Discord bot + FastAPI + WebSocket
- ✅ `voxbridge-frontend` (port 4903) - React dashboard (4 pages, production build)

**Core Features**:
- ✅ Real-time speech-to-text (WhisperX on RTX 5060 Ti)
- ✅ Text-to-speech (Chatterbox TTS integration)
- ✅ Streaming AI responses with clause splitting
- ✅ Thinking indicator sound + duration tracking
- ✅ Active speaker UX indicators
- ✅ AI generation status indicators
- ✅ Parallel TTS generation (optional)
- ✅ Single-speaker lock system

**API Endpoints** (11+ total):
- ✅ Voice: `/voice/join`, `/voice/leave`, `/voice/speak`
- ✅ Monitoring: `/health`, `/status`, `/api/metrics`
- ✅ Data: `/api/channels`, `/api/transcripts`
- ✅ Config: `/api/config`, `/api/tts/config`
- ✅ Control: `/api/speaker/unlock`
- ✅ Real-time: WebSocket `/ws/events`

**Performance & Reliability**:
- ✅ E2E latency benchmark framework
- ✅ Comprehensive metrics tracking
- ✅ TTS error handling with retry
- ✅ HTTP retry with exponential backoff
- ✅ Graceful degradation

**Testing** (Updated Nov 2025):
- ✅ 99 total tests (99 passing, 0 failing)
- ✅ 90%+ code coverage
- ✅ WebRTC Phase 4: 45 tests (28 WebRTC + 17 integration/E2E)
- ✅ Unit, integration, and E2E test frameworks
- ✅ Test runner wrapper script

**Source Code**:
- 3,665 lines of Python code
- src/discord_bot.py (1,200+ lines)
- src/speaker_manager.py (800+ lines)
- src/streaming_handler.py (700+ lines)

### 🔴 Not Implemented (Future Plans)

**Multi-Agent System**:
- ❌ PostgreSQL + Redis infrastructure
- ❌ Session management
- ❌ Queue-based concurrency (still uses single-speaker lock)
- ❌ Agent routing service
- ❌ Conversation context/history
- ❌ User agent selection via Discord commands

**LangGraph Integration**:
- ❌ LangChain/LangGraph agent framework
- ❌ Alternative to n8n webhooks
- ❌ Multi-agent orchestration

---

## Critical Architectural Concepts

### Database Architecture (VoxBridge 2.0)

**PostgreSQL schema for agent storage and session management** - Foundation for multi-agent system.

**Status**: ✅ **Phase 1 COMPLETE** (Oct 26, 2025)
**Branch**: `voxbridge-2.0`

**Schema Design**:

```sql
-- Agents: AI agent configurations
CREATE TABLE agents (
    id UUID PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    system_prompt TEXT NOT NULL,
    llm_provider VARCHAR(50) NOT NULL,  -- 'openrouter' | 'local_llm'
    llm_model VARCHAR(100) NOT NULL,     -- e.g., 'anthropic/claude-3.5-sonnet'
    temperature FLOAT DEFAULT 0.7,
    tts_voice VARCHAR(100),               -- Voice ID (e.g., 'en_US-amy-medium')
    tts_exaggeration FLOAT DEFAULT 1.0,   -- Emotion intensity (0.25-2.0)
    tts_cfg_weight FLOAT DEFAULT 0.7,     -- Speech pace control (0.0-1.0)
    tts_temperature FLOAT DEFAULT 0.3,    -- Voice sampling randomness (0.05-5.0)
    tts_language VARCHAR(10) DEFAULT 'en', -- Language code
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Sessions: User voice sessions
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,      -- Discord user ID or web user ID
    user_name VARCHAR(100),
    agent_id UUID REFERENCES agents(id),
    active BOOLEAN DEFAULT TRUE,
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    session_type VARCHAR(20) NOT NULL,  -- 'web' | 'discord' | 'extension'
    metadata TEXT                        -- JSON for extension-specific data
);

-- Conversations: Message history
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    role VARCHAR(20) NOT NULL,           -- 'user' | 'assistant' | 'system'
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    audio_duration_ms INTEGER,           -- For user messages
    tts_duration_ms INTEGER,             -- For assistant messages
    llm_latency_ms INTEGER,              -- For assistant messages
    total_latency_ms INTEGER             -- End-to-end latency
);
```

**Design Decisions** (Phase 1):
- **UUID primary keys** - Globally unique, scalable for distributed systems
- **API keys from env vars only** - No encrypted keys in database (simple, secure)
- **PostgreSQL only** - Redis deferred to Phase 5 (start simple)
- **Integer PKs for conversations** - High-volume insert performance

**TTS Configuration (Nov 2025)** - Aligned with Chatterbox API:
- **Removed deprecated fields**: `tts_rate`, `tts_pitch` (not supported by Chatterbox)
- **Added Chatterbox fields**: `tts_exaggeration` (emotion), `tts_cfg_weight` (pace), `tts_temperature` (sampling), `tts_language`
- **Migration required**: Alembic migration `011_align_tts_with_chatterbox.py`
- **Breaking change**: Existing `tts_rate`/`tts_pitch` values will be lost

**Indexes**:
- `agents.name` (unique) - Lookup by name
- `sessions.user_id`, `sessions.agent_id`, `sessions.active` - Session queries
- `conversations.session_id`, `conversations.timestamp` - History retrieval

**Key Files**:
- `src/database/models.py:170` - SQLAlchemy ORM models
- `src/database/session.py:140` - Async connection management
- `src/database/seed.py:160` - Example agent seeding
- `alembic/versions/001_initial_schema.py` - Initial migration

**Example Agents** (with new TTS config):
1. **Auren (Default)** - Friendly general-purpose assistant (temp=0.7, tts_exaggeration=1.0, tts_cfg_weight=0.7)
2. **TechSupport** - Technical troubleshooting specialist (temp=0.5, tts_cfg_weight=0.5 for slower speech)
3. **Creative Writer** - Creative writing assistant (temp=0.9, tts_exaggeration=1.5 for expressive delivery)

---

### Speaker Lock System

**Single-speaker constraint** - Only one user can speak at a time.

**Lock Acquisition Flow:**
1. User starts speaking → `on_speaking_start(user_id)`
2. Check if `active_speaker` is None
3. If locked, ignore new speaker
4. If free, acquire lock and start transcription

**Lock Release Triggers:**
- Silence detected (600ms threshold, Nov 2025 fix)
- Timeout (45 seconds max)
- Manual finalization

**Key Files:**
- `src/speaker_manager.py:74-103` - Lock acquisition
- `src/speaker_manager.py:334-358` - Lock release

### WebRTC Voice Chat (Phase 4)

**Browser-based voice chat** - Real-time transcription and AI responses via WebRTC.

**Status**: ✅ **COMPLETE** (Nov 2025) - 45 tests, 90%+ coverage

**Critical Fixes (Nov 5-7, 2025)**:
1. **Silence Detection Bug** - Timer would freeze during WebM buffering, causing transcripts to hang indefinitely
   - **Fix**: Move `last_audio_time` update to BEFORE silence check (not inside PCM extraction block)
   - **Impact**: Silence now detected correctly after 600ms

2. **TTS Audio Bug** - Zero TTS audio played (100% failure rate) due to premature WebSocket disconnect
   - **Fix**: Keep WebSocket open until user disconnects (not on `ai_response_complete`)
   - **Flow**: ai_response_complete → Stop animation → tts_start → tts_complete → Play buffered audio
   - **Impact**: TTS audio now plays in 100% of cases, multi-turn conversations work

3. **Duplicate Response Bug** - AI responses appeared twice then disappeared (React Query race condition)
   - **Fix**: Remove optimistic updates, use streaming display exclusively, transition to database
   - **State Machine**: `[Active Streaming] → [Waiting for DB] → [Database Persisted]`
   - **Impact**: Zero duplicates, seamless transition, single source of truth

**Architecture Patterns**:
- **Silence Detection**: Update timer on EVERY audio chunk (even when pcm_data is empty)
- **WebSocket Lifecycle**: Persist until user disconnect (enables multi-turn conversations)
- **Optimistic Updates**: ❌ **ANTI-PATTERN** for backend-generated data (use streaming → database transition)
- **Audio Format Detection**: Explicit 'opus' or 'pcm' format indicator sent to WhisperX

**Key Files**:
- `src/voice/webrtc_handler.py:590` - WebRTC audio pipeline (refactored to use service layer)
- `frontend/src/hooks/useWebRTCAudio.ts:344` - Browser audio capture and WebSocket streaming
- `frontend/src/pages/VoxbridgePage.tsx` - Multi-turn conversation UI (streaming → database transition)

**Test Coverage** (Phase 4 + Nov 2025):
- 28 WebRTC tests (100% passing)
- 10 integration tests (mock WhisperX)
- 4 E2E tests (real WhisperX)
- 3 unit tests (PCM audio decoding)
- **Total**: 45 tests, 90%+ WebRTC handler coverage

**See Also**: [docs/WEBRTC_FIXES_SESSION_SUMMARY.md](docs/WEBRTC_FIXES_SESSION_SUMMARY.md) for detailed fix analysis and migration guide.

---

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

### Python Core (VoxBridge 2.0 Service Architecture)
```
/
├── src/                        # Python source code
│   ├── discord_bot.py          # Main entry point + Discord bot
│   ├── whisper_server.py       # WhisperX server (runs in whisperx container)
│   ├── api/                    # FastAPI application (Phase 6.4.1)
│   │   ├── server.py           # Decoupled FastAPI routes
│   │   └── __init__.py
│   ├── services/               # Service layer (Phase 5)
│   │   ├── conversation_service.py  # Session + context management
│   │   ├── stt_service.py      # WhisperX abstraction
│   │   ├── llm_service.py      # LLM provider routing
│   │   ├── tts_service.py      # Chatterbox abstraction
│   │   ├── memory_service.py   # Mem0 fact extraction
│   │   └── agent_service.py    # Agent CRUD
│   ├── plugins/                # Plugin system (Phase 6)
│   │   ├── discord_plugin.py   # Plugin-based Discord voice
│   │   └── base.py             # Plugin base class
│   ├── database/               # Database layer
│   │   ├── models.py           # SQLAlchemy ORM models
│   │   ├── session.py          # Async connection management
│   │   └── seed.py             # Example agent seeding
│   └── utils/                  # Utility modules
│       ├── encryption.py       # API key encryption (Fernet)
│       └── text_filters.py     # Text processing
├── alembic/                    # Database migrations
│   ├── env.py                  # Alembic environment (async)
│   └── versions/               # Migration scripts (001-028+)
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
5. **Restart container** - `docker compose restart voxbridge-api`

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
docker compose restart voxbridge-api
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

### ❌ Optimistic Updates for Backend-Generated Data

**Context**: Fixed Nov 5-7, 2025 (WebRTC duplicate response bug)

```typescript
// BAD - Optimistic update for AI response (backend-generated)
queryClient.setQueryData(['messages', sessionId], (old) => [
  ...old,
  { role: 'assistant', content: streamingText }  // Creates duplicate when DB fetches
]);

// GOOD - Streaming display with database transition
// 1. Show streaming display during active streaming
{streamingChunks.length > 0 && (
  <StreamingMessageDisplay chunks={streamingChunks} />
)}

// 2. Automatically clear when database has message
useEffect(() => {
  if (!isStreaming && streamingChunks.length > 0) {
    const latestAssistant = messages.find(m => m.role === 'assistant');
    if (latestAssistant) setStreamingChunks([]);  // Clear - DB ready
  }
}, [messages, isStreaming, streamingChunks]);
```

**Why This is Bad**:
- Optimistic updates create race conditions with database queries
- Frontend sees two messages: optimistic (cache) + database (query)
- React rendering causes duplicates and flickering
- Backend should be single source of truth for AI-generated data

**When to Use Optimistic Updates**:
- ✅ User-initiated actions (posting a comment, liking a post)
- ❌ Backend-generated responses (AI streaming, webhook data)

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
docker compose restart voxbridge-api

# View logs
docker logs voxbridge-api -f

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

## Claude Code Workflows

VoxBridge is optimized for use with Claude Code (claude.ai/code) using slash commands, custom agents, and structured documentation.

### Slash Commands

Repeatable workflow templates are available via the `/` menu:

- **`/test-unit`** - Run unit tests with coverage report
- **`/test-integration`** - Run integration tests with mock servers
- **`/test-all`** - Run full test suite with HTML coverage
- **`/logs-discord`** - Tail Discord bot logs (filtered)
- **`/logs-latency`** - Show latency tracking logs
- **`/rebuild`** - Rebuild and restart containers (no cache)
- **`/debug-streaming`** - Debug streaming response flow
- **`/status`** - Check services health and metrics

**Usage:**
```
Type `/` in Claude Code to see available commands
Select command from menu or type full name
```

**Team Benefit:** These commands are checked into git (`.claude/commands/`), ensuring consistent workflows across the team.

### Custom Agents

Specialized sub-agents with focused system prompts are available via the `/agents` command:

#### test-reviewer
**Purpose:** Review test coverage and quality, identify gaps and edge cases

**When to use:**
- After adding new features
- Before code reviews or pull requests
- When coverage drops below 80%

**Example:**
```
/agents test-reviewer

Please analyze test coverage for speaker_manager.py and recommend improvements.
```

#### latency-optimizer
**Purpose:** Analyze latency logs and recommend performance optimizations

**When to use:**
- Investigating performance issues
- After adding new features (latency regression check)
- Optimizing user experience

**Example:**
```
/agents latency-optimizer

Please analyze the last 500 latency logs and recommend optimizations for reducing end-to-end conversation latency.
```

#### docker-troubleshooter
**Purpose:** Diagnose Docker, container, networking, and GPU issues

**When to use:**
- Containers won't start or keep restarting
- GPU not detected or CUDA errors
- Network connectivity issues
- After Docker/driver updates

**Example:**
```
/agents docker-troubleshooter

The voxbridge-whisperx container keeps restarting. Please diagnose and provide a solution.
```

#### api-documenter
**Purpose:** Generate and update OpenAPI specifications for FastAPI endpoints

**When to use:**
- Adding new API endpoints
- Preparing API documentation for external users
- Setting up API testing tools

**Example:**
```
/agents api-documenter

Please generate a complete OpenAPI 3.0 specification for all VoxBridge endpoints and save it to openapi.yaml.
```

### Test-Writing Agents

Specialized agents for increasing test coverage from 61% to 80%+:

#### unit-test-writer
**Purpose:** Create unit tests for uncovered code paths

**When to use:**
- Coverage reports show gaps in critical modules
- Adding new features (write tests for new code)
- Refactoring (ensure tests still cover functionality)
- Bug fixes (add test that reproduces bug, then fix)

**Capabilities:**
- Analyze coverage reports (htmlcov/, pytest --cov)
- Write async/await unit tests
- Mock Discord.py, WhisperX, n8n, Chatterbox
- Focus on critical paths (speaker lock, streaming, error handling)
- Run tests after writing to verify they pass

**Example:**
```
/agents unit-test-writer

Analyze coverage for speaker_manager.py and write unit tests for lines 450-475 (n8n webhook error handling). Goal: increase coverage from 45% to 75%+.
```

#### integration-test-writer
**Purpose:** Create integration tests using mock servers

**When to use:**
- Testing component interactions
- Validating full workflows (STT → AI → TTS)
- Benchmarking latency and performance
- Testing retry logic and error recovery

**Capabilities:**
- Write integration tests (tests/integration/)
- Use existing mock servers (tests/mocks/)
- Test component interactions (Discord ↔ WhisperX ↔ n8n ↔ Chatterbox)
- Include latency benchmarks and assertions
- Test error handling and recovery

**Example:**
```
/agents integration-test-writer

Write integration test for the full streaming pipeline (STT → n8n → TTS) with latency benchmarks. Target: first audio in < 1s.
```

#### test-fixture-builder
**Purpose:** Build reusable test fixtures and mock infrastructure

**When to use:**
- Multiple tests have duplicate setup code
- Test setup is complex (> 5 lines)
- Creating new test data samples
- Building mock infrastructure for new components

**Capabilities:**
- Create pytest fixtures (@pytest.fixture)
- Build mock Discord objects (VoiceClient, User, Guild)
- Generate realistic sample data (Opus audio, transcripts, TTS responses)
- Organize fixtures in conftest.py
- Reduce code duplication

**Example:**
```
/agents test-fixture-builder

Create fixtures for mock Discord voice clients and sample Opus audio data. Multiple tests need these and setup is currently duplicated.
```

#### e2e-test-writer
**Purpose:** Create end-to-end tests using real services

**When to use:**
- Validating production readiness
- Testing complete user workflows
- Benchmarking real-world performance
- Smoke testing before deployment
- Verifying service integrations with real components

**Capabilities:**
- Write E2E tests (tests/e2e/)
- Use real Docker services (VoxBridge, WhisperX, Chatterbox)
- Test complete user workflows (join → speak → transcribe → respond → TTS)
- Handle service availability gracefully (@pytest.mark.skipif)
- Focus on critical paths (10-20 tests, not comprehensive coverage)

**Example:**
```
/agents e2e-test-writer

Write an E2E test for the complete conversation workflow using real VoxBridge, WhisperX, and Chatterbox services. Include latency benchmarks and error handling.
```

**Test Coverage Workflow:**

1. **Analyze gaps:**
   ```
   /test-all  # Run full suite
   /agents test-reviewer  # Analyze coverage gaps
   ```

2. **Build infrastructure (if needed):**
   ```
   /agents test-fixture-builder
   Create fixtures for [scenario X]
   ```

3. **Write tests (by type):**
   ```
   /agents unit-test-writer
   Write unit tests for speaker_manager.py lines 450-475

   /agents integration-test-writer
   Write integration test for streaming pipeline

   /agents e2e-test-writer
   Write E2E test for full conversation loop
   ```

4. **Verify improvements:**
   ```
   /test-all  # Run full suite
   /agents test-reviewer  # Re-analyze coverage
   ```

### Extended Thinking

For complex tasks, use extended thinking to improve solution quality:

- **`think`** - Basic extended thinking (standard)
- **`think hard`** - More thorough analysis
- **`think harder`** - Deep analysis for complex problems
- **`ultrathink`** - Maximum thinking budget for critical tasks

**Example use cases:**
- Complex refactoring (speaker_manager.py, streaming_handler.py)
- Architectural decisions (new streaming patterns, latency optimizations)
- Debugging intricate async/await issues
- Designing new test frameworks

**Example:**
```
think harder

How can we reduce latency in the streaming pipeline while maintaining accuracy and reliability?
```

### Parallel Development with Git Worktrees

Run multiple Claude Code sessions simultaneously on different features:

```bash
# Main session: Refactoring speaker_manager.py
cd /home/wiley/Docker/voxbridge

# Parallel session 1: Adding new metrics
git worktree add ../voxbridge-metrics -b feature/new-metrics
cd ../voxbridge-metrics
# Run claude code here

# Parallel session 2: Fixing bug
git worktree add ../voxbridge-bugfix -b fix/tts-timeout
cd ../voxbridge-bugfix
# Run claude code here

# Cleanup when done
git worktree remove ../voxbridge-metrics
git worktree remove ../voxbridge-bugfix
```

**Benefits:**
- Work on multiple features simultaneously
- Each session has independent context
- No context pollution between sessions
- Easy to switch between tasks

### Recommended Workflows

#### Adding a New Feature
1. **Plan:** Use `think hard` to analyze requirements and design approach
2. **Implement:** Write code following existing patterns (see Modification Patterns section)
3. **Test:** Use `/test-unit` to verify unit tests pass
4. **Review:** Use `/agents test-reviewer` to check coverage
5. **Document:** Update relevant documentation (README.md, CLAUDE.md)
6. **Integration:** Use `/test-integration` to verify integration
7. **Verify:** Use `/status` to check services are healthy
8. **Commit:** Create git commit with detailed message

#### Debugging Performance Issues
1. **Collect Data:** Use `/logs-latency` to gather metrics
2. **Analyze:** Use `/agents latency-optimizer` for recommendations
3. **Implement:** Apply optimizations (code or configuration)
4. **Validate:** Compare before/after metrics
5. **Document:** Update CLAUDE.md with findings

#### Troubleshooting Container Issues
1. **Check Status:** Use `/status` to see container health
2. **View Logs:** Use `/logs-discord` or check specific container
3. **Diagnose:** Use `/agents docker-troubleshooter` for analysis
4. **Fix:** Apply recommended solution
5. **Verify:** Use `/status` again to confirm fix
6. **Rebuild if needed:** Use `/rebuild` for clean slate

### Documentation Hierarchy

VoxBridge uses a three-tier documentation system optimized for Claude Code:

1. **CLAUDE.md** (~200 lines) - Quick reference for common tasks
   - Common commands, file locations, API endpoints
   - Claude Code auto-reads this on every conversation start
   - Use for quick lookups and common operations

2. **AGENTS.md** (~700 lines) - Comprehensive architectural guidance
   - Architecture patterns, modification guidelines, anti-patterns
   - Deep dive into system design and implementation
   - Use for understanding system behavior and best practices

3. **README.md** (~700 lines) - User-facing documentation
   - Setup instructions, API reference, troubleshooting
   - Designed for end users and new developers
   - Use for onboarding and external documentation

**When to use which:**
- **Quick task** (restart service, run tests) → CLAUDE.md
- **Understanding architecture** (how streaming works) → AGENTS.md
- **Setup or API usage** (how to install, API endpoints) → README.md

### Tips for Working with Claude Code

1. **Use Slash Commands Liberally** - They encapsulate best practices and save time
2. **Delegate to Specialized Agents** - Reduces context pollution, improves focus
3. **Think Before Complex Tasks** - Use `think hard` for refactoring or architectural changes
4. **Run Tests Frequently** - Use `/test-unit` after every significant change
5. **Check Logs Early** - Use `/logs-discord` or `/logs-latency` to catch issues fast
6. **Leverage Parallel Sessions** - Use git worktrees for concurrent feature development
7. **Keep Documentation Updated** - Update CLAUDE.md with new patterns or commands

## Getting Help

- **README.md** - User-facing documentation, setup, API reference
- **tests/README.md** - Testing framework guide
- **tests/TESTING_FRAMEWORK_SUMMARY.md** - Detailed testing architecture
- **tests/INTEGRATION_TEST_SUMMARY.md** - Latency benchmarks and integration results
- **tests/TEST_RESULTS.md** - Coverage reports and test results
- **AGENTS.md** - This file (architectural guidance)
