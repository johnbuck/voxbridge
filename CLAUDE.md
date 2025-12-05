# CLAUDE.md - VoxBridge

Quick reference for Claude Code when working with VoxBridge.

For comprehensive architecture and patterns, see [AGENTS.md](./AGENTS.md).

## 📐 Architecture & Planning

**Active implementation plans** are in `docs/`. See [ARCHITECTURE.md](ARCHITECTURE.md) for complete index.

### ⚠️ Critical Architecture Decision: Single Unified Voice Interface

**VoxBridge uses ONE unified interface at the root path ("/") for ALL voice interactions:**

- **VoxbridgePage.tsx** (`frontend/src/pages/VoxbridgePage.tsx`) is the ONLY voice interface page
- Handles BOTH Discord voice chat AND browser WebRTC voice chat in a unified experience
- Unified conversation management with real-time animations (STT waiting indicators, AI generating indicators)
- Real-time WebSocket connections:
  - `/ws/events` - Discord events (partial_transcript, final_transcript, ai_response_chunk, ai_response_complete)
  - `/ws/voice` - Browser WebRTC audio streaming
- Both Discord and WebRTC events trigger the SAME animation states for a consistent UX

**❌ NO separate `/voice-chat` route should EVER exist:**
- VoiceChatPage.tsx was obsolete and has been deleted
- All voice features are consolidated in VoxbridgePage.tsx
- This prevents user confusion and code duplication

**Navigation Structure:**
- `/` - VoxbridgePage (Analytics + Voice Chat + Conversation Management)
- `/agents` - AgentsPage (AI Agent Management)
- `/settings` - SettingsPage (Service Configuration)

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

**Testing** (Updated Nov 2025): 99 tests (99 passing, 0 failing), 90%+ coverage - includes 45 WebRTC tests (28 WebRTC + 17 integration/E2E)

### 🟢 VoxBridge 2.0 - In Progress (Oct-Nov 2025)

**Branch**: `voxbridge-2.0`
**Plan**: [docs/architecture/voxbridge-2.0-transformation-plan.md](docs/architecture/voxbridge-2.0-transformation-plan.md)
**Status**: Phase 5 ✅ COMPLETE (Oct 28, 2025)

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

**Phase 3: LLM Provider Abstraction** ✅:
- Abstract LLM provider interface with streaming support
- OpenRouter.ai provider (SSE streaming)
- Local LLM provider (Ollama, vLLM, LM Studio)
- LLM provider factory with agent configuration
- Hybrid n8n mode (webhooks + direct LLM)
- 90 unit tests with ~88% coverage

**Phase 4: Web Voice Interface** ✅ (Nov 2025 WebRTC Fixes):
- Backend WebSocket handler (`/ws/voice` endpoint)
- Opus audio decoding, WhisperX integration
- LLM provider routing (OpenRouter/Local/n8n)
- Frontend WebRTC hook (useWebRTCAudio)
- Audio capture UI (AudioControls component)
- Real-time transcription + AI response display
- **Critical Fixes**: Silence detection (timer update before check), TTS audio (keep WebSocket open), duplicate responses (streaming → database transition)
- 45 tests (28 WebRTC + 17 integration/E2E, 100% passing, 90%+ coverage)

**Phase 5: Core Voice Pipeline Refactor** ✅:
- 4 new services (2,342 lines): ConversationService, STTService, LLMService, TTSService
- Refactored WebRTC handler + Discord bot to use service layer
- Deleted old files: speaker_manager.py, whisper_client.py, streaming_handler.py
- Net code reduction: -272 lines (22% smaller)
- 99 unit tests with 90%+ coverage
- ~300ms latency reduction per conversation turn

**Phase 6: Discord Plugin Integration** ✅:
- Per-agent Discord bot plugin system
- Plugin-based voice control endpoints (`/api/plugins/discord/voice/*`)
- Discord snowflake ID precision preservation (manual JSON serialization)
- Per-agent Discord status tracking (`/api/plugins/discord/voice/status/{agent_id}`)
- Channel selector modal with guild/channel browsing
- Auto-reconnect logic for state desync handling
- localStorage persistence for guild IDs across page reloads
- Responsive two-row layout for Discord plugin cards
- TTS test modal for agent-specific voice testing

