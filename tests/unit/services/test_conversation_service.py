"""
Unit tests for ConversationService

Tests session management, context caching, message storage, TTL expiration,
concurrency control, and database integration.
"""
import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import UUID, uuid4

from src.services.conversation_service import (
    ConversationService,
    Message,
    CachedContext,
    CONVERSATION_CACHE_TTL_MINUTES,
    MAX_CONTEXT_MESSAGES,
)
from src.database.models import Agent, Session, Conversation


# ============================================================
# Initialization Tests
# ============================================================

@pytest.mark.asyncio
async def test_init_with_defaults():
    """Test initialization with default parameters"""
    service = ConversationService()

    assert service._cache_ttl == timedelta(minutes=CONVERSATION_CACHE_TTL_MINUTES)
    assert service._max_context == MAX_CONTEXT_MESSAGES
    assert len(service._cache) == 0
    assert service._running is False
    assert service._cleanup_task is None


@pytest.mark.asyncio
async def test_init_with_custom_ttl():
    """Test initialization with custom cache TTL"""
    service = ConversationService(cache_ttl_minutes=30, max_context_messages=50)

    assert service._cache_ttl == timedelta(minutes=30)
    assert service._max_context == 50


@pytest.mark.asyncio
async def test_start_stop_lifecycle():
    """Test service lifecycle (start/stop background tasks)"""
    service = ConversationService()

    # Start service
    await service.start()
    assert service._running is True
    assert service._cleanup_task is not None
    assert not service._cleanup_task.done()

    # Stop service
    await service.stop()
    assert service._running is False
    assert service._cleanup_task.done()


@pytest.mark.asyncio
async def test_start_when_already_running():
    """Test starting service when already running (idempotent)"""
    service = ConversationService()

    await service.start()
    first_task = service._cleanup_task

    # Try starting again
    await service.start()
    assert service._cleanup_task == first_task  # Same task

    await service.stop()


# ============================================================
# Session Management Tests
# ============================================================

@pytest.mark.asyncio
async def test_get_or_create_session_new():
    """Test creating a new session"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    # Mock database operations
    mock_agent = Agent(
        id=UUID(agent_id),
        name="TestAgent",
        system_prompt="You are a helpful assistant",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id="discord_123",
        user_name="TestUser",
        agent_id=UUID(agent_id),
        session_type="webrtc",
        active=True
    )
    mock_session.agent = mock_agent

    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx

        # Mock queries
        mock_db_ctx.execute = AsyncMock()

        # First query: check if session exists (return None)
        # Second query: get agent (return mock_agent)
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # Session not found
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_agent)),  # Agent found
        ]
        mock_db_ctx.execute.side_effect = results
        mock_db_ctx.add = MagicMock()
        mock_db_ctx.commit = AsyncMock()
        mock_db_ctx.refresh = AsyncMock()

        # After refresh, set the agent relationship
        async def refresh_side_effect(session):
            session.agent = mock_agent
        mock_db_ctx.refresh.side_effect = refresh_side_effect

        # Call method
        session = await service.get_or_create_session(
            session_id=session_id,
            user_id="discord_123",
            agent_id=agent_id,
            channel_type="webrtc",
            user_name="TestUser"
        )

        # Verify session was created
        assert mock_db_ctx.add.called
        assert mock_db_ctx.commit.called

        # Verify session is cached
        assert session_id in service._cache


@pytest.mark.asyncio
async def test_get_or_create_session_existing():
    """Test retrieving an existing session"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    mock_agent = Agent(
        id=UUID(agent_id),
        name="TestAgent",
        system_prompt="You are helpful",
        temperature=0.7,
        llm_provider="local",
        llm_model="llama3"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id="discord_123",
        agent_id=UUID(agent_id),
        session_type="webrtc",
        active=True
    )
    mock_session.agent = mock_agent

    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx

        # Mock existing session found
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_session
        mock_db_ctx.execute = AsyncMock(return_value=result)

        # Mock loading messages
        messages_result = MagicMock()
        messages_result.scalars.return_value.all.return_value = []

        # Two executes: one for session, one for messages
        mock_db_ctx.execute = AsyncMock(side_effect=[result, messages_result])

        # Call method
        session = await service.get_or_create_session(
            session_id=session_id,
            user_id="discord_123",
            agent_id=agent_id,
            channel_type="webrtc"
        )

        # Verify session was loaded (not created)
        assert session_id in service._cache


