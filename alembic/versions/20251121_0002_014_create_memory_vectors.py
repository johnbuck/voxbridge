"""create memory vectors table placeholder

Revision ID: 014
Revises: 013
Create Date: 2025-11-21 00:02:00.000000

Description:
    Placeholder migration for memory vector table creation.

    Note: Mem0 framework automatically manages vector table creation
    and indexing via pgvector/pgvectorscale. This migration is a
    placeholder for reference and manual intervention if needed.

    Mem0 creates tables like:
    - user_memories (collection_name configured in Mem0 config)
    - Columns: id, user_id, memory, hash, metadata, created_at, updated_at
    - Vector column with pgvectorscale StreamingDiskANN index

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Placeholder for vector table creation.

    Mem0 manages vector table creation automatically when initialized.
    No manual SQL needed here.

    To verify Mem0 tables after initialization:
        docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "\\dt"
    """
    # Mem0 will create tables automatically
    print("ℹ️ Vector tables will be created by Mem0 framework on first initialization")
    pass


def downgrade() -> None:
    """
    Placeholder for vector table cleanup.

    Note: Mem0 manages vector tables. Only drop if manually created outside Mem0.
    """
    # Mem0 manages vector tables
    print("ℹ️ Vector tables managed by Mem0 framework (no manual cleanup needed)")
    pass
