"""create system_settings table

Revision ID: 018
Revises: 017
Create Date: 2025-11-22

VoxBridge 2.0 Phase 2: Global System Settings
- Create system_settings table for global configuration
- Add embedding_config setting with local defaults
- Supports future admin-only settings
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON, TIMESTAMP

# revision identifiers, used by Alembic.
revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create system_settings table for global configuration."""

    # Create system_settings table
    op.create_table(
        'system_settings',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('setting_key', sa.String(100), unique=True, nullable=False),
        sa.Column('setting_value', JSON, nullable=False),
        sa.Column('updated_at', TIMESTAMP(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.Column('updated_by', sa.String(255), nullable=True),  # For future admin tracking
    )

    # Create index on setting_key for faster lookups
    op.create_index('ix_system_settings_setting_key', 'system_settings', ['setting_key'], unique=True)

    # Insert default embedding config (uses local embeddings by default)
    op.execute(
        """
        INSERT INTO system_settings (setting_key, setting_value, updated_at)
        VALUES (
            'embedding_config',
            '{"provider": "local", "model": "sentence-transformers/all-mpnet-base-v2", "dims": 768}'::jsonb,
            NOW()
        )
        """
    )

    print("✅ Created system_settings table with default local embedding config")


def downgrade() -> None:
    """Drop system_settings table."""
    op.drop_index('ix_system_settings_setting_key', 'system_settings')
    op.drop_table('system_settings')
    print("⚠️ Dropped system_settings table")