**Upcoming**: Phase 7 (Extension System), Phase 8 (Documentation), Phase 9 (Testing & Migration)

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

### 🐛 Critical WebRTC Fixes (Nov 5-7, 2025)

**Branch**: `feature/sentence-level-streaming`
**Summary**: [docs/WEBRTC_FIXES_SESSION_SUMMARY.md](docs/WEBRTC_FIXES_SESSION_SUMMARY.md)
**Commits**: 12 logical commits (ce70c3f...886c781)

**Three critical bugs resolved** (100% fix rate):

1. **Silence Detection Bug** (src/voice/webrtc_handler.py:590)
   - **Problem**: Timer froze during WebM buffering → transcripts hung indefinitely
   - **Fix**: Move `last_audio_time` update BEFORE silence check (not inside PCM extraction)
   - **Impact**: Silence detected correctly after 600ms

2. **TTS Audio Bug** (frontend/src/hooks/useWebRTCAudio.ts:344)
   - **Problem**: WebSocket disconnected on `ai_response_complete` BEFORE TTS audio generated (100% failure)
   - **Fix**: Keep WebSocket open until user disconnect (not on ai_response_complete)
   - **Impact**: TTS audio plays in 100% of cases, multi-turn conversations work

3. **Duplicate Response Bug** (frontend/src/pages/VoxbridgePage.tsx)
   - **Problem**: Optimistic updates + database query = two messages visible (race condition)
   - **Fix**: Remove optimistic updates, use streaming → database transition pattern
   - **Impact**: Zero duplicates, seamless transition, single source of truth

**Key Changes**:
- TTS configuration aligned with Chatterbox API (breaking change - migration required)
- 27 new tests (100% passing): 10 integration + 4 E2E + 3 unit
- Comprehensive documentation in `docs/analysis/` and `docs/implementation/`

**Migration Required**:
```bash
docker exec voxbridge-api alembic upgrade head  # Run 011_align_tts_with_chatterbox.py
```

## Quick Start

