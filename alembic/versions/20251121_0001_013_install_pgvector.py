"""install pgvectorscale extension

Revision ID: 013
Revises: 012
Create Date: 2025-11-21 00:01:00.000000

Description:
    Install pgvectorscale extension for vector search in PostgreSQL.
    pgvectorscale provides StreamingDiskANN indexing for high-performance
    similarity search (11x throughput vs Qdrant).

    Prerequisites:
    - PostgreSQL 12+ (VoxBridge uses PostgreSQL 15)
    - pgvector extension (installed first)

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Install pgvector extension.

    pgvector: Core vector type and operations (REQUIRED for Mem0)

    Note: pgvectorscale is optional (performance optimization) but not included
    in standard pgvector/pgvector Docker image. Mem0 works fine with pgvector alone.
    """
    # Enable pgvector extension (REQUIRED)
    op.execute('CREATE EXTENSION IF NOT EXISTS vector;')
    print("✅ Installed pgvector extension (Mem0 vector storage enabled)")


def downgrade() -> None:
    """
    Remove pgvectorscale and pgvector extensions.

    Warning: This will drop all vector columns and indexes.
    """
    op.execute('DROP EXTENSION IF EXISTS vectorscale CASCADE;')
    op.execute('DROP EXTENSION IF EXISTS vector CASCADE;')

    print("⚠️ Removed pgvector and pgvectorscale extensions")
