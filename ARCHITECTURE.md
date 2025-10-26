# VoxBridge Architecture Documentation

Quick navigation to comprehensive architecture and planning documents.

---

## 🎯 Current Implementation Status

**Last Updated**: October 26, 2025

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

### 🔴 Not Yet Implemented (Future Plans)

**Multi-Agent System**:
- ❌ Session management (PostgreSQL + Redis)
- ❌ Queue-based concurrency (still single-speaker lock)
- ❌ Agent routing service
- ❌ Conversation context/history
- ❌ User agent selection (Discord slash commands)

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

### ✅ Completed (October 2025)
1. **Frontend Dashboard** - React 19 + TypeScript + Vite, deployed on port 4903
2. **Backend API** - All 11+ endpoints implemented and operational
3. **STT/TTS Pipeline** - WhisperX + Chatterbox with streaming optimizations
4. **Performance Features** - Thinking indicators, active speaker UX, clause splitting
5. **Testing Infrastructure** - 43 tests with 88% coverage
6. **E2E Benchmarking** - Latency tracking and metrics framework

### 🔴 Future Work (Not Started)

1. **Multi-Agent System** (8-12 days effort)
   - Phase 1: Session Management (PostgreSQL + Redis)
   - Phase 2: Queue-Based Concurrency (replace single-speaker lock)
   - Phase 3: Agent Routing Service (multi-agent support)
   - Phase 4: Enhanced Webhook Payload (conversation context)
   - Phase 5: User Agent Selection (Discord slash commands)
   - Phase 6: Runtime Configuration (agent management)
   - Phase 7: Infrastructure Updates (Docker Compose)

2. **LangGraph Agent System** (TBD)
   - LangChain/LangGraph framework integration
   - Alternative to n8n webhooks
   - Multi-agent orchestration capabilities

3. **Test Coverage Improvements** (Ongoing)
   - Fix 5 failing speaker_manager tests
   - Increase coverage from 88% to 90%+
   - Add more integration test scenarios

---

**Last Updated**: October 26, 2025
**Maintained By**: VoxBridge Development Team
