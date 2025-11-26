"""fix global scope agent_ids

Revision ID: 020
Revises: 019
Create Date: 2025-11-24 00:01:00.000000

Description:
    Fix agent_id for facts where the associated agent has memory_scope='global'.

    MEMORY SCOPING DESIGN:
    - Global facts (agent_id = NULL): Shared across all agents for a user
    - Agent-specific facts (agent_id = UUID): Scoped to specific agent

    PROBLEM:
    Previous code always assigned agent_id even for global-scoped agents.
    This migration sets agent_id = NULL for facts where agent.memory_scope = 'global'.

    CORRECTED BEHAVIOR:
    - agent.memory_scope = 'global' → user_facts.agent_id = NULL
    - agent.memory_scope = 'agent' → user_facts.agent_id = agent.id

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '020'
down_revision: Union[str, None] = '019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Set agent_id = NULL for facts where agent has memory_scope='global'"""

    # Update user_facts to set agent_id = NULL where agent has memory_scope = 'global'
    op.execute(text("""
        UPDATE user_facts
        SET agent_id = NULL
        FROM agents
        WHERE user_facts.agent_id = agents.id
          AND agents.memory_scope = 'global'
    """))
    print("✅ Updated user_facts: Set agent_id = NULL for global-scoped agents")

    # Count affected rows for verification
    result = op.get_bind().execute(text("""
        SELECT COUNT(*) FROM user_facts WHERE agent_id IS NULL
    """))
    count = result.scalar()
    print(f"📊 Total global facts (agent_id = NULL): {count}")


def downgrade() -> None:
    """Restore agent_id for facts that were set to NULL (NOT recommended)"""

    # This is a data migration - downgrade would require storing previous values
    # Since all current agents are global-scoped, downgrade is not practical
    print("⚠️ Downgrade not supported for this data migration")
    print("⚠️ To restore, you would need to manually reassign agent_id values")
