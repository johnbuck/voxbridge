"""Add memory_bank column to user_facts

Revision ID: 024_add_memory_banks
Revises: 023_add_per_agent_memory_preferences
Create Date: 2025-12-04

Phase 1 of Memory System Enhancements:
- Adds memory_bank column for categorizing memories (Personal, Work, General, etc.)
- Creates index for efficient bank-based queries
- All existing facts default to 'General' bank
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add memory_bank column with default 'General'
    op.add_column(
        'user_facts',
        sa.Column('memory_bank', sa.String(50), server_default='General', nullable=False)
    )

    # Create composite index for user + bank queries
    op.create_index(
        'idx_user_facts_user_memory_bank',
        'user_facts',
        ['user_id', 'memory_bank']
    )


def downgrade() -> None:
    # Drop index first
    op.drop_index('idx_user_facts_user_memory_bank', table_name='user_facts')

    # Drop column
    op.drop_column('user_facts', 'memory_bank')