@pytest.mark.asyncio
async def test_get_or_create_session_agent_not_found():
    """Test error when agent not found"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx

        # Mock session not found, agent not found
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # Session not found
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # Agent not found
        ]
        mock_db_ctx.execute = AsyncMock(side_effect=results)

        # Should raise ValueError
        with pytest.raises(ValueError, match="Agent .* not found"):
            await service.get_or_create_session(
                session_id=session_id,
                user_id="discord_123",
                agent_id=agent_id,
                channel_type="webrtc"
            )


# ============================================================
# Context Management Tests
# ============================================================

@pytest.mark.asyncio
async def test_get_conversation_context_empty():
    """Test getting context for session with no messages"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    mock_agent = Agent(
        id=UUID(agent_id),
        name="TestAgent",
        system_prompt="You are a helpful assistant",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id="test_user",
        agent_id=UUID(agent_id),
        session_type="webrtc",
        active=True,
        started_at=datetime.utcnow()
    )

    # Create cached context
    cached = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[],
        last_activity=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    service._cache[session_id] = cached

    # Get context
    context = await service.get_conversation_context(session_id, include_system_prompt=True)

    # Should have only system prompt
    assert len(context) == 1
    assert context[0].role == "system"
    assert context[0].content == "You are a helpful assistant"


@pytest.mark.asyncio
async def test_get_conversation_context_with_messages():
    """Test getting context with conversation history"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    mock_agent = Agent(
        id=UUID(agent_id),
        name="TestAgent",
        system_prompt="System prompt",
        temperature=0.7,
        llm_provider="local",
        llm_model="llama3"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id="test_user",
        agent_id=UUID(agent_id),
        session_type="webrtc",
        active=True,
        started_at=datetime.utcnow()
    )

    # Create mock conversation messages
    conv1 = Conversation(
        session_id=UUID(session_id),
        role="user",
        content="Hello",
        timestamp=datetime.utcnow(),
        audio_duration_ms=1000
    )

    conv2 = Conversation(
        session_id=UUID(session_id),
        role="assistant",
        content="Hi there!",
        timestamp=datetime.utcnow(),
        tts_duration_ms=500
    )

    # Create cached context (messages in DESC order by timestamp)
    cached = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[conv2, conv1],  # Reversed chronological
        last_activity=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    service._cache[session_id] = cached

    # Get context
    context = await service.get_conversation_context(session_id, limit=10, include_system_prompt=True)

    # Should have system + 2 messages (chronological order)
    assert len(context) == 3
    assert context[0].role == "system"
    assert context[1].role == "user"
    assert context[1].content == "Hello"
    assert context[2].role == "assistant"
    assert context[2].content == "Hi there!"


@pytest.mark.asyncio
async def test_get_conversation_context_limit():
    """Test context limiting to N recent messages"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    mock_agent = Agent(
        id=UUID(agent_id),
        name="TestAgent",
        system_prompt=None,  # No system prompt
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id="test_user",
        agent_id=UUID(agent_id),
        session_type="webrtc",
        active=True,
        started_at=datetime.utcnow()
    )

    # Create 5 messages
    messages = []
    for i in range(5):
        conv = Conversation(
            session_id=UUID(session_id),
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}",
            timestamp=datetime.utcnow()
        )
        messages.append(conv)

    # Reverse for DESC order
    messages.reverse()

    cached = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=messages,
        last_activity=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    service._cache[session_id] = cached

    # Get context with limit=2
    context = await service.get_conversation_context(session_id, limit=2, include_system_prompt=False)

    # Should have only 2 most recent messages
    assert len(context) == 2


