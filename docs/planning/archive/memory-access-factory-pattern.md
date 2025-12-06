# Memory Access Fix: Factory Pattern Implementation Plan

> ⚠️ **ARCHIVED**: This fix has been implemented and merged
>
> **Archived**: 2025-12-05
> **Reason**: Branch merged, fix complete - see `docs/planning/memory-system-enhancements.md`

---

**Branch**: ~~`feature/memory-access-factory-pattern`~~ (deleted, merged to `feature/memory-system`)
**Created**: November 25, 2025
**Status**: ~~🔧 In Progress~~ **✅ COMPLETE**
**Priority**: 🔴 Critical (blocks agent memory access)

---

## Executive Summary

### Problem

Agents cannot access user memories during conversations due to an `asyncio.run()` event loop conflict in `ConversationService.__init__()`. While memory retrieval logic is **fully implemented and correct**, MemoryService initialization fails silently for all WebRTC and Discord plugin instances.

### Root Cause

**Location**: `src/services/conversation_service.py:145`

```python
# ❌ WRONG: asyncio.run() called inside running event loop
db_embedding_config = asyncio.run(get_global_embedding_config())
self._memory_service = MemoryService(db_embedding_config=db_embedding_config)
```

**Error**: `asyncio.run() cannot be called from a running event loop`

### Impact

- **WebRTC voice chat**: 0% memory access (all instances fail)
- **Discord plugin**: 0% memory access (instance creation fails)
- **Module-level instance** (server.py:456): 100% memory access (but not used by voice handlers)

### Solution

Implement **async factory pattern** to properly initialize services within running event loop, add **comprehensive logging** following established emoji patterns, and create **comprehensive test coverage** (unit + integration + E2E).

---

## Background & Investigation

### What Works

✅ **Memory Retrieval Logic** - Fully implemented and correct:
- `ConversationService.get_conversation_context()` retrieves memories
- `MemoryService.get_user_memory_context()` searches vector database
- Memories are injected as system messages with `<user_memories>` XML tags
- Scope resolution (global vs agent-specific) works correctly

✅ **Configuration** - All settings are correct:
- Database has 4 facts for test user
- `memory_extraction_enabled=true`
- Agent memory_scope set appropriately
- Admin policy allows agent-specific memory

✅ **Test Coverage** - Existing tests prove code is correct:
- `test_get_memory_context_success` verifies XML formatting
- `test_get_memory_context_no_results` verifies graceful degradation
- `test_get_memory_context_error_handling` verifies error handling

### What Fails

❌ **Service Initialization** - Event loop conflict:

```log
⚠️ MemoryService initialization failed, memory features disabled:
asyncio.run() cannot be called from a running event loop

RuntimeWarning: coroutine 'get_global_embedding_config' was never awaited
```

**When it happens**:
1. **WebRTC handler** creates `ConversationService()` during WebSocket connection (webrtc_handler.py:77)
2. **Discord plugin** creates `ConversationService()` during plugin init (discord_plugin.py:447)
3. Both occur **inside running event loop** → asyncio.run() fails

**Why module-level instance works**:
- Created at import time (server.py:456)
- Event loop not started yet
- asyncio.run() creates new loop successfully
- But this instance isn't used by voice handlers

---

## Detailed Design

### Phase 1: Factory Pattern for Service Initialization

#### 1.1 Create Async Factory Functions

**New File**: `src/services/factory.py` (~150 lines)

