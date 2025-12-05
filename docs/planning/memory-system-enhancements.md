# Memory System Enhancements Plan

**Status**: ✅ Complete (All 7 Phases)
**Branch**: `feature/memory-system`
**Inspired by**: OpenWebUI Adaptive Memory v3.0
**Created**: 2025-12-04
**Updated**: 2025-12-05

---

## Implementation Status

| Phase | Feature | Status | Notes |
|-------|---------|--------|-------|
| 1 | Memory Banks | ✅ Complete | Migration 024, frontend filtering |
| 2 | Pruning (FIFO/LRU) | ✅ Complete | Migrations 025-026, is_protected field |
| 3 | Summarization | ✅ Complete | Migration 027, background worker, LLM integration |
| 4 | Enhanced Extraction | ✅ Complete | Updated prompt with 7 memory categories |
| 5 | LLM Optimization | ✅ Complete | Preference shortcuts, regex patterns, `_extract_preference_shortcut()` |
| 6 | Error Guards | ✅ Complete | `ErrorGuard` circuit breaker, auto-reset after cooldown |
| 7 | Deduplication | ✅ Complete | Embedding + text similarity, `_is_duplicate()`, configurable thresholds |

---

## Executive Summary

This plan outlines enhancements to VoxBridge's memory system, drawing inspiration from OpenWebUI's Adaptive Memory plugin. The goal is to improve memory extraction quality, add organizational features, implement intelligent pruning, and optimize performance.

---

## Current State (VoxBridge) - Updated Dec 2025

### Architecture
- **Dual-table design**: `user_facts` (relational) + `user_memories` (vectors via pgvector)
- **Mem0 framework**: Handles extraction, embedding, and vector CRUD
- **Queue-based extraction**: Background worker processes conversation turns
- **Memory scopes**: Global vs agent-specific (per-agent isolation)
- **Memory banks**: Personal, Work, General, Relationships, Health, Interests, Events
- **Pruning**: FIFO and LRU strategies with protected facts
- **Summarization**: Background worker clusters and summarizes old facts

### Resolved Limitations
1. ~~No memory categorization/banks~~ ✅ Memory banks implemented
2. ~~No pruning strategy (unbounded growth)~~ ✅ FIFO/LRU pruning with configurable limits
3. ~~No memory summarization/clustering~~ ✅ Embedding-based clustering + LLM summarization
4. ~~Basic extraction prompt (relies on Mem0 defaults)~~ ✅ Enhanced prompt with 7 memory categories
5. ~~No LLM call optimization (always uses LLM for extraction)~~ ✅ Preference shortcuts skip LLM for simple statements
6. ~~No error rate monitoring/guards~~ ✅ ErrorGuard circuit breaker with auto-reset cooldown
7. ~~No deduplication (duplicate facts could be stored)~~ ✅ Embedding + text similarity deduplication

---

## Enhancement Phases

### Phase 1: Memory Banks
**Priority**: High
**Effort**: Medium
**Impact**: Better organization and focused retrieval

#### Concept
Categorize memories into domains (Personal, Work, General, etc.) so retrieval can be focused on relevant context.

#### Database Changes
```sql
-- Add memory_bank column to user_facts
ALTER TABLE user_facts ADD COLUMN memory_bank VARCHAR(50) DEFAULT 'General';

-- Add index for bank-based queries
CREATE INDEX idx_user_facts_memory_bank ON user_facts(user_id, memory_bank);
```

#### Configuration
```python
# System settings or agent-level config
allowed_memory_banks: List[str] = ["General", "Personal", "Work", "Hobby"]
default_memory_bank: str = "General"
```

#### Extraction Changes
- Update extraction prompt to request `memory_bank` assignment
- LLM assigns bank based on content context
- Validate bank against allowed list, fallback to default

#### Retrieval Changes
- Add optional `memory_bank` filter to `get_user_memory_context()`
- Agent can specify preferred banks for context injection
- UI can filter facts by bank

