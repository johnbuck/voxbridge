"""add streaming config to agents

Revision ID: 009
Revises: 008
Create Date: 2025-11-03 22:30:00.000000

Adds sentence-level streaming configuration fields to agents table
for latency optimization. These fields control how LLM responses are
processed sentence-by-sentence to reduce time-to-first-audio.

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    """Add streaming configuration fields to agents table"""

    # Add streaming_enabled column (default True for new agents)
    op.add_column(
        'agents',
        sa.Column('streaming_enabled', sa.Boolean(), nullable=False, server_default='true')
    )

    # Add streaming_min_sentence_length column (default 10 characters)
    op.add_column(
        'agents',
        sa.Column('streaming_min_sentence_length', sa.Integer(), nullable=False, server_default='10')
    )

    # Add streaming_max_concurrent_tts column (default 3 concurrent requests)
    op.add_column(
        'agents',
        sa.Column('streaming_max_concurrent_tts', sa.Integer(), nullable=False, server_default='3')
    )

    # Add streaming_error_strategy column (default 'retry')
    op.add_column(
        'agents',
        sa.Column('streaming_error_strategy', sa.String(length=20), nullable=False, server_default='retry')
    )

    # Add streaming_interruption_strategy column (default 'graceful')
    op.add_column(
        'agents',
        sa.Column('streaming_interruption_strategy', sa.String(length=20), nullable=False, server_default='graceful')
    )


def downgrade():
    """Remove streaming configuration fields from agents table"""

    op.drop_column('agents', 'streaming_interruption_strategy')
    op.drop_column('agents', 'streaming_error_strategy')
    op.drop_column('agents', 'streaming_max_concurrent_tts')
    op.drop_column('agents', 'streaming_min_sentence_length')
    op.drop_column('agents', 'streaming_enabled')
