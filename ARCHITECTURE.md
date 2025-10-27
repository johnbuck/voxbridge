# VoxBridge Architecture Documentation

Quick navigation to comprehensive architecture and planning documents.

---

## 🎯 Current Implementation Status

**Last Updated**: October 27, 2025

### ✅ Fully Implemented Features

**Frontend Dashboard** (Port 4903):
- ✅ React 19 + TypeScript + Vite production deployment
- ✅ 4 pages: VoxBridge, Discord Bot, WhisperX, Chatterbox TTS
- ✅ Real-time monitoring via WebSocket (`/ws/events`)
- ✅ Dark mode with Chatterbox-inspired styling (shadcn/ui)
- ✅ Connection status indicators for all services
- ✅ Live transcription display with active speaker tracking

**Backend API** (Port 4900):
- ✅ Voice control: `/voice/join`, `/voice/leave`, `/voice/speak`
- ✅ Monitoring: `/health`, `/status`, `/api/metrics`
- ✅ Data access: `/api/channels`, `/api/transcripts`
- ✅ Configuration: `/api/config`, `/api/tts/config`
- ✅ Speaker management: `/api/speaker/unlock`
- ✅ Real-time events: WebSocket `/ws/events`

**STT/TTS Pipeline**:
- ✅ WhisperX speech-to-text (GPU-accelerated, RTX 5060 Ti)
- ✅ Chatterbox TTS integration with error handling
- ✅ Streaming responses with clause splitting for low latency
- ✅ Parallel TTS generation (optional)
- ✅ Thinking indicator sound with duration tracking
- ✅ Active speaker UX indicators
- ✅ AI generation status indicators

**Performance & Reliability**:
- ✅ E2E latency benchmark framework
- ✅ Comprehensive metrics tracking (latency, duration, counts)
- ✅ TTS error handling with automatic retry
- ✅ Graceful degradation and failover
- ✅ HTTP retry logic with exponential backoff

**Testing Infrastructure**:
- ✅ 43 total tests (38 passing, 5 failing speaker_manager tests)
- ✅ 88% code coverage (38/43 passing rate)
- ✅ Unit tests (fully mocked, fast)
- ✅ Integration tests (mock servers)
- ✅ E2E tests (real services)
- ✅ Test runner wrapper script (`./test.sh`)

**Deployment**:
- ✅ Docker Compose orchestration (3 containers)
- ✅ GPU support for WhisperX (NVIDIA runtime)
- ✅ Health checks for all services
- ✅ Volume management with bind mounts
- ✅ Network isolation (bot-network, pinkleberry_bridge)

### 🟡 In Progress (VoxBridge 2.0)

**Phase 1: Core Infrastructure** ✅ **COMPLETE** (Oct 26, 2025):
- ✅ PostgreSQL 15 database (docker-compose.yml)
- ✅ SQLAlchemy ORM models (Agent, Session, Conversation)
- ✅ Alembic migrations (async PostgreSQL support)
- ✅ Database seed script (3 example agents)

**Phase 2: Agent Management System** ✅ **COMPLETE** (Oct 27, 2025):
- ✅ Full CRUD API for agents (`/api/agents`)
- ✅ AgentService with async database operations
- ✅ Dedicated AgentsPage UI at `/agents` route
- ✅ AgentCard and AgentForm components
- ✅ Real-time WebSocket updates for agent changes
- ✅ Navigation integration (Brain icon in header)
- ✅ Support for multiple LLM providers (OpenRouter, Local)

**Upcoming Phases**:
- ⏳ Phase 3: LLM Provider abstraction (OpenRouter + Local LLM)
- ⏳ Phase 4: Web Voice Interface (WebRTC browser chat)
- ⏳ Phase 5: Core Refactor (decouple from Discord, session-based routing)
- ⏳ Phase 6: Extension System (Discord + n8n as plugins)
- ⏳ Phase 7: Documentation Overhaul (rewrite all docs)
- ⏳ Phase 8: Testing & Migration (update test suite)

### 🔴 Not Yet Implemented (Post-VoxBridge 2.0)

