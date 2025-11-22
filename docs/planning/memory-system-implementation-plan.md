# VoxBridge Memory System - Tentative Implementation Plan

> **⚠️ DRAFT STATUS**: This document is a tentative plan and **STILL NEEDS WORK**. It is **NOT FINALIZED** and subject to significant changes based on further research, testing, and strategic decisions.
>
> **Last Updated**: 2025-11-21
> **Status**: Planning Phase - Awaiting Final Approval
> **Next Steps**: Review, refine architecture decisions, validate technical approaches

---

## Executive Summary

This document outlines a comprehensive, phased approach to implementing a memory system for VoxBridge, incorporating:
- **Provider Pattern Architecture**: Pluggable vector store backends (pgvector, Qdrant, Zep)
- **Azure AI Embeddings**: text-embedding-3-large (3072 dimensions)
- **User-Configurable Extraction**: Reuse existing LLM provider UI
- **Hybrid Memory Scope**: Global by default, agent-specific override
- **Temporal Reasoning**: Zep + Graphiti integration (Phase 2)

**Timeline**: 3 months (12 weeks)
**Approach**: Phased implementation (MVP → Integration → Advanced Features)

---

## Strategic Context

### User Requirements (from Planning Session 2025-11-21)

**Decisions Made**:
1. ✅ **Vector Database**: Provider pattern (start with pgvector, Zep/Qdrant pluggable)
2. ✅ **Embeddings**: Azure AI text-embedding-3-large via Azure OpenAI
3. ✅ **Fact Extraction**: User-configurable LLM (reuse existing provider UI)
4. ✅ **Memory Scope**: Global by default, agent-specific option in agent settings
5. ✅ **Latency Tolerance**: Acceptable (<500ms for complex queries)
6. ✅ **Features Priority**: Simple facts now, temporal/relationships on roadmap
7. ✅ **Deployment**: Self-hosted (full control, ~$150-190/month)
8. ✅ **Timeline**: Patient (2-3 months for comprehensive solution)

### Frameworks Considered

Research conducted on:
- **Zep** (memory layer + Graphiti temporal graph)
- **Mem0** (hybrid vector + KV + graph)
- **GraphRAG** (Microsoft - knowledge graph RAG)
- **LangGraph** (stateful multi-agent orchestration)

**Selected Approach**: Phased hybrid (Custom pgvector MVP → Zep + Graphiti integration)

---

## Architecture Overview

### Three-Tier Memory System

```
Tier 1: Short-Term Cache (ConversationService)
├── In-memory (15-min TTL)
├── Last 10-20 messages
└── Zero latency (<1ms)

Tier 2: Fast Fact Retrieval (pgvector)
├── PostgreSQL + pgvector extension
├── User facts + embeddings
├── <100ms retrieval (local DB)
└── Provider pattern (swappable backend)

Tier 3: Deep Memory (Zep + Graphiti) [Phase 2]
├── Neo4j temporal knowledge graph
├── Entity relationships + temporal reasoning
├── 300-500ms retrieval (complex queries)
└── Self-hosted (full control)
```

### Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Vector Store** | pgvector (Phase 1) → Zep (Phase 2) | Start simple, scale to graph |
| **Embeddings** | Azure AI text-embedding-3-large | 3072 dims, high quality, Azure integration |
| **Graph DB** | Neo4j 5 Community | Temporal reasoning, self-hosted |
| **Memory Framework** | Zep + Graphiti | Bi-temporal model, 94.8% accuracy |
| **Extraction LLM** | User-configurable | Flexibility, reuse existing UI |

---

## PHASE 1: Custom pgvector Foundation (Month 1)

**Goal**: Establish core memory infrastructure with minimal disruption

### Week 1: Database Schema & Provider Interface

**Tasks**:
1. Install pgvector extension in PostgreSQL
2. Create memory tables (users, user_facts, conversation_embeddings, user_preferences, conversation_topics)
3. Implement provider interface (`VectorStoreProvider` abstract class)
4. Implement `PgvectorProvider` and `QdrantProvider` (preparation)
5. Create factory pattern (`VectorStoreFactory.create_provider()`)

