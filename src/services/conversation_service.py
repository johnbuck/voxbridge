"""
VoxBridge 2.0 Phase 5 - ConversationService

Purpose: Manage conversation sessions with in-memory context caching, session lifecycle,
and agent configuration loading from PostgreSQL.

Key Features:
- Session-based routing (UUID session IDs)
- In-memory conversation context cache (TTL-based, default 15 minutes)
- Support multiple concurrent sessions (async/await)
- Load context from PostgreSQL conversations table
- Cache conversation history (last N messages, default 20)
- TTL-based cache expiration with background cleanup task
- Agent configuration loading from database
- Per-session async locks for concurrency control

Design Patterns:
- Cache-Aside Pattern: Check cache first, load from DB on miss
- TTL-based Expiration: Automatic cleanup of inactive sessions
- Async Locks: Per-session locks prevent race conditions
- Repository Pattern: Encapsulates database access logic
"""

import os
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, update, and_
from sqlalchemy.orm import selectinload

from zoneinfo import ZoneInfo

from src.config.logging_config import get_logger
from src.database.models import Agent, Session, Conversation, User
from src.database.session import get_db_session
from src.services.memory_service import MemoryService

# Configure logging with emoji prefixes
logger = get_logger(__name__)

# Configuration from environment variables
CONVERSATION_CACHE_TTL_MINUTES = int(os.getenv('CONVERSATION_CACHE_TTL_MINUTES', '15'))
MAX_CONTEXT_MESSAGES = int(os.getenv('MAX_CONTEXT_MESSAGES', '20'))
CACHE_CLEANUP_INTERVAL_SECONDS = int(os.getenv('CACHE_CLEANUP_INTERVAL_SECONDS', '60'))


@dataclass
class Message:
    """
    Plain dataclass for cached conversation messages (detached from SQLAlchemy).

    This replaces direct storage of Conversation ORM objects in the cache to prevent
    SQLAlchemy DetachedInstanceError when database sessions close. All fields are
    copied from the ORM model at cache time, creating a fully independent object.

    Attributes:
        id: Database primary key
        session_id: UUID of the conversation session
        role: Message role ('user', 'assistant', or 'system')
        content: Message text content
        timestamp: When message was created
        audio_duration_ms: Duration of user audio input (nullable)
        tts_duration_ms: Duration of TTS synthesis (nullable)
        llm_latency_ms: LLM generation latency (nullable)
        total_latency_ms: Total end-to-end latency (nullable)
    """
    id: int
    session_id: str
    role: str
    content: str
    timestamp: datetime
    audio_duration_ms: Optional[int] = None
    tts_duration_ms: Optional[int] = None
    llm_latency_ms: Optional[int] = None
    total_latency_ms: Optional[int] = None


