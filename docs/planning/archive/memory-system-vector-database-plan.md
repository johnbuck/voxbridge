# VoxBridge Memory System - Implementation Plan

> ⚠️ **ARCHIVED**: Historical architecture reference document
>
> **Archived**: 2025-12-05
> **Reason**: Implementation complete, see `docs/planning/memory-system-enhancements.md` for current status

---

**Status**: FINAL / APPROVED → **✅ IMPLEMENTED**
**Last Updated**: 2025-11-21
**Vector Database**: pgvectorscale (PostgreSQL extension)
**Framework**: Mem0 (Apache 2.0, self-hosted)
**Embeddings**: Azure AI text-embedding-3-large (3072 dimensions)
**Fact Extraction**: Real-time with LLM relevance filtering
**Caching**: Optional Redis layer (Phase 6 - Future Enhancement)
**Frontend**: Full-stack memory viewer UI

---

## ✅ APPROVED ARCHITECTURE

This document describes the **final approved architecture** for VoxBridge memory system.

**Key Architectural Decisions**:
- ✅ **Vector Database**: pgvectorscale (11x throughput, zero deployment complexity)
- ✅ **Framework**: Mem0 (Apache 2.0, 26% accuracy improvement, self-hosted)
- ✅ **Embeddings**: Configurable (Azure AI text-embedding-3-large OR local open-source models)
- ✅ **Fact Extraction**: Real-time per-turn with LLM relevance filtering
- ⏳ **Caching**: Redis (optional Phase 6 enhancement, not required for v1)
- ✅ **Memory Scope**: Global by default, agent-specific option in agent settings

---

## 📋 Implementation Guide

This document describes the **approved VoxBridge memory system architecture** using:
- **Vector Store**: pgvectorscale (PostgreSQL extension)
- **Framework**: Mem0 (handles fact extraction, storage, retrieval)
- **Embeddings**: Configurable (Azure AI OR local models)

**Key Sections**:
- **Phase 1**: PostgreSQL Extension Setup (pgvectorscale + Mem0)
- **Phase 2**: Mem0 Framework Integration
- **Phase 3**: Database Schema & Models
- **Phase 4**: Memory Retrieval & Context Injection
- **Phase 5**: Frontend Memory Viewer UI
- **Phase 6**: Redis Caching (optional enhancement)

**Future Migration**: If performance requirements exceed pgvectorscale capabilities, we can migrate to Qdrant using Mem0's provider switching (see "Migration Strategy" section)

---

## 🚀 Quick Implementation Summary

**What Changed from Original Plan:**
1. **Qdrant → pgvectorscale**: Use PostgreSQL extension instead of separate container
2. **Custom Extraction → Mem0**: Use battle-tested framework (90% less code, 26% better accuracy)
3. **Embeddings**: Configurable provider (Azure AI OR local open-source models, user choice)
4. **Always Extract → LLM Relevance Filter**: Only extract when data is actually relevant
5. **Redis Caching**: Moved to Phase 6 (optional enhancement, not required for v1)

**Mem0 Framework Integration (Configurable Embeddings):**

```python
from mem0 import Memory
import os

# Select embedding provider via environment variable
embedding_provider = os.getenv("EMBEDDING_PROVIDER", "azure")  # "azure" or "local"

# Azure AI Embeddings (3072 dimensions, $0.13 per 1M tokens)
if embedding_provider == "azure":
    embedder_config = {
        "provider": "azure_openai",
        "config": {
            "model": "text-embedding-3-large",
            "embedding_dims": 3072,
            "azure_kwargs": {
                "api_version": os.getenv("AZURE_EMBEDDING_API_VERSION", "2024-12-01-preview"),
                "azure_deployment": os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"),
                "azure_endpoint": os.getenv("AZURE_EMBEDDING_ENDPOINT"),
                "api_key": os.getenv("AZURE_EMBEDDING_API_KEY")
            }
        }
    }
# Local Open-Source Embeddings (768-1024 dimensions, free, runs in container)
elif embedding_provider == "local":
    embedder_config = {
        "provider": "huggingface",
        "config": {
            "model": os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"),
            "embedding_dims": int(os.getenv("LOCAL_EMBEDDING_DIMS", "768"))
        }
    }

# Mem0 Configuration
config = {
    "vector_store": {
        "provider": "pgvector",
        "config": {
            "dbname": "voxbridge",
            "host": "postgres",
            "collection_name": "user_memories"
        }
    },
    "llm": {
        "provider": "openai",
        "config": {
            "model": "gpt-4o-mini",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": os.getenv("OPENROUTER_API_KEY")
        }
    },
    "embedder": embedder_config
}

memory = Memory.from_config(config)

# Add facts with relevance filtering
if await should_extract_facts(user_message, ai_response):
    await memory.add(
        user_id=user_id,
        messages=[
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": ai_response}
        ],
        metadata={"agent_id": str(agent_id)}
    )

# Search with context injection
results = await memory.search(
    query=user_message,
    user_id=user_id,
    agent_id=str(agent_id),
    limit=5
)
```

**Installation Steps:**
1. Install pgvectorscale: `CREATE EXTENSION vectorscale CASCADE;` (Alembic migration)
2. Install Mem0: `pip install mem0ai` (add to requirements-bot.txt)
3. **Choose embedding provider**: Configure Azure AI OR local model in `.env`
   - **Azure AI**: Set `EMBEDDING_PROVIDER=azure` + Azure credentials (costs $1/month)
   - **Local**: Set `EMBEDDING_PROVIDER=local` + model name (free, runs in container)
4. (Optional) Install Redis for caching: Add to docker-compose.yml (Phase 6)

**Note**: Some code examples in this document still reference Qdrant/custom providers for historical context. Use the Mem0 integration pattern shown above for actual implementation.

---

## Executive Summary

VoxBridge will implement a three-tier conversational memory system using **Mem0 framework** with **pgvectorscale**:

1. **Short-Term Memory**: In-memory conversation cache (15-minute TTL, existing ConversationService)
2. **Long-Term Memory**: Mem0 + pgvectorscale (user facts extracted from conversations, 3072-dimension embeddings)
3. **Relational Metadata**: PostgreSQL (user preferences, fact metadata, temporal tracking)

**Why Mem0?**
- ✅ **Apache 2.0 License**: Fully open-source, self-hostable
- ✅ **26% Accuracy Improvement**: Over custom extraction logic
- ✅ **Dual-Phase Extraction**: Extract facts → Update existing facts (intelligent deduplication)
- ✅ **90% Less Code**: Battle-tested framework vs custom implementation
- ✅ **Automatic Deduplication**: Semantic similarity matching prevents duplicate facts
- ✅ **Multi-Provider Support**: Works with Azure AI, OpenAI, local LLMs

**Why pgvectorscale over Qdrant?**
- ✅ **11x Better Throughput**: 471.57 QPS vs 41.47 QPS (99% recall)
- ✅ **Zero Deployment Complexity**: PostgreSQL extension (no separate container)
- ✅ **75% Less Memory**: ~2GB for 100K vectors vs ~8GB Qdrant
- ✅ **ACID Transactions**: No data consistency issues (Qdrant requires eventual consistency)
- ✅ **StreamingDiskANN**: Disk-based indexing scales to millions of vectors
- ✅ **Proven at Scale**: Discord uses pgvector at billions of vectors

**Expected Performance** (pgvectorscale benchmarks):
- **Query Latency**: 31ms p50, 60ms p95, 74ms p99 at 99% recall
- **Throughput**: 471.57 QPS at 99% recall (11x better than Qdrant)
- **Scalability**: 10K → 100K → 1M+ vectors with consistent performance
- **Resource Requirements**: ~2GB RAM for 100K vectors, ~12GB RAM for 1M vectors

