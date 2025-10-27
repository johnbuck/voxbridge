# CLAUDE.md - VoxBridge

Quick reference for Claude Code when working with VoxBridge.

For comprehensive architecture and patterns, see [AGENTS.md](./AGENTS.md).

## 📐 Architecture & Planning

**Active implementation plans** are in `docs/`. See [ARCHITECTURE.md](ARCHITECTURE.md) for complete index.

### ✅ Implemented Features (October 2025)

**Frontend Dashboard** (Port 4903):
- ✅ React 19 + TypeScript + Vite production deployment
- ✅ 4 pages: VoxBridge, Discord Bot, WhisperX, Chatterbox TTS
- ✅ Real-time WebSocket monitoring (`/ws/events`)
- ✅ Dark mode with Chatterbox styling

**Agent Management UI** (Phase 2):
- ✅ Dedicated AgentsPage at `/agents` route
- ✅ Agent CRUD operations (create, edit, delete)
- ✅ Real-time updates via WebSocket
- ✅ Agent cards with provider badges
- ✅ Form validation for all agent fields

**Backend API** (Port 4900):
- ✅ All 11+ endpoints operational (voice, monitoring, config)
- ✅ WebSocket real-time events
- ✅ Health checks and metrics

**Performance Features**:
- ✅ Thinking indicator with sound + duration tracking
- ✅ Active speaker UX indicators
- ✅ Streaming optimizations (clause splitting, parallel TTS)
- ✅ E2E latency benchmark framework
- ✅ TTS error handling with retry logic

**Testing**: 43 tests (38 passing), 88% coverage

### 🟢 VoxBridge 2.0 - In Progress (Oct-Nov 2025)

**Branch**: `voxbridge-2.0`
**Plan**: [docs/architecture/voxbridge-2.0-transformation-plan.md](docs/architecture/voxbridge-2.0-transformation-plan.md)
**Status**: Phase 2 ✅ COMPLETE (Oct 27, 2025)

**Phase 1: Core Infrastructure** ✅:
- PostgreSQL 15 database for agents, sessions, conversations
- SQLAlchemy 2.0 ORM models with UUID primary keys
- Alembic migrations (async PostgreSQL)
- Database seed script (3 example agents)

**Phase 2: Agent Management System** ✅:
- Full CRUD API for AI agents (`/api/agents`)
- Dedicated AgentsPage at `/agents` route
- Real-time WebSocket updates for agent changes
- Support for multiple LLM providers (OpenRouter, Local)

**Upcoming**: Phase 3 (LLM Provider Abstraction), Phase 4 (Session/Conversation Management), Phase 5 (WebRTC)

### 📚 Related Planning Documents

1. **Multi-Agent System** - [docs/architecture/multi-agent-implementation-plan.md](docs/architecture/multi-agent-implementation-plan.md)
   - **Summary**: 7-phase refactor (session mgmt, queue concurrency, agent routing)
   - **Status**: Core phases incorporated into VoxBridge 2.0
   - **Effort**: 2,222 lines of detailed planning
   - **Note**: VoxBridge 2.0 builds on this foundation with expanded scope

2. **LangGraph Integration** - [docs/planning/frontend-langgraph-plan.md](docs/planning/frontend-langgraph-plan.md)
   - **Summary**: LangChain/LangGraph as alternative to n8n webhooks
   - **Status**: Future work (post-VoxBridge 2.0)
   - **Goal**: Multi-agent orchestration

**Quick navigation**: Start with [ARCHITECTURE.md](ARCHITECTURE.md) for complete documentation and roadmap.

## Quick Start

### Development Setup
```bash
# Start all services
docker compose up -d

# Watch logs (filtered)
docker logs voxbridge-discord --tail 100 --follow | grep -v "GET /health"

# Rebuild after changes
docker compose down && docker compose build --no-cache && docker compose up -d
```

### Testing
```bash
# Run unit tests with coverage
./test.sh tests/unit -v --cov=src --cov-report=term-missing

# Run integration tests
./test.sh tests/integration -v

# Run all tests with HTML coverage report
./test.sh tests/unit tests/integration --cov=. --cov-report=html --cov-report=term
```

## Architecture Overview

**Four-Container Setup (VoxBridge 2.0):**
- `postgres` (port 5432) - PostgreSQL 15 database for agents/sessions/conversations
- `voxbridge-whisperx` (ports 4901, 4902) - WhisperX STT server (GPU: RTX 5060 Ti)
- `voxbridge-discord` (port 4900) - Discord.py bot with FastAPI + streaming responses
- `voxbridge-frontend` (port 4903) - React monitoring dashboard ✅ **DEPLOYED**

**Key Integration Points:**
- Discord → PostgreSQL: Async SQLAlchemy (agent/session storage)
- Discord → WhisperX: WebSocket at `ws://whisperx:4901`
- Discord → Chatterbox TTS: HTTP at `http://chatterbox:4800`
- Discord → n8n: HTTP streaming webhook (`N8N_WEBHOOK_URL`)
- Frontend → Discord: WebSocket at `ws://localhost:4900/ws`

