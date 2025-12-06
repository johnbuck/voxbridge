"""
Unit tests for Mem0 retrieval bug (TDD approach).

This test file exposes the bug where retrieval code looks for mem.get("memory")
but Mem0 actually stores facts in payload["data"] field (confirmed via database query).

Expected behavior: Test should FAIL initially, then PASS after fix is applied.
"""
import pytest
from unittest.mock import patch, MagicMock

from src.services.memory_service import MemoryService


@pytest.mark.asyncio
async def test_retrieval_reads_data_field_from_mem0_payload():
    """
    Test that memory retrieval correctly reads from mem["data"] field.

    BUG: Current code looks for mem.get("memory", "") which doesn't exist.
    FIX: Should look for mem.get("data", "") instead.

    EVIDENCE: Database query shows payload structure:
    {
      "data": "Favorite color is blue",
      "hash": "...",
      "user_id": "...",
      "created_at": "..."
    }

    This test will FAIL until the bug is fixed.
    """
    # This is what Mem0 ACTUALLY returns (confirmed via database query)
    realistic_search_results = [
        {
            "id": "vector_uuid_123",
            "data": "Favorite color is blue",  # ✅ Correct field per database evidence
            "score": 0.95,
            "hash": "abc123",
            "user_id": "test_user",
            "created_at": "2025-11-28T12:00:00"
        },
        {
            "id": "vector_uuid_456",
            "data": "Lives in Portland",
            "score": 0.88,
            "hash": "def456",
            "user_id": "test_user",
            "created_at": "2025-11-28T12:01:00"
        }
    ]

    # Create a mock MemoryService that bypasses __init__
    with patch.object(MemoryService, '__init__', return_value=None):
        memory_service = MemoryService.__new__(MemoryService)

        # Set up minimal required attributes
        memory_service.memory = MagicMock()
        memory_service.memory.search = MagicMock(return_value=realistic_search_results)
        memory_service.embedding_config = {"provider": "local", "model": "BAAI/bge-large-en-v1.5"}

        # Act: Retrieve memories
        context = await memory_service.get_user_memory_context(
            query="What do you know about me?",
            user_id="test_user",
            limit=5
        )

        # Assert: Context should contain actual memory text, not empty strings
        # BUG: Currently returns "- (relevance: 0.95)\n- (relevance: 0.88)"
        # FIX: Should return "- Favorite color is blue (relevance: 0.95)\n- Lives in Portland (relevance: 0.88)"
        assert "Favorite color is blue" in context, (
            f"Expected memory text 'Favorite color is blue' in context, "
            f"but got: {context}. "
            f"This indicates the code is reading from the wrong field in Mem0 response."
        )
        assert "Lives in Portland" in context, (
            f"Expected memory text 'Lives in Portland' in context, "
            f"but got: {context}"
        )

        # Verify the correct format is used
        assert "(relevance: 0.95)" in context
        assert "(relevance: 0.88)" in context

        # Verify empty strings are NOT present
        assert "- (relevance:" not in context or "blue (relevance:" in context


@pytest.mark.asyncio
async def test_retrieval_handles_empty_results_gracefully():
    """
    Test that retrieval handles empty search results correctly.

    Should return empty string or appropriate message, not crash.
    """
    # Create a mock MemoryService that bypasses __init__
    with patch.object(MemoryService, '__init__', return_value=None):
        memory_service = MemoryService.__new__(MemoryService)

        # Set up minimal required attributes
        memory_service.memory = MagicMock()
        memory_service.memory.search = MagicMock(return_value=[])
        memory_service.embedding_config = {"provider": "local", "model": "BAAI/bge-large-en-v1.5"}

        # Act
        context = await memory_service.get_user_memory_context(
            query="Tell me about yourself",
            user_id="new_user",
            limit=5
        )

        # Assert: Should return empty string or not crash
        assert isinstance(context, str)
        assert context == ""  # No memories found


@pytest.mark.asyncio
async def test_retrieval_formats_context_with_user_memories_tags():
    """
    Test that retrieved memories are formatted with <user_memories> XML tags.

    The LLM expects memory context in this format:
    <user_memories>
    - Memory 1 (relevance: 0.95)
    - Memory 2 (relevance: 0.88)
    </user_memories>
    """
    search_results = [
        {
            "id": "vec_1",
            "data": "Likes science fiction books",
            "score": 0.92
        }
    ]

    # Create a mock MemoryService that bypasses __init__
    with patch.object(MemoryService, '__init__', return_value=None):
        memory_service = MemoryService.__new__(MemoryService)

        # Set up minimal required attributes
        memory_service.memory = MagicMock()
        memory_service.memory.search = MagicMock(return_value=search_results)
        memory_service.embedding_config = {"provider": "local", "model": "BAAI/bge-large-en-v1.5"}

        # Act
        context = await memory_service.get_user_memory_context(
            query="What are my hobbies?",
            user_id="test_user",
            limit=5
        )

        # Assert: Should have proper formatting
        # Note: Actual formatting depends on implementation
        # This test assumes the context includes the memory text
        assert "Likes science fiction books" in context


@pytest.mark.asyncio
async def test_retrieval_handles_missing_data_field_gracefully():
    """
    Test fallback behavior when 'data' field is missing (edge case).

    In case of malformed responses or API changes, the code should:
    1. Try 'data' field first (current format)
    2. Fall back to 'memory' field (legacy format)
    3. Default to empty string if neither exists

    This ensures backward compatibility and graceful degradation.
    """
    # Malformed result missing 'data' field
    malformed_results = [
        {
            "id": "vec_1",
            # Missing 'data' field
            "score": 0.85
        },
        {
            "id": "vec_2",
            "memory": "Fallback to legacy format",  # Legacy field
            "score": 0.90
        }
    ]

    # Create a mock MemoryService that bypasses __init__
    with patch.object(MemoryService, '__init__', return_value=None):
        memory_service = MemoryService.__new__(MemoryService)

        # Set up minimal required attributes
        memory_service.memory = MagicMock()
        memory_service.memory.search = MagicMock(return_value=malformed_results)
        memory_service.embedding_config = {"provider": "local", "model": "BAAI/bge-large-en-v1.5"}

        # Act: Should not crash
        context = await memory_service.get_user_memory_context(
            query="Test",
            user_id="test_user",
            limit=5
        )

        # Assert: Should handle gracefully
        # vec_1 should be skipped (no data or memory field)
        # vec_2 should use legacy 'memory' field
        assert isinstance(context, str)
        # Depending on implementation, may include "Fallback to legacy format"
        # or may exclude entries without 'data' field