**Database Schema**:

```sql
-- Users table (unified identity)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT UNIQUE NOT NULL,
    display_name TEXT,
    email TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    memory_extraction_provider_id UUID REFERENCES llm_providers(id)
);

-- User facts table (core memory)
CREATE TABLE user_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id),  -- NULL = global
    fact_key TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    fact_text TEXT NOT NULL,  -- Natural language
    importance FLOAT DEFAULT 0.5,
    source_conversation_id INTEGER REFERENCES conversations(id),
    first_mentioned_at TIMESTAMPTZ DEFAULT NOW(),
    last_referenced_at TIMESTAMPTZ DEFAULT NOW(),
    reference_count INTEGER DEFAULT 1,
    embedding VECTOR(3072),  -- Azure AI text-embedding-3-large
    validity_start TIMESTAMPTZ DEFAULT NOW(),
    validity_end TIMESTAMPTZ,  -- NULL = currently valid
    UNIQUE(user_id, fact_key, agent_id)
);

-- Indexes
CREATE INDEX idx_user_facts_user_agent ON user_facts(user_id, agent_id);
CREATE INDEX idx_user_facts_embedding ON user_facts USING hnsw (embedding vector_cosine_ops);

-- Conversation embeddings (recall memory)
CREATE TABLE conversation_embeddings (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER UNIQUE REFERENCES conversations(id) ON DELETE CASCADE,
    embedding VECTOR(3072),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_conversation_embeddings ON conversation_embeddings USING hnsw (embedding vector_cosine_ops);

-- User preferences (structured metadata)
CREATE TABLE user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id),
    preference_category TEXT NOT NULL,
    preference_key TEXT NOT NULL,
    preference_value TEXT NOT NULL,
    confidence FLOAT DEFAULT 0.5,
    learned_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, agent_id, preference_category, preference_key)
);

-- Conversation topics (topic tracking)
CREATE TABLE conversation_topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    first_discussed_at TIMESTAMPTZ DEFAULT NOW(),
    last_discussed_at TIMESTAMPTZ DEFAULT NOW(),
    discussion_count INTEGER DEFAULT 1,
    UNIQUE(user_id, agent_id, topic)
);
```

**Provider Interface** (src/memory/providers/base.py):
```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

class VectorStoreProvider(ABC):
    """Abstract interface for vector store backends"""

    @abstractmethod
    async def index_embedding(
        self, collection: str, id: str,
        embedding: List[float], metadata: Dict
    ) -> None:
        """Index embedding with metadata"""
        pass

    @abstractmethod
    async def search_similar(
        self, collection: str, query_embedding: List[float],
        filters: Dict, limit: int, score_threshold: float = 0.7
    ) -> List[Dict]:
        """Search for similar embeddings"""
        pass

    @abstractmethod
    async def delete_embedding(
        self, collection: str, id: str
    ) -> None:
        """Delete embedding by ID"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check provider health"""
        pass
```

**Deliverables**:
- ✅ Alembic migration for memory tables
- ✅ Provider interface and factory pattern
- ✅ PgvectorProvider implementation

---

### Week 2: Azure AI Embeddings & Memory Service

**Tasks**:
1. Create `EmbeddingService` with Azure OpenAI integration
2. Implement `MemoryService` core methods
3. Integrate with `ConversationService` (background indexing)
4. Add memory context injection to LLM prompts

**EmbeddingService** (src/services/embedding_service.py):
- Abstract `EmbeddingProvider` interface
- `AzureOpenAIEmbeddingProvider` implementation
- Batch processing (32-64 texts per request)
- Fallback queue for failed embeddings
- Configuration via existing `llm_providers` table

**MemoryService** (src/services/memory_service.py):

