"""Add filter_actions_for_tts to agents

Revision ID: 012
Revises: 011
Create Date: 2025-11-21

Description:
    Adds filter_actions_for_tts boolean field to agents table to enable
    per-agent filtering of roleplay actions (*text*) before TTS synthesis.

    Default: False (opt-in per agent)
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    """Add filter_actions_for_tts column to agents table"""
    op.add_column(
        'agents',
        sa.Column(
            'filter_actions_for_tts',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false')
        )
    )


def downgrade():
    """Remove filter_actions_for_tts column from agents table"""
    op.drop_column('agents', 'filter_actions_for_tts')
