# VoxBridge Memory System - Implementation Plan

> **Status**: Active Development - Phase 2 In Progress (~50% Complete)
>
> **Last Updated**: 2025-11-23 (Frontend UI Complete)
> **Approach**: Mem0 Framework Integration (Simplified from Original Custom Provider Plan)

---

## Executive Summary

VoxBridge now includes a conversational memory system powered by the Mem0 framework, providing:
- **Mem0 Framework**: Automatic fact extraction with 26% accuracy improvement over custom approaches
- **Dual Embedding Support**: Azure OpenAI (3072-dim) OR local sentence-transformers (768-dim)
- **Queue-Based Extraction**: Non-blocking fact extraction doesn't delay voice responses
- **Memory Scope**: Global (shared across agents) or agent-specific memory
- **Vector Search**: pgvector-backed semantic memory retrieval

**Current Status**: Phase 1 backend infrastructure complete, user-facing features in progress.

**Architecture Decision**: We chose Mem0 framework over the originally planned custom pgvector provider pattern for simplicity, better accuracy, and faster development.

---

## Strategic Context

### Original Planning Decisions (2025-11-21)

**Requirements**:
1. ✅ **Vector Database**: pgvector (via Mem0 framework)
2. ✅ **Embeddings**: sentence-transformers/all-mpnet-base-v2 (768 dims, local, works out of the box)
   - Azure AI text-embedding-3-large (3072 dims) available as upgrade via Frontend UI settings
3. ✅ **Fact Extraction**: LLM-based (via Mem0, with relevance filtering)
4. ✅ **Memory Scope**: Global by default, agent-specific override
5. ✅ **Latency Tolerance**: <100ms retrieval (pgvector HNSW)
6. ✅ **Features Priority**: Simple facts first, temporal/relationships on roadmap
7. ✅ **Deployment**: Self-hosted PostgreSQL + pgvector

### Framework Selection: Mem0

**Why Mem0**:
- **26% accuracy improvement** over custom extraction approaches
- **Out-of-the-box features**: Fact extraction, deduplication, semantic search
- **Provider flexibility**: Supports Azure AI, OpenAI, local LLMs, HuggingFace embeddings
- **Graph-ready**: Optional graph pipeline for future enhancements
- **Self-hosted**: Apache 2.0 license, full control
- **Significantly simpler**: ~90% less code than custom provider pattern

**Trade-offs**:
- Less control over extraction logic (delegated to Mem0)
- Vendor lock-in risk (mitigated by open source + self-hosted)

---

## Architecture Overview

### Three-Tier Memory System

```
Tier 1: Short-Term Cache (ConversationService)
├── In-memory (15-min TTL)
├── Last 10-20 messages
└── Zero latency (<1ms)

Tier 2: Fast Fact Retrieval (Mem0 + pgvector) [CURRENT]
├── PostgreSQL + pgvector extension
├── Mem0 framework for extraction/search
├── User facts + embeddings
├── <100ms retrieval (local DB)
└── Dual embeddings (Azure 3072-dim OR local 768-dim)

Tier 3: Deep Memory (Zep + Graphiti) [FUTURE - Phase 3]
├── Neo4j temporal knowledge graph
├── Entity relationships + temporal reasoning
├── 300-500ms retrieval (complex queries)
└── Self-hosted (full control)
```

### Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Memory Framework** | Mem0 | 26% accuracy improvement, self-hosted, Apache 2.0 |
| **Vector Store** | pgvector 0.8.1 | Integrated with PostgreSQL, HNSW indexing |
| **Embeddings (Planned)** | Azure AI text-embedding-3-large | 3072 dims, high quality |
| **Embeddings (Fallback)** | sentence-transformers/all-mpnet-base-v2 | 768 dims, free, self-hosted |
| **Graph DB (Future)** | Neo4j 5 Community | Temporal reasoning, self-hosted |
| **Extraction LLM** | Mem0 auto-configured | Uses same LLM as conversation |

---

## Implementation Status

### PHASE 1: Backend Infrastructure (~50% Complete)

#### ✅ Completed: Database Layer

**Migrations Created** (alembic/versions/):
- **013_install_pgvector.py** - Installed pgvector 0.8.1 extension
- **014_create_memory_vectors.py** - Mem0-managed vector table (user_memories)
- **015_add_memory_tables.py** - users, user_facts tables
- **016_create_extraction_queue.py** - extraction_tasks queue + agent memory_scope
- **017_add_auth_tokens.py** - WebRTC auth token support

