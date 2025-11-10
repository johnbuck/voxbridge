# VoxBridge 2.0: Modular AI Voice Platform - Transformation Plan

**Created**: October 26, 2025
**Last Updated**: October 29, 2025
**Status**: 🟢 Implementation In Progress (Phases 1-5 Complete, Phase 6 In Progress)
**Estimated Effort**: 14-16 days
**Project Type**: Complete architectural transformation

---

## 📊 Progress Summary

**Overall Progress**: 6.35 / 8 phases complete (79%)

| Phase | Status | Completion Date | Key Deliverables |
|-------|--------|----------------|------------------|
| 1. Core Infrastructure | ✅ Complete | Oct 26, 2025 | PostgreSQL, SQLAlchemy models, Alembic migrations |
| 2. Agent Management | ✅ Complete | Oct 26, 2025 | Agent CRUD API, AgentsPage UI, WebSocket updates |
| 3. LLM Provider Abstraction | ✅ Complete | Oct 27, 2025 | OpenRouter + Local LLM providers, streaming support |
| 4. Web Voice Interface | ✅ Complete | Oct 28, 2025 | WebRTC audio, voice chat UI, real-time transcription |
| 5. Core Pipeline Refactor | ✅ Complete | Oct 28, 2025 | 4 new services (2,342 lines), session-based routing |
| 6. Plugin System | 🟡 85% Complete | Started Oct 29 | Discord plugin complete, Phase 6.5 in progress |
| 7. Documentation Overhaul | ⏳ Pending | - | Major doc rewrite needed |
| 8. Testing & Migration | ⏳ Pending | - | Test updates, coverage verification |

**Recent Achievements** (October 29-30, 2025):
- ✅ **LLM Provider Management System** (Phase 6.5.4) - October 30
  - Full CRUD UI for managing OpenRouter, Ollama, OpenAI, custom providers
  - API key encryption using existing plugin encryption system
  - Model fetching with caching, connection testing with metrics
  - 4 new database migrations (005, 006, 007, 008)
- ✅ **Multi-Turn Voice Conversations** - October 30
  - Per-utterance timeout (configurable per agent, 2 min default)
  - Replaces global speaker lock with continuous monitoring
  - Database migration 008 for `max_utterance_time_ms` field
- ✅ **Discord Plugin Integration** - October 29
  - Per-agent Discord bot controls in UI
  - Discord snowflake ID precision fix (critical bug fix)
  - Channel selector modal with guild/channel browsing
  - Auto-reconnect logic for state desync
- ✅ **Frontend Consolidation** - October 30
  - Settings hub architecture (`/settings/*` routes)
  - LLMProvidersPage, settings pages organized
  - Agent configuration cleanup (removed 4 deprecated agents)

**Next Steps**:
1. Complete Phase 6.5: Frontend Experience & LLM Provider Management
2. Clean up test suite (remove 3 legacy test files)
3. Phase 7: Documentation overhaul
4. Phase 8: Testing updates

**Note**: n8n plugin work has been removed from scope. Agents can still use n8n via the existing `use_n8n` boolean field.

---

## 🎯 Strategic Vision

Transform VoxBridge from a Discord-centric bot into a **modular AI voice platform** with optional integrations.

### Current Architecture (v1.0)
```
Discord Voice → WhisperX STT → n8n Webhook → Streaming Response → Chatterbox TTS → Discord
```
- ❌ Tightly coupled to Discord
- ❌ Hard-coded n8n webhook
- ❌ Single-speaker lock system
- ❌ No persistent storage
- ❌ No multi-agent support

### Target Architecture (v2.0)
```
Core Platform:
  Web Browser (WebRTC) → WhisperX STT → Agent Router → LLM Provider → Chatterbox TTS → Browser Audio

Optional Extensions:
  - Discord Extension (voice bot)
  - n8n Extension (workflow integration)
```
- ✅ Standalone web voice interface
- ✅ Multi-agent system (PostgreSQL)
- ✅ Configurable LLM providers (OpenRouter + Local)
- ✅ Session-based routing (no speaker lock)
- ✅ Modular extension system
- ✅ Frontend agent management UI

---

## 📋 Implementation Phases

### Phase 1: Core Infrastructure & Database (2 days) ✅ COMPLETE

**Status**: ✅ Completed October 26, 2025
**Objective**: Set up PostgreSQL and database schema for agent storage.

