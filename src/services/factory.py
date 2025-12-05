"""
Async factory functions for service initialization.

Replaces direct __init__() calls to properly handle async initialization
within running event loops. This solves the asyncio.run() event loop conflict
that prevented MemoryService from initializing in WebRTC and Discord instances.

Usage:
    # Before (FAILS in running event loop)
    service = ConversationService()

    # After (WORKS in running event loop)
    service = await create_conversation_service()

Author: VoxBridge Team
Created: 2025-11-25
"""

import logging
from typing import Optional

from src.services.conversation_service import ConversationService
from src.services.stt_service import STTService
from src.services.llm_service import LLMService
from src.services.tts_service import TTSService
from src.services.memory_service import MemoryService, get_global_embedding_config

logger = logging.getLogger(__name__)


async def create_conversation_service(
    cache_ttl_minutes: int = 15,
    max_context_messages: int = 20,
    memory_service: Optional[MemoryService] = None
) -> ConversationService:
    """
    Create ConversationService with optional MemoryService injection.

    This factory function accepts an optional global MemoryService instance
    to prevent creating multiple MemoryService instances (singleton pattern).
    If no memory_service is provided, it creates one (for backward compatibility).

    Args:
        cache_ttl_minutes: How long to keep inactive sessions in cache (default: 15)
        max_context_messages: Maximum messages to cache per session (default: 20)
        memory_service: Optional global MemoryService singleton to inject (default: None)

    Returns:
        ConversationService instance with memory access enabled (if memory_service provided)

    Raises:
        Exception: If critical initialization fails (ConversationService creation itself)

    Example:
        >>> # Inject global singleton (recommended for production)
        >>> global_memory_service = MemoryService(...)
        >>> service = await create_conversation_service(memory_service=global_memory_service)
        >>>
        >>> # Create standalone (testing/development)
        >>> service = await create_conversation_service()
    """
    logger.info("🏭 Creating ConversationService via factory...")

    # If no MemoryService provided, create one (backward compatibility)
    if memory_service is None:
        logger.debug("🧠 No MemoryService provided, creating standalone instance...")
        try:
            logger.debug("🧠 Fetching embedding configuration from database...")
            db_embedding_config = await get_global_embedding_config()

            model_name = db_embedding_config.get('model_name', 'unknown')
            logger.info(f"🧠 Initializing MemoryService with model: {model_name}")

            memory_service = MemoryService(db_embedding_config=db_embedding_config)
            logger.info("✅ MemoryService initialized successfully (ready for retrieval)")

        except Exception as e:
            logger.warning(f"⚠️ MemoryService initialization failed: {e}")
            logger.warning("🧠 Continuing without memory features (conversations will work, but no fact retrieval)")
            memory_service = None
    else:
        logger.info("✅ Using injected global MemoryService singleton")

    # Create ConversationService with MemoryService
    try:
        service = ConversationService(
            cache_ttl_minutes=cache_ttl_minutes,
            max_context_messages=max_context_messages,
            memory_service=memory_service
        )
        logger.info(
            f"✅ ConversationService created: "
            f"memory_enabled={memory_service is not None}, "
            f"cache_ttl={cache_ttl_minutes}min, "
            f"max_context={max_context_messages}"
        )
        return service

    except Exception as e:
        logger.error(f"❌ ConversationService creation failed: {e}")
        raise


async def create_stt_service() -> STTService:
    """
    Create STTService with async initialization.

    Future-proofing: Currently STTService doesn't require async init,
    but this factory provides consistency and allows for future async
    initialization if needed.

    Returns:
        STTService instance

    Raises:
        Exception: If critical initialization fails

    Example:
        >>> stt_service = await create_stt_service()
        >>> await stt_service.start()
    """
    logger.info("🏭 Creating STTService via factory...")
    try:
        service = STTService()
        logger.info("✅ STTService created")
        return service
    except Exception as e:
        logger.error(f"❌ STTService creation failed: {e}")
        raise


async def create_llm_service() -> LLMService:
    """
    Create LLMService with async initialization.

    Future-proofing: Currently LLMService doesn't require async init,
    but this factory provides consistency and allows for future async
    initialization if needed (e.g., model caching, API key validation).

    Returns:
        LLMService instance

    Raises:
        Exception: If critical initialization fails

    Example:
        >>> llm_service = await create_llm_service()
        >>> response = await llm_service.generate_response(...)
    """
    logger.info("🏭 Creating LLMService via factory...")
    try:
        service = LLMService()
        logger.info("✅ LLMService created")
        return service
    except Exception as e:
        logger.error(f"❌ LLMService creation failed: {e}")
        raise


async def create_tts_service() -> TTSService:
    """
    Create TTSService with async initialization.

    Future-proofing: Currently TTSService doesn't require async init,
    but this factory provides consistency and allows for future async
    initialization if needed (e.g., voice model caching, health checks).

    Returns:
        TTSService instance

    Raises:
        Exception: If critical initialization fails

    Example:
        >>> tts_service = await create_tts_service()
        >>> await tts_service.synthesize(text="Hello, world!", voice_id="default")
    """
    logger.info("🏭 Creating TTSService via factory...")
    try:
        service = TTSService()
        logger.info("✅ TTSService created")
        return service
    except Exception as e:
        logger.error(f"❌ TTSService creation failed: {e}")
        raise
