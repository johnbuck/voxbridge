# VoxBridge Architecture Documentation

Quick navigation to comprehensive architecture and planning documents.

---

## 🎯 Current Implementation Status

**Last Updated**: October 28, 2025

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
- ✅ 71 total tests (66 passing, 5 failing speaker_manager tests)
- ✅ 88% code coverage overall
- ✅ Unit tests (fully mocked, fast) - includes 28 WebRTC tests
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

**Phase 3: LLM Provider Abstraction** ✅ **COMPLETE** (Oct 27, 2025):
- ✅ Abstract LLM provider interface (`src/llm/base.py`)
- ✅ OpenRouter.ai provider with SSE streaming (`src/llm/openrouter.py`)
- ✅ Local LLM provider - OpenAI-compatible (`src/llm/local_llm.py`)
- ✅ LLM provider factory with agent configuration support (`src/llm/factory.py`)
- ✅ Hybrid n8n mode (support both webhooks and direct LLM)
- ✅ Comprehensive error handling (timeout, rate limit, connection, auth)
- ✅ 90 unit tests with ~88% coverage of LLM module

**Phase 4: Web Voice Interface** ✅ **COMPLETE** (Oct 27, 2025):
- ✅ Backend WebSocket handler (`/ws/voice` endpoint)
- ✅ Opus audio decoding (opuslib)
- ✅ WhisperX streaming integration
- ✅ LLM provider routing (OpenRouter/Local/n8n)
- ✅ Database persistence (conversations table)
- ✅ Frontend WebRTC hook (useWebRTCAudio)
- ✅ Audio capture UI (AudioControls component)
- ✅ Real-time transcription display
- ✅ Streaming AI response visualization
- ✅ 28 unit tests (all passing)
- ✅ Comprehensive documentation (1,730+ lines)

**Phase 5: Core Voice Pipeline Refactor** ✅ **COMPLETE** (Oct 28, 2025):
- ✅ Service layer architecture (4 services, 2,342 lines)
  - ConversationService (643 lines) - Session management + caching
  - STTService (586 lines) - WhisperX abstraction
  - LLMService (499 lines) - LLM provider routing
  - TTSService (614 lines) - Chatterbox abstraction
- ✅ Refactored WebRTC handler to use service layer (590 lines)
- ✅ Refactored Discord bot to use service layer (1,031 lines)
- ✅ Deleted legacy files (speaker_manager.py, whisper_client.py, streaming_handler.py)
- ✅ 99 unit tests with 90%+ coverage
- ✅ ~300ms latency reduction per conversation turn
- ✅ Net code reduction: -272 lines (22% smaller)

**Phase 6: Extension System** ✅ **Phase 6.4.1 COMPLETE** (Oct 28, 2025):
- ✅ **Batch 1: FastAPI Decoupling** - Extracted FastAPI server to `src/api/server.py` (715 lines)
- ✅ **Batch 2a: Bot Deprecation** - Added `USE_LEGACY_DISCORD_BOT` toggle for rollback support
- ✅ **Batch 2b: Frontend Plugin UI** - Plugin Management page (485 lines, 3 files)
- ✅ **Batch 3: Agent Routing** - Discord slash commands (`/agent list`, `/agent select`)
- ✅ **Batch 4: Comprehensive Testing** - 76 tests (100% passing), 49% API coverage
- ✅ **Batch 5: Migration Documentation** - Complete migration guide + docs updates

**Upcoming Phases**:
- ⏳ Phase 6 (Remaining): n8n plugin, dynamic plugin loading, plugin marketplace
- ⏳ Phase 7: Documentation Overhaul (rewrite all docs)
- ⏳ Phase 8: Testing & Migration (update test suite)

### 📐 Phase 6.4.1: Discord Plugin Voice Integration - Architecture Details

**Status**: ✅ **COMPLETE** (October 28, 2025)
**Duration**: 5 batches across 2 days

#### Architecture Evolution

**Old Architecture** (VoxBridge 1.x - Monolithic):
```
discord_bot.py (1,680 lines)
├── FastAPI server (routes, WebSocket)
├── Discord bot (client, events, voice)
├── Voice handlers (join, leave, speak)
├── Metrics tracking
└── WebSocket manager
```

**Problems with Old Architecture**:
- Tight coupling: API cannot run without Discord bot
- Testing difficulty: Must mock Discord client for all tests
- Single responsibility violation: One file handles HTTP + Discord
- Hard to extend: Adding new platforms requires modifying core file

