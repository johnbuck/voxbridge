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
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func, text

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
    )  # 'openrouter' or 'local_llm' (LEGACY - use llm_provider_id instead)
    llm_model = Column(String(100), nullable=False)  # e.g., 'openai/gpt-4'
    temperature = Column(Float, nullable=False, default=0.7)

    # VoxBridge 2.0 Phase 6.5: LLM Provider Management
    # Foreign key to llm_providers table (nullable for backward compatibility)
    # Priority: database provider (llm_provider_id) > env var provider (OPENROUTER_API_KEY)
    llm_provider_id = Column(
        UUID(as_uuid=True),
        ForeignKey("llm_providers.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # TTS Configuration - Aligned with Chatterbox TTS API
    tts_voice = Column(String(100), nullable=True)  # Voice ID/name for Chatterbox
    tts_exaggeration = Column(Float, nullable=False, default=1.0)  # Emotion intensity (0.25-2.0)
    tts_cfg_weight = Column(Float, nullable=False, default=0.7)  # Pace control (0.0-1.0)
    tts_temperature = Column(Float, nullable=False, default=0.3)  # Sampling randomness (0.05-5.0)
    tts_language = Column(String(10), nullable=False, default="en")  # Language code

    # TTS Action Filtering - Remove roleplay actions before synthesis
    filter_actions_for_tts = Column(Boolean, nullable=False, default=False)
    """
    Remove roleplay actions (*text*) from LLM responses before TTS synthesis.
    When enabled, asterisk-wrapped actions are filtered to prevent TTS from
    speaking unnatural action descriptions. Original text is preserved in
    conversation history. Math expressions like 2*3*4 are preserved.

    Default: False (opt-in per agent)
    """

    # VoxBridge 2.0 Phase 3: LLM Routing (DEPRECATED - use plugins instead)
    use_n8n = Column(Boolean, nullable=False, default=False)  # Use n8n webhook instead of direct LLM
    n8n_webhook_url = Column(String(500), nullable=True)  # Per-agent n8n webhook URL

    # VoxBridge 2.0 Phase 5: Default Agent Selection
    is_default = Column(Boolean, nullable=False, default=False, index=True)  # Mark as default agent

    # VoxBridge 2.0 Phase 6: Plugin System
    plugins = Column(JSONB, nullable=False, default={})  # Plugin configurations (discord, n8n, slack, etc.)

    # Voice Configuration
    max_utterance_time_ms = Column(Integer, nullable=True, default=120000)  # Max duration per speaking turn (ms)

    # Memory System Configuration (Phase 1: Memory System)
    memory_scope = Column(String(20), server_default='global')  # 'global' (shared across agents) or 'agent' (agent-specific)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active = Column(Boolean, default=True)

    # Relationships
    sessions = relationship("Session", back_populates="agent", cascade="all, delete-orphan")
    llm_provider_ref = relationship("LLMProvider", foreign_keys=[llm_provider_id])

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
    title = Column(String(200), nullable=True)  # Conversation title (auto-generated or user-set)

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

    # Discord Integration (Phase 6.X: Unified Conversation Threading)
    # Tracks which Discord guild is currently linked to this session
    # Allows Discord voice input and web input to share same conversation thread
    # One session per guild at a time (guild isolation), but multiple sessions per guild over time
    discord_guild_id = Column(String(100), nullable=True, index=True)  # Discord guild (server) ID if linked

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


class LLMProvider(Base):
    """
    LLM Provider Configuration

    Stores OpenAI-compatible API endpoint configurations for flexible LLM routing.
    Supports multiple provider types: OpenRouter, Ollama, OpenAI, vLLM, custom.

    Phase 6.5.4: LLM Provider Management System
    - Providers are OpenAI-compatible API endpoints
    - API keys are encrypted before storing in database
    - Models are fetched from /v1/models and cached as JSONB array
    - Agents can reference providers for flexible LLM routing
    """

    __tablename__ = "llm_providers"

    # Primary key - UUID for global uniqueness
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))

    # Provider Identity
    name = Column(String(255), nullable=False)
    base_url = Column(String(512), nullable=False)

    # Authentication (encrypted)
    api_key_encrypted = Column(Text, nullable=True)

    # Provider Type (openrouter, ollama, openai, vllm, custom)
    provider_type = Column(String(50), nullable=True, index=True)

    # Model Configuration
    models = Column(JSONB, server_default='[]')  # List of available models
    default_model = Column(String(255), nullable=True)

    # Status
    is_active = Column(Boolean, server_default=text('true'), index=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<LLMProvider(id={self.id}, name='{self.name}', provider_type='{self.provider_type}')>"


class User(Base):
    """
    User Model for Memory Personalization

    Stores user identity and memory preferences.
    Supports both Discord users (permanent IDs) and WebRTC users (token-based auth).

    Phase 1: Memory System
    - user_id: "discord_{snowflake}" or "webrtc_{random}"
    - memory_extraction_enabled: Opt-in (GDPR-compliant)
    - auth_token: For WebRTC users only (Discord uses snowflake IDs)
    """

    __tablename__ = "users"

    # Primary key - UUID for global uniqueness
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    # User Identity
    user_id = Column(String(255), unique=True, nullable=False, index=True)  # Discord ID or WebRTC session
    display_name = Column(String(255), nullable=True)

    # Memory Configuration
    embedding_provider = Column(String(50), server_default='azure')  # 'azure' or 'local'
    memory_extraction_enabled = Column(Boolean, server_default=text('false'))  # Opt-in (GDPR)
    allow_agent_specific_memory = Column(Boolean, server_default=text('true'))  # When False: forces all facts to global, deletes existing agent-specific facts

    # Authentication (WebRTC users only)
    auth_token = Column(String(255), unique=True, nullable=True, index=True)  # JWT or random token
    token_created_at = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    facts = relationship("UserFact", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, user_id='{self.user_id}', display_name='{self.display_name}')>"


class UserFact(Base):
    """
    User Fact Model (Metadata for Mem0 Memory System)

    Stores relational metadata for facts in Mem0 vector database.
    Complements vector storage with structured data for SQL queries.

    Phase 1: Memory System
    - user_id: Foreign key to users table
    - agent_id: NULL = global fact, otherwise agent-specific
    - vector_id: References Mem0 memory ID for sync
    - validity_start/end: Temporal validity tracking
    """

    __tablename__ = "user_facts"

    # Primary key - UUID for global uniqueness
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    # Associations
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True)  # NULL = global

    # Fact Data
    fact_key = Column(String(100), nullable=False)  # 'name', 'location', 'preferences', etc.
    fact_value = Column(Text, nullable=False)       # Raw value
    fact_text = Column(Text, nullable=False)        # Natural language fact
    importance = Column(Float, server_default='0.5')  # 0.0-1.0 importance score

    # Vector Store Sync
    vector_id = Column(String(255), unique=True, nullable=False, index=True)  # Vector store memory ID (managed by Mem0)
    embedding_provider = Column(String(50), nullable=False)  # Which embedder was used
    embedding_model = Column(String(100), nullable=True)     # Model name (e.g., 'text-embedding-3-large')

    # Temporal Validity
    validity_start = Column(DateTime(timezone=True), server_default=func.now())
    validity_end = Column(DateTime(timezone=True), nullable=True)  # NULL = still valid

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="facts")
    agent = relationship("Agent")

    def __repr__(self):
        return f"<UserFact(id={self.id}, user_id={self.user_id}, fact_key='{self.fact_key}')>"