Core methods:
1. `get_user_memory_context(user_id, current_query, session_id, agent_id)` - Retrieve facts + conversations
2. `extract_user_facts(session_id, conversation_text, user_id, extraction_config)` - LLM extraction
3. `index_conversation(conversation_id, content, user_id, agent_id, metadata)` - Embed & store
4. `search_relevant_conversations(user_id, query, agent_id, limit)` - Hybrid search
5. `upsert_user_fact(user_id, fact, agent_id)` - Create/update facts with deduplication

**Integration** (src/services/conversation_service.py):
```python
async def add_message(self, session_id: str, role: str, content: str):
    # Save conversation
    message = await super().add_message(session_id, role, content)

    # Background: Index conversation embedding
    asyncio.create_task(
        memory_service.index_conversation(message.id, content, user_id, agent_id)
    )

    # Background: Extract user facts (if user message)
    if role == "user":
        extraction_config = await get_user_extraction_config(user_id)
        asyncio.create_task(
            memory_service.extract_user_facts(session_id, content, user_id, extraction_config)
        )

    return message
```

**Deliverables**:
- ✅ Azure AI embeddings integration
- ✅ MemoryService implementation
- ✅ Background indexing (non-blocking)
- ✅ Memory context injection into LLM prompts

---

### Week 3: User-Configurable Extraction & Memory Scope

**Tasks**:
1. Add memory settings API endpoints
2. Create memory settings frontend page
3. Extend agent configuration with memory scope
4. Implement global vs agent-specific memory retrieval logic

**Backend API**:
- `PUT /api/users/{user_id}/memory-settings` - Configure extraction LLM
- `GET /api/users/{user_id}/memory-settings` - Get current settings
- Store `memory_extraction_provider_id` in `users` table

**Frontend** (frontend/src/pages/MemorySettingsPage.tsx):
- Tab: "Extraction Configuration"
- LLM provider dropdown (reuse from AgentCard.tsx)
- Model selection (GPT-4o-mini, Claude Haiku, Llama-3.1-8B)
- Temperature slider (default 0.0)
- Test extraction button

**Agent Configuration** (frontend/src/pages/AgentsPage.tsx):
- Add `memory_scope` field: ENUM('global', 'agent_specific', 'hybrid')
- Add `shared_fact_tags` JSONB for hybrid mode
- UI: Dropdown in agent settings

**Memory Retrieval Logic**:
```python
async def get_user_memory_context(self, user_id, query, session_id, agent_id):
    agent = await get_agent(agent_id)

    # Determine fact scope
    if agent.memory_scope == 'global':
        facts = await self._get_global_facts(user_id)
    elif agent.memory_scope == 'agent_specific':
        facts = await self._get_agent_facts(user_id, agent_id)
    else:  # hybrid
        global_facts = await self._get_global_facts(user_id, tags=['name', 'location'])
        agent_facts = await self._get_agent_facts(user_id, agent_id)
        facts = merge(global_facts, agent_facts)

    # Semantic search
    query_embedding = await embedding_service.embed(query)
    relevant_convos = await self.vector_store.search_similar(
        collection="conversations",
        query_embedding=query_embedding,
        filters={"user_id": user_id, "agent_id": agent_id if not global else None},
        limit=5
    )

    return self._format_memory_context(facts, relevant_convos)
```

**Deliverables**:
- ✅ User-configurable extraction LLM
- ✅ Memory settings frontend page
- ✅ Global + agent-specific memory scoping
- ✅ Hybrid memory mode support

---

### Week 4: Frontend Memory Viewer & Testing

**Tasks**:
1. Create user profile page with memory management
2. Implement fact viewing/editing UI
3. Add GDPR export/delete functionality
4. Write comprehensive tests

**User Profile Page** (frontend/src/pages/UserProfilePage.tsx):

Tabs:
1. **Facts** - List, edit, delete, add facts manually
2. **Preferences** - View/override learned preferences
3. **Topics** - Discussion frequency by agent
4. **Settings** - Extraction LLM, data retention, export/import

**API Endpoints**:
- `GET /api/users/{user_id}/facts`
- `POST /api/users/{user_id}/facts`
- `PUT /api/users/{user_id}/facts/{fact_id}`
- `DELETE /api/users/{user_id}/facts/{fact_id}`
- `GET /api/users/{user_id}/export` - GDPR data export
- `POST /api/users/{user_id}/forget` - Delete all user data

