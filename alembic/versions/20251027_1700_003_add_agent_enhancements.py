"""Add agent default selection and per-agent n8n webhooks

Revision ID: 003
Revises: b2f73d54f76b
Create Date: 2025-10-27 17:00:00

This migration adds two key features:
1. Default agent selection (is_default column with unique constraint)
2. Per-agent n8n webhook URLs (n8n_webhook_url column)

Design Decisions:
- Only one agent can be marked as default at a time
- Partial unique index ensures database-level constraint
- n8n_webhook_url is optional (nullable) - falls back to global env var
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = 'b2f73d54f76b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_default column for default agent selection
    op.add_column('agents', sa.Column('is_default', sa.Boolean(),
                                      nullable=False, server_default='false'))

    # Create partial unique index to ensure only one default agent
    # PostgreSQL-specific: index only rows where is_default = true
    op.execute(
        "CREATE UNIQUE INDEX ix_agents_is_default_unique "
        "ON agents (is_default) "
        "WHERE is_default = true"
    )

    # Add n8n_webhook_url for per-agent webhook configuration
    op.add_column('agents', sa.Column('n8n_webhook_url', sa.String(500), nullable=True))


def downgrade() -> None:
    # Drop columns and index in reverse order
    op.drop_column('agents', 'n8n_webhook_url')
    op.execute("DROP INDEX IF EXISTS ix_agents_is_default_unique")
    op.drop_column('agents', 'is_default')
