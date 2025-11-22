"""add memory system tables

Revision ID: 015
Revises: 014
Create Date: 2025-11-21 00:03:00.000000

Description:
    Add memory system tables for user personalization:
    - users: User identity and memory preferences
    - user_facts: Extracted facts metadata (complements Mem0 vector storage)

    Design:
    - users.user_id: "discord_{snowflake}" or "webrtc_{random}"
    - user_facts: Relational metadata for facts stored in Mem0 vector DB
    - user_facts.vector_id: References Mem0 memory ID for sync

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create users and user_facts tables for memory system.

    users table: User identity and preferences
    user_facts table: Metadata for Mem0-managed facts (relational complement to vector storage)
    """
    # Users table (for memory personalization)
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.String(255), unique=True, nullable=False),  # Discord ID or WebRTC session
        sa.Column('display_name', sa.String(255)),
        sa.Column('embedding_provider', sa.String(50), server_default='azure'),  # 'azure' or 'local'
        sa.Column('memory_extraction_enabled', sa.Boolean, server_default=sa.text('false')),  # Opt-in (GDPR)
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())
    )
    op.create_index('idx_users_user_id', 'users', ['user_id'])

    # User facts table (metadata for Mem0 memory system)
    op.create_table(
        'user_facts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=True),  # NULL = global
        sa.Column('fact_key', sa.String(100), nullable=False),  # 'name', 'location', 'preferences', etc.
        sa.Column('fact_value', sa.Text, nullable=False),       # Raw value
        sa.Column('fact_text', sa.Text, nullable=False),        # Natural language fact
        sa.Column('importance', sa.Float, server_default='0.5'),  # 0.0-1.0 importance score
        sa.Column('vector_id', sa.String(255), unique=True, nullable=False),  # Vector store memory ID (managed by Mem0)
        sa.Column('embedding_provider', sa.String(50), nullable=False),  # Which embedder was used
        sa.Column('embedding_model', sa.String(100)),           # Model name (e.g., 'text-embedding-3-large')
        sa.Column('validity_start', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('validity_end', sa.DateTime(timezone=True), nullable=True),  # NULL = still valid
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('user_id', 'fact_key', 'agent_id', name='uq_user_fact_key_agent')
    )
    op.create_index('idx_user_facts_user_id', 'user_facts', ['user_id'])
    op.create_index('idx_user_facts_agent_id', 'user_facts', ['agent_id'])
    op.create_index('idx_user_facts_validity', 'user_facts', ['validity_start', 'validity_end'])
    op.create_index('idx_user_facts_vector_id', 'user_facts', ['vector_id'])

    print("✅ Created users and user_facts tables for memory system")


def downgrade() -> None:
    """
    Drop users and user_facts tables.

    Warning: This will delete all user data and memory metadata.
    Vector data in Mem0 will remain orphaned until manually cleaned.
    """
    op.drop_table('user_facts')
    op.drop_table('users')

    print("⚠️ Dropped users and user_facts tables (memory system disabled)")