#### API Changes
- `POST /api/facts` - Accept `memory_bank` field
- `GET /api/facts` - Add `?bank=Personal` filter
- `PUT /api/facts/{id}` - Allow bank reassignment
- `GET /api/memory-banks` - List available banks

#### Frontend Changes
- Memory page: Bank filter/tabs
- Fact cards: Bank badge
- Agent form: Default bank selection

---

### Phase 2: Intelligent Pruning
**Priority**: High
**Effort**: Medium
**Impact**: Prevents unbounded memory growth

#### Concept
Limit total memories per user and intelligently prune when limits are reached.

#### Configuration
```python
max_total_memories: int = 200  # Per user limit
pruning_strategy: Literal["fifo", "least_relevant", "oldest_accessed"] = "fifo"
pruning_batch_size: int = 10  # How many to prune at once
```

#### Pruning Strategies

1. **FIFO (First In, First Out)**
   - Delete oldest memories first
   - Simple, predictable
   - May lose important old facts

2. **Least Relevant**
   - Calculate relevance to recent conversations
   - Delete memories with lowest scores
   - Preserves important memories regardless of age

3. **Oldest Accessed** (LRU-like)
   - Track `last_accessed_at` timestamp
   - Delete memories not retrieved recently
   - Requires schema change

#### Implementation
```python
async def enforce_memory_limit(user_id: str, new_count: int = 1):
    """Check limit and prune if needed before adding new memories."""
    current_count = await get_user_fact_count(user_id)

    if current_count + new_count > max_total_memories:
        to_prune = (current_count + new_count) - max_total_memories

        if pruning_strategy == "fifo":
            await prune_oldest_facts(user_id, to_prune)
        elif pruning_strategy == "least_relevant":
            await prune_least_relevant_facts(user_id, to_prune, context)
```

#### Database Changes
```sql
-- Optional: Track last access for LRU strategy
ALTER TABLE user_facts ADD COLUMN last_accessed_at TIMESTAMP WITH TIME ZONE;

-- Update on retrieval
UPDATE user_facts SET last_accessed_at = NOW() WHERE id = ANY($1);
```

---

### Phase 3: Memory Summarization
**Priority**: Medium
**Effort**: High
**Impact**: Reduces clutter, improves context density

#### Concept
Periodically cluster related old memories and summarize them into single comprehensive facts.

#### Configuration
```python
enable_summarization: bool = True
summarization_interval_hours: int = 24  # Run daily
summarization_min_memory_age_days: int = 7
summarization_min_cluster_size: int = 3
summarization_max_cluster_size: int = 8
summarization_strategy: Literal["embeddings", "tags", "hybrid"] = "hybrid"
summarization_similarity_threshold: float = 0.7
```

#### Clustering Strategies

1. **Embedding-based**
   - Group memories with high semantic similarity
   - Uses vector cosine similarity
   - Best for catching nuanced relationships

2. **Tag-based**
   - Group by shared fact_key or tags
   - Simpler, more predictable
   - May miss semantically related but differently tagged memories

3. **Hybrid**
   - First group by embedding similarity
   - Then refine with tag matching
   - Best accuracy, higher compute cost

#### Process Flow
```
1. Query old memories (age > min_age_days)
2. Compute embeddings if not cached
3. Cluster using selected strategy
4. For each cluster >= min_size:
   a. Build summary prompt with all memories
   b. Call LLM to generate summary
   c. Create new fact with [summarized] tag
   d. Delete original memories
   e. Delete corresponding vectors
```

#### Summarization Prompt
```python
summarization_prompt = """
You are a memory consolidation assistant. Combine these related memories about a user into a single concise summary.

Rules:
1. Preserve all key information
2. Resolve contradictions (prefer newer information)
3. Remove redundancy
4. Maintain specific details when important
5. Keep the summary under 100 words

Memories to summarize:
{memories}

Output a single paragraph summary.
"""
```

#### Database Changes
```sql
-- Track summarization metadata
ALTER TABLE user_facts ADD COLUMN is_summarized BOOLEAN DEFAULT FALSE;
ALTER TABLE user_facts ADD COLUMN summarized_from JSONB;  -- Array of original fact IDs
```