@pytest.mark.asyncio
async def test_get_conversation_context_without_system_prompt():
    """Test context excluding agent system prompt"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    mock_agent = Agent(
        id=UUID(agent_id),
        name="TestAgent",
        system_prompt="System prompt",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id="test_user",
        agent_id=UUID(agent_id),
        session_type="webrtc",
        active=True,
        started_at=datetime.utcnow()
    )

    cached = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[],
        last_activity=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    service._cache[session_id] = cached

    # Get context without system prompt
    context = await service.get_conversation_context(session_id, include_system_prompt=False)

    # Should have no messages
    assert len(context) == 0


# ============================================================
# Message Management Tests
# ============================================================

@pytest.mark.asyncio
async def test_add_message_user():
    """Test adding user message to conversation"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    mock_agent = Agent(
        id=UUID(agent_id),
        name="TestAgent",
        system_prompt="System",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id="test_user",
        agent_id=UUID(agent_id),
        session_type="webrtc",
        active=True,
        started_at=datetime.utcnow()
    )

    cached = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[],
        last_activity=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    service._cache[session_id] = cached

    # Mock database
    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx

        mock_db_ctx.add = MagicMock()
        mock_db_ctx.commit = AsyncMock()

        mock_conv = Conversation(
            session_id=UUID(session_id),
            role="user",
            content="Hello",
            timestamp=datetime.utcnow()
        )

        async def refresh_side_effect(conv):
            pass
        mock_db_ctx.refresh = AsyncMock(side_effect=refresh_side_effect)

        # Add message
        message = await service.add_message(
            session_id=session_id,
            role="user",
            content="Hello",
            metadata={"audio_duration_ms": 1500}
        )

        # Verify message added
        assert message.role == "user"
        assert message.content == "Hello"
        assert message.metadata["audio_duration_ms"] == 1500

        # Verify database call
        assert mock_db_ctx.add.called
        assert mock_db_ctx.commit.called

        # Verify cache updated
        assert len(cached.messages) == 1


@pytest.mark.asyncio
async def test_add_message_with_metadata():
    """Test adding message with metadata (latency metrics)"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    mock_agent = Agent(
        id=UUID(agent_id),
        name="TestAgent",
        system_prompt="System",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id="test_user",
        agent_id=UUID(agent_id),
        session_type="webrtc",
        active=True,
        started_at=datetime.utcnow()
    )

    cached = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[],
        last_activity=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    service._cache[session_id] = cached

    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx

        mock_db_ctx.add = MagicMock()
        mock_db_ctx.commit = AsyncMock()
        mock_db_ctx.refresh = AsyncMock()

        # Add message with full metadata
        metadata = {
            "audio_duration_ms": 1500,
            "tts_duration_ms": 800,
            "llm_latency_ms": 1200,
            "total_latency_ms": 3500
        }

        message = await service.add_message(
            session_id=session_id,
            role="assistant",
            content="Hello there!",
            metadata=metadata
        )

        # Verify metadata preserved
        assert message.metadata == metadata


# ============================================================
# Cache Tests
# ============================================================

@pytest.mark.asyncio
async def test_cache_hit():
    """Test cache hit for session"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    mock_agent = Agent(
        id=UUID(agent_id),
        name="TestAgent",
        system_prompt="System",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id="test_user",
        agent_id=UUID(agent_id),
        session_type="webrtc",
        active=True,
        started_at=datetime.utcnow()
    )

    # Pre-populate cache
    cached = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[],
        last_activity=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    service._cache[session_id] = cached

    # Get session (should hit cache, not database)
    with patch('src.services.conversation_service.get_db_session') as mock_db:
        session = await service.get_or_create_session(
            session_id=session_id,
            user_id="test_user",
            agent_id=agent_id
        )

        # Should NOT call database
        assert not mock_db.called
        assert session == mock_session


@pytest.mark.asyncio
async def test_cache_ttl_expiration():
    """Test cache entry expires after TTL"""
    service = ConversationService()

    session_id = str(uuid4())

    # Create expired cache entry
    mock_session = Session(
        id=UUID(session_id),
        user_id="test_user",
        agent_id=UUID(str(uuid4())),
        session_type="webrtc",
        active=True,
        started_at=datetime.utcnow()
    )

    cached = CachedContext(
        session=mock_session,
        agent=Agent(
            id=UUID(str(uuid4())),
            name="Test",
            system_prompt="System",
            temperature=0.7,
            llm_provider="openrouter",
            llm_model="gpt-4"
        ),
        messages=[],
        last_activity=datetime.utcnow() - timedelta(hours=1),
        expires_at=datetime.utcnow() - timedelta(minutes=1)  # Expired
    )
    service._cache[session_id] = cached

    # Run cleanup manually
    now = datetime.utcnow()
    expired = []
    for sid, cache_entry in list(service._cache.items()):
        if now > cache_entry.expires_at:
            expired.append(sid)

    for sid in expired:
        del service._cache[sid]

    # Verify cache cleared
    assert session_id not in service._cache


