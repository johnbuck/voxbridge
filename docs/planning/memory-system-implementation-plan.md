# VoxBridge Memory System - Implementation Plan

> **Status**: Active Development - Phase 1 In Progress (~50% Complete)
>
> **Last Updated**: 2025-11-22
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

---

## PHASE 2: User-Facing Features (Not Started)

**Goal**: Complete the memory system with user-accessible UI and API endpoints.

### Tasks

1. **Implement Memory API Endpoints**:
   - Memory settings (GET/PUT)
   - Fact management (GET/POST/PUT/DELETE)
   - GDPR export/delete

2. **Build Frontend UI**:
   - User Profile Page with fact viewer
   - Memory Settings Page
   - FactCard component
   - Memory metrics dashboard

3. **Add Integration Tests**:
   - E2E conversation flow with memory
   - Global vs agent-specific scoping
   - GDPR export/delete validation

4. **Performance Validation**:
   - Benchmark retrieval latency (target: <100ms)
   - Monitor extraction queue processing
   - Track Mem0 accuracy

5. **Documentation**:
   - Update README.md with memory section
   - Update CLAUDE.md with configuration instructions
   - Create MEMORY.md architecture guide

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