**New Architecture** (VoxBridge 2.0 - Plugin-Based):
```
src/api/server.py (715 lines)           src/plugins/discord_plugin.py (1,706 lines)
├── FastAPI application                 ├── DiscordPlugin class
├── All HTTP routes                     ├── Discord bot client
│   ├── /voice/* (bridge pattern)      ├── Voice pipeline
│   ├── /api/agents                     ├── Audio receiver
│   ├── /api/plugins                    ├── Agent routing
│   └── /ws (WebSocket events)          └── Slash commands
├── WebSocket manager
├── Metrics tracker                     src/plugins/base.py (71 lines)
└── Startup/shutdown hooks              ├── PluginBase (abstract class)
                                        ├── start() / stop()
        ↕️ Bridge Pattern               └── get_stats()
   set_bot_bridge(functions)
                                        src/services/plugin_manager.py (621 lines)
                                        ├── PluginRegistry (singleton)
                                        ├── Load/unload plugins
                                        └── Health monitoring
```

**Benefits of New Architecture**:
- ✅ **Separation of Concerns**: API and Discord bot are independent
- ✅ **Testability**: Can test API without Discord client, test Discord plugin in isolation
- ✅ **Flexibility**: API can run without Discord (returns 503 if bot not available)
- ✅ **Extensibility**: New plugins (Telegram, Slack) don't modify core
- ✅ **Zero Breaking Changes**: All existing endpoints preserved

#### Bridge Pattern Implementation

The **bridge pattern** enables API ↔ Discord plugin communication:

```python
# In src/api/server.py (API side)
bot_bridge = {}

def set_bot_bridge(functions: Dict[str, Callable]):
    """Register bridge functions from Discord plugin"""
    global bot_bridge
    bot_bridge.update(functions)

@app.post("/voice/join")
async def join_voice_channel(request: VoiceJoinRequest):
    """API endpoint calls bridge function"""
    if "join_voice" not in bot_bridge:
        raise HTTPException(503, "Discord bot not initialized")
    return await bot_bridge["join_voice"](request.channelId, request.guildId)
```

```python
# In src/plugins/discord_plugin.py (Discord side)
from src.api.server import set_bot_bridge

class DiscordPlugin(PluginBase):
    async def start(self):
        """Register bridge functions with API server"""
        set_bot_bridge({
            "join_voice": self.join_voice_channel,
            "leave_voice": self.leave_voice_channel,
            "speak_text": self.speak_text,
            "get_bot_status": self.get_status
        })
```

**Bridge Functions Registered**:
1. `join_voice(channel_id, guild_id)` - Join Discord voice channel
2. `leave_voice()` - Leave current voice channel
3. `speak_text(text)` - Speak text via TTS in voice channel
4. `get_bot_status()` - Get Discord bot status (ready, in_voice, etc.)

#### Legacy Mode Support

For backward compatibility, legacy mode is available via environment variable:

```bash
# In .env
USE_LEGACY_DISCORD_BOT=true   # Use old monolithic handlers (deprecated)
USE_LEGACY_DISCORD_BOT=false  # Use new plugin system (default)
```

**How it works**:
```python
# In src/discord_bot.py
USE_LEGACY_DISCORD_BOT = os.getenv("USE_LEGACY_DISCORD_BOT", "false").lower() == "true"

if USE_LEGACY_DISCORD_BOT:
    logger.warning("⚠️  DEPRECATION WARNING: Using legacy Discord bot handlers")
    # Old voice handlers enabled
else:
    logger.info("✅ Using new plugin-based Discord bot (recommended)")
    # Legacy handlers disabled, plugins take over
```

**Deprecation Timeline**:
- **VoxBridge 2.x**: Legacy mode supported as fallback
- **VoxBridge 3.0**: Legacy mode removed entirely

#### Frontend Plugin Management UI

**Location**: `http://localhost:4903/plugins`

**Files Created** (485 lines, 3 files):
1. `frontend/src/pages/PluginsPage.tsx` (216 lines)
   - Main plugin management dashboard
   - Grid layout with plugin cards
   - Start/stop/restart controls

2. `frontend/src/components/PluginStatusCard.tsx` (166 lines)
   - Individual plugin status display
   - Resource monitoring (CPU, memory)
   - Action buttons (start, stop, restart)
   - Real-time status updates via WebSocket

3. `frontend/src/services/plugins.ts` (103 lines)
   - Plugin API client
   - TypeScript interfaces for plugins
   - HTTP client for plugin operations

**Features**:
- View all loaded plugins with status badges (Active/Inactive)
- Monitor plugin resource usage (memory, CPU, uptime)
- Start/stop/restart plugins via UI
- View plugin configuration and stats
- Real-time updates via WebSocket

#### Agent Routing with Discord Commands

**New Slash Commands** (~176 lines added):
```python
# In src/plugins/discord_plugin.py

@bot.slash_command(name="agent", description="Manage AI agents")
async def agent_command(ctx, action: str, agent_name: str = None):
    """
    /agent list - View all available agents
    /agent current - View current default agent
    /agent select <name> - Switch to a specific agent
    """
```

