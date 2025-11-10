# VoxBridge 2.0 - Phase 3: LLM Provider Abstraction

**Status:** ✅ COMPLETE
**Date:** October 26, 2025
**Branch:** `voxbridge-2.0`

## Overview

Phase 3 introduces LLM provider abstraction, allowing VoxBridge to route conversations either to n8n webhooks (legacy flow) or directly to LLM providers (OpenRouter, local LLMs). This provides flexibility for different use cases and reduces latency for direct LLM interactions.

## Implementation Summary

### 1. LLM Provider Infrastructure (`src/llm/`)

Created a complete LLM provider abstraction layer with streaming support:

**`src/llm/types.py`** (53 lines)
- `LLMMessage`: Dataclass for conversation messages (system/user/assistant)
- `LLMStreamChunk`: Dataclass for streaming response chunks
- `LLMError`: Exception class with provider, status_code, and retryable flag

**`src/llm/base.py`** (34 lines)
- `LLMProvider`: Abstract base class defining the provider interface
- `generate_stream()`: Abstract method for streaming LLM responses

**`src/llm/openrouter.py`** (134 lines)
- `OpenRouterProvider`: OpenRouter API integration with SSE streaming
- Automatic retry logic (3 attempts) with exponential backoff
- Supports temperature, max_tokens parameters
- Parses Server-Sent Events (SSE) format
- Tracks token usage in final chunk

**`src/llm/local_llm.py`** (128 lines)
- `LocalLLMProvider`: OpenAI-compatible API for local LLMs (Ollama, LM Studio)
- Similar SSE streaming implementation
- Longer timeout (120s vs 60s) for local inference
- Optional API key support

**`src/llm/factory.py`** (81 lines)
- `LLMProviderFactory.create_provider()`: Factory method to instantiate providers
- Reads environment variables: `OPENROUTER_API_KEY`, `LOCAL_LLM_BASE_URL`
- Validates API keys and raises `LLMError` if missing

### 2. Database Schema Updates

**`alembic/versions/20251026_2014_602b72a921f3_add_use_n8n_to_agents.py`**
- Added `use_n8n` BOOLEAN column to `agents` table
- Default: `false` (use direct LLM)
- Migration ID: `602b72a921f3`

**Agent Model Updates (`src/database/models.py`)**
```python
use_n8n = Column(Boolean, nullable=False, default=False)  # Use n8n webhook instead of direct LLM
```

### 3. Agent API Updates

**`src/routes/agent_routes.py`** (Updated AgentResponse constructors)
- Added `use_n8n` field to `AgentCreateRequest`, `AgentUpdateRequest`, `AgentResponse`
- All 4 AgentResponse constructor calls updated (lines 120, 163, 213, 276)
- WebSocket broadcasts include `use_n8n` field for real-time UI updates

**`src/services/agent_service.py`** (Updated CRUD operations)
- `create_agent()`: Accepts `use_n8n` parameter (default: False)
- `update_agent()`: Accepts optional `use_n8n` parameter
- Validation: `use_n8n` must be boolean

### 4. Frontend Updates

**`frontend/src/services/api.ts`** (TypeScript interfaces)
```typescript
export interface Agent {
  // ... existing fields
  use_n8n: boolean; // Phase 3: Use n8n webhook instead of direct LLM
}

export interface AgentCreateRequest {
  // ... existing fields
  use_n8n?: boolean;
}

export interface AgentUpdateRequest {
  // ... existing fields
  use_n8n?: boolean;
}
```

**`frontend/src/components/AgentForm.tsx`** (UI component)
- Added `useN8n` state variable (boolean)
- Added Switch component toggle: "Use n8n Webhook"
- Description: "Route to n8n webhook instead of direct LLM"
- Populated in edit mode, submitted with form data

### 5. SpeakerManager Integration

**`src/speaker_manager.py`** (Major refactor)

**New Imports:**
```python
from uuid import UUID
from src.llm.factory import LLMProviderFactory
from src.llm.types import LLMMessage, LLMStreamChunk, LLMError
from src.services.agent_service import AgentService
```

**New Attributes:**
```python
self.default_agent_id = UUID(default_agent_id) if default_agent_id else None
```
- Reads `DEFAULT_AGENT_ID` environment variable
- Falls back to auto-detect (first available agent)

**New Method: `_handle_llm_response()`** (96 lines)
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, LLMError)),
    reraise=True
)
async def _handle_llm_response(self, transcript: str, agent_id: Optional[UUID] = None) -> None
```

**Functionality:**
1. **Agent Loading**: Queries database for agent by ID or uses default/first agent
2. **Provider Creation**: Uses `LLMProviderFactory.create_provider(agent)`
3. **Message Building**: Creates `LLMMessage` list with system prompt + user transcript
4. **Streaming Response**: Iterates over `provider.generate_stream()` chunks
5. **Latency Tracking**: Records first chunk latency, total LLM generation time
6. **Metrics Integration**: Records via `metrics_tracker.record_n8n_first_chunk_latency()` and `record_ai_generation_latency()`
7. **Streaming Handler**: Passes chunks to `streaming_handler.process_chunk()` for TTS
8. **Error Handling**: Catches `LLMError`, logs provider/retryable info

**Modified Method: `_finalize_transcription()`**

**Old Logic:**
```python
if transcript and self.n8n_webhook_url:
    await self._send_to_n8n(transcript)
