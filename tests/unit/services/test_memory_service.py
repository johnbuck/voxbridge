"""
Unit tests for MemoryService

Tests Mem0 integration, memory extraction, retrieval, relevance filtering,
and graceful degradation.
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import UUID, uuid4

from src.services.memory_service import MemoryService
from src.database.models import User, UserFact, ExtractionTask, Agent


# ============================================================
# Initialization Tests
# ============================================================

@pytest.mark.asyncio
async def test_init_with_azure_embeddings():
    """Test initialization with Azure OpenAI embeddings"""
    with patch.dict('os.environ', {
        'EMBEDDING_PROVIDER': 'azure',
        'AZURE_EMBEDDING_API_KEY': 'test_key',
        'AZURE_EMBEDDING_ENDPOINT': 'https://test.openai.azure.com',
        'AZURE_EMBEDDING_DEPLOYMENT': 'text-embedding-3-large',
        'AZURE_EMBEDDING_API_VERSION': '2024-12-01-preview',
        'OPENROUTER_API_KEY': 'test_openrouter_key'
    }):
        with patch('src.services.memory_service.Memory') as mock_memory:
            with patch('src.services.memory_service.LLMService'):
                service = MemoryService()

                # Verify Memory.from_config called with Azure config
                mock_memory.from_config.assert_called_once()
                config = mock_memory.from_config.call_args[0][0]

                assert config['embedder']['provider'] == 'azure_openai'
                assert config['embedder']['config']['model'] == 'text-embedding-3-large'
                assert config['embedder']['config']['embedding_dims'] == 3072
                assert 'azure_kwargs' in config['embedder']['config']
                assert config['llm']['provider'] == 'openai'
                assert config['llm']['config']['model'] == 'gpt-4o-mini'


@pytest.mark.asyncio
async def test_init_with_local_embeddings():
    """Test initialization with local sentence-transformers embeddings"""
    with patch.dict('os.environ', {
        'EMBEDDING_PROVIDER': 'local',
        'LOCAL_EMBEDDING_MODEL': 'sentence-transformers/all-mpnet-base-v2',
        'LOCAL_EMBEDDING_DIMS': '768',
        'OPENROUTER_API_KEY': 'test_key'
    }):
        with patch('src.services.memory_service.Memory') as mock_memory:
            with patch('src.services.memory_service.LLMService'):
                service = MemoryService()

                # Verify Memory.from_config called with local config
                mock_memory.from_config.assert_called_once()
                config = mock_memory.from_config.call_args[0][0]

                assert config['embedder']['provider'] == 'huggingface'
                assert config['embedder']['config']['model'] == 'sentence-transformers/all-mpnet-base-v2'
                assert config['embedder']['config']['embedding_dims'] == 768


@pytest.mark.asyncio
async def test_init_fallback_to_local_when_azure_unconfigured():
    """Test automatic fallback to local embeddings when Azure credentials missing"""
    with patch.dict('os.environ', {
        'EMBEDDING_PROVIDER': 'azure',
        # No AZURE_EMBEDDING_API_KEY or AZURE_EMBEDDING_ENDPOINT
        'OPENROUTER_API_KEY': 'test_key'
    }, clear=True):
        with patch('src.services.memory_service.Memory') as mock_memory:
            with patch('src.services.memory_service.LLMService'):
                service = MemoryService()

                # Should fall back to local embeddings
                config = mock_memory.from_config.call_args[0][0]
                assert config['embedder']['provider'] == 'huggingface'


# ============================================================
# Queue Extraction Tests
# ============================================================

@pytest.mark.asyncio
async def test_queue_extraction_success():
    """Test successfully queuing an extraction task"""
    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    user_id = "user123"
    agent_id = uuid4()
    user_message = "My name is Alice"
    ai_response = "Nice to meet you, Alice!"

    # Mock task
    mock_task = ExtractionTask(
        id=uuid4(),
        user_id=user_id,
        agent_id=agent_id,
        user_message=user_message,
        ai_response=ai_response,
        status="pending",
        attempts=0
    )

    # Mock database session with async context manager pattern
    with patch('src.services.memory_service.get_db_session') as mock_get_db:
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db

        # Configure session methods
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock(side_effect=lambda t: setattr(t, 'id', mock_task.id))

        task_id = await service.queue_extraction(user_id, agent_id, user_message, ai_response)

        # Verify task was created
        assert mock_db.add.called
        mock_db.commit.assert_called_once()
        assert task_id == mock_task.id


@pytest.mark.asyncio
async def test_queue_extraction_database_error():
    """Test handling database errors when queuing extraction"""
    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    # Mock database session with async context manager pattern
    with patch('src.services.memory_service.get_db_session') as mock_get_db:
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db

        # Configure session methods - commit raises exception
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock(side_effect=Exception("Database connection failed"))

        with pytest.raises(Exception, match="Database connection failed"):
            await service.queue_extraction("user123", uuid4(), "test", "test")


# ============================================================
# Process Extraction Queue Tests
# ============================================================

@pytest.mark.asyncio
async def test_process_extraction_queue_single_task():
    """Test processing a single extraction task"""
    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    # Mock extraction method
    service._extract_facts_from_turn = AsyncMock()

    # Mock task
    task = ExtractionTask(
        id=uuid4(),
        user_id="user123",
        agent_id=uuid4(),
        user_message="My name is Alice",
        ai_response="Nice to meet you, Alice!",
        status="pending",
        attempts=0
    )

    # Mock database session with async context manager pattern
    with patch('src.services.memory_service.get_db_session') as mock_get_db:
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db

        # Configure execute to return proper result chain
        # First call returns task, second call returns empty list (exit loop)
        mock_result_1 = MagicMock()
        mock_result_1.scalars.return_value.all.return_value = [task]

        mock_result_2 = MagicMock()
        mock_result_2.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_result_1, mock_result_2])
        mock_db.commit = AsyncMock()

        # Run for one iteration
        with patch('asyncio.sleep', side_effect=[None, asyncio.CancelledError()]):
            try:
                await service.process_extraction_queue()
            except asyncio.CancelledError:
                pass

    # Verify task was processed
    service._extract_facts_from_turn.assert_called_once_with(
        task.user_id,
        task.agent_id,
        task.user_message,
        task.ai_response
    )
    assert task.status == "completed"


@pytest.mark.asyncio
async def test_process_extraction_queue_retry_on_failure():
    """Test retry logic when extraction fails"""
    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    # Mock extraction method to fail
    service._extract_facts_from_turn = AsyncMock(side_effect=Exception("Extraction failed"))

    # Mock task
    task = ExtractionTask(
        id=uuid4(),
        user_id="user123",
        agent_id=uuid4(),
        user_message="test",
        ai_response="test",
        status="pending",
        attempts=0
    )

    # Mock database session with async context manager pattern
    with patch('src.services.memory_service.get_db_session') as mock_get_db:
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db

        # Configure execute to return proper result chain
        mock_result_1 = MagicMock()
        mock_result_1.scalars.return_value.all.return_value = [task]

        mock_result_2 = MagicMock()
        mock_result_2.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_result_1, mock_result_2])
        mock_db.commit = AsyncMock()

        with patch('asyncio.sleep', side_effect=[None, asyncio.CancelledError()]):
            try:
                await service.process_extraction_queue()
            except asyncio.CancelledError:
                pass

    # Verify task marked as pending (will retry) and attempts incremented
    assert task.status == "pending"
    assert task.attempts == 1


@pytest.mark.asyncio
async def test_process_extraction_queue_max_retries():
    """Test task marked as failed after max retries"""
    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    service._extract_facts_from_turn = AsyncMock(side_effect=Exception("Extraction failed"))

    # Task that has already failed twice
    task = ExtractionTask(
        id=uuid4(),
        user_id="user123",
        agent_id=uuid4(),
        user_message="test",
        ai_response="test",
        status="pending",
        attempts=2
    )

    # Mock database session with async context manager pattern
    with patch('src.services.memory_service.get_db_session') as mock_get_db:
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db

        # Configure execute to return proper result chain
        mock_result_1 = MagicMock()
        mock_result_1.scalars.return_value.all.return_value = [task]

        mock_result_2 = MagicMock()
        mock_result_2.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_result_1, mock_result_2])
        mock_db.commit = AsyncMock()

        with patch('asyncio.sleep', side_effect=[None, asyncio.CancelledError()]):
            try:
                await service.process_extraction_queue()
            except asyncio.CancelledError:
                pass

    # Verify task marked as failed after 3rd attempt
    assert task.status == "failed"
    assert task.attempts == 3


# ============================================================
# Extract Facts Tests
# ============================================================

@pytest.mark.asyncio
async def test_extract_facts_success():
    """Test successful fact extraction with Mem0"""
    # Create mock memory with proper return value
    mock_memory = MagicMock()
    mock_memory.add.return_value = {
        "memories": [
            {"id": "mem1", "memory": "name: Alice", "score": 0.9},
            {"id": "mem2", "memory": "location: San Francisco", "score": 0.85}
        ]
    }

    with patch('src.services.memory_service.Memory') as MockMemory:
        MockMemory.from_config.return_value = mock_memory
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    # Mock relevance filter to return True
    service._should_extract_facts = AsyncMock(return_value=True)
    service._get_or_create_user = AsyncMock(return_value=User(id=1, user_id="user123"))
    service._get_agent = AsyncMock(return_value=Agent(
        id=uuid4(),
        name="TestAgent",
        system_prompt="test",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4",
        memory_scope="global"
    ))
    service._upsert_fact = AsyncMock()

    # Mock database session with async context manager pattern
    with patch('src.services.memory_service.get_db_session') as mock_get_db:
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db

        await service._extract_facts_from_turn(
            "user123",
            uuid4(),
            "My name is Alice and I live in San Francisco",
            "Nice to meet you, Alice!"
        )

    # Verify Mem0 add was called
    mock_memory.add.assert_called_once()

    # Verify facts were upserted
    assert service._upsert_fact.call_count == 2


@pytest.mark.asyncio
async def test_extract_facts_skip_irrelevant():
    """Test skipping extraction when relevance filter returns False"""
    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    # Mock relevance filter to return False
    service._should_extract_facts = AsyncMock(return_value=False)

    mock_db = AsyncMock()

    with patch('src.services.memory_service.get_db_session', return_value=mock_db):
        await service._extract_facts_from_turn(
            "user123",
            uuid4(),
            "Hello",
            "Hi there!"
        )

    # Verify extraction was skipped (no database operations)
    assert not mock_db.execute.called


@pytest.mark.asyncio
async def test_extract_facts_agent_specific_scope():
    """Test agent-specific memory scope uses user_id:agent_id format"""
    # Create mock memory
    mock_memory = MagicMock()
    mock_memory.add.return_value = {"memories": []}

    with patch('src.services.memory_service.Memory') as MockMemory:
        MockMemory.from_config.return_value = mock_memory
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    agent_id = uuid4()
    service._should_extract_facts = AsyncMock(return_value=True)
    service._get_or_create_user = AsyncMock(return_value=User(id=1, user_id="user123"))
    service._get_agent = AsyncMock(return_value=Agent(
        id=agent_id,
        name="TestAgent",
        system_prompt="test",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4",
        memory_scope="agent"  # Agent-specific scope
    ))

    # Mock database session with async context manager pattern
    with patch('src.services.memory_service.get_db_session') as mock_get_db:
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db

        await service._extract_facts_from_turn(
            "user123",
            agent_id,
            "test message",
            "test response"
        )

    # Verify Mem0 add was called with user_id:agent_id
    call_args = mock_memory.add.call_args
    assert call_args[1]['user_id'] == f"user123:{agent_id}"


# ============================================================
# Get User Memory Context Tests
# ============================================================

@pytest.mark.asyncio
async def test_get_memory_context_success():
    """Test retrieving relevant user memories"""
    # Create mock memory with search results
    mock_memory = MagicMock()
    mock_memory.search.return_value = [
        {"memory": "name: Alice", "score": 0.9},
        {"memory": "location: San Francisco", "score": 0.85},
        {"memory": "occupation: Engineer", "score": 0.8}
    ]

    with patch('src.services.memory_service.Memory') as MockMemory:
        MockMemory.from_config.return_value = mock_memory
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    agent_id = uuid4()
    service._get_agent = AsyncMock(return_value=Agent(
        id=agent_id,
        name="TestAgent",
        system_prompt="test",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4",
        memory_scope="global"
    ))

    # Mock database session with async context manager pattern
    with patch('src.services.memory_service.get_db_session') as mock_get_db:
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db

        context = await service.get_user_memory_context(
            "user123",
            agent_id,
            "What's my name?",
            limit=5
        )

    # Verify context formatted correctly
    assert "<user_memories>" in context
    assert "</user_memories>" in context
    assert "name: Alice" in context
    assert "location: San Francisco" in context
    assert "relevance: 0.90" in context


@pytest.mark.asyncio
async def test_get_memory_context_empty():
    """Test handling when no memories found"""
    mock_memory = MagicMock()
    mock_memory.search.return_value = []

    with patch('src.services.memory_service.Memory', return_value=mock_memory):
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    service._get_agent = AsyncMock(return_value=Agent(
        id=uuid4(),
        name="TestAgent",
        system_prompt="test",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4",
        memory_scope="global"
    ))

    mock_db = AsyncMock()

    with patch('src.services.memory_service.get_db_session', return_value=mock_db):
        context = await service.get_user_memory_context(
            "user123",
            uuid4(),
            "test query",
            limit=5
        )

    # Should return empty string
    assert context == ""


@pytest.mark.asyncio
async def test_get_memory_context_error_handling():
    """Test graceful degradation when memory retrieval fails"""
    mock_memory = MagicMock()
    mock_memory.search.side_effect = Exception("Mem0 connection failed")

    with patch('src.services.memory_service.Memory', return_value=mock_memory):
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    service._get_agent = AsyncMock(return_value=Agent(
        id=uuid4(),
        name="TestAgent",
        system_prompt="test",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="gpt-4",
        memory_scope="global"
    ))

    mock_db = AsyncMock()

    with patch('src.services.memory_service.get_db_session', return_value=mock_db):
        context = await service.get_user_memory_context(
            "user123",
            uuid4(),
            "test query",
            limit=5
        )

    # Should return empty string on error (graceful degradation)
    assert context == ""


# ============================================================
# Relevance Filter Tests
# ============================================================

@pytest.mark.asyncio
async def test_should_extract_facts_yes():
    """Test relevance filter returning True for relevant conversation"""
    mock_llm_service = AsyncMock()
    mock_llm_service.generate.return_value = "yes"

    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService', return_value=mock_llm_service):
            service = MemoryService()

    result = await service._should_extract_facts(
        "My name is Alice and I'm a software engineer",
        "Nice to meet you, Alice!"
    )

    assert result is True


@pytest.mark.asyncio
async def test_should_extract_facts_no():
    """Test relevance filter returning False for irrelevant conversation"""
    mock_llm_service = AsyncMock()
    mock_llm_service.generate.return_value = "no"

    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService', return_value=mock_llm_service):
            service = MemoryService()

    result = await service._should_extract_facts(
        "Hello",
        "Hi there!"
    )

    assert result is False


@pytest.mark.asyncio
async def test_should_extract_facts_llm_error():
    """Test relevance filter handling LLM errors"""
    mock_llm_service = AsyncMock()
    mock_llm_service.generate.side_effect = Exception("LLM API failed")

    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService', return_value=mock_llm_service):
            service = MemoryService()

    # Should handle error gracefully (return False to skip extraction)
    with pytest.raises(Exception, match="LLM API failed"):
        await service._should_extract_facts("test", "test")


# ============================================================
# Helper Method Tests
# ============================================================

@pytest.mark.asyncio
async def test_get_or_create_user_existing():
    """Test getting existing user from database"""
    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    existing_user = User(id=1, user_id="user123")

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_user
    mock_db.execute = AsyncMock(return_value=mock_result)

    user = await service._get_or_create_user("user123", mock_db)

    assert user == existing_user
    assert not mock_db.add.called


@pytest.mark.asyncio
async def test_get_or_create_user_new():
    """Test creating new user when not exists"""
    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # User doesn't exist
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    user = await service._get_or_create_user("user123", mock_db)

    assert mock_db.add.called
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_upsert_fact_new():
    """Test creating new fact"""
    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    user = User(id=1, user_id="user123")
    agent_id = uuid4()

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # Fact doesn't exist
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    await service._upsert_fact(
        user=user,
        agent_id=agent_id,
        vector_id="vec123",
        fact_text="name: Alice",
        importance=0.9,
        embedding_provider="azure",
        embedding_model="text-embedding-3-large",
        db=mock_db
    )

    # Verify new fact was added
    assert mock_db.add.called
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_upsert_fact_update_existing():
    """Test updating existing fact"""
    with patch('src.services.memory_service.Memory'):
        with patch('src.services.memory_service.LLMService'):
            service = MemoryService()

    user = User(id=1, user_id="user123")
    agent_id = uuid4()

    existing_fact = UserFact(
        id=1,
        user_id=user.id,
        agent_id=agent_id,
        fact_key="name",
        fact_value="Bob",
        fact_text="name: Bob",
        importance=0.7,
        vector_id="vec123"
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_fact
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()

    await service._upsert_fact(
        user=user,
        agent_id=agent_id,
        vector_id="vec456",
        fact_text="name: Alice",
        importance=0.9,
        embedding_provider="azure",
        embedding_model="text-embedding-3-large",
        db=mock_db
    )

    # Verify fact was updated
    assert existing_fact.fact_value == "Alice"
    assert existing_fact.fact_text == "name: Alice"
    assert existing_fact.importance == 0.9
    assert existing_fact.vector_id == "vec456"
    assert not mock_db.add.called  # Should not add new fact
    assert mock_db.commit.called
