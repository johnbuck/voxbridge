"""
Unit tests for Mem0 extraction bug (TDD approach).

This test file exposes the bug where extraction code looks for result["memories"]
but Mem0 v1.1 actually returns result["results"].

Expected behavior: Test should FAIL initially, then PASS after fix is applied.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, Agent


@pytest.mark.asyncio
async def test_extraction_uses_results_key_from_mem0_response():
    """
    Test that extraction correctly reads from result["results"] (v1.1 format).

    BUG: Current code looks for result["memories"] which doesn't exist in v1.1.
    FIX: Should look for result["results"] instead.

    This test will FAIL until the bug is fixed.
    """
    # Arrange: Mock all dependencies to isolate the bug
    mock_db = AsyncMock(spec=AsyncSession)
    mock_user = User(id="user_123", user_id="test_user")
    mock_agent = Agent(id="agent_123", name="Test Agent")

    # This is what Mem0 v1.1 ACTUALLY returns (confirmed via research)
    realistic_mem0_response = {
        "results": [  # ✅ Correct key per API docs
            {
                "id": "vector_uuid_123",
                "memory": "Favorite color is blue",
                "event": "ADD"
            },
            {
                "id": "vector_uuid_456",
                "memory": "Lives in Portland",
                "event": "ADD"
            }
        ]
    }

    # Import here to avoid initialization issues
    from src.services.memory_service import MemoryService

    # Create a mock MemoryService that bypasses __init__
    with patch.object(MemoryService, '__init__', return_value=None):
        memory_service = MemoryService.__new__(MemoryService)

        # Set up minimal required attributes
        memory_service.memory = MagicMock()
        memory_service.memory.add = MagicMock(return_value=realistic_mem0_response)
        memory_service.embedding_config = {"provider": "local", "model": "test"}
        memory_service.executor = MagicMock()

        # Mock _upsert_fact to track calls
        memory_service._upsert_fact = AsyncMock()

        # Mock asyncio.get_event_loop and run_in_executor
        with patch('asyncio.get_event_loop') as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.run_in_executor = AsyncMock(return_value=realistic_mem0_response)
            mock_get_loop.return_value = mock_loop

            # Act: Call the actual extraction method
            await memory_service._extract_facts_from_turn(
                user_id="test_user",
                agent_id=mock_agent.id,
                user_message="What's your favorite color?",
                ai_response="My favorite color is blue and I live in Portland"
            )

        # Assert: _upsert_fact should be called TWICE (one for each result)
        # BUG: Currently called 0 times because code looks for result["memories"]
        # FIX: After fix, should be called 2 times for result["results"]
        assert memory_service._upsert_fact.call_count == 2, (
            f"Expected _upsert_fact to be called 2 times (one per fact in results), "
            f"but was called {memory_service._upsert_fact.call_count} times. "
            f"This indicates the code is looking for 'memories' key instead of 'results' key."
        )

        # Verify correct data was passed
        calls = memory_service._upsert_fact.call_args_list
        assert calls[0].kwargs["fact_text"] == "Favorite color is blue"
        assert calls[0].kwargs["vector_id"] == "vector_uuid_123"
        assert calls[1].kwargs["fact_text"] == "Lives in Portland"
        assert calls[1].kwargs["vector_id"] == "vector_uuid_456"


@pytest.mark.asyncio
async def test_extraction_handles_empty_results_gracefully():
    """
    Test that extraction handles result["results"] = [] correctly.
    """
    from src.services.memory_service import MemoryService

    mock_db = AsyncMock(spec=AsyncSession)
    mock_user = User(id="user_123", user_id="test_user")
    mock_agent = Agent(id="agent_123", name="Test Agent")

    empty_response = {"results": []}

    with patch.object(MemoryService, '__init__', return_value=None):
        memory_service = MemoryService.__new__(MemoryService)
        memory_service.memory = MagicMock()
        memory_service.embedding_config = {"provider": "local"}
        memory_service.executor = MagicMock()
        memory_service._upsert_fact = AsyncMock()

        with patch('asyncio.get_event_loop') as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.run_in_executor = AsyncMock(return_value=empty_response)
            mock_get_loop.return_value = mock_loop

            # Act: Should not raise exception
            await memory_service._extract_facts_from_turn(
                user_id="test_user",
                agent_id=mock_agent.id,
                user_message="Hello",
                ai_response="Hi"
            )

        # Assert: No facts should be created
        assert memory_service._upsert_fact.call_count == 0


@pytest.mark.asyncio
async def test_extraction_filters_update_and_delete_events():
    """
    Test that extraction only processes ADD events, not UPDATE or DELETE.
    """
    from src.services.memory_service import MemoryService

    mock_db = AsyncMock(spec=AsyncSession)
    mock_user = User(id="user_123", user_id="test_user")
    mock_agent = Agent(id="agent_123", name="Test Agent")

    mixed_events_response = {
        "results": [
            {"id": "vec_1", "memory": "Fact 1", "event": "ADD"},
            {"id": "vec_2", "memory": "Fact 2", "event": "UPDATE"},
            {"id": "vec_3", "memory": "Fact 3", "event": "DELETE"},
            {"id": "vec_4", "memory": "Fact 4", "event": "ADD"},
        ]
    }

    with patch.object(MemoryService, '__init__', return_value=None):
        memory_service = MemoryService.__new__(MemoryService)
        memory_service.memory = MagicMock()
        memory_service.embedding_config = {"provider": "local"}
        memory_service.executor = MagicMock()
        memory_service._upsert_fact = AsyncMock()

        with patch('asyncio.get_event_loop') as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.run_in_executor = AsyncMock(return_value=mixed_events_response)
            mock_get_loop.return_value = mock_loop

            # Act
            await memory_service._extract_facts_from_turn(
                user_id="test_user",
                agent_id=mock_agent.id,
                user_message="Test",
                ai_response="Response"
            )

        # Assert: Only 2 ADD events should result in upserts
        assert memory_service._upsert_fact.call_count == 2
        calls = memory_service._upsert_fact.call_args_list
        assert calls[0].kwargs["fact_text"] == "Fact 1"
        assert calls[1].kwargs["fact_text"] == "Fact 4"