**Example Usage**:
```
User: /agent list
Bot:
  Available agents:
  1. Assistant (Default) - GPT-4 Turbo [OpenRouter]
  2. Assistant_Pro - Claude Sonnet 3.5 [OpenRouter]
  3. Coding_Expert - DeepSeek Coder [Local LLM]

User: /agent select Assistant_Pro
Bot:
  ✅ Switched to agent: Assistant_Pro
  Provider: OpenRouter (Claude Sonnet 3.5)
  Voice: alloy (1.0x speed)
```

**Implementation Details**:
- Agents loaded from PostgreSQL database
- Default agent cached in ConversationService
- Voice events route to default agent
- Per-agent LLM provider/model/voice configuration

#### Testing Coverage

**Test Results** (Phase 6.4.1 Batch 4):
- **Total Tests**: 76 tests created
- **Executed**: 59 tests in integration suite
- **Passing**: 59 (100% pass rate)
- **API Coverage**: 49% (src/api/server.py)
- **Execution Time**: 0.36 seconds

**Test Files Created**:
1. `tests/integration/test_api_server_decoupling.py` (19 tests)
   - Core endpoints (health, status, metrics)
   - Agent management endpoints
   - Voice control bridge pattern
   - WebSocket events
   - Server independence

2. `tests/integration/test_legacy_bot_toggle.py` (14 tests)
   - Environment variable parsing
   - Logging behavior
   - Bot behavior changes
   - Migration path validation

3. `tests/integration/test_voice_pipeline_migration.py` (13 tests)
   - Voice pipeline integration
   - Service layer functionality
   - Database persistence
   - Error handling

4. `tests/integration/test_agent_routing.py` (13 tests)
   - Slash command functionality
   - Agent selection logic
   - Database integration
   - Default agent caching

**E2E Tests** (17 tests):
- End-to-end voice pipeline tests
- Integration with real WhisperX + LLM + TTS services
- Performance and latency benchmarks

#### Migration Path

**Migration Guide**: [docs/MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md)

**8-Step Migration**:
1. Backup data (PostgreSQL dump + .env backup)
2. Update environment variables (`USE_LEGACY_DISCORD_BOT=false`)
3. Pull latest changes (`git pull origin voxbridge-2.0`)
4. Stop existing containers (`docker compose down`)
5. Rebuild containers (`docker compose build --no-cache`)
6. Verify plugin system logs
7. Run database migrations (`alembic upgrade head`)
8. Test functionality (API, voice, Discord commands)

**Rollback Options**:
- **Temporary**: Set `USE_LEGACY_DISCORD_BOT=true` (no rebuild required)
- **Permanent**: Git checkout previous commit, rebuild containers
- **Recovery**: Restore from PostgreSQL backup

**Zero Breaking Changes**: All existing API endpoints, Discord commands, and voice pipeline functionality preserved.

---

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

### VoxBridge 2.0 Phase Completions
- **Phase 1**: [docs/progress/phase-1-completion.md](docs/progress/phase-1-completion.md) - Core Infrastructure ✅
- **Phase 2**: [docs/progress/phase-2-completion.md](docs/progress/phase-2-completion.md) - Agent Management System ✅
- **Phase 3**: [docs/progress/phase-3-completion.md](docs/progress/phase-3-completion.md) - LLM Provider Abstraction ✅
- **Phase 4**: [docs/progress/phase-4-completion.md](docs/progress/phase-4-completion.md) - Web Voice Interface ✅
- **Phase 5**: [docs/progress/voxbridge-2.0-progress.md](docs/progress/voxbridge-2.0-progress.md#-phase-5-core-voice-pipeline-refactor) - Core Voice Pipeline Refactor ✅

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
- **tests/TEST_RESULTS.md** - Coverage report (88%, 71 tests: 66 passing, 5 failing)

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

**Status**: 🟢 **Phase 5 COMPLETE** - 62.5% Progress
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
2. **Agent Management System** ✅ **COMPLETE** (Oct 26, 2025)
   - Full CRUD API + UI for agent configuration
3. **LLM Provider Abstraction** ✅ **COMPLETE** (Oct 27, 2025)
   - OpenRouter + Local LLM abstraction with 90 unit tests
4. **Web Voice Interface** ✅ **COMPLETE** (Oct 27, 2025)
   - WebRTC browser voice chat with real-time transcription
5. **Core Voice Pipeline Refactor** ✅ **COMPLETE** (Oct 28, 2025)
   - Service layer architecture (4 services, 2,342 lines)
   - Refactored WebRTC handler + Discord bot
   - 99 unit tests with 90%+ coverage
   - ~300ms latency reduction
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

**Last Updated**: October 28, 2025
**Maintained By**: VoxBridge Development Team
