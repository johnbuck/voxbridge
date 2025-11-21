# VoxBridge Multi-Agent Support Implementation Plan

**Created:** October 21, 2025
**Author:** Claude Code Analysis
**Status:** Planning Phase
**Estimated Effort:** 8-12 development days

---

## 📋 Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current Architecture Analysis](#current-architecture-analysis)
3. [Research Findings](#research-findings)
4. [Implementation Plan](#implementation-plan)
5. [Phase Details](#phase-details)
6. [Architecture Diagrams](#architecture-diagrams)
7. [Technical References](#technical-references)

---

## Executive Summary

### Current State

VoxBridge is fundamentally a **single-speaker, single-agent system** with the following architectural constraints:

- ❌ **Global speaker lock** - Only 1 user can be transcribed at a time
- ❌ **Single static webhook URL** - All traffic goes to one n8n agent
- ❌ **No session/conversation tracking** - Each turn is isolated
- ❌ **No persistent storage** - All state is in-memory
- ❌ **Singleton architecture** - Cannot scale horizontally

### Proposed Solution

A **7-phase implementation plan** to transform VoxBridge into a multi-agent, multi-user concurrent system:

1. **Session Management** - PostgreSQL + Redis for persistent state
2. **Queue-Based Concurrency** - Replace speaker lock with per-user queues
3. **Agent Routing Service** - Route transcripts to appropriate n8n agents
4. **Enhanced Payload** - Add conversation context and session tracking
5. **User Agent Selection** - Discord slash commands for agent preferences
6. **Configuration** - Runtime-configurable routing and agent definitions
7. **Infrastructure** - Docker Compose updates for new services

### Key Benefits

✅ Multiple users can speak simultaneously (queue-based fairness)
✅ Multiple n8n agents can run in parallel (routing strategies)
✅ Conversation context preserved across turns (session management)
✅ User preference for agent selection (Discord commands)
✅ Scalable architecture (distributed via Redis/PostgreSQL)

---

## Current Architecture Analysis

### Critical Blockers for Multi-Agent Support

Detailed analysis saved at: `/home/wiley/Docker/voxbridge/ANALYSIS_n8n_WEBHOOKS_SESSIONS.md`

#### 1. Global Speaker Lock (`src/speaker_manager.py:86-107`)

```python
async def on_speaking_start(self, user_id: str, audio_stream) -> bool:
    """Handle user starting to speak"""

    # BLOCKER: Only one speaker allowed
    if self.active_speaker:
        logger.info(f"🔇 Ignoring {user_id} - {self.active_speaker} is currently speaking")
        return False  # Second speaker IGNORED

    # Lock to this speaker (GLOBAL STATE)
    self.active_speaker = user_id
    self.lock_start_time = time.time()
```

**Impact:**
- Only 1 user can be transcribed at a time
- Other speakers completely ignored (not queued)
- Cannot process multiple transcriptions in parallel
- Cannot route to different agents simultaneously

#### 2. Single Static Webhook URL (`src/speaker_manager.py:52-68`)

```python
# Configuration loaded at startup
n8n_webhook_prod = os.getenv('N8N_WEBHOOK_URL')
n8n_webhook_test = os.getenv('N8N_WEBHOOK_TEST_URL')
test_mode = os.getenv('N8N_TEST_MODE', 'false').lower() == 'true'

# Single webhook URL selected
if test_mode and n8n_webhook_test:
    self.n8n_webhook_url = n8n_webhook_test
else:
    self.n8n_webhook_url = n8n_webhook_prod
```

**Impact:**
- Cannot route same transcript to multiple agents
- Cannot branch to different workflows
- Single point of failure
- No agent selection logic

#### 3. No Session/Conversation Context (`src/speaker_manager.py:272-277`)

```python
payload = {
    'text': transcript,
    'userId': self.active_speaker,      # Only user ID
    'timestamp': datetime.now().isoformat(),
    'useStreaming': self.use_streaming
}
# Missing: conversationId, sessionId, agentId, turnNumber, context
```

**Impact:**
- No `conversationId` to link multiple turns
- No `sessionId` to track multi-agent sessions
- No agent selection information
- No context routing rules

#### 4. No Persistent Storage

**Current architecture:**
- ❌ No Redis for session storage
- ❌ No Database for user context
- ❌ No File-based session store
- ❌ No Distributed cache
- ✅ Only in-memory instance variables

**Impact:**
- Cannot remember user preferences across restarts
- Cannot store multi-turn conversation history
- Cannot implement user-specific routing logic
- Cannot scale to multiple bot instances

#### 5. Singleton Architecture (`src/discord_bot.py:65-69`)

```python
# Global singleton SpeakerManager
speaker_manager = SpeakerManager()
```

**Impact:**
- One `SpeakerManager` instance per bot
- Cannot have per-agent isolation
- Global state prevents concurrent processing
- Cannot scale horizontally

### Current Data Flow

```
User speaks in Discord
    ↓
AudioReceiver.write(user, opus_data)
    ↓
user_id extracted (only identifier)
    ↓
on_speaking_start(user_id, stream)
    ├─ if active_speaker exists:
    │   └─ IGNORE this speaker, return False ❌
    └─ else:
        └─ Lock: active_speaker = user_id
           ├─ Create WhisperClient
           ├─ Stream audio to WhisperX
           ├─ Silence/timeout timers
           └─ Wait for finalization
               ↓
           finalize() called
               ↓
           Get transcript
               ↓
           Unlock: active_speaker = None
               ↓
           _send_to_n8n(transcript)
               ↓
           POST to single webhook ⚠️
               ↓
           Receive response
               ↓
           StreamingResponseHandler
               ↓
           Play in Discord
```

---

## Research Findings

### Industry Best Practices (2025)

#### Multi-Agent Routing Approaches

**Source:** Web search results from leading voice AI platforms

1. **LLM-Powered Dynamic Routing**
   - Advanced LLMs analyze queries and route based on context
   - Zero-shot functionality (no predefined intents)
   - Eliminates need for extensive training data

2. **Agent Orchestration Patterns**
   - Each agent executes and decides to finish or route to another
   - Handoffs common pattern (agent-to-agent control transfer)
   - AgentMaster-style decomposition into specialized workflows

3. **Voice Bot Session Management**
   - Session control critical for latency and interruptions
   - Session persistence across multiple processing nodes
   - Geographic distribution and load balancing

#### Concurrent Processing Architectures

**Source:** Gladia, WhisperLiveKit, Assembly AI research

1. **Queue-Based Approaches**
   - Queue serialization per session prevents overlapping actions
   - Worker pools publish availability to Redis
   - Main service initiates connections to most available worker

2. **Concurrency Management Patterns**
   - Async queues, actor models, race condition handling
   - **Finite State Machines:** Track lifecycle (listening → processing → speaking → ready)
   - **Actor Model:** Each processing unit has own state + message queue

3. **Performance Considerations**
   - Concurrent processing capabilities
   - Geographic server distribution
   - Load balancing for usage spikes

#### Discord Bot Session Management

**Source:** Stack Overflow, GitHub examples, Redis documentation

1. **Redis + PostgreSQL Pattern**
   - Redis for fast caching (~1ms response time)
   - PostgreSQL for long-term persistence
   - Combined approach: Try Redis first, fallback to PostgreSQL

2. **Session Storage Structure**
   ```
   session:<user_id> → {agentId, conversationId, lastActivity, state}
   speaker_queue:<channel_id> → [user_id_1, user_id_2, ...]
   active_transcriptions:<user_id> → {status, startTime, whisperId}
   ```

3. **Multi-Container Session Management**
   - Redis as shared cache/database for all containers
   - Ensures session validity regardless of which container serves request
   - Built-in TTL (time to live) for automatic cleanup

#### Webhook Routing in Microservices

**Source:** Solace, Convoy, Hookdeck articles

1. **Webhook Gateway Pattern**
   - Central infrastructure for ingesting and routing webhooks
   - Route to internal backend services AND external client endpoints
   - Match headers and payload to determine destinations

2. **Event Routing and Branching**
   - Gateway receives events and routes to one or more destinations
   - Enables fan-out (single event → multiple microservices)
   - Routing rules based on content, headers, or user context

3. **Architecture Components**
   - Message broker for queuing
   - Rate limiter for controlled relay
   - Load balancer for distributing webhook load
   - Ordering preservation via queue reads

---

## Implementation Plan

### Phase Timeline & Priorities

| Phase | Priority | Effort | Impact | Dependencies |
|-------|----------|--------|--------|--------------|
| **1. Session Management** | CRITICAL | High (2-3 days) | Foundation for all features | PostgreSQL, Redis, asyncpg |
| **2. Queue System** | CRITICAL | Medium (1-2 days) | Enables concurrency | None |
| **3. Agent Routing** | HIGH | Medium (2 days) | Core multi-agent feature | Phase 1 |
| **4. Enhanced Payload** | HIGH | Low (4 hours) | Context passing | Phase 1, 3 |
| **5. User Selection** | MEDIUM | Low (4 hours) | UX improvement | Phase 1, 3 |
| **6. Configuration** | MEDIUM | Low (2 hours) | Operational flexibility | None |
| **7. Infrastructure** | CRITICAL | Low (2 hours) | Deployment support | Docker Compose |

**Total Estimated Effort:** 8-12 days of development

---

## Phase Details

### Phase 1: Session Management Layer (Foundation)

**Goal:** Track user sessions and conversation context persistently

#### 1.1 Database Schema (PostgreSQL)

**Create file:** `init.sql`

```sql
-- User sessions table
CREATE TABLE user_sessions (
    user_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    conversation_id UUID NOT NULL DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true
);

-- Conversation history table
CREATE TABLE conversation_history (
    id SERIAL PRIMARY KEY,
    conversation_id UUID NOT NULL,
    user_id TEXT NOT NULL,
    turn_number INT NOT NULL,
    transcript TEXT NOT NULL,
    response TEXT,
    agent_id TEXT,
    timestamp TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Agent configuration table
CREATE TABLE agent_config (
    agent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    webhook_url TEXT NOT NULL,
    routing_rules JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_conversation_history_conversation_id ON conversation_history(conversation_id);
CREATE INDEX idx_conversation_history_user_id ON conversation_history(user_id);
CREATE INDEX idx_conversation_history_timestamp ON conversation_history(timestamp DESC);
CREATE INDEX idx_user_sessions_conversation_id ON user_sessions(conversation_id);
CREATE INDEX idx_agent_config_active ON agent_config(is_active);

-- Sample agent data
INSERT INTO agent_config (agent_id, name, description, webhook_url, routing_rules, is_active) VALUES
('general_assistant', 'General Assistant', 'General purpose AI assistant', 'https://n8n-tunnel.iamjohnbuck.com/webhook/general', '{"keywords": ["help", "question", "general"]}', true),
('technical_support', 'Technical Support', 'Technical troubleshooting and coding help', 'https://n8n-tunnel.iamjohnbuck.com/webhook/tech-support', '{"keywords": ["bug", "error", "code", "debug"]}', true),
('creative_writer', 'Creative Writer', 'Creative writing and storytelling', 'https://n8n-tunnel.iamjohnbuck.com/webhook/creative', '{"keywords": ["story", "poem", "creative", "write"]}', true);
```

#### 1.2 Database Manager

**Create file:** `src/database/db_manager.py`

```python
"""
Database connection pool manager for PostgreSQL
"""
import asyncpg
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages PostgreSQL connection pool"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.database_url = os.getenv('DATABASE_URL')

    async def connect(self):
        """Initialize connection pool"""
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")

        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info("✅ Connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            raise

    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("🔒 Closed database connection pool")

    async def execute(self, query: str, *args):
        """Execute a query without returning results"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        """Execute a query and return all results"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        """Execute a query and return first result"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """Execute a query and return single value"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

# Global instance
db_manager = DatabaseManager()
```

#### 1.3 Session Store

**Create file:** `src/database/session_store.py`

```python
"""
Session store for managing user sessions and conversation history
"""
import logging
from typing import Optional, List, Dict
from datetime import datetime
import uuid
from src.database.db_manager import db_manager

logger = logging.getLogger(__name__)

class SessionStore:
    """Manages user sessions, conversation history, and agent assignments"""

    async def get_or_create_session(self, user_id: str, default_agent_id: str = 'general_assistant') -> dict:
        """Get existing session or create new one"""

        # Try to get existing session
        row = await db_manager.fetchrow(
            "SELECT * FROM user_sessions WHERE user_id = $1 AND is_active = true",
            user_id
        )

        if row:
            # Update last activity
            await db_manager.execute(
                "UPDATE user_sessions SET updated_at = NOW() WHERE user_id = $1",
                user_id
            )
            return dict(row)

        # Create new session
        conversation_id = uuid.uuid4()
        session_id = f"sess_{user_id}_{int(datetime.now().timestamp())}"

        await db_manager.execute(
            """
            INSERT INTO user_sessions (user_id, agent_id, conversation_id, session_id)
            VALUES ($1, $2, $3, $4)
            """,
            user_id, default_agent_id, conversation_id, session_id
        )

        logger.info(f"📝 Created new session for user {user_id} with agent {default_agent_id}")

        return {
            'user_id': user_id,
            'agent_id': default_agent_id,
            'conversation_id': conversation_id,
            'session_id': session_id,
            'turn_count': 0
        }

    async def get_session(self, user_id: str) -> Optional[dict]:
        """Get active session for user"""
        row = await db_manager.fetchrow(
            "SELECT * FROM user_sessions WHERE user_id = $1 AND is_active = true",
            user_id
        )
        return dict(row) if row else None

    async def set_user_agent(self, user_id: str, agent_id: str):
        """Set user's preferred agent"""
        await db_manager.execute(
            """
            INSERT INTO user_sessions (user_id, agent_id, conversation_id, session_id)
            VALUES ($1, $2, gen_random_uuid(), $3)
            ON CONFLICT (user_id)
            DO UPDATE SET agent_id = $2, updated_at = NOW()
            """,
            user_id, agent_id, f"sess_{user_id}_{int(datetime.now().timestamp())}"
        )
        logger.info(f"🔄 Updated user {user_id} to use agent {agent_id}")

    async def add_turn(self, conversation_id: uuid.UUID, user_id: str,
                       transcript: str, response: str, agent_id: str):
        """Add a turn to conversation history"""

        # Get current turn number
        turn_number = await db_manager.fetchval(
            "SELECT COALESCE(MAX(turn_number), 0) + 1 FROM conversation_history WHERE conversation_id = $1",
            conversation_id
        )

        await db_manager.execute(
            """
            INSERT INTO conversation_history
            (conversation_id, user_id, turn_number, transcript, response, agent_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            conversation_id, user_id, turn_number, transcript, response, agent_id
        )

        logger.info(f"💬 Added turn {turn_number} to conversation {conversation_id}")

    async def get_conversation_history(self, conversation_id: uuid.UUID, limit: int = 5) -> List[dict]:
        """Get recent conversation history"""
        rows = await db_manager.fetch(
            """
            SELECT transcript, response, turn_number, timestamp
            FROM conversation_history
            WHERE conversation_id = $1
            ORDER BY turn_number DESC
            LIMIT $2
            """,
            conversation_id, limit
        )
        return [dict(row) for row in reversed(rows)]

    async def get_agent(self, agent_id: str) -> Optional[dict]:
        """Get agent configuration"""
        row = await db_manager.fetchrow(
            "SELECT * FROM agent_config WHERE agent_id = $1 AND is_active = true",
            agent_id
        )
        return dict(row) if row else None

    async def get_agent_by_name(self, name: str) -> Optional[dict]:
        """Get agent by name"""
        row = await db_manager.fetchrow(
            "SELECT * FROM agent_config WHERE name ILIKE $1 AND is_active = true",
            name
        )
        return dict(row) if row else None

    async def get_all_agents(self) -> List[dict]:
        """Get all active agents"""
        rows = await db_manager.fetch(
            "SELECT * FROM agent_config WHERE is_active = true ORDER BY name"
        )
        return [dict(row) for row in rows]
```

#### 1.4 Redis Client

**Create file:** `src/cache/redis_client.py`

```python
"""
Redis client for session caching and queue management
"""
import redis.asyncio as redis
import json
import os
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

class RedisClient:
    """Async Redis client for caching and queue operations"""

    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    async def connect(self):
        """Connect to Redis"""
        try:
            self.client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self.client.ping()
            logger.info("✅ Connected to Redis")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            raise

    async def close(self):
        """Close Redis connection"""
        if self.client:
            await self.client.close()
            logger.info("🔒 Closed Redis connection")

    async def get_session(self, user_id: str) -> Optional[dict]:
        """Get cached session"""
        data = await self.client.get(f"session:{user_id}")
        return json.loads(data) if data else None

    async def set_session(self, user_id: str, session: dict, ttl: int = 86400):
        """Cache session with TTL (default 24 hours)"""
        await self.client.setex(
            f"session:{user_id}",
            ttl,
            json.dumps(session, default=str)
        )

    async def queue_speaker(self, channel_id: str, user_id: str):
        """Add speaker to queue"""
        await self.client.rpush(f"speaker_queue:{channel_id}", user_id)

    async def dequeue_speaker(self, channel_id: str) -> Optional[str]:
        """Remove and return next speaker from queue"""
        return await self.client.lpop(f"speaker_queue:{channel_id}")

    async def get_queue_size(self, channel_id: str) -> int:
        """Get current queue size"""
        return await self.client.llen(f"speaker_queue:{channel_id}")

    async def set_active_transcription(self, user_id: str, data: dict, ttl: int = 300):
        """Mark user as actively being transcribed"""
        await self.client.setex(
            f"active_transcription:{user_id}",
            ttl,
            json.dumps(data, default=str)
        )

    async def get_active_transcription(self, user_id: str) -> Optional[dict]:
        """Get active transcription status"""
        data = await self.client.get(f"active_transcription:{user_id}")
        return json.loads(data) if data else None

    async def clear_active_transcription(self, user_id: str):
        """Clear active transcription status"""
        await self.client.delete(f"active_transcription:{user_id}")

# Global instance
redis_client = RedisClient()
```

#### 1.5 Dependencies Update

**Update `pyproject.toml`:**

```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "asyncpg>=0.30.0",
    "redis>=5.2.0",
]
```

---

### Phase 2: Queue-Based Concurrency System

**Goal:** Allow multiple users to be transcribed simultaneously with queue-based fairness

#### 2.1 Replace Speaker Lock with Queue System

**Update `src/speaker_manager.py`:**

```python
"""
Speaker Manager - Queue-based concurrent processing
"""
import asyncio
import logging
from typing import Dict, Optional
from src.database.session_store import SessionStore
from src.cache.redis_client import RedisClient

logger = logging.getLogger(__name__)

class SpeakerManager:
    def __init__(self):
        # NEW: Remove global speaker lock
        # self.active_speaker = None  # REMOVED

        # NEW: Track active transcriptions per user
        self.active_transcriptions: Dict[str, dict] = {}

        # NEW: Processing queue
        self.speaker_queue: asyncio.Queue = asyncio.Queue()

        # NEW: Concurrency settings
        self.max_concurrent = int(os.getenv('MAX_CONCURRENT_SPEAKERS', '3'))
        self.processing_workers = []

        # NEW: Database and cache
        self.session_store = SessionStore()
        self.redis = RedisClient()

        # Existing components
        self.voice_connection = None
        self.streaming_handler = None
        self.audio_receiver = None

        # Configuration
        self.silence_threshold_ms = int(os.getenv('SILENCE_THRESHOLD_MS', '800'))
        self.max_speaking_time_ms = int(os.getenv('MAX_SPEAKING_TIME_MS', '45000'))
        self.use_streaming = os.getenv('USE_STREAMING', 'true').lower() == 'true'

    async def start_workers(self, num_workers: int = 3):
        """Start background processing workers"""
        for i in range(num_workers):
            worker = asyncio.create_task(self._processing_worker(i))
            self.processing_workers.append(worker)
        logger.info(f"🏃 Started {num_workers} processing workers")

    async def on_speaking_start(self, user_id: str, audio_stream) -> bool:
        """Queue speaker for processing (no longer blocks)"""

        # Check if user already has active transcription
        if user_id in self.active_transcriptions:
            logger.info(f"🔄 {user_id} already being transcribed")
            return False

        # Check Redis for active transcription (distributed check)
        active = await self.redis.get_active_transcription(user_id)
        if active:
            logger.info(f"🔄 {user_id} has active transcription in cache")
            return False

        # Add to queue
        queue_item = {
            'user_id': user_id,
            'audio_stream': audio_stream,
            'queued_at': time.time()
        }

        await self.speaker_queue.put(queue_item)

        queue_size = self.speaker_queue.qsize()
        logger.info(f"📋 Queued {user_id} (queue size: {queue_size})")

        return True

    async def _processing_worker(self, worker_id: int):
        """Worker that processes transcription queue"""
        logger.info(f"👷 Worker {worker_id} started")

        while True:
            try:
                # Check if we're at concurrent limit
                if len(self.active_transcriptions) >= self.max_concurrent:
                    await asyncio.sleep(0.1)
                    continue

                # Get next speaker from queue (with timeout)
                try:
                    item = await asyncio.wait_for(
                        self.speaker_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                user_id = item['user_id']
                audio_stream = item['audio_stream']

                wait_time = time.time() - item['queued_at']
                logger.info(f"🎬 Worker {worker_id} processing {user_id} (waited {wait_time:.1f}s)")

                # Start transcription in background
                task = asyncio.create_task(
                    self._process_transcription(user_id, audio_stream)
                )

                self.active_transcriptions[user_id] = {
                    'task': task,
                    'started_at': time.time(),
                    'worker_id': worker_id
                }

                # Mark in Redis
                await self.redis.set_active_transcription(user_id, {
                    'status': 'processing',
                    'started_at': time.time(),
                    'worker_id': worker_id
                })

            except Exception as e:
                logger.error(f"❌ Worker {worker_id} error: {e}")
                await asyncio.sleep(1)

    async def _process_transcription(self, user_id: str, audio_stream):
        """Process a single user's transcription (runs concurrently)"""
        try:
            logger.info(f"🎙️ Starting transcription for {user_id}")

            # Create WhisperX client for this user
            whisper_client = WhisperClient()
            await whisper_client.connect(user_id)

            # Stream audio to WhisperX
            await self._stream_audio(user_id, audio_stream, whisper_client)

            # Finalize and get transcript
            transcript = await whisper_client.finalize()
            await whisper_client.close()

            if transcript:
                logger.info(f"✅ Transcription complete for {user_id}: \"{transcript}\"")

                # Send to appropriate agent(s)
                await self._send_to_agents(user_id, transcript)
            else:
                logger.info(f"⚠️ Empty transcript for {user_id}")

        except Exception as e:
            logger.error(f"❌ Transcription failed for {user_id}: {e}")

        finally:
            # Clean up
            if user_id in self.active_transcriptions:
                del self.active_transcriptions[user_id]

            await self.redis.clear_active_transcription(user_id)

            logger.info(f"🏁 Finished processing {user_id}")

    async def _stream_audio(self, user_id: str, audio_stream, whisper_client):
        """Stream audio to WhisperX with silence detection"""
        last_audio_time = time.time()
        start_time = time.time()

        silence_threshold_s = self.silence_threshold_ms / 1000.0
        max_speaking_time_s = self.max_speaking_time_ms / 1000.0

        async for audio_chunk in audio_stream:
            # Send to WhisperX
            await whisper_client.send_audio(audio_chunk)
            last_audio_time = time.time()

            # Check for max speaking time
            elapsed = time.time() - start_time
            if elapsed > max_speaking_time_s:
                logger.info(f"⏱️ Max speaking time reached for {user_id}")
                break

            # Check for silence
            silence_duration = time.time() - last_audio_time
            if silence_duration > silence_threshold_s:
                logger.info(f"🔇 Silence detected for {user_id}")
                break
```

---

### Phase 3: Agent Routing Service

**Goal:** Route transcripts to appropriate n8n agents based on user context

#### 3.1 Routing Strategies

**Create file:** `src/routing/routing_strategy.py`

```python
"""
Routing strategies for agent selection
"""
from enum import Enum

class RoutingStrategy(Enum):
    """Available routing strategies"""
    USER_PREFERENCE = "user_preference"  # User selects agent
    CONTENT_BASED = "content_based"      # LLM analyzes content
    ROUND_ROBIN = "round_robin"          # Distribute load
    BROADCAST = "broadcast"              # Send to multiple agents
```

#### 3.2 Agent Router

**Create file:** `src/routing/agent_router.py`

```python
"""
Agent routing service for directing transcripts to appropriate n8n agents
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime
import asyncio
import uuid

from src.routing.routing_strategy import RoutingStrategy
from src.database.session_store import SessionStore
from src.cache.redis_client import RedisClient

logger = logging.getLogger(__name__)

class AgentRouter:
    """Routes transcripts to appropriate n8n agent(s)"""

    def __init__(self, session_store: SessionStore, redis: RedisClient):
        self.session_store = session_store
        self.redis = redis
        self.round_robin_index = 0

    async def route(
        self,
        user_id: str,
        transcript: str,
        strategy: RoutingStrategy = RoutingStrategy.USER_PREFERENCE
    ) -> List[Dict]:
        """
        Route transcript to appropriate agent(s)

        Args:
            user_id: Discord user ID
            transcript: Transcribed speech
            strategy: Routing strategy to use

        Returns:
            List of {agent_id, webhook_url, payload} dicts
        """

        # Get or create user session
        session = await self.session_store.get_or_create_session(user_id)

        # Route based on strategy
        if strategy == RoutingStrategy.USER_PREFERENCE:
            agent = await self._get_agent_for_user(user_id, session)
            return [await self._build_webhook_call(agent, user_id, transcript, session)]

        elif strategy == RoutingStrategy.CONTENT_BASED:
            agent = await self._llm_select_agent(transcript)
            return [await self._build_webhook_call(agent, user_id, transcript, session)]

        elif strategy == RoutingStrategy.BROADCAST:
            agents = await self.session_store.get_all_agents()
            return [
                await self._build_webhook_call(agent, user_id, transcript, session)
                for agent in agents
            ]

        elif strategy == RoutingStrategy.ROUND_ROBIN:
            agent = await self._next_round_robin_agent()
            return [await self._build_webhook_call(agent, user_id, transcript, session)]

        else:
            raise ValueError(f"Unknown routing strategy: {strategy}")

    async def _get_agent_for_user(self, user_id: str, session: dict) -> dict:
        """Get user's preferred agent from session"""
        agent_id = session.get('agent_id')
        agent = await self.session_store.get_agent(agent_id)

        if not agent:
            # Fallback to default
            logger.warning(f"⚠️ Agent {agent_id} not found, using default")
            agent = await self.session_store.get_agent('general_assistant')

        return agent

    async def _llm_select_agent(self, transcript: str) -> dict:
        """
        Use LLM to select best agent based on transcript content

        NOTE: This is a placeholder - implement with your LLM of choice
        """
        # TODO: Implement LLM-based routing
        # For now, use keyword matching as fallback

        agents = await self.session_store.get_all_agents()

        transcript_lower = transcript.lower()

        for agent in agents:
            routing_rules = agent.get('routing_rules', {})
            keywords = routing_rules.get('keywords', [])

            if any(keyword in transcript_lower for keyword in keywords):
                logger.info(f"🎯 Matched agent {agent['name']} via keywords")
                return agent

        # Default to general assistant
        return await self.session_store.get_agent('general_assistant')

    async def _next_round_robin_agent(self) -> dict:
        """Get next agent in round-robin rotation"""
        agents = await self.session_store.get_all_agents()

        if not agents:
            raise ValueError("No active agents available")

        agent = agents[self.round_robin_index % len(agents)]
        self.round_robin_index += 1

        return agent

    async def _build_webhook_call(
        self,
        agent: dict,
        user_id: str,
        transcript: str,
        session: dict
    ) -> dict:
        """Build enhanced webhook payload with context"""

        # Get conversation history
        conversation_id = session['conversation_id']
        history = await self.session_store.get_conversation_history(conversation_id, limit=5)

        # Build context
        context = {
            'previousTurns': [
                {
                    'transcript': turn['transcript'],
                    'response': turn['response'],
                    'turnNumber': turn['turn_number']
                }
                for turn in history
            ],
            'userPreferences': session.get('metadata', {})
        }

        # Build enhanced payload
        payload = {
            'text': transcript,
            'userId': user_id,
            'conversationId': str(conversation_id),
            'sessionId': session['session_id'],
            'agentId': agent['agent_id'],
            'turnNumber': len(history) + 1,
            'timestamp': datetime.now().isoformat(),
            'useStreaming': True,
            'context': context
        }

        return {
            'agent_id': agent['agent_id'],
            'agent_name': agent['name'],
            'webhook_url': agent['webhook_url'],
            'payload': payload
        }
```

#### 3.3 Update SpeakerManager to Use Router

**Update `src/speaker_manager.py`:**

```python
from src.routing.agent_router import AgentRouter
from src.routing.routing_strategy import RoutingStrategy

class SpeakerManager:
    def __init__(self):
        # ... existing init ...

        # NEW: Agent router
        self.agent_router = AgentRouter(self.session_store, self.redis)

        # NEW: Routing strategy from environment
        self.routing_strategy = RoutingStrategy(
            os.getenv('ROUTING_STRATEGY', 'user_preference')
        )

    async def _send_to_agents(self, user_id: str, transcript: str) -> None:
        """Send transcript to appropriate agent(s) via router"""

        try:
            # Use router to determine destination(s)
            webhook_calls = await self.agent_router.route(
                user_id=user_id,
                transcript=transcript,
                strategy=self.routing_strategy
            )

            logger.info(f"📤 Routing to {len(webhook_calls)} agent(s)")

            # Execute webhook calls
            if len(webhook_calls) == 1:
                # Single agent - direct call
                await self._execute_webhook(webhook_calls[0], user_id)
            else:
                # Multiple agents - concurrent calls
                await asyncio.gather(*[
                    self._execute_webhook(call, user_id)
                    for call in webhook_calls
                ])

        except Exception as e:
            logger.error(f"❌ Failed to send to agents: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True
    )
    async def _execute_webhook(self, call: dict, user_id: str) -> None:
        """Execute individual webhook call with retry"""

        agent_id = call['agent_id']
        agent_name = call['agent_name']
        webhook_url = call['webhook_url']
        payload = call['payload']

        logger.info(f"📤 Sending to {agent_name} ({agent_id}): {webhook_url}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            if payload['useStreaming']:
                # Streaming response
                await self._handle_streaming_response(
                    client,
                    webhook_url,
                    payload,
                    agent_id
                )
            else:
                # Non-streaming response
                response = await client.post(webhook_url, json=payload)
                response.raise_for_status()

                data = response.json()
                if 'content' in data:
                    # Play response
                    await self._play_response(user_id, data['content'])

        # Save to conversation history
        conversation_id = uuid.UUID(payload['conversationId'])
        await self.session_store.add_turn(
            conversation_id=conversation_id,
            user_id=user_id,
            transcript=payload['text'],
            response='',  # Will be updated after streaming completes
            agent_id=agent_id
        )
```

---

### Phase 4: Enhanced Webhook Payload

**Goal:** Add conversation context and session tracking to webhook payloads

#### Enhanced Payload Structure

```json
{
  "text": "what time is it?",
  "userId": "12345678",
  "conversationId": "550e8400-e29b-41d4-a716-446655440000",
  "sessionId": "sess_12345678_1729526400",
  "agentId": "general_assistant",
  "turnNumber": 5,
  "timestamp": "2025-10-21T14:30:00",
  "useStreaming": true,
  "context": {
    "previousTurns": [
      {
        "transcript": "hello",
        "response": "Hi! How can I help you?",
        "turnNumber": 1
      },
      {
        "transcript": "what's the weather",
        "response": "It's sunny and 72°F today.",
        "turnNumber": 2
      }
    ],
    "userPreferences": {
      "voiceMode": "clone",
      "temperature": 0.75
    }
  },
  "metadata": {
    "channelId": "1429982041348378776",
    "guildId": "680488880935403563"
  }
}
```

This payload is already implemented in the `AgentRouter._build_webhook_call()` method from Phase 3.

---

### Phase 5: User Agent Selection

**Goal:** Allow users to select their agent via Discord slash commands

#### 5.1 Discord Slash Commands

**Update `src/discord_bot.py`:**

```python
@bot.tree.command(name="agent", description="Select or view your AI agent")
@app_commands.describe(
    action="Action to perform",
    agent_name="Name of the agent to select"
)
@app_commands.choices(action=[
    app_commands.Choice(name="select", value="select"),
    app_commands.Choice(name="list", value="list"),
    app_commands.Choice(name="info", value="info")
])
async def agent_command(
    interaction: discord.Interaction,
    action: str,
    agent_name: str = None
):
    """Manage user's agent selection"""

    user_id = str(interaction.user.id)
    session_store = speaker_manager.session_store

    if action == "list":
        # Show available agents
        agents = await session_store.get_all_agents()

        if not agents:
            await interaction.response.send_message(
                "❌ No agents available",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🤖 Available AI Agents",
            description="Select an agent using `/agent select <name>`",
            color=0x00ff00
        )

        for agent in agents:
            embed.add_field(
                name=f"**{agent['name']}**",
                value=agent['description'] or "No description",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    elif action == "select":
        # Set user's agent preference
        if not agent_name:
            await interaction.response.send_message(
                "❌ Please specify an agent name using `/agent select <name>`",
                ephemeral=True
            )
            return

        # Find agent by name (case-insensitive)
        agent = await session_store.get_agent_by_name(agent_name)

        if not agent:
            await interaction.response.send_message(
                f"❌ Agent '{agent_name}' not found. Use `/agent list` to see available agents.",
                ephemeral=True
            )
            return

        # Update user's agent preference
        await session_store.set_user_agent(user_id, agent['agent_id'])

        embed = discord.Embed(
            title="✅ Agent Updated",
            description=f"Now using: **{agent['name']}**",
            color=0x00ff00
        )
        embed.add_field(
            name="Description",
            value=agent['description'] or "No description",
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    elif action == "info":
        # Show current agent
        session = await session_store.get_session(user_id)

        if not session:
            await interaction.response.send_message(
                "ℹ️ You haven't selected an agent yet. Use `/agent select <name>` to choose one.",
                ephemeral=True
            )
            return

        agent = await session_store.get_agent(session['agent_id'])

        if not agent:
            await interaction.response.send_message(
                "❌ Your selected agent is no longer available",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🤖 Current Agent: {agent['name']}",
            description=agent['description'] or "No description",
            color=0x0099ff
        )

        # Add additional info
        embed.add_field(
            name="Agent ID",
            value=f"`{agent['agent_id']}`",
            inline=True
        )

        embed.add_field(
            name="Status",
            value="🟢 Active" if agent['is_active'] else "🔴 Inactive",
            inline=True
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="session", description="View your current session info")
async def session_command(interaction: discord.Interaction):
    """Show user's current session information"""

    user_id = str(interaction.user.id)
    session_store = speaker_manager.session_store

    session = await session_store.get_session(user_id)

    if not session:
        await interaction.response.send_message(
            "ℹ️ You don't have an active session yet. Speak in a voice channel to start one!",
            ephemeral=True
        )
        return

    agent = await session_store.get_agent(session['agent_id'])
    history = await session_store.get_conversation_history(
        session['conversation_id'],
        limit=3
    )

    embed = discord.Embed(
        title="📊 Your Session",
        color=0x0099ff
    )

    embed.add_field(
        name="Current Agent",
        value=f"**{agent['name']}**" if agent else "Unknown",
        inline=True
    )

    embed.add_field(
        name="Conversation Turns",
        value=str(len(history)),
        inline=True
    )

    embed.add_field(
        name="Session ID",
        value=f"`{session['session_id']}`",
        inline=False
    )

    if history:
        recent = "\n".join([
            f"**Turn {turn['turn_number']}:** {turn['transcript'][:50]}..."
            for turn in history[:3]
        ])
        embed.add_field(
            name="Recent Turns",
            value=recent,
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# Register slash commands on bot ready
@bot.event
async def on_ready():
    logger.info(f'✅ {bot.user} has connected to Discord!')

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ Synced {len(synced)} slash command(s)")
    except Exception as e:
        logger.error(f"❌ Failed to sync commands: {e}")

    # Connect to database and Redis
    await db_manager.connect()
    await redis_client.connect()

    # Start processing workers
    await speaker_manager.start_workers(num_workers=3)
```

---

### Phase 6: Configuration

**Goal:** Runtime-configurable routing and agent definitions

#### 6.1 Environment Variables

**Update `.env`:**

```env
# ============================================================
# VoxBridge Environment Configuration
# ============================================================

# Discord
DISCORD_TOKEN=your_discord_token_here

# WhisperX Server
WHISPER_SERVER_URL=ws://voxbridge-whisperx:4901
WHISPER_LANGUAGE=en

# Chatterbox TTS
CHATTERBOX_URL=http://chatterbox-tts-api-uv-blackwell:4123/v1

# ============================================================
# DATABASE & CACHE (NEW)
# ============================================================

# PostgreSQL
DATABASE_URL=postgresql://voxbridge:your_password_here@postgres:5432/voxbridge

# Redis
REDIS_URL=redis://redis:6379/0

# ============================================================
# CONCURRENCY SETTINGS (NEW)
# ============================================================

# Maximum concurrent speakers being transcribed
MAX_CONCURRENT_SPEAKERS=3

# Number of background processing workers
PROCESSING_WORKERS=3

# ============================================================
# AGENT ROUTING (NEW)
# ============================================================

# Routing strategy: user_preference | content_based | round_robin | broadcast
ROUTING_STRATEGY=user_preference

# Default agent ID for new users
DEFAULT_AGENT_ID=general_assistant

# Agent configuration file path
AGENTS_CONFIG_PATH=./config/agents.json

# ============================================================
# SESSION MANAGEMENT (NEW)
# ============================================================

# Session TTL in hours (default 24 hours)
SESSION_TTL_HOURS=24

# Maximum conversation history to include in context
CONVERSATION_HISTORY_LIMIT=5

# ============================================================
# SPEAKER MANAGEMENT
# ============================================================

# Silence detection threshold in milliseconds
SILENCE_THRESHOLD_MS=800

# Maximum speaking time in milliseconds
MAX_SPEAKING_TIME_MS=45000

# ============================================================
# STREAMING
# ============================================================

# Enable streaming responses from n8n
USE_STREAMING=true

# Enable clause-based sentence splitting
USE_CLAUSE_SPLITTING=true

# Enable parallel TTS generation
USE_PARALLEL_TTS=false
```

#### 6.2 Agent Configuration File

**Create `config/agents.json`:**

```json
{
  "agents": [
    {
      "id": "general_assistant",
      "name": "General Assistant",
      "description": "General purpose AI assistant for everyday questions and tasks",
      "webhook_url": "https://n8n-tunnel.iamjohnbuck.com/webhook/16a9d95c-dfa2-41f1-93a4-13f05d3b8fbe",
      "is_active": true,
      "routing_rules": {
        "keywords": ["help", "question", "general", "what", "how", "why"],
        "priority": 1
      }
    },
    {
      "id": "technical_support",
      "name": "Technical Support",
      "description": "Technical troubleshooting, coding help, and debugging assistance",
      "webhook_url": "https://n8n-tunnel.iamjohnbuck.com/webhook/tech-support",
      "is_active": true,
      "routing_rules": {
        "keywords": ["bug", "error", "code", "debug", "technical", "programming"],
        "priority": 2
      }
    },
    {
      "id": "creative_writer",
      "name": "Creative Writer",
      "description": "Creative writing, storytelling, and imaginative content generation",
      "webhook_url": "https://n8n-tunnel.iamjohnbuck.com/webhook/creative",
      "is_active": true,
      "routing_rules": {
        "keywords": ["story", "poem", "creative", "write", "imagine", "create"],
        "priority": 2
      }
    }
  ]
}
```

---

### Phase 7: Infrastructure Updates

**Goal:** Deploy PostgreSQL and Redis services with Docker Compose

#### 7.1 Docker Compose Updates

**Update `docker-compose.yml`:**

```yaml
version: '3.8'

services:
  # ============================================================
  # PostgreSQL Database (NEW)
  # ============================================================
  postgres:
    image: postgres:17-alpine
    container_name: voxbridge-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: voxbridge
      POSTGRES_PASSWORD: ${DB_PASSWORD:-changeme}
      POSTGRES_DB: voxbridge
    volumes:
      - ../zexternal-volumes/voxbridge-postgres:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    networks:
      - bot-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U voxbridge"]
      interval: 10s
      timeout: 5s
      retries: 5
    ports:
      - "5432:5432"  # Expose for development (remove in production)

  # ============================================================
  # Redis Cache (NEW)
  # ============================================================
  redis:
    image: redis:7-alpine
    container_name: voxbridge-redis
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - ../zexternal-volumes/voxbridge-redis:/data
    networks:
      - bot-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    ports:
      - "6379:6379"  # Expose for development (remove in production)

  # ============================================================
  # WhisperX Server (Existing)
  # ============================================================
  voxbridge-whisperx:
    build:
      context: .
      dockerfile: docker/Dockerfile.whisperx.blackwell
    container_name: voxbridge-whisperx
    restart: unless-stopped
    volumes:
      - ./src/whisper_server.py:/app/whisper_server.py
      - ../zexternal-volumes/whisperx-models:/root/.cache/whisperx
    environment:
      WHISPER_MODEL: base.en
      WHISPER_DEVICE: cuda
      WHISPER_COMPUTE_TYPE: float16
    networks:
      - bot-network
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['1']  # RTX 5060 Ti
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:4902/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
    ports:
      - "4901:4901"
      - "4902:4902"

  # ============================================================
  # VoxBridge Discord Bot (Updated)
  # ============================================================
  voxbridge-api:
    build:
      context: .
      dockerfile: docker/Dockerfile.discord
    container_name: voxbridge-api
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      voxbridge-whisperx:
        condition: service_healthy
    volumes:
      - ./src:/app/src:ro
      - ./config:/app/config:ro
    environment:
      # Discord
      DISCORD_TOKEN: ${DISCORD_TOKEN}

      # WhisperX
      WHISPER_SERVER_URL: ws://voxbridge-whisperx:4901
      WHISPER_LANGUAGE: en

      # Chatterbox TTS
      CHATTERBOX_URL: http://chatterbox-tts-api-uv-blackwell:4123/v1

      # Database & Cache (NEW)
      DATABASE_URL: postgresql://voxbridge:${DB_PASSWORD:-changeme}@postgres:5432/voxbridge
      REDIS_URL: redis://redis:6379/0

      # Concurrency (NEW)
      MAX_CONCURRENT_SPEAKERS: ${MAX_CONCURRENT_SPEAKERS:-3}
      PROCESSING_WORKERS: ${PROCESSING_WORKERS:-3}

      # Routing (NEW)
      ROUTING_STRATEGY: ${ROUTING_STRATEGY:-user_preference}
      DEFAULT_AGENT_ID: ${DEFAULT_AGENT_ID:-general_assistant}
      AGENTS_CONFIG_PATH: /app/config/agents.json

      # Session Management (NEW)
      SESSION_TTL_HOURS: ${SESSION_TTL_HOURS:-24}
      CONVERSATION_HISTORY_LIMIT: ${CONVERSATION_HISTORY_LIMIT:-5}

      # Speaker Management
      SILENCE_THRESHOLD_MS: ${SILENCE_THRESHOLD_MS:-800}
      MAX_SPEAKING_TIME_MS: ${MAX_SPEAKING_TIME_MS:-45000}

      # Streaming
      USE_STREAMING: ${USE_STREAMING:-true}
      USE_CLAUSE_SPLITTING: ${USE_CLAUSE_SPLITTING:-true}
      USE_PARALLEL_TTS: ${USE_PARALLEL_TTS:-false}
    networks:
      - bot-network
      - pinkleberry_bridge
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4900/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    ports:
      - "4900:4900"

# ============================================================
# Networks
# ============================================================
networks:
  bot-network:
    driver: bridge
  pinkleberry_bridge:
    external: true
```

#### 7.2 Create Volume Directories

```bash
# Create new volume directories
mkdir -p ../zexternal-volumes/voxbridge-postgres
mkdir -p ../zexternal-volumes/voxbridge-redis

# Verify all volumes exist
ls -la ../zexternal-volumes/
```

#### 7.3 Update .env.example

**Create `.env.example`:**

```env
# ============================================================
# VoxBridge Environment Configuration Template
# Copy this file to .env and fill in your values
# ============================================================

# Discord Bot Token
DISCORD_TOKEN=your_discord_token_here

# Database Password
DB_PASSWORD=your_secure_password_here

# WhisperX Configuration
WHISPER_SERVER_URL=ws://voxbridge-whisperx:4901
WHISPER_LANGUAGE=en

# Chatterbox TTS API
CHATTERBOX_URL=http://chatterbox-tts-api-uv-blackwell:4123/v1

# Database URL
DATABASE_URL=postgresql://voxbridge:your_password_here@postgres:5432/voxbridge

# Redis URL
REDIS_URL=redis://redis:6379/0

# Concurrency Settings
MAX_CONCURRENT_SPEAKERS=3
PROCESSING_WORKERS=3

# Agent Routing
ROUTING_STRATEGY=user_preference
DEFAULT_AGENT_ID=general_assistant

# Session Management
SESSION_TTL_HOURS=24
CONVERSATION_HISTORY_LIMIT=5

# Speaker Settings
SILENCE_THRESHOLD_MS=800
MAX_SPEAKING_TIME_MS=45000

# Streaming Configuration
USE_STREAMING=true
USE_CLAUSE_SPLITTING=true
USE_PARALLEL_TTS=false
```

---

## Architecture Diagrams

### Before: Single-Agent Architecture

```
┌────────────────────────────────────────────────────┐
│                  CURRENT STATE                     │
│            (Single Agent, Blocking)                │
└────────────────────────────────────────────────────┘

User 1 speaks
    ↓
[Speaker Lock] ← BLOCKS User 2 ❌
    ↓
WhisperX Transcription
    ↓
[Single Webhook URL]
    ↓
n8n Agent (single)
    ↓
TTS Response
    ↓
Discord Voice

User 2 speaks ❌ IGNORED
User 3 speaks ❌ IGNORED
```

### After: Multi-Agent Architecture

```
┌────────────────────────────────────────────────────┐
│                  NEW ARCHITECTURE                  │
│     (Multi-Agent, Concurrent, Queue-Based)         │
└────────────────────────────────────────────────────┘

User 1 speaks ──┐
User 2 speaks ──┼──→ [Processing Queue] ──→ [Worker Pool]
User 3 speaks ──┘         ↓                      ↓
                    [Redis Cache]          [3 Workers]
                          ↓                      ↓
                  ┌───────┴────────┐      ┌─────┴─────┐
                  │                │      │           │
                  ↓                ↓      ↓           ↓
            WhisperX 1      WhisperX 2  WhisperX 3
                  ↓                ↓      ↓
                  └────────┬───────┘      │
                           ↓              ↓
                   [Agent Router]   [Session DB]
                           ↓
            ┌──────────────┼──────────────┐
            ↓              ↓              ↓
        Agent A        Agent B        Agent C
        (n8n)          (n8n)          (n8n)
            ↓              ↓              ↓
            └──────────────┼──────────────┘
                           ↓
                    [TTS Generation]
                           ↓
                    Discord Voice
```

### Session & Context Flow

```
┌─────────────────────────────────────────────────────┐
│            SESSION & CONTEXT MANAGEMENT             │
└─────────────────────────────────────────────────────┘

User speaks
    ↓
Get/Create Session
    ├─ Check Redis Cache (~1ms)
    ├─ Fallback to PostgreSQL
    └─ Create if not exists
        ↓
    [Session Data]
    ├─ conversationId: UUID
    ├─ sessionId: String
    ├─ agentId: String
    ├─ turnNumber: Int
    └─ metadata: JSONB
        ↓
Fetch Conversation History
    ├─ Last 5 turns from PostgreSQL
    └─ Include in webhook payload
        ↓
Route to Agent
    ├─ User preference (default)
    ├─ Content-based (LLM)
    ├─ Round-robin (load balance)
    └─ Broadcast (multi-agent)
        ↓
Send Enhanced Payload
    {
      "text": "...",
      "userId": "...",
      "conversationId": "...",
      "sessionId": "...",
      "agentId": "...",
      "turnNumber": 5,
      "context": {
        "previousTurns": [...],
        "userPreferences": {...}
      }
    }
        ↓
Save to History
    └─ PostgreSQL conversation_history table
```

---

## Technical References

### File Structure

```
voxbridge/
├── src/
│   ├── discord_bot.py              # Main bot (updated with slash commands)
│   ├── speaker_manager.py          # Queue-based speaker management
│   ├── streaming_handler.py        # TTS streaming (existing)
│   ├── whisper_client.py           # WhisperX client (existing)
│   ├── whisper_server.py           # WhisperX server (existing)
│   ├── database/                   # NEW
│   │   ├── __init__.py
│   │   ├── db_manager.py           # PostgreSQL connection pool
│   │   └── session_store.py        # Session CRUD operations
│   ├── cache/                      # NEW
│   │   ├── __init__.py
│   │   └── redis_client.py         # Redis client wrapper
│   └── routing/                    # NEW
│       ├── __init__.py
│       ├── routing_strategy.py     # Routing strategy enum
│       └── agent_router.py         # Agent routing service
├── config/                         # NEW
│   └── agents.json                 # Agent definitions
├── tests/
│   ├── unit/
│   └── e2e/
├── docker/
│   ├── Dockerfile.discord
│   └── Dockerfile.whisperx.blackwell
├── docker-compose.yml              # Updated with PostgreSQL & Redis
├── init.sql                        # NEW - Database initialization
├── .env                            # Environment variables
├── .env.example                    # NEW - Environment template
├── pyproject.toml                  # Updated dependencies
└── README.md
```

### Database Schema Reference

**Tables:**
- `user_sessions` - Active user sessions with agent assignments
- `conversation_history` - Multi-turn conversation logs
- `agent_config` - Agent definitions and webhook URLs

**Indexes:**
- `idx_conversation_history_conversation_id` - Fast history lookup
- `idx_user_sessions_conversation_id` - Session-to-conversation mapping
- `idx_agent_config_active` - Active agent filtering

### Redis Key Patterns

```
session:<user_id>                      → Session cache (JSON)
speaker_queue:<channel_id>             → Queue of pending speakers (list)
active_transcription:<user_id>         → Active transcription status (JSON)
```

### API Endpoints (Existing)

- `GET /health` - Bot health check
- `GET /status` - Detailed status info
- `POST /voice/join` - Join voice channel
- `POST /voice/leave` - Leave voice channel
- `POST /voice/speak` - Direct TTS playback

### Discord Slash Commands (New)

- `/agent list` - Show available agents
- `/agent select <name>` - Select preferred agent
- `/agent info` - Show current agent
- `/session` - View session information

---

## Implementation Checklist

### Phase 1: Session Management ✅
- [ ] Create `init.sql` with database schema
- [ ] Implement `src/database/db_manager.py`
- [ ] Implement `src/database/session_store.py`
- [ ] Implement `src/cache/redis_client.py`
- [ ] Update `pyproject.toml` dependencies
- [ ] Test database connection and CRUD operations

### Phase 2: Queue System ✅
- [ ] Update `src/speaker_manager.py` with queue logic
- [ ] Remove global speaker lock
- [ ] Implement `_processing_worker()` method
- [ ] Implement `_process_transcription()` method
- [ ] Add concurrent transcription tracking
- [ ] Test with multiple users speaking simultaneously

### Phase 3: Agent Routing ✅
- [ ] Create `src/routing/routing_strategy.py`
- [ ] Implement `src/routing/agent_router.py`
- [ ] Add routing logic to `SpeakerManager`
- [ ] Implement all 4 routing strategies
- [ ] Test routing with multiple agents

### Phase 4: Enhanced Payload ✅
- [ ] Verify payload structure in `AgentRouter`
- [ ] Add conversation history to context
- [ ] Test context passing to n8n webhooks

### Phase 5: User Selection ✅
- [ ] Add `/agent` slash command to `discord_bot.py`
- [ ] Add `/session` slash command
- [ ] Implement agent list, select, and info actions
- [ ] Sync slash commands on bot startup
- [ ] Test slash commands in Discord

### Phase 6: Configuration ✅
- [ ] Update `.env` with new variables
- [ ] Create `.env.example`
- [ ] Create `config/agents.json`
- [ ] Load agents from JSON on startup
- [ ] Test configuration loading

### Phase 7: Infrastructure ✅
- [ ] Update `docker-compose.yml` with PostgreSQL
- [ ] Update `docker-compose.yml` with Redis
- [ ] Create volume directories
- [ ] Add health checks for new services
- [ ] Test complete stack startup

### Integration Testing ✅
- [ ] Test end-to-end flow with single user
- [ ] Test concurrent users (3+ simultaneously)
- [ ] Test agent switching via slash commands
- [ ] Test conversation context preservation
- [ ] Test all routing strategies
- [ ] Load test with multiple users

### Documentation ✅
- [ ] Update README.md
- [ ] Document new slash commands
- [ ] Document routing strategies
- [ ] Document database schema
- [ ] Add migration guide from old version

---

## Migration Guide

### Upgrading from Single-Agent to Multi-Agent

**Step 1: Backup Data**
```bash
# Backup current .env
cp .env .env.backup

# Note: Old version had no persistent data to backup
```

**Step 2: Update Environment**
```bash
# Copy new environment template
cp .env.example .env

# Fill in required values:
# - DISCORD_TOKEN (from old .env)
# - DB_PASSWORD (new, create secure password)
# - Agent webhook URLs
```

**Step 3: Create Volumes**
```bash
# Create new volume directories
mkdir -p ../zexternal-volumes/voxbridge-postgres
mkdir -p ../zexternal-volumes/voxbridge-redis
```

**Step 4: Update Agent Configuration**
```bash
# Create config directory
mkdir -p config

# Copy agents.json template
cp config/agents.json.example config/agents.json

# Edit config/agents.json with your n8n webhook URLs
```

**Step 5: Deploy**
```bash
# Pull new images
docker compose pull

# Build updated bot
docker compose build

# Start services (database will auto-initialize)
docker compose up -d

# Watch logs
docker compose logs -f voxbridge-api
```

**Step 6: Verify**
```bash
# Check all services are healthy
docker compose ps

# Test slash commands in Discord
# /agent list
# /agent select general_assistant
# /session
```

**Step 7: Test Multi-User**
- Have 3+ users join voice channel
- All users speak simultaneously
- Verify all get transcribed (no blocking)
- Check logs for concurrent processing

---

## Performance Considerations

### Scalability Limits

**Current Design:**
- 3 concurrent speakers (configurable via `MAX_CONCURRENT_SPEAKERS`)
- Single Discord bot instance
- Single WhisperX server (GPU-bound)

**Bottlenecks:**
- **WhisperX GPU capacity** - Limited by GPU memory and compute
- **Database connections** - Pooled (max 10 connections)
- **Redis memory** - Default 256MB (can increase)

**Future Scaling Options:**
1. **Horizontal Scaling:**
   - Multiple Discord bot instances
   - Load balancer for WhisperX servers
   - Shared PostgreSQL + Redis

2. **GPU Scaling:**
   - Multiple WhisperX servers with different GPUs
   - Round-robin distribution

3. **Caching Strategy:**
   - Increase Redis memory limit
   - Add TTL policies
   - Cache frequent agent lookups

### Monitoring

**Key Metrics to Track:**
- Queue wait time (how long users wait to be processed)
- Active transcription count (should stay ≤ MAX_CONCURRENT_SPEAKERS)
- Database query latency
- Redis cache hit rate
- Agent webhook response time

**Recommended Tools:**
- Prometheus + Grafana for metrics
- Discord bot `/stats` command
- PostgreSQL pg_stat_statements
- Redis INFO command

---

## Troubleshooting

### Common Issues

**Issue: Bot not responding to voice**
```bash
# Check processing workers started
docker compose logs voxbridge-api | grep "Started.*workers"

# Check queue size
# Should show queue additions when users speak
docker compose logs voxbridge-api | grep "Queued"
```

**Issue: Database connection failed**
```bash
# Check PostgreSQL is healthy
docker compose ps postgres

# Test connection manually
docker compose exec postgres psql -U voxbridge -c "SELECT 1"

# Check DATABASE_URL is correct
docker compose exec voxbridge-api env | grep DATABASE_URL
```

**Issue: Redis not caching**
```bash
# Check Redis is healthy
docker compose ps redis

# Test Redis manually
docker compose exec redis redis-cli ping

# Check cache operations
docker compose logs voxbridge-api | grep "Redis"
```

**Issue: Slash commands not appearing**
```bash
# Check bot has applications.commands scope
# Check command sync succeeded
docker compose logs voxbridge-api | grep "Synced.*command"

# Force re-sync (restart bot)
docker compose restart voxbridge-api
```

**Issue: Agents not routing correctly**
```bash
# Check agent config loaded
docker compose logs voxbridge-api | grep "agent"

# Verify agents in database
docker compose exec postgres psql -U voxbridge -c "SELECT * FROM agent_config"

# Check routing strategy
docker compose exec voxbridge-api env | grep ROUTING_STRATEGY
```

---

## Conclusion

This implementation plan transforms VoxBridge from a single-speaker, single-agent system into a robust multi-agent platform capable of:

✅ **Concurrent Processing** - Multiple users can speak simultaneously
✅ **Agent Routing** - Transcripts route to appropriate n8n agents
✅ **Session Management** - Conversation context preserved across turns
✅ **User Control** - Discord slash commands for agent selection
✅ **Scalability** - Queue-based architecture with PostgreSQL + Redis

**Total Development Time:** 8-12 days
**Infrastructure Additions:** PostgreSQL, Redis
**New Dependencies:** asyncpg, redis
**Backward Compatibility:** Migration guide provided

Ready to implement! 🚀