#### Background Worker
```python
class SummarizationWorker:
    """Background task for periodic memory summarization."""

    async def run_cycle(self):
        for user_id in await get_users_with_old_memories():
            clusters = await find_memory_clusters(user_id)
            for cluster in clusters:
                if len(cluster) >= min_cluster_size:
                    await summarize_cluster(user_id, cluster)
```

---

### Phase 4: Enhanced Extraction Prompt
**Priority**: High
**Effort**: Low
**Impact**: Better extraction quality

#### Current State
- Uses Mem0's default extraction
- No explicit output format enforcement
- No memory bank assignment

#### Enhanced Prompt
```python
memory_extraction_prompt = """
You are an automated JSON data extraction system. Your ONLY function is to identify user-specific, persistent facts from the conversation and output them STRICTLY as a JSON array.

**ABSOLUTE OUTPUT REQUIREMENT:**
- Your ENTIRE response MUST be ONLY a valid JSON array starting with `[` and ending with `]`
- Each element MUST be a JSON object with this structure:
  {
    "fact_text": "Concise fact about the user",
    "fact_key": "category_keyword",
    "importance": 0.0-1.0,
    "memory_bank": "Personal|Work|General"
  }
- If NO relevant user-specific facts are found, output ONLY: []
- DO NOT include ANY text before or after the JSON array

**INFORMATION TO EXTRACT (User-Specific ONLY):**
- Identity: Name, location, age, profession
- Preferences: "I love X", "My favorite is Y"
- Goals: Aspirations, plans, objectives
- Relationships: Family, friends, colleagues
- Possessions: Things owned or desired
- Behaviors: Interests, habits, routines

**MEMORY BANK ASSIGNMENT:**
- "Personal" - Family, hobbies, personal preferences
- "Work" - Professional goals, job skills, work relationships
- "General" - Facts that don't clearly fit elsewhere

**IMPORTANCE SCORING:**
- 1.0: Critical identity facts (name, location)
- 0.8: Strong preferences, important relationships
- 0.6: General interests, casual mentions
- 0.4: Minor details, context-dependent
- 0.2: Trivial mentions

**DO NOT EXTRACT:**
- General knowledge or trivia
- AI commands or meta-requests
- Temporary states ("I'm tired today")

**EXAMPLE OUTPUT:**
[
  {
    "fact_text": "User loves drinking coffee in the morning",
    "fact_key": "preference_coffee",
    "importance": 0.7,
    "memory_bank": "Personal"
  }
]
"""
```

#### Implementation
- Override Mem0's default prompt or post-process its output
- Parse JSON response and map to our `user_facts` schema
- Validate memory_bank against allowed list

---

### Phase 5: LLM Call Optimization
**Priority**: Medium
**Effort**: Medium
**Impact**: Reduced latency and cost

#### Concept
Skip expensive LLM calls when vector similarity is confident enough.

#### Configuration
```python
# Retrieval optimization
use_llm_for_relevance: bool = False  # Default to vector-only
llm_skip_relevance_threshold: float = 0.93  # Skip LLM if all vectors exceed this
vector_similarity_threshold: float = 0.7  # Minimum for initial filtering

# Extraction optimization
enable_short_preference_shortcut: bool = True
short_preference_max_length: int = 60
preference_keywords: List[str] = ["favorite", "love", "like", "enjoy", "prefer", "hate"]
```

#### Retrieval Optimization
```python
async def get_relevant_memories(query: str, user_id: str) -> List[Memory]:
    # Step 1: Vector similarity filtering
    candidates = await vector_search(query, user_id, limit=20)

    # Step 2: Check if all candidates exceed confidence threshold
    if all(m.similarity >= llm_skip_relevance_threshold for m in candidates):
        logger.info("All candidates exceed confidence threshold, skipping LLM")
        return candidates[:top_n]

    # Step 3: Only call LLM if needed
    if use_llm_for_relevance:
        return await llm_rerank(query, candidates)
    else:
        return candidates[:top_n]
```

