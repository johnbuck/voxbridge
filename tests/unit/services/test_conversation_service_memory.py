"""
Unit tests for ConversationService memory injection functionality

Tests the factory pattern initialization with MemoryService and memory context
retrieval/injection into conversation contexts.
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import UUID, uuid4

from src.services.conversation_service import (
    ConversationService,
    Message,
    CachedContext,
)
from src.services.memory_service import MemoryService
from src.database.models import Agent, Session, Conversation
from datetime import timedelta


# ============================================================
# Initialization Tests (Factory Pattern)
# ============================================================

@pytest.mark.asyncio
async def test_init_with_memory_service():
    """Test initialization with MemoryService provided by factory"""
    # Create mock MemoryService
    mock_memory_service = MagicMock(spec=MemoryService)

    # Initialize ConversationService with memory_service
    service = ConversationService(
        cache_ttl_minutes=15,
        max_context_messages=20,
        memory_service=mock_memory_service
    )

    # Verify MemoryService was injected
    assert service._memory_service is not None
    assert service._memory_service == mock_memory_service


@pytest.mark.asyncio
async def test_init_without_memory_service():
    """Test initialization without MemoryService (graceful degradation)"""
    # Initialize ConversationService without memory_service
    service = ConversationService(
        cache_ttl_minutes=15,
        max_context_messages=20,
        memory_service=None
    )

    # Verify MemoryService is None
    assert service._memory_service is None


@pytest.mark.asyncio
async def test_init_default_memory_service():
    """Test initialization with default memory_service parameter (None)"""
    # Initialize ConversationService without providing memory_service
    service = ConversationService()

    # Verify MemoryService defaults to None
    assert service._memory_service is None


# ============================================================
# Memory Context Retrieval Tests
# ============================================================

@pytest.mark.asyncio
async def test_get_conversation_context_with_memory_injection():
    """Test memory context retrieval and injection into conversation context"""
    # Setup
    session_id = str(uuid4())
    user_id = "discord_123"
    agent_id = uuid4()

    # Create mock MemoryService
    mock_memory_service = MagicMock(spec=MemoryService)
    mock_memory_service.get_user_memory_context = AsyncMock(
        return_value="<user_memories>\n- User's favorite color is blue (relevance: 0.95)\n</user_memories>"
    )

    # Create mock agent and session
    mock_agent = Agent(
        id=agent_id,
        name="TestAgent",
        system_prompt="You are a helpful assistant",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id=user_id,
        user_name="TestUser",
        agent_id=agent_id,
        session_type="webrtc",
        active=True
    )
    mock_session.agent = mock_agent

    # Initialize ConversationService with MemoryService
    service = ConversationService(memory_service=mock_memory_service)

    # Manually populate cache with session and messages
    user_conv = Conversation(
        session_id=UUID(session_id),
        role="user",
        content="What is my favorite color?",
        timestamp=datetime.utcnow()
    )

    now = datetime.utcnow()
    service._cache[session_id] = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[user_conv],
        last_activity=now,
        expires_at=now + timedelta(minutes=15)
    )

    # Mock database operations
    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx
        mock_db_ctx.execute = AsyncMock()

        # Get conversation context
        context = await service.get_conversation_context(
            session_id=session_id,
            include_system_prompt=True
        )

    # Verify MemoryService was called
    mock_memory_service.get_user_memory_context.assert_called_once_with(
        user_id=user_id,
        agent_id=agent_id,
        query="What is my favorite color?",
        limit=5
    )

    # Verify memory context was injected into messages
    assert len(context) >= 2  # At least system prompt + memory + user message

    # Find the memory message
    memory_messages = [msg for msg in context if "<user_memories>" in msg.content]
    assert len(memory_messages) == 1
    assert "favorite color is blue" in memory_messages[0].content
    assert memory_messages[0].role == "system"


@pytest.mark.asyncio
async def test_get_conversation_context_with_empty_memory():
    """Test handling when MemoryService returns empty context"""
    # Setup
    session_id = str(uuid4())
    user_id = "discord_456"
    agent_id = uuid4()

    # Create mock MemoryService that returns empty string
    mock_memory_service = MagicMock(spec=MemoryService)
    mock_memory_service.get_user_memory_context = AsyncMock(return_value="")

    # Create mock agent and session
    mock_agent = Agent(
        id=agent_id,
        name="TestAgent",
        system_prompt="You are a helpful assistant",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id=user_id,
        user_name="TestUser",
        agent_id=agent_id,
        session_type="webrtc",
        active=True
    )
    mock_session.agent = mock_agent

    # Initialize ConversationService with MemoryService
    service = ConversationService(memory_service=mock_memory_service)

    # Manually populate cache with session and messages
    user_conv = Conversation(
        session_id=UUID(session_id),
        role="user",
        content="Hello!",
        timestamp=datetime.utcnow()
    )

    now = datetime.utcnow()
    service._cache[session_id] = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[user_conv],
        last_activity=now,
        expires_at=now + timedelta(minutes=15)
    )

    # Mock database operations
    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx
        mock_db_ctx.execute = AsyncMock()

        # Get conversation context
        context = await service.get_conversation_context(
            session_id=session_id,
            include_system_prompt=True
        )

    # Verify MemoryService was called
    mock_memory_service.get_user_memory_context.assert_called_once()

    # Verify no memory message was injected (empty result)
    memory_messages = [msg for msg in context if "<user_memories>" in msg.content]
    assert len(memory_messages) == 0


@pytest.mark.asyncio
async def test_get_conversation_context_without_memory_service():
    """Test conversation context retrieval when MemoryService is not available"""
    # Setup
    session_id = str(uuid4())
    user_id = "discord_789"
    agent_id = uuid4()

    # Create mock agent and session
    mock_agent = Agent(
        id=agent_id,
        name="TestAgent",
        system_prompt="You are a helpful assistant",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id=user_id,
        user_name="TestUser",
        agent_id=agent_id,
        session_type="webrtc",
        active=True
    )
    mock_session.agent = mock_agent

    # Initialize ConversationService WITHOUT MemoryService
    service = ConversationService(memory_service=None)

    # Manually populate cache with session and messages
    user_conv = Conversation(
        session_id=UUID(session_id),
        role="user",
        content="What is my favorite food?",
        timestamp=datetime.utcnow()
    )

    now = datetime.utcnow()
    service._cache[session_id] = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[user_conv],
        last_activity=now,
        expires_at=now + timedelta(minutes=15)
    )

    # Mock database operations
    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx
        mock_db_ctx.execute = AsyncMock()

        # Get conversation context
        context = await service.get_conversation_context(
            session_id=session_id,
            include_system_prompt=True
        )

    # Verify no memory messages were injected (MemoryService is None)
    memory_messages = [msg for msg in context if "<user_memories>" in msg.content]
    assert len(memory_messages) == 0

    # Verify context still contains system prompt and user message
    assert len(context) >= 2
    assert any(msg.role == "system" for msg in context)
    assert any(msg.role == "user" for msg in context)


@pytest.mark.asyncio
async def test_get_conversation_context_with_memory_error():
    """Test error handling when MemoryService fails"""
    # Setup
    session_id = str(uuid4())
    user_id = "discord_error"
    agent_id = uuid4()

    # Create mock MemoryService that raises exception
    mock_memory_service = MagicMock(spec=MemoryService)
    mock_memory_service.get_user_memory_context = AsyncMock(
        side_effect=Exception("Database connection failed")
    )

    # Create mock agent and session
    mock_agent = Agent(
        id=agent_id,
        name="TestAgent",
        system_prompt="You are a helpful assistant",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id=user_id,
        user_name="TestUser",
        agent_id=agent_id,
        session_type="webrtc",
        active=True
    )
    mock_session.agent = mock_agent

    # Initialize ConversationService with failing MemoryService
    service = ConversationService(memory_service=mock_memory_service)

    # Manually populate cache with session and messages
    user_conv = Conversation(
        session_id=UUID(session_id),
        role="user",
        content="What do you remember about me?",
        timestamp=datetime.utcnow()
    )

    now = datetime.utcnow()
    service._cache[session_id] = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[user_conv],
        last_activity=now,
        expires_at=now + timedelta(minutes=15)
    )

    # Mock database operations
    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx
        mock_db_ctx.execute = AsyncMock()

        # Get conversation context (should not raise exception)
        context = await service.get_conversation_context(
            session_id=session_id,
            include_system_prompt=True
        )

    # Verify MemoryService was called
    mock_memory_service.get_user_memory_context.assert_called_once()

    # Verify context was still returned (graceful degradation)
    assert context is not None
    assert len(context) >= 2

    # Verify no memory messages were injected (error occurred)
    memory_messages = [msg for msg in context if "<user_memories>" in msg.content]
    assert len(memory_messages) == 0


@pytest.mark.asyncio
async def test_get_conversation_context_no_user_messages():
    """Test memory retrieval skipped when no user messages exist"""
    # Setup
    session_id = str(uuid4())
    user_id = "discord_nomsg"
    agent_id = uuid4()

    # Create mock MemoryService
    mock_memory_service = MagicMock(spec=MemoryService)
    mock_memory_service.get_user_memory_context = AsyncMock()

    # Create mock agent and session
    mock_agent = Agent(
        id=agent_id,
        name="TestAgent",
        system_prompt="You are a helpful assistant",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id=user_id,
        user_name="TestUser",
        agent_id=agent_id,
        session_type="webrtc",
        active=True
    )
    mock_session.agent = mock_agent

    # Initialize ConversationService with MemoryService
    service = ConversationService(memory_service=mock_memory_service)

    # Manually populate cache with NO user messages (only system message)
    now = datetime.utcnow()
    service._cache[session_id] = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[],  # Empty messages list
        last_activity=now,
        expires_at=now + timedelta(minutes=15)
    )

    # Mock database operations
    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx
        mock_db_ctx.execute = AsyncMock()

        # Get conversation context
        context = await service.get_conversation_context(
            session_id=session_id,
            include_system_prompt=True
        )

    # Verify MemoryService was NOT called (no user messages to query with)
    mock_memory_service.get_user_memory_context.assert_not_called()

    # Verify context only contains system prompt
    assert len(context) == 1
    assert context[0].role == "system"


@pytest.mark.asyncio
async def test_memory_context_position_in_messages():
    """Test that memory context appears after system prompt and before user messages"""
    # Setup
    session_id = str(uuid4())
    user_id = "discord_position"
    agent_id = uuid4()

    # Create mock MemoryService
    mock_memory_service = MagicMock(spec=MemoryService)
    mock_memory_service.get_user_memory_context = AsyncMock(
        return_value="<user_memories>\n- User works as a software engineer (relevance: 0.90)\n</user_memories>"
    )

    # Create mock agent and session
    mock_agent = Agent(
        id=agent_id,
        name="TestAgent",
        system_prompt="You are a helpful assistant",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id=user_id,
        user_name="TestUser",
        agent_id=agent_id,
        session_type="webrtc",
        active=True
    )
    mock_session.agent = mock_agent

    # Initialize ConversationService with MemoryService
    service = ConversationService(memory_service=mock_memory_service)

    # Manually populate cache with multiple messages (Conversation objects in reverse chronological order)
    msg3_time = datetime.utcnow()
    msg2_time = msg3_time - timedelta(seconds=10)
    msg1_time = msg3_time - timedelta(seconds=20)

    conv1 = Conversation(
        session_id=UUID(session_id),
        role="user",
        content="Hello!",
        timestamp=msg1_time
    )
    conv2 = Conversation(
        session_id=UUID(session_id),
        role="assistant",
        content="Hi there!",
        timestamp=msg2_time
    )
    conv3 = Conversation(
        session_id=UUID(session_id),
        role="user",
        content="What do I do for work?",
        timestamp=msg3_time
    )

    now = datetime.utcnow()
    service._cache[session_id] = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[conv3, conv2, conv1],  # Reverse chronological order
        last_activity=now,
        expires_at=now + timedelta(minutes=15)
    )

    # Mock database operations
    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx
        mock_db_ctx.execute = AsyncMock()

        # Get conversation context
        context = await service.get_conversation_context(
            session_id=session_id,
            include_system_prompt=True
        )

    # Verify context order: system prompt → memory → conversation messages
    assert len(context) >= 5  # system + memory + 3 conversation messages
    assert context[0].role == "system"  # System prompt first
    assert context[0].content == "You are a helpful assistant"

    # Find memory message (should be second)
    assert context[1].role == "system"  # Memory is also system role
    assert "<user_memories>" in context[1].content
    assert "software engineer" in context[1].content

    # Verify conversation messages follow (in chronological order: oldest → newest)
    assert context[2].role == "user"
    assert context[2].content == "What do I do for work?"
    assert context[3].role == "assistant"
    assert context[3].content == "Hi there!"
    assert context[4].role == "user"
    assert context[4].content == "Hello!"


@pytest.mark.asyncio
async def test_memory_uses_last_user_message_as_query():
    """Test that memory retrieval uses the most recent user message as query"""
    # Setup
    session_id = str(uuid4())
    user_id = "discord_query"
    agent_id = uuid4()

    # Create mock MemoryService
    mock_memory_service = MagicMock(spec=MemoryService)
    mock_memory_service.get_user_memory_context = AsyncMock(return_value="")

    # Create mock agent and session
    mock_agent = Agent(
        id=agent_id,
        name="TestAgent",
        system_prompt="You are a helpful assistant",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4"
    )

    mock_session = Session(
        id=UUID(session_id),
        user_id=user_id,
        user_name="TestUser",
        agent_id=agent_id,
        session_type="webrtc",
        active=True
    )
    mock_session.agent = mock_agent

    # Initialize ConversationService with MemoryService
    service = ConversationService(memory_service=mock_memory_service)

    # Manually populate cache with multiple user messages (Conversation objects in reverse chronological order)
    msg5_time = datetime.utcnow()
    msg4_time = msg5_time - timedelta(seconds=5)
    msg3_time = msg5_time - timedelta(seconds=10)
    msg2_time = msg5_time - timedelta(seconds=15)
    msg1_time = msg5_time - timedelta(seconds=20)

    conv1 = Conversation(
        session_id=UUID(session_id),
        role="user",
        content="First message",
        timestamp=msg1_time
    )
    conv2 = Conversation(
        session_id=UUID(session_id),
        role="assistant",
        content="Response",
        timestamp=msg2_time
    )
    conv3 = Conversation(
        session_id=UUID(session_id),
        role="user",
        content="Second message",
        timestamp=msg3_time
    )
    conv4 = Conversation(
        session_id=UUID(session_id),
        role="assistant",
        content="Another response",
        timestamp=msg4_time
    )
    conv5 = Conversation(
        session_id=UUID(session_id),
        role="user",
        content="Most recent user message",
        timestamp=msg5_time
    )

    now = datetime.utcnow()
    service._cache[session_id] = CachedContext(
        session=mock_session,
        agent=mock_agent,
        messages=[conv5, conv4, conv3, conv2, conv1],  # Reverse chronological order
        last_activity=now,
        expires_at=now + timedelta(minutes=15)
    )

    # Mock database operations
    with patch('src.services.conversation_service.get_db_session') as mock_db:
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx
        mock_db_ctx.execute = AsyncMock()

        # Get conversation context
        await service.get_conversation_context(
            session_id=session_id,
            include_system_prompt=True
        )

    # Verify MemoryService was called with the LAST user message (chronologically oldest in reversed iteration)
    # Note: Cache stores in reverse chronological order (newest first),
    # Service reverses to chronological order, then takes first user message = oldest chronologically
    mock_memory_service.get_user_memory_context.assert_called_once_with(
        user_id=user_id,
        agent_id=agent_id,
        query="First message",  # Chronologically oldest user message
        limit=5
    )
