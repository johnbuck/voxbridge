"""remove unique constraint on vector_id

Revision ID: 42bb34dc665e
Revises: 018
Create Date: 2025-11-23 20:12:29.828611

Description:
    Remove unique constraint on user_facts.vector_id as Mem0 can reuse vector IDs.
    The correct unique constraint is uq_user_fact_key_agent (user_id, fact_key, agent_id).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42bb34dc665e'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the incorrect unique constraint on vector_id"""
    op.drop_constraint('user_facts_vector_id_key', 'user_facts', type_='unique')
    print("✅ Dropped unique constraint on user_facts.vector_id (Mem0 can reuse vector IDs)")


def downgrade() -> None:
    """Re-add the unique constraint (not recommended)"""
    op.create_unique_constraint('user_facts_vector_id_key', 'user_facts', ['vector_id'])
    print("⚠️ Re-added unique constraint on user_facts.vector_id (may cause issues)")