**Database Schema**:
```sql
-- Users table (unified identity)
users (
    id UUID PRIMARY KEY,
    user_id TEXT UNIQUE NOT NULL,
    display_name TEXT,
    embedding_provider TEXT,  -- 'azure' or 'local'
    memory_extraction_enabled BOOLEAN DEFAULT true,
    auth_token TEXT,          -- WebRTC authentication
    token_created_at TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
)

-- User facts (relational metadata + PostgreSQL queries)
user_facts (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    agent_id UUID REFERENCES agents(id),  -- NULL = global
    fact_key TEXT,            -- 'name', 'location', etc.
    fact_value TEXT,          -- Extracted value
    fact_text TEXT,           -- Natural language: "name: Alice"
    importance FLOAT,         -- 0.0-1.0 relevance score
    vector_id TEXT,           -- Mem0 vector ID reference
    embedding_provider TEXT,
    embedding_model TEXT,
    validity_start TIMESTAMPTZ,
    validity_end TIMESTAMPTZ,  -- NULL = currently valid
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    UNIQUE(user_id, fact_key, agent_id)
)

-- Extraction queue (async, non-blocking)
extraction_tasks (
    id UUID PRIMARY KEY,
    user_id TEXT,
    agent_id UUID REFERENCES agents(id),
    user_message TEXT,
    ai_response TEXT,
    status TEXT,              -- 'pending', 'processing', 'completed', 'failed'
    attempts INTEGER,         -- Retry counter (max 3)
    error TEXT,
    created_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
)

-- Mem0 vector table (auto-created by framework)
user_memories (
    id TEXT PRIMARY KEY,
    vector VECTOR(1536),      -- NOTE: Currently 1536-dim (OpenAI default)
    payload JSONB
)
```

#### ✅ Completed: MemoryService Implementation

**File**: `src/services/memory_service.py` (395 lines)

**Core Methods**:
1. `__init__()` - Initialize Mem0 with configurable embeddings (Azure or local)
2. `queue_extraction(user_id, agent_id, user_message, ai_response)` - Queue extraction task
3. `process_extraction_queue()` - Background worker processes extraction queue
4. `get_user_memory_context(user_id, agent_id, query, limit=5)` - Retrieve relevant memories
5. `_extract_facts_from_turn(user_id, agent_id, user_message, ai_response)` - Mem0 extraction
6. `_should_extract_facts(user_message, ai_response)` - LLM relevance filter
7. `_get_or_create_user(user_id, db)` - User management
8. `_get_agent(agent_id, db)` - Agent retrieval
9. `_upsert_fact(user, agent_id, vector_id, fact_text, importance, ...)` - Sync to PostgreSQL

**Key Features**:
- **Non-blocking extraction**: Queue-based, doesn't delay voice responses
- **Retry logic**: Up to 3 attempts per task with error tracking
- **Memory scope**: Global (user_id) vs agent-specific (user_id:agent_id) namespacing
- **Relevance filtering**: LLM determines if conversation contains memorable facts
- **Graceful degradation**: Returns empty string on errors, doesn't crash
- **Configurable embeddings**: Auto-detects Azure credentials, falls back to local

#### ✅ Completed: ConversationService Integration

**File**: `src/services/conversation_service.py`

**Integration Points**:
1. **Initialization** (line 143-149): MemoryService initialized with error handling
2. **Context Injection** (line 322-341): User memories retrieved and injected as system message
3. **Extraction Queuing** (line 512-513, 700-743): After AI responses, extraction task queued

**Memory Context Format**:
```xml
<user_memories>
- name: Alice (relevance: 0.92)
- location: San Francisco (relevance: 0.87)
- occupation: Software Engineer (relevance: 0.81)
</user_memories>
```

#### ✅ Completed: API Server Integration

**File**: `src/api/server.py`

**Integration Points**:
1. **Service Initialization** (line 459): `memory_service = MemoryService()`
2. **Background Worker** (line 514-515): `asyncio.create_task(memory_service.process_extraction_queue())`

The background worker continuously polls the extraction_tasks table and processes pending tasks.

#### ✅ Completed: Testing

**File**: `tests/unit/services/test_memory_service.py` (720 lines, 21 tests)

**Test Coverage**:
- Initialization (Azure, local, fallback)
- Queue extraction (success, database errors)
- Process extraction queue (single task, retry, max retries)
- Extract facts (success, skip irrelevant, agent-specific scope)
- Get memory context (success, empty, error handling)
- Relevance filter (yes, no, LLM errors)
- Helper methods (get_or_create_user, upsert_fact)

**Results**: ✅ 21/21 passing (100% pass rate)

---

### ❌ Missing: User-Facing Features

#### API Endpoints (Not Implemented)

**Memory Settings**:
- `GET /api/users/{user_id}/memory-settings` - Get extraction configuration
- `PUT /api/users/{user_id}/memory-settings` - Configure extraction LLM

**Fact Management**:
- `GET /api/users/{user_id}/facts` - List user facts
- `POST /api/users/{user_id}/facts` - Manually add fact
- `PUT /api/users/{user_id}/facts/{fact_id}` - Edit fact
- `DELETE /api/users/{user_id}/facts/{fact_id}` - Delete fact

**GDPR Compliance**:
- `GET /api/users/{user_id}/export` - Export all user data (JSON)
- `POST /api/users/{user_id}/forget` - Delete all user data (irreversible)

#### Frontend UI (Not Implemented)

**User Profile Page** (`frontend/src/pages/UserProfilePage.tsx`):
- Tab 1: **Facts** - List, edit, delete, manually add facts
- Tab 2: **Preferences** - View/override learned preferences
- Tab 3: **Topics** - Discussion frequency by agent
- Tab 4: **Settings** - Extraction LLM, data retention, export/delete

**Memory Settings Page** (`frontend/src/pages/MemorySettingsPage.tsx`):
- Extraction LLM configuration (provider, model, temperature)
- Test extraction button
- Data retention policy selector
- GDPR export/delete controls

**Components**:
- `frontend/src/components/FactCard.tsx` - Fact display/edit card
- `frontend/src/components/MemoryMetrics.tsx` - Memory performance dashboard

