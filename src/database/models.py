"""
VoxBridge 2.0 - SQLAlchemy ORM Models

Database schema for agents, sessions, and conversations.

Design Decisions (Phase 1):
- UUID primary keys (globally unique, scalable)
- API keys from environment variables only (simple, secure)
- PostgreSQL only (Redis deferred to Phase 5)
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Text,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
    Integer,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Agent(Base):
    """
    AI Agent Configuration

    Stores agent definitions with LLM and TTS settings.
    API keys are managed via environment variables (not stored in DB).
    """

    __tablename__ = "agents"

    # Primary key - UUID for global uniqueness
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Agent Identity
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=False)

    # LLM Configuration
    llm_provider = Column(
        String(50), nullable=False
    )  # 'openrouter' or 'local_llm'
    llm_model = Column(String(100), nullable=False)  # e.g., 'openai/gpt-4'
    temperature = Column(Float, nullable=False, default=0.7)

    # TTS Configuration
    tts_voice = Column(String(100), nullable=True)  # Voice ID for Chatterbox
    tts_rate = Column(Float, nullable=False, default=1.0)  # Speech rate (0.5-2.0)
    tts_pitch = Column(Float, nullable=False, default=1.0)  # Pitch (0.5-2.0)

    # VoxBridge 2.0 Phase 3: LLM Routing
    use_n8n = Column(Boolean, nullable=False, default=False)  # Use n8n webhook instead of direct LLM

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active = Column(Boolean, default=True)

    # Relationships
    sessions = relationship("Session", back_populates="agent", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Agent(id={self.id}, name='{self.name}', llm_provider='{self.llm_provider}')>"


class Session(Base):
    """
    User Voice Session

    Represents a voice chat session with an agent.
    Replaces the global speaker lock system with session-based routing.
    """

    __tablename__ = "sessions"

    # Primary key - UUID for global uniqueness
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Session Identity
    user_id = Column(
        String(100), nullable=False, index=True
    )  # Discord user ID or web user ID
    user_name = Column(String(100), nullable=True)  # Display name for debugging

    # Agent Association
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True)
    agent = relationship("Agent", back_populates="sessions")

    # Session Status
    active = Column(Boolean, default=True, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # Session Metadata
    session_type = Column(
        String(20), nullable=False
    )  # 'web', 'discord', 'extension'
    session_metadata = Column(Text, nullable=True)  # JSON string for extension-specific data

    # Relationships
    conversations = relationship(
        "Conversation", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Session(id={self.id}, user_id='{self.user_id}', agent_id={self.agent_id}, active={self.active})>"


class Conversation(Base):
    """
    Conversation History

    Stores individual messages in a conversation for context and history.
    """

    __tablename__ = "conversations"

    # Primary key - Integer auto-increment (performance for high-volume inserts)
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Session Association
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    session = relationship("Session", back_populates="conversations")

    # Message Data
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Optional Metadata
    audio_duration_ms = Column(
        Integer, nullable=True
    )  # For user messages (STT duration)
    tts_duration_ms = Column(Integer, nullable=True)  # For assistant messages
    llm_latency_ms = Column(Integer, nullable=True)  # For assistant messages
    total_latency_ms = Column(Integer, nullable=True)  # End-to-end latency

    def __repr__(self):
        return f"<Conversation(id={self.id}, session_id={self.session_id}, role='{self.role}', timestamp={self.timestamp})>"


# Index optimizations for common queries
# These are created automatically by SQLAlchemy based on index=True parameters above:
# - agents.name (unique index for agent lookup by name)
# - sessions.user_id (index for finding user's sessions)
# - sessions.agent_id (index for finding agent's sessions)
# - sessions.active (index for finding active sessions)
# - conversations.session_id (index for conversation history queries)
# - conversations.timestamp (index for time-based queries)
