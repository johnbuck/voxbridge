"""Initial schema for VoxBridge 2.0

Revision ID: 001
Revises:
Create Date: 2025-10-26 12:00:00

This migration creates the initial database schema:
- agents: AI agent configurations
- sessions: User voice sessions
- conversations: Conversation history

Design Decisions:
- UUID primary keys for agents and sessions (globally unique)
- Integer primary key for conversations (performance for high-volume inserts)
- API keys NOT stored in database (environment variables only)
- Indexes on frequently queried columns
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create agents table
    op.create_table(
        'agents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('llm_provider', sa.String(length=50), nullable=False),
        sa.Column('llm_model', sa.String(length=100), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=False),
        sa.Column('tts_voice', sa.String(length=100), nullable=True),
        sa.Column('tts_rate', sa.Float(), nullable=False),
        sa.Column('tts_pitch', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agents_name'), 'agents', ['name'], unique=True)

    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=False),
        sa.Column('user_name', sa.String(length=100), nullable=True),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('session_type', sa.String(length=20), nullable=False),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sessions_active'), 'sessions', ['active'], unique=False)
    op.create_index(op.f('ix_sessions_agent_id'), 'sessions', ['agent_id'], unique=False)
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)

    # Create conversations table
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('audio_duration_ms', sa.Integer(), nullable=True),
        sa.Column('tts_duration_ms', sa.Integer(), nullable=True),
        sa.Column('llm_latency_ms', sa.Integer(), nullable=True),
        sa.Column('total_latency_ms', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversations_session_id'), 'conversations', ['session_id'], unique=False)
    op.create_index(op.f('ix_conversations_timestamp'), 'conversations', ['timestamp'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order (to handle foreign keys)
    op.drop_index(op.f('ix_conversations_timestamp'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_session_id'), table_name='conversations')
    op.drop_table('conversations')

    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_agent_id'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_active'), table_name='sessions')
    op.drop_table('sessions')

    op.drop_index(op.f('ix_agents_name'), table_name='agents')
    op.drop_table('agents')
