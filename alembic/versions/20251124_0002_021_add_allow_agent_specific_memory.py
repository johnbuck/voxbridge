"""add allow_agent_specific_memory to users

Revision ID: 021
Revises: 020
Create Date: 2025-11-24 22:35:00.000000

Description:
    Add allow_agent_specific_memory boolean field to users table to control
    memory scoping behavior.

    BEHAVIOR:
    - When True (default): Allows agent-specific memories to be created
    - When False: Forces ALL new memories to be global (agent_id = NULL)
                  AND deletes all existing agent-specific memories for that user

    PURPOSE:
    - Gives users control over whether agents can create private memories
    - System-wide toggle (no per-agent overrides)
    - GDPR-compliant: User can force all memories to be shared/transparent

    DEFAULT VALUE:
    - True for all users (maintains current behavior)
    - Opt-in to global-only memory mode via Settings UI

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '021'
down_revision: Union[str, None] = '020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add allow_agent_specific_memory column to users table"""

    # Add the new column with default True
    op.add_column(
        'users',
        sa.Column(
            'allow_agent_specific_memory',
            sa.Boolean(),
            server_default=text('true'),
            nullable=False
        )
    )
    print("✅ Added allow_agent_specific_memory column to users table")

    # Backfill existing users with True (maintains current behavior)
    op.execute(text("""
        UPDATE users
        SET allow_agent_specific_memory = true
        WHERE allow_agent_specific_memory IS NULL
    """))
    print("✅ Backfilled existing users with allow_agent_specific_memory = true")

    # Count affected rows for verification
    result = op.get_bind().execute(text("""
        SELECT COUNT(*) FROM users WHERE allow_agent_specific_memory = true
    """))
    count = result.scalar()
    print(f"📊 Total users with agent-specific memory enabled: {count}")


def downgrade() -> None:
    """Remove allow_agent_specific_memory column from users table"""

    op.drop_column('users', 'allow_agent_specific_memory')
    print("✅ Removed allow_agent_specific_memory column from users table")
