"""Add llm_provider_id foreign key to agents table

Revision ID: 006
Revises: 005
Create Date: 2025-10-29 14:00:00

This migration links agents to llm_providers for database-backed LLM configuration.

Design Decision:
- llm_provider_id is NULLABLE to support fallback to env vars
- Priority: database provider > env var provider (OPENROUTER_API_KEY)
- Old llm_provider string field remains for backward compatibility

Migration Strategy:
1. Add llm_provider_id column (nullable)
2. Add foreign key constraint to llm_providers table
3. Create index for performance
4. Keep existing llm_provider string field for legacy support
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add llm_provider_id foreign key to agents table"""

    # Add llm_provider_id column (nullable)
    op.add_column(
        'agents',
        sa.Column('llm_provider_id', postgresql.UUID(as_uuid=True), nullable=True)
    )

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_agents_llm_provider_id',
        'agents',
        'llm_providers',
        ['llm_provider_id'],
        ['id'],
        ondelete='SET NULL'  # If provider is deleted, set agent's llm_provider_id to NULL
    )

    # Create index for performance
    op.create_index('idx_agents_llm_provider_id', 'agents', ['llm_provider_id'])


def downgrade() -> None:
    """Remove llm_provider_id foreign key from agents table"""

    # Drop index
    op.drop_index('idx_agents_llm_provider_id')

    # Drop foreign key constraint
    op.drop_constraint('fk_agents_llm_provider_id', 'agents', type_='foreignkey')

    # Drop column
    op.drop_column('agents', 'llm_provider_id')
