"""
Session API Routes

FastAPI routes for managing chat sessions and conversation history.
VoxBridge 2.0 Phase 4: Web Voice Interface
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from datetime import datetime

from src.services.session_service import SessionService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SessionCreateRequest(BaseModel):
    """Request body for creating a session"""

    user_id: str = Field(..., min_length=1, max_length=100, description="User identifier")
    agent_id: str = Field(..., description="Agent UUID")
    user_name: Optional[str] = Field(None, max_length=100, description="User display name")
    title: Optional[str] = Field(None, max_length=200, description="Conversation title")
    session_type: str = Field("web", description="Session type (web, discord, extension)")
    session_metadata: Optional[str] = Field(None, description="Optional JSON metadata")


class SessionUpdateRequest(BaseModel):
    """Request body for updating a session"""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    active: Optional[bool] = None


class SessionResponse(BaseModel):
    """Response model for session data"""

    id: str
    user_id: str
    user_name: Optional[str]
    title: Optional[str]
    agent_id: str
    active: bool
    started_at: str
    ended_at: Optional[str]
    session_type: str
    session_metadata: Optional[str]
    message_count: int = 0  # Number of messages in this session

    class Config:
        from_attributes = True


class MessageRequest(BaseModel):
    """Request body for adding a message"""

    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., min_length=1, description="Message content")
    audio_duration_ms: Optional[int] = None
    tts_duration_ms: Optional[int] = None
    llm_latency_ms: Optional[int] = None
    total_latency_ms: Optional[int] = None


class MessageResponse(BaseModel):
    """Response model for conversation messages"""

    id: int
    session_id: str
    role: str
    content: str
    timestamp: str
    audio_duration_ms: Optional[int]
    tts_duration_ms: Optional[int]
    llm_latency_ms: Optional[int]
    total_latency_ms: Optional[int]

    class Config:
        from_attributes = True


# ============================================================================
# Routes
# ============================================================================

@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Session",
    description="Create a new chat session with an agent"
)
async def create_session(request: SessionCreateRequest):
    """
    Create a new session.

    Returns the created session with generated ID and timestamps.
    """
    try:
        session = await SessionService.create_session(
            user_id=request.user_id,
            agent_id=UUID(request.agent_id),
            user_name=request.user_name,
            title=request.title,
            session_type=request.session_type,
            session_metadata=request.session_metadata,
        )

        return SessionResponse(
            id=str(session.id),
            user_id=session.user_id,
            user_name=session.user_name,
            title=session.title,
            agent_id=str(session.agent_id),
            active=session.active,
            started_at=session.started_at.isoformat(),
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            session_type=session.session_type,
            session_metadata=session.session_metadata,
            message_count=0,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}"
        )


@router.get(
    "",
    response_model=List[SessionResponse],
    summary="List Sessions",
    description="Get all sessions for a user"
)
async def list_sessions(
    user_id: str,
    active_only: bool = False,
    limit: int = 50
):
    """
    Get all sessions for a user.

    Query parameters:
    - user_id: User identifier (required)
    - active_only: Only return active sessions (default: false)
    - limit: Maximum number of sessions to return (default: 50)
    """
    try:
        sessions = await SessionService.get_user_sessions(
            user_id=user_id,
            active_only=active_only,
            limit=limit
        )

        # Get message count for each session
        responses = []
        for session in sessions:
            messages = await SessionService.get_session_messages(session.id)
            responses.append(SessionResponse(
                id=str(session.id),
                user_id=session.user_id,
                user_name=session.user_name,
                title=session.title,
                agent_id=str(session.agent_id),
                active=session.active,
                started_at=session.started_at.isoformat(),
                ended_at=session.ended_at.isoformat() if session.ended_at else None,
                session_type=session.session_type,
                session_metadata=session.session_metadata,
                message_count=len(messages),
            ))

        return responses
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch sessions: {str(e)}"
        )


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get Session",
    description="Get a specific session by ID"
)
async def get_session(session_id: UUID):
    """
    Get session by ID.

    Args:
        session_id: Session UUID

    Returns:
        Session data

    Raises:
        404: Session not found
    """
    try:
        session = await SessionService.get_session(session_id)

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session with ID {session_id} not found"
            )

        # Get message count
        messages = await SessionService.get_session_messages(session.id)

        return SessionResponse(
            id=str(session.id),
            user_id=session.user_id,
            user_name=session.user_name,
            title=session.title,
            agent_id=str(session.agent_id),
            active=session.active,
            started_at=session.started_at.isoformat(),
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            session_type=session.session_type,
            session_metadata=session.session_metadata,
            message_count=len(messages),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch session: {str(e)}"
        )


@router.patch(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Update Session",
    description="Update session title or active status"
)
async def update_session(session_id: UUID, request: SessionUpdateRequest):
    """
    Update session.

    Args:
        session_id: Session UUID
        request: Fields to update (all optional)

    Returns:
        Updated session data

    Raises:
        404: Session not found
    """
    try:
        session = await SessionService.update_session(
            session_id=session_id,
            title=request.title,
            active=request.active,
        )

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session with ID {session_id} not found"
            )

        # Get message count
        messages = await SessionService.get_session_messages(session.id)

        return SessionResponse(
            id=str(session.id),
            user_id=session.user_id,
            user_name=session.user_name,
            title=session.title,
            agent_id=str(session.agent_id),
            active=session.active,
            started_at=session.started_at.isoformat(),
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            session_type=session.session_type,
            session_metadata=session.session_metadata,
            message_count=len(messages),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session: {str(e)}"
        )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Session",
    description="Delete a session and all associated messages"
)
async def delete_session(session_id: UUID):
    """
    Delete session.

    Args:
        session_id: Session UUID

    Raises:
        404: Session not found
    """
    try:
        deleted = await SessionService.delete_session(session_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session with ID {session_id} not found"
            )

        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}"
        )


@router.get(
    "/{session_id}/messages",
    response_model=List[MessageResponse],
    summary="Get Messages",
    description="Get all messages in a session"
)
async def get_session_messages(session_id: UUID, limit: Optional[int] = None):
    """
    Get messages in a session.

    Args:
        session_id: Session UUID
        limit: Optional limit on number of messages

    Returns:
        List of messages (chronological order)
    """
    try:
        messages = await SessionService.get_session_messages(session_id, limit=limit)

        return [
            MessageResponse(
                id=msg.id,
                session_id=str(msg.session_id),
                role=msg.role,
                content=msg.content,
                timestamp=msg.timestamp.isoformat(),
                audio_duration_ms=msg.audio_duration_ms,
                tts_duration_ms=msg.tts_duration_ms,
                llm_latency_ms=msg.llm_latency_ms,
                total_latency_ms=msg.total_latency_ms,
            )
            for msg in messages
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch messages: {str(e)}"
        )


@router.post(
    "/{session_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Message",
    description="Add a message to a session"
)
async def add_message(session_id: UUID, request: MessageRequest):
    """
    Add a message to a session.

    Args:
        session_id: Session UUID
        request: Message data

    Returns:
        Created message

    Raises:
        400: Invalid role
        404: Session not found
    """
    try:
        message = await SessionService.add_message(
            session_id=session_id,
            role=request.role,
            content=request.content,
            audio_duration_ms=request.audio_duration_ms,
            tts_duration_ms=request.tts_duration_ms,
            llm_latency_ms=request.llm_latency_ms,
            total_latency_ms=request.total_latency_ms,
        )

        return MessageResponse(
            id=message.id,
            session_id=str(message.session_id),
            role=message.role,
            content=message.content,
            timestamp=message.timestamp.isoformat(),
            audio_duration_ms=message.audio_duration_ms,
            tts_duration_ms=message.tts_duration_ms,
            llm_latency_ms=message.llm_latency_ms,
            total_latency_ms=message.total_latency_ms,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add message: {str(e)}"
        )
