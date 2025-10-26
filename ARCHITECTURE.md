# VoxBridge Architecture Documentation

Quick navigation to comprehensive architecture and planning documents.

---

## 🏗️ Architecture Plans

### Multi-Agent System Implementation

**Status**: 🟡 In Progress (Phase 1-2)
**Document**: [docs/architecture/multi-agent-implementation-plan.md](docs/architecture/multi-agent-implementation-plan.md)
**Effort**: 8-12 development days

**Summary**: 7-phase architectural refactor to transform VoxBridge from single-speaker to multi-agent concurrent system.

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

**Status**: 🟢 Active Development
**Document**: [docs/planning/frontend-langgraph-plan.md](docs/planning/frontend-langgraph-plan.md)
**Progress**: [docs/progress/frontend-progress.md](docs/progress/frontend-progress.md)

**Summary**: Web frontend for VoxBridge with Chatterbox-inspired styling, plus LangChain/LangGraph-based agent system as alternative to n8n webhooks.

**Tech Stack**:
- **Frontend**: React 19 + TypeScript + Vite
- **Styling**: Tailwind CSS v4 + shadcn/ui (New York style)
- **Real-time**: WebSocket + Server-Sent Events
- **Agent Framework**: LangChain/LangGraph (Python)

**Progress**:
- ✅ Frontend foundation complete (20+ files, 1500+ LOC)
- ✅ UI component library (11 shadcn components)
- ✅ API client with type safety
- ✅ WebSocket real-time updates
- ✅ Dark mode Chatterbox aesthetic
- ⏳ Backend API endpoints pending
- ⏳ LangGraph agent system pending

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
- **tests/TEST_RESULTS.md** - Coverage report (70%, 86 unit tests)

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

## 🎯 Current Implementation Priorities

1. **Multi-Agent Refactor** (8-12 days)
   - Phase 1: Session Management (PostgreSQL + Redis) - **In Progress**
   - Phase 2: Queue-Based Concurrency - **In Progress**
   - Phases 3-7: Agent routing, payloads, UI, config, infrastructure

2. **Frontend Development** (Active)
   - Backend API endpoints - **Next**
   - WebSocket event emissions - **Next**
   - Channel selector + TTS testing
   - Docker deployment

3. **LangGraph Integration** (Planned)
   - LangChain/LangGraph agent framework
   - Alternative to n8n webhooks
   - Multi-agent orchestration

---

**Last Updated**: October 26, 2025
**Maintained By**: VoxBridge Development Team