```python
"""
Async factory functions for service initialization.

Replaces direct __init__() calls to properly handle async initialization
within running event loops.
"""

import logging
from typing import Optional

from src.services.conversation_service import ConversationService
from src.services.stt_service import STTService
from src.services.llm_service import LLMService
from src.services.tts_service import TTSService
from src.services.memory_service import MemoryService
from src.config.embedding import get_global_embedding_config

logger = logging.getLogger(__name__)


async def create_conversation_service() -> ConversationService:
    """
    Create ConversationService with properly initialized MemoryService.

    Returns:
        ConversationService instance with memory access

    Raises:
        Exception: If critical initialization fails
    """
    logger.info("🏭 Creating ConversationService via factory...")

    # Initialize MemoryService with async database config
    memory_service: Optional[MemoryService] = None
    try:
        logger.debug("🧠 Fetching embedding configuration from database...")
        db_embedding_config = await get_global_embedding_config()

        logger.info(f"🧠 Initializing MemoryService with model: {db_embedding_config.get('model_name', 'unknown')}")
        memory_service = MemoryService(db_embedding_config=db_embedding_config)
        logger.info("✅ MemoryService initialized successfully (ready for retrieval)")

    except Exception as e:
        logger.warning(f"⚠️ MemoryService initialization failed: {e}")
        logger.warning("🧠 Continuing without memory features (conversations will work, but no fact retrieval)")
        memory_service = None

    # Create ConversationService with initialized MemoryService
    service = ConversationService(memory_service=memory_service)
    logger.info(f"✅ ConversationService created (memory_enabled={memory_service is not None})")

    return service


async def create_stt_service() -> STTService:
    """
    Create STTService with async initialization.

    Returns:
        STTService instance
    """
    logger.info("🏭 Creating STTService via factory...")
    service = STTService()
    logger.info("✅ STTService created")
    return service


async def create_llm_service() -> LLMService:
    """
    Create LLMService with async initialization.

    Returns:
        LLMService instance
    """
    logger.info("🏭 Creating LLMService via factory...")
    service = LLMService()
    logger.info("✅ LLMService created")
    return service


async def create_tts_service() -> TTSService:
    """
    Create TTSService with async initialization.

    Returns:
        TTSService instance
    """
    logger.info("🏭 Creating TTSService via factory...")
    service = TTSService()
    logger.info("✅ TTSService created")
    return service
```

**Key Features**:
- ✅ Async/await instead of asyncio.run()
- ✅ Graceful degradation (service works without memory)
- ✅ Comprehensive logging with emoji prefixes
- ✅ Proper exception handling
- ✅ Type hints for IDE support

#### 1.2 Refactor ConversationService

**File**: `src/services/conversation_service.py`

**Changes**:

```python
# Before (lines 140-149)
try:
    db_embedding_config = asyncio.run(get_global_embedding_config())  # ❌ FAILS
    self._memory_service = MemoryService(db_embedding_config=db_embedding_config)
    logger.info("🧠 MemoryService integrated with ConversationService")
except Exception as e:
    logger.warning(f"⚠️ MemoryService initialization failed, memory features disabled: {e}")
    self._memory_service = None

# After (lines 140-145)
# Accept optional MemoryService from factory
self._memory_service = memory_service  # ✅ Set directly, no async call
if self._memory_service:
    logger.debug("🧠 MemoryService injected into ConversationService")
else:
    logger.debug("🧠 ConversationService created without MemoryService")
```

**Signature Changes**:

```python
def __init__(
    self,
    session_ttl_seconds: int = 900,
    memory_service: Optional[MemoryService] = None  # ✅ NEW: Accept from factory
):
```

#### 1.3 Update Service Consumers

**File**: `src/voice/webrtc_handler.py:77`

```python
# Before
self.conversation_service = ConversationService()  # ❌ FAILS

# After
self.conversation_service = await create_conversation_service()  # ✅ WORKS
```

**File**: `src/plugins/discord_plugin.py:447`

```python
# Before
self.conversation_service = ConversationService()  # ❌ FAILS

# After
self.conversation_service = await create_conversation_service()  # ✅ WORKS
```

**File**: `src/api/server.py:456` (startup hook)

```python
# Before
conversation_service = ConversationService()  # Works but sync

# After (in async startup function)
conversation_service = await create_conversation_service()  # ✅ Proper async
```

---

### Phase 2: Detailed Memory Logging

Following established VoxBridge logging patterns:
- **Emoji prefixes** for log filtering (🧠 memory, 🏭 factory, ✅ success, ❌ error)
- **Structured messages** with key=value pairs
- **Log levels**: DEBUG for trace, INFO for lifecycle, WARNING for degradation, ERROR for failures

#### 2.1 Memory Retrieval Lifecycle Logs

**File**: `src/services/conversation_service.py` (lines 322-342)

**Add logging**:

```python
# Before retrieval (DEBUG)
logger.debug(
    f"🧠 Retrieving memories: "
    f"user_id={cached.session.user_id[:12]}..., "
    f"agent_id={cached.agent.id[:8]}..., "
    f"query='{last_user_msg.content[:50]}...'"
)

# After retrieval success (INFO)
fact_count = memory_context.count("\n-")  # Count facts in XML
avg_relevance = 0.85  # Extract from context if available
logger.info(
    f"🧠 Memory retrieval SUCCESS: "
    f"facts={fact_count}, "
    f"avg_relevance={avg_relevance:.2f}, "
    f"context_chars={len(memory_context)}"
)

# Context injection (DEBUG)
logger.debug(f"🧠 Injected memory context into system messages ({len(memory_context)} chars)")

# Retrieval failure (WARNING)
logger.warning(f"❌ Memory retrieval FAILED: {str(e)[:100]}")
```