### Development Setup
```bash
# Start all services
docker compose up -d

# Watch logs (filtered)
docker logs voxbridge-api --tail 100 --follow | grep -v "GET /health"

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
- `voxbridge-api` (port 4900) - Discord.py bot with FastAPI + streaming responses
- `voxbridge-frontend` (port 4903) - React monitoring dashboard ✅ **DEPLOYED**

**Service Layer Architecture (Phase 5):**

VoxBridge 2.0 introduces a service-oriented architecture with 4 core services:

1. **ConversationService** (`src/services/conversation_service.py`, 643 lines)
   - Session management with UUID routing
   - In-memory conversation context caching (15-minute TTL)
   - PostgreSQL persistence for agents/sessions/conversations
   - Background cache cleanup task

2. **STTService** (`src/services/stt_service.py`, 586 lines)
   - WhisperX WebSocket abstraction
   - Per-session connection pooling
   - Auto-reconnect with exponential backoff
   - Async callback system for transcriptions

3. **LLMService** (`src/services/llm_service.py`, 499 lines)
   - Hybrid LLM routing (OpenRouter + Local LLM)
   - Streaming support via async callbacks
   - Fallback chain (OpenRouter → Local)
   - HTTP connection pooling

4. **TTSService** (`src/services/tts_service.py`, 614 lines)
   - Chatterbox TTS abstraction
   - Streaming and buffered synthesis modes
   - Health monitoring and metrics
   - Per-session TTS tracking

**Key Benefits:**
- Multi-user concurrent support (no global speaker lock)
- Connection pooling and resource efficiency
- Database-backed session persistence
- Per-agent LLM provider/model/voice configuration
- 90%+ test coverage
- ~300ms latency reduction per conversation turn

### Memory System Architecture (VoxBridge 2.0 Phase 2)

**Industry-Validated Dual-Table Design:**

VoxBridge uses a **dual-table architecture** for memory management, validated through comparison with Open WebUI (November 2025):

- **user_memories** (Mem0-managed) - Vector embeddings for semantic similarity search
  - Table: `user_memories` (VECTOR(1024) data type via pgvector)
  - Model: BAAI/bge-large-en-v1.5 (1024 dimensions)
  - Purpose: Semantic search ("Find facts similar to 'favorite food'")
  - Managed by: Mem0 framework (automatic CRUD)

- **user_facts** (VoxBridge-managed) - Relational metadata for CRUD operations
  - Table: `user_facts` (PostgreSQL with foreign keys)
  - Fields: fact_key, fact_value, fact_text, importance, validity_start/end, vector_id, memory_bank, last_accessed_at, is_protected, is_summarized, summarized_from
  - Purpose: Frontend display, filtering, sorting, joins
  - Queries: SQL (WHERE, ORDER BY, GROUP BY)

**1:1 Relationship:**
- Each `user_fact` has **exactly ONE** corresponding `user_memory` vector
- Linked via `user_facts.vector_id` → `user_memories.id` (UNIQUE constraint)
- Migration `019` (Nov 23, 2025) restored UNIQUE constraint after incorrect removal

**Why Dual-Table?**
- ✅ Mixing relational + vector operations in one table is inefficient
- ✅ Vector columns don't support SQL indexes (ORDER BY, GROUP BY)
- ✅ Relational columns don't support similarity search
- ✅ Separation allows independent optimization (SQL vs vector)
- ✅ Industry-standard pattern (Open WebUI, LangChain, LlamaIndex all use this)

**Mem0 Framework Benefits:**
- ✅ Automatic fact extraction from conversations (LLM-based)
- ✅ Vector CRUD management (pgvector operations)
- ✅ Relevance filtering ("Does this conversation contain facts?")
- ✅ +26% accuracy improvement over custom RAG implementations
- ✅ Automatic orphan cleanup (syncs vector deletions with metadata)

**Key Features:**
1. **Automatic Extraction**: Queue-based background worker extracts facts from conversations
2. **Temporal Validity**: `validity_start`/`validity_end` for soft deletion and audit trails
3. **Importance Scoring**: 0.0-1.0 scale for fact prioritization (1.0 = critical, 0.0 = trivial)
4. **Complete Cascade Deletion**: When fact is deleted, vector is also deleted (no orphaned data)
5. **Real-time WebSocket Updates**: Frontend receives extraction events (queued → processing → completed)
6. **Memory Banks**: Categorize facts into Personal, Work, General, Relationships, Health, Interests, Events
7. **Pruning Protection**: `is_protected` flag prevents important facts from being pruned
8. **LRU Tracking**: `last_accessed_at` for least-recently-used pruning strategy
9. **Summarization**: Background worker clusters similar old facts and summarizes them via LLM
10. **LLM Optimization**: Preference shortcuts skip LLM for simple "I love X" statements (regex-based)
11. **Deduplication**: Embedding similarity (0.9) + text similarity (0.85) prevents duplicate facts
12. **Error Guards**: Circuit breaker disables extraction after 5 errors in 10min, auto-resets after 5min cooldown

**Documentation:**
- **Architecture Analysis**: [docs/architecture/open-webui-comparison.md](docs/architecture/open-webui-comparison.md) - Comprehensive validation via Open WebUI comparison
- **FAQ**: [docs/faq/memory-system-faq.md](docs/faq/memory-system-faq.md) - 16 Q&A covering all aspects
- **Enhancement Plan**: [docs/planning/memory-system-enhancements.md](docs/planning/memory-system-enhancements.md) - Phase 1-7 implementation plan
- **Migration**: `alembic/versions/20251123_2030_019_restore_vector_id_unique.py` - UNIQUE constraint restoration
- **Sync Script**: `src/database/sync_facts.py` - Re-embed orphaned facts (vector_id IS NULL)

**Common Operations:**
```bash
# Sync orphaned facts (facts with no vectors)
docker exec voxbridge-api python -m src.database.sync_facts

# View memory extraction queue metrics
curl http://localhost:4900/api/metrics/extraction-queue | python3 -m json.tool

# View all facts for a user
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT fact_key, fact_value, importance FROM user_facts WHERE user_id = '<uuid>';"

# Check for orphaned facts (should return 0)
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT COUNT(*) FROM user_facts WHERE vector_id IS NULL;"

# Trigger manual summarization cycle
curl -X POST http://localhost:4900/api/summarization/run | python3 -m json.tool

# View summarized facts
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT fact_key, fact_text, summarized_from FROM user_facts WHERE is_summarized = true;"