#### Testing (Not Implemented)

**Integration Tests**:
- `tests/integration/test_memory_extraction.py` - E2E conversation → extraction → retrieval
- `tests/integration/test_memory_scope.py` - Global vs agent-specific memory

**Load Tests**:
- `tests/load/test_memory_performance.py` - 10k conversations, <100ms retrieval benchmark

---

### ✅ Configuration Complete - Database-Backed Global Settings

**Global Database-Backed Embeddings Configuration** (2025-11-22):

**3-Tier Prioritization Pattern** (matches LLM provider pattern):
1. ✅ **Database** - Global system settings table (`system_settings.embedding_config`) - **HIGHEST PRIORITY**
2. ✅ **Environment Variables** - `.env` fallback (`EMBEDDING_PROVIDER`, `AZURE_EMBEDDING_API_KEY`)
3. ✅ **Hardcoded Defaults** - `local` embeddings (sentence-transformers/all-mpnet-base-v2)

**Implementation Details**:
- ✅ Database schema: `system_settings` table with JSONB config storage
- ✅ Database model: `SystemSettings` class with setting_key/setting_value
- ✅ Service layer: `MemoryService.__init__(db_embedding_config=None)` with prioritization logic
- ✅ API endpoints: GET/PUT/POST `/api/system-settings/embedding-config`
- ✅ Helper function: `get_global_embedding_config()` for database fetching
- ✅ `.env.example` documentation updated with priority explanation
- ✅ Default config: Local embeddings (768 dims, sentence-transformers/all-mpnet-base-v2)
- ✅ Works out of the box - no API keys required
- ✅ All 21 unit tests passing

**Configuration Methods**:
1. **Settings UI** (recommended): `/settings/embeddings` - persists across container restarts
2. **Environment Variables**: `.env` file - fallback if database not configured
3. **API Endpoints**: Direct API calls for programmatic configuration

**Azure Embeddings Available as Upgrade**:
- Higher quality embeddings (3072 dims vs 768 dims)
- Requires Azure OpenAI API key and endpoint
- Configurable via Settings UI or API endpoints
- API key encryption (TODO: implement before production use)

**Admin Access** (Future):
- Settings UI currently accessible to all users
- Will be restricted to admin-only access in Phase 3
- Admin role system out of scope for Phase 1-2

### ✅ Model Cache Volume - Provider-Agnostic Storage (COMPLETE)

**Docker Volume for ML Model Caching** (2025-11-22):

**Volume Name**: `voxbridge-models` (provider-agnostic, scalable for future ML caching needs)

**Purpose**:
- Cache downloaded embedding models from HuggingFace
- Persist models across container rebuilds
- Prevent re-downloading ~420MB-1.34GB on every `docker compose build`
- Support future ML model caching (not just embeddings)

**Implementation**:
- ✅ Volume mount: `/home/appuser/.cache/huggingface` → `voxbridge-models`
- ✅ Environment variable: `HF_HOME=/home/appuser/.cache/huggingface`
- ✅ Model Status API: `GET /api/system-settings/embedding-model-status?model={optional}`
- ✅ Model Download API: `POST /api/system-settings/embedding-model/download`
- ✅ Model Cleanup API: `POST /api/system-settings/embedding-model/cleanup`
- ✅ Frontend UI: Model cache status card in Embeddings Settings page

**Model Selection** (7 models organized by quality/speed):
- ✅ **384 dims (Fast)**:
  - `sentence-transformers/all-MiniLM-L6-v2` (80MB, fast)
  - `BAAI/bge-small-en-v1.5` (130MB, better quality)
- ✅ **768 dims (Balanced)**:
  - `sentence-transformers/all-mpnet-base-v2` (420MB) [default]
  - `BAAI/bge-base-en-v1.5` (420MB, recommended)
  - `jinaai/jina-embeddings-v2-base-en` (500MB, 8K context)
- ✅ **1024 dims (High Quality)**:
  - `BAAI/bge-large-en-v1.5` (1.34GB, best quality)
  - `intfloat/e5-large-v2` (1.34GB, high quality)

**Advanced Features**:
- ✅ **Live Cache Status**: Real-time cache updates as user browses models (before saving)
- ✅ **Auto-Download**: Models download immediately when selected (not on first use)
- ✅ **Smart Toasts**: Pre-checks cache before showing "downloading" notification
- ✅ **Cleanup Feature**: Delete all cached models except currently selected one
  - Confirmation dialog prevents accidental deletions
  - Shows models deleted and space reclaimed (e.g., "Reclaimed 1697.86 MB")
  - Uses HuggingFace `delete_revisions()` API with revision hashes
- ✅ **Dimension Detection**: Auto-detects and saves correct dimensions for each model

**Model Download Status API**:
- Returns cache status, size, file count, last modified timestamp
- Provider-aware: Shows "no cache needed" for Azure (API-based)
- Accepts optional `?model=` parameter to check arbitrary models
- Uses `huggingface_hub.scan_cache_dir()` for inspection

**Benefits**:
- 80MB-1.34GB saved per rebuild (depending on model)
- 1-5 min saved per rebuild (network-dependent)
- User visibility into download status before using embeddings
- Efficient disk space management (cleanup unused models)
- Follows existing WhisperX model caching pattern

