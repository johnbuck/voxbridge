"""Add summarization columns to user_facts

Revision ID: 027
Revises: 026
Create Date: 2025-12-04

Phase 3: Memory Summarization - Track which facts are summaries and their source facts.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '027'
down_revision = '026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_summarized column - marks facts that are summaries of other facts
    op.add_column(
        'user_facts',
        sa.Column('is_summarized', sa.Boolean(), server_default='false', nullable=False)
    )

    # Add summarized_from column - JSONB array of original fact IDs that were summarized
    op.add_column(
        'user_facts',
        sa.Column('summarized_from', JSONB, nullable=True)
    )

    # Add index for finding summarized facts
    op.create_index(
        'idx_user_facts_is_summarized',
        'user_facts',
        ['user_id', 'is_summarized'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_user_facts_is_summarized', table_name='user_facts')
    op.drop_column('user_facts', 'summarized_from')
    op.drop_column('user_facts', 'is_summarized')