**Testing**:
- Unit: VectorStoreProvider mocking, MemoryService fact extraction
- Integration: E2E conversation → extraction → retrieval
- Load: 10k conversations, benchmark <100ms retrieval

**Phase 1 Deliverables**:
- ✅ User facts extracted and stored with Azure AI embeddings
- ✅ Memory context injected into LLM prompts
- ✅ Global + agent-specific memory scoping
- ✅ User profile UI for viewing/editing facts
- ✅ <100ms retrieval latency (pgvector HNSW)
- ✅ Provider pattern (can swap to Qdrant/Zep later)

---

## PHASE 2: Zep + Graphiti Integration (Month 2)

**Goal**: Add temporal reasoning and entity relationship capabilities

### Week 5: Self-Hosted Zep + Neo4j Deployment

**Tasks**:
1. Add Neo4j to docker-compose.yml
2. Add Zep to docker-compose.yml
3. Configure Zep to use PostgreSQL + Neo4j backends
4. Set up health checks and monitoring

**Docker Compose Extension**:
```yaml
services:
  neo4j:
    image: neo4j:5-community
    container_name: voxbridge-neo4j
    ports:
      - "7474:7474"  # HTTP
      - "7687:7687"  # Bolt
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_dbms_memory_heap_max__size: 4G
      NEO4J_dbms_memory_pagecache_size: 2G
    volumes:
      - neo4j-data:/data
      - neo4j-logs:/logs
    restart: unless-stopped
    networks:
      - bot-network

  zep:
    image: ghcr.io/getzep/zep:latest
    container_name: voxbridge-zep
    ports:
      - "8000:8000"
    environment:
      ZEP_STORE_TYPE: postgres
      ZEP_STORE_POSTGRES_DSN: postgresql://voxbridge:${POSTGRES_PASSWORD}@postgres:5432/voxbridge
      ZEP_GRAPH_STORE_TYPE: neo4j
      ZEP_GRAPH_STORE_NEO4J_URI: bolt://neo4j:7687
      ZEP_OPENAI_API_KEY: ${OPENAI_API_KEY}
    depends_on:
      - postgres
      - neo4j
    restart: unless-stopped
    networks:
      - bot-network
```

**Deliverables**:
- ✅ Neo4j deployed and configured
- ✅ Zep deployed and integrated with PostgreSQL + Neo4j
- ✅ Health checks operational

---

### Week 6: Zep SDK Integration & Episode Ingestion

**Tasks**:
1. Install Zep Python SDK
2. Implement `ZepProvider` (VectorStoreProvider interface)
3. Create episode ingestion pipeline
4. Implement hybrid retrieval (pgvector → Zep fallback)
5. Backfill existing conversations into Zep

**ZepProvider** (src/memory/providers/zep_provider.py):
```python
from zep_cloud import Zep

class ZepProvider(VectorStoreProvider):
    def __init__(self, api_url: str = "http://zep:8000"):
        self.client = Zep(api_url=api_url)

    async def index_episode(
        self, session_id: str, user_id: str,
        role: str, content: str, metadata: Dict
    ):
        await self.client.memory.add_episode(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            metadata=metadata
        )
```

**Hybrid Retrieval**:
```python
async def get_user_memory_context(self, user_id, query, session_id, agent_id):
    # Tier 1: Local cache (pgvector) - fast facts
    local_facts = await self.pgvector_provider.search_similar(...)

    # Tier 2: Zep graph search - temporal reasoning
    zep_results = await self.zep_provider.search_memory(...)

    # Merge and rank
    combined = self._merge_memory_results(local_facts, zep_results)
    return self._format_memory_context(combined)
```

**Deliverables**:
- ✅ Zep SDK integrated
- ✅ Episode ingestion pipeline
- ✅ Hybrid retrieval working
- ✅ Existing conversations backfilled

---

