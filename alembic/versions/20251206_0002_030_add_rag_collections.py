"""add RAG knowledge collections system

Revision ID: 030
Revises: 029
Create Date: 2025-12-06

Description:
    Add tables for RAG document collections (Phase 3.1):
    - collections: Knowledge bases for organizing documents
    - documents: Uploaded documents (PDF, DOCX, TXT, MD, web)
    - document_chunks: Chunked content with vector embeddings
    - agent_collections: Many-to-many linking agents to their knowledge scope

    Architecture:
    - Each agent can access multiple collections
    - Each collection can be shared across multiple agents
    - Chunks are stored in pgvector for similarity search
    - Entity graph is maintained separately in Neo4j via Graphiti

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '030'
down_revision = '029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create tables for RAG knowledge collection system.
    """
    # Collections table (knowledge bases)
    op.create_table(
        'collections',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('is_public', sa.Boolean, server_default=sa.text('false')),  # Shared across all agents
        sa.Column('document_count', sa.Integer, server_default='0'),
        sa.Column('chunk_count', sa.Integer, server_default='0'),
        sa.Column('metadata', JSONB, server_default='{}'),  # Flexible metadata
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('user_id', 'name', name='uq_collection_user_name')
    )
    op.create_index('idx_collections_user_id', 'collections', ['user_id'])

    # Documents table (uploaded files and web content)
    op.create_table(
        'documents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('collection_id', UUID(as_uuid=True), sa.ForeignKey('collections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=False),  # 'pdf', 'docx', 'txt', 'md', 'web', 'code'
        sa.Column('source_url', sa.Text),  # For web content
        sa.Column('mime_type', sa.String(100)),
        sa.Column('file_size_bytes', sa.BigInteger),
        sa.Column('content_hash', sa.String(64)),  # SHA-256 for deduplication
        sa.Column('chunk_count', sa.Integer, server_default='0'),
        sa.Column('processing_status', sa.String(50), server_default="'pending'"),  # 'pending', 'processing', 'completed', 'failed'
        sa.Column('processing_error', sa.Text),
        sa.Column('metadata', JSONB, server_default='{}'),  # Title, author, etc.
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())
    )
    op.create_index('idx_documents_collection_id', 'documents', ['collection_id'])
    op.create_index('idx_documents_content_hash', 'documents', ['content_hash'])
    op.create_index('idx_documents_status', 'documents', ['processing_status'])

    # Document chunks table (chunked content with embeddings)
    # Note: Vector column will be added by a separate migration using raw SQL for pgvector
    op.create_table(
        'document_chunks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_index', sa.Integer, nullable=False),  # Order within document
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('token_count', sa.Integer),
        sa.Column('start_char', sa.Integer),  # Character position in original document
        sa.Column('end_char', sa.Integer),
        sa.Column('page_number', sa.Integer),  # For PDFs
        sa.Column('section_title', sa.String(500)),  # Extracted heading
        sa.Column('metadata', JSONB, server_default='{}'),
        # Temporal tracking (bi-temporal model)
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('valid_from', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('valid_until', sa.DateTime(timezone=True)),  # NULL = still valid
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )
    op.create_index('idx_document_chunks_document_id', 'document_chunks', ['document_id'])
    op.create_index('idx_document_chunks_order', 'document_chunks', ['document_id', 'chunk_index'])

    # Add vector column using raw SQL (pgvector extension)
    op.execute("""
        ALTER TABLE document_chunks
        ADD COLUMN embedding vector(1024);
    """)
    op.execute("""
        CREATE INDEX idx_document_chunks_embedding
        ON document_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """)

    # Agent-Collection junction table (many-to-many)
    op.create_table(
        'agent_collections',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('collection_id', UUID(as_uuid=True), sa.ForeignKey('collections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('priority', sa.Integer, server_default='0'),  # Higher = more relevant
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('agent_id', 'collection_id', name='uq_agent_collection')
    )
    op.create_index('idx_agent_collections_agent_id', 'agent_collections', ['agent_id'])
    op.create_index('idx_agent_collections_collection_id', 'agent_collections', ['collection_id'])

    print("Created RAG knowledge collections system (collections, documents, document_chunks, agent_collections)")


def downgrade() -> None:
    """
    Drop all RAG collection tables.

    Warning: This will delete all uploaded documents and knowledge bases.
    """
    op.drop_table('agent_collections')
    op.drop_table('document_chunks')
    op.drop_table('documents')
    op.drop_table('collections')

    print("Dropped RAG knowledge collections system")
