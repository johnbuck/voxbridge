"""create extraction queue table

Revision ID: 016
Revises: 015
Create Date: 2025-11-21 00:04:00.000000

Description:
    Add extraction_tasks table for queue-based fact extraction.

    Design:
    - Non-blocking: Extraction happens in background worker (doesn't delay voice responses)
    - Retry logic: Up to 3 attempts per task with error tracking
    - Status tracking: pending → processing → completed/failed

    Also adds memory_scope column to agents table:
    - 'global': Memories shared across all agents (default)
    - 'agent': Memories scoped to specific agent only

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create extraction_tasks queue table and add memory_scope to agents.

    extraction_tasks: Queue for background fact extraction
    agents.memory_scope: Control memory sharing (global vs agent-specific)
    """
    # Extraction task queue
    op.create_table(
        'extraction_tasks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_message', sa.Text, nullable=False),
        sa.Column('ai_response', sa.Text, nullable=False),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),  # pending, processing, completed, failed
        sa.Column('attempts', sa.Integer, server_default='0'),
        sa.Column('error', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index('idx_extraction_tasks_status', 'extraction_tasks', ['status', 'attempts'])
    op.create_index('idx_extraction_tasks_created', 'extraction_tasks', ['created_at'])

    # Add memory_scope column to agents table
    op.add_column('agents', sa.Column('memory_scope', sa.String(20), server_default='global'))
    # Values: 'global' (shared across agents) or 'agent' (agent-specific memories)

    print("✅ Created extraction_tasks queue table and added memory_scope to agents")


def downgrade() -> None:
    """
    Drop extraction_tasks table and remove memory_scope from agents.

    Warning: This will delete all pending extraction tasks.
    """
    op.drop_column('agents', 'memory_scope')
    op.drop_table('extraction_tasks')

    print("⚠️ Dropped extraction_tasks table and removed memory_scope from agents")
