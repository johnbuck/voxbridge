"""add_title_to_sessions

Revision ID: b2f73d54f76b
Revises: 602b72a921f3
Create Date: 2025-10-26 20:38:23.861528

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f73d54f76b'
down_revision: Union[str, None] = '602b72a921f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add title column to sessions table
    # Title is auto-generated from first user message or manually set
    op.add_column('sessions', sa.Column('title', sa.String(200), nullable=True))


def downgrade() -> None:
    # Remove title column
    op.drop_column('sessions', 'title')