#### 2.2 Memory Service Initialization Logs

**File**: `src/services/factory.py`

Already included in factory functions above:

```python
logger.info(f"🧠 Initializing MemoryService with model: {model_name}")
logger.info("✅ MemoryService initialized successfully (ready for retrieval)")
logger.error(f"❌ MemoryService initialization failed: {error}")
```

#### 2.3 Scope Resolution Logs

**File**: `src/services/memory_service.py` (lines 92-163)

**Add logging**:

```python
# Start of resolution (DEBUG)
logger.debug(
    f"🧠 Resolving memory scope: "
    f"user_id={user_id[:12]}..., "
    f"agent_id={agent_id[:8] if agent_id else 'none'}..., "
    f"agent_default={agent.memory_scope}"
)

# Admin policy check (DEBUG)
logger.debug(f"🧠 Admin policy: allow_agent_specific={admin_allows}")

# User preference check (DEBUG)
if user_pref:
    logger.debug(
        f"🧠 User preference found: "
        f"allow_agent_specific={user_pref.allow_agent_specific_memory}"
    )

# Final resolution (INFO)
logger.info(
    f"🧠 Memory scope RESOLVED: "
    f"scope={final_scope}, "
    f"source={source}, "
    f"namespace={mem_user_id[:20]}..."
)
```

#### 2.4 LLM Prompt Construction Logs

**File**: `src/services/llm_service.py`

**Add logging** when building prompts:

```python
# Count memory messages in prompt
memory_msg_count = sum(1 for m in messages if "<user_memories>" in m.content)
memory_char_count = sum(len(m.content) for m in messages if "<user_memories>" in m.content)

if memory_msg_count > 0:
    logger.debug(
        f"🧠 LLM prompt includes memory: "
        f"messages={memory_msg_count}, "
        f"chars={memory_char_count}"
    )
```

---

### Phase 3: Comprehensive Testing

#### 3.1 Unit Tests for Memory Injection

**New File**: `tests/unit/services/test_conversation_service_memory.py` (~400 lines)

**Test Cases**:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.conversation_service import ConversationService
from src.services.memory_service import MemoryService
from src.services.factory import create_conversation_service