#### Extraction Shortcuts
```python
async def extract_memories(message: str, user_id: str):
    # Shortcut for obvious preference statements
    if (enable_short_preference_shortcut and
        len(message) <= short_preference_max_length and
        any(kw in message.lower() for kw in preference_keywords)):

        # Direct save without full LLM extraction
        return await save_preference_shortcut(message, user_id)

    # Full extraction pipeline
    return await full_extraction(message, user_id)
```

---

### Phase 6: Error Guards
**Priority**: Low
**Effort**: Low
**Impact**: System stability

#### Concept
Temporarily disable memory features if error rates spike to prevent cascade failures.

#### Configuration
```python
enable_error_guard: bool = True
error_guard_threshold: int = 5  # Errors within window
error_guard_window_seconds: int = 600  # 10 minutes
error_guard_cooldown_seconds: int = 300  # 5 minute cooldown
```

#### Implementation
```python
class ErrorGuard:
    def __init__(self):
        self.error_timestamps = deque()
        self.guard_active = False
        self.guard_activated_at = 0

    def record_error(self):
        now = time.time()
        self.error_timestamps.append(now)

        # Clean old timestamps
        while self.error_timestamps and self.error_timestamps[0] < now - window:
            self.error_timestamps.popleft()

        # Activate guard if threshold exceeded
        if len(self.error_timestamps) >= threshold:
            self.guard_active = True
            self.guard_activated_at = now
            logger.warning("Error guard activated - disabling memory features")

    def is_active(self) -> bool:
        if not self.guard_active:
            return False

        # Auto-deactivate after cooldown
        if time.time() - self.guard_activated_at > cooldown:
            self.guard_active = False
            logger.info("Error guard deactivated - resuming memory features")

        return self.guard_active
```

#### Usage
```python
async def extract_memories(message: str):
    if error_guard.is_active():
        logger.debug("Memory extraction skipped - error guard active")
        return []

    try:
        return await _extract_memories(message)
    except Exception as e:
        error_guard.record_error()
        raise
```

---

### Phase 7: Deduplication Improvements
**Priority**: Medium
**Effort**: Low
**Impact**: Cleaner memory store

#### Current State
- Mem0 may handle some deduplication
- No explicit embedding-based duplicate detection

#### Enhanced Deduplication
```python
deduplicate_memories: bool = True
use_embeddings_for_deduplication: bool = True
embedding_similarity_threshold: float = 0.97  # Very high for duplicates
text_similarity_threshold: float = 0.95  # Fallback

# Bypass for short preference statements
short_preference_no_dedupe_length: int = 100
```

#### Implementation
```python
async def is_duplicate(new_content: str, user_id: str) -> bool:
    existing = await get_user_facts(user_id)

    if use_embeddings_for_deduplication:
        new_embedding = await get_embedding(new_content)

        for fact in existing:
            existing_embedding = await get_embedding(fact.fact_text)
            similarity = cosine_similarity(new_embedding, existing_embedding)

            if similarity >= embedding_similarity_threshold:
                logger.debug(f"Duplicate found (similarity={similarity:.3f})")
                return True
    else:
        # Text-based fallback
        for fact in existing:
            similarity = SequenceMatcher(None, new_content, fact.fact_text).ratio()
            if similarity >= text_similarity_threshold:
                return True

    return False
```

---

## Database Schema Changes Summary

```sql
-- Phase 1: Memory Banks
ALTER TABLE user_facts ADD COLUMN memory_bank VARCHAR(50) DEFAULT 'General';
CREATE INDEX idx_user_facts_memory_bank ON user_facts(user_id, memory_bank);

-- Phase 2: Pruning (optional LRU)
ALTER TABLE user_facts ADD COLUMN last_accessed_at TIMESTAMP WITH TIME ZONE;

-- Phase 3: Summarization
ALTER TABLE user_facts ADD COLUMN is_summarized BOOLEAN DEFAULT FALSE;
ALTER TABLE user_facts ADD COLUMN summarized_from JSONB;

-- Phase 6: Error tracking (optional, can be in-memory)
-- No schema changes needed
```

---

## Configuration Schema

