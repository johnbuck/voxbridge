# Memory vs RAG Architecture Decision

**Date**: December 2025
**Status**: Accepted (revisit when triggers met)

---

## Context

Both Memory and RAG systems share fundamental similarities:

| Aspect | Memory | RAG |
|--------|--------|-----|
| Embedding Model | BAAI/bge-large-en-v1.5 | BAAI/bge-large-en-v1.5 |
| Vector Dimensions | 1024 | 1024 |
| Vector Storage | pgvector | pgvector |
| Purpose | Retrieve context for LLM | Retrieve context for LLM |
| Heavy Dependencies | sentence-transformers, torch | sentence-transformers, torch |

**Current architecture:**
- **Memory**: Mem0 framework in `voxbridge-api` container
  - Automatic fact extraction from conversations
  - `user_memories` (vectors) + `user_facts` (metadata) tables
  - Queue-based background extraction
  - WebSocket notifications for real-time UI updates

- **RAG**: Dedicated `voxbridge-rag` container (as of Dec 2025)
  - Document ingestion and chunking
  - Hybrid search (vector + BM25 + graph)
  - `collections`, `documents`, `document_chunks` tables
  - FlagEmbedding reranker for cross-encoder reranking

---

## Decision

**Keep Memory and RAG in separate containers for now.**

---

## Rationale

1. **Mem0 manages its own embeddings**
   Memory uses the Mem0 framework which internally manages embedding model lifecycle. RAG uses raw `sentence-transformers` directly. These are different code paths that aren't easily unified.

2. **Memory has real-time requirements**
   Memory extraction fires WebSocket events, polls every 5 seconds, and has frontend status hooks. Moving to HTTP-based calls would add latency and complexity.

3. **Different ownership models**
   - Memory: Per-user facts (personal memory)
   - RAG: Per-agent collections (shared knowledge base)

4. **Risk of regression**
   The memory system is working well and tightly integrated. Premature merging could introduce bugs.

---

## Trade-offs

### Current Approach (Separate)

| Pros | Cons |
|------|------|
| Clean separation of concerns | Duplicate embedding model (~2GB GPU memory) |
| Memory tightly integrated with conversation flow | Can't share reranker for memory retrieval |
| Lower refactoring risk | Two codebases doing similar vector operations |
| Mem0 manages its own lifecycle | Duplicate heavy dependencies |

### Future Approach (Merged)

| Pros | Cons |
|------|------|
| Single embedding model | Requires significant refactoring |
| Shared reranker for better retrieval | Memory extraction needs WebSocket proxy |
| All vector operations in one place | Adds latency to memory operations |
| Smaller overall footprint | Higher complexity at service boundary |

---

## Future Direction

```
Phase 1 (Current): Keep separate
    └── Memory in voxbridge-api, RAG in voxbridge-rag
    └── Accept duplicate embedding model for now

Phase 2: Shared embedding service
    └── Create lightweight voxbridge-embeddings service
    └── Both Memory and RAG call it for embeddings
    └── Single model loaded once

Phase 3: Full merge (if warranted)
    └── Combine into voxbridge-knowledge container
    └── Unified retrieval with reranking for all queries
    └── Single place for all vector operations
```

---

## Triggers to Revisit This Decision

- [ ] GPU memory becomes a bottleneck (need to free ~2GB)
- [ ] Want to use RAG's reranker for memory retrieval (higher quality)
- [ ] Replacing Mem0 with custom implementation
- [ ] Building shared embedding service for other uses (e.g., semantic search)
- [ ] Significant refactoring of memory system anyway

---

## Related Documentation

- [`docs/guides/memory-system.md`](../guides/memory-system.md) - Memory system architecture
- [`rag/src/services/retrieval.py`](../../rag/src/services/retrieval.py) - RAG retrieval implementation
- [`src/services/memory_service.py`](../../src/services/memory_service.py) - Memory service implementation

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      voxbridge-api                          │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │  Memory Service │  │   RAG Client    │                  │
│  │  (Mem0)         │  │   (HTTP proxy)  │                  │
│  └────────┬────────┘  └────────┬────────┘                  │
│           │                    │                            │
│           │ embeddings         │ HTTP                       │
│           │ (internal)         │                            │
└───────────┼────────────────────┼────────────────────────────┘
            │                    │
            ▼                    ▼
┌───────────────────┐  ┌─────────────────────────────────────┐
│    PostgreSQL     │  │          voxbridge-rag              │
│    (pgvector)     │  │  ┌─────────────────┐               │
│                   │◄─┼──│ Retrieval Svc   │               │
│  user_memories    │  │  │ (sentence-      │               │
│  user_facts       │  │  │  transformers)  │               │
│  collections      │  │  └─────────────────┘               │
│  documents        │  │  ┌─────────────────┐               │
│  document_chunks  │  │  │ Reranker        │               │
│                   │  │  │ (FlagEmbedding) │               │
└───────────────────┘  │  └─────────────────┘               │
                       └─────────────────────────────────────┘
```

**Note**: Both services load `BAAI/bge-large-en-v1.5` independently. This is the main inefficiency to address in Phase 2.