class TestMemoryInjection:
    """Unit tests for memory injection in conversation context."""

    @pytest.mark.asyncio
    async def test_memory_injection_when_service_available(self):
        """Verify memories appear in context when MemoryService exists."""
        # Arrange
        mock_memory_service = AsyncMock(spec=MemoryService)
        mock_memory_service.get_user_memory_context.return_value = (
            "<user_memories>\n"
            "- User's favorite flower is a water lily (relevance: 0.90)\n"
            "</user_memories>"
        )

        service = ConversationService(memory_service=mock_memory_service)

        # Act
        context = await service.get_conversation_context(
            session_id="test-session-123",
            user_id="user-123",
            agent_id="agent-456"
        )

        # Assert
        assert any("<user_memories>" in msg.content for msg in context.messages)
        assert any("water lily" in msg.content for msg in context.messages)
        mock_memory_service.get_user_memory_context.assert_called_once()


    @pytest.mark.asyncio
    async def test_memory_injection_skipped_when_service_none(self):
        """Verify graceful degradation when MemoryService is None."""
        # Arrange
        service = ConversationService(memory_service=None)

        # Act
        context = await service.get_conversation_context(
            session_id="test-session-123",
            user_id="user-123",
            agent_id="agent-456"
        )

        # Assert
        assert not any("<user_memories>" in msg.content for msg in context.messages)
        # Conversation should still work
        assert len(context.messages) > 0


    @pytest.mark.asyncio
    async def test_memory_injection_error_handling(self):
        """Verify errors don't break conversation flow."""
        # Arrange
        mock_memory_service = AsyncMock(spec=MemoryService)
        mock_memory_service.get_user_memory_context.side_effect = Exception("DB connection failed")

        service = ConversationService(memory_service=mock_memory_service)

        # Act & Assert (should not raise)
        context = await service.get_conversation_context(
            session_id="test-session-123",
            user_id="user-123",
            agent_id="agent-456"
        )

        # Conversation continues without memories
        assert not any("<user_memories>" in msg.content for msg in context.messages)


    @pytest.mark.asyncio
    async def test_memory_context_formatting(self):
        """Verify XML tags and structure are correct."""
        # Arrange
        mock_memory_service = AsyncMock(spec=MemoryService)
        mock_memory_service.get_user_memory_context.return_value = (
            "<user_memories>\n"
            "- fact 1 (relevance: 0.95)\n"
            "- fact 2 (relevance: 0.82)\n"
            "</user_memories>"
        )

        service = ConversationService(memory_service=mock_memory_service)

        # Act
        context = await service.get_conversation_context(
            session_id="test-session-123",
            user_id="user-123",
            agent_id="agent-456"
        )

        # Assert
        memory_msg = next(m for m in context.messages if "<user_memories>" in m.content)
        assert memory_msg.role == "system"
        assert "relevance:" in memory_msg.content
        assert memory_msg.content.startswith("<user_memories>")
        assert memory_msg.content.endswith("</user_memories>")


    @pytest.mark.asyncio
    async def test_factory_initialization_success(self):
        """Verify factory creates service with MemoryService."""
        # Arrange
        with patch('src.services.factory.get_global_embedding_config') as mock_config:
            mock_config.return_value = {"model_name": "test-model"}

            # Act
            service = await create_conversation_service()

            # Assert
            assert service._memory_service is not None


    @pytest.mark.asyncio
    async def test_factory_initialization_db_failure(self):
        """Verify factory handles DB errors gracefully."""
        # Arrange
        with patch('src.services.factory.get_global_embedding_config') as mock_config:
            mock_config.side_effect = Exception("DB unreachable")

            # Act (should not raise)
            service = await create_conversation_service()

            # Assert
            assert service._memory_service is None
```

#### 3.2 Integration Tests for Full Flow

**New File**: `tests/integration/test_memory_retrieval_flow.py` (~350 lines)

**Test Cases**:

```python
import pytest
from src.services.factory import create_conversation_service
from src.services.memory_service import MemoryService
from src.database.models import UserFact, Agent, Session, User


