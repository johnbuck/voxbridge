"""Add is_protected column to user_facts for pruning protection

Revision ID: 026_add_is_protected
Revises: 20251204_0002_025_add_last_accessed_at
Create Date: 2025-12-04

Manual facts should never be pruned - this column marks them as protected.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_protected column with default False
    op.add_column(
        'user_facts',
        sa.Column('is_protected', sa.Boolean(), server_default='false', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('user_facts', 'is_protected')
