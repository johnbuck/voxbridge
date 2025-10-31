"""Add llm_providers table for OpenAI-compatible LLM endpoint management

Revision ID: 005
Revises: 004
Create Date: 2025-10-29 12:00:00

This migration introduces the LLM Provider management system for VoxBridge 2.0:
1. Adds llm_providers table for storing OpenAI-compatible API configurations
2. Supports multiple provider types: OpenRouter, Ollama, OpenAI, vLLM, custom
3. Encrypts API keys before storing in database
4. Stores available models as JSONB array for flexible model selection

LLM Provider Design:
- Providers are OpenAI-compatible API endpoints
- Each provider has a base_url (e.g., https://openrouter.ai/api/v1)
- API keys are encrypted using Fernet symmetric encryption
- Models are fetched from /v1/models endpoint and cached in database
- Agents can reference providers by ID for flexible LLM routing

Example provider config:
{
  "name": "OpenRouter",
  "base_url": "https://openrouter.ai/api/v1",
  "api_key_encrypted": "__encrypted__:gAAAAABf...",
  "provider_type": "openrouter",
  "models": ["anthropic/claude-3.5-sonnet", "openai/gpt-4"],
  "default_model": "anthropic/claude-3.5-sonnet",
  "is_active": true
}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add llm_providers table"""

    # Create llm_providers table
    op.create_table(
        'llm_providers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('base_url', sa.String(512), nullable=False),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('provider_type', sa.String(50), nullable=True),
        sa.Column('models', postgresql.JSONB, server_default='[]'),
        sa.Column('default_model', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now())
    )

    # Create indexes for performance
    op.create_index('idx_llm_providers_is_active', 'llm_providers', ['is_active'])
    op.create_index('idx_llm_providers_provider_type', 'llm_providers', ['provider_type'])


def downgrade() -> None:
    """Remove llm_providers table"""

    # Drop indexes
    op.drop_index('idx_llm_providers_provider_type')
    op.drop_index('idx_llm_providers_is_active')

    # Drop table
    op.drop_table('llm_providers')