@pytest.mark.integration
class TestMemoryRetrievalFlow:
    """Integration tests for end-to-end memory retrieval."""

    @pytest.mark.asyncio
    async def test_create_fact_then_retrieve_in_conversation(self, db_session):
        """
        E2E test: Create fact → Trigger conversation → Verify fact in context.
        """
        # Arrange: Create test data
        user = User(user_id="test-user-123", memory_extraction_enabled=True)
        agent = Agent(name="Test Agent", memory_scope="global")
        db_session.add_all([user, agent])
        await db_session.commit()

        # Create fact
        memory_service = MemoryService()
        await memory_service.create_user_fact(
            user_id=user.id,
            agent_id=agent.id,
            scope="global",
            fact_key="favorite_color",
            fact_value="blue",
            fact_text="User's favorite color is blue"
        )

        # Act: Get conversation context
        conversation_service = await create_conversation_service()
        context = await conversation_service.get_conversation_context(
            session_id="test-session",
            user_id=user.id,
            agent_id=agent.id
        )

        # Assert: Fact appears in context
        memory_msg = next((m for m in context.messages if "<user_memories>" in m.content), None)
        assert memory_msg is not None
        assert "favorite color is blue" in memory_msg.content


    @pytest.mark.asyncio
    async def test_global_vs_agent_scope_filtering(self, db_session):
        """Verify global facts appear for all agents, agent facts don't."""
        # Arrange: Create 2 agents, 1 global fact, 1 agent-specific fact
        agent1 = Agent(name="Agent 1", memory_scope="global")
        agent2 = Agent(name="Agent 2", memory_scope="agent")
        user = User(user_id="test-user", memory_extraction_enabled=True)
        db_session.add_all([agent1, agent2, user])
        await db_session.commit()

        # Global fact (agent_id=NULL)
        global_fact = UserFact(
            user_id=user.id,
            agent_id=None,
            fact_key="global_pref",
            fact_value="coffee",
            fact_text="User prefers coffee"
        )

        # Agent-specific fact
        agent_fact = UserFact(
            user_id=user.id,
            agent_id=agent2.id,
            fact_key="agent_pref",
            fact_value="tea",
            fact_text="User prefers tea with Agent 2"
        )
        db_session.add_all([global_fact, agent_fact])
        await db_session.commit()

        # Act: Get context for both agents
        service = await create_conversation_service()

        context1 = await service.get_conversation_context(
            session_id="session1",
            user_id=user.id,
            agent_id=agent1.id
        )

        context2 = await service.get_conversation_context(
            session_id="session2",
            user_id=user.id,
            agent_id=agent2.id
        )

        # Assert: Agent 1 sees only global fact
        memory1 = next((m.content for m in context1.messages if "<user_memories>" in m.content), "")
        assert "coffee" in memory1
        assert "tea" not in memory1

        # Assert: Agent 2 sees both facts
        memory2 = next((m.content for m in context2.messages if "<user_memories>" in m.content), "")
        assert "coffee" in memory2
        assert "tea" in memory2


    @pytest.mark.asyncio
    async def test_memory_relevance_ranking(self, db_session):
        """Verify most relevant facts appear first."""
        # Arrange: Create facts with different importance scores
        # ... (implementation similar to above)

        # Act: Query with limit=3

        # Assert: Top 3 facts are returned in relevance order


    @pytest.mark.asyncio
    async def test_no_memories_graceful_degradation(self, db_session):
        """Verify conversation works even with no facts."""
        # Arrange: Empty database
        user = User(user_id="test-user", memory_extraction_enabled=False)
        agent = Agent(name="Agent", memory_scope="global")
        db_session.add_all([user, agent])
        await db_session.commit()

        # Act
        service = await create_conversation_service()
        context = await service.get_conversation_context(
            session_id="session",
            user_id=user.id,
            agent_id=agent.id
        )

        # Assert: No memory messages, but conversation works
        assert not any("<user_memories>" in m.content for m in context.messages)
        assert len(context.messages) > 0  # System prompt at minimum


    @pytest.mark.asyncio
    async def test_admin_policy_blocks_agent_memory(self, db_session):
        """Verify admin policy forces global scope."""
        # Arrange: Set admin policy to disallow agent memory
        # ... (implementation requires admin settings API)

        # Act: Create agent-specific fact

        # Assert: Fact is forced to global scope
```

#### 3.3 Mock LLM Capture Tests

**New File**: `tests/integration/test_llm_prompt_capture.py` (~300 lines)

**Test Cases**:

```python
import pytest
from unittest.mock import AsyncMock
from src.llm.base import LLMProvider
from src.llm.types import LLMMessage, LLMRequest, LLMResponse


class CapturingLLMProvider(LLMProvider):
    """Mock LLM provider that captures prompts for testing."""

    def __init__(self):
        self.captured_prompts: list[list[LLMMessage]] = []

    async def generate_stream(self, request: LLMRequest):
        """Capture prompt and return mock response."""
        self.captured_prompts.append(request.messages)

        # Mock streaming response
        yield {
            "role": "assistant",
            "content": "Mock response based on memories",
            "finish_reason": "stop"
        }

    async def health_check(self) -> bool:
        return True


