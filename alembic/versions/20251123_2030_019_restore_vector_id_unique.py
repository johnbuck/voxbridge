"""restore unique constraint on vector_id

Revision ID: 019
Revises: 42bb34dc665e
Create Date: 2025-11-23 20:30:00.000000

Description:
    Restore UNIQUE constraint on user_facts.vector_id.

    ARCHITECTURE CLARIFICATION:
    - user_memories (Mem0): Stores vector embeddings for semantic search
    - user_facts (VoxBridge): Stores relational metadata for CRUD/frontend
    - Relationship: 1:1 (each fact has exactly ONE vector)

    The previous migration incorrectly assumed Mem0 reuses vector IDs.
    In reality, mem0.add() creates NEW vectors with UNIQUE IDs each time.

    UNIQUE constraint ensures:
    1. Data integrity (no duplicate vector references)
    2. Safe cleanup (delete vector when fact is deleted)
    3. Proper 1:1 relationship between tables

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '019'
down_revision: Union[str, None] = '42bb34dc665e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Restore UNIQUE constraint on user_facts.vector_id"""

    # First, remove any duplicate vector_id entries (keep oldest)
    op.execute("""
        DELETE FROM user_facts a USING user_facts b
        WHERE a.id > b.id AND a.vector_id = b.vector_id AND a.vector_id IS NOT NULL
    """)
    print("🧹 Cleaned up duplicate vector_id entries")

    # Restore UNIQUE constraint
    op.create_unique_constraint('user_facts_vector_id_key', 'user_facts', ['vector_id'])
    print("✅ Restored UNIQUE constraint on user_facts.vector_id (1:1 relationship with vectors)")


def downgrade() -> None:
    """Remove the unique constraint (NOT recommended)"""
    op.drop_constraint('user_facts_vector_id_key', 'user_facts', type_='unique')
    print("⚠️ Dropped UNIQUE constraint on user_facts.vector_id (breaks 1:1 relationship)")