---

## PHASE 2: User-Facing Features (~33% Complete)

**Goal**: Complete the memory system with user-accessible UI and API endpoints.

**Progress**: 2 of 6 tasks complete (Task 1: Memory API Endpoints ✅, Task 2: Ollama Integration ✅)

### ✅ Task 1: Memory API Endpoints (COMPLETE - 2025-11-22)

**Implementation**: `src/routes/memory_routes.py` (495 lines, 8 endpoints)

**Endpoints Implemented**:
1. ✅ `GET /api/memory/users/{user_id}/facts` - List all user facts (with filtering)
2. ✅ `POST /api/memory/users/{user_id}/facts` - Manually create a fact
3. ✅ `PUT /api/memory/users/{user_id}/facts/{fact_id}` - Update existing fact
4. ✅ `DELETE /api/memory/users/{user_id}/facts/{fact_id}` - Delete specific fact
5. ✅ `GET /api/memory/users/{user_id}/settings` - Get user memory settings
6. ✅ `PUT /api/memory/users/{user_id}/settings` - Update memory settings
7. ✅ `GET /api/memory/users/{user_id}/export` - GDPR data export (JSON)
8. ✅ `DELETE /api/memory/users/{user_id}` - GDPR right to erasure (delete all data)

**Key Features**:
- **Automatic fact creation**: Integrated with Mem0 for embedding generation and pgvector storage
- **Ollama integration**: Uses local Ollama LLM (gemma3n:latest) for fact extraction when OpenRouter unavailable
- **OpenRouter fallback**: Prioritizes OpenRouter (gpt-4o-mini) when API key is available
- **Agent-specific scoping**: Facts can be global or agent-specific (via `agent_id` parameter)
- **Filtering support**: Query parameters for `agent_id` and `include_invalid`
- **GDPR compliant**: Export and deletion endpoints for data privacy
- **Error handling**: Comprehensive error logging and user-friendly error messages

**Fixes Applied During Implementation**:
1. **Environment variable fix**: Added `LOCAL_LLM_BASE_URL=http://ollama:11434` to `.env` (was missing, causing empty string)
2. **Vector dimension mismatch fix**: Recreated `user_memories` table with 1024 dimensions (was 1536, but BAAI/bge-large-en-v1.5 generates 1024)
3. **Mem0 result format fix**: Changed from `mem0_result["memories"]` to `mem0_result["results"]` (API breaking change)
4. **Enhanced error logging**: Added detailed traceback logging and Ollama URL logging for troubleshooting

**Testing Results** (2025-11-22):
- ✅ Test 1: List facts - Working
- ✅ Test 2: Create fact - Working (Ollama + Mem0 integration successful)
- ✅ Test 3: Update fact - Working
- ✅ Test 4: Get memory settings - Working
- ✅ Test 5: Update memory settings - Working
- ✅ Test 6: GDPR export - Working
- ✅ Test 7: Delete fact - Working
- ✅ Test 8: GDPR delete - Working

**Database Integration**:
- Fact creation triggers Mem0 embedding generation
- Vector embeddings stored in pgvector (`user_memories` table)
- Metadata stored in PostgreSQL (`user_facts` table)
- Cross-reference via `vector_id` field

### ✅ Task 2: Ollama Integration (COMPLETE - External Service)

**Goal**: Ensure VoxBridge can connect to external Ollama service for fact extraction

**Decision**: Keep Ollama as **shared external service** (not VoxBridge-specific)

**Rationale**:
- Ollama is used by multiple services across the Docker infrastructure
- Deploying Ollama within VoxBridge would duplicate resources
- Current setup on `pinkleberry_bridge` network allows multi-service access
- VoxBridge already successfully connects via `http://ollama:11434`

**Current Configuration**:
- Ollama running on parent Docker network (`pinkleberry_bridge`)
- VoxBridge API connects via shared network
- Model: `gemma3n:latest` for fact extraction
- Environment variable: `LOCAL_LLM_BASE_URL=http://ollama:11434`

**Integration Status**:
- ✅ Network connectivity verified
- ✅ Fact creation working with Ollama LLM
- ✅ Automatic fallback from OpenRouter to Ollama
- ✅ Mem0 successfully uses Ollama for fact extraction

**No changes needed** - current external Ollama setup is optimal for multi-service architecture.

### ✅ Task 3: Build Frontend UI (COMPLETE - 2025-11-23)

**Implementation**: Full CRUD interface for memory management

**Files Created** (3 files, ~1,000 lines):
1. **frontend/src/services/memory.ts** (210 lines) - TypeScript API client
   - 8 functions: listUserFacts, createUserFact, updateUserFact, deleteUserFact, getMemorySettings, updateMemorySettings, exportUserData, deleteAllUserData
   - Full TypeScript interfaces: UserFact, MemorySettings, CreateFactRequest, UpdateFactRequest, GDPRExport
   - Error handling with typed error responses

2. **frontend/src/components/FactCard.tsx** (119 lines) - Fact display component
   - Edit/delete action buttons with confirmation dialogs
   - Color-coded importance badges (green ≥80%, yellow ≥50%, gray <50%)
   - Badges for: importance, agent scope, validity, created date, embedding provider
   - Natural language fact text display
   - Responsive card layout with shadcn/ui