```python
class MemoryConfig(BaseModel):
    """Memory system configuration."""

    # Memory Banks
    allowed_memory_banks: List[str] = ["General", "Personal", "Work"]
    default_memory_bank: str = "General"

    # Pruning
    max_total_memories: int = 200
    pruning_strategy: Literal["fifo", "least_relevant"] = "fifo"
    pruning_batch_size: int = 10

    # Summarization
    enable_summarization: bool = True
    summarization_interval_hours: int = 24
    summarization_min_memory_age_days: int = 7
    summarization_min_cluster_size: int = 3
    summarization_similarity_threshold: float = 0.7

    # LLM Optimization
    use_llm_for_relevance: bool = False
    llm_skip_relevance_threshold: float = 0.93
    vector_similarity_threshold: float = 0.7
    enable_short_preference_shortcut: bool = True

    # Deduplication
    deduplicate_memories: bool = True
    use_embeddings_for_deduplication: bool = True
    embedding_similarity_threshold: float = 0.97

    # Error Guards
    enable_error_guard: bool = True
    error_guard_threshold: int = 5
    error_guard_window_seconds: int = 600
```

---

## Implementation Order

| Phase | Feature | Priority | Effort | Dependencies | Status |
|-------|---------|----------|--------|--------------|--------|
| 1 | Memory Banks | High | Medium | None | ✅ Complete |
| 2 | Pruning | High | Medium | None | ✅ Complete |
| 3 | Summarization | Medium | High | Phase 1 (banks), Phase 2 (pruning) | ✅ Complete |
| 4 | Enhanced Extraction | High | Low | Phase 1 (banks in prompt) | ✅ Complete |
| 5 | LLM Optimization | Medium | Medium | None | 🔜 Pending |
| 6 | Error Guards | Low | Low | None | 🔜 Pending |
| 7 | Deduplication | Medium | Low | None | 🔜 Pending |

---

## Testing Strategy

### Unit Tests
- Memory bank assignment logic
- Pruning strategy selection
- Cluster detection algorithms
- Deduplication similarity calculations
- Error guard activation/deactivation

### Integration Tests
- Full extraction → storage → retrieval flow with banks
- Pruning triggers at memory limit
- Summarization worker cycle
- LLM skip optimization verification

### E2E Tests
- Conversation with memory extraction
- Memory page bank filtering
- Agent-specific bank preferences

---

## Metrics & Observability

### New Metrics
- `memory_bank_distribution` - Count per bank per user
- `memories_pruned_total` - Counter by strategy
- `memories_summarized_total` - Summarization events
- `llm_calls_skipped_total` - Optimization savings
- `extraction_shortcuts_total` - Preference shortcuts used
- `error_guard_activations_total` - Guard triggers

### Logging
```python
logger.info("🏦 Memory saved to bank: {bank}")
logger.info("✂️ Pruned {count} memories using {strategy}")
logger.info("📦 Summarized {count} memories into 1")
logger.info("⚡ LLM call skipped - vector confidence high")
logger.info("🛡️ Error guard activated - {error_count} errors in {window}s")
```

---

## Migration Path

### From Current State
1. Add new columns with defaults (non-breaking)
2. Deploy new extraction prompt
3. Enable pruning (set reasonable limit)
4. Enable summarization (background, non-blocking)
5. Enable optimizations one by one

### Rollback
- All features are configuration-gated
- Disable via `enable_*` flags
- No data loss on rollback

---

## Open Questions

1. **Bank auto-detection**: Should we use LLM for bank assignment or rule-based?
2. **Cross-agent summarization**: Summarize global memories across all agents?
3. **User control**: Let users configure their own memory limits/preferences?
4. **Memory importance decay**: Should importance decrease over time if not accessed?
5. **Contradiction resolution**: How to handle conflicting facts during summarization?

---

## References

- OpenWebUI Adaptive Memory v3.0 (source of inspiration)
- VoxBridge Memory Architecture: `docs/architecture/open-webui-comparison.md`
- Memory System FAQ: `docs/faq/memory-system-faq.md`
- Current Mem0 Integration: `src/services/memory_service.py`