**Latency Trade-off Accepted**:
- pgvectorscale p95: 60ms vs Qdrant p95: 37ms (23ms difference)
- **Analysis**: 23ms = 1% of 2-second conversation turn, not user-perceptible
- **Rationale**: 11x throughput + zero deployment complexity >> 23ms latency difference

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Technology Research Summary](#technology-research-summary)
3. [Phase 1: pgvectorscale Infrastructure](#phase-1-pgvectorscale-infrastructure)
4. [Phase 2: Mem0 Framework Integration](#phase-2-mem0-framework-integration)
5. [Phase 3: LLM Relevance Filtering & Fact Extraction](#phase-3-llm-relevance-filtering--fact-extraction)
6. [Phase 4: Memory Retrieval & Context Injection](#phase-4-memory-retrieval--context-injection)
7. [Phase 5: Frontend Memory Viewer UI](#phase-5-frontend-memory-viewer-ui)
8. [Phase 6: Redis Caching (Optional Enhancement)](#phase-6-redis-caching-optional-enhancement)
9. [Database Schema](#database-schema)
10. [Testing Strategy](#testing-strategy)
11. [Monitoring & Metrics](#monitoring--metrics)
12. [Migration Strategy](#migration-strategy)
13. [Cost Analysis](#cost-analysis)

---

## Architecture Overview

### System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│             VoxBridge Memory System (Mem0 + pgvectorscale)          │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  Discord Voice   │      │  WebRTC Voice    │      │  Frontend UI     │
│  (Discord Bot)   │      │  (Browser)       │      │  (Memory Viewer) │
└────────┬─────────┘      └────────┬─────────┘      └────────┬─────────┘
         │                         │                         │
         └─────────────────────────┼─────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   ConversationService       │
                    │   (Short-term cache)        │
                    └──────────────┬──────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
         ▼                         ▼                         ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  LLMService     │      │  Mem0 Memory    │      │ PostgreSQL 15   │
│  (AI responses) │      │  (Framework)    │      │ (pgvectorscale) │
└────────┬────────┘      └────────┬────────┘      └─────────┬───────┘
         │                        │                         │
         │              ┌─────────▼─────────┐               │
         │              │  LLM Relevance    │               │
         │              │  Filter           │               │
         │              └─────────┬─────────┘               │
         │                        │                         │
         │              ┌─────────▼─────────┐               │
         │              │  Azure AI         │               │
         │              │  Embeddings       │               │
         │              │  (3072-dim)       │               │
         │              └─────────┬─────────┘               │
         │                        │                         │
         │                        ▼                         │
         └───────────────────────────────────────────────────┘
                                  │
                        ┌─────────▼─────────┐
                        │  pgvectorscale    │
                        │  (Vector index)   │
                        │  StreamingDiskANN │
                        └───────────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  [Phase 6] Redis Cache     │
                    │  (Optional Enhancement)    │
                    └────────────────────────────┘
```

### Data Flow

**1. User sends message** (Discord or WebRTC):
```
User Message → ConversationService → Mem0.search()
                      ↓                    ↓
                 STTService          pgvectorscale
                                (search similar facts)
                                      ↓
                                LLMService
                            (context-injected prompt)
                                      ↓
                                 AI Response
```

**2. Real-time fact extraction with relevance filtering**:
```
Conversation Turn → LLM Relevance Filter
                         ↓
              "Is this data relevant to store?"
                         ↓
                    (if yes) → Mem0.add()
                                  ↓
                    Mem0 Extract & Update Logic
                                  ↓
              ┌───────────────────┴─────────────────┐
              ▼                                     ▼
    Azure AI Embeddings                    PostgreSQL
    (direct API call)                      (metadata)
              ↓                                     ↓
         pgvectorscale ←──────────────────────────┘
      (vector index + ACID)
```

**3. Memory-aware AI response with Mem0**:
```
User Query → Mem0.search(query, user_id, agent_id)
                  ↓
          Azure AI (embed query)
                  ↓
          pgvectorscale (search top-k facts)
                  ↓
          Mem0 formats context string
                  ↓
          LLMService (inject into system prompt)
                  ↓
          AI Response (memory-aware)
```

---

## Technology Research Summary

### Why pgvectorscale + Mem0?

After comprehensive research comparing vector databases (**pgvector**, **pgvectorscale**, **Qdrant**, **Milvus**, **Weaviate**, **Chroma**, **LanceDB**) and memory frameworks (**Mem0**, **Letta**, **OpenMemory**, **LangChain Memory**, **custom**), we selected **pgvectorscale + Mem0** for the following reasons:

#### Performance Benchmarks (99% Recall)

| Metric | pgvector HNSW | **pgvectorscale** | Qdrant | Winner |
|--------|---------------|-------------------|--------|--------|
| **QPS** | ~50-100 | **471.57** | 41.47 | ✅ pgvectorscale (11x) |
| **p50 Latency** | 20-50ms | 31ms | 31ms | ✅ Tie |
| **p95 Latency** | 60-100ms | 60ms | 37ms | ⚠️ Qdrant (+23ms) |
| **p99 Latency** | 100-200ms | 74ms | 39ms | ⚠️ Qdrant (+35ms) |
| **Memory (100K)** | ~5GB | **~2GB** | ~8GB | ✅ pgvectorscale (75% less) |
| **Memory (1M)** | ~50GB | **~12GB** | ~40GB | ✅ pgvectorscale (70% less) |
| **Deployment** | PostgreSQL ext | **PostgreSQL ext** | +1 container | ✅ pgvectorscale (zero complexity) |
| **ACID Transactions** | ✅ | ✅ | ❌ (eventual consistency) | ✅ pgvectorscale |

**Key Insights**:
- **pgvectorscale wins decisively**: 11x throughput, 75% less memory, zero deployment complexity
- **Latency trade-off is acceptable**: 23ms p95 difference = 1% of conversation time (not user-perceptible)
- **ACID transactions eliminate data consistency issues**: No PostgreSQL ↔ Qdrant synchronization bugs
- **Proven at scale**: Discord uses pgvector at billions of vectors

#### Why pgvectorscale over Qdrant?

**Advantages of pgvectorscale**:
1. ✅ **11x Better Throughput**: 471.57 QPS vs 41.47 QPS (99% recall)
2. ✅ **Zero Deployment Complexity**: PostgreSQL extension (no separate container)
3. ✅ **75% Less Memory**: ~2GB for 100K vectors vs ~8GB Qdrant
4. ✅ **ACID Transactions**: Eliminates data consistency issues (PostgreSQL ↔ Qdrant sync)
5. ✅ **StreamingDiskANN**: Disk-based indexing scales to millions of vectors
6. ✅ **Proven at Scale**: Discord uses pgvector at billions of vectors
7. ✅ **Lower TCO**: $0 infrastructure cost (uses existing PostgreSQL)

**Trade-offs Accepted**:
- ⚠️ **Higher p95 Latency**: 60ms vs 37ms Qdrant (+23ms)
- ⚠️ **Higher p99 Latency**: 74ms vs 39ms Qdrant (+35ms)

**Rationale**: 23ms latency difference = **1% of 2-second conversation turn** (not user-perceptible). The 11x throughput advantage, zero deployment complexity, and ACID transactions far outweigh the minor latency cost.

#### Why Mem0 Framework?

**Mem0 vs Custom Implementation**:
- ✅ **Apache 2.0 License**: Fully open-source, self-hostable
- ✅ **26% Accuracy Improvement**: Over custom extraction logic (benchmarked)
- ✅ **90% Less Code**: Battle-tested framework vs custom implementation
- ✅ **Automatic Deduplication**: Semantic similarity matching prevents duplicate facts
- ✅ **Dual-Phase Extraction**: Extract facts → Update existing facts (intelligent merge)
- ✅ **Multi-Provider Support**: Works with Azure AI, OpenAI, local LLMs
- ✅ **Active Development**: 24K+ GitHub stars, strong community

**Mem0 vs Alternatives** (Letta, OpenMemory, LangChain Memory):
- Letta: More complex (agent-focused), not purely memory-focused
- OpenMemory: Less mature, smaller community
- LangChain Memory: Good but requires full LangChain stack (VoxBridge uses OpenRouter/local LLMs)

**Conclusion**: Mem0 provides best-in-class memory extraction with minimal code overhead.

---
## pgvectorscale Decision (Implementation Note)

**Decision Date**: November 21, 2025
**Status**: ✅ Deferred to v2+ (pgvector-only for v1)

### Executive Summary

VoxBridge v1 will use **pgvector-only** (without pgvectorscale). This is the correct architectural decision for the expected scale and complexity requirements.

### What is pgvectorscale?

**pgvectorscale** is a PostgreSQL extension developed by Timescale that adds performance optimizations on top of pgvector:

- **StreamingDiskANN Index**: Disk-based approximate nearest neighbor search (vs in-memory HNSW)
- **Statistical Binary Quantization**: Memory-efficient vector compression
- **Performance**: 11x throughput improvement (471 QPS vs 41 QPS for Qdrant)
- **Memory Savings**: 75% reduction (2GB vs 8GB for 100K vectors)

### Why pgvector-only for v1?

**1. Scale Mismatch**
- VoxBridge v1 expected scale: 10K-50K facts (Year 1)
- pgvectorscale benefits kick in at: 100K+ facts (Year 2+)
- pgvector HNSW performs excellently at v1 scale: <50ms p50 latency, <100 QPS

**2. Complexity vs Benefit**
- pgvectorscale installation options:
  - ❌ Not in standard `pgvector/pgvector:pg15` Docker image
  - ⚠️ Requires PostgreSQL 16 migration (via TimescaleDB-HA image)
  - ⚠️ OR custom Dockerfile with Rust/PGRX build process (10-20 min builds)
- Current pgvector setup: ✅ 2-minute deployment, zero custom builds

**3. Mem0 Compatibility**
- ✅ Mem0 works 100% with pgvector alone
- ✅ pgvectorscale is purely a performance optimization, not a functional requirement
- ✅ Drop-in upgrade path when needed (Mem0 auto-detects StreamingDiskANN)

**4. Cost-Benefit Analysis (v1 Scale)**

| Metric | pgvector HNSW | pgvectorscale | Impact |
|--------|---------------|---------------|--------|
| Query Latency (50K vectors) | 20-50ms p50 | 31ms p50 | ⚪ Negligible (within budget) |
| Throughput | 50-100 QPS | 471 QPS | ⚪ Overkill (v1 needs <10 QPS) |
| Memory Usage | ~2.5GB | ~1.5GB | ⚪ Minimal savings |
| Deployment Complexity | ✅ Simple | ❌ Complex | ✅ Favor simplicity |

### When to Add pgvectorscale?

**Upgrade Triggers** (monitor these metrics):
- ⚠️ PostgreSQL memory usage >8GB for vector storage
- ⚠️ HNSW index build times >30 minutes
- ⚠️ Query latency p95 >100ms
- ⚠️ Vector count >100K facts

**Expected Timeline**: Year 2+ (when reaching 100K+ facts)

**Estimated User Scale**:
- 10K facts = ~100 users × 100 facts each
- 50K facts = ~500 users × 100 facts each (v1 target)
- 100K facts = ~1,000 users × 100 facts each (upgrade threshold)

### Upgrade Path (Future)

**When Ready** (Year 2+):

**Option A: Migrate to PostgreSQL 16 + TimescaleDB** (Recommended):
```yaml
# docker-compose.yml
postgres:
  image: timescale/timescaledb-ha:pg16  # Changed from pgvector/pgvector:pg15
```

```bash
# Migration steps
1. Backup: docker exec voxbridge-postgres pg_dump -U voxbridge voxbridge > backup.sql
2. Stop: docker compose down
3. Update docker-compose.yml
4. Start: docker compose up -d postgres
5. Restore: cat backup.sql | docker exec -i voxbridge-postgres psql -U voxbridge -d voxbridge
6. Install: docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "CREATE EXTENSION vectorscale CASCADE;"
7. Verify: docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "\dx"
```

**Option B: Build Custom PostgreSQL 15 Image** (if PG15 required):
- Requires Rust toolchain + PGRX framework
- 10-20 minute builds, custom image maintenance
- See [pgvectorscale GitHub](https://github.com/timescale/pgvectorscale) for build instructions

### Monitoring Recommendations

Add these monitoring queries to track when pgvectorscale becomes necessary:

```bash
# Monitor PostgreSQL memory usage
docker stats voxbridge-postgres --no-stream --format "{{.MemUsage}}"

# Monitor vector table size
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "
  SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size('public.' || tablename)) AS total_size,
    pg_size_pretty(pg_indexes_size('public.' || tablename)) AS index_size
  FROM pg_tables
  WHERE schemaname = 'public' AND tablename LIKE '%mem0%'
  ORDER BY pg_total_relation_size('public.' || tablename) DESC;
"

# Count total vectors
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "
  SELECT COUNT(*) as total_facts FROM user_facts;
"
```

**Alert Thresholds**:
- 🟡 Warning: 50K+ facts OR 5GB+ memory usage
- 🔴 Critical: 100K+ facts OR 8GB+ memory usage OR build time >30min

### Decision Rationale

**Architectural Principle**: Start simple, optimize when data proves it necessary.

**Key Quote** from Timescale docs:
> "For datasets under 100,000 vectors, pgvector's HNSW index is highly effective.
> pgvectorscale's benefits become significant at larger scales where memory constraints
> and build times become bottlenecks."

**VoxBridge v1 Reality**:
- ✅ Expected scale: 10K-50K facts (well under 100K threshold)
- ✅ pgvector HNSW proven at this scale (50ms latency, no warnings)
- ✅ Avoid premature optimization (YAGNI principle)
- ✅ Clear upgrade path when metrics indicate need

### References

- [pgvectorscale GitHub](https://github.com/timescale/pgvectorscale)
- [Timescale Blog: pgvectorscale Launch](https://www.timescale.com/blog/pgvector-is-now-as-fast-as-pinecone-at-75-less-cost/)
- [Mem0 pgvector Documentation](https://docs.mem0.ai/components/vectordbs/dbs/pgvector)
- [PostgreSQL HNSW Index Documentation](https://github.com/pgvector/pgvector#hnsw)

---


## Phase 1: pgvector Infrastructure ✅ IMPLEMENTED

**Status**: ✅ Complete (November 21, 2025)
**Actual Implementation**: pgvector-only (pgvectorscale deferred to v2+)

### PostgreSQL Extension Setup

#### Tasks

1. **Install pgvector Extension** ✅ COMPLETED

pgvector is a PostgreSQL extension, no additional Docker containers needed. Installed using `pgvector/pgvector:pg15` Docker image.

**Actual Migration**: `alembic/versions/20251121_0001_013_install_pgvector.py`

```python
"""
Install pgvector extension for Mem0 vector storage.

Note: pgvectorscale omitted (see pgvectorscale Decision section above).
Mem0 works perfectly with pgvector alone at v1 scale.
"""
from alembic import op

revision = '013'
down_revision = '012'

def upgrade() -> None:
    # Enable pgvector extension (REQUIRED for Mem0)
    op.execute('CREATE EXTENSION IF NOT EXISTS vector;')
    print("✅ Installed pgvector extension (Mem0 vector storage enabled)")

def downgrade() -> None:
    # Remove pgvector extension
    op.execute('DROP EXTENSION IF EXISTS vector CASCADE;')
    print("⚠️ Removed pgvector extension")
```

**Run migration**:
```bash
docker exec voxbridge-api alembic upgrade head
```

2. **Update PostgreSQL Docker Image** ✅ COMPLETED

Changed from `postgres:15-alpine` to `pgvector/pgvector:pg15` to include pgvector extension pre-installed.

**Updated `docker-compose.yml`**:
```yaml
services:
  postgres:
    # Using pgvector/pgvector image for pgvector extension support (memory system)
    image: pgvector/pgvector:pg15  # Changed from postgres:15-alpine
    container_name: voxbridge-postgres
    # ... existing configuration
```

**Benefits**:
- ✅ pgvector v0.8.1 pre-installed (no manual compilation needed)
- ✅ Official pgvector Docker image (maintained by pgvector authors)
- ✅ Based on PostgreSQL 15 (no version change)
- ✅ Zero additional complexity vs postgres:15-alpine

**Note**: pgvector is a PostgreSQL extension, not a separate service. Zero additional infrastructure.

3. **Create Vector Table Placeholder** ✅ COMPLETED

**Actual Migration**: `alembic/versions/20251121_0002_014_create_memory_vectors.py`

```python
"""
Create memory vectors table placeholder.

Note: Mem0 framework automatically manages vector table creation
and indexing via pgvector. This migration is a placeholder for
reference and manual intervention if needed.
"""
from alembic import op

revision = '014'
down_revision = '013'

def upgrade() -> None:
    # Mem0 will create tables automatically on first initialization
    print("ℹ️ Vector tables will be created by Mem0 framework on first initialization")
    pass

def downgrade() -> None:
    # Mem0 manages vector tables
    print("ℹ️ Vector tables managed by Mem0 framework (no manual cleanup needed)")
    pass
```

**Verification**:
```bash
# Check pgvector extension installed
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
# Expected output: vector | 0.8.1
```


## Future Migration Options

**Note**: VoxBridge v1 uses **pgvectorscale** (PostgreSQL extension) managed by Mem0. If performance requirements exceed pgvectorscale capabilities in future versions, we can migrate to Qdrant using Mem0's built-in provider switching. See "Migration Strategy" section below for details.

---

### Database Schema & Alembic Migration

#### PostgreSQL Schema

**File**: `alembic/versions/014_add_memory_tables.py`

```python
"""
Add memory system tables (users, user_facts, embedding_preferences).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '014'
down_revision = '013'

def upgrade():
    # Users table (for memory personalization)
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.String(255), unique=True, nullable=False),  # Discord ID or WebRTC session
        sa.Column('display_name', sa.String(255)),
        sa.Column('embedding_provider', sa.String(50), server_default='azure'),  # 'azure' or 'local'
        sa.Column('memory_extraction_enabled', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())
    )
    op.create_index('idx_users_user_id', 'users', ['user_id'])

    # User facts table (metadata for Mem0 memory system)
    op.create_table(
        'user_facts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=True),  # NULL = global
        sa.Column('fact_key', sa.String(100), nullable=False),  # 'name', 'location', 'preferences', etc.
        sa.Column('fact_value', sa.Text, nullable=False),       # Raw value
        sa.Column('fact_text', sa.Text, nullable=False),        # Natural language fact
        sa.Column('importance', sa.Float, server_default='0.5'),  # 0.0-1.0 importance score
        sa.Column('vector_id', sa.String(255), unique=True, nullable=False),  # Vector store point ID (managed by Mem0)
        sa.Column('embedding_provider', sa.String(50), nullable=False),  # Which embedder was used
        sa.Column('embedding_model', sa.String(100)),           # Model name (e.g., 'text-embedding-3-large')
        sa.Column('validity_start', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('validity_end', sa.DateTime(timezone=True), nullable=True),  # NULL = still valid
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('user_id', 'fact_key', 'agent_id', name='uq_user_fact_key_agent')
    )
    op.create_index('idx_user_facts_user_id', 'user_facts', ['user_id'])
    op.create_index('idx_user_facts_agent_id', 'user_facts', ['agent_id'])
    op.create_index('idx_user_facts_validity', 'user_facts', ['validity_start', 'validity_end'])
    op.create_index('idx_user_facts_vector_id', 'user_facts', ['vector_id'])

def downgrade():
    op.drop_table('user_facts')
    op.drop_table('users')
```

#### SQLAlchemy Models

**File**: `src/database/models.py` (add to existing file)

```python
# ... existing imports

class User(Base):
    """User model for memory personalization."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(String(255), unique=True, nullable=False)  # Discord ID or WebRTC session
    display_name = Column(String(255))
    embedding_provider = Column(String(50), server_default='azure')  # 'azure' or 'local'
    memory_extraction_enabled = Column(Boolean, server_default=text('true'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    facts = relationship("UserFact", back_populates="user", cascade="all, delete-orphan")

class UserFact(Base):
    """User fact model (metadata for Mem0 memory system)."""
    __tablename__ = "user_facts"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True)
    fact_key = Column(String(100), nullable=False)
    fact_value = Column(Text, nullable=False)
    fact_text = Column(Text, nullable=False)
    importance = Column(Float, server_default='0.5')
    vector_id = Column(String(255), unique=True, nullable=False)  # Vector store point ID (managed by Mem0)
    embedding_provider = Column(String(50), nullable=False)
    embedding_model = Column(String(100))
    validity_start = Column(DateTime(timezone=True), server_default=func.now())
    validity_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="facts")
    agent = relationship("Agent")

    __table_args__ = (
        UniqueConstraint('user_id', 'fact_key', 'agent_id', name='uq_user_fact_key_agent'),
    )

**File**: `alembic/versions/015_create_extraction_queue.py`

```python
"""
Create extraction_tasks table for queue-based fact extraction.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '015'
down_revision = '014'

def upgrade():
    # Extraction task queue
    op.create_table(
        'extraction_tasks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_message', sa.Text, nullable=False),
        sa.Column('ai_response', sa.Text, nullable=False),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),  # pending, processing, completed, failed
        sa.Column('attempts', sa.Integer, server_default='0'),
        sa.Column('error', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index('idx_extraction_tasks_status', 'extraction_tasks', ['status', 'attempts'])
    op.create_index('idx_extraction_tasks_created', 'extraction_tasks', ['created_at'])
    
    # Add memory_scope column to agents table
    op.add_column('agents', sa.Column('memory_scope', sa.String(20), server_default='global'))
    # Values: 'global' (shared across agents) or 'agent' (agent-specific memories)

def downgrade():
    op.drop_column('agents', 'memory_scope')
    op.drop_table('extraction_tasks')
```

**SQLAlchemy Model** (add to `src/database/models.py`):

```python
class ExtractionTask(Base):
    """Queue for background fact extraction."""
    __tablename__ = "extraction_tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(String(255), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    user_message = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    status = Column(String(20), server_default='pending', nullable=False)  # pending, processing, completed, failed
    attempts = Column(Integer, server_default='0')
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    agent = relationship("Agent")
```

```


## Phase 2: Mem0 Framework Integration

### Mem0 Installation & Configuration

**Install Mem0**:
```bash
# Add to requirements-bot.txt
mem0ai>=0.1.0
sentence-transformers>=2.2.0  # For local embeddings (optional)

# Install
docker exec voxbridge-api pip install mem0ai
```

### Embedding Provider Configuration

VoxBridge supports **two embedding providers** - choose based on your requirements:

#### Option 1: Azure AI Embeddings (Recommended for Production)

**Pros**:
- ✅ **State-of-the-art quality**: text-embedding-3-large (3072 dimensions)
- ✅ **Fast API response**: ~50ms latency
- ✅ **Scalable**: No local GPU/CPU overhead
- ✅ **Latest models**: Always up-to-date

**Cons**:
- ❌ **Cost**: $0.13 per 1M tokens (~$1/month for 30K conversations)
- ❌ **Internet required**: Cannot work offline
- ❌ **Azure account needed**: Requires Azure subscription

**Configuration**:
```bash
# .env
EMBEDDING_PROVIDER=azure
AZURE_EMBEDDING_API_KEY=your_azure_key
AZURE_EMBEDDING_ENDPOINT=https://your-resource.openai.azure.com
AZURE_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_EMBEDDING_API_VERSION=2024-12-01-preview
AZURE_EMBEDDING_DIMS=3072
```

**When to use**: Production deployments, best quality, willing to pay $1/month

---

#### Option 2: Local Open-Source Embeddings (Free, Self-Hosted)

**Pros**:
- ✅ **Free**: No API costs ($0/month)
- ✅ **Privacy**: Data never leaves your server
- ✅ **Offline**: Works without internet
- ✅ **No external dependencies**: Fully self-contained

**Cons**:
- ❌ **Lower quality**: 768-1024 dims vs 3072 dims Azure
- ❌ **Slower**: ~200-500ms CPU inference (vs 50ms Azure API)
- ❌ **Resource intensive**: Uses CPU/RAM in voxbridge-api container
- ❌ **Model management**: Must download models (~400MB each)

**Recommended Models**:

| Model | Dimensions | Quality | Speed | Size |
|-------|------------|---------|-------|------|
| `sentence-transformers/all-mpnet-base-v2` | 768 | Good | Fast | 420MB |
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | Fair | Very Fast | 80MB |
| `BAAI/bge-large-en-v1.5` | 1024 | Better | Moderate | 1.34GB |
| `thenlper/gte-large` | 1024 | Better | Moderate | 670MB |

**Configuration**:
```bash
# .env
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
LOCAL_EMBEDDING_DIMS=768
```

**When to use**: Development, cost-sensitive, privacy-focused, offline deployments

---

### Embedding Provider Comparison

| Metric | Azure AI | Local (all-mpnet) |
|--------|----------|-------------------|
| **Cost** | $1/month | $0/month |
| **Quality** | Excellent (3072d) | Good (768d) |
| **Latency** | 50ms | 200-500ms |
| **Privacy** | Data sent to Azure | Fully private |
| **Setup** | Azure account required | pip install only |
| **Scalability** | Unlimited | Limited by CPU |

**Recommendation**: Start with **Azure AI** for best quality, switch to **local** if cost or privacy is a concern.

---

### Switching Embedding Providers

**⚠️ Important**: Switching providers requires re-indexing all memories (incompatible dimensions).

**Migration Script** (if switching providers):

```python
# scripts/migrate_embeddings.py
async def migrate_embedding_provider(old_provider: str, new_provider: str):
    """
    Migrate from one embedding provider to another.

    WARNING: This re-generates ALL embeddings (can take time + API costs).
    """
    from src.services.memory_service import MemoryService

    # 1. Get all memories from old collection
    old_memories = await db.execute("SELECT * FROM memories")

    # 2. Drop old vector index (old dimensions)
    await db.execute("DROP INDEX IF EXISTS memories_embedding_idx")

    # 3. Update embedding provider in .env
    os.environ["EMBEDDING_PROVIDER"] = new_provider

    # 4. Re-initialize MemoryService with new provider
    memory_service = MemoryService()

    # 5. Re-generate embeddings for all memories
    for mem in old_memories:
        await memory_service.memory.add(
            user_id=mem.user_id,
            messages=[{"role": "user", "content": mem.text}],
            metadata=mem.metadata
        )

    print(f"✅ Migrated {len(old_memories)} memories to {new_provider}")
```

**Note**: This is only needed if you switch providers AFTER accumulating memories. For new deployments, just set `EMBEDDING_PROVIDER` before first run.

---

### Frontend UI Configuration

**Settings Page**: `/settings/embedding-providers`

VoxBridge provides a comprehensive UI for managing embedding providers, inspired by Open WebUI's settings experience.

#### UI Features

**Provider Management**:
- Grid layout showing all configured providers
- Single active provider enforcement (only one can be active at a time)
- Quick start examples (Azure AI, Local, OpenAI templates)
- Stats card: Total providers, Active provider, Avg latency

**Provider Cards**:
```
┌─────────────────────┐
│ [☁️] Azure AI       │
│ [✓ Active]          │
│                     │
│ Deployment:         │
│ text-embedding-3... │
│                     │
│ Dimensions: 3072    │
│ Avg: 234ms          │
│ P95: 289ms          │
│                     │
│ [Test] [Edit] [Del] │
└─────────────────────┘
```

**Supported Providers** (Predefined Only):
1. **Azure OpenAI** - Enterprise, 3072 dimensions
2. **Local HuggingFace** - Free, self-hosted, 768-1024 dimensions
3. **OpenAI** - Hosted, 1536-3072 dimensions
4. **Ollama** - Local, variable dimensions

**Provider Form** (Conditional Fields):

**Azure AI Fields**:
- Provider Name (text)
- Azure Endpoint (URL, validated: `*.openai.azure.com`)
- API Key (password, encrypted at rest)
- Deployment Name (text)
- API Version (dropdown: 2024-12-01-preview, 2024-02-01, etc.)
- Model (dropdown: text-embedding-3-large, text-embedding-3-small)
- Dimensions (auto-populated: 3072 or 1536)

**Local HuggingFace Fields**:
- Provider Name (text)
- Model (dropdown: all-mpnet-base-v2, bge-large-en-v1.5, etc.)
- Dimensions (dropdown: 384, 768, 1024, 1536)
- Device (dropdown: Auto, CPU, CUDA)

**Test Connection**:
- Generates sample embedding ("Hello, world")
- Validates dimensions match configuration
- Measures latency (ms)
- Displays result: "✓ Connection successful! Dimensions: 3072, Latency: 234ms"

**Latency Metrics**:
- Tracks last 100 embedding requests per provider
- Calculates avg, p95, p99 latency
- Displays in provider card
- Updates in real-time

**Security**:
- API keys encrypted at rest (Fernet encryption)
- API keys never exposed in GET requests
- API keys masked in UI (password field)
- Option to update provider without changing API key (null = keep existing)

**Single Active Provider**:
- Only one provider can be active at a time (enforced at DB level)
- Activating a provider automatically deactivates others
- Delete prevented if it's the only provider
- Switching providers shows migration warning

#### Backend API

**Endpoints**:
```
GET    /api/settings/embedding-providers      # List all providers
POST   /api/settings/embedding-providers      # Create new (auto-activates)
PUT    /api/settings/embedding-providers/{id} # Update provider
DELETE /api/settings/embedding-providers/{id} # Delete provider
POST   /api/settings/embedding-providers/{id}/test    # Test connection
POST   /api/settings/embedding-providers/{id}/activate # Switch active
```

**Database Schema**:
```sql
CREATE TABLE embedding_providers (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    provider_type VARCHAR(50) NOT NULL, -- 'azure_openai', 'huggingface', 'openai', 'ollama'
    is_active BOOLEAN DEFAULT TRUE,
    dimensions INTEGER NOT NULL,

    -- Encrypted config (JSON)
    encrypted_config TEXT NOT NULL,

    -- Latency metrics
    avg_latency_ms FLOAT,
    p95_latency_ms FLOAT,
    p99_latency_ms FLOAT,
    total_requests INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT single_active CHECK (
        NOT is_active OR (SELECT COUNT(*) FROM embedding_providers WHERE is_active = TRUE) = 1
    )
);
```

**Integration with Memory System**:
- MemoryService queries active provider on initialization
- Builds Mem0 configuration dynamically based on active provider
- Switching providers: New embeddings use new provider, old embeddings remain
- Optional: Re-index all memories with new provider (background job)

---

**Note**: Mem0 handles all embedding operations internally via its `embedder` config. See "Quick Implementation Summary" (lines 54-131) for complete Mem0 configuration with both Azure AI and local embedding providers.

No custom embedding provider code needed.



### MemoryService Implementation

**File**: `src/services/memory_service.py`

```python
"""
Memory service wrapping Mem0 for fact extraction, retrieval, and management.
Implements queue-based extraction with retry logic and metrics tracking.
"""
import asyncio
import os
import json
from typing import List, Dict, Optional
from uuid import UUID
from datetime import datetime, timedelta
from mem0 import Memory
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from src.database.models import User, UserFact, ExtractionTask
from src.services.llm_service import LLMService
from src.config import logger

class MemoryService:
    """
    Memory service for VoxBridge conversational memory system.
    
    Architecture:
    - Wraps Mem0 for fact extraction/retrieval
    - Queue-based extraction (doesn't block voice responses)
    - Error handling with retry logic
    - Metrics tracking for monitoring
    """
    
    def __init__(self, db_session: AsyncSession):
        """Initialize memory service with Mem0."""
        self.db = db_session
        self.llm_service = LLMService()
        
        # Initialize Mem0 based on environment config
        embedding_provider = os.getenv("EMBEDDING_PROVIDER", "azure")
        
        if embedding_provider == "azure":
            embedder_config = {
                "provider": "azure_openai",
                "config": {
                    "model": "text-embedding-3-large",
                    "embedding_dims": 3072,
                    "azure_kwargs": {
                        "api_version": os.getenv("AZURE_EMBEDDING_API_VERSION", "2024-12-01-preview"),
                        "azure_deployment": os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"),
                        "azure_endpoint": os.getenv("AZURE_EMBEDDING_ENDPOINT"),
                        "api_key": os.getenv("AZURE_EMBEDDING_API_KEY")
                    }
                }
            }
        else:  # local
            embedder_config = {
                "provider": "huggingface",
                "config": {
                    "model": os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"),
                    "embedding_dims": int(os.getenv("LOCAL_EMBEDDING_DIMS", "768"))
                }
            }
        
        # Mem0 configuration
        config = {
            "vector_store": {
                "provider": "pgvector",
                "config": {
                    "dbname": os.getenv("POSTGRES_DB", "voxbridge"),
                    "host": "postgres",
                    "collection_name": "user_memories"
                }
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-4o-mini",
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key": os.getenv("OPENROUTER_API_KEY")
                }
            },
            "embedder": embedder_config
        }
        
        self.memory = Memory.from_config(config)
        logger.info(f"✅ MemoryService initialized with {embedding_provider} embeddings")
    
    async def queue_extraction(
        self,
        user_id: str,
        agent_id: UUID,
        user_message: str,
        ai_response: str
    ) -> UUID:
        """
        Queue a fact extraction task (non-blocking).
        
        Returns:
            task_id: UUID of the queued task
        """
        # Create extraction task in queue
        task = ExtractionTask(
            user_id=user_id,
            agent_id=agent_id,
            user_message=user_message,
            ai_response=ai_response,
            status="pending",
            attempts=0
        )
        
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        
        logger.info(f"📋 Queued extraction task {task.id} for user {user_id}")
        return task.id
    
    async def process_extraction_queue(self):
        """
        Background worker to process extraction queue.
        Call this in a separate asyncio task.
        """
        while True:
            try:
                # Get pending tasks
                result = await self.db.execute(
                    select(ExtractionTask)
                    .where(and_(
                        ExtractionTask.status == "pending",
                        ExtractionTask.attempts < 3
                    ))
                    .order_by(ExtractionTask.created_at)
                    .limit(10)
                )
                tasks = result.scalars().all()
                
                for task in tasks:
                    try:
                        # Mark as processing
                        task.status = "processing"
                        task.attempts += 1
                        await self.db.commit()
                        
                        # Extract facts
                        await self._extract_facts_from_turn(
                            task.user_id,
                            task.agent_id,
                            task.user_message,
                            task.ai_response
                        )
                        
                        # Mark as completed
                        task.status = "completed"
                        task.completed_at = func.now()
                        await self.db.commit()
                        
                        logger.info(f"✅ Completed extraction task {task.id}")
                        
                    except Exception as e:
                        logger.error(f"❌ Extraction task {task.id} failed (attempt {task.attempts}): {e}")
                        task.status = "failed" if task.attempts >= 3 else "pending"
                        task.error = str(e)
                        await self.db.commit()
                
                # Sleep before next batch
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"❌ Queue processor error: {e}")
                await asyncio.sleep(10)
    
    async def _extract_facts_from_turn(
        self,
        user_id: str,
        agent_id: UUID,
        user_message: str,
        ai_response: str
    ):
        """Extract and store facts from a conversation turn using Mem0."""
        # Check relevance filter first
        if not await self._should_extract_facts(user_message, ai_response):
            logger.debug(f"⏭️ Skipping extraction for user {user_id} (not relevant)")
            return
        
        # Get or create user
        user = await self._get_or_create_user(user_id)
        
        # Use Mem0 to extract and store facts
        try:
            memories = await self.memory.add(
                user_id=user_id,
                messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": ai_response}
                ],
                metadata={"agent_id": str(agent_id)}
            )
            
            # Sync facts to PostgreSQL for relational queries
            for mem in memories:
                await self._upsert_fact(
                    user=user,
                    agent_id=agent_id,
                    vector_id=mem["id"],
                    fact_text=mem["fact"],
                    importance=mem.get("importance", 0.5),
                    embedding_provider=os.getenv("EMBEDDING_PROVIDER", "azure"),
                    embedding_model=mem.get("model", "unknown")
                )
            
            logger.info(f"💾 Extracted {len(memories)} facts for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Mem0 extraction failed: {e}")
            raise
    
    async def get_user_memory_context(
        self,
        user_id: str,
        query: str,
        agent_id: Optional[UUID] = None,
        limit: int = 5
    ) -> str:
        """
        Retrieve relevant user memories and format as context.
        
        Returns:
            Formatted context string for LLM prompt injection
        """
        # Determine memory scope
        agent = await self._get_agent(agent_id) if agent_id else None
        memory_scope = agent.memory_scope if (agent and hasattr(agent, 'memory_scope')) else 'global'
        
        # Search Mem0 for relevant facts
        search_metadata = {}
        if memory_scope == 'agent' and agent_id:
            search_metadata["agent_id"] = str(agent_id)
        
        try:
            results = await self.memory.search(
                query=query,
                user_id=user_id,
                limit=limit,
                filters=search_metadata
            )
            
            if not results:
                return ""
            
            # Format context
            facts = [f"- {mem['memory']}" for mem in results]
            context = f"""
**User Memory Context:**
The following facts are known about {user_id}:
{chr(10).join(facts)}

Use this context naturally in your responses.
"""
            
            logger.debug(f"🔍 Retrieved {len(results)} memories for user {user_id}")
            return context
            
        except Exception as e:
            logger.error(f"❌ Memory search failed: {e}")
            return ""  # Degrade gracefully
    
    async def _should_extract_facts(self, user_message: str, ai_response: str) -> bool:
        """LLM-based relevance filter to reduce noise."""
        relevance_prompt = f"""
Determine if this conversation contains factual information about the user that should be remembered.

User: {user_message}
Assistant: {ai_response}

Criteria for extraction:
- User shares personal information (name, location, preferences, relationships)
- User mentions goals, habits, or important life events
- Conversation reveals user context useful for future interactions

Do NOT extract if:
- Just casual greetings or small talk
- Technical questions with no personal context
- User is testing the system

Should we extract and store facts from this conversation?
Answer with only "yes" or "no".
"""
        
        response = await self.llm_service.generate(
            messages=[{"role": "system", "content": relevance_prompt}],
            model_override="gpt-4o-mini"
        )
        
        return response.strip().lower() == "yes"
    
    async def _get_or_create_user(self, user_id: str) -> User:
        """Get user from database or create if doesn't exist."""
        result = await self.db.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(user_id=user_id)
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            logger.info(f"👤 Created new user: {user_id}")
        
        return user
    
    async def _get_agent(self, agent_id: UUID):
        """Get agent by ID."""
        from src.database.models import Agent
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        return result.scalar_one()
    
    async def _upsert_fact(
        self,
        user: User,
        agent_id: UUID,
        vector_id: str,
        fact_text: str,
        importance: float,
        embedding_provider: str,
        embedding_model: str
    ):
        """
        Upsert fact to PostgreSQL (for relational queries and metadata).
        """
        # Extract fact key from text (e.g., "name", "location")
        fact_key = fact_text.split(":")[0].strip().lower() if ":" in fact_text else "general"
        fact_value = fact_text.split(":", 1)[1].strip() if ":" in fact_text else fact_text
        
        # Check if fact exists
        result = await self.db.execute(
            select(UserFact).where(and_(
                UserFact.user_id == user.id,
                UserFact.fact_key == fact_key,
                UserFact.agent_id == agent_id
            ))
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # Update existing fact
            existing.fact_value = fact_value
            existing.fact_text = fact_text
            existing.importance = importance
            existing.vector_id = vector_id
            existing.updated_at = func.now()
        else:
            # Create new fact
            fact = UserFact(
                user_id=user.id,
                agent_id=agent_id,
                fact_key=fact_key,
                fact_value=fact_value,
                fact_text=fact_text,
                importance=importance,
                vector_id=vector_id,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model
            )
            self.db.add(fact)
        
        await self.db.commit()
```

**Usage in voice handlers**:
```python
# In webrtc_handler.py or discord_plugin.py
from src.services.memory_service import MemoryService

# After AI response is sent to user
await memory_service.queue_extraction(
    user_id=user_id,
    agent_id=agent_id,
    user_message=transcript,
    ai_response=ai_response_text
)

# Context injection before LLM call
memory_context = await memory_service.get_user_memory_context(
    user_id=user_id,
    query=transcript,
    agent_id=agent_id
)
system_prompt = base_system_prompt + "\n\n" + memory_context
```

## Phase 3: LLM Relevance Filtering & Fact Extraction

### LLM Relevance Filtering + Mem0 Extraction

**Key Change**: Add relevance filter before extraction to reduce noise.

**File**: `src/services/memory_service.py`

```python
async def should_extract_facts(self, user_message: str, ai_response: str) -> bool:
    """
    LLM relevance filter: Only extract if conversation contains relevant user facts.

    This reduces unnecessary LLM calls and prevents storing trivial information.
    """
    relevance_prompt = f"""
    Analyze this conversation and determine if it contains NEW, IMPORTANT facts about the user
    that should be stored in long-term memory.

    Answer with ONLY "yes" or "no".

    Conversation:
    USER: {user_message}
    AI: {ai_response}

    Should we extract and store facts from this conversation?
    """

    response = await self.llm_service.generate(
        messages=[{"role": "system", "content": relevance_prompt}],
        model_override="gpt-4o-mini"  # Fast, cheap
    )

    return response.strip().lower() == "yes"
```

---

## Phase 4: Memory Retrieval & Context Injection


### Voice Pipeline Integration

This section shows **exact code changes** needed to integrate memory extraction into existing voice handlers.

#### WebRTC Handler Integration

**File**: `src/voice/webrtc_handler.py`

**Changes needed**:

1. **Import MemoryService**:
```python
# Add to imports at top of file
from src.services.memory_service import MemoryService
```

2. **Initialize service in `__init__`**:
```python
def __init__(self, ...):
    # ... existing code
    self.memory_service = None  # Will be initialized async

async def initialize(self):
    """Initialize async components."""
    from src.database.session import get_db_session
    db = await get_db_session()
    self.memory_service = MemoryService(db)
```

3. **Queue extraction after AI response** (in `handle_final_transcript` method):
```python
# After AI response is sent to client
async def handle_final_transcript(self, transcript: str, user_id: str):
    # ... existing code to get AI response
    ai_response = await llm_service.generate_stream(...)
    
    # Send response to client
    await self.send_response(ai_response)
    
    # Queue memory extraction (non-blocking)
    if self.memory_service and user_id:
        await self.memory_service.queue_extraction(
            user_id=user_id,  # From WebRTC session (requires login, see WebRTC User Identity section)
            agent_id=self.agent_id,
            user_message=transcript,
            ai_response=ai_response_text
        )
        logger.debug(f"📋 Queued memory extraction for {user_id}")
```

4. **Inject context before LLM call**:
```python
async def handle_final_transcript(self, transcript: str, user_id: str):
    # Get memory context first
    memory_context = ""
    if self.memory_service and user_id:
        memory_context = await self.memory_service.get_user_memory_context(
            user_id=user_id,
            query=transcript,
            agent_id=self.agent_id,
            limit=5
        )
    
    # Add to system prompt
    system_prompt = self.agent.system_prompt
    if memory_context:
        system_prompt += "\n\n" + memory_context
    
    # Generate response with injected context
    ai_response = await llm_service.generate_stream(
        session_id=self.session_id,
        user_message=transcript,
        agent_id=self.agent_id,
        system_prompt_override=system_prompt  # Inject memory context
    )
```

---

#### Discord Plugin Integration

**File**: `src/plugins/discord_plugin.py`

**Changes needed**:

1. **Import and initialize** (in `DiscordPlugin.__init__`):
```python
from src.services.memory_service import MemoryService

async def initialize(self):
    """Initialize plugin."""
    # ... existing code
    from src.database.session import get_db_session
    db = await get_db_session()
    self.memory_service = MemoryService(db)
    
    # Start background extraction worker
    asyncio.create_task(self.memory_service.process_extraction_queue())
```

2. **Queue extraction after AI response** (in voice message handler):
```python
async def handle_voice_message(self, guild_id: int, user_id: str, transcript: str):
    # ... existing code to get AI response
    ai_response = await llm_service.generate_stream(...)
    
    # Send TTS response to Discord
    await self.send_tts_response(guild_id, ai_response)
    
    # Queue memory extraction (non-blocking)
    await self.memory_service.queue_extraction(
        user_id=f"discord_{user_id}",  # Prefix Discord IDs
        agent_id=self.active_agent_id,
        user_message=transcript,
        ai_response=ai_response_text
    )
```

3. **Inject context before LLM call** (same pattern as WebRTC):
```python
# Get memory context
memory_context = await self.memory_service.get_user_memory_context(
    user_id=f"discord_{user_id}",
    query=transcript,
    agent_id=self.active_agent_id
)

# Inject into system prompt
system_prompt = agent.system_prompt
if memory_context:
    system_prompt += "\n\n" + memory_context
```

---

#### Background Worker Setup

**File**: `src/api/server.py` (add to startup)

```python
from src.services.memory_service import MemoryService

@app.on_event("startup")
async def startup():
    """Start background workers."""
    # ... existing startup code
    
    # Start memory extraction queue processor
    from src.database.session import get_db_session
    db = await get_db_session()
    memory_service = MemoryService(db)
    
    asyncio.create_task(memory_service.process_extraction_queue())
    logger.info("✅ Started memory extraction queue worker")
```

---

#### Key Integration Points Summary

| Location | Action | When |
|----------|--------|------|
| WebRTC Handler | Initialize MemoryService | On handler creation |
| WebRTC Handler | Inject memory context | Before LLM call |
| WebRTC Handler | Queue extraction | After AI response sent |
| Discord Plugin | Initialize MemoryService | On plugin load |
| Discord Plugin | Inject memory context | Before LLM call |
| Discord Plugin | Queue extraction | After AI response sent |
| API Server | Start queue worker | On server startup |

**Critical**: Queue extraction happens **after** response is sent to user (non-blocking). Context injection happens **before** LLM call (blocking but fast, ~50-100ms).


### LLM Context Injection

**File**: `src/services/llm_service.py` (modify existing)

```python
# Modify generate_stream to inject memory context

async def generate_stream(
    self,
    session_id: UUID,
    user_message: str,
    agent_id: UUID,
    user_id: str = None
) -> AsyncGenerator[str, None]:
    """Generate streaming response with memory context."""
    # Get agent
    agent = await self._get_agent(agent_id)

    # Get memory context (if user_id provided)
    memory_context = ""
    if user_id:
        memory_service = get_memory_service()
        memory_context = await memory_service.get_user_memory_context(
            user_id=user_id,
            query=user_message,
            agent_id=agent_id
        )

    # Augment system prompt with memory
    system_prompt = agent.system_prompt
    if memory_context:
        system_prompt = f"{agent.system_prompt}\n\n{memory_context}"

    # Generate response (existing logic)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    async for chunk in self.provider.generate_stream(messages):
        yield chunk
```

---
### WebRTC User Identity Management

**Requirement**: WebRTC sessions need persistent user identity for memory storage.

**Solution**: Simple server-side authentication with name registration and token-based sessions.

#### Architecture Overview

**Authentication Flow**:
1. User enters name in modal (first visit)
2. Frontend calls `/api/auth/register` with name
3. Backend creates User record in database, returns auth token
4. Frontend stores token in localStorage
5. Token is sent with all WebRTC/API requests
6. Backend validates token and retrieves user_id

**Key Features**:
- Server-side user records (persistent across browsers)
- Token-based authentication (simple, stateless)
- Opt-in memory extraction (disabled by default)
- GDPR-compliant data export/deletion
- No passwords (username-only registration)

---

#### Database Schema Updates

**Migration**: `alembic/versions/016_add_auth_tokens.py`

```python
"""Add auth tokens for WebRTC user authentication"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '016'
down_revision = '015'

def upgrade():
    # Add auth_token column to users table
    op.add_column('users', sa.Column('auth_token', sa.String(255), unique=True, nullable=True))
    op.add_column('users', sa.Column('token_created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))

    # Create index for fast token lookup
    op.create_index('idx_users_auth_token', 'users', ['auth_token'])

def downgrade():
    op.drop_index('idx_users_auth_token')
    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'token_created_at')
    op.drop_column('users', 'auth_token')
```

**SQLAlchemy Model Update** (modify `src/database/models.py`):

```python
class User(Base):
    """User model for memory personalization."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(String(255), unique=True, nullable=False, index=True)  # "discord_123" or "webrtc_abc"
    display_name = Column(String(255), nullable=True)

    # Authentication (WebRTC users only)
    auth_token = Column(String(255), unique=True, nullable=True, index=True)  # JWT or random token
    token_created_at = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Memory settings
    memory_extraction_enabled = Column(Boolean, server_default=text('false'))  # Opt-in (GDPR)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    facts = relationship("UserFact", back_populates="user", cascade="all, delete-orphan")
```

---

#### Backend Authentication Service

**File**: `src/services/auth_service.py` (new file)

```python
"""
Authentication service for WebRTC users.
Implements simple token-based authentication without passwords.
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.models import User
from src.config import logger

class AuthService:
    """Simple authentication service for WebRTC users."""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def register_user(self, display_name: str) -> dict:
        """
        Register a new WebRTC user or return existing user.

        Args:
            display_name: User's chosen display name

        Returns:
            {
                "user_id": "webrtc_abc123",
                "auth_token": "random_token_here",
                "display_name": "John Doe"
            }
        """
        # Generate secure random token (32 bytes = 256 bits)
        auth_token = secrets.token_urlsafe(32)

        # Generate unique user_id
        user_id_suffix = secrets.token_urlsafe(8)
        user_id = f"webrtc_{user_id_suffix}"

        # Create user record
        user = User(
            user_id=user_id,
            display_name=display_name,
            auth_token=auth_token,
            token_created_at=datetime.utcnow(),
            last_login_at=datetime.utcnow(),
            memory_extraction_enabled=False  # Opt-in (disabled by default)
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"👤 Registered new WebRTC user: {user_id} ({display_name})")

        return {
            "user_id": user.user_id,
            "auth_token": auth_token,
            "display_name": display_name,
            "memory_enabled": False
        }

    async def validate_token(self, auth_token: str) -> Optional[User]:
        """
        Validate auth token and return user.

        Args:
            auth_token: Authentication token from localStorage

        Returns:
            User object if valid, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.auth_token == auth_token)
        )
        user = result.scalar_one_or_none()

        if user:
            # Update last login
            user.last_login_at = datetime.utcnow()
            await self.db.commit()
            logger.debug(f"✅ Validated token for user: {user.user_id}")
        else:
            logger.warning(f"❌ Invalid auth token: {auth_token[:10]}...")

        return user

    async def get_user_by_token(self, auth_token: str) -> Optional[dict]:
        """
        Get user info by auth token.

        Returns:
            User info dict or None if invalid
        """
        user = await self.validate_token(auth_token)

        if not user:
            return None

        return {
            "user_id": user.user_id,
            "display_name": user.display_name,
            "memory_enabled": user.memory_extraction_enabled,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }

    async def enable_memory_extraction(self, user_id: str) -> bool:
        """
        Enable memory extraction for user (opt-in).

        Returns:
            True if successful, False otherwise
        """
        result = await self.db.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return False

        user.memory_extraction_enabled = True
        await self.db.commit()

        logger.info(f"💾 Enabled memory extraction for user: {user_id}")
        return True

    async def delete_user_data(self, user_id: str):
        """
        Delete all user data (GDPR right to erasure).

        Deletes:
        - User record
        - All facts (cascades)
        - All sessions (cascades)
        - All extraction tasks (cascades)
        """
        result = await self.db.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User not found: {user_id}")

        # Delete from vector store (Mem0)
        from src.services.memory_service import MemoryService
        memory_service = MemoryService(self.db)
        await memory_service.memory.delete(user_id=user_id)

        # Delete from PostgreSQL (cascades to facts, sessions, conversations)
        await self.db.delete(user)
        await self.db.commit()

        logger.info(f"🗑️ Deleted all data for user: {user_id}")
```

---

#### Backend API Endpoints

**File**: `src/api/server.py` (add auth routes)

```python
from src.services.auth_service import AuthService
from pydantic import BaseModel

# Request/response models
class RegisterRequest(BaseModel):
    display_name: str

class RegisterResponse(BaseModel):
    user_id: str
    auth_token: str
    display_name: str
    memory_enabled: bool

class UserInfoResponse(BaseModel):
    user_id: str
    display_name: str
    memory_enabled: bool
    created_at: Optional[str]

# Dependency for auth validation
async def get_current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Validate auth token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    auth_service = AuthService(db)
    user = await auth_service.validate_token(token)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    return user

# Authentication endpoints
@app.post("/api/auth/register", response_model=RegisterResponse)
async def register_webrtc_user(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new WebRTC user.

    Body: {"display_name": "John Doe"}
    Returns: {"user_id": "webrtc_abc123", "auth_token": "...", "display_name": "John Doe", "memory_enabled": false}
    """
    auth_service = AuthService(db)
    result = await auth_service.register_user(request.display_name)
    return result

@app.get("/api/auth/me", response_model=UserInfoResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current user info (requires auth token).

    Headers: Authorization: Bearer <token>
    Returns: {"user_id": "...", "display_name": "...", "memory_enabled": true, "created_at": "..."}
    """
    return {
        "user_id": current_user.user_id,
        "display_name": current_user.display_name,
        "memory_enabled": current_user.memory_extraction_enabled,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None
    }

@app.post("/api/auth/enable-memory")
async def enable_memory_extraction(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Enable memory extraction for current user (opt-in).

    Headers: Authorization: Bearer <token>
    Returns: {"success": true}
    """
    auth_service = AuthService(db)
    success = await auth_service.enable_memory_extraction(current_user.user_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to enable memory extraction")

    return {"success": True}

@app.delete("/api/auth/delete-account")
async def delete_user_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete user account and all data (GDPR right to erasure).

    Headers: Authorization: Bearer <token>
    Returns: {"success": true}
    """
    auth_service = AuthService(db)
    await auth_service.delete_user_data(current_user.user_id)

    return {"success": True, "message": "All user data deleted"}
```

---

#### Frontend Implementation

**File**: `frontend/src/components/UserRegistrationModal.tsx` (new file)

```typescript
import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { api } from '@/services/api';

interface UserRegistrationModalProps {
  open: boolean;
  onRegistered: (userId: string, authToken: string, displayName: string) => void;
}

export function UserRegistrationModal({ open, onRegistered }: UserRegistrationModalProps) {
  const [displayName, setDisplayName] = useState('');
  const [enableMemory, setEnableMemory] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!displayName.trim()) {
      setError('Please enter your name');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      // Register user
      const response = await api.post('/api/auth/register', {
        display_name: displayName.trim()
      });

      const { user_id, auth_token, display_name: name } = response.data;

      // Store auth token in localStorage
      localStorage.setItem('voxbridge_auth_token', auth_token);
      localStorage.setItem('voxbridge_user_id', user_id);
      localStorage.setItem('voxbridge_display_name', name);

      // Optionally enable memory extraction
      if (enableMemory) {
        await api.post('/api/auth/enable-memory', {}, {
          headers: { Authorization: `Bearer ${auth_token}` }
        });
      }

      // Notify parent component
      onRegistered(user_id, auth_token, name);

    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed. Please try again.');
      console.error('Registration error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="sm:max-width-[425px]">
        <DialogHeader>
          <DialogTitle>Welcome to VoxBridge</DialogTitle>
          <DialogDescription>
            Enter your name to start a voice conversation. Your identity will be saved for future visits.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <Input
            id="name"
            placeholder="Enter your name..."
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSubmit()}
            autoFocus
            disabled={isLoading}
          />

          <div className="flex items-center space-x-2">
            <Checkbox
              id="memory"
              checked={enableMemory}
              onCheckedChange={(checked) => setEnableMemory(!!checked)}
              disabled={isLoading}
            />
            <label htmlFor="memory" className="text-sm text-muted-foreground cursor-pointer">
              Enable AI memory (helps remember your preferences across conversations)
            </label>
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <p className="text-xs text-muted-foreground">
            By registering, you agree to our{' '}
            <a href="/privacy" className="underline">Privacy Policy</a> and{' '}
            <a href="/terms" className="underline">Terms of Service</a>.
          </p>
        </div>

        <Button onClick={handleSubmit} disabled={!displayName.trim() || isLoading}>
          {isLoading ? 'Registering...' : 'Continue'}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
```

**File**: `frontend/src/pages/VoxbridgePage.tsx` (modify existing)

```typescript
import { UserRegistrationModal } from '@/components/UserRegistrationModal';

export function VoxbridgePage() {
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState<string | null>(null);
  const [showRegistrationModal, setShowRegistrationModal] = useState(false);

  useEffect(() => {
    // Check if user is already authenticated
    const storedToken = localStorage.getItem('voxbridge_auth_token');
    const storedUserId = localStorage.getItem('voxbridge_user_id');
    const storedName = localStorage.getItem('voxbridge_display_name');

    if (storedToken && storedUserId) {
      // Validate token with server
      validateToken(storedToken, storedUserId, storedName || 'Unknown');
    }
  }, []);

  const validateToken = async (token: string, userId: string, name: string) => {
    try {
      // Verify token is still valid
      await api.get('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` }
      });

      // Token is valid
      setAuthToken(token);
      setUserId(userId);
      setDisplayName(name);
    } catch (err) {
      // Token invalid or expired - clear storage
      localStorage.removeItem('voxbridge_auth_token');
      localStorage.removeItem('voxbridge_user_id');
      localStorage.removeItem('voxbridge_display_name');
    }
  };

  const handleStartVoiceChat = () => {
    if (!authToken || !userId) {
      // Show registration modal first
      setShowRegistrationModal(true);
    } else {
      // Start voice chat directly
      startWebRTCAudio(userId, authToken);
    }
  };

  const handleRegistered = (newUserId: string, newToken: string, newName: string) => {
    setUserId(newUserId);
    setAuthToken(newToken);
    setDisplayName(newName);
    setShowRegistrationModal(false);

    // Start voice chat immediately
    startWebRTCAudio(newUserId, newToken);
  };

  return (
    <>
      <UserRegistrationModal
        open={showRegistrationModal}
        onRegistered={handleRegistered}
      />
      {/* Rest of page */}
    </>
  );
}
```

**File**: `frontend/src/hooks/useWebRTCAudio.ts` (modify to send auth token)

```typescript
export function useWebRTCAudio() {
  // ... existing code

  const connect = async (userId: string, authToken: string) => {
    // Send auth token in initial WebSocket connection
    const ws = new WebSocket(`ws://localhost:4900/ws/voice?token=${encodeURIComponent(authToken)}`);

    ws.onopen = () => {
      console.log('WebSocket connected with authenticated user:', userId);
    };

    // ... rest of WebSocket logic
  };
}
```

---

#### WebRTC Handler Integration

**File**: `src/voice/webrtc_handler.py` (modify to validate auth token)

```python
from src.services.auth_service import AuthService

class WebRTCHandler:
    def __init__(self, websocket: WebSocket, db_session: AsyncSession):
        self.websocket = websocket
        self.db = db_session
        self.user = None  # Set after authentication
        self.user_id = None
        self.auth_service = AuthService(db_session)

    async def authenticate(self, auth_token: str) -> bool:
        """
        Authenticate user via token.

        Returns:
            True if authenticated, False otherwise
        """
        user = await self.auth_service.validate_token(auth_token)

        if not user:
            logger.warning("❌ WebRTC authentication failed")
            return False

        self.user = user
        self.user_id = user.user_id
        logger.info(f"✅ WebRTC user authenticated: {self.user_id} ({user.display_name})")
        return True

# WebSocket endpoint (src/api/server.py)
@app.websocket("/ws/voice")
async def websocket_voice_endpoint(
    websocket: WebSocket,
    token: str = Query(...),  # Auth token from query param
    db: AsyncSession = Depends(get_db)
):
    """WebSocket endpoint for browser voice chat (authenticated)."""
    await websocket.accept()

    # Create handler and authenticate
    handler = WebRTCHandler(websocket, db)

    if not await handler.authenticate(token):
        await websocket.send_json({
            "type": "error",
            "message": "Authentication failed. Please register again."
        })
        await websocket.close()
        return

    # Proceed with voice chat
    await handler.handle_audio_stream()
```

---

#### User ID Format

| Platform | Format | Example | Persistence |
|----------|--------|---------|-------------|
| Discord | `discord_{snowflake}` | `discord_1234567890` | Permanent (Discord account) |
| WebRTC | `webrtc_{random}` | `webrtc_aBc123DeF` | Server-side (auth token in localStorage) |

**Key Differences**:
- **Discord users**: User ID is Discord snowflake (permanent)
- **WebRTC users**: User ID is random (server-generated), persisted via auth token

---

#### Security Considerations

1. **Token Storage**:
   - Stored in localStorage (XSS risk if site compromised)
   - Alternative: HTTP-only cookies (CSRF risk, needs CSRF tokens)
   - **Decision**: localStorage for v1 (simpler, WebRTC is same-origin)

2. **Token Rotation**:
   - Tokens never expire (simpler for v1)
   - Future: 30-day expiration with refresh tokens

3. **Rate Limiting**:
   - Per-user rate limiting now possible (not per-IP)
   - Prevents memory spam attacks

4. **GDPR Compliance**:
   - Opt-in memory extraction (disabled by default)
   - Right to access: GET `/api/memory/users/{user_id}/facts`
   - Right to erasure: DELETE `/api/auth/delete-account`
   - Data export: GET `/api/memory/users/{user_id}/export`

---

#### Privacy & GDPR

**Data Collected**:
- Display name (user-provided)
- Auth token (random, non-identifying)
- Conversation transcripts (if memory enabled)
- Extracted facts (if memory enabled)

**User Rights** (GDPR Articles 15-17):
- **View all data**: GET `/api/auth/me` + GET `/api/memory/users/{user_id}/facts`
- **Export data**: GET `/api/memory/users/{user_id}/export` (JSON format)
- **Delete data**: DELETE `/api/auth/delete-account` (cascades to all facts, sessions)
- **Opt-out memory**: Memory extraction disabled by default (opt-in checkbox)

**Data Retention**:
- User records: Indefinite (until user deletes account)
- Conversations: Indefinite (until user deletes account)
- Extraction queue: 7 days (cleanup task)

**Export Reminder** (on first localStorage clear):
```typescript
useEffect(() => {
  // Check if user cleared localStorage recently
  const lastClearWarning = localStorage.getItem('voxbridge_clear_warning');
  const oneHourAgo = Date.now() - 3600000;

  if (!authToken && (!lastClearWarning || parseInt(lastClearWarning) < oneHourAgo)) {
    // Show toast: "Did you clear your browser data? Download your conversation history before losing access."
    localStorage.setItem('voxbridge_clear_warning', Date.now().toString());
  }
}, [authToken]);
```

---

#### Migration Path (from hardcoded "web_user_default")

**Step 1**: Run migration 016 to add auth_token columns

```bash
docker exec voxbridge-discord alembic upgrade head
```

**Step 2**: Migrate existing "web_user_default" users (if any)

```python
# migration/scripts/migrate_web_users.py
async def migrate_legacy_web_users():
    """Convert legacy 'web_user_default' sessions to individual users."""

    # Get all sessions with "web_user_default"
    result = await db.execute(
        select(Session).where(Session.user_id == "web_user_default")
    )
    legacy_sessions = result.scalars().all()

    for session in legacy_sessions:
        # Create new user for this session
        auth_service = AuthService(db)
        user_data = await auth_service.register_user(f"Legacy User {session.id[:8]}")

        # Update session to point to new user
        session.user_id = user_data["user_id"]

    await db.commit()
    logger.info(f"✅ Migrated {len(legacy_sessions)} legacy sessions")
```

**Step 3**: Deploy frontend changes (UserRegistrationModal)

**Step 4**: Update WebRTC handler to require authentication

---

## Phase 5: Frontend Memory Viewer UI

### Memory API Endpoints

**File**: `src/api/server.py` (add memory routes)

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from uuid import UUID
from typing import List, Optional

memory_router = APIRouter(prefix="/api/memory", tags=["memory"])

# Request/response models
class FactCreateRequest(BaseModel):
    fact_key: str
    fact_value: str
    fact_text: str
    importance: float = 0.5
    agent_id: Optional[UUID] = None

class FactUpdateRequest(BaseModel):
    fact_text: Optional[str] = None
    importance: Optional[float] = None

class FactResponse(BaseModel):
    id: UUID
    user_id: UUID
    agent_id: Optional[UUID]
    fact_key: str
    fact_value: str
    fact_text: str
    importance: float
    embedding_provider: str
    validity_start: str
    validity_end: Optional[str]
    created_at: str

@memory_router.get("/users/{user_id}/facts", response_model=List[FactResponse])
async def get_user_facts(
    user_id: str,
    agent_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get all facts for a user, optionally filtered by agent."""
    memory_service = get_memory_service()
    user = await memory_service._get_or_create_user(user_id)

    query = select(UserFact).where(
        and_(
            UserFact.user_id == user.id,
            UserFact.validity_end.is_(None)  # Only current facts
        )
    )

    if agent_id:
        query = query.where(UserFact.agent_id == agent_id)

    result = await db.execute(query.order_by(UserFact.importance.desc(), UserFact.created_at.desc()))
    facts = result.scalars().all()

    return [FactResponse.from_orm(fact) for fact in facts]

@memory_router.post("/users/{user_id}/facts", response_model=FactResponse)
async def create_user_fact(
    user_id: str,
    request: FactCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Manually create a user fact."""
    memory_service = get_memory_service()
    user = await memory_service._get_or_create_user(user_id)

    fact = await memory_service._upsert_fact(
        user=user,
        agent_id=request.agent_id,
        fact_key=request.fact_key,
        fact_value=request.fact_value,
        fact_text=request.fact_text,
        importance=request.importance
    )

    return FactResponse.from_orm(fact)

@memory_router.put("/facts/{fact_id}", response_model=FactResponse)
async def update_fact(
    fact_id: UUID,
    request: FactUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update fact text or importance."""
    result = await db.execute(
        select(UserFact).where(UserFact.id == fact_id)
    )
    fact = result.scalar_one_or_none()

    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    # Update fields
    if request.fact_text:
        fact.fact_text = request.fact_text
        # Re-embed and update Qdrant
        # ... implementation

    if request.importance is not None:
        fact.importance = request.importance
        # Update Qdrant metadata
        # ... implementation

    await db.commit()
    await db.refresh(fact)
    return FactResponse.from_orm(fact)

@memory_router.delete("/facts/{fact_id}")
async def delete_fact(fact_id: UUID, db: AsyncSession = Depends(get_db)):
    """Soft-delete a fact (set validity_end)."""
    result = await db.execute(
        select(UserFact).where(UserFact.id == fact_id)
    )
    fact = result.scalar_one_or_none()

    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    # Soft delete
    fact.validity_end = func.now()
    await db.commit()

    # Delete from Mem0 vector store
    memory_service = get_memory_service()
    await memory_service.memory.delete(memory_id=fact.vector_id)

    return {"success": True}

@memory_router.get("/stats")
async def get_memory_stats(db: AsyncSession = Depends(get_db)):
    """Get memory statistics."""
    # Total facts
    total_facts = await db.execute(
        select(func.count(UserFact.id)).where(UserFact.validity_end.is_(None))
    )
    total_facts_count = total_facts.scalar()

    # Total users
    total_users = await db.execute(select(func.count(User.id)))
    total_users_count = total_users.scalar()

    # Facts per user (average)
    avg_facts = total_facts_count / max(total_users_count, 1)

    return {
        "total_facts": total_facts_count,
        "total_users": total_users_count,
        "avg_facts_per_user": round(avg_facts, 2)
    }

# Register router
app.include_router(memory_router)
```

### Memory Viewer Page

**File**: `frontend/src/pages/MemoryPage.tsx`

```typescript
import React, { useState, useEffect } from 'react';
import { Trash2, Edit2, Plus, Filter, Search } from 'lucide-react';

interface UserFact {
  id: string;
  user_id: string;
  agent_id: string | null;
  fact_key: string;
  fact_value: string;
  fact_text: string;
  importance: number;
  embedding_provider: string;
  validity_start: string;
  created_at: string;
}

interface MemoryStats {
  total_facts: number;
  total_users: number;
  avg_facts_per_user: number;
}

const MemoryPage: React.FC = () => {
  const [facts, setFacts] = useState<UserFact[]>([]);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterAgent, setFilterAgent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadFacts();
    loadStats();
  }, [filterAgent]);

  const loadFacts = async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (filterAgent) params.append('agent_id', filterAgent);

    const response = await fetch(`/api/memory/users/current/facts?${params}`);
    const data = await response.json();
    setFacts(data);
    setLoading(false);
  };

  const loadStats = async () => {
    const response = await fetch('/api/memory/stats');
    const data = await response.json();
    setStats(data);
  };

  const handleDelete = async (factId: string) => {
    if (!confirm('Delete this fact?')) return;

    await fetch(`/api/memory/facts/${factId}`, { method: 'DELETE' });
    loadFacts();
  };

  const filteredFacts = facts.filter(fact =>
    fact.fact_text.toLowerCase().includes(searchQuery.toLowerCase()) ||
    fact.fact_key.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Memory Viewer</h1>
        <p className="text-gray-400">
          View and manage user facts extracted from conversations
        </p>
      </div>

      {/* Statistics Cards */}
      {stats && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-gray-800 p-4 rounded-lg">
            <div className="text-gray-400 text-sm">Total Facts</div>
            <div className="text-2xl font-bold">{stats.total_facts}</div>
          </div>
          <div className="bg-gray-800 p-4 rounded-lg">
            <div className="text-gray-400 text-sm">Total Users</div>
            <div className="text-2xl font-bold">{stats.total_users}</div>
          </div>
          <div className="bg-gray-800 p-4 rounded-lg">
            <div className="text-gray-400 text-sm">Avg Facts/User</div>
            <div className="text-2xl font-bold">{stats.avg_facts_per_user}</div>
          </div>
        </div>
      )}

      {/* Search & Filter */}
      <div className="flex gap-4 mb-6">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
          <input
            type="text"
            placeholder="Search facts..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg"
          />
        </div>
        <button className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg flex items-center gap-2">
          <Plus size={20} />
          Add Fact
        </button>
      </div>

      {/* Facts List */}
      <div className="space-y-3">
        {loading ? (
          <div className="text-center py-12 text-gray-400">Loading facts...</div>
        ) : filteredFacts.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            No facts found. Facts will be automatically extracted during conversations.
          </div>
        ) : (
          filteredFacts.map(fact => (
            <div key={fact.id} className="bg-gray-800 p-4 rounded-lg flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-sm font-mono bg-gray-700 px-2 py-1 rounded">
                    {fact.fact_key}
                  </span>
                  <div className="flex">
                    {[...Array(3)].map((_, i) => (
                      <span
                        key={i}
                        className={`text-yellow-500 ${
                          i < Math.floor(fact.importance * 3) ? '' : 'opacity-30'
                        }`}
                      >
                        ⭐
                      </span>
                    ))}
                  </div>
                  <span className="text-xs text-gray-500">
                    {new Date(fact.created_at).toLocaleDateString()}
                  </span>
                </div>
                <div className="text-lg mb-1">{fact.fact_text}</div>
                <div className="text-sm text-gray-400">
                  Value: <span className="text-gray-300">{fact.fact_value}</span>
                  {' • '}
                  Provider: <span className="text-gray-300">{fact.embedding_provider}</span>
                  {fact.agent_id && (
                    <>
                      {' • '}
                      Scope: <span className="text-blue-400">Agent-specific</span>
                    </>
                  )}
                </div>
              </div>

              <div className="flex gap-2 ml-4">
                <button className="p-2 hover:bg-gray-700 rounded">
                  <Edit2 size={18} />
                </button>
                <button
                  onClick={() => handleDelete(fact.id)}
                  className="p-2 hover:bg-red-900/30 rounded text-red-400"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default MemoryPage;
```

### WebSocket Real-Time Updates

**File**: `src/api/server.py` (add WebSocket events)

```python
# Add memory event broadcasting

async def broadcast_fact_extracted(fact: UserFact):
    """Broadcast new fact to connected clients."""
    await websocket_manager.broadcast({
        "type": "fact_extracted",
        "data": {
            "id": str(fact.id),
            "user_id": str(fact.user_id),
            "fact_text": fact.fact_text,
            "importance": fact.importance
        }
    })
```

**File**: `frontend/src/pages/MemoryPage.tsx` (add WebSocket listener)

```typescript
// Add to MemoryPage component

useEffect(() => {
  const ws = new WebSocket('ws://localhost:4900/ws/events');

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);

    if (message.type === 'fact_extracted') {
      // Reload facts when new fact is extracted
      loadFacts();
    }
  };

  return () => ws.close();
}, []);
```

---

## Phase 6: Redis Caching (Optional Enhancement)

### Frontend TypeScript Types

**File**: `frontend/src/types/memory.ts` (new file)

```typescript
// User memory fact
export interface UserFact {
  id: string;
  userId: string;
  agentId: string | null;
  factKey: string;
  factValue: string;
  factText: string;
  importance: number;
  vectorId: string;
  embeddingProvider: string;
  embeddingModel: string;
  validityStart: string;
  validityEnd: string | null;
  createdAt: string;
  updatedAt: string;
}

// Memory statistics
export interface MemoryStats {
  totalFacts: number;
  totalUsers: number;
  avgFactsPerUser: number;
  recentExtractions24h: number;
}

// Embedding provider
export interface EmbeddingProvider {
  id: string;
  name: string;
  providerType: 'azure' | 'local' | 'openai' | 'ollama';
  isActive: boolean;
  dimensions: number;
  encryptedConfig: string;
  avgLatencyMs: number | null;
  p95LatencyMs: number | null;
  p99LatencyMs: number | null;
  totalRequests: number;
  createdAt: string;
  updatedAt: string;
}

// Memory metrics
export interface MemoryMetrics {
  extractionQueueSize: number;
  avgExtractionLatency: number;
  p95ExtractionLatency: number;
  extractionSuccessRate: number;
  cacheHitRate: number | null;
}

// WebSocket events
export interface FactExtractionEvent {
  type: 'fact_extracted';
  userId: string;
  agentId: string;
  factCount: number;
  facts: Array<{
    fact_text: string;
    importance: number;
  }>;
}

// API request/response types
export interface CreateFactRequest {
  userId: string;
  agentId: string | null;
  factKey: string;
  factValue: string;
  factText: string;
  importance: number;
}

export interface UpdateFactRequest {
  factText?: string;
  factValue?: string;
  importance?: number;
}

export interface SearchFactsRequest {
  query: string;
  userId?: string;
  agentId?: string | null;
  limit?: number;
}

export interface DeleteUserDataRequest {
  userId: string;
  confirm: boolean;
}
```

**File**: `frontend/src/services/memory.ts` (new file)

```typescript
import { api } from './api';
import type { UserFact, MemoryStats, SearchFactsRequest, CreateFactRequest } from '@/types/memory';

export const memoryService = {
  async getFacts(userId?: string, agentId?: string): Promise<UserFact[]> {
    const params = new URLSearchParams();
    if (userId) params.append('user_id', userId);
    if (agentId) params.append('agent_id', agentId);
    
    const response = await api.get(`/api/memory/facts?${params}`);
    return response.data;
  },

  async searchFacts(request: SearchFactsRequest): Promise<UserFact[]> {
    const response = await api.post('/api/memory/search', request);
    return response.data;
  },

  async createFact(fact: CreateFactRequest): Promise<UserFact> {
    const response = await api.post('/api/memory/facts', fact);
    return response.data;
  },

  async deleteFact(factId: string): Promise<void> {
    await api.delete(`/api/memory/facts/${factId}`);
  },

  async getStats(): Promise<MemoryStats> {
    const response = await api.get('/api/memory/stats');
    return response.data;
  },

  async exportUserData(userId: string): Promise<Blob> {
    const response = await api.get(`/api/users/${userId}/export`, {
      responseType: 'blob'
    });
    return response.data;
  },

  async deleteUserData(userId: string): Promise<void> {
    await api.delete(`/api/users/${userId}`, {
      data: { confirm: true }
    });
  }
};
```


### Overview

Redis caching is an **optional Phase 6 enhancement** to improve performance by caching embeddings and search results. **Not required for v1 launch** - the system works without Redis, just with slightly higher latency on repeated queries.

### Why Defer Redis to Phase 6?

1. **Complexity**: Adds another infrastructure component
2. **Operational Overhead**: Requires monitoring, backups, eviction policies
3. **Diminishing Returns**: pgvectorscale is already fast (60ms p95 latency)
4. **Unknown Usage Patterns**: Need production data to optimize cache hit rates

**When to implement**: After v1 launch, if query latency metrics show >30% repeated queries.

### Redis Caching Strategy

#### Two-Level Cache

**Level 1: Embedding Cache** (24-hour TTL)
- **Key**: `embedding:{hash(user_id:query)}`
- **Value**: 3072-dimension float array (JSON)
- **Purpose**: Avoid redundant Azure AI API calls for repeated queries
- **Expected Hit Rate**: 30-50% (same user asking similar questions)

**Level 2: Search Results Cache** (1-hour TTL)
- **Key**: `memories:{hash(user_id:query)}`
- **Value**: List of top-5 memory results (JSON)
- **Purpose**: Skip pgvectorscale search for exact duplicate queries
- **Expected Hit Rate**: 10-20% (exact repeated questions)

### Implementation Code (Phase 6)

**File**: `src/services/memory_cache_service.py`

```python
import redis
import hashlib
import json
from typing import List, Dict, Optional

class MemoryCacheService:
    """Redis caching for embeddings and memory search results."""

    def __init__(self, redis_url: str = "redis://redis:6379"):
        self.redis = redis.from_url(redis_url, decode_responses=False)
        self.embedding_ttl = 86400  # 24 hours
        self.results_ttl = 3600     # 1 hour

    def _hash_key(self, user_id: str, query: str) -> str:
        return hashlib.sha256(f"{user_id}:{query}".encode()).hexdigest()

    async def get_cached_embedding(self, user_id: str, query: str) -> Optional[List[float]]:
        key = f"embedding:{self._hash_key(user_id, query)}"
        cached = self.redis.get(key)
        return json.loads(cached) if cached else None

    async def cache_embedding(self, user_id: str, query: str, embedding: List[float]):
        key = f"embedding:{self._hash_key(user_id, query)}"
        self.redis.setex(key, self.embedding_ttl, json.dumps(embedding))
```

### Docker Compose Configuration (Phase 6)

```yaml
services:
  redis:
    image: redis:7-alpine
    container_name: voxbridge-redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped
    networks:
      - bot-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru

volumes:
  redis-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ../zexternal-volumes/voxbridge-redis-data
```

### Performance Impact Estimates

| Metric | Without Redis | With Redis (50% hit rate) |
|--------|---------------|---------------------------|
| Avg Query Latency | 150ms | 90ms (40% improvement) |
| Azure AI API Calls | 30K/month | 15K/month (50% reduction) |
| Embedding Cost | ~$1/month | ~$0.50/month |

**Conclusion**: Redis provides moderate performance gains. Implement only if production metrics show need.

---

## Database Schema

### Complete PostgreSQL Schema

```sql
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) UNIQUE NOT NULL,          -- Discord ID or WebRTC session
    display_name VARCHAR(255),
    embedding_provider VARCHAR(50) DEFAULT 'azure', -- 'azure' or 'local'
    memory_extraction_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_user_id ON users(user_id);

-- User facts table (metadata for Qdrant embeddings)
CREATE TABLE user_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,  -- NULL = global
    fact_key VARCHAR(100) NOT NULL,                         -- 'name', 'preference_food', etc.
    fact_value TEXT NOT NULL,                               -- Raw value
    fact_text TEXT NOT NULL,                                -- Natural language
    importance FLOAT DEFAULT 0.5,                           -- 0.0-1.0
    vector_id VARCHAR(255) UNIQUE NOT NULL,                 -- Vector store point ID (managed by Mem0)
    embedding_provider VARCHAR(50) NOT NULL,                -- 'azure' or 'local'
    embedding_model VARCHAR(100),                           -- Model name
    validity_start TIMESTAMPTZ DEFAULT NOW(),
    validity_end TIMESTAMPTZ,                               -- NULL = still valid
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, fact_key, agent_id)
);

CREATE INDEX idx_user_facts_user_id ON user_facts(user_id);
CREATE INDEX idx_user_facts_agent_id ON user_facts(agent_id);
CREATE INDEX idx_user_facts_validity ON user_facts(validity_start, validity_end);
CREATE INDEX idx_user_facts_vector_id ON user_facts(vector_id);

-- Modify agents table (add memory_scope column)
ALTER TABLE agents ADD COLUMN memory_scope VARCHAR(20) DEFAULT 'global';
-- Values: 'global', 'agent_specific', 'hybrid'
```

### Qdrant Collections

```python
# user_facts collection
{
    "collection_name": "user_facts",
    "vectors": {
        "size": 3072,  # Azure AI text-embedding-3-large
        "distance": "Cosine"
    },
    "payload_schema": {
        "user_id": "keyword",      # User UUID
        "agent_id": "keyword",     # Agent UUID (null for global)
        "fact_key": "keyword",     # Fact category
        "fact_value": "text",      # Raw value
        "fact_text": "text",       # Natural language
        "importance": "float"      # 0.0-1.0
    }
}
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/unit/memory/test_memory_service.py`

```python
"""
Unit tests for MemoryService.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from src.services.memory_service import MemoryService

@pytest.mark.asyncio
async def test_extract_facts_from_turn():
    """Test real-time fact extraction."""
    memory_service = MemoryService(db=mock_db, llm_service=mock_llm, embedding_service=mock_embed)

    # Mock LLM extraction response
    mock_llm.generate.return_value = json.dumps([
        {"fact_key": "name", "fact_value": "Alice", "fact_text": "User's name is Alice", "importance": 0.9}
    ])

    facts = await memory_service.extract_facts_from_turn(
        user_id="discord_123",
        agent_id=uuid4(),
        user_message="Hi, I'm Alice",
        ai_response="Nice to meet you Alice!"
    )

    assert len(facts) == 1
    assert facts[0].fact_key == "name"

@pytest.mark.asyncio
async def test_get_user_memory_context():
    """Test memory context retrieval."""
    memory_service = MemoryService(...)

    # Mock Mem0 search
    with patch.object(memory_service.memory, 'search') as mock_search:
        mock_search.return_value = [
            {"id": "fact-1", "memory": "User likes pizza", "score": 0.95}
        ]

        context = await memory_service.get_user_memory_context(
            user_id="discord_123",
            query="What food should I order?",
            agent_id=uuid4()
        )

        assert "User likes pizza" in context
        mock_search.assert_called_once()
```

### Integration Tests

**File**: `tests/integration/test_memory_pipeline.py`

```python
"""
Integration test for complete memory pipeline.
"""
import pytest
from src.services.memory_service import MemoryService
from src.services.llm_service import LLMService
from src.services.embedding_service import EmbeddingService

@pytest.mark.asyncio
async def test_end_to_end_memory_extraction():
    """Test full pipeline: conversation → fact extraction → retrieval."""
    # Real database, mock LLM/embeddings
    memory_service = MemoryService(real_db, mock_llm, mock_embed)

    # 1. Extract facts
    facts = await memory_service.extract_facts_from_turn(
        user_id="test_user",
        agent_id=test_agent.id,
        user_message="I love hiking in the mountains",
        ai_response="That sounds amazing!"
    )

    assert len(facts) > 0

    # 2. Retrieve context
    context = await memory_service.get_user_memory_context(
        user_id="test_user",
        query="What outdoor activities do I enjoy?",
        agent_id=test_agent.id
    )

    assert "hiking" in context.lower() or "mountains" in context.lower()
```

### E2E Tests

**File**: `tests/e2e/test_memory_ux.py`

```python
"""
End-to-end test with real Qdrant and LLM.
"""
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_conversation_with_memory():
    """Test conversation remembers user facts."""
    # Real Qdrant, real LLM (OpenRouter or local)

    # Turn 1: User introduces themselves
    response1 = await webrtc_client.send_message("Hi, I'm Bob from Seattle")
    # Extract facts (background)

    # Turn 2: Ask question requiring memory
    response2 = await webrtc_client.send_message("What's my name?")

    assert "Bob" in response2  # AI should remember
```

---

## Monitoring & Metrics

### Key Metrics to Track

```python
class MemoryMetrics:
    # Latency
    fact_extraction_latency_ms: float      # Time to extract facts from conversation
    embedding_generation_latency_ms: float # Time to generate embeddings
    qdrant_index_latency_ms: float         # Time to index in Qdrant
    memory_retrieval_latency_ms: float     # Time to search and retrieve facts

    # Quality
    facts_extracted_per_turn: float        # Average facts extracted
    fact_deduplication_rate: float         # % of facts that were duplicates
    memory_retrieval_accuracy: float       # % of relevant facts retrieved

    # Volume
    total_facts_stored: int                # Total facts in system
    facts_per_user_avg: float              # Average facts per user
    embeddings_generated_total: int        # Total embeddings created

    # Resources
    qdrant_collection_size_mb: float       # Qdrant storage usage
    postgresql_facts_table_size_mb: float  # PostgreSQL storage
```

### Performance Targets

| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| Fact extraction latency | <2000ms | >5000ms |
| Embedding generation | <500ms | >2000ms |
| Qdrant indexing | <100ms | >500ms |
| Memory retrieval | <200ms | >1000ms |
| Facts per conversation turn | 0-3 | >5 (too noisy) |
| Qdrant p95 latency | <50ms | >100ms |

---

## Migration Strategy

### pgvectorscale is the Primary Solution (v1)

**No migration needed** - pgvectorscale is a PostgreSQL extension:
1. Install via Alembic migration (`CREATE EXTENSION vectorscale CASCADE;`)
2. Mem0 handles vector table creation and indexing automatically
3. Zero infrastructure changes (uses existing PostgreSQL container)


### ⏳ Optional Future Migration to Qdrant (v2+)

**Future Option**: If pgvectorscale doesn't meet performance requirements at scale (>500K facts, p95 latency >100ms), we can migrate to Qdrant using Mem0's provider switching. Mem0 supports Qdrant natively, making migration straightforward via config change and data export/import.

**Not part of v1 implementation.**

### Rollback Plan

If memory system encounters issues:

1. **Short-term disable**: Set `MEMORY_EXTRACTION_ENABLED=false` in `.env`
2. **Disable relevance filter**: Set all extractions to pass filter (debug mode)
3. **Data preservation**: All metadata remains in PostgreSQL (pgvectorscale is just an index)

**No risk of data loss** - pgvectorscale stores vectors in PostgreSQL tables with ACID transactions.

---

## Cost Analysis

### Infrastructure Costs (v1 - Without Redis)

**pgvectorscale** (PostgreSQL extension):
- **Cost**: $0/month (uses existing PostgreSQL container)
- **No additional infrastructure**: Zero deployment complexity

**Total Infrastructure** (VoxBridge scale 100K facts):
- pgvectorscale: $0 (existing PostgreSQL)
- PostgreSQL: $0 (existing)
- **Total: $0/month**

### Infrastructure Costs (Phase 6 - With Redis)

**Redis** (embedding + result cache):
- **Docker container**: redis:alpine (~50MB image)
- **Memory usage**: ~100MB for 10K cached embeddings
- **Cost**: $0/month (self-hosted)

**Total Infrastructure** (with Redis):
- pgvectorscale: $0
- Redis: $0 (self-hosted)
- PostgreSQL: $0 (existing)
- **Total: $0/month** (no infrastructure cost increase)

### Embedding Costs

#### Azure AI Embeddings (text-embedding-3-large)

**Pricing**:
- **Base cost**: $0.13 per 1M tokens
- **Avg conversation**: ~250 tokens
- **VoxBridge estimate**: 1K conversations/day = 30K/month

**Monthly Embedding Costs**:

| Scenario | Conversations | Tokens | Cost |
|----------|---------------|--------|------|
| v1 (No Redis) | 30K | 7.5M | **$1/month** |
| Phase 6 (Redis 50% hit) | 15K | 3.75M | **$0.50/month** |

#### Local Open-Source Embeddings

**Pricing**:
- **Cost**: **$0/month** (free, self-hosted)
- **Models**: sentence-transformers/all-mpnet-base-v2 (768 dims)
- **Resource cost**: CPU time in voxbridge-api container (~200-500ms per embedding)

**Trade-offs**:
- ✅ Free ($0/month)
- ❌ Lower quality (768 dims vs 3072 dims Azure)
- ❌ Slower (200-500ms vs 50ms Azure)
- ❌ CPU overhead in container

### LLM Costs (Fact Extraction)

**gpt-4o-mini** (via OpenRouter):
- **Relevance filter**: ~$0.0001/conversation (50 tokens input, 5 tokens output)
- **Mem0 extraction**: ~$0.0003/conversation (200 tokens input, 100 tokens output)
- **Total**: ~$0.0004 per conversation with fact extraction

**Monthly LLM Costs**:
- Relevance filter for all: 30K × $0.0001 = **$3/month**
- Mem0 extraction (20% pass filter): 6K × $0.0003 = **$1.80/month**
- **Total**: **~$5/month**

### Total Monthly Cost

**v1 (Azure AI Embeddings, No Redis)**:

| Component | Cost |
|-----------|------|
| Infrastructure (pgvectorscale) | $0 |
| Azure AI embeddings | ~$1 |
| LLM fact extraction (gpt-4o-mini) | ~$5 |
| PostgreSQL | $0 (existing) |
| **Total** | **~$6/month** |

**v1 (Local Embeddings, No Redis)**:

| Component | Cost |
|-----------|------|
| Infrastructure (pgvectorscale) | $0 |
| Local embeddings (sentence-transformers) | $0 |
| LLM fact extraction (gpt-4o-mini) | ~$5 |
| PostgreSQL | $0 (existing) |
| **Total** | **~$5/month** |

**Phase 6 (Azure AI + Redis)**:

| Component | Cost |
|-----------|------|
| Infrastructure (pgvectorscale + Redis) | $0 |
| Azure AI embeddings (50% cached) | ~$0.50 |
| LLM fact extraction (gpt-4o-mini) | ~$5 |
| PostgreSQL | $0 (existing) |
| **Total** | **~$5.50/month** |

**Phase 6 (Local Embeddings + Redis)**:

| Component | Cost |
|-----------|------|
| Infrastructure (pgvectorscale + Redis) | $0 |
| Local embeddings (no cache benefit) | $0 |
| LLM fact extraction (gpt-4o-mini) | ~$5 |
| PostgreSQL | $0 (existing) |
| **Total** | **~$5/month** |

**Cost Comparison**:
- **Original plan (Qdrant + custom + Azure embeddings)**: $31/month
- **v1 (Azure AI embeddings)**: $6/month (81% savings)
- **v1 (Local embeddings)**: $5/month (84% savings)
- **Phase 6 (Azure + Redis)**: $5.50/month (82% savings)
- **Phase 6 (Local + Redis)**: $5/month (84% savings, but Redis provides no benefit for local)

**Recommendation**:
- **Best quality**: Azure AI embeddings ($6/month)
- **Best value**: Local embeddings ($5/month, 84% savings vs original plan)
- **Zero cost**: Local embeddings + local LLM for extraction (~$0/month, but lower quality)

---

## Next Steps (Implementation Checklist)

### Phase 1: Setup (Infrastructure)

- [ ] Install pgvectorscale extension via Alembic migration
- [ ] Install Mem0: `pip install mem0ai`
- [ ] Configure Azure AI embeddings in `.env`
- [ ] Test pgvectorscale: Create test vector table + index

### Phase 2: Mem0 Integration

- [ ] Create Mem0 configuration with pgvector + Azure AI
- [ ] Implement `MemoryService` wrapper around Mem0
- [ ] Add LLM relevance filter (`should_extract_facts()`)
- [ ] Test Mem0 add/search/delete operations

### Phase 3: Voice Pipeline Integration

- [ ] Integrate memory into WebRTC handler
- [ ] Integrate memory into Discord plugin
- [ ] Add background fact extraction (fire-and-forget)
- [ ] Implement context injection in LLMService
- [ ] Test end-to-end conversation with memory

### Phase 4: Frontend & API

- [ ] Add memory API endpoints (`/api/memory/*`)
- [ ] Build MemoryPage UI (view/edit/delete facts)
- [ ] Add WebSocket real-time updates for facts
- [ ] Add memory statistics dashboard
- [ ] Test GDPR compliance (export/delete user data)

### Phase 5: Testing & Optimization

- [ ] Unit tests for MemoryService (Mem0 wrapper)
- [ ] Integration tests (real pgvectorscale)
- [ ] E2E tests (conversation → extraction → retrieval)
- [ ] Load test pgvectorscale at 10K, 100K facts
- [ ] Optimize StreamingDiskANN index parameters

### Phase 6: Redis Caching (Optional)

- [ ] Analyze production query patterns (repeated query rate)
- [ ] Add Redis container to docker-compose.yml
- [ ] Implement MemoryCacheService (embedding + result caching)
- [ ] Integrate caching into MemoryService
- [ ] Monitor cache hit rates (target >50%)

### Outstanding Questions

1. **Azure OpenAI Configuration**:
   - Which Azure region for lowest latency?
   - Dedicated vs shared capacity?
   - Rate limiting strategy?

2. **pgvectorscale Production Tuning**:
   - Optimal StreamingDiskANN parameters for 3072-dim vectors?
   - Disk space allocation for vector index?
   - Monitoring and alerting setup?

3. **Mem0 Customization**:
   - Test Mem0 extraction accuracy on VoxBridge conversations
   - Tune Mem0 similarity threshold for deduplication?
   - Custom fact categories vs default Mem0 categories?

4. **GDPR Compliance**:
   - User data export API (download all facts)
   - User data deletion (cascade delete user → facts → pgvectorscale)
   - Data retention policy (auto-delete old facts?)

5. **Performance Benchmarking**:
   - Measure end-to-end latency (extraction + retrieval)
   - Compare Mem0 extraction vs custom (accuracy benchmark)
   - Analyze query patterns to determine if Redis caching is needed (Phase 6)
   - Iterate on extraction prompt

3. **Local Embedding Model Selection**:
   - Benchmark all-mpnet-base-v2 vs bge-large-en-v1.5 vs nomic-embed
   - Quality comparison vs Azure AI
   - Resource usage profiling

---

## Appendix: Environment Variables

```bash
# Mem0 Configuration
MEM0_ENABLED=true

# Embedding Provider Selection
EMBEDDING_PROVIDER=azure  # "azure" or "local"

# Azure AI Embeddings (if EMBEDDING_PROVIDER=azure)
AZURE_EMBEDDING_API_KEY=<your_azure_key>
AZURE_EMBEDDING_ENDPOINT=https://<your_resource>.openai.azure.com/
AZURE_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_EMBEDDING_API_VERSION=2024-12-01-preview
AZURE_EMBEDDING_DIMS=3072

# Local Open-Source Embeddings (if EMBEDDING_PROVIDER=local)
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
LOCAL_EMBEDDING_DIMS=768

# LLM Provider (for Mem0 fact extraction)
OPENROUTER_API_KEY=<your_openrouter_key>  # Already configured for VoxBridge
MEM0_EXTRACTION_MODEL=gpt-4o-mini  # Fast, cheap model for fact extraction

# Memory Extraction
MEMORY_EXTRACTION_ENABLED=true
MEMORY_RELEVANCE_FILTER_ENABLED=true  # LLM filter before extraction

# pgvectorscale Configuration (automatic via Alembic)
# No manual configuration needed - extension is installed via migration

# Database (existing)
DATABASE_URL=postgresql+asyncpg://voxbridge:voxbridge_dev_password@postgres:5432/voxbridge
```

**Add to requirements-bot.txt**:
```
# Memory system
mem0ai>=0.1.0
sentence-transformers>=2.2.0  # For local embeddings (optional, only if EMBEDDING_PROVIDER=local)
```

**Optional Phase 6 - Add Redis** (see Phase 6 section for docker-compose.yml configuration)

---

**Document Status**: ✅ FINAL / APPROVED
**Last Updated**: 2025-11-21
**Architecture**: pgvectorscale + Mem0 + Azure AI + Redis
**Ready for Implementation**: Yes


---

## Deployment Checklist

### Prerequisites

- [ ] PostgreSQL 15+ installed and running
- [ ] Python 3.10+ environment
- [ ] Azure OpenAI account (for Azure embeddings) OR local GPU (for local embeddings)
- [ ] OpenRouter API key (for LLM)

### Azure OpenAI Setup (if using Azure embeddings)

1. **Create Azure OpenAI resource**:
   - Go to https://portal.azure.com
   - Create new "Azure OpenAI" resource
   - Select region (e.g., East US)
   - Choose pricing tier (Standard S0)

2. **Deploy embedding model**:
   - In Azure OpenAI Studio (https://oai.azure.com)
   - Go to "Deployments" → "Create new deployment"
   - Model: `text-embedding-3-large`
   - Deployment name: `text-embedding-3-large` (must match AZURE_EMBEDDING_DEPLOYMENT)
   - Deploy

3. **Get credentials**:
   - Navigate to resource → "Keys and Endpoint"
   - Copy KEY 1 → `AZURE_EMBEDDING_API_KEY`
   - Copy Endpoint → `AZURE_EMBEDDING_ENDPOINT`

### Environment Variables

Create `.env` file:

```bash
# PostgreSQL
POSTGRES_USER=voxbridge
POSTGRES_PASSWORD=voxbridge_dev_password
POSTGRES_DB=voxbridge
DATABASE_URL=postgresql+asyncpg://voxbridge:voxbridge_dev_password@postgres:5432/voxbridge

# Embedding Provider (choose one)
EMBEDDING_PROVIDER=azure  # or 'local'

# Azure AI Embeddings (if EMBEDDING_PROVIDER=azure)
AZURE_EMBEDDING_API_KEY=your_azure_key_here
AZURE_EMBEDDING_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_EMBEDDING_API_VERSION=2024-12-01-preview
AZURE_EMBEDDING_DIMS=3072

# Local Embeddings (if EMBEDDING_PROVIDER=local)
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
LOCAL_EMBEDDING_DIMS=768

# LLM Provider
OPENROUTER_API_KEY=your_openrouter_key

# Discord (optional)
DISCORD_TOKEN=your_discord_bot_token

# N8N (optional)
N8N_WEBHOOK_URL=your_n8n_webhook_url
```

### Database Migration

```bash
# 1. Start PostgreSQL
docker compose up -d postgres

# 2. Wait for health check
docker compose ps | grep postgres

# 3. Run migrations
docker exec voxbridge-api alembic upgrade head

# Expected output:
# INFO  [alembic.runtime.migration] Running upgrade 011 -> 012, install_pgvectorscale
# INFO  [alembic.runtime.migration] Running upgrade 012 -> 013, create_memory_vectors
# INFO  [alembic.runtime.migration] Running upgrade 013 -> 014, add_memory_tables
# INFO  [alembic.runtime.migration] Running upgrade 014 -> 015, create_extraction_queue

# 4. Verify tables exist
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "\dt"
# Should show: users, user_facts, extraction_tasks, agents, sessions, conversations
```

### Installation

```bash
# 1. Install dependencies
docker exec voxbridge-api pip install mem0ai sentence-transformers

# 2. Restart services
docker compose restart voxbridge-api voxbridge-frontend

# 3. Start background worker (automatic on server startup)
# Verify in logs:
docker logs voxbridge-api | grep "Started memory extraction queue worker"
```

### Verification Tests

```bash
# 1. Test Mem0 initialization
docker exec voxbridge-api python -c "
from mem0 import Memory
from src.services.memory_service import MemoryService
from src.database.session import get_db_session
import asyncio

async def test():
    db = await get_db_session()
    ms = MemoryService(db)
    print('✅ MemoryService initialized successfully')
    print(f'Embedding provider: {ms.memory.config}')

asyncio.run(test())
"

# 2. Test queue extraction
# Make a voice call in Discord or WebRTC
# Check extraction queue:
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT id, user_id, status, attempts FROM extraction_tasks ORDER BY created_at DESC LIMIT 5;"

# 3. Test memory retrieval
# Check stored facts:
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT user_id, fact_key, fact_text, importance FROM user_facts LIMIT 10;"
```

### Monitoring

```bash
# Queue health
docker logs voxbridge-api | grep "extraction task"

# Memory stats
curl http://localhost:4900/api/memory/stats | python3 -m json.tool

# Extraction latency
docker logs voxbridge-api | grep "LATENCY.*extraction"
```

### Troubleshooting

**Issue**: "Extension vectorscale does not exist"
```bash
# Solution: Install pgvectorscale manually
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;"
```

**Issue**: "Azure OpenAI authentication failed"
```bash
# Solution: Verify credentials
echo $AZURE_EMBEDDING_API_KEY  # Should not be empty
echo $AZURE_EMBEDDING_ENDPOINT  # Should end with .azure.com/

# Test API manually:
curl -X POST "$AZURE_EMBEDDING_ENDPOINT/openai/deployments/text-embedding-3-large/embeddings?api-version=2024-12-01-preview" \
  -H "api-key: $AZURE_EMBEDDING_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "test"}'
```

**Issue**: "Queue tasks stuck in processing"
```bash
# Solution: Reset stuck tasks
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "UPDATE extraction_tasks SET status='pending' WHERE status='processing' AND created_at < NOW() - INTERVAL '10 minutes';"
```

### Production Recommendations

- [ ] Set `EMBEDDING_PROVIDER=azure` for production (better quality)
- [ ] Enable Redis caching (Phase 6) for >10K users
- [ ] Monitor extraction queue size (alert if >100 pending tasks)
- [ ] Set up automated backups for PostgreSQL
- [ ] Monitor Azure AI costs (should be ~$1/month per 30K conversations)
- [ ] Configure GDPR data export/deletion endpoints
- [ ] Add rate limiting to `/api/memory/*` endpoints