@pytest.mark.asyncio
async def test_cache_cleanup_task():
    """Test background cache cleanup removes expired entries"""
    service = ConversationService()

    # Override cleanup interval for faster testing
    with patch('src.services.conversation_service.CACHE_CLEANUP_INTERVAL_SECONDS', 0.1):
        await service.start()

        # Add expired entry
        session_id = str(uuid4())
        cached = CachedContext(
            session=Session(
                id=UUID(session_id),
                user_id="test",
                agent_id=UUID(str(uuid4())),
                session_type="webrtc",
                active=True,
                started_at=datetime.utcnow()
            ),
            agent=Agent(
                id=UUID(str(uuid4())),
                name="Test",
                system_prompt="System",
                temperature=0.7,
                llm_provider="openrouter",
                llm_model="gpt-4"
            ),
            messages=[],
            last_activity=datetime.utcnow() - timedelta(hours=1),
            expires_at=datetime.utcnow() - timedelta(minutes=1)  # Expired
        )
        service._cache[session_id] = cached

        # Wait for cleanup
        await asyncio.sleep(0.2)

        # Verify cleanup ran
        assert session_id not in service._cache

        await service.stop()


# ============================================================
# Agent Configuration Tests
# ============================================================

@pytest.mark.asyncio
async def test_get_agent_config():
    """Test retrieving agent configuration for session"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    mock_agent = Agent(
        id=UUID(agent_id),
        name="TestAgent",
        system_prompt="You are helpful",
        temperature=0.8,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id="test_user",
        agent_id=UUID(agent_id),
        session_type="webrtc",
        active=True,
        started_at=datetime.utcnow()
    )

    cached = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[],
        last_activity=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    service._cache[session_id] = cached

    # Get agent config
    agent = await service.get_agent_config(session_id)

    assert agent.id == UUID(agent_id)
    assert agent.name == "TestAgent"
    assert agent.temperature == 0.8


# ============================================================
# Concurrency Tests
# ============================================================

@pytest.mark.asyncio
async def test_concurrent_session_access():
    """Test concurrent access to same session (locking)"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    mock_agent = Agent(
        id=UUID(agent_id),
        name="TestAgent",
        system_prompt="System",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id="test_user",
        agent_id=UUID(agent_id),
        session_type="webrtc",
        active=True,
        started_at=datetime.utcnow()
    )

    cached = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[],
        last_activity=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    service._cache[session_id] = cached

    # Mock database for add_message
    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx

        mock_db_ctx.add = MagicMock()
        mock_db_ctx.commit = AsyncMock()
        mock_db_ctx.refresh = AsyncMock()

        # Concurrent operations
        tasks = [
            service.add_message(session_id, "user", f"Message {i}")
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all succeeded (no race conditions)
        assert all(isinstance(r, Message) for r in results)
        assert len(cached.messages) == 5


@pytest.mark.asyncio
async def test_multiple_sessions_concurrent():
    """Test multiple different sessions concurrently"""
    service = ConversationService()

    # Create 3 different sessions
    sessions = []
    for i in range(3):
        session_id = str(uuid4())
        agent_id = str(uuid4())

        mock_agent = Agent(
            id=UUID(agent_id),
            name=f"Agent{i}",
            system_prompt="System",
            temperature=0.7,
            llm_provider="openrouter",
            llm_model="gpt-4"
        )

        mock_session = Session(
            id=UUID(session_id),
            user_id=f"user_{i}",
            agent_id=UUID(agent_id),
            session_type="webrtc",
            active=True,
            started_at=datetime.utcnow()
        )

        cached = CachedContext(
            session=mock_session,
            agent=mock_agent,
            messages=[],
            last_activity=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=15)
        )
        service._cache[session_id] = cached
        sessions.append(session_id)

    # Concurrent context retrieval
    tasks = [
        service.get_conversation_context(sid)
        for sid in sessions
    ]

    results = await asyncio.gather(*tasks)

    # All should succeed
    assert len(results) == 3
    assert all(isinstance(r, list) for r in results)


# ============================================================
# Error Handling Tests
# ============================================================

@pytest.mark.asyncio
async def test_get_conversation_context_graceful_degradation():
    """Test graceful degradation on database errors"""
    service = ConversationService()

    session_id = str(uuid4())

    # No cache entry, so it will try to load from DB
    with patch('src.services.conversation_service.get_db_session') as mock_db:
        # Simulate database error
        mock_db.side_effect = Exception("Database connection failed")

        # Should return empty list (graceful degradation)
        context = await service.get_conversation_context(session_id)

        assert context == []


# ============================================================
# Cleanup Tests
# ============================================================

