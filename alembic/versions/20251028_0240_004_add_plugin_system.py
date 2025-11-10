"""Add plugin system with JSONB storage

Revision ID: 004
Revises: 003
Create Date: 2025-10-28 02:40:00

This migration introduces the plugin architecture for VoxBridge 2.0:
1. Adds plugins JSONB column for flexible plugin configuration
2. Migrates existing n8n config (use_n8n, n8n_webhook_url) to plugin format
3. Keeps old columns for backward compatibility (can be dropped later)

Plugin System Design:
- JSONB column stores all plugin configs: {plugin_type: config_dict}
- Schema-free: Third parties can add plugins without migrations
- Each plugin validates its own config at runtime
- Supports multiple plugin types: discord, n8n, slack, telegram, etc.

Example plugin config:
{
  "discord": {
    "enabled": true,
    "bot_token": "MTIzNDU2...",
    "channels": ["1234567890"]
  },
  "n8n": {
    "enabled": true,
    "webhook_url": "https://n8n.example.com/webhook/abc",
    "fallback_only": false
  }
}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add plugins JSONB column and migrate existing n8n config"""

    # 1. Add plugins JSONB column (default to empty object)
    op.add_column(
        'agents',
        sa.Column('plugins', postgresql.JSONB, nullable=False, server_default='{}')
    )

    # 2. Migrate existing n8n configuration to plugin format
    # This updates all agents that have n8n enabled or configured
    op.execute("""
        UPDATE agents
        SET plugins = jsonb_set(
            plugins,
            '{n8n}',
            jsonb_build_object(
                'enabled', COALESCE(use_n8n, false),
                'webhook_url', n8n_webhook_url,
                'fallback_only', false
            )
        )
        WHERE use_n8n = true OR n8n_webhook_url IS NOT NULL
    """)

    # 3. Create GIN index for fast JSONB queries (optional but recommended)
    op.execute("CREATE INDEX ix_agents_plugins_gin ON agents USING GIN (plugins)")

    # Note: We keep use_n8n and n8n_webhook_url columns for backward compatibility.
    # They can be dropped in a future migration once all code is migrated.


def downgrade() -> None:
    """Remove plugins column (keeps old n8n columns)"""

    # Drop GIN index
    op.execute("DROP INDEX IF EXISTS ix_agents_plugins_gin")

    # Drop plugins column
    op.drop_column('agents', 'plugins')

    # Note: use_n8n and n8n_webhook_url columns are preserved (not dropped in upgrade)