elif transcript:
    logger.info(f"📝 Transcript (no webhook): \"{transcript}\"")
```

**New Logic (Phase 3):**
```python
# VoxBridge 2.0 Phase 3: Route to n8n or direct LLM based on agent configuration
if transcript:
    try:
        # Load agent to determine routing
        if self.default_agent_id:
            agent = await AgentService.get_agent(self.default_agent_id)
        else:
            # Fallback: Get first available agent
            agents = await AgentService.get_all_agents()
            agent = agents[0] if agents else None

        if agent and not agent.use_n8n:
            # Route to direct LLM provider
            logger.info(f"🤖 Routing to direct LLM (agent: {agent.name}, use_n8n=False)")
            await self._handle_llm_response(transcript, agent.id)
        elif self.n8n_webhook_url:
            # Route to n8n webhook (legacy flow)
            logger.info("🌐 Routing to n8n webhook (use_n8n=True or default)")
            await self._send_to_n8n(transcript)
        else:
            logger.warning("⚠️ No AI routing available (no agent or n8n webhook)")
            logger.info(f"📝 Transcript: \"{transcript}\"")
    except Exception as e:
        logger.error(f"❌ Error routing AI request: {e}")
```

**Routing Decision Tree:**
1. Load agent from database (by default_agent_id or first agent)
2. If `agent.use_n8n == False`: Route to `_handle_llm_response()` (direct LLM)
3. Else if `n8n_webhook_url` configured: Route to `_send_to_n8n()` (n8n webhook)
4. Else: Log warning and display transcript only

## Testing Results

### Agent CRUD Operations
✅ **Create agent with use_n8n=true:**
```bash
curl -X POST http://localhost:4900/api/agents -H "Content-Type: application/json" -d '{
  "name": "n8n Test Agent",
  "system_prompt": "You are a test agent that uses n8n webhooks for processing.",
  "use_n8n": true
}'
```
Response: Agent created with `use_n8n: true`

✅ **Update agent use_n8n field:**
```bash
curl -X PUT http://localhost:4900/api/agents/{id} -H "Content-Type: application/json" -d '{
  "use_n8n": false
}'
```
Response: Agent updated successfully

✅ **List agents with use_n8n field:**
```bash
curl http://localhost:4900/api/agents
```
Response: All agents include `use_n8n` field

### Service Startup
✅ **Discord bot starts with LLM integration:**
```
2025-10-26 20:25:30,801 - src.speaker_manager - INFO - 📋 SpeakerManager initialized:
2025-10-26 20:25:30,801 - src.speaker_manager - INFO -    Silence threshold: 600ms
2025-10-26 20:25:30,801 - src.speaker_manager - INFO -    Max speaking time: 45000ms
2025-10-26 20:25:30,801 - src.speaker_manager - INFO -    Streaming mode: True
2025-10-26 20:25:30,801 - src.speaker_manager - INFO -    Default agent ID: auto-detect
```

✅ **Frontend build successful:**
- AgentForm displays "Use n8n Webhook" toggle
- Agent cards show `use_n8n` status
- Real-time WebSocket updates work

### Current Agent Configuration
- **Auren (Default)**: `use_n8n=false` → Routes to direct LLM
- **TechSupport**: `use_n8n=false` → Routes to direct LLM
- **Creative Writer**: `use_n8n=false` → Routes to direct LLM
- **Test**: `use_n8n=false` → Routes to direct LLM
- **n8n Test Agent**: `use_n8n=true` → Routes to n8n webhook

## Architecture Decisions

### 1. Agent-Level Routing (✅ Implemented)
**Decision:** `use_n8n` flag at agent level, not global configuration
**Rationale:** Allows different agents to use different backends (e.g., creative agents use direct LLM for lower latency, complex workflows use n8n for tool integration)

### 2. Session-Based History (⏳ Deferred to Phase 4)
**Decision:** Use agent.system_prompt directly, no conversation history yet
**Rationale:** Phase 3 focuses on provider abstraction; multi-turn conversations require sessions table integration (planned for Phase 4)

### 3. Default Agent Fallback (✅ Implemented)
**Decision:** If `DEFAULT_AGENT_ID` not set, use first available agent
**Rationale:** Ensures system works out-of-box without manual configuration

### 4. Streaming Integration (✅ Implemented)
**Decision:** Pass LLM chunks to existing `StreamingResponseHandler`
**Rationale:** Reuses battle-tested TTS streaming infrastructure, maintains clause splitting and parallel TTS features

## Environment Variables

### New (Phase 3)
- `OPENROUTER_API_KEY`: OpenRouter API key (required for `llm_provider=openrouter`)
- `LOCAL_LLM_BASE_URL`: Local LLM endpoint (default: `http://localhost:11434/v1`)
- `LOCAL_LLM_API_KEY`: Optional API key for local LLM
- `DEFAULT_AGENT_ID`: UUID of default agent (optional, auto-detects if not set)