# View facts by memory bank
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT memory_bank, COUNT(*) FROM user_facts GROUP BY memory_bank;"
```

**Key Integration Points:**
- Discord → PostgreSQL: Async SQLAlchemy (agent/session storage)
- Discord → Services: ConversationService, STTService, LLMService, TTSService
- Services → WhisperX: WebSocket at `ws://whisperx:4901`
- Services → Chatterbox TTS: HTTP at `http://chatterbox:4800`
- Services → LLM Providers: OpenRouter API, Local LLM (Ollama/vLLM)
- Services → Mem0: Automatic fact extraction and vector management
- Frontend → Discord: WebSocket at `ws://localhost:4900/ws`

## Key Files

### Core Application (Phase 6.4.1 - NEW)

**API Server**:
- **src/api/server.py** (715 lines) - Standalone FastAPI application
  - All HTTP routes (voice, agents, plugins, metrics)
  - WebSocket manager for real-time events
  - Bridge pattern for Discord bot communication
  - Startup/shutdown hooks
- **src/api/__init__.py** (11 lines) - Module exports and bridge initialization

**Discord Bot** (Legacy):
- **src/discord_bot.py** (1,145 lines) - Legacy Discord bot (USE_LEGACY_DISCORD_BOT=true)
  - Reduced from 1,680 lines after FastAPI extraction (Phase 6.4.1 Batch 1)
  - Contains bridge functions for API integration
  - Service layer integration (Phase 5)
  - **⚠️ DEPRECATED** - Will be removed in VoxBridge 3.0

**Plugins** (Phase 6.4.1):
- **src/plugins/discord_plugin.py** (1,706 lines) - NEW Plugin-based Discord bot
  - Complete voice pipeline (AudioReceiver, STT, LLM, TTS)
  - Agent routing with slash commands (`/agent list`, `/agent select`)
  - Resource monitoring integration
  - Bridge pattern registration with API server
- **src/plugins/base.py** (71 lines) - PluginBase abstract class
- **src/plugins/registry.py** (153 lines) - PluginRegistry (singleton pattern)
- **src/services/plugin_manager.py** (621 lines) - PluginManager orchestration

**WhisperX Server**:
- **src/whisper_server.py** (400+ lines) - WhisperX STT server (GPU-accelerated)

### Services (Phase 5)
- **src/services/conversation_service.py** (643 lines) - Session management + caching
- **src/services/stt_service.py** (586 lines) - WhisperX abstraction
- **src/services/llm_service.py** (499 lines) - LLM provider routing
- **src/services/tts_service.py** (614 lines) - Chatterbox abstraction
- **src/services/agent_service.py** (340 lines) - Agent CRUD operations
- **src/services/memory_service.py** (602 lines) - Mem0 integration, fact extraction, queue management (Phase 2)
- **src/services/plugin_manager.py** (621 lines) - Plugin orchestration (Phase 6.4.1)

### Voice Module (Phase 4 + Phase 5)
- **src/voice/webrtc_handler.py** (590 lines) - Refactored to use service layer ✅ (Phase 5)
- **src/voice/__init__.py** (7 lines) - Module initialization

### Database (VoxBridge 2.0)
- **src/database/models.py** (170 lines) - SQLAlchemy ORM models (Agent, Session, Conversation, UserFact, ExtractionTask)
- **src/database/session.py** (140 lines) - Async session management with connection pooling
- **src/database/seed.py** (160 lines) - Example agent seeding script
- **src/database/sync_facts.py** (136 lines) - Re-embed orphaned facts (vector_id IS NULL)
- **alembic/versions/001_initial_schema.py** - Initial database migration
- **alembic/versions/20251123_2030_019_restore_vector_id_unique.py** - Restore UNIQUE constraint on vector_id

### LLM Providers (VoxBridge 2.0 Phase 3)
- **src/llm/base.py** (66 lines) - Abstract LLMProvider class with generate_stream() and health_check()
- **src/llm/types.py** (54 lines) - Pydantic models (LLMMessage, LLMRequest, LLMError, etc.)
- **src/llm/openrouter.py** (262 lines) - OpenRouter.ai provider with SSE streaming
- **src/llm/local_llm.py** (264 lines) - Local LLM provider (Ollama, vLLM, LM Studio)
- **src/llm/factory.py** (110 lines) - LLM provider factory with agent configuration support
- **src/llm/__init__.py** (25 lines) - Package exports