## Key Files

### Core Implementation
- **src/discord_bot.py** (1200+ lines) - Main bot, FastAPI server, metrics tracking
- **src/speaker_manager.py** (800+ lines) - Speaker lock, STT→n8n, thinking indicator
- **src/streaming_handler.py** (700+ lines) - Streaming AI responses, TTS playback
- **src/whisper_client.py** (350+ lines) - WhisperX WebSocket client
- **src/whisper_server.py** (400+ lines) - WhisperX server (GPU-accelerated)

### Database (VoxBridge 2.0)
- **src/database/models.py** (170 lines) - SQLAlchemy ORM models (Agent, Session, Conversation)
- **src/database/session.py** (140 lines) - Async session management with connection pooling
- **src/database/seed.py** (160 lines) - Example agent seeding script
- **alembic/versions/001_initial_schema.py** - Initial database migration

### Frontend
- **frontend/src/App.tsx** - Main dashboard with real-time metrics
- **frontend/src/components/** - UI components (MetricsCard, AudioVisualization, etc.)

### Configuration
- **docker-compose.yml** - Main orchestration (4 containers: postgres + whisperx + discord + frontend)
- **.env** - Environment variables (not in repo, see .env.example for template)
- **.env.example** - Environment variable template with database config
- **alembic.ini** - Alembic migration configuration
- **requirements-bot.txt** - Discord bot Python dependencies (includes SQLAlchemy, asyncpg)
- **requirements.txt** - WhisperX server dependencies
- **requirements-test.txt** - Testing dependencies

### Testing
- **tests/unit/** - Unit tests (43 total: 38 passing, 5 failing)
- **tests/integration/** - Integration tests (mock servers)
- **tests/e2e/** - End-to-end tests (real services)
- **tests/mocks/** - Mock servers (WhisperX, n8n, Chatterbox, Discord)
- **tests/fixtures/** - Test data (audio, transcripts, TTS samples)
- **Coverage**: 88% (38/43 passing rate)

## Environment Variables

**Required:**
- `DISCORD_TOKEN` - Discord bot token
- `N8N_WEBHOOK_URL` - n8n webhook for AI responses
- `CHATTERBOX_URL` - Chatterbox TTS API URL
- `CHATTERBOX_VOICE_ID` - Voice ID for TTS

**Database (VoxBridge 2.0):**
- `POSTGRES_USER=voxbridge` - PostgreSQL username
- `POSTGRES_PASSWORD=voxbridge_dev_password` - PostgreSQL password
- `POSTGRES_DB=voxbridge` - PostgreSQL database name
- `DATABASE_URL` - Auto-constructed from above or override
- `OPENROUTER_API_KEY` - Optional: OpenRouter API key for LLM provider
- `LOCAL_LLM_BASE_URL` - Optional: Local LLM endpoint (e.g., http://localhost:11434/v1)

**Optional (with defaults):**
- `WHISPER_SERVER_URL=ws://whisperx:4901` - WhisperX WebSocket
- `SILENCE_THRESHOLD_MS=600` - Silence detection (ms)
- `MAX_SPEAKING_TIME_MS=45000` - Max speaking time (45s)
- `USE_STREAMING=true` - Enable streaming responses
- `USE_CLAUSE_SPLITTING=true` - Split on clauses for lower latency
- `USE_THINKING_INDICATORS=true` - Play thinking sound during AI processing
- `THINKING_INDICATOR_PROBABILITY=0.8` - % chance of playing indicator

**WhisperX Configuration:**
- `WHISPERX_MODEL=small` - Model size (tiny, base, small, medium, large-v2)
- `WHISPERX_DEVICE=auto` - Device selection (auto, cuda, cpu)
- `WHISPERX_COMPUTE_TYPE=float16` - Computation type (float16 for GPU, int8 for CPU)
- `WHISPERX_BATCH_SIZE=16` - Batch size for transcription

## Common Commands

### Database Management (VoxBridge 2.0)
```bash
# Run Alembic migrations
docker exec voxbridge-discord alembic upgrade head

# Seed example agents
docker exec voxbridge-discord python -m src.database.seed

# Clear all agents (WARNING: Destructive!)
docker exec voxbridge-discord python -m src.database.seed --clear

# Check database connection
docker exec voxbridge-discord python -c "import asyncio; from src.database import check_db_connection; print(asyncio.run(check_db_connection()))"

# PostgreSQL shell
docker exec -it voxbridge-postgres psql -U voxbridge -d voxbridge

# View agents in database
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "SELECT id, name, llm_provider, llm_model FROM agents;"
```

### Docker Management
```bash
# View status
docker compose ps

# View logs (Discord bot only)
docker logs voxbridge-discord --tail 200 --follow

# View logs (WhisperX only)
docker logs voxbridge-whisperx --tail 200 --follow

# Restart specific service
docker compose restart voxbridge-discord

# Rebuild specific service
docker compose up -d --force-recreate --build voxbridge-discord
```

### Debugging
```bash
# Check health
curl http://localhost:4900/health | python3 -m json.tool

# Check metrics
curl http://localhost:4900/metrics | python3 -m json.tool

# View latency logs
docker logs voxbridge-discord --tail 200 | grep -E "(LATENCY|⏱️)"

# View streaming logs
docker logs voxbridge-discord --tail 300 | grep -E "(🌊|streaming|chunk|sentence)"

# View thinking indicator logs
docker logs voxbridge-discord --tail 200 | grep -E "(💭|thinking indicator|🎵)"
```

### Testing Shortcuts
```bash
# Run specific test file
./test.sh tests/unit/test_speaker_manager.py -v

# Run specific test function
./test.sh tests/unit/test_speaker_manager.py::test_silence_detection -v

# Run with print statements visible
./test.sh tests/unit -s

# Run integration tests (requires Docker services running)
docker compose up -d
./test.sh tests/integration -v
```

## Modification Patterns

### Adding New Latency Tracking
1. Add timestamp attribute in relevant class (e.g., `self.t_event_start`)
2. Calculate duration: `(time.time() - self.t_event_start) * 1000`
3. Log with emoji: `logger.info(f"⏱️ LATENCY [event_name]: {duration_ms:.2f}ms")`
4. Record in MetricsTracker if user-facing metric
5. Broadcast via WebSocket to frontend if real-time display needed

### Adding New Streaming Feature
1. Modify `streaming_handler.py` to handle new streaming pattern
2. Update `speaker_manager.py` to pass through streaming options
3. Add tests in `tests/unit/test_streaming_handler.py`
4. Update frontend `StreamingResponseChart.tsx` if visualization needed
5. Document in README.md

### Adding New Environment Variable
1. Add to `docker-compose.yml` with default value
2. Read in Python code: `os.getenv('VAR_NAME', 'default')`
3. Document in this file (Environment Variables section)
4. Add to README.md (Environment Variables section)

## API Endpoints

### Voice Control
- **POST /voice/join** - Join voice channel (`{channelId, guildId}`)
- **POST /voice/leave** - Leave voice channel
- **POST /voice/speak** - Speak text via TTS (`{text}` or `{output, options}`)

### Agent Management (VoxBridge 2.0)
- **GET /api/agents** - List all AI agents
- **GET /api/agents/{id}** - Get specific agent by UUID
- **POST /api/agents** - Create new agent (`{name, system_prompt, temperature?, llm_provider?, llm_model?, tts_voice?, tts_rate?, tts_pitch?, use_n8n?}`)
- **PUT /api/agents/{id}** - Update agent (partial update, all fields optional)
- **DELETE /api/agents/{id}** - Delete agent (cascades to sessions/conversations)

### Monitoring
- **GET /health** - Health check (bot ready, in voice, speaker status)
- **GET /status** - Detailed status (bot, voice, whisper, services)
- **GET /metrics** - Performance metrics (latency, durations, samples)
- **GET /api/channels** - Available Discord channels
- **WS /ws** - WebSocket for real-time events

## Code Style

- **Logging:** Use emoji prefixes (🎤 voice, 📡 network, ⏱️ latency, 🌊 streaming, 💭 thinking)
- **Async:** Prefer `async/await` over callbacks
- **Error Handling:** Try/except with detailed logging, graceful degradation
- **Type Hints:** Use Python type hints for function signatures
- **Docstrings:** Use docstrings for public methods, classes
- **Comments:** Explain "why" not "what"

## Anti-Patterns (AVOID)

❌ **Don't modify `AGENTS.md`** without careful review - it's comprehensive and well-structured
❌ **Don't remove emoji logging** - used for log filtering and debugging
❌ **Don't add `await` to sync functions** - causes "coroutine was never awaited" errors
❌ **Don't modify tests without running them** - test coverage is critical
❌ **Don't commit `.env` files** - contains secrets
❌ **Don't skip latency logging** - essential for performance tracking

## Links to Detailed Documentation

- **[AGENTS.md](./AGENTS.md)** - Comprehensive architecture, patterns, and guidelines (637 lines)
- **[README.md](./README.md)** - User-facing documentation and setup guide (671 lines)
- **[tests/README.md](./tests/README.md)** - Testing framework guide (432 lines)
- **[tests/TESTING_FRAMEWORK_SUMMARY.md](./tests/TESTING_FRAMEWORK_SUMMARY.md)** - Testing architecture
- **[tests/INTEGRATION_TEST_SUMMARY.md](./tests/INTEGRATION_TEST_SUMMARY.md)** - Integration test results
- **[tests/TEST_RESULTS.md](./tests/TEST_RESULTS.md)** - Test coverage report (61%, 86 unit tests)

## Notes for Claude Code

- **Context Priority:** Read AGENTS.md for comprehensive patterns, this file for quick tasks
- **Parallel Development:** Use git worktrees for concurrent feature work
- **Extended Thinking:** Use "think hard" for complex refactoring or architectural changes
- **Testing First:** Always run relevant tests after code changes
- **Log Verification:** Check Docker logs to verify behavior matches expectations