### Existing (Still Supported)
- `N8N_WEBHOOK_URL`: n8n webhook URL (required if `use_n8n=true`)
- `USE_STREAMING`: Enable streaming responses (default: `true`)

## File Changes Summary

### Created Files (9 files)
1. `src/llm/__init__.py` - Package init
2. `src/llm/types.py` - Type definitions (53 lines)
3. `src/llm/base.py` - Abstract base class (34 lines)
4. `src/llm/openrouter.py` - OpenRouter provider (134 lines)
5. `src/llm/local_llm.py` - Local LLM provider (128 lines)
6. `src/llm/factory.py` - Provider factory (81 lines)
7. `alembic/versions/20251026_2014_602b72a921f3_add_use_n8n_to_agents.py` - Migration (29 lines)
8. `docs/progress/phase3-llm-provider-abstraction-complete.md` - This document

### Modified Files (7 files)
1. `src/database/models.py` - Added `use_n8n` column
2. `src/routes/agent_routes.py` - Added `use_n8n` to API models
3. `src/services/agent_service.py` - Added `use_n8n` to CRUD operations
4. `src/speaker_manager.py` - Added LLM routing logic (96 lines new method + refactored finalization)
5. `frontend/src/services/api.ts` - Added `use_n8n` to TypeScript types
6. `frontend/src/components/AgentForm.tsx` - Added use_n8n toggle UI
7. `docker-compose.yml` - No changes required (env vars optional)

### Total Lines of Code
- **Backend (Python)**: ~600 lines
- **Frontend (TypeScript)**: ~50 lines
- **Migration (SQL)**: ~15 lines
- **Total**: ~665 lines

## Next Steps (Phase 4)

Phase 3 is complete. The next phase (Phase 4: Web Voice Interface) is NOT yet started. However, based on the current architecture, the following enhancements would be natural follow-ons:

### Conversation History (Future Enhancement)
Currently, each LLM call sends only:
```python
messages = [
    LLMMessage(role="system", content=agent.system_prompt),
    LLMMessage(role="user", content=transcript)
]
```

**Future Implementation (Phase 5 or later):**
```python
# Load session for this user
session = await SessionService.get_or_create_session(user_id=self.active_speaker, agent_id=agent.id)

# Load recent conversations (last N messages)
conversations = await ConversationService.get_recent_conversations(session_id=session.id, limit=10)

# Build message history
messages = [LLMMessage(role="system", content=agent.system_prompt)]
for conv in conversations:
    messages.append(LLMMessage(role="user", content=conv.user_message))
    messages.append(LLMMessage(role="assistant", content=conv.agent_response))
messages.append(LLMMessage(role="user", content=transcript))

# After LLM responds, save conversation
await ConversationService.create_conversation(
    session_id=session.id,
    user_message=transcript,
    agent_response=full_response
)
```

### Agent Switching (Future Enhancement)
Currently uses default/first agent. Future phases can add:
- Per-user agent preferences (stored in `sessions.session_metadata`)
- Voice command to switch agents ("Hey Auren, switch to TechSupport")
- Frontend UI to select active agent

### Performance Metrics (Already Implemented)
Phase 3 already tracks:
- ✅ First chunk latency (LLM time-to-first-token)
- ✅ Total LLM generation time
- ✅ Token usage (if provided by LLM)

## Known Limitations

1. **No conversation history yet**: Each LLM call is stateless (single-turn)
2. **No session persistence**: Conversations not saved to database yet
3. **Agent selection**: Currently uses default agent for all users
4. **Error recovery**: LLM errors may not gracefully fall back to n8n
5. **TTS voice**: Agent `tts_voice` field not yet integrated with `_handle_llm_response()`

## Conclusion

Phase 3 successfully implements LLM provider abstraction with:
- ✅ Two LLM providers (OpenRouter, Local LLM) with streaming
- ✅ Agent-level routing (`use_n8n` flag)
- ✅ Full CRUD API + frontend UI for agent management
- ✅ Integrated with existing streaming infrastructure
- ✅ Comprehensive error handling and retry logic
- ✅ Latency tracking and metrics

The system is now ready for Phase 4 (Web Voice Interface) or can continue with Phase 5 (Core Refactor) to add conversation history and session management.

---

**Implemented by:** Claude Code (VoxBridge 2.0 Orchestrator Agent)
**Date:** October 26, 2025
**Commit:** Ready for git commit to `voxbridge-2.0` branch