**LangGraph Integration**:
- ❌ LangChain/LangGraph agent framework
- ❌ Alternative to n8n webhooks
- ❌ Multi-agent orchestration

---

## 🏗️ Architecture Plans

### Multi-Agent System Implementation

**Status**: 🔴 **NOT STARTED** (Future Work)
**Document**: [docs/architecture/multi-agent-implementation-plan.md](docs/architecture/multi-agent-implementation-plan.md)
**Effort**: 8-12 development days

**Summary**: Planned 7-phase architectural refactor to transform VoxBridge from single-speaker to multi-agent concurrent system.

**Key Changes**:
- **Phase 1**: Session Management (PostgreSQL + Redis)
- **Phase 2**: Queue-Based Concurrency (replace speaker lock)
- **Phase 3**: Agent Routing Service (multi-agent support)
- **Phase 4**: Enhanced Webhook Payload (conversation context)
- **Phase 5**: User Agent Selection (Discord slash commands)
- **Phase 6**: Runtime Configuration (agent management)
- **Phase 7**: Infrastructure Updates (Docker Compose)

**Current Blockers**:
- ❌ Global speaker lock (only 1 user at a time)
- ❌ Single static webhook URL
- ❌ No session/conversation tracking
- ❌ No persistent storage

**After Refactor**:
- ✅ Multiple users speaking simultaneously (queue-based)
- ✅ Multiple n8n agents running in parallel
- ✅ Conversation context preserved across turns
- ✅ User preference for agent selection

---

### Frontend + LangGraph Agent System

**Status**: ✅ **Frontend COMPLETE** | 🔴 LangGraph NOT STARTED
**Document**: [docs/planning/frontend-langgraph-plan.md](docs/planning/frontend-langgraph-plan.md)
**Progress**: [docs/progress/frontend-progress.md](docs/progress/frontend-progress.md)

**Summary**: Web frontend for VoxBridge with Chatterbox-inspired styling. LangChain/LangGraph agent system planned as alternative to n8n webhooks.

**Tech Stack**:
- **Frontend**: React 19 + TypeScript + Vite ✅ **DEPLOYED**
- **Styling**: Tailwind CSS v4 + shadcn/ui (New York style) ✅
- **Real-time**: WebSocket + Server-Sent Events ✅
- **Agent Framework**: LangChain/LangGraph (Python) 🔴 **Not Started**

**Frontend Completion**:
- ✅ Production deployment on port 4903
- ✅ 4 pages with full functionality (VoxBridge, Discord Bot, WhisperX, Chatterbox TTS)
- ✅ Backend API fully implemented (all 11+ endpoints)
- ✅ WebSocket real-time events
- ✅ Dark mode Chatterbox aesthetic
- ✅ Monitoring dashboard with metrics
- 🔴 LangGraph agent system not yet started

---

## 📊 Progress Tracking

### Frontend Development Progress
**Document**: [docs/progress/frontend-progress.md](docs/progress/frontend-progress.md)

**Latest Update**: Frontend foundation complete ✅

**Completed**:
- React 19 + Vite + TypeScript project
- Chatterbox theme integration
- 11 UI components (shadcn/ui)
- API client + WebSocket hook
- Main dashboard with monitoring
- Connection status indicators
- Live transcription display

**Next Steps**:
- Backend API endpoints (`/api/channels`, `/api/transcripts`, `/api/metrics`)
- WebSocket event emissions
- Channel selector component
- TTS testing interface
- Docker deployment

---

## 🔍 Analysis Documents

### n8n Webhooks & Sessions Analysis
**Document**: [ANALYSIS_n8n_WEBHOOKS_SESSIONS.md](ANALYSIS_n8n_WEBHOOKS_SESSIONS.md)

**Summary**: Detailed analysis of current VoxBridge architecture constraints and blockers for multi-agent support.

**Key Findings**:
- Single-speaker, single-agent system by design
- Global speaker lock prevents concurrent processing
- No session management or conversation history
- Static webhook URL limits routing capabilities
- Singleton architecture prevents scaling

