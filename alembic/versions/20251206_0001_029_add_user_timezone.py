"""Add user timezone preference

Revision ID: 029
Revises: 028
Create Date: 2025-12-06

Adds timezone column to users table for timezone-aware date/time display.
Uses IANA timezone identifiers (e.g., "America/Los_Angeles", "Europe/London").
Defaults to America/Los_Angeles (Pacific Time).
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = '029'
down_revision = '028'
branch_labels = None
depends_on = None


def upgrade():
    # Add timezone column with default to Pacific Time
    op.add_column('users', sa.Column(
        'timezone',
        sa.String(50),
        server_default='America/Los_Angeles',
        nullable=False
    ))


def downgrade():
    op.drop_column('users', 'timezone')