@pytest.mark.asyncio
async def test_end_session():
    """Test ending a session (remove from cache, mark inactive)"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    mock_agent = Agent(
        id=UUID(agent_id),
        name="TestAgent",
        system_prompt="System",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id="test_user",
        agent_id=UUID(agent_id),
        session_type="webrtc",
        active=True,
        started_at=datetime.utcnow()
    )

    cached = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[],
        last_activity=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    service._cache[session_id] = cached

    # Mock database
    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx

        mock_db_ctx.execute = AsyncMock()
        mock_db_ctx.commit = AsyncMock()

        # End session
        await service.end_session(session_id, persist=True)

        # Verify removed from cache
        assert session_id not in service._cache

        # Verify database update called
        assert mock_db_ctx.execute.called
        assert mock_db_ctx.commit.called


@pytest.mark.asyncio
async def test_clear_cache_specific():
    """Test clearing cache for specific session"""
    service = ConversationService()

    # Add two sessions
    session1 = str(uuid4())
    session2 = str(uuid4())

    for sid in [session1, session2]:
        cached = CachedContext(
            session=Session(
                id=UUID(sid),
                user_id="test",
                agent_id=UUID(str(uuid4())),
                session_type="webrtc",
                active=True,
                started_at=datetime.utcnow()
            ),
            agent=Agent(
                id=UUID(str(uuid4())),
                name="Test",
                system_prompt="System",
                temperature=0.7,
                llm_provider="openrouter",
                llm_model="gpt-4"
            ),
            messages=[],
            last_activity=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=15)
        )
        service._cache[sid] = cached

    # Clear one session
    await service.clear_cache(session1)

    # Verify only one cleared
    assert session1 not in service._cache
    assert session2 in service._cache


@pytest.mark.asyncio
async def test_clear_cache_all():
    """Test clearing all cache"""
    service = ConversationService()

    # Add multiple sessions
    for i in range(3):
        sid = str(uuid4())
        cached = CachedContext(
            session=Session(
                id=UUID(sid),
                user_id=f"user_{i}",
                agent_id=UUID(str(uuid4())),
                session_type="webrtc",
                active=True,
                started_at=datetime.utcnow()
            ),
            agent=Agent(
                id=UUID(str(uuid4())),
                name=f"Agent{i}",
                system_prompt="System",
                temperature=0.7,
                llm_provider="openrouter",
                llm_model="gpt-4"
            ),
            messages=[],
            last_activity=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=15)
        )
        service._cache[sid] = cached

    # Clear all
    await service.clear_cache()

    # Verify all cleared
    assert len(service._cache) == 0


@pytest.mark.asyncio
async def test_get_active_sessions():
    """Test retrieving list of active session IDs"""
    service = ConversationService()

    # Add sessions
    session_ids = [str(uuid4()) for _ in range(3)]

    for sid in session_ids:
        cached = CachedContext(
            session=Session(
                id=UUID(sid),
                user_id="test",
                agent_id=UUID(str(uuid4())),
                session_type="webrtc",
                active=True,
                started_at=datetime.utcnow()
            ),
            agent=Agent(
                id=UUID(str(uuid4())),
                name="Test",
                system_prompt="System",
                temperature=0.7,
                llm_provider="openrouter",
                llm_model="gpt-4"
            ),
            messages=[],
            last_activity=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=15)
        )
        service._cache[sid] = cached

    # Get active sessions
    active = await service.get_active_sessions()

    assert len(active) == 3
    assert set(active) == set(session_ids)


@pytest.mark.asyncio
async def test_update_session_activity():
    """Test updating session activity timestamp (keepalive)"""
    service = ConversationService()

    session_id = str(uuid4())

    cached = CachedContext(
        session=Session(
            id=UUID(session_id),
            user_id="test",
            agent_id=UUID(str(uuid4())),
            session_type="webrtc",
            active=True,
            started_at=datetime.utcnow()
        ),
        agent=Agent(
            id=UUID(str(uuid4())),
            name="Test",
            system_prompt="System",
            temperature=0.7,
            llm_provider="openrouter",
            llm_model="gpt-4"
        ),
        messages=[],
        last_activity=datetime.utcnow() - timedelta(minutes=10),
        expires_at=datetime.utcnow() - timedelta(minutes=5)
    )
    service._cache[session_id] = cached

    old_activity = cached.last_activity
    old_expires = cached.expires_at

    # Update activity
    await service.update_session_activity(session_id)

    # Verify updated
    assert cached.last_activity > old_activity
    assert cached.expires_at > old_expires