**Deliverables**:
- PostgreSQL container in docker-compose.yml
- Database schema:
  - `agents` table: Agent definitions (name, system_prompt, LLM config, TTS config)
  - `sessions` table: User sessions with agent selection
  - `conversations` table: Conversation history with context
- SQLAlchemy ORM models
- Alembic migrations
- Database connection pooling

**New Files**:
- `src/database/models.py`
- `src/database/session.py`
- `alembic/versions/001_initial_schema.py`
- `alembic.ini`

**Modified Files**:
- `docker-compose.yml` (add PostgreSQL service)
- `requirements-bot.txt` (add SQLAlchemy, Alembic, asyncpg)

**Documentation**:
- Update ARCHITECTURE.md: Mark Phase 1 as IN PROGRESS
- Update CLAUDE.md: Add database connection info
- Update AGENTS.md: Document database schema

---

### Phase 2: Agent Management System (2 days) ✅ COMPLETE

**Status**: ✅ Completed October 26, 2025
**Objective**: Build API and UI for managing AI agents.

**Deliverables**:
- Backend API endpoints:
  - `POST /api/agents` - Create agent
  - `GET /api/agents` - List agents
  - `GET /api/agents/{id}` - Get agent
  - `PUT /api/agents/{id}` - Update agent
  - `DELETE /api/agents/{id}` - Delete agent
- Frontend UI components:
  - Agent list page with cards
  - Agent creation form
  - Agent edit modal
  - LLM provider selector (OpenRouter/Local)
  - Voice configuration (TTS voice, rate, pitch)
- Default agent seeding (seed 2-3 example agents)

**New Files**:
- `src/services/agent_service.py`
- `src/routes/agent_routes.py`
- `frontend/src/pages/AgentsPage.tsx`
- `frontend/src/components/AgentCard.tsx`
- `frontend/src/components/AgentForm.tsx`
- `frontend/src/api/agents.ts`

**Documentation**:
- Update ARCHITECTURE.md: Add "Agent Management System" section
- Update CLAUDE.md: Document agent API endpoints
- Update `.claude/agents/api-documenter.md`: Add agent API examples

---

### Phase 3: LLM Provider Abstraction (2 days) ✅ COMPLETE

**Status**: ✅ Completed October 27, 2025
**Objective**: Create abstraction layer for multiple LLM providers.

**Deliverables**:
- Abstract `LLMProvider` base class with streaming support
- OpenRouter implementation
- Local LLM implementation (OpenAI-compatible API)
- Provider factory pattern
- Error handling, retries, rate limiting
- Response streaming to frontend

**New Files**:
- `src/llm/base.py` - Abstract provider interface
- `src/llm/openrouter.py` - OpenRouter implementation
- `src/llm/local_llm.py` - Local LLM implementation
- `src/llm/factory.py` - Provider factory
- `src/llm/types.py` - Type definitions

**Provider Interface**:
```python
class LLMProvider(ABC):
    @abstractmethod
    async def generate_stream(
        self,
        messages: List[Dict],
        temperature: float,
        model: str
    ) -> AsyncIterator[str]:
        pass
```