class ExtractionTask(Base):
    """
    Extraction Task Queue

    Queue for background fact extraction from conversation turns.
    Non-blocking design: Extraction happens after voice response is sent.

    Phase 1: Memory System
    - status: pending → processing → completed/failed
    - attempts: Retry up to 3 times on failure
    - error: Store error message for debugging
    """

    __tablename__ = "extraction_tasks"

    # Primary key - UUID for global uniqueness
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    # Task Data
    user_id = Column(String(255), nullable=False)  # User identifier (not FK to allow orphaned tasks)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    user_message = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)

    # Task Status
    status = Column(String(20), server_default='pending', nullable=False)  # pending, processing, completed, failed
    attempts = Column(Integer, server_default='0')
    error = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    agent = relationship("Agent")

    def __repr__(self):
        return f"<ExtractionTask(id={self.id}, user_id='{self.user_id}', status='{self.status}', attempts={self.attempts})>"


class SystemSettings(Base):
    """
    Global System Settings (VoxBridge 2.0 Phase 2)

    Stores system-wide configuration that can be modified via Admin UI.

    Fields:
    - setting_key: Unique key for the setting (e.g., 'embedding_config')
    - setting_value: JSON value of the setting
    - updated_at: Timestamp of last update
    - updated_by: User who last updated (for future admin tracking)

    Current Settings:
    - embedding_config: Global embedding provider configuration
      {
        "provider": "azure" | "local",
        "azure_api_key": "...",  # Encrypted
        "azure_endpoint": "https://...",
        "azure_deployment": "text-embedding-3-large",
        "model": "sentence-transformers/all-mpnet-base-v2",
        "dims": 768
      }

    Configuration Priority (matches LLM provider pattern):
    1. Database (this table) - Highest priority
    2. Environment variables (.env)
    3. Hardcoded defaults in code

    NOTE: Settings UI will be restricted to admin-only access in a future phase.
    """

    __tablename__ = "system_settings"

    # Primary key - UUID for global uniqueness
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    # Setting Data
    setting_key = Column(String(100), unique=True, nullable=False, index=True)
    setting_value = Column(JSONB, nullable=False)  # Flexible JSON storage

    # Metadata
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(255), nullable=True)  # For future admin tracking

    def __repr__(self):
        return f"<SystemSettings(key='{self.setting_key}', value={self.setting_value})>"
