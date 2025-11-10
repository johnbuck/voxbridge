"""Remove streaming config from agents (moved to TTS provider settings)

Revision ID: 010
Revises: 009
Create Date: 2025-11-03 14:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove streaming configuration columns from agents table.

    These settings are being moved to:
    1. Global defaults (environment variables)
    2. TTS provider configuration (per-provider settings)

    Reasoning: Streaming settings are infrastructure/operational parameters
    that belong with TTS configuration, not agent personality configuration.
    """
    op.drop_column('agents', 'streaming_enabled')
    op.drop_column('agents', 'streaming_min_sentence_length')
    op.drop_column('agents', 'streaming_max_concurrent_tts')
    op.drop_column('agents', 'streaming_error_strategy')
    op.drop_column('agents', 'streaming_interruption_strategy')


def downgrade() -> None:
    """Restore streaming configuration columns to agents table."""
    op.add_column('agents', sa.Column('streaming_enabled', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('agents', sa.Column('streaming_min_sentence_length', sa.Integer(), nullable=False, server_default='10'))
    op.add_column('agents', sa.Column('streaming_max_concurrent_tts', sa.Integer(), nullable=False, server_default='3'))
    op.add_column('agents', sa.Column('streaming_error_strategy', sa.String(20), nullable=False, server_default='retry'))
    op.add_column('agents', sa.Column('streaming_interruption_strategy', sa.String(20), nullable=False, server_default='graceful'))