**Environment Variables**:
- `OPENROUTER_API_KEY`
- `LOCAL_LLM_BASE_URL` (e.g., http://localhost:11434/v1)

**Documentation**:
- Update ARCHITECTURE.md: Add "LLM Provider Architecture" section
- Update AGENTS.md: Document LLM integration patterns
- Update CLAUDE.md: Add LLM environment variables
- Create `.claude/agents/llm-integrator.md`: New agent for LLM tasks

---

### Phase 4: Web Voice Interface (2-3 days) ✅ COMPLETE

**Status**: ✅ Completed October 28, 2025
**Objective**: Build browser-based voice chat interface using WebRTC.

**Deliverables**:
- WebRTC audio capture (getUserMedia)
- Real-time audio streaming to backend (WebSocket binary)
- Voice activity detection (VAD)
- Browser audio playback (Audio element)
- Voice chat UI components:
  - Microphone controls (start/stop, mute)
  - Volume controls
  - Agent selector dropdown
  - Conversation history display
  - Real-time transcription display

**New Files**:
- `frontend/src/hooks/useWebRTC.ts` - WebRTC hook
- `frontend/src/hooks/useVoiceChat.ts` - Voice chat logic
- `frontend/src/components/VoiceChat.tsx` - Main component
- `frontend/src/components/AudioControls.tsx` - Audio controls
- `frontend/src/components/TranscriptionDisplay.tsx` - Live transcription
- `src/voice/webrtc_handler.py` - WebSocket audio handler
- `src/voice/audio_buffer.py` - Audio buffering

**WebSocket Protocol**:
- Client → Server: Binary audio frames (Opus or PCM)
- Server → Client: JSON messages (transcript, status, audio URL)

**Browser Requirements**:
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+ (limited support)

**Documentation**:
- Update ARCHITECTURE.md: Add "Web Voice Interface" with flow diagram
- Update README.md: Add browser compatibility section
- Update CLAUDE.md: Document WebSocket voice endpoints
- Create `.claude/commands/test-web-voice.md`: Voice testing command

---

### Phase 5: Core Voice Pipeline Refactor (2-3 days) ✅ COMPLETE

**Status**: ✅ Completed October 28, 2025
**Objective**: Decouple core services from Discord and refactor to session-based routing.

**Current Structure** (Discord-centric):
```
discord_bot.py (1200 lines) → speaker_manager.py (800 lines) → streaming_handler.py (700 lines)
```

**Target Structure** (Modular):
```
services/
  ├── conversation_service.py  # Session management (was speaker_manager)
  ├── stt_service.py           # WhisperX abstraction (was whisper_client)
  ├── llm_service.py           # LLM routing (was streaming_handler)
  └── tts_service.py           # Chatterbox abstraction (new)
```

**Key Changes**:
- ✅ Remove global speaker lock → session-based routing
- ✅ Decouple WhisperX from Discord
- ✅ Decouple LLM streaming from n8n
- ✅ Add conversation context management
- ✅ Support multiple concurrent sessions

**Refactored Files**:
- `src/speaker_manager.py` → `src/services/conversation_service.py`
- `src/whisper_client.py` → `src/services/stt_service.py`
- `src/streaming_handler.py` → `src/services/llm_service.py`
- Create `src/services/tts_service.py`

**New Architecture Flow**:
```
WebSocket Audio → STT Service → Conversation Service → Agent Router
                                                           ↓
                                                    LLM Service (Provider)
                                                           ↓
                                                    TTS Service → WebSocket
```

**Documentation** (MAJOR UPDATES):
- **ARCHITECTURE.md**:
  - Rewrite "Current Implementation Status"
  - Add new architecture diagram (standalone + extensions)
  - Document conversation flow
  - Replace "speaker lock" with "session management"
- **AGENTS.md**:
  - Replace "Speaker Lock System" → "Session Management System"
  - Document conversation service patterns
  - Update "Critical Architectural Concepts"
- **CLAUDE.md**:
  - Update "Key Files" section
  - Reflect new service structure

---

### Phase 6: Extension System (2 days) 🟡 IN PROGRESS

**Status**: 🟡 Partially Complete - Discord Plugin Integration finished October 29, 2025
**Objective**: Create plugin architecture for Discord and n8n as optional extensions.

**Completed Sub-phases**:
- ✅ **Discord Plugin Integration** (October 29, 2025):
  - Per-agent Discord bot plugin system
  - Plugin-based voice control endpoints (`/api/plugins/discord/voice/*`)
  - Discord snowflake ID precision preservation (manual JSON serialization)
  - Per-agent Discord status tracking (`/api/plugins/discord/voice/status/{agent_id}`)
  - Channel selector modal with guild/channel browsing
  - Auto-reconnect logic for state desync handling
  - localStorage persistence for guild IDs across page reloads
  - Responsive two-row layout for Discord plugin cards
  - TTS test modal for agent-specific voice testing
  - Frontend components: DiscordPluginCard, ChannelSelectorModal, TTSTestModal
  - Backend: plugin-based endpoints, per-agent status tracking

**Remaining Work**:
- ⏳ Complete Phase 6.5: Frontend Experience & LLM Provider Management
  - Route consolidation (voice chat to `/` route)
  - UX behavior unification (STT/AI indicators)
  - Settings hub refinement

**Note**: Generic extension base class and n8n webhook extension have been removed from scope. Discord plugin implementation is sufficient for Phase 6 completion.

**Deliverables** (Revised):
- ✅ Discord plugin system (per-agent bot controls) - COMPLETE
- ✅ Plugin-based voice endpoints (`/api/plugins/discord/voice/*`) - COMPLETE
- ✅ Frontend plugin UI (DiscordPluginCard, modals) - COMPLETE
- ⏳ Phase 6.5: Frontend Experience & LLM Provider Management - IN PROGRESS

**Plugin Architecture**:
The Discord plugin system uses a plugin-based architecture with:
- `src/plugins/base.py` - PluginBase abstract class
- `src/plugins/registry.py` - PluginRegistry (singleton pattern)
- `src/plugins/discord_plugin.py` - Discord bot implementation (per-agent)
- `src/services/plugin_manager.py` - PluginManager orchestration

**Environment Variables**:
- `USE_LEGACY_DISCORD_BOT=true/false` - Toggle legacy bot (deprecated)
- `DISCORD_TOKEN` - Discord bot token (stored encrypted in database per-agent)

**Documentation**:
- ✅ Update ARCHITECTURE.md: Add "Plugin System Architecture" - COMPLETE
- ✅ Update CLAUDE.md: Document plugin environment variables - COMPLETE
- ✅ Update README.md: Add plugin configuration guide - COMPLETE

---

### Phase 6.5: Frontend Experience & LLM Provider Management (2 days)

**Objective**: Consolidate voice chat to primary route, unify UX behaviors, and create unified LLM provider management interface.

**Priority**: HIGH - Critical user experience issues identified

**Deliverables**:

#### 6.5.1: Route Consolidation (3-4 hours)
- Move voice chat functionality to `/` route (primary interaction)
- Rename current VoxbridgePage → DiscordBotLegacyPage
- Move to `/discord-bot` route as optional fallback
- Update navigation links and routing

**New Files**:
- `frontend/src/pages/DiscordBotLegacyPage.tsx` (rename existing VoxbridgePage)

**Modified Files**:
- `frontend/src/App.tsx` - Update routes
- `frontend/src/pages/VoxbridgePage.tsx` - Replace with voice chat
- `frontend/src/components/Navigation.tsx` - Update links

#### 6.5.2: UX Behavior Unification (4-6 hours)
- STT waiting indicator (microphone pulse, "Listening..." text, duration counter)
- AI generation indicator ("Thinking..." with animated dots, loading spinner)
- Chunk handling & streaming display (typewriter effect, auto-scroll)
- Speaker lock visualization (which user has lock, duration timer)

**New Files**:
- `frontend/src/components/STTWaitingIndicator.tsx`
- `frontend/src/components/AIGeneratingIndicator.tsx`
- `frontend/src/components/StreamingMessageDisplay.tsx`

**Modified Files**:
- `frontend/src/components/AudioControls.tsx` - Add animations
- `frontend/src/hooks/useWebRTCAudio.ts` - Emit state events
- `frontend/src/pages/VoxbridgePage.tsx` - Integrate indicators

#### 6.5.3: Settings Hub Architecture (5-7 hours)
- Create `/settings` main hub with sidebar navigation
- Move existing settings pages to child routes:
  - `/settings/whisperx` (move from `/whisperx`)
  - `/settings/chatterbox` (move from `/chatterbox-tts`)
  - `/settings/plugins` (move from `/plugins`)
- Add breadcrumbs and overview cards

**New Files**:
- `frontend/src/pages/SettingsPage.tsx` - Main hub
- `frontend/src/components/SettingsSidebar.tsx`
- `frontend/src/components/SettingsCard.tsx`
- `frontend/src/pages/settings/WhisperXSettingsPage.tsx` (move existing)
- `frontend/src/pages/settings/ChatterboxSettingsPage.tsx` (move existing)
- `frontend/src/pages/settings/PluginsSettingsPage.tsx` (move existing)

#### 6.5.4: LLM Provider Management (5-6 hours)
**Inspired by Open WebUI's unified provider management**

- Unified LLM providers page at `/settings/llm-providers`
- Manage all OpenAI-compatible API endpoints (OpenRouter, Ollama, OpenAI, vLLM, LM Studio, custom)
- Provider card grid with connection status, model count, actions
- Add/edit provider dialog with form validation
- Connection testing (calls `/v1/models` endpoint)
- Auto-fetch available models on successful connection
- Database-backed storage with encrypted API keys

**Database Schema**:
```sql
CREATE TABLE llm_providers (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    base_url VARCHAR(512) NOT NULL,
    api_key_encrypted TEXT,
    provider_type VARCHAR(50),
    models JSONB DEFAULT '[]',
    default_model VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**New Files**:
- `frontend/src/pages/settings/LLMProvidersPage.tsx`
- `frontend/src/components/LLMProviderCard.tsx`
- `frontend/src/components/LLMProviderDialog.tsx`
- `frontend/src/components/LLMProviderTestButton.tsx`
- `src/routes/llm_provider_routes.py`
- `src/services/llm_provider_service.py`
- `src/database/models.py` - Add LLMProvider model
- `alembic/versions/005_add_llm_providers_table.py`
- `docs/user-guides/llm-provider-setup.md`

**Modified Files**:
- `frontend/src/services/api.ts` - Add LLM provider API methods
- `src/llm/factory.py` - Use database providers instead of env vars
- `src/services/agent_service.py` - Link agents to LLM providers
- `frontend/src/components/AgentForm.tsx` - LLM provider dropdown

**API Endpoints**:
```
GET    /api/settings/llm-providers          - List all providers
POST   /api/settings/llm-providers          - Create new provider
GET    /api/settings/llm-providers/:id      - Get provider details
PUT    /api/settings/llm-providers/:id      - Update provider
DELETE /api/settings/llm-providers/:id      - Delete provider
POST   /api/settings/llm-providers/:id/test - Test connection
```

**Example Providers**:
- **OpenRouter**: `https://openrouter.ai/api/v1` with API key
- **Local Ollama**: `http://localhost:11434/v1` (no API key)
- **OpenAI**: `https://api.openai.com/v1` with API key
- **Custom**: Any OpenAI-compatible endpoint

**Integration with Agents**:
- Agents reference LLM provider by UUID (foreign key)
- Agent form shows dropdown of available providers
- Select provider → select model from provider's available models
- Backward compatible with existing `llm_provider` string field

**Documentation**:
- User guide: Setting up LLM providers (OpenRouter, Ollama, OpenAI, custom)
- API documentation: LLM provider endpoints
- Migration guide: Converting from env vars to database providers

---

### Phase 7: Documentation Overhaul (1 day)

**Objective**: Complete rewrite of all documentation to reflect VoxBridge 2.0 architecture.

**Files to Rewrite** (Major):
1. **ARCHITECTURE.md**:
   - Rewrite "Current Implementation Status" → VoxBridge 2.0 features
   - Update "Project Roadmap" → standalone + extensions model
   - Add architecture diagrams (4-container setup with PostgreSQL)
   - Document all 8 phases
   - Update "Not Yet Implemented" section

2. **CLAUDE.md**:
   - Update "Architecture Overview" → 4-container setup
   - Rewrite "Key Files" → new service structure
   - Add "Extension Configuration" section
   - Update environment variables (LLM providers, extensions)
   - Update API endpoints (add agent management, web voice)

3. **AGENTS.md**:
   - Complete rewrite of "Critical Architectural Concepts"
   - Replace "Speaker Lock System" → "Session Management System"
   - Add "Extension System Architecture"
   - Update "Code Modification Guidelines"
   - Document LLM provider integration patterns

4. **README.md**:
   - Rewrite introduction (standalone platform, not Discord bot)
   - Update "Features" section
   - Add "Standalone Mode" setup instructions
   - Add "Extension Configuration" section
   - Update quick start guide

**Files to Create**:
- `docs/architecture/voxbridge-2.0-implementation.md` (this file)
- `docs/progress/transformation-progress.md` (tracking)
- Archive `docs/architecture/multi-agent-implementation-plan.md` (mark as superseded)

**Claude Agent Updates** (.claude/):
- Update `.claude/commands/status.md` → check standalone + extensions
- Create `.claude/commands/test-web-voice.md` → test browser voice
- Create `.claude/agents/extension-builder.md` → build extensions
- Create `.claude/agents/llm-integrator.md` → integrate LLMs
- Update `.claude/agents/unit-test-writer.md` → new module structure
- Update `.claude/agents/integration-test-writer.md` → test extensions

---

### Phase 8: Testing & Migration (1 day)

**Objective**: Update test suite and verify all functionality.

**Test Updates**:
- Rename test files to match new structure:
  - `test_speaker_manager.py` → `test_conversation_service.py`
  - `test_whisper_client.py` → `test_stt_service.py`
  - `test_streaming_handler.py` → `test_llm_service.py`
- Create new test files:
  - `test_agent_service.py` - Agent CRUD tests
  - `test_llm_providers.py` - LLM provider tests
  - `test_discord_extension.py` - Discord extension tests
  - `test_n8n_extension.py` - n8n extension tests
  - `test_web_voice.py` - WebRTC integration tests

**Test Targets**:
- Maintain 88%+ coverage
- All 43 tests passing (fix 5 failing tests)
- Add 20+ new tests for new features

**Documentation**:
- Update `tests/README.md`: New test structure
- Update `.claude/commands/test-coverage.md`: New coverage targets
- Final update to ARCHITECTURE.md: Mark all phases ✅ COMPLETE

---

## 📊 Effort Breakdown

| Phase | Est. Days | Actual Days | Status | Notes |
|-------|-----------|-------------|--------|-------|
| 1. Infrastructure | 2 | 1.5 | ✅ Complete | Oct 26 - PostgreSQL, models, migrations |
| 2. Agent Management | 2 | 1.5 | ✅ Complete | Oct 26 - CRUD API + UI |
| 3. LLM Providers | 2 | 2 | ✅ Complete | Oct 27 - OpenRouter + Local |
| 4. Web Voice | 3 | 2.5 | ✅ Complete | Oct 28 - WebRTC + audio UI |
| 5. Core Refactor | 3 | 2.5 | ✅ Complete | Oct 28 - Service layer |
| 6. Plugin System | 2 | 2.7 | 🟡 85% Complete | Oct 29-30 - Discord + LLM Provider Mgmt |
| 7. Documentation | 1 | - | ⏳ Pending | Major doc rewrite |
| 8. Testing | 1 | - | ⏳ Pending | Test updates needed |
| **Total** | **16** | **13.2 (so far)** | **79%** | On track |

**Velocity**: Averaging 2.1 days per phase (vs estimated 2.0 days) - on schedule!

**Note**: Phase 6 expanded to include Phase 6.5 (Frontend Experience & LLM Provider Management). n8n plugin work removed from scope.

---

## 🎯 Key Architectural Decisions

1. **WebRTC for Voice**: Browser-based voice interface (no desktop client)
2. **PostgreSQL for Storage**: Persistent agent/session/conversation data
3. **Clean-Slate Refactor**: No backward compatibility with v1.0
4. **Extension System**: Discord/n8n become optional plugins
5. **LLM Flexibility**: Support both OpenRouter and local LLMs
6. **Session-Based**: No global speaker lock, multi-session capable

---

## 📝 Open Questions

**To be decided during implementation**:

1. **Authentication**:
   - Single-user mode only?
   - Multi-user with basic auth?
   - OAuth integration?

2. **Agent Sharing**:
   - Public agent library?
   - Private agents only?
   - Export/import functionality?

3. **API Key Security**:
   - Store encrypted in database?
   - Require environment variables?
   - User-provided per session?

4. **Redis**:
   - Needed for session caching?
   - PostgreSQL only sufficient?

---

## 🚀 Success Criteria

**VoxBridge 2.0 is complete when**:

- ✅ User can create agents in frontend UI *(Complete - Oct 26)*
- ✅ User can chat with agent via browser voice (WebRTC) *(Complete - Oct 28)*
- ✅ Agents use configurable LLM (OpenRouter or local) *(Complete - Oct 27)*
- ✅ Conversation history persisted in PostgreSQL *(Complete - Oct 26)*
- ✅ Discord plugin integration working per-agent *(Complete - Oct 29)*
- ✅ LLM Provider Management UI complete *(Complete - Oct 30)*
- 🟡 Frontend experience unified (Phase 6.5) *(In Progress)*
- ⏳ Test suite cleaned up (3 legacy files removed) *(Pending)*
- ⏳ All tests passing (88%+ coverage) *(Needs cleanup)*
- ⏳ Documentation fully updated *(Major rewrite pending - Phase 7)*

**Current Score**: 6.5 / 10 criteria met (65%)

**Note**: n8n extension and generic extension manager removed from scope. Existing `use_n8n` boolean field on agents provides n8n integration without requiring a separate plugin system.

---

**Status**: 🟢 Implementation In Progress - Phase 6 (79% complete)
**Current Phase**: Phase 6.5 - Frontend Experience & LLM Provider Management (85% complete)
**Next Milestone**: Complete Phase 6.5, then proceed to Phase 7 (Documentation)
**Original Estimated Completion**: November 11, 2025
**Revised Estimated Completion**: November 5, 2025 (ahead of schedule by 6 days)

**Scope Changes**:
- ✅ Phase 6.5 added (Frontend Experience & LLM Provider Management)
- ❌ n8n plugin removed from scope (use existing `use_n8n` boolean field instead)
- ❌ Generic extension base class removed from scope (Discord plugin implementation sufficient)