@dataclass
class CachedContext:
    """
    In-memory cache entry for a conversation session.

    Attributes:
        session: SQLAlchemy Session model
        agent: SQLAlchemy Agent model (eagerly loaded)
        messages: Recent conversation history as Message dataclasses (detached from SQLAlchemy)
        last_activity: Last cache access time (updated on each access)
        expires_at: When to evict from cache (last_activity + TTL)
        lock: Async lock for concurrent access control
    """
    session: Session
    agent: Agent
    messages: List[Message]  # Changed from List[Conversation] to prevent detachment errors
    last_activity: datetime
    expires_at: datetime
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ConversationService:
    """
    Manages conversation sessions with in-memory context caching.

    This service replaces the global speaker lock system with session-based routing,
    enabling multiple concurrent users (Discord + multiple web users).

    Usage:
        # Initialize and start background cleanup
        conv_service = ConversationService(cache_ttl_minutes=15, max_context_messages=20)
        await conv_service.start()

        # Get or create session
        session = await conv_service.get_or_create_session(
            session_id="550e8400-e29b-41d4-a716-446655440000",
            user_id="discord_123456",
            agent_id="agent_uuid",
            channel_type="discord"
        )

        # Get conversation context
        context = await conv_service.get_conversation_context(
            session_id="550e8400-e29b-41d4-a716-446655440000",
            limit=10,
            include_system_prompt=True
        )

        # Add message
        message = await conv_service.add_message(
            session_id="550e8400-e29b-41d4-a716-446655440000",
            role="user",
            content="Hello, AI!",
            metadata={"audio_duration_ms": 1500}
        )

        # End session
        await conv_service.end_session(session_id="550e8400-e29b-41d4-a716-446655440000")

        # Shutdown
        await conv_service.stop()
    """

    def __init__(self,
                 cache_ttl_minutes: int = CONVERSATION_CACHE_TTL_MINUTES,
                 max_context_messages: int = MAX_CONTEXT_MESSAGES,
                 memory_service: Optional['MemoryService'] = None):
        """
        Initialize ConversationService.

        Args:
            cache_ttl_minutes: How long to keep inactive sessions in cache (default: 15)
            max_context_messages: Maximum messages to cache per session (default: 20)
            memory_service: Optional MemoryService instance (provided by factory)
        """
        self._cache: Dict[str, CachedContext] = {}
        self._cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self._max_context = max_context_messages
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

        # Accept MemoryService from factory (no async initialization here)
        self._memory_service = memory_service
        if self._memory_service:
            logger.debug("🧠 MemoryService injected into ConversationService")
        else:
            logger.debug("🧠 ConversationService created without MemoryService")

        cache_ttl_log = f"{cache_ttl_minutes}min"
        logger.info(
            f"🎤 ConversationService initialized: "
            f"cache_ttl={cache_ttl_log}, max_context={max_context_messages}, "
            f"memory_enabled={self._memory_service is not None}"
        )

    async def start(self) -> None:
        """
        Start background cache cleanup task.

        Should be called on application startup (after database initialization).
        """
        if self._running:
            logger.warning("🔄 ConversationService already running")
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_cache())
        logger.info(f"✅ ConversationService started (cleanup interval: {CACHE_CLEANUP_INTERVAL_SECONDS}s)")

    async def stop(self) -> None:
        """
        Stop background tasks and cleanup.

        Should be called on application shutdown.
        """
        if not self._running:
            return

        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("✅ ConversationService stopped")

    async def get_or_create_session(
        self,
        session_id: str,
        user_id: str,
        agent_id: str,
        channel_type: str = "webrtc",
        user_name: Optional[str] = None,
        title: Optional[str] = None
    ) -> Session:
        """
        Get existing session or create new one.

        Args:
            session_id: UUID string for the session
            user_id: User identifier (Discord ID, web user ID, etc.)
            agent_id: Agent UUID string
            channel_type: Session type ('webrtc', 'discord', 'extension')
            user_name: Optional display name for debugging
            title: Optional conversation title

        Returns:
            Session: SQLAlchemy Session model

        Raises:
            ValueError: If agent_id not found in database
        """
        # Check cache first
        if session_id in self._cache:
            cached = self._cache[session_id]
            async with cached.lock:
                # Update activity
                cached.last_activity = datetime.utcnow()
                cached.expires_at = cached.last_activity + self._cache_ttl
                logger.debug(f"🎤 Session {session_id[:8]}... found in cache")
                return cached.session

        # Load from database or create new
        try:
            async with get_db_session() as db:
                # Try to load existing session
                result = await db.execute(
                    select(Session)
                    .options(selectinload(Session.agent))
                    .where(Session.id == UUID(session_id))
                )
                session = result.scalar_one_or_none()

                if session:
                    logger.info(f"📡 Loaded existing session {session_id[:8]}... from database")
                    # Cache it
                    await self._ensure_session_cached(str(session.id))
                    return session

                # Create new session
                # First verify agent exists
                result = await db.execute(
                    select(Agent).where(Agent.id == UUID(agent_id))
                )
                agent = result.scalar_one_or_none()
                if not agent:
                    raise ValueError(f"Agent {agent_id} not found")

                session = Session(
                    id=UUID(session_id),
                    user_id=user_id,
                    user_name=user_name,
                    agent_id=UUID(agent_id),
                    session_type=channel_type,
                    title=title,
                    active=True
                )
                db.add(session)
                await db.commit()
                await db.refresh(session)

                logger.info(
                    f"✅ Created new session {session_id[:8]}... "
                    f"(user={user_id}, agent={agent.name})"
                )

                # Cache it
                await self._ensure_session_cached(str(session.id))
                return session

        except Exception as e:
            logger.error(f"💥 Error getting/creating session {session_id[:8]}...: {e}")
            raise

    async def get_conversation_context(
        self,
        session_id: str,
        limit: int = 10,
        include_system_prompt: bool = True
    ) -> List[Message]:
        """
        Get conversation context for a session.

        Args:
            session_id: UUID string for the session
            limit: Maximum number of recent messages to return (default: 10)
            include_system_prompt: Prepend agent's system prompt (default: True)

        Returns:
            List[Message]: Recent conversation history in chronological order (oldest→newest)

        Note:
            - Returns empty list if session not found (graceful degradation)
            - System prompt is inserted as first message if include_system_prompt=True
            - Messages are in chronological order (oldest first, newest last)
            - ✅ FIX: Messages are now loaded from DB in ASC order to match append() behavior
        """
        try:
            # Ensure session is cached
            cached = await self._ensure_session_cached(session_id)

            async with cached.lock:
                # Update activity
                cached.last_activity = datetime.utcnow()
                cached.expires_at = cached.last_activity + self._cache_ttl

                # Build message list
                messages = []

                # Add system prompt if requested
                if include_system_prompt and cached.agent.system_prompt:
                    # Build system prompt with date/time awareness (user's timezone)
                    user_timezone = await self._get_user_timezone(cached.session.user_id)
                    try:
                        user_tz = ZoneInfo(user_timezone)
                    except Exception:
                        user_tz = ZoneInfo("America/Los_Angeles")

                    now = datetime.now(user_tz)
                    tz_abbrev = now.strftime('%Z')  # e.g., "PST", "EST"

                    date_context = (
                        f"\n\n[Current Date/Time Context]\n"
                        f"Today is {now.strftime('%A, %B %d, %Y')}. "
                        f"The current time is {now.strftime('%I:%M %p')} {tz_abbrev}."
                    )
                    enhanced_prompt = cached.agent.system_prompt + date_context

                    messages.append(Message(
                        id=0,  # System message placeholder (not from database)
                        session_id=session_id,
                        role="system",
                        content=enhanced_prompt,
                        timestamp=cached.session.started_at
                    ))

                # Add user memories (VoxBridge 2.0 Phase 2: Memory System)
                if self._memory_service and cached.messages:
                    # Get last user message as query for relevant memories
                    last_user_msg = next((m for m in reversed(cached.messages) if m.role == "user"), None)
                    if last_user_msg:
                        try:
                            # Log memory retrieval attempt
                            query_preview = last_user_msg.content[:100] + '...' if len(last_user_msg.content) > 100 else last_user_msg.content
                            logger.info(
                                f"🧠 Memory retrieval started: "
                                f"session={session_id[:8]}, "
                                f"user={str(cached.session.user_id)[:8]}, "
                                f"agent={str(cached.agent.id)[:8]}, "
                                f"query=\"{query_preview}\""
                            )

                            memory_context = await self._memory_service.get_user_memory_context(
                                user_id=cached.session.user_id,
                                agent_id=cached.agent.id,
                                query=last_user_msg.content,
                                limit=5
                            )

                            if memory_context:
                                # Log successful retrieval with content preview
                                context_preview = memory_context[:150] + '...' if len(memory_context) > 150 else memory_context
                                logger.info(
                                    f"🧠 Memory retrieval successful: "
                                    f"session={session_id[:8]}, "
                                    f"context_length={len(memory_context)}, "
                                    f"preview=\"{context_preview}\""
                                )

                                messages.append(Message(
                                    id=0,  # System message placeholder (not from database)
                                    session_id=session_id,
                                    role="system",
                                    content=memory_context,
                                    timestamp=datetime.utcnow()
                                ))
                                logger.info(f"✅ Injected user memories into conversation context: session={session_id[:8]}")
                            else:
                                # Log when no memories found
                                logger.info(
                                    f"🧠 Memory retrieval returned empty context: "
                                    f"session={session_id[:8]}, "
                                    f"user={str(cached.session.user_id)[:8]}, "
                                    f"agent={str(cached.agent.id)[:8]}"
                                )
                        except Exception as e:
                            logger.error(
                                f"❌ Memory retrieval failed: "
                                f"session={session_id[:8]}, "
                                f"user={str(cached.session.user_id)[:8]}, "
                                f"error={str(e)}"
                            )

                # Add conversation messages (already Message dataclasses, no conversion needed)
                # ✅ FIX: cached.messages are now in ASC order (oldest first)
                # No need to reverse - just take last N messages directly
                # ✅ cached.messages are already Message dataclasses, so no reconstruction needed
                messages.extend(cached.messages[-limit:])

                # DIAGNOSTIC: Log all messages being returned
                logger.info(f"📋 [CONVERSATION_CONTEXT] Returning {len(messages)} messages for session {session_id[:8]}:")
                for idx, msg in enumerate(messages):
                    content_preview = msg.content[:60] + '...' if len(msg.content) > 60 else msg.content
                    logger.info(f"   [{idx}] {msg.role}: \"{content_preview}\"")

                return messages

        except Exception as e:
            logger.error(f"💥 Error getting conversation context {session_id[:8]}...: {e}")
            # Graceful degradation: return empty context
            return []

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
        correlation_id: Optional[str] = None
    ) -> Message:
        """
        Add message to conversation history.

        Args:
            session_id: UUID string for the session
            role: Message role ('user', 'assistant', or 'system')
            content: Message text content
            metadata: Optional metrics (audio_duration_ms, tts_duration_ms, etc.)
            correlation_id: Optional correlation ID for end-to-end tracing

        Returns:
            Message: The added message

        Raises:
            ValueError: If session not found
        """
        metadata = metadata or {}
        import time
        import uuid

        # Generate correlation ID if not provided
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Start timing
        t_start = time.time()

        logger.info(
            f"💾 [DB_SAVE_START] Saving message "
            f"(role={role}, session={session_id[:8]}..., "
            f"length={len(content)} chars, correlation_id={correlation_id[:8]}...)"
        )

        try:
            # Ensure session is cached
            cached = await self._ensure_session_cached(session_id)

            async with cached.lock:
                # Update activity
                cached.last_activity = datetime.utcnow()
                cached.expires_at = cached.last_activity + self._cache_ttl

                # Create conversation entry
                t_db_start = time.time()
                async with get_db_session() as db:
                    # ✅ FIX: Check for duplicate messages and PREVENT insertion
                    ten_seconds_ago = datetime.utcnow() - timedelta(seconds=10)
                    existing_check = await db.execute(
                        select(Conversation)
                        .where(
                            and_(
                                Conversation.session_id == UUID(session_id),
                                Conversation.role == role,
                                Conversation.content == content,
                                Conversation.timestamp >= ten_seconds_ago
                            )
                        )
                    )
                    existing = existing_check.scalar_one_or_none()
                    if existing:
                        logger.warning(
                            f"🚫 [DB_DUPLICATE] Duplicate message detected - returning existing! "
                            f"session={session_id[:8]}..., role={role}, "
                            f"existing_id={existing.id}, existing_timestamp={existing.timestamp}"
                        )

                        # Return existing message instead of creating duplicate
                        return Message(
                            id=existing.id,
                            session_id=str(existing.session_id),
                            role=existing.role,
                            content=existing.content,
                            timestamp=existing.timestamp,
                            audio_duration_ms=existing.audio_duration_ms,
                            tts_duration_ms=existing.tts_duration_ms,
                            llm_latency_ms=existing.llm_latency_ms,
                            total_latency_ms=existing.total_latency_ms
                        )

                    # Create and insert new conversation (only if not duplicate)
                    logger.info(
                        f"💾 [DB_INSERT] Inserting message: session={session_id[:8]}..., "
                        f"role={role}, length={len(content)} chars"
                    )

                    conversation = Conversation(
                        session_id=UUID(session_id),
                        role=role,
                        content=content,
                        audio_duration_ms=metadata.get("audio_duration_ms"),
                        tts_duration_ms=metadata.get("tts_duration_ms"),
                        llm_latency_ms=metadata.get("llm_latency_ms"),
                        total_latency_ms=metadata.get("total_latency_ms")
                    )
                    db.add(conversation)
                    await db.commit()
                    await db.refresh(conversation)

                    # Calculate database transaction duration
                    t_db_end = time.time()
                    db_duration_ms = (t_db_end - t_db_start) * 1000

                    logger.info(
                        f"✅ [DB_INSERT] Saved with id={conversation.id}, "
                        f"timestamp={conversation.timestamp}"
                    )

                # Convert ORM object to Message dataclass before adding to cache
                # This prevents SQLAlchemy DetachedInstanceError when the database session closes
                message = Message(
                    id=conversation.id,
                    session_id=str(conversation.session_id),
                    role=conversation.role,
                    content=conversation.content,
                    timestamp=conversation.timestamp,
                    audio_duration_ms=conversation.audio_duration_ms,
                    tts_duration_ms=conversation.tts_duration_ms,
                    llm_latency_ms=conversation.llm_latency_ms,
                    total_latency_ms=conversation.total_latency_ms
                )

                # Add to cache (maintain max_context limit)
                cached.messages.append(message)  # Now appends Message dataclass, not ORM object
                if len(cached.messages) > self._max_context:
                    cached.messages = cached.messages[-self._max_context:]

                # Calculate total duration
                t_end = time.time()
                total_duration_ms = (t_end - t_start) * 1000

                logger.info(
                    f"💾 [DB_SAVE_COMPLETE] Message saved "
                    f"(id={conversation.id}, role={role}, "
                    f"db_duration={db_duration_ms:.2f}ms, "
                    f"total_duration={total_duration_ms:.2f}ms, "
                    f"correlation_id={correlation_id[:8]}...)"
                )

                logger.debug(
                    f"💬 Added {role} message to session {session_id[:8]}... "
                    f"(length={len(content)} chars)"
                )

                # Queue memory extraction after assistant responses (VoxBridge 2.0 Phase 2: Memory System)
                if role == "assistant" and self._memory_service:
                    asyncio.create_task(self._queue_memory_extraction(session_id, cached, content))

                return message

        except Exception as e:
            logger.error(f"💥 Error adding message to session {session_id[:8]}...: {e}")
            raise

    async def get_agent_config(self, session_id: str) -> Agent:
        """
        Get agent configuration for a session.

        Args:
            session_id: UUID string for the session

        Returns:
            Agent: SQLAlchemy Agent model with LLM and TTS settings

        Raises:
            ValueError: If session not found
        """
        try:
            # Ensure session is cached
            cached = await self._ensure_session_cached(session_id)

            async with cached.lock:
                # Update activity
                cached.last_activity = datetime.utcnow()
                cached.expires_at = cached.last_activity + self._cache_ttl

                logger.debug(
                    f"🎤 Retrieved agent config for session {session_id[:8]}... "
                    f"(agent={cached.agent.name})"
                )
                return cached.agent

        except Exception as e:
            logger.error(f"💥 Error getting agent config for session {session_id[:8]}...: {e}")
            raise

    async def update_session_activity(self, session_id: str) -> None:
        """
        Update session activity timestamp (keepalive).

        Args:
            session_id: UUID string for the session

        Note:
            This is a lightweight operation to prevent cache expiration
            for long-running sessions with infrequent messages.
        """
        try:
            if session_id in self._cache:
                cached = self._cache[session_id]
                async with cached.lock:
                    cached.last_activity = datetime.utcnow()
                    cached.expires_at = cached.last_activity + self._cache_ttl
                    logger.debug(f"🔄 Updated activity for session {session_id[:8]}...")
        except Exception as e:
            logger.warning(f"⚠️ Error updating session activity {session_id[:8]}...: {e}")

    async def end_session(self, session_id: str, persist: bool = True) -> None:
        """
        End a conversation session.

        Args:
            session_id: UUID string for the session
            persist: If True, mark session as inactive in database (default: True)

        Note:
            - Removes session from cache immediately
            - If persist=True, updates database to set active=False and ended_at
            - If persist=False, only removes from cache (session remains active in DB)
        """
        try:
            # Remove from cache
            if session_id in self._cache:
                del self._cache[session_id]
                logger.info(f"🎤 Removed session {session_id[:8]}... from cache")

            # Update database if persisting
            if persist:
                async with get_db_session() as db:
                    await db.execute(
                        update(Session)
                        .where(Session.id == UUID(session_id))
                        .values(active=False, ended_at=datetime.utcnow())
                    )
                    await db.commit()
                    logger.info(f"✅ Ended session {session_id[:8]}... in database")

        except Exception as e:
            logger.error(f"💥 Error ending session {session_id[:8]}...: {e}")

    async def clear_cache(self, session_id: Optional[str] = None) -> None:
        """
        Clear conversation cache.

        Args:
            session_id: Optional session UUID to clear. If None, clears all cache.

        Note:
            This does not affect database records, only in-memory cache.
        """
        try:
            if session_id:
                if session_id in self._cache:
                    del self._cache[session_id]
                    logger.info(f"🔄 Cleared cache for session {session_id[:8]}...")
            else:
                count = len(self._cache)
                self._cache.clear()
                logger.info(f"🔄 Cleared all cache ({count} sessions)")

        except Exception as e:
            logger.error(f"💥 Error clearing cache: {e}")

    async def get_active_sessions(self) -> List[str]:
        """
        Get list of active session IDs currently in cache.

        Returns:
            List[str]: List of session UUID strings

        Note:
            This only returns sessions currently in cache, not all active
            sessions in the database.
        """
        return list(self._cache.keys())

    async def _get_user_timezone(self, user_id: str) -> str:
        """
        Get the user's timezone preference from the database.

        Attempts to look up user by:
        1. UUID (internal user ID)
        2. String user_id (legacy Discord/external ID)

        Args:
            user_id: User identifier (UUID string or legacy ID)

        Returns:
            str: IANA timezone string (e.g., "America/Los_Angeles")
        """
        default_tz = "America/Los_Angeles"

        if not user_id:
            return default_tz

        try:
            async with get_db_session() as db:
                # Try to find user by UUID first
                try:
                    user_uuid = UUID(user_id)
                    result = await db.execute(
                        select(User.timezone).where(User.id == user_uuid)
                    )
                    timezone = result.scalar_one_or_none()
                    if timezone:
                        return timezone
                except ValueError:
                    pass  # Not a valid UUID, try legacy lookup

                # Fallback: try legacy user_id field
                result = await db.execute(
                    select(User.timezone).where(User.user_id == user_id)
                )
                timezone = result.scalar_one_or_none()
                if timezone:
                    return timezone

                return default_tz
        except Exception as e:
            logger.debug(f"⚠️ Could not fetch user timezone: {e}")
            return default_tz

    async def _load_session_from_db(self, session_id: str) -> Optional[CachedContext]:
        """
        Load session from database and create cache entry.

        Args:
            session_id: UUID string for the session

        Returns:
            Optional[CachedContext]: Cache entry if session found, None otherwise
        """
        try:
            async with get_db_session() as db:
                # Load session with agent (eager loading)
                result = await db.execute(
                    select(Session)
                    .options(selectinload(Session.agent))
                    .where(Session.id == UUID(session_id))
                )
                session = result.scalar_one_or_none()

                if not session:
                    logger.warning(f"⚠️ Session {session_id[:8]}... not found in database")
                    return None

                # Load recent messages in ASC order (oldest first)
                # This matches the order when we append() new messages to the cache
                result = await db.execute(
                    select(Conversation)
                    .where(Conversation.session_id == UUID(session_id))
                    .order_by(Conversation.timestamp.asc())
                    .limit(self._max_context)
                )
                orm_messages = list(result.scalars().all())

                # Convert ORM objects to Message dataclasses immediately
                # This prevents SQLAlchemy DetachedInstanceError when the database session closes
                messages = [
                    Message(
                        id=msg.id,
                        session_id=str(msg.session_id),
                        role=msg.role,
                        content=msg.content,
                        timestamp=msg.timestamp,
                        audio_duration_ms=msg.audio_duration_ms,
                        tts_duration_ms=msg.tts_duration_ms,
                        llm_latency_ms=msg.llm_latency_ms,
                        total_latency_ms=msg.total_latency_ms
                    )
                    for msg in orm_messages
                ]

                # Create cache entry
                now = datetime.utcnow()
                cached = CachedContext(
                    session=session,
                    agent=session.agent,
                    messages=messages,  # Now stores Message dataclasses, not ORM objects
                    last_activity=now,
                    expires_at=now + self._cache_ttl
                )

                logger.debug(
                    f"📡 Loaded session {session_id[:8]}... from DB "
                    f"({len(messages)} messages)"
                )

                return cached

        except Exception as e:
            logger.error(f"💥 Error loading session {session_id[:8]}... from DB: {e}")
            return None

    async def _queue_memory_extraction(
        self,
        session_id: str,
        cached: CachedContext,
        ai_response: str
    ) -> None:
        """
        Queue memory extraction for a conversation turn (VoxBridge 2.0 Phase 2: Memory System).

        Args:
            session_id: Session ID
            cached: Cached context with messages
            ai_response: The AI response just added

        Note:
            - Finds the most recent user message
            - Queues extraction task (non-blocking)
            - Gracefully degrades on errors
        """
        try:
            # Find most recent user message
            recent_user_msg = next(
                (m for m in reversed(cached.messages) if m.role == "user"),
                None
            )

            if not recent_user_msg:
                logger.debug(f"🧠 No user message found for extraction (session {session_id[:8]})")
                return

            # Queue extraction task
            task_id = await self._memory_service.queue_extraction(
                user_id=cached.session.user_id,
                agent_id=cached.agent.id,
                user_message=recent_user_msg.content,
                ai_response=ai_response
            )

            logger.info(
                f"🧠 Queued memory extraction task {task_id} for session {session_id[:8]} "
                f"(user_id={cached.session.user_id})"
            )

        except Exception as e:
            logger.error(f"❌ Failed to queue memory extraction for session {session_id[:8]}: {e}")

    async def _cleanup_expired_cache(self) -> None:
        """
        Background task to remove expired cache entries.

        Runs every CACHE_CLEANUP_INTERVAL_SECONDS seconds.
        Removes entries where datetime.utcnow() > expires_at.
        """
        logger.info(f"🔄 Cache cleanup task started (interval: {CACHE_CLEANUP_INTERVAL_SECONDS}s)")

        while self._running:
            try:
                await asyncio.sleep(CACHE_CLEANUP_INTERVAL_SECONDS)

                now = datetime.utcnow()
                expired = []

                for session_id, cached in list(self._cache.items()):
                    if now > cached.expires_at:
                        expired.append(session_id)

                for session_id in expired:
                    del self._cache[session_id]

                if expired:
                    logger.info(
                        f"🔄 Cleaned up {len(expired)} expired sessions from cache "
                        f"({len(self._cache)} remaining)"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"💥 Error in cache cleanup task: {e}")

        logger.info("✅ Cache cleanup task stopped")

    async def _ensure_session_cached(self, session_id: str) -> CachedContext:
        """
        Ensure session is in cache, loading from database if needed.

        Args:
            session_id: UUID string for the session

        Returns:
            CachedContext: Cache entry for the session

        Raises:
            ValueError: If session not found in database
        """
        # Check cache first
        if session_id in self._cache:
            return self._cache[session_id]

        # Load from database
        cached = await self._load_session_from_db(session_id)
        if not cached:
            raise ValueError(f"Session {session_id} not found")

        # Add to cache
        self._cache[session_id] = cached
        return cached
