"""add discord_guild_id to sessions

Revision ID: 007
Revises: 006
Create Date: 2025-10-29 16:00:00.000000

Phase 6.X: Unified Conversation Threading
- Add discord_guild_id to sessions table for linking Discord voice to web conversations
- Allows Discord voice input and web interface input to share same conversation thread
- One active session per guild at a time (guild isolation)

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add discord_guild_id column to sessions table
    op.add_column('sessions', sa.Column('discord_guild_id', sa.String(length=100), nullable=True))

    # Create index on discord_guild_id for fast lookup
    op.create_index(
        'ix_sessions_discord_guild_id',
        'sessions',
        ['discord_guild_id'],
        unique=False
    )


def downgrade() -> None:
    # Drop index first
    op.drop_index('ix_sessions_discord_guild_id', table_name='sessions')

    # Drop column
    op.drop_column('sessions', 'discord_guild_id')
