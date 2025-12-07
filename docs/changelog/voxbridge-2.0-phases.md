# VoxBridge 2.0 Changelog

**Completed**: November 2025
**Branch**: `voxbridge-2.0`
**Plan**: [docs/architecture/voxbridge-2.0-transformation-plan.md](../architecture/voxbridge-2.0-transformation-plan.md)

---

## Phase Summary

| Phase | Description | Status | Date |
|-------|-------------|--------|------|
| Phase 1 | Core Infrastructure | Complete | Oct 2025 |
| Phase 2 | Agent Management System | Complete | Oct 2025 |
| Phase 3 | LLM Provider Abstraction | Complete | Oct 2025 |
| Phase 4 | Web Voice Interface | Complete | Nov 2025 |
| Phase 5 | Core Voice Pipeline Refactor | Complete | Oct 28, 2025 |
| Phase 6 | Discord Plugin Integration | Complete | Nov 2025 |

---

## Phase 1: Core Infrastructure

**Status**: Complete (October 2025)

- PostgreSQL 15 database for agents, sessions, conversations
- SQLAlchemy 2.0 ORM models with UUID primary keys
- Alembic migrations (async PostgreSQL)
- Database seed script (3 example agents)

---

## Phase 2: Agent Management System

**Status**: Complete (October 2025)

- Full CRUD API for AI agents (`/api/agents`)
- Dedicated AgentsPage at `/agents` route
- Real-time WebSocket updates for agent changes
- Support for multiple LLM providers (OpenRouter, Local)

---

## Phase 3: LLM Provider Abstraction

**Status**: Complete (October 2025)

- Abstract LLM provider interface with streaming support
- OpenRouter.ai provider (SSE streaming)
- Local LLM provider (Ollama, vLLM, LM Studio)
- LLM provider factory with agent configuration
- Hybrid n8n mode (webhooks + direct LLM)
- 90 unit tests with ~88% coverage

---

## Phase 4: Web Voice Interface

**Status**: Complete (November 2025)

- Backend WebSocket handler (`/ws/voice` endpoint)
- Opus audio decoding, WhisperX integration
- LLM provider routing (OpenRouter/Local/n8n)
- Frontend WebRTC hook (useWebRTCAudio)
- Audio capture UI (AudioControls component)
- Real-time transcription + AI response display
- 45 tests (28 WebRTC + 17 integration/E2E, 100% passing, 90%+ coverage)

### Critical WebRTC Fixes (Nov 5-7, 2025)

**Branch**: `feature/sentence-level-streaming`
**Summary**: [docs/WEBRTC_FIXES_SESSION_SUMMARY.md](../WEBRTC_FIXES_SESSION_SUMMARY.md)
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

---

## Phase 5: Core Voice Pipeline Refactor

**Status**: Complete (October 28, 2025)

- 4 new services (2,342 lines): ConversationService, STTService, LLMService, TTSService
- Refactored WebRTC handler + Discord bot to use service layer
- Deleted old files: speaker_manager.py, whisper_client.py, streaming_handler.py
- Net code reduction: -272 lines (22% smaller)
- 99 unit tests with 90%+ coverage
- ~300ms latency reduction per conversation turn

---

## Phase 6: Discord Plugin Integration

**Status**: Complete (November 2025)

- Per-agent Discord bot plugin system
- Plugin-based voice control endpoints (`/api/plugins/discord/voice/*`)
- Discord snowflake ID precision preservation (manual JSON serialization)
- Per-agent Discord status tracking (`/api/plugins/discord/voice/status/{agent_id}`)
- Channel selector modal with guild/channel browsing
- Auto-reconnect logic for state desync handling
- localStorage persistence for guild IDs across page reloads
- Responsive two-row layout for Discord plugin cards
- TTS test modal for agent-specific voice testing

---

## Implemented Features Summary

### Frontend Dashboard (Port 4903)
- React 19 + TypeScript + Vite production deployment
- 4 pages: VoxBridge, Discord Bot, WhisperX, Chatterbox TTS
- Real-time WebSocket monitoring (`/ws/events`)
- Dark mode with Chatterbox styling

### Agent Management UI
- Dedicated AgentsPage at `/agents` route
- Agent CRUD operations (create, edit, delete)
- Real-time updates via WebSocket
- Agent cards with provider badges
- Form validation for all agent fields

### Backend API (Port 4900)
- All 11+ endpoints operational (voice, monitoring, config)
- WebSocket real-time events
- Health checks and metrics

### Performance Features
- Thinking indicator with sound + duration tracking
- Active speaker UX indicators
- Streaming optimizations (clause splitting, parallel TTS)
- E2E latency benchmark framework
- TTS error handling with retry logic

---

## Test Coverage

**Testing** (Updated Nov 2025): 99 tests (99 passing, 0 failing), 90%+ coverage

Includes:
- 45 WebRTC tests (28 WebRTC + 17 integration/E2E)
- 90 unit tests with ~88% LLM module coverage
- 90%+ services coverage

---

## Related Planning Documents

1. **Multi-Agent System** - [docs/architecture/multi-agent-implementation-plan.md](../architecture/multi-agent-implementation-plan.md)
   - Summary: 7-phase refactor (session mgmt, queue concurrency, agent routing)
   - Status: Core phases incorporated into VoxBridge 2.0
   - Effort: 2,222 lines of detailed planning

2. **LangGraph Integration** - [docs/planning/frontend-langgraph-plan.md](../planning/frontend-langgraph-plan.md)
   - Summary: LangChain/LangGraph as alternative to n8n webhooks
   - Status: Future work (post-VoxBridge 2.0)
   - Goal: Multi-agent orchestration
