"""Add max_utterance_time_ms to agents

Revision ID: 008_max_utterance_time
Revises: 007_add_discord_guild_id
Create Date: 2025-10-30 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    """Add max_utterance_time_ms column to agents table"""
    op.add_column('agents',
        sa.Column('max_utterance_time_ms', sa.Integer(), nullable=True, server_default='120000')
    )


def downgrade():
    """Remove max_utterance_time_ms column from agents table"""
    op.drop_column('agents', 'max_utterance_time_ms')