### Frontend

**Core Pages**:
- **frontend/src/App.tsx** - Main dashboard with real-time metrics
- **frontend/src/pages/VoiceChatPage.tsx** - WebRTC voice chat page with real-time transcription
- **frontend/src/pages/AgentsPage.tsx** (280 lines) - Agent management UI (Phase 2)
- **frontend/src/pages/PluginsPage.tsx** (216 lines) - Plugin management UI (Phase 6.4.1 Batch 2b)

**Components**:
- **frontend/src/components/** - UI components (MetricsCard, AudioVisualization, etc.)
- **frontend/src/components/AudioControls.tsx** (100 lines) - Mic button, connection status, pulse animation (Phase 4)
- **frontend/src/components/PluginStatusCard.tsx** (166 lines) - Plugin status display (Phase 6.4.1 Batch 2b)
- **frontend/src/components/DiscordPluginCard.tsx** (370 lines) - Per-agent Discord plugin controls (Phase 6)
- **frontend/src/components/ChannelSelectorModal.tsx** (220 lines) - Guild/channel selector modal (Phase 6)
- **frontend/src/components/TTSTestModal.tsx** - TTS testing modal for Discord plugin (Phase 6)
- **frontend/src/components/AgentCard.tsx** (135 lines) - Agent card with embedded Discord plugin controls (Phase 6)

**Hooks & Services**:
- **frontend/src/hooks/useWebRTCAudio.ts** (344 lines) - Microphone capture, Opus encoding, WebSocket streaming (Phase 4)
- **frontend/src/services/plugins.ts** (103 lines) - Plugin API client (Phase 6.4.1 Batch 2b)

**Types**:
- **frontend/src/types/webrtc.ts** (80 lines) - TypeScript interfaces for WebRTC (Phase 4)

### Configuration
- **docker-compose.yml** - Main orchestration (4 containers: postgres + whisperx + discord + frontend)
- **.env** - Environment variables (not in repo, see .env.example for template)
- **.env.example** - Environment variable template with database config
- **alembic.ini** - Alembic migration configuration
- **src/config/streaming.py** (177 lines) - Streaming configuration with chunking strategies (StreamingConfig dataclass, environment variable loading, runtime overrides)
- **src/config/__init__.py** (15 lines) - Configuration module exports
- **requirements-bot.txt** - Discord bot Python dependencies (includes SQLAlchemy, asyncpg)
- **requirements.txt** - WhisperX server dependencies
- **requirements-test.txt** - Testing dependencies

### Testing
- **tests/unit/** - Unit tests (285 total: 280+ passing)
- **tests/unit/test_streaming_config.py** (307 lines, 25 tests) - Streaming configuration tests
- **tests/unit/test_llm_types.py** (350 lines, 21 tests) - LLM type validation tests
- **tests/unit/test_llm_factory.py** (421 lines, 24 tests) - Factory pattern tests
- **tests/unit/test_openrouter_provider.py** (772 lines, 21 tests) - OpenRouter provider tests
- **tests/unit/test_local_llm_provider.py** (882 lines, 24 tests) - Local LLM provider tests
- **tests/unit/test_webrtc_handler.py** (900 lines, 28 tests) - WebRTC handler tests (Phase 4)
- **tests/unit/services/test_conversation_service.py** (1,128 lines, 25 tests) - ConversationService tests (Phase 5)
- **tests/unit/services/test_stt_service.py** (784 lines, 27 tests) - STTService tests (Phase 5)
- **tests/unit/services/test_llm_service.py** (742 lines, 23 tests) - LLMService tests (Phase 5)
- **tests/unit/services/test_tts_service.py** (735 lines, 24 tests) - TTSService tests (Phase 5)
- **tests/integration/** - Integration tests (mock servers)
- **tests/e2e/** - End-to-end tests (real services)
- **tests/mocks/** - Mock servers (WhisperX, n8n, Chatterbox, Discord)
- **tests/fixtures/** - Test data (audio, transcripts, TTS samples)
- **Coverage**: 90%+ overall, ~88% LLM module coverage, 90%+ services coverage

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

**Discord Bot Mode (Phase 6.4.1 Batch 2a):**
- `USE_LEGACY_DISCORD_BOT` - Toggle between new plugin-based bot (false) and legacy handlers (true)
  - **Default**: `false` (recommended - uses new plugin system)
  - **Legacy Mode**: Set to `true` to re-enable legacy Discord bot handlers
  - **Deprecated**: Legacy mode will be removed in VoxBridge 3.0
  - **Use Case**: Temporary rollback if issues arise with plugin system
  - **Migration Guide**: See [docs/MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md)

**Optional (with defaults):**
- `WHISPER_SERVER_URL=ws://whisperx:4901` - WhisperX WebSocket
- `SILENCE_THRESHOLD_MS=600` - Silence detection (ms)
- `MAX_SPEAKING_TIME_MS=45000` - Max speaking time (45s)
- `USE_STREAMING=true` - Enable streaming responses
- `USE_CLAUSE_SPLITTING=true` - Split on clauses for lower latency
- `USE_THINKING_INDICATORS=true` - Play thinking sound during AI processing
- `THINKING_INDICATOR_PROBABILITY=0.8` - % chance of playing indicator

**Streaming Configuration with Chunking Strategies (TTS Provider Settings):**

These settings can be configured via:
1. **Environment variables** (default values, restored on container restart)
2. **Frontend settings page** (runtime overrides at http://localhost:4903/settings/chatterbox)

- `STREAMING_ENABLED=true` - Enable LLM response streaming (parse responses chunk-by-chunk for lower latency)
- `STREAMING_CHUNKING_STRATEGY=sentence` - How to chunk responses (sentence/paragraph/word/fixed)
- `STREAMING_MIN_CHUNK_LENGTH=10` - Minimum chunk length before TTS synthesis (characters, 5-200)
- `STREAMING_MAX_CONCURRENT_TTS=3` - Maximum concurrent TTS synthesis requests (1-8)
- `STREAMING_ERROR_STRATEGY=retry` - Error handling strategy (skip/retry/fallback)
- `STREAMING_INTERRUPTION_STRATEGY=graceful` - Interruption handling (immediate/graceful/drain)

**Note**: Runtime changes via frontend persist until container restart, then environment defaults are restored.

**WhisperX Configuration:**
- `WHISPERX_MODEL=small` - Model size (tiny, base, small, medium, large-v2)
- `WHISPERX_DEVICE=auto` - Device selection (auto, cuda, cpu)
- `WHISPERX_COMPUTE_TYPE=float16` - Computation type (float16 for GPU, int8 for CPU)
- `WHISPERX_BATCH_SIZE=16` - Batch size for transcription

**Memory Summarization (Phase 3):**

Background worker that clusters semantically similar old facts and summarizes them using an LLM.

- `ENABLE_SUMMARIZATION=true` - Enable/disable summarization
- `SUMMARIZATION_INTERVAL_HOURS=24` - Background worker interval (hours)
- `SUMMARIZATION_MIN_AGE_DAYS=7` - Only summarize facts older than this
- `SUMMARIZATION_MIN_CLUSTER_SIZE=3` - Minimum facts to form a cluster
- `SUMMARIZATION_MAX_CLUSTER_SIZE=8` - Maximum facts per cluster
- `SUMMARIZATION_SIMILARITY_THRESHOLD=0.6` - Embedding similarity threshold (0.0-1.0)
- `SUMMARIZATION_LLM_PROVIDER=local` - LLM provider (local/openrouter)
- `SUMMARIZATION_LLM_MODEL=gpt-oss:20b` - Model for summarization
- `LOCAL_LLM_BASE_URL=http://ollama:11434/v1` - Ollama endpoint on pinkleberry_bridge network

**Manual Trigger:**
```bash
curl -X POST http://localhost:4900/api/summarization/run | python3 -m json.tool
```

## Common Commands

### Database Management (VoxBridge 2.0)
```bash
# Run Alembic migrations
docker exec voxbridge-api alembic upgrade head

# Seed example agents
docker exec voxbridge-api python -m src.database.seed

# Clear all agents (WARNING: Destructive!)
docker exec voxbridge-api python -m src.database.seed --clear

# Check database connection
docker exec voxbridge-api python -c "import asyncio; from src.database import check_db_connection; print(asyncio.run(check_db_connection()))"

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
docker logs voxbridge-api --tail 200 --follow

# View logs (WhisperX only)
docker logs voxbridge-whisperx --tail 200 --follow

# Restart specific service
docker compose restart voxbridge-api

# Rebuild specific service
docker compose up -d --force-recreate --build voxbridge-api
```

**⚠️ CRITICAL: When to REBUILD vs RESTART**

**REBUILD required** (changes are baked into Docker image):
- ✅ **voxbridge-frontend** - Uses Dockerfile COPY for source code
  ```bash
  docker compose build voxbridge-frontend && docker compose up -d voxbridge-frontend
  ```
- ✅ **When Dockerfile changes** (any service)
- ✅ **When dependencies change** (package.json, requirements.txt)

**RESTART sufficient** (changes are volume-mounted):
- ✅ **voxbridge-api** - Source code is volume-mounted at runtime
  ```bash
  docker compose restart voxbridge-api
  ```
- ✅ **Environment variable changes** (in docker-compose.yml)
- ✅ **Configuration file changes** (if volume-mounted)

**Rule of thumb**: If you changed frontend code → REBUILD. If you changed backend code → RESTART.

### Debugging
```bash
# Check health
curl http://localhost:4900/health | python3 -m json.tool

# Check metrics
curl http://localhost:4900/metrics | python3 -m json.tool

# View latency logs
docker logs voxbridge-api --tail 200 | grep -E "(LATENCY|⏱️)"

# View streaming logs
docker logs voxbridge-api --tail 300 | grep -E "(🌊|streaming|chunk|sentence)"

# View thinking indicator logs
docker logs voxbridge-api --tail 200 | grep -E "(💭|thinking indicator|🎵)"

# View memory extraction queue logs
docker logs voxbridge-api --tail 200 | grep -E "(🧠|🧵|memory|extraction)"

# Check memory extraction queue metrics
curl http://localhost:4900/api/metrics/extraction-queue | python3 -m json.tool
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

## Memory Queue Patterns

### ThreadPoolExecutor for Blocking Operations

VoxBridge uses ThreadPoolExecutor to prevent event loop blocking when calling Mem0's synchronous APIs.

**Problem**: Mem0's `memory.add()` uses `concurrent.futures.wait()` which blocks the async event loop for ~56 seconds during fact extraction (35s LLM + 20s embeddings + 1s storage).

**Solution**: Wrap blocking Mem0 calls with `loop.run_in_executor()` to run them in a thread pool:

```python
# In MemoryService.__init__
self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mem0_extraction")

# When calling blocking Mem0 methods
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(
    self.executor,
    lambda: self.memory.add(messages=[...], user_id=...)
)
```

**Key Implementation Points**:
- ThreadPoolExecutor initialized in `src/services/memory_service.py` (lines 90-94)
- Used in automatic extraction: `_extract_facts_from_turn()` (lines 269-278)
- Used in manual fact creation: `src/routes/memory_routes.py` (lines 250-259)
- Cleanup via `__del__()` method (lines 597-602)

### WebSocket Real-Time Notifications

Memory extraction events are broadcast via WebSocket for real-time UI updates:

**Events**:
- `memory_extraction_queued` - Task added to queue
- `memory_extraction_processing` - Processing started
- `memory_extraction_completed` - Successfully completed (includes `facts_count`)
- `memory_extraction_failed` - Failed or retrying (includes `error`, `attempts`)

**Frontend Integration**:
```typescript
// In MemoryPage.tsx
useMemoryExtractionStatus({
  onCompleted: (task) => {
    toast.success(`Extracted ${task.facts_count} facts`);
    queryClient.invalidateQueries({ queryKey: ['facts', userId] });
  },
  onFailed: (task) => {
    toast.error(task.error || 'Extraction failed');
  }
});
```

**Files**:
- Backend: `src/services/memory_service.py` (broadcasting logic)
- Frontend: `frontend/src/hooks/useMemoryExtractionStatus.ts` (WebSocket subscription)

### Queue Metrics & Observability

**Metrics Endpoint**: `GET /api/metrics/extraction-queue`

Returns:
```json
{
  "pending": 5,
  "processing": 2,
  "completed": 142,
  "failed": 3,
  "avg_duration_sec": 58.3,
  "oldest_pending_age_sec": 12.5
}
```

**Periodic Logging**: Queue worker logs metrics every 60 seconds (every 12 iterations of 5-second polling):
```
🧠 Memory extraction queue metrics: 3 tasks processed this batch
```

### Troubleshooting Memory Extraction

**Issue**: Facts not being extracted
1. Check queue status: `curl http://localhost:4900/api/metrics/extraction-queue`
2. View extraction logs: `docker logs voxbridge-api | grep -E "🧠|🧵"`
3. Verify MemoryService initialized: Look for "✅ MemoryService initialized" in startup logs
4. Check database connectivity: `docker exec voxbridge-postgres psql -U voxbridge -c "SELECT COUNT(*) FROM extraction_tasks;"`

**Issue**: Event loop blocking (heartbeat failures)
- If you see "heartbeat blocked for more than 20 seconds", verify ThreadPoolExecutor is being used
- Check `src/services/memory_service.py` lines 269-278 for `run_in_executor()` wrapper
- Check `src/routes/memory_routes.py` lines 250-259 for manual creation wrapper

**Issue**: WebSocket notifications not appearing
1. Check WebSocket connection: Frontend should show "🔌 WebSocket client connected"
2. Verify `ws_manager` connected to `memory_service` (server.py:1216-1217)
3. Check browser console for WebSocket errors
4. Verify WebSocket URL: `ws://localhost:4900/ws/events`

## API Endpoints

### Voice Control
- **POST /voice/join** - Join voice channel (`{channelId, guildId}`)
- **POST /voice/leave** - Leave voice channel
- **POST /voice/speak** - Speak text via TTS (`{text}` or `{output, options}`)

### Agent Management (VoxBridge 2.0)
- **GET /api/agents** - List all AI agents
- **GET /api/agents/{id}** - Get specific agent by UUID
- **POST /api/agents** - Create new agent (`{name, system_prompt, temperature?, llm_provider?, llm_model?, tts_voice?, tts_exaggeration?, tts_cfg_weight?, tts_temperature?, tts_language?, use_n8n?, plugins?}`)
- **PUT /api/agents/{id}** - Update agent (partial update, all fields optional)
- **DELETE /api/agents/{id}** - Delete agent (cascades to sessions/conversations)

### Discord Plugin (Phase 6)
- **GET /api/plugins/discord/voice/status/{agent_id}** - Get per-agent Discord voice status
- **POST /api/plugins/discord/voice/join** - Join voice channel (`{agent_id, channel_id, guild_id}`)
- **POST /api/plugins/discord/voice/leave** - Leave voice channel (`{agent_id, guild_id}`)
- **GET /api/channels** - List available Discord guilds and voice channels

### Monitoring
- **GET /health** - Health check (bot ready, in voice, speaker status)
- **GET /status** - Detailed status (bot, voice, whisper, services)
- **GET /metrics** - Performance metrics (latency, durations, samples)
- **GET /api/streaming-config** - Get global streaming configuration with chunking strategies (runtime overrides or environment defaults)
- **PUT /api/streaming-config** - Update streaming configuration at runtime (`{enabled?, chunking_strategy?, min_chunk_length?, max_concurrent_tts?, error_strategy?, interruption_strategy?}`)
- **POST /api/streaming-config/reset** - Reset streaming configuration to environment variable defaults
- **GET /api/system-settings/embedding-model-status** - Get embedding model cache status (download status, size, file count)
- **GET /api/channels** - Available Discord channels
- **WS /ws** - WebSocket for real-time events

### WebRTC Voice (Phase 4)
- **WS /ws/voice** - WebSocket for browser voice chat (Opus/WebM audio streaming)

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

### Architecture & Patterns
- **[AGENTS.md](./AGENTS.md)** - Comprehensive architecture, patterns, and guidelines (637 lines)
- **[README.md](./README.md)** - User-facing documentation and setup guide (671 lines)
- **[docs/architecture/open-webui-comparison.md](docs/architecture/open-webui-comparison.md)** - Memory architecture validation (31KB, Open WebUI comparison)
- **[docs/faq/memory-system-faq.md](docs/faq/memory-system-faq.md)** - Memory system FAQ (16 Q&A)

### Testing
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
