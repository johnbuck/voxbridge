"""add use_n8n to agents

Revision ID: 602b72a921f3
Revises: 001
Create Date: 2025-10-26 20:14:35.683549

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '602b72a921f3'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add use_n8n column to agents table
    op.add_column('agents', sa.Column('use_n8n', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # Remove use_n8n column
    op.drop_column('agents', 'use_n8n')
