# Memory System Guide

VoxBridge memory system architecture, patterns, and troubleshooting.

---

## Architecture Overview

VoxBridge uses an **industry-validated dual-table architecture** for memory management, validated through comparison with Open WebUI (November 2025).

### Dual-Table Design

| Table | Manager | Purpose |
|-------|---------|---------|
| `user_memories` | Mem0 | Vector embeddings for semantic similarity search |
| `user_facts` | VoxBridge | Relational metadata for CRUD operations |

### user_memories (Mem0-managed)
- **Data Type**: VECTOR(1024) via pgvector
- **Embedding Model**: BAAI/bge-large-en-v1.5 (1024 dimensions)
- **Purpose**: Semantic search ("Find facts similar to 'favorite food'")
- **Managed by**: Mem0 framework (automatic CRUD)

### user_facts (VoxBridge-managed)
- **Table**: PostgreSQL with foreign keys
- **Fields**: fact_key, fact_value, fact_text, importance, validity_start/end, vector_id, memory_bank, last_accessed_at, is_protected, is_summarized, summarized_from
- **Purpose**: Frontend display, filtering, sorting, joins
- **Queries**: SQL (WHERE, ORDER BY, GROUP BY)

### 1:1 Relationship
- Each `user_fact` has **exactly ONE** corresponding `user_memory` vector
- Linked via `user_facts.vector_id` → `user_memories.id` (UNIQUE constraint)
- Migration `019` (Nov 23, 2025) restored UNIQUE constraint after incorrect removal

---

## Why Dual-Table?

| Reason | Explanation |
|--------|-------------|
| Efficiency | Mixing relational + vector operations in one table is inefficient |
| SQL Indexes | Vector columns don't support SQL indexes (ORDER BY, GROUP BY) |
| Vector Search | Relational columns don't support similarity search |
| Optimization | Separation allows independent optimization (SQL vs vector) |
| Industry Standard | Open WebUI, LangChain, LlamaIndex all use this pattern |

---

## Mem0 Framework Benefits

- Automatic fact extraction from conversations (LLM-based)
- Vector CRUD management (pgvector operations)
- Relevance filtering ("Does this conversation contain facts?")
- +26% accuracy improvement over custom RAG implementations
- Automatic orphan cleanup (syncs vector deletions with metadata)

---

## Key Features

1. **Automatic Extraction**: Queue-based background worker extracts facts from conversations
2. **Temporal Validity**: `validity_start`/`validity_end` for soft deletion and audit trails
3. **Importance Scoring**: 0.0-1.0 scale for fact prioritization (1.0 = critical, 0.0 = trivial)
4. **Complete Cascade Deletion**: When fact is deleted, vector is also deleted (no orphaned data)
5. **Real-time WebSocket Updates**: Frontend receives extraction events (queued → processing → completed)
6. **Memory Banks**: Categorize facts into Personal, Work, General, Relationships, Health, Interests, Events
7. **Pruning Protection**: `is_protected` flag prevents important facts from being pruned
8. **LRU Tracking**: `last_accessed_at` for least-recently-used pruning strategy
9. **Summarization**: Background worker clusters similar old facts and summarizes them via LLM
10. **LLM Optimization**: Preference shortcuts skip LLM for simple "I love X" statements (regex-based)
11. **Deduplication**: Embedding similarity (0.9) + text similarity (0.85) prevents duplicate facts
12. **Error Guards**: Circuit breaker disables extraction after 5 errors in 10min, auto-resets after 5min cooldown

---

## Memory Queue Patterns

### ThreadPoolExecutor for Blocking Operations

VoxBridge uses ThreadPoolExecutor to prevent event loop blocking when calling Mem0's synchronous APIs.

**Problem**: Mem0's `memory.add()` uses `concurrent.futures.wait()` which blocks the async event loop for ~56 seconds during fact extraction (35s LLM + 20s embeddings + 1s storage).

**Solution**: Wrap blocking Mem0 calls with `loop.run_in_executor()` to run them in a thread pool:

```python
# In MemoryService.__init__
self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mem0_extraction")

# When calling blocking Mem0 methods
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(
    self.executor,
    lambda: self.memory.add(messages=[...], user_id=...)
)
```

**Key Implementation Points**:
- ThreadPoolExecutor initialized in `src/services/memory_service.py` (lines 90-94)
- Used in automatic extraction: `_extract_facts_from_turn()` (lines 269-278)
- Used in manual fact creation: `src/routes/memory_routes.py` (lines 250-259)
- Cleanup via `__del__()` method (lines 597-602)

---

## WebSocket Real-Time Notifications

