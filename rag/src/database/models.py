"""
VoxBridge RAG Service - Database Models

SQLAlchemy ORM models for RAG collections, documents, and chunks.
These models are a subset of the main VoxBridge models, focused on RAG functionality.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Text,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func, text

Base = declarative_base()


# Read-only models for validation (managed by main API container)

class User(Base):
    """User model (read-only, for validation)."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(String(255), unique=True, nullable=True, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    username = Column(String(100), unique=True, nullable=True, index=True)

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class Agent(Base):
    """Agent model (read-only, for validation)."""

    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = Column(String(100), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<Agent(id={self.id}, name='{self.name}')>"


# RAG-specific models

class Collection(Base):
    """
    Knowledge Collection (RAG Phase 3.1)

    Stores knowledge bases for organizing documents.
    Each collection can be shared across multiple agents via agent_collections.
    """

    __tablename__ = "collections"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    # Collection Identity
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Ownership
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    is_public = Column(Boolean, server_default=text("false"))

    # Statistics (denormalized for performance)
    document_count = Column(Integer, server_default="0")
    chunk_count = Column(Integer, server_default="0")

    # Flexible metadata (JSON) - Column mapped to 'metadata' in DB
    meta_data = Column("metadata", JSONB, server_default="{}")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    documents = relationship("Document", back_populates="collection", cascade="all, delete-orphan")
    agent_collections = relationship("AgentCollection", back_populates="collection", cascade="all, delete-orphan")

    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_collection_user_name"),
    )

    def __repr__(self):
        return f"<Collection(id={self.id}, name='{self.name}', document_count={self.document_count})>"


class Document(Base):
    """
    Document (RAG Phase 3.1)

    Stores uploaded documents (PDF, DOCX, TXT, MD) and web content.
    Documents are chunked into DocumentChunk entries for vector search.
    """

    __tablename__ = "documents"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    # Collection Association
    collection_id = Column(UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)

    # Document Identity
    filename = Column(String(500), nullable=False)
    source_type = Column(String(50), nullable=False)  # 'pdf', 'docx', 'txt', 'md', 'web', 'code'
    source_url = Column(Text, nullable=True)
    mime_type = Column(String(100), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)

    # Deduplication
    content_hash = Column(String(64), nullable=True, index=True)  # SHA-256

    # Processing Status
    chunk_count = Column(Integer, server_default="0")
    processing_status = Column(String(50), server_default="'pending'")
    processing_error = Column(Text, nullable=True)

    # Flexible metadata - Column mapped to 'metadata' in DB
    meta_data = Column("metadata", JSONB, server_default="{}")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    collection = relationship("Collection", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', status='{self.processing_status}')>"


class DocumentChunk(Base):
    """
    Document Chunk (RAG Phase 3.1)

    Stores chunked content with vector embeddings for similarity search.
    Uses pgvector for efficient vector storage and retrieval.
    """

    __tablename__ = "document_chunks"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    # Document Association
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)

    # Chunk Content
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True)

    # Position in Original Document
    start_char = Column(Integer, nullable=True)
    end_char = Column(Integer, nullable=True)
    page_number = Column(Integer, nullable=True)
    section_title = Column(String(500), nullable=True)

    # Flexible metadata - Column mapped to 'metadata' in DB
    meta_data = Column("metadata", JSONB, server_default="{}")

    # Bi-Temporal Tracking
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    valid_from = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True), nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # NOTE: embedding column (vector(1024)) is added via raw SQL in migration

    # Relationships
    document = relationship("Document", back_populates="chunks")

    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_index={self.chunk_index})>"


class AgentCollection(Base):
    """
    Agent-Collection Junction Table (RAG Phase 3.1)

    Links agents to their knowledge collections (many-to-many).
    """

    __tablename__ = "agent_collections"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    # Associations
    agent_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    collection_id = Column(UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)

    # Ordering
    priority = Column(Integer, server_default="0")

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    collection = relationship("Collection", back_populates="agent_collections")

    # Constraints
    __table_args__ = (
        UniqueConstraint("agent_id", "collection_id", name="uq_agent_collection"),
    )

    def __repr__(self):
        return f"<AgentCollection(agent_id={self.agent_id}, collection_id={self.collection_id}, priority={self.priority})>"
