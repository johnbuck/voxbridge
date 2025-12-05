"""Add last_accessed_at column for LRU pruning strategy

Revision ID: 025
Revises: 024
Create Date: 2025-12-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '025'
down_revision: Union[str, None] = '024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add last_accessed_at column for LRU (Least Recently Used) pruning strategy
    # This tracks when a memory was last retrieved/used
    op.add_column('user_facts', sa.Column(
        'last_accessed_at',
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=True
    ))

    # Add index for efficient LRU queries (oldest accessed first)
    op.create_index(
        'idx_user_facts_last_accessed',
        'user_facts',
        ['user_id', 'last_accessed_at']
    )


def downgrade() -> None:
    op.drop_index('idx_user_facts_last_accessed', table_name='user_facts')
    op.drop_column('user_facts', 'last_accessed_at')