Memory extraction events are broadcast via WebSocket for real-time UI updates.

### Events

| Event | Description |
|-------|-------------|
| `memory_extraction_queued` | Task added to queue |
| `memory_extraction_processing` | Processing started |
| `memory_extraction_completed` | Successfully completed (includes `facts_count`) |
| `memory_extraction_failed` | Failed or retrying (includes `error`, `attempts`) |

### Frontend Integration

```typescript
// In MemoryPage.tsx
useMemoryExtractionStatus({
  onCompleted: (task) => {
    toast.success(`Extracted ${task.facts_count} facts`);
    queryClient.invalidateQueries({ queryKey: ['facts', userId] });
  },
  onFailed: (task) => {
    toast.error(task.error || 'Extraction failed');
  }
});
```

### Files
- Backend: `src/services/memory_service.py` (broadcasting logic)
- Frontend: `frontend/src/hooks/useMemoryExtractionStatus.ts` (WebSocket subscription)

---

## Queue Metrics & Observability

### Metrics Endpoint

**GET** `/api/metrics/extraction-queue`

```json
{
  "pending": 5,
  "processing": 2,
  "completed": 142,
  "failed": 3,
  "avg_duration_sec": 58.3,
  "oldest_pending_age_sec": 12.5
}
```

### Periodic Logging

Queue worker logs metrics every 60 seconds (every 12 iterations of 5-second polling):
```
🧠 Memory extraction queue metrics: 3 tasks processed this batch
```

---

## Common Operations

```bash
# Sync orphaned facts (facts with no vectors)
docker exec voxbridge-api python -m src.database.sync_facts

# View memory extraction queue metrics
curl http://localhost:4900/api/metrics/extraction-queue | python3 -m json.tool

# View all facts for a user
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT fact_key, fact_value, importance FROM user_facts WHERE user_id = '<uuid>';"

# Check for orphaned facts (should return 0)
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT COUNT(*) FROM user_facts WHERE vector_id IS NULL;"

# Trigger manual summarization cycle
curl -X POST http://localhost:4900/api/summarization/run | python3 -m json.tool

# View summarized facts
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT fact_key, fact_text, summarized_from FROM user_facts WHERE is_summarized = true;"

# View facts by memory bank
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c \
  "SELECT memory_bank, COUNT(*) FROM user_facts GROUP BY memory_bank;"
```

---

## Troubleshooting

### Issue: Facts not being extracted

1. Check queue status:
   ```bash
   curl http://localhost:4900/api/metrics/extraction-queue
   ```

2. View extraction logs:
   ```bash
   docker logs voxbridge-api | grep -E "🧠|🧵"
   ```

3. Verify MemoryService initialized:
   - Look for "✅ MemoryService initialized" in startup logs

4. Check database connectivity:
   ```bash
   docker exec voxbridge-postgres psql -U voxbridge -c "SELECT COUNT(*) FROM extraction_tasks;"
   ```

### Issue: Event loop blocking (heartbeat failures)

**Symptom**: "heartbeat blocked for more than 20 seconds"

**Fix**: Verify ThreadPoolExecutor is being used:
- Check `src/services/memory_service.py` lines 269-278 for `run_in_executor()` wrapper
- Check `src/routes/memory_routes.py` lines 250-259 for manual creation wrapper

### Issue: WebSocket notifications not appearing

1. Check WebSocket connection:
   - Frontend should show "🔌 WebSocket client connected"

2. Verify `ws_manager` connected to `memory_service`:
   - Check `server.py:1216-1217`

3. Check browser console for WebSocket errors

4. Verify WebSocket URL:
   - Should be `ws://localhost:4900/ws/events`

---

## Related Documentation

- **Architecture Analysis**: [docs/architecture/open-webui-comparison.md](../architecture/open-webui-comparison.md)
- **FAQ**: [docs/faq/memory-system-faq.md](../faq/memory-system-faq.md)
- **Enhancement Plan**: [docs/planning/archive/memory-system-enhancements.md](../planning/archive/memory-system-enhancements.md)
- **Migration**: `alembic/versions/20251123_2030_019_restore_vector_id_unique.py`
- **Sync Script**: `src/database/sync_facts.py`

---

## Key Files

| File | Description |
|------|-------------|
| `src/services/memory_service.py` | Core memory service with Mem0 integration |
| `src/routes/memory_routes.py` | Memory API endpoints |
| `src/database/models.py` | UserFact, ExtractionTask models |
| `src/database/sync_facts.py` | Re-embed orphaned facts script |
| `frontend/src/hooks/useMemoryExtractionStatus.ts` | WebSocket subscription hook |