3. **frontend/src/pages/MemoryPage.tsx** (645 lines) - Complete CRUD interface
   - React Query for data fetching and mutations with cache invalidation
   - Create and Edit modals with form validation
   - Filters for agent_id (dropdown) and include_invalid (toggle)
   - Stats cards showing: total facts, global facts, agent-specific facts
   - Settings panel with memory extraction toggle
   - GDPR export (downloads JSON file)
   - GDPR delete with double confirmation
   - Toast notifications for all operations
   - Loading states and error handling

**Routing Integration**:
- Added `/memory` route to `frontend/src/App.tsx`
- Added "Memory" navigation link with Database icon to `frontend/src/components/Navigation.tsx`
- Frontend accessible at http://localhost:4903/memory

**Key Features**:
- Full CRUD operations on facts (Create, Read, Update, Delete)
- Real-time updates via React Query cache invalidation
- Memory extraction toggle (enable/disable automatic fact extraction)
- GDPR compliance (export all data, right to erasure)
- Agent filtering (view facts for specific agents or all agents)
- Validity filtering (include/exclude expired facts)
- Importance slider (0.0-1.0) for manual fact creation
- Form validation with error messages
- Responsive grid layout (1-3 columns based on screen size)

**Deployment**: Frontend rebuilt and deployed successfully (build passed with 0 TypeScript errors)

### ⏳ Task 4: Add Integration Tests (NOT STARTED)

**Test Coverage**:
- E2E conversation flow with memory
- Global vs agent-specific scoping
- GDPR export/delete validation

### ⏳ Task 5: Performance Validation (NOT STARTED)

**Benchmarks**:
- Retrieval latency (target: <100ms)
- Extraction queue processing
- Mem0 accuracy tracking

### ⏳ Task 6: Documentation (NOT STARTED)

**Updates Needed**:
- README.md with memory section
- CLAUDE.md with configuration instructions
- MEMORY.md architecture guide

---

## Known Issues & Future Optimizations

### ✅ RESOLVED: Mem0 Fact Creation Latency (ThreadPoolExecutor Solution)

**Discovered**: 2025-11-23 during frontend testing
**Severity**: High (poor UX, event loop blocking)
**Status**: ✅ **RESOLVED** (2025-11-23) with ThreadPoolExecutor + WebSocket notifications

#### Root Cause Analysis

Manual fact creation via `POST /api/memory/users/{user_id}/facts` took **56 seconds** due to Mem0's architectural limitation:

**The Problem**:
- Mem0's `memory.add()` uses synchronous `concurrent.futures.wait()` in an async context
- This blocked the FastAPI event loop while waiting for two I/O-bound operations:
  1. **LLM fact extraction** (~35 seconds with Ollama gemma3n:latest)
  2. **HuggingFace embedding generation** (~20 seconds with sentence-transformers/all-mpnet-base-v2)
  3. **pgvector storage** (~1 second)

**Evidence**:
```python
# From error traceback:
File "/app/src/routes/memory_routes.py", line 251
    mem0_result = memory_service.memory.add(...)
File "/usr/local/lib/python3.11/site-packages/mem0/memory/main.py", line 373
    concurrent.futures.wait([future1, future2])  # BLOCKS EVENT LOOP
```

**Impact** (before fix):
- Manual fact creation via frontend took 56 seconds with loading spinner
- Discord bot heartbeat failed: "heartbeat blocked for more than 20 seconds"
- All concurrent API requests blocked (entire event loop frozen)
- WebRTC voice chat interruptions
- Poor user experience for memory management UI

**Known Upstream Issue**: Mem0 GitHub Issue #2892 - "AsyncMemory blocking event loop"

#### ✅ Solution Implemented: ThreadPoolExecutor + Real-Time Notifications

**Approach**: Run blocking Mem0 calls in thread pool executor with WebSocket real-time status updates

**Implementation Date**: 2025-11-23