@pytest.mark.integration
class TestLLMPromptCapture:
    """Tests that capture and verify exact LLM prompts."""

    @pytest.mark.asyncio
    async def test_capture_prompt_with_memories(self, db_session):
        """Capture exact prompt sent to LLM and verify memory XML."""
        # Arrange: Create fact and mock LLM
        capturing_provider = CapturingLLMProvider()

        # ... create test data (user, agent, fact)

        # Act: Generate response (triggers prompt construction)
        service = await create_conversation_service()
        await service.generate_response(
            session_id="session",
            user_message="What's my favorite color?",
            llm_provider=capturing_provider
        )

        # Assert: Prompt contains memory XML
        assert len(capturing_provider.captured_prompts) == 1
        messages = capturing_provider.captured_prompts[0]

        memory_msg = next((m for m in messages if "<user_memories>" in m.content), None)
        assert memory_msg is not None
        assert memory_msg.role == "system"
        assert "favorite color is blue" in memory_msg.content


    @pytest.mark.asyncio
    async def test_memory_appears_before_conversation(self):
        """Verify message order: system → memories → conversation."""
        # Arrange
        capturing_provider = CapturingLLMProvider()

        # Act: Generate response
        # ...

        # Assert: Message order
        messages = capturing_provider.captured_prompts[0]
        system_idx = next(i for i, m in enumerate(messages) if m.role == "system" and "You are" in m.content)
        memory_idx = next(i for i, m in enumerate(messages) if "<user_memories>" in m.content)
        user_idx = next(i for i, m in enumerate(messages) if m.role == "user")

        assert system_idx < memory_idx < user_idx


    @pytest.mark.asyncio
    async def test_memory_xml_format_in_prompt(self):
        """Assert exact XML structure in prompt."""
        # Arrange
        capturing_provider = CapturingLLMProvider()

        # Act
        # ...

        # Assert: XML structure
        messages = capturing_provider.captured_prompts[0]
        memory_content = next(m.content for m in messages if "<user_memories>" in m.content)

        assert memory_content.startswith("<user_memories>")
        assert memory_content.endswith("</user_memories>")
        assert "relevance:" in memory_content


    @pytest.mark.asyncio
    async def test_relevance_scores_in_prompt(self):
        """Verify relevance scores are included."""
        # ... similar to above

        # Assert
        assert "relevance: 0." in memory_content  # Decimal score present


    @pytest.mark.asyncio
    async def test_multiple_facts_formatting(self):
        """Verify multi-fact XML structure."""
        # Arrange: Create 3 facts
        # ...

        # Assert: All 3 facts in XML
        memory_content = next(m.content for m in messages if "<user_memories>" in m.content)
        fact_lines = [line for line in memory_content.split("\n") if line.startswith("- ")]
        assert len(fact_lines) == 3
```

---

### Phase 4: Verification & Validation

#### 4.1 Manual Testing Checklist

- [ ] Create fact via Memory UI (http://localhost:4903/memory)
- [ ] Verify fact appears in database
- [ ] Start WebRTC voice chat (http://localhost:4903/)
- [ ] Ask question related to fact ("What's my favorite flower?")
- [ ] Verify agent response uses the fact
- [ ] Check logs for `🧠` emoji entries showing retrieval
- [ ] Repeat test with Discord plugin
- [ ] Test with global scope agent
- [ ] Test with agent-specific scope agent
- [ ] Verify admin policy override works

#### 4.2 Log Monitoring Commands

```bash
# Check MemoryService initialization
docker logs voxbridge-api 2>&1 | grep "🧠 MemoryService"

# Check memory retrieval
docker logs voxbridge-api 2>&1 | grep "🧠 Memory retrieval"

# Check factory creation
docker logs voxbridge-api 2>&1 | grep "🏭 Creating"

# Check initialization errors
docker logs voxbridge-api 2>&1 | grep "asyncio.run()"

# Full memory log stream
docker logs voxbridge-api --follow --tail 100 | grep -E "(🧠|🏭|✅|❌)"
```

#### 4.3 Expected Log Sequence

**Successful flow**:

```
🏭 Creating ConversationService via factory...
🧠 Fetching embedding configuration from database...
🧠 Initializing MemoryService with model: BAAI/bge-large-en-v1.5
✅ MemoryService initialized successfully (ready for retrieval)
✅ ConversationService created (memory_enabled=True)

[User asks question]

🧠 Retrieving memories: user_id=discord:12345..., agent_id=abc-123..., query='What's my favorite...'
🧠 Resolving memory scope: user_id=discord:12345..., agent_id=abc-123..., agent_default=global
🧠 Admin policy: allow_agent_specific=True
🧠 Memory scope RESOLVED: scope=global, source=agent, namespace=discord:12345...
🧠 Memory retrieval SUCCESS: facts=3, avg_relevance=0.87, context_chars=245
🧠 Injected memory context into system messages (245 chars)
🧠 LLM prompt includes memory: messages=1, chars=245
```

#### 4.4 Test Coverage Goals

Run tests and verify coverage:

```bash
# Run all tests with coverage
./test.sh tests/unit tests/integration --cov=. --cov-report=term --cov-report=html