**Conclusion**: Multi-agent support requires core architectural changes (covered in multi-agent implementation plan).

---

## 📚 Additional Resources

### Quick References
- **CLAUDE.md** - Quick reference guide for Claude Code
- **AGENTS.md** - Comprehensive documentation for AI agents
- **README.md** - User-facing setup and usage guide

### Testing
- **tests/README.md** - Testing framework guide
- **tests/TESTING_FRAMEWORK_SUMMARY.md** - Architecture overview
- **tests/INTEGRATION_TEST_SUMMARY.md** - Integration test results
- **tests/TEST_RESULTS.md** - Coverage report (88%, 43 tests: 38 passing, 5 failing)

---

## 🗺️ Documentation Map

```
voxbridge/
├── ARCHITECTURE.md                  # 👈 You are here
├── CLAUDE.md                        # Quick reference for Claude Code
├── AGENTS.md                        # Comprehensive agent documentation
├── README.md                        # User guide
├── ANALYSIS_n8n_WEBHOOKS_SESSIONS.md # Current architecture analysis
│
├── docs/
│   ├── architecture/                # Permanent architecture plans
│   │   └── multi-agent-implementation-plan.md (2223 lines, 7 phases)
│   │
│   ├── planning/                    # Active development plans
│   │   └── frontend-langgraph-plan.md (Frontend + LangGraph)
│   │
│   └── progress/                    # Progress tracking
│       └── frontend-progress.md (Frontend development status)
│
├── tests/                           # Test suite documentation
│   ├── README.md
│   ├── TESTING_FRAMEWORK_SUMMARY.md
│   ├── INTEGRATION_TEST_SUMMARY.md
│   └── TEST_RESULTS.md
│
└── src/                             # Source code
    ├── discord_bot.py
    ├── speaker_manager.py
    ├── streaming_handler.py
    ├── whisper_client.py
    └── whisper_server.py
```

---

## 🗺️ Project Roadmap

### 📚 Planning Documents (Detailed Architecture Plans)

We have **three comprehensive planning documents** totaling over 4,000 lines of detailed architecture:

1. **[VoxBridge 2.0 Transformation Plan](docs/architecture/voxbridge-2.0-transformation-plan.md)** - **NEW** 🆕
   - **Scope**: Complete architectural transformation (14-16 days)
   - **Focus**: Standalone modular platform with web interface + optional extensions
   - **Status**: 🟡 Planning Complete - Ready for Implementation

2. **[Multi-Agent Implementation Plan](docs/architecture/multi-agent-implementation-plan.md)** - **INCORPORATED** ✅
   - **Scope**: 7-phase multi-agent system (2,222 lines, 8-12 days)
   - **Focus**: PostgreSQL + Redis, session management, agent routing, queue concurrency
   - **Status**: **Core phases incorporated into VoxBridge 2.0**

3. **[Frontend + LangGraph Plan](docs/planning/frontend-langgraph-plan.md)** - **INCORPORATED** ✅
   - **Scope**: LangGraph agent system design (948 lines)
   - **Focus**: LangChain/LangGraph integration, agent orchestration
   - **Status**: **LLM abstraction in VoxBridge 2.0 enables future LangGraph integration**

### 🔄 How VoxBridge 2.0 Incorporates Existing Plans

**VoxBridge 2.0 = Multi-Agent Plan + Strategic Expansion**

| Multi-Agent Phase | VoxBridge 2.0 Phase | Enhancement |
|-------------------|---------------------|-------------|
| Phase 1: Session Management (PostgreSQL + Redis) | Phase 1: Infrastructure | ✅ Same - PostgreSQL for agents/sessions |
| Phase 2: Queue Concurrency | Phase 5: Core Refactor | ✅ Expanded - Session-based routing (not just queue) |
| Phase 3: Agent Routing | Phase 2: Agent Management + Phase 3: LLM Providers | ✅ Expanded - Full LLM abstraction (OpenRouter/Local) |
| Phase 4: Enhanced Payload | Phase 5: Core Refactor | ✅ Incorporated - Conversation context |
| Phase 5: User Selection | Phase 2: Agent Management (Frontend UI) | ✅ Enhanced - Web UI instead of Discord commands |
| Phase 6: Configuration | Phase 2: Agent Management | ✅ Enhanced - Full CRUD UI for agents |
| Phase 7: Infrastructure | Phase 1 + Phase 6: Extensions | ✅ Expanded - Plus extension system |
| *(Not in multi-agent plan)* | **Phase 4: Web Voice Interface** | 🆕 **NEW** - Browser-based voice (WebRTC) |
| *(Not in multi-agent plan)* | **Phase 6: Extension System** | 🆕 **NEW** - Discord/n8n as plugins |