### Week 7: Temporal Reasoning & Graph Queries

**Tasks**:
1. Implement temporal fact queries API
2. Integrate Graphiti for temporal knowledge graph
3. Add multi-hop relationship queries
4. Test temporal reasoning features

**Temporal Queries**:
- `GET /api/users/{user_id}/facts/timeline` - Facts over time
- `GET /api/users/{user_id}/facts/compare?t1={timestamp1}&t2={timestamp2}` - Compare time periods

**Graphiti Integration**:
```python
async def query_temporal_facts(
    self, user_id: str, fact_key: str,
    start_time: datetime, end_time: datetime
):
    """Query how a fact changed over time"""
    query = """
    MATCH (u:User {id: $user_id})-[:HAS_FACT]->(f:Fact {key: $fact_key})
    WHERE f.valid_from >= $start_time AND f.valid_from <= $end_time
    RETURN f.value, f.valid_from, f.valid_to
    ORDER BY f.valid_from
    """
    return await self.graphiti.execute_query(query, ...)
```

**Deliverables**:
- ✅ Temporal fact queries operational
- ✅ Graphiti integrated
- ✅ Multi-hop relationship queries

---

### Week 8: Performance Optimization & Monitoring

**Tasks**:
1. Add in-memory caching (Redis or LRU)
2. Implement batch processing for embeddings
3. Add memory metrics to MetricsTracker
4. Create memory performance dashboard

**Metrics**:
- `embedding_latency_ms` - Azure AI embedding time
- `fact_extraction_latency_ms` - LLM extraction time
- `memory_search_latency_ms` - Vector + graph search time
- `zep_query_latency_ms` - Zep API latency
- `memory_retrieval_count` - Retrieval frequency
- `fact_extraction_success_rate` - Accuracy

**Phase 2 Deliverables**:
- ✅ Zep + Graphiti self-hosted deployment
- ✅ Temporal fact queries working
- ✅ Relationship tracking operational
- ✅ Multi-hop reasoning (graph traversal)
- ✅ <500ms retrieval for complex queries
- ✅ Hybrid retrieval (pgvector fast, Zep deep)

---

## PHASE 3: Advanced Features & Optimization (Month 3)

### Week 9: Entity Relationship Visualization

**Tasks**:
1. Create graph visualization component (Cytoscape.js or React Flow)
2. Add graph export API endpoint
3. Implement interactive exploration (click entity → show facts)
4. Add timeline scrubbing for temporal changes

**API**:
- `GET /api/users/{user_id}/memory-graph` - Export Neo4j subgraph as JSON

---

### Week 10: Advanced Retrieval Features

**Tasks**:
1. Implement hybrid search (vector + keyword)
2. Add cross-encoder re-ranking
3. Implement MMR for diversity
4. Benchmark and tune performance

**Features**:
- Hybrid search: 70% semantic + 30% keyword
- Re-ranking: `cross-encoder/ms-marco-MiniLM-L-6-v2`
- MMR: λ=0.7 (relevance vs diversity)

---

### Week 11: Memory Pruning & Consolidation

**Tasks**:
1. Create background job for fact deduplication
2. Implement memory archival (>1 year old facts)
3. Add topic consolidation
4. Build user controls for retention policies

**Background Jobs**:
- Fact deduplication (weekly)
- Memory archival (monthly)
- Topic consolidation (weekly)

---

### Week 12: Production Hardening & Documentation

**Tasks**:
1. Comprehensive testing (unit, integration, load, chaos)
2. Write architecture documentation
3. Create user guide
4. Write deployment runbook

**Testing**:
- Load: 100k conversations, <100ms retrieval
- Chaos: Neo4j downtime, Zep failures (graceful degradation)

**Phase 3 Deliverables**:
- ✅ Entity relationship visualization
- ✅ Advanced retrieval (hybrid, re-ranking, MMR)
- ✅ Memory pruning & consolidation
- ✅ Production-ready (testing, docs, monitoring)
- ✅ GDPR-compliant (export, delete)

---

## Success Criteria