**Results**:
- ✅ Event loop no longer blocked (API remains responsive during extraction)
- ✅ Discord heartbeat healthy
- ✅ Concurrent API requests work normally
- ✅ WebRTC voice chat unaffected
- ✅ Real-time WebSocket notifications for extraction status
- ⚠️ Background processing still takes ~56s (but doesn't block event loop)

**Note**: The 56-second processing time still exists but runs in the background. Users can continue using the application while facts are being extracted. WebSocket notifications keep users informed of progress.

**Implementation Details**:

**Phase 1: ThreadPoolExecutor Integration**
- `src/services/memory_service.py`:
  - Added ThreadPoolExecutor with 2 workers (line 90-94)
  - Wrapped `memory.add()` in automatic extraction with `run_in_executor()` (lines 269-278)
  - Added `__del__()` cleanup method for graceful shutdown (lines 597-602)
  - Modified `_extract_facts_from_turn()` to return facts count (line 305)

- `src/routes/memory_routes.py`:
  - Wrapped `memory.add()` in manual fact creation with `run_in_executor()` (lines 250-259)
  - Fixed event loop blocking for both automatic AND manual fact creation

**Phase 2: WebSocket Real-Time Notifications**
- `src/services/memory_service.py`:
  - Added `ws_manager` parameter to `__init__()` (line 66)
  - Broadcast `memory_extraction_queued` event when task queued (lines 187-197)
  - Broadcast `memory_extraction_processing` event when processing starts (lines 228-240)
  - Broadcast `memory_extraction_completed` event with facts count (lines 257-269)
  - Broadcast `memory_extraction_failed` event on errors (lines 277-290)

- `src/api/server.py`:
  - Connected `ws_manager` to `memory_service` (lines 1216-1217)

- `frontend/src/hooks/useMemoryExtractionStatus.ts` (NEW FILE - 245 lines):
  - WebSocket subscription hook for extraction events
  - Task status tracking (queued → processing → completed/failed)
  - Auto-reconnect with exponential backoff
  - Callbacks for `onCompleted` and `onFailed`

- `frontend/src/pages/MemoryPage.tsx`:
  - Integrated `useMemoryExtractionStatus` hook (lines 59-81)
  - Toast notifications for extraction completion/failure
  - React Query cache invalidation on completion

**Phase 3: Queue Metrics & Observability**
- `src/api/server.py`:
  - Added `GET /api/metrics/extraction-queue` endpoint (lines 702-758)
  - Returns: pending, processing, completed, failed counts
  - Metrics: avg_duration_sec, oldest_pending_age_sec

- `src/services/memory_service.py`:
  - Added periodic queue metrics logging every 60 seconds (lines 293-299)

**Files Modified** (5 backend + 2 frontend):
- Backend: `src/services/memory_service.py`, `src/routes/memory_routes.py`, `src/api/server.py`
- Frontend: `frontend/src/hooks/useMemoryExtractionStatus.ts` (NEW), `frontend/src/pages/MemoryPage.tsx`

**Testing**:
- ✅ Manual fact creation: No event loop blocking
- ✅ Automatic extraction: Queue processing works correctly
- ✅ WebSocket notifications: Toast messages appear in real-time
- ✅ Queue metrics: Endpoint returns correct counts
- ✅ Concurrent requests: Multiple users can create facts simultaneously

#### Solution: Queue-Based Background Processing (NOT YET IMPLEMENTED)

**Approach**: Convert fact creation to asynchronous queue-based processing with WebSocket notifications

**Expected Outcome**:
- API response time: **56s → <100ms** (instant)
- User sees optimistic UI while fact processes in background
- WebSocket notification when fact creation completes
- No event loop blocking (Discord heartbeat healthy)
- Multiple users can create facts concurrently

#### Implementation Plan (8-10 days)

**Phase 1: Backend Queue System** (Days 1-2)
1. Create `FactCreationTask` database model (similar to existing `ExtractionTask`)
   - Fields: id, user_id, agent_id, fact_key, fact_value, status, vector_id, attempts, error_message
   - Migration: `alembic/versions/20251124_create_fact_creation_tasks.py`

2. Extend `MemoryService.process_extraction_queue()` to handle fact creation tasks
   - File: `src/services/memory_service.py`
   - Add `queue_fact_creation()` method (returns task_id immediately)
   - Wrap Mem0 calls in `asyncio.to_thread()` to prevent event loop blocking
   - Add retry logic (max 3 attempts on failure)

3. Update API route to return task_id
   - File: `src/routes/memory_routes.py`
   - Change `create_user_fact()` response to include task_id + status
   - Add `GET /api/memory/tasks/{task_id}` for polling

**Phase 2: WebSocket Notifications** (Days 3-4)
1. Add fact creation events to WebSocket manager
   - File: `src/api/server.py`
   - Events: `fact_creation_started`, `fact_creation_completed`, `fact_creation_failed`

2. Broadcast events from MemoryService
   - File: `src/services/memory_service.py`
   - Emit WebSocket events at key stages (0%, 50%, 100% progress)

**Phase 3: Frontend Integration** (Days 5-7)
1. Update MemoryPage for async creation
   - File: `frontend/src/pages/MemoryPage.tsx`
   - Show optimistic UI (fact card with "Creating..." status)
   - Subscribe to WebSocket events for completion
   - Fallback to polling if WebSocket disconnected

2. Add progress indicator to FactCard
   - File: `frontend/src/components/FactCard.tsx`
   - Show spinner + progress bar for pending/processing facts
   - Disable edit/delete until completed

**Phase 4: Testing & Deployment** (Days 8-10)
- Integration tests for queue processing, WebSocket delivery, retry logic
- Verify existing facts unaffected
- Monitor queue worker performance

**Files to Modify** (8 files, ~600 lines):
- `src/database/models.py` (+50 lines) - FactCreationTask model
- `alembic/versions/20251124_*.py` (+40 lines) - Migration
- `src/services/memory_service.py` (+150 lines) - Queue methods
- `src/routes/memory_routes.py` (+80 lines) - Task endpoints
- `src/api/server.py` (+30 lines) - WebSocket events
- `frontend/src/pages/MemoryPage.tsx` (+150 lines) - Async UI
- `frontend/src/components/FactCard.tsx` (+50 lines) - Progress indicator
- `frontend/src/types/memory.ts` (+20 lines) - Type definitions

#### Optional: Performance Optimization via Settings

**Note**: Users can reduce the 56-second background processing time by configuring faster models via **Settings > Embeddings** area:

**Option 1: Use OpenRouter for LLM Extraction**
- Navigate to Settings > Embeddings
- Configure OpenRouter API key
- Select `gpt-4o-mini` model
- **Result**: LLM extraction 35s → 3s (12x faster)

**Option 2: Use Azure OpenAI for Embeddings**
- Navigate to Settings > Embeddings
- Configure Azure OpenAI credentials
- Select `text-embedding-3-small` model
- **Result**: Embedding generation 20s → 0.2s (100x faster)

**Combined Optimization**: 56s → ~4s total processing time (14x faster)

**Trade-off**: API costs (~$0.0001 per fact) vs. free local processing

#### Alternative Solutions (NOT RECOMMENDED)

1. **asyncio.to_thread() wrapper** (quick fix)
   - Prevents event loop blocking but still takes 56s
   - User still waits with loading spinner
   - 1 hour implementation, low risk

2. **Switch to AsyncMemory** (Mem0's async client)
   - Still uses ThreadPoolExecutor internally (same issue)
   - Waiting for upstream fix (Mem0 issue #2892)

3. **Replace Mem0 entirely** (custom async implementation)
   - Very high complexity (~1000 lines)
   - Lose Mem0's features (deduplication, graph memory)
   - High maintenance burden

**Recommendation**: Implement queue-based solution when ready to prioritize memory UI performance. Until then, the 56-second latency is acceptable for infrequent manual fact creation.

---

### Deliverables

- ✅ API endpoints for user/fact management
- ✅ Frontend UI for viewing/editing facts
- ✅ GDPR-compliant export/delete
- ✅ Integration tests (E2E conversation flow)
- ✅ Performance benchmarks validated
- ✅ Documentation complete

---

## PHASE 3: Advanced Features (Future)

**Goal**: Add temporal reasoning and entity relationship capabilities.

### Tasks

1. **Deploy Zep + Neo4j**:
   - Add Neo4j to docker-compose.yml
   - Add Zep to docker-compose.yml
   - Configure Zep with PostgreSQL + Neo4j backends
   - Set up health checks

2. **Integrate Zep SDK**:
   - Install Zep Python SDK
   - Create episode ingestion pipeline
   - Implement hybrid retrieval (Mem0 → Zep fallback)
   - Backfill existing conversations

3. **Temporal Reasoning**:
   - Implement temporal fact queries API
   - Integrate Graphiti for knowledge graph
   - Add multi-hop relationship queries

4. **Entity Visualization**:
   - Create graph visualization component (React Flow or Cytoscape.js)
   - Add graph export API endpoint
   - Implement interactive exploration

5. **Advanced Retrieval**:
   - Hybrid search (vector + keyword)
   - Cross-encoder re-ranking
   - MMR for diversity

6. **Memory Pruning**:
   - Background job for fact deduplication
   - Memory archival (>1 year old facts)
   - Topic consolidation

### Deliverables

- ✅ Zep + Neo4j self-hosted deployment
- ✅ Temporal fact queries
- ✅ Entity relationship visualization
- ✅ Advanced retrieval features
- ✅ Memory pruning/consolidation
- ✅ <500ms retrieval for complex queries

---

## PHASE 4: Production Hardening (Future)

**Goal**: Ensure production-ready reliability, performance, and maintainability.

### Tasks

1. **Comprehensive Testing**:
   - Unit tests (complete coverage)
   - Integration tests (E2E scenarios)
   - Load tests (100k conversations, <100ms retrieval)
   - Chaos tests (Neo4j downtime, Zep failures)

2. **Performance Optimization**:
   - Add Redis caching for hot queries
   - Batch embedding generation
   - Optimize pgvector HNSW parameters
   - Tune Neo4j memory allocation

3. **Monitoring**:
   - Add memory metrics to MetricsTracker
   - Create memory performance dashboard
   - Alert on extraction failures
   - Track fact count growth

4. **Documentation**:
   - Architecture documentation (MEMORY.md)
   - User guide (how to use memory features)
   - Deployment runbook
   - Troubleshooting guide

### Deliverables

- ✅ Production-ready testing (unit, integration, load, chaos)
- ✅ Performance optimization complete
- ✅ Monitoring dashboard operational
- ✅ Complete documentation (architecture, user guide, runbook)

---

## Success Criteria

**Performance** (Phase 1-2):
- [ ] <100ms retrieval for simple facts (Mem0 + pgvector)
- [ ] >90% fact extraction accuracy (Mem0 baseline: 26% improvement)
- [ ] Zero impact on voice response latency (queue-based extraction)

**Performance** (Phase 3-4):
- [ ] <500ms retrieval for complex queries (Zep + Neo4j)
- [ ] >95% uptime (Neo4j + Zep monitoring)

**Features** (Phase 1-2):
- [x] User facts extracted automatically ✅ DONE
- [x] Memory context in all LLM prompts ✅ DONE
- [x] Multi-agent memory scoping (global + agent-specific) ✅ DONE
- [ ] User profile UI for facts management
- [ ] GDPR-compliant export/delete
- [ ] Memory settings page

**Features** (Phase 3-4):
- [ ] Temporal queries working
- [ ] Relationship tracking working
- [ ] Graph visualization of relationships

**Operations**:
- [x] Self-hosted deployment (PostgreSQL + pgvector) ✅ DONE
- [ ] Automated backups
- [ ] Monitoring dashboard
- [ ] Complete documentation

---

## Risk Mitigation

| Risk | Mitigation | Status |
|------|------------|--------|
| **Azure embeddings not configured** | Fallback to local embeddings (sentence-transformers) | ⚠️ ACTIVE |
| **Mem0 API latency spikes** | Queue-based extraction + graceful degradation | ✅ MITIGATED |
| **Database connection failures** | Retry logic (3 attempts) + error tracking | ✅ MITIGATED |
| **Neo4j high RAM usage** | Phase 3 only - defer until needed | ✅ DEFERRED |
| **Zep API latency** | Phase 3 only - local cache + timeout | ✅ DEFERRED |
| **Complex graph queries slow** | Phase 3 only - query timeout (500ms) | ✅ DEFERRED |

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                    VoxBridge Frontend                         │
│  ┌────────────────────┐  ┌────────────────────────────┐     │
│  │  User Profile      │  │  Memory Settings            │     │
│  │  (Facts, Prefs)    │  │  (LLM Config, GDPR)         │     │
│  └────────────────────┘  └────────────────────────────┘     │
│                  [PHASE 2 - NOT YET IMPLEMENTED]             │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│              VoxBridge API - MemoryService                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Mem0 Framework Integration [PHASE 1 ✅]          │     │
│  │  ├── queue_extraction() - Non-blocking extraction  │     │
│  │  ├── process_extraction_queue() - Background worker│     │
│  │  ├── get_user_memory_context() - Retrieval         │     │
│  │  └── _extract_facts_from_turn() - Mem0 extraction  │     │
│  └────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
           ↓                        ↓
┌──────────────────────┐  ┌──────────────────────────────────┐
│  PostgreSQL 15       │  │  Mem0 Framework                   │
│  ├── users           │  │  ├── Fact extraction              │
│  ├── user_facts      │  │  ├── Deduplication                │
│  ├── extraction_tasks│  │  ├── Semantic search              │
│  └── user_memories   │  │  └── Vector storage (pgvector)    │
│      VECTOR(1536)    │  │                                   │
└──────────────────────┘  └──────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  Embeddings (Configurable)                                    │
│  ├── Azure AI text-embedding-3-large (3072 dims) [PLANNED]   │
│  └── sentence-transformers (768 dims) [DEFAULT]              │
└──────────────────────────────────────────────────────────────┘

[PHASE 3 - FUTURE]
┌──────────────────────┐  ┌──────────────────────────────┐
│  Zep + Graphiti      │  │  Neo4j 5 Community           │
│  ├── Temporal graph  │  │  ├── Entity relationships    │
│  ├── Episode storage │  │  ├── Temporal reasoning      │
│  └── Hybrid search   │  │  └── Multi-hop queries       │
└──────────────────────┘  └──────────────────────────────┘
```

---

## Current Phase Summary

### ✅ Phase 1: Backend Infrastructure (~50% Complete)

**Completed**:
- ✅ Database schema (users, user_facts, extraction_tasks, user_memories)
- ✅ Mem0 framework integration
- ✅ Queue-based extraction (non-blocking)
- ✅ ConversationService integration
- ✅ Memory context injection
- ✅ Agent memory scope (global vs agent-specific)
- ✅ Relevance filtering
- ✅ 21 unit tests (100% passing)

**Missing**:
- ❌ Memory settings API endpoints (including Azure embeddings configuration UI)
- ❌ Fact management API endpoints
- ❌ GDPR export/delete endpoints
- ❌ User profile frontend page
- ❌ Memory settings frontend page
- ❌ Integration tests (E2E conversation flow)
- ❌ Load tests (performance benchmarks)

---

## Next Steps

### Immediate (Complete Phase 1)

1. ~~**Fix Configuration**~~ ✅ **COMPLETED** (2025-11-22):
   - ✅ Local embeddings configured as default
   - ✅ Mem0 using correct embedding dimensions (768)

2. **Implement Memory API Endpoints**:
   - Memory settings (GET/PUT /api/users/{user_id}/memory-settings)
   - Fact management (CRUD /api/users/{user_id}/facts)
   - GDPR export/delete

3. **Build Frontend UI**:
   - User Profile Page (facts viewer, GDPR controls)
   - Memory Settings Page (LLM configuration)

4. **Add Integration Tests**:
   - E2E conversation → extraction → retrieval flow
   - Global vs agent-specific memory scoping

5. **Document**:
   - README.md memory section
   - CLAUDE.md configuration instructions
   - MEMORY.md architecture guide

### Future (Phases 2-4)

- **Phase 2**: User-facing features (API + Frontend + Testing)
- **Phase 3**: Advanced features (Zep, Neo4j, temporal reasoning, visualization)
- **Phase 4**: Production hardening (comprehensive testing, monitoring, docs)

---

## Appendix: Related Documentation

- **VoxBridge 2.0 Plan**: `docs/architecture/voxbridge-2.0-transformation-plan.md`
- **Multi-Agent System**: `docs/architecture/multi-agent-implementation-plan.md`
- **Current Architecture**: `AGENTS.md`, `CLAUDE.md`
- **Database Models**: `src/database/models.py`
- **Service Layer**: `src/services/`
- **Mem0 Documentation**: https://mem0.ai/docs

---

**Document Status**: Active Development
**Current Phase**: Phase 1 (~50% Complete)
**Last Updated**: 2025-11-22