# Expected results:
# - ConversationService: 95%+ coverage (up from ~90%)
# - Factory functions: 100% coverage
# - Memory integration: 100% coverage
# - All 15+ new tests: PASSING
```

**Coverage Targets**:
- `src/services/factory.py`: 100%
- `src/services/conversation_service.py`: 95%+
- `src/services/memory_service.py`: 90%+ (existing, maintain)
- Overall project: Maintain 90%+ coverage

---

## Implementation Order

### Step 1: Factory Pattern (Core Fix)

1. Create `src/services/factory.py` with async factory functions
2. Refactor `ConversationService.__init__()` to accept optional `memory_service`
3. Update `webrtc_handler.py:77` to use `await create_conversation_service()`
4. Update `discord_plugin.py:447` to use `await create_conversation_service()`
5. Update `server.py:456` to use factory in startup hook

**Validation**: Service instances should have `_memory_service` initialized (check logs for "✅ MemoryService initialized")

### Step 2: Logging (Parallel with Step 1)

1. Add memory retrieval logs to `conversation_service.py`
2. Add factory logs to `factory.py` (already included in factories)
3. Add scope resolution logs to `memory_service.py`
4. Add LLM prompt logs to `llm_service.py`

**Validation**: Run conversation, check logs for `🧠` emoji entries

### Step 3: Unit Tests

1. Write `test_conversation_service_memory.py` (6 test functions)
2. Run tests: `./test.sh tests/unit/services/test_conversation_service_memory.py -v`
3. Verify all tests pass

**Validation**: All 6 unit tests passing

### Step 4: Integration Tests

1. Write `test_memory_retrieval_flow.py` (5 test functions)
2. Write `test_llm_prompt_capture.py` (5 test functions)
3. Run integration tests: `./test.sh tests/integration -v`
4. Verify all tests pass

**Validation**: All 10 integration tests passing

### Step 5: Manual Testing

1. Follow manual testing checklist (Section 4.1)
2. Monitor logs for expected sequence (Section 4.3)
3. Verify agent uses facts in responses

**Validation**: Agent correctly uses user facts in conversation responses

---

## Files Modified

### New Files

| File | Lines | Purpose |
|------|-------|---------|
| `src/services/factory.py` | ~150 | Async factory functions for service initialization |
| `tests/unit/services/test_conversation_service_memory.py` | ~400 | Unit tests for memory injection |
| `tests/integration/test_memory_retrieval_flow.py` | ~350 | Integration tests for E2E memory flow |
| `tests/integration/test_llm_prompt_capture.py` | ~300 | Mock LLM tests for prompt verification |

**Total new**: ~1,200 lines

### Modified Files

| File | Changes | Purpose |
|------|---------|---------|
| `src/services/conversation_service.py` | +30 logging, -5 asyncio.run | Remove event loop conflict, add logging |
| `src/services/memory_service.py` | +15 logging | Add scope resolution logging |
| `src/services/llm_service.py` | +10 logging | Add prompt construction logging |
| `src/voice/webrtc_handler.py` | Line 77 change | Use factory instead of direct init |
| `src/plugins/discord_plugin.py` | Line 447 change | Use factory instead of direct init |
| `src/api/server.py` | Update startup hook | Use factory in async startup |

**Total modified**: ~60 lines changed across 6 files

---

## Success Criteria

### Functional Requirements

- ✅ All WebRTC voice chat sessions have memory access
- ✅ All Discord plugin sessions have memory access
- ✅ No `asyncio.run()` event loop conflicts in logs
- ✅ Memory logs appear for every conversation with facts
- ✅ Agent responses correctly use user facts

### Technical Requirements

- ✅ All 15+ new tests passing (6 unit + 10 integration)
- ✅ Test coverage ≥95% for ConversationService
- ✅ Test coverage ≥100% for factory.py
- ✅ Overall project coverage maintained at 90%+
- ✅ No regressions in existing tests

### Quality Requirements

- ✅ Logging follows established emoji patterns
- ✅ Code follows existing style conventions
- ✅ Type hints on all public functions
- ✅ Docstrings on all factory functions
- ✅ Error handling with graceful degradation

---

## Rollback Plan

If critical issues arise during deployment:

### Feature Flag Rollback

1. Add environment variable: `USE_FACTORY_PATTERN=true` (default)
2. Keep old `__init__()` logic as `_init_sync()` fallback method
3. If flag=false, use old synchronous initialization (without memory)
4. Allows instant rollback via environment variable change

### Implementation

```python
# In ConversationService.__init__()
if os.getenv('USE_FACTORY_PATTERN', 'true').lower() == 'false':
    # Fallback to old sync initialization (without memory)
    self._memory_service = None
    logger.warning("🔄 Using legacy initialization (factory pattern disabled)")