**Performance**:
- [ ] <100ms retrieval for simple facts (pgvector)
- [ ] <500ms retrieval for complex queries (Zep)
- [ ] >90% fact extraction accuracy
- [ ] >95% uptime (Neo4j + Zep monitoring)

**Features**:
- [ ] User facts extracted automatically
- [ ] Memory context in all LLM prompts
- [ ] Temporal queries working
- [ ] Relationship tracking working
- [ ] Multi-agent memory scoping (global + agent-specific)

**User Experience**:
- [ ] User profile UI for facts management
- [ ] Graph visualization of relationships
- [ ] Memory settings page
- [ ] GDPR-compliant export/delete

**Operations**:
- [ ] Self-hosted deployment (PostgreSQL + Neo4j + Zep)
- [ ] Automated backups
- [ ] Monitoring dashboard
- [ ] Complete documentation

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| **Neo4j high RAM usage** | Use FalkorDB alternative, tune heap size |
| **Zep API latency spikes** | Local cache, timeout with fallback |
| **Azure AI embedding costs** | Batch processing, monitor spend |
| **Complex graph queries slow** | Query timeout (500ms), fallback |
| **Data privacy concerns** | Self-hosted only, encryption at rest |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    VoxBridge Frontend                        │
│  ┌────────────────────┐  ┌────────────────────────────┐    │
│  │  User Profile      │  │  Memory Graph View          │    │
│  │  (Facts, Prefs)    │  │  (Entity Relationships)     │    │
│  └────────────────────┘  └────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              VoxBridge API - MemoryService                   │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Provider Pattern (VectorStoreProvider)            │    │
│  │  ├── PgvectorProvider (fast facts)                 │    │
│  │  ├── ZepProvider (temporal + relationships)        │    │
│  │  └── QdrantProvider (future scalability)           │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
           ↓                        ↓
┌──────────────────────┐  ┌──────────────────────────────┐
│  PostgreSQL 15       │  │  Zep + Graphiti              │
│  ├── users           │  │  ├── Neo4j (graph DB)        │
│  ├── user_facts      │  │  ├── Temporal reasoning      │
│  ├── embeddings      │  │  ├── Entity extraction       │
│  └── pgvector HNSW   │  │  └── Hybrid search           │
└──────────────────────┘  └──────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│                  Azure AI (text-embedding-3-large)            │
└──────────────────────────────────────────────────────────────┘
```

---

## Next Steps (Before Implementation)

**Outstanding Questions**:
1. Azure OpenAI endpoint configuration details
2. Neo4j resource allocation (4GB heap sufficient?)
3. User authentication model (Discord ID vs unified user model)
4. Data retention policy defaults (30 days? 1 year? Forever?)
5. Extraction prompt templates (need examples for each LLM provider)
6. Graph visualization library selection (Cytoscape.js vs React Flow)

**Required Research**:
1. Azure AI pricing for text-embedding-3-large at VoxBridge scale
2. Neo4j Community vs Enterprise features comparison
3. Zep self-hosted vs cloud cost-benefit analysis
4. pgvector HNSW tuning for 3072-dimensional vectors
5. Temporal fact invalidation strategies (when to mark facts as outdated)

**Stakeholder Approvals Needed**:
1. Azure AI budget approval
2. Neo4j deployment approval (~$150-190/month AWS cost)
3. Memory feature scope prioritization (which Phase 1-3 features are MVP?)
4. GDPR compliance review (legal team)

---

## Appendix: Related Documentation

- **VoxBridge 2.0 Plan**: `docs/architecture/voxbridge-2.0-transformation-plan.md`
- **Multi-Agent System**: `docs/architecture/multi-agent-implementation-plan.md`
- **Current Architecture**: `AGENTS.md`, `CLAUDE.md`
- **Database Models**: `src/database/models.py`
- **Service Layer**: `src/services/`

---

**Document Status**: DRAFT / TENTATIVE
**Author**: Claude Code (AI Assistant)
**Review Required**: Yes
**Approval Status**: Pending
