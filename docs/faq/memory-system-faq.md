# Memory System FAQ

**Last Updated**: November 23, 2025
**Status**: Dual-Table Architecture Validated

---

## Table of Contents

1. [Architecture Questions](#architecture-questions)
2. [Data Model Questions](#data-model-questions)
3. [Operations Questions](#operations-questions)
4. [Comparison Questions](#comparison-questions)
5. [Troubleshooting](#troubleshooting)

---

## Architecture Questions

### Q1: Why does VoxBridge use two tables (user_facts + user_memories)?

**A**: The **dual-table pattern** separates concerns for optimal performance:

- **user_facts** (Relational Metadata):
  - Purpose: CRUD operations, filtering, sorting, joins
  - Database: PostgreSQL
  - Queries: SQL (WHERE, ORDER BY, GROUP BY)
  - Examples: "Show facts for user X", "Sort by importance", "Filter by agent"

- **user_memories** (Vector Embeddings):
  - Purpose: Semantic similarity search
  - Database: pgvector (via Mem0 framework)
  - Queries: Cosine similarity (vector operations)
  - Examples: "Find facts similar to 'favorite food'", "Semantic search for 'hobbies'"

**Why Not One Table?**
- Mixing relational + vector operations is inefficient
- Vector columns don't support SQL indexes (ORDER BY, GROUP BY)
- Relational columns don't support similarity search
- Separation allows independent optimization (SQL vs vector)

**Industry Validation**: Open WebUI, LangChain, and LlamaIndex all use this pattern.

---

### Q2: Is the dual-table design correct, or should we use a single table?

**A**: ✅ **The dual-table design is correct and industry-validated.**

After comprehensive research comparing VoxBridge with Open WebUI (November 2025), we confirmed:
- **Open WebUI uses dual-table**: File/Knowledge/Memory (metadata) + document_chunk (vectors)
- **VoxBridge uses dual-table**: user_facts (metadata) + user_memories (vectors)
- **Same architectural pattern** for the same reasons (metadata vs embeddings separation)

See `docs/architecture/open-webui-comparison.md` for full analysis.

---

### Q3: What is Mem0, and why does VoxBridge use it?

**A**: **Mem0** is an open-source memory framework that:

1. **Automates fact extraction**: LLM-based structured extraction from conversations
2. **Manages vector storage**: Handles pgvector CRUD operations automatically
3. **Provides relevance filtering**: "Does this conversation contain facts worth extracting?"
4. **Improves accuracy**: +26% improvement over custom RAG implementations (benchmark)

**Why Use Mem0**:
- ✅ Eliminates manual memory management (Open WebUI requires manual upload)
- ✅ Automatic orphan cleanup (Mem0 syncs vector deletions with metadata)
- ✅ Proven accuracy improvement (+26% vs custom approaches)
- ✅ Open-source (MIT license, can fork if needed)

**Trade-off**: Dependency on Mem0 library, but accuracy/automation benefits outweigh lock-in risk.

---

## Data Model Questions

### Q4: What is the relationship between user_facts and user_memories?

**A**: **1:1 relationship** via `user_facts.vector_id`:

```sql
user_facts.vector_id  →  user_memories.id
(Foreign Key)            (Primary Key)
```

**Relationship Rules**:
1. Each `user_fact` has **exactly ONE** corresponding `user_memory` vector
2. `vector_id` must be **UNIQUE** (enforced by database constraint)
3. When a fact is deleted, the vector **must also be deleted** (cascade)

**Migration History**:
- Migration `42bb34dc665e` **incorrectly removed** UNIQUE constraint
- Migration `019` **restored** UNIQUE constraint (November 23, 2025)
- Current state: ✅ UNIQUE constraint enforced

---

### Q5: What happens if vector_id is NULL?

**A**: **Orphaned metadata** - fact exists but has no embedding for semantic search.

**Causes**:
- Fact created before Mem0 was properly configured
- Vector creation failed (Ollama error, network timeout, etc.)
- Sync issue during migration

**Solution**:
```bash
# Run sync script to re-embed orphaned facts
docker exec voxbridge-api python -m src.database.sync_facts

# Dry run to preview changes
docker exec voxbridge-api python -m src.database.sync_facts --dry-run
```

**Prevention**: Mem0 framework ensures vector_id is always set during fact creation.

---

### Q6: What fields does user_facts have, and what do they mean?

**A**: **user_facts schema**:

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `id` | UUID | Primary key | `550e8400-e29b-41d4-a716-446655440000` |
| `user_id` | UUID (FK) | Links to users table | References `users.id` |
| `agent_id` | UUID (FK) | Links to agents table | References `agents.id` |
| `fact_key` | VARCHAR(100) | Fact category | `"hometown"`, `"favorite_color"` |
| `fact_value` | TEXT | Fact content | `"Seattle"`, `"blue"` |
| `fact_text` | TEXT | Natural language | `"User lives in Seattle"` |
| `vector_id` | VARCHAR(255) | Links to vector | `"ab92db79-5351-4a8d-8b31-ec69e888060d"` |
| `importance` | FLOAT | Relevance score (0.0-1.0) | `0.9` (critical), `0.3` (low priority) |
| `validity_start` | TIMESTAMPTZ | Fact became valid | `2025-11-01 10:00:00+00` |
| `validity_end` | TIMESTAMPTZ | Fact expired (NULL = still valid) | `2025-11-15 18:30:00+00` OR `NULL` |
| `created_at` | TIMESTAMPTZ | Creation timestamp | `2025-11-23 03:15:22+00` |
| `updated_at` | TIMESTAMPTZ | Last modification | `2025-11-23 14:22:10+00` |

**Unique Features**:
- `importance`: Prioritize critical facts (name, allergies) over preferences (favorite color)
- `validity_end`: Soft deletion (mark expired, preserve audit trail)
- `fact_key`: Structured categorization (not in Open WebUI)

---

## Operations Questions

### Q7: How does orphan cleanup work when a fact is deleted?

**A**: **Complete cascade deletion** via two mechanisms:

**1. Relational Layer** (PostgreSQL):
```sql
-- Foreign key CASCADE ensures relational integrity
ALTER TABLE user_facts
ADD CONSTRAINT fk_user_facts_user
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
```
- When user is deleted → all their facts are deleted automatically
- PostgreSQL enforces referential integrity

**2. Vector Layer** (Mem0):
```python
# Delete endpoint implementation
@router.delete("/users/{user_id}/facts/{fact_id}")
async def delete_user_fact(user_id: str, fact_id: UUID):
    # Step 1: Get fact (need vector_id before deletion)
    fact = await db.get(UserFact, fact_id)
    vector_id = fact.vector_id

    # Step 2: Delete from PostgreSQL (relational metadata)
    await db.delete(fact)
    await db.commit()

    # Step 3: Delete from Mem0 (vector embeddings)
    memory_service.memory.delete(memory_id=vector_id)
    # ✅ No orphaned vectors - complete cleanup
```

**Result**: ✅ **No orphaned vectors** remain after deletion (unlike Open WebUI).

---

### Q8: How are facts extracted automatically?

**A**: **Queue-based background extraction** via `extraction_tasks` table:

**Flow**:
```
1. User Interaction (Discord voice chat)
   ↓
2. Conversation Logged (user_message + ai_response)
   ↓
3. Queue Extraction Task
   - Table: extraction_tasks
   - Status: 'queued'
   - Task ID: UUID
   ↓
4. Background Worker Picks Up Task
   - Status: 'queued' → 'processing'
   ↓
5. Mem0 Relevance Filter
   - LLM: "Does this conversation contain facts?"
   - If NO: Mark 'completed' (no facts extracted)
   - If YES: Proceed to extraction
   ↓
6. Mem0 Fact Extraction
   - LLM: "Extract structured facts"
   - Returns: fact_key, fact_value, importance
   ↓
7. Embedding Generation
   - Model: BAAI/bge-large-en-v1.5 (1024-dim) OR Azure (3072-dim)
   ↓
8. Dual-Table Insert
   - user_memories: Vector embeddings (Mem0-managed)
   - user_facts: Metadata (vector_id, importance, timestamps)
   ↓
9. WebSocket Broadcast
   - Frontend UI updates in real-time
   - Pending fact card → completed fact card
   ↓
10. Task Status: 'processing' → 'completed'
```

**Advantages**:
- ✅ Automatic (no manual upload like Open WebUI)
- ✅ Asynchronous (doesn't block conversation)
- ✅ Reliable (task queue ensures processing)
- ✅ Observable (WebSocket updates show progress)

---

### Q9: Can I update a fact, or do I need to delete and recreate?

**A**: **Use temporal validity** (soft update):

**Option 1: Soft Update** (Recommended):
```sql
-- Mark old fact as expired
UPDATE user_facts
SET validity_end = NOW()
WHERE fact_key = 'hometown' AND user_id = 'user-123';

-- Create new fact with current information
INSERT INTO user_facts (user_id, fact_key, fact_value, validity_start)
VALUES ('user-123', 'hometown', 'San Francisco', NOW());
```

**Benefits**:
- ✅ Preserves audit trail (historical facts remain)
- ✅ Enables point-in-time queries ("Where did user live in 2023?")
- ✅ GDPR-compliant (soft deletion, no immediate erasure)

**Option 2: Hard Update**:
```python
# Update via API endpoint
PUT /api/memory/users/{user_id}/facts/{fact_id}
{
  "fact_value": "San Francisco",
  "validity_end": null  # Mark as currently valid
}
```

**Trade-off**: Hard update loses historical context.

---

### Q10: How does importance scoring work?

**A**: **0.0-1.0 scale** for fact prioritization:

**Scoring Guidelines**:
- `0.9-1.0`: **Critical** (name, allergies, medical conditions)
- `0.7-0.8`: **High** (occupation, family members, major life events)
- `0.5-0.6`: **Medium** (hometown, hobbies, preferences)
- `0.3-0.4`: **Low** (favorite color, minor preferences)
- `0.0-0.2`: **Trivial** (ephemeral facts, temporary states)

**Automatic Scoring** (Mem0):
```python
# Mem0 LLM-based importance scoring
relevance_prompt = f"""
Rate the importance of this fact on a 0.0-1.0 scale:
- 1.0 = Critical (name, medical, safety)
- 0.5 = Preference (likes, hobbies)
- 0.0 = Trivial (temporary, ephemeral)

Fact: "{fact_text}"
Importance:
"""
importance = await llm_service.generate_response(relevance_prompt)
```

**Usage**:
```sql
-- High-importance facts only (context window budget)
SELECT * FROM user_facts
WHERE importance >= 0.8 AND validity_end IS NULL
ORDER BY importance DESC
LIMIT 10;
```

---

## Comparison Questions

### Q11: How is VoxBridge different from Open WebUI?

**A**: **Key differences** (see `docs/architecture/open-webui-comparison.md` for full analysis):

| Feature | Open WebUI | VoxBridge | Winner |
|---------|-----------|-----------|--------|
| **Dual-Table Design** | ✅ Yes | ✅ Yes | TIE |
| **Automatic Extraction** | ❌ Manual | ✅ Automatic (Mem0) | VoxBridge |
| **Temporal Validity** | ❌ No | ✅ validity_start/end | VoxBridge |
| **Importance Scoring** | ❌ No | ✅ 0.0-1.0 | VoxBridge |
| **Orphan Cleanup** | ❌ Manual scripts | ✅ Automatic (Mem0) | VoxBridge |
| **Hybrid Search** | ✅ BM25 + vector | ❌ Pure vector | Open WebUI |
| **Multi-Vector DB** | ✅ 6 options | ❌ pgvector only | Open WebUI |
| **Accuracy** | Baseline (custom) | +26% (Mem0) | VoxBridge |

**Summary**: VoxBridge is **superior for automatic user memory extraction**, while Open WebUI is **better for manual document RAG** (file uploads, knowledge bases).

---

### Q12: Should VoxBridge switch to Open WebUI's architecture?

**A**: ❌ **No - VoxBridge's architecture is validated and superior** for its use case.

**Research Findings** (November 2025):
1. ✅ **Both use dual-table** - industry-standard pattern (no changes needed)
2. ✅ **VoxBridge advantages** - automatic extraction, temporal validity, importance scoring
3. ❌ **Open WebUI weaknesses** - incomplete cascade deletion, orphaned vectors, manual management

**Recommendation**: **Keep current design**, selectively adopt Open WebUI patterns:
- ✅ Add hybrid search (BM25 + vector + re-ranking) - Phase 3 roadmap
- ✅ Add Qdrant support (optional vector DB) - Low priority (much later)
- ❌ Do NOT adopt dual-collection pattern (2x storage waste)
- ❌ Do NOT replace Mem0 (26% accuracy loss)

---

## Troubleshooting

### Q13: Facts have vector_ids but user_memories table is empty - is this normal?

**A**: ⚠️ **Possible configuration issue** - Mem0 might be using a different backend.

**Diagnosis**:
```bash
# Check if vector_ids are populated
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "
  SELECT COUNT(*) as facts_with_vectors
  FROM user_facts
  WHERE vector_id IS NOT NULL;
"

# Check if vectors exist
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "
  SELECT COUNT(*) as vector_count
  FROM user_memories;
"

# If facts_with_vectors > 0 but vector_count = 0:
# → Mem0 might be using Qdrant or ChromaDB instead of pgvector
```

**Solution**: Verify Mem0 configuration in `memory_service.py`:
```python
config = {
    "vector_store": {
        "provider": "pgvector",  # ← Should be pgvector
        "config": {
            "dbname": "voxbridge",
            "host": "postgres",
            "port": 5432,
            "collection_name": "user_memories"
        }
    }
}
```

**Note**: If Mem0 is using a different backend (Qdrant, ChromaDB), vectors are stored elsewhere (not in `user_memories` table). This is OK as long as `vector_id` is populated and deletion cleanup works.

---

### Q14: How do I manually clean up orphaned vectors?

**A**: **Use the sync script** (no manual SQL needed):

```bash
# Dry run (preview only, no changes)
docker exec voxbridge-api python -m src.database.sync_facts --dry-run

# Actual sync (re-embed orphaned facts)
docker exec voxbridge-api python -m src.database.sync_facts

# Verify sync completed
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "
  SELECT COUNT(*) as orphaned_facts
  FROM user_facts
  WHERE vector_id IS NULL;
"
# Should return: orphaned_facts = 0
```

**What the script does**:
1. Finds facts with `vector_id IS NULL`
2. Re-embeds using Mem0 (`memory.add()`)
3. Updates `vector_id` with new embedding ID
4. Logs progress (found, synced, failed counts)

---

### Q15: How do I delete ALL memories for a user (admin reset)?

**A**: **Use the deletion API** (handles cascade automatically):

**Option 1: Delete User** (cascades to all facts):
```bash
# Delete user (cascades to all facts via FK)
curl -X DELETE http://localhost:4900/api/memory/users/{user_id}
```

**Option 2: Delete Facts Individually**:
```bash
# Get all fact IDs for user
curl http://localhost:4900/api/memory/users/{user_id}/facts

# Delete each fact (Mem0 cleanup automatic)
curl -X DELETE http://localhost:4900/api/memory/users/{user_id}/facts/{fact_id}
```

**Future Enhancement** (Phase 2 roadmap):
```bash
# Admin reset endpoint (delete all facts for user)
curl -X POST http://localhost:4900/api/memory/users/{user_id}/facts/reset \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
```

**Safety**: Deletion requires confirmation parameter to prevent accidental data loss.

---

### Q16: How do I export all memories for GDPR compliance?

**A**: **Future endpoint** (Phase 2 roadmap):

```bash
# Export all user facts as JSON
curl http://localhost:4900/api/memory/users/{user_id}/export \
  -H "Accept: application/json" \
  > user_memories.json

# Export as CSV (optional format)
curl http://localhost:4900/api/memory/users/{user_id}/export?format=csv \
  -H "Accept: text/csv" \
  > user_memories.csv
```

**Current Workaround** (SQL query):
```bash
# Export via PostgreSQL
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "
  COPY (
    SELECT fact_key, fact_value, fact_text, importance,
           validity_start, validity_end, created_at
    FROM user_facts
    WHERE user_id = (SELECT id FROM users WHERE user_id = 'discord_12345')
  ) TO STDOUT WITH CSV HEADER;
" > user_memories.csv
```

---

## Additional Resources

- **Architecture Comparison**: `docs/architecture/open-webui-comparison.md`
- **Database Models**: `src/database/models.py`
- **Memory Service**: `src/services/memory_service.py`
- **API Routes**: `src/routes/memory_routes.py`
- **Sync Script**: `src/database/sync_facts.py`

**Need Help?** Check GitHub Issues or CLAUDE.md for troubleshooting guidance.

---

*Last Updated: November 23, 2025*