else:
    # New factory-based initialization
    self._memory_service = memory_service
```

### Rollback Steps

```bash
# 1. Set environment variable
echo "USE_FACTORY_PATTERN=false" >> .env

# 2. Restart service
docker compose restart voxbridge-api

# 3. Verify service is running (without memory)
curl http://localhost:4900/health

# 4. Monitor logs for warnings
docker logs voxbridge-api --tail 100 | grep "legacy initialization"
```

**Note**: Rollback disables memory features but maintains service availability.

---

## Risk Assessment

### Low Risk

✅ **Graceful Degradation**: Service works without MemoryService (existing behavior)
✅ **Comprehensive Tests**: 15+ tests covering all scenarios
✅ **Rollback Available**: Feature flag allows instant rollback
✅ **No Breaking Changes**: API contracts unchanged

### Medium Risk

⚠️ **Async Initialization**: Requires await in multiple places (potential for missed conversions)
⚠️ **Log Volume**: Detailed logging may increase log noise (mitigated by DEBUG level)

### Mitigation Strategies

1. **Missed Awaits**: Run full test suite (unit + integration) before merging
2. **Log Noise**: Use DEBUG level for detailed logs, INFO for lifecycle only
3. **Performance**: Factory initialization is cached (no per-request overhead)

---

## Open Questions

None (all requirements clarified during planning)

---

## Documentation Updates

After implementation, update:

1. **CLAUDE.md**: Add factory pattern to "Key Files" section
2. **AGENTS.md**: Update service initialization patterns
3. **README.md**: Update architecture diagram to show factory
4. **tests/README.md**: Document new test patterns

---

## Related Planning Documents

- [Memory System Implementation Plan](./memory-system-implementation-plan.md) - Phase 1-7 overview
- [Per-Agent Memory Preferences](./per-agent-memory-preferences.md) - Phase 6 interactive controls
- [Open WebUI Comparison](../architecture/open-webui-comparison.md) - Memory architecture validation
- [Memory System FAQ](../faq/memory-system-faq.md) - 16 Q&A covering all aspects

---

## Changelog

- **2025-11-25**: Initial planning document created
- **2025-11-25**: Branch `feature/memory-access-factory-pattern` created

---

## Appendix A: Example Factory Usage

```python
# Before (FAILS in running event loop)
service = ConversationService()

# After (WORKS in running event loop)
service = await create_conversation_service()
```

## Appendix B: Example Log Output

```
2025-11-25 23:45:12 - src.services.factory - INFO - 🏭 Creating ConversationService via factory...
2025-11-25 23:45:12 - src.services.factory - DEBUG - 🧠 Fetching embedding configuration from database...
2025-11-25 23:45:12 - src.services.factory - INFO - 🧠 Initializing MemoryService with model: BAAI/bge-large-en-v1.5
2025-11-25 23:45:13 - src.services.factory - INFO - ✅ MemoryService initialized successfully (ready for retrieval)
2025-11-25 23:45:13 - src.services.factory - INFO - ✅ ConversationService created (memory_enabled=True)
2025-11-25 23:45:20 - src.services.conversation_service - DEBUG - 🧠 Retrieving memories: user_id=discord:12345..., agent_id=abc-123...
2025-11-25 23:45:20 - src.services.memory_service - DEBUG - 🧠 Resolving memory scope: user_id=discord:12345..., agent_id=abc-123...
2025-11-25 23:45:20 - src.services.memory_service - INFO - 🧠 Memory scope RESOLVED: scope=global, source=agent
2025-11-25 23:45:21 - src.services.conversation_service - INFO - 🧠 Memory retrieval SUCCESS: facts=3, avg_relevance=0.87
2025-11-25 23:45:21 - src.services.conversation_service - DEBUG - 🧠 Injected memory context into system messages (245 chars)
2025-11-25 23:45:21 - src.services.llm_service - DEBUG - 🧠 LLM prompt includes memory: messages=1, chars=245
```

## Appendix C: Test Execution Examples

```bash
# Run specific test file
./test.sh tests/unit/services/test_conversation_service_memory.py -v

# Run all memory-related tests
./test.sh tests/unit tests/integration -k memory -v

# Run with coverage report
./test.sh tests/unit tests/integration --cov=src/services --cov-report=term-missing

# Run integration tests only
./test.sh tests/integration -v --tb=short
```