**Key Insight**: VoxBridge 2.0 **builds on** the multi-agent plan by:
- ✅ Keeping the database/session architecture (Phases 1-4)
- ✅ Expanding agent management with UI and LLM flexibility
- 🆕 Adding standalone web interface (not Discord-dependent)
- 🆕 Making Discord/n8n optional extensions (not core)

---

### ✅ VoxBridge 1.0 - Completed (October 2025)

**Current Production System:**
1. **Frontend Dashboard** - React 19 + TypeScript + Vite, deployed on port 4903
2. **Backend API** - All 11+ endpoints implemented and operational
3. **STT/TTS Pipeline** - WhisperX + Chatterbox with streaming optimizations
4. **Performance Features** - Thinking indicators, active speaker UX, clause splitting
5. **Testing Infrastructure** - 43 tests with 88% coverage
6. **E2E Benchmarking** - Latency tracking and metrics framework

**Architecture**: Discord-centric bot with single-speaker lock

---

### 🚀 VoxBridge 2.0 - In Progress (Oct-Nov 2025)

**Status**: 🟢 **Phase 1 COMPLETE** - Implementation Started
**Branch**: `voxbridge-2.0`
**Effort**: 14-16 days (est. completion: Nov 11, 2025)
**Complete Plan**: [docs/architecture/voxbridge-2.0-transformation-plan.md](docs/architecture/voxbridge-2.0-transformation-plan.md)

**Strategic Transformation**: Discord bot → Standalone modular AI voice platform

**8 Implementation Phases**:
1. **Core Infrastructure** ✅ **COMPLETE** (Oct 26, 2025)
   - PostgreSQL 15 service in docker-compose.yml
   - SQLAlchemy 2.0 ORM models (Agent, Session, Conversation)
   - Alembic migrations with async PostgreSQL support
   - Database seed script with 3 example agents
   - UUID primary keys, env-based API keys, PostgreSQL-only (Redis deferred)
2. **Agent Management** (2 days) - CRUD API + UI for agent configuration
3. **LLM Providers** (2 days) - OpenRouter + Local LLM abstraction
4. **Web Voice Interface** (2-3 days) - WebRTC browser voice chat
5. **Core Refactor** (2-3 days) - Decouple from Discord, session-based routing
6. **Extension System** (2 days) - Discord + n8n as optional plugins
7. **Documentation Overhaul** (1 day) - Rewrite all docs for new architecture
8. **Testing & Migration** (1 day) - Update test suite, verify functionality

**New Capabilities**:
- ✨ Standalone web voice chat (no Discord required)
- ✨ Multi-agent support with PostgreSQL storage
- ✨ Configurable LLMs (OpenRouter or local)
- ✨ Frontend agent management UI
- ✨ Extension system (Discord/n8n optional)
- ✨ Session-based concurrent conversations

---

### 🔮 Future Considerations (Post-2.0)

1. **LangGraph Full Integration**
   - Implement LangChain/LangGraph framework
   - Advanced agent orchestration
   - Tool use and function calling
   - **Note**: LLM abstraction in v2.0 prepares for this

2. **Authentication & Multi-User**
   - User accounts and permissions
   - Agent sharing marketplace
   - Multi-tenant support

3. **Mobile & Advanced Features**
   - Native mobile apps
   - Voice cloning
   - Real-time translation
   - Multi-language support

---

**Last Updated**: October 26, 2025
**Maintained By**: VoxBridge Development Team
