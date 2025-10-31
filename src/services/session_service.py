"""
Session Service Layer

Business logic for managing voice chat sessions and conversation history.
VoxBridge 2.0 Phase 4: Web Voice Interface
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Session, Conversation, Agent
from src.database.session import get_db_session


class SessionService:
    """Service for managing chat sessions and conversation history"""

    @staticmethod
    async def create_session(
        user_id: str,
        agent_id: UUID,
        user_name: Optional[str] = None,
        title: Optional[str] = None,
        session_type: str = "web",
        session_metadata: Optional[str] = None,
    ) -> Session:
        """
        Create a new chat session.

        Args:
            user_id: User identifier (Discord ID, web session ID, etc.)
            agent_id: Agent to use for this session
            user_name: Optional display name
            title: Optional conversation title (auto-generated if not provided)
            session_type: 'web', 'discord', or 'extension'
            session_metadata: Optional JSON metadata

        Returns:
            Created Session instance

        Raises:
            ValueError: If agent_id doesn't exist
        """
        async with get_db_session() as db:
            # Verify agent exists
            result = await db.execute(select(Agent).where(Agent.id == agent_id))
            agent = result.scalar_one_or_none()
            if not agent:
                raise ValueError(f"Agent with ID {agent_id} not found")

            # Create session
            session = Session(
                user_id=user_id,
                user_name=user_name,
                agent_id=agent_id,
                title=title or "New Conversation",  # Default title
                session_type=session_type,
                session_metadata=session_metadata,
                active=True,
            )

            db.add(session)
            await db.commit()
            await db.refresh(session)

            return session

    @staticmethod
    async def get_all_sessions(
        active_only: bool = False,
        limit: int = 50,
    ) -> List[Session]:
        """
        Get all sessions across all users.

        Args:
            active_only: If True, only return active sessions
            limit: Maximum number of sessions to return

        Returns:
            List of Session instances (most recent first)
        """
        async with get_db_session() as db:
            query = select(Session)

            if active_only:
                query = query.where(Session.active == True)

            query = query.order_by(desc(Session.started_at)).limit(limit)

            result = await db.execute(query)
            sessions = result.scalars().all()
            return list(sessions)

    @staticmethod
    async def get_user_sessions(
        user_id: str,
        active_only: bool = False,
        limit: int = 50,
    ) -> List[Session]:
        """
        Get all sessions for a user.

        Args:
            user_id: User identifier
            active_only: If True, only return active sessions
            limit: Maximum number of sessions to return

        Returns:
            List of Session instances (most recent first)
        """
        async with get_db_session() as db:
            query = select(Session).where(Session.user_id == user_id)

            if active_only:
                query = query.where(Session.active == True)

            query = query.order_by(desc(Session.started_at)).limit(limit)

            result = await db.execute(query)
            sessions = result.scalars().all()
            return list(sessions)

    @staticmethod
    async def get_session(session_id: UUID) -> Optional[Session]:
        """
        Get session by ID.

        Args:
            session_id: Session UUID

        Returns:
            Session instance or None if not found
        """
        async with get_db_session() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()
            return session

    @staticmethod
    async def update_session(
        session_id: UUID,
        title: Optional[str] = None,
        active: Optional[bool] = None,
    ) -> Optional[Session]:
        """
        Update session fields.

        Args:
            session_id: Session UUID
            title: New title (optional)
            active: New active status (optional)

        Returns:
            Updated Session instance or None if not found
        """
        async with get_db_session() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()

            if not session:
                return None

            if title is not None:
                session.title = title

            if active is not None:
                session.active = active
                if not active:
                    session.ended_at = datetime.now()

            await db.commit()
            await db.refresh(session)

            return session

    @staticmethod
    async def delete_session(session_id: UUID) -> bool:
        """
        Delete session and all associated conversations.

        Args:
            session_id: Session UUID

        Returns:
            True if deleted, False if not found
        """
        async with get_db_session() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()

            if not session:
                return False

            await db.delete(session)
            await db.commit()

            return True

    @staticmethod
    async def get_session_messages(
        session_id: UUID,
        limit: Optional[int] = None,
    ) -> List[Conversation]:
        """
        Get conversation messages for a session.

        Args:
            session_id: Session UUID
            limit: Optional limit on number of messages (most recent first)

        Returns:
            List of Conversation instances (chronological order)
        """
        async with get_db_session() as db:
            query = select(Conversation).where(Conversation.session_id == session_id).order_by(Conversation.timestamp)

            if limit:
                query = query.limit(limit)

            result = await db.execute(query)
            messages = result.scalars().all()
            return list(messages)

    @staticmethod
    async def add_message(
        session_id: UUID,
        role: str,
        content: str,
        audio_duration_ms: Optional[int] = None,
        tts_duration_ms: Optional[int] = None,
        llm_latency_ms: Optional[int] = None,
        total_latency_ms: Optional[int] = None,
    ) -> Conversation:
        """
        Add a message to a session.

        Args:
            session_id: Session UUID
            role: 'user', 'assistant', or 'system'
            content: Message text
            audio_duration_ms: Optional STT duration (for user messages)
            tts_duration_ms: Optional TTS duration (for assistant messages)
            llm_latency_ms: Optional LLM latency (for assistant messages)
            total_latency_ms: Optional end-to-end latency

        Returns:
            Created Conversation instance

        Raises:
            ValueError: If role is invalid or session doesn't exist
        """
        if role not in ["user", "assistant", "system"]:
            raise ValueError(f"Invalid role: {role}. Must be 'user', 'assistant', or 'system'")

        async with get_db_session() as db:
            # Verify session exists
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()
            if not session:
                raise ValueError(f"Session with ID {session_id} not found")

            # Create conversation message
            conversation = Conversation(
                session_id=session_id,
                role=role,
                content=content,
                audio_duration_ms=audio_duration_ms,
                tts_duration_ms=tts_duration_ms,
                llm_latency_ms=llm_latency_ms,
                total_latency_ms=total_latency_ms,
            )

            db.add(conversation)
            await db.commit()
            await db.refresh(conversation)

            # Auto-generate session title from first user message (if not set)
            if not session.title or session.title == "New Conversation":
                if role == "user":
                    # Use first 50 chars of first user message as title
                    auto_title = content[:50] + ("..." if len(content) > 50 else "")
                    session.title = auto_title
                    await db.commit()

            return conversation

    @staticmethod
    async def end_session(session_id: UUID) -> Optional[Session]:
        """
        Mark session as inactive and set ended_at timestamp.

        Args:
            session_id: Session UUID

        Returns:
            Updated Session instance or None if not found
        """
        return await SessionService.update_session(session_id, active=False)
