"""add admin memory policy to system settings

Revision ID: 022
Revises: 021
Create Date: 2025-11-25

Description:
    Add admin-level memory policy setting to system_settings table.

    NEW SETTING:
    - setting_key: 'admin_memory_policy'
    - setting_value: {
        "allow_agent_specific_memory_globally": true
      }

    BEHAVIOR:
    - When true (default): Allows agent-specific memories to be created
    - When false: Forces ALL memories to be global (agent_id = NULL) system-wide

    THREE-TIER HIERARCHY:
    1. Admin Global Policy (highest priority) - This setting
    2. Per-Agent Default (Agent.memory_scope) - Only if admin allows
    3. User Restriction (User.allow_agent_specific_memory) - Can further restrict

    PURPOSE:
    - Admin can enforce global memory policy
    - User-level settings can only restrict, not expand admin policy
    - Maintains backward compatibility (defaults to true)

    DEFAULT VALUE:
    - true (maintains current behavior - agent-specific memory allowed)

    NOTE: Admin UI will show yellow warning banner (no RBAC enforcement yet)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '022'
down_revision: Union[str, None] = '021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add admin memory policy setting to system_settings table"""

    # Insert default admin memory policy (allows agent-specific memory globally)
    op.execute(
        """
        INSERT INTO system_settings (setting_key, setting_value, updated_at)
        VALUES (
            'admin_memory_policy',
            '{"allow_agent_specific_memory_globally": true}'::jsonb,
            NOW()
        )
        ON CONFLICT (setting_key) DO NOTHING
        """
    )

    print("✅ Added admin_memory_policy setting to system_settings")
    print("   Default: allow_agent_specific_memory_globally = true (maintains current behavior)")


def downgrade() -> None:
    """Remove admin memory policy setting from system_settings table"""

    op.execute(
        """
        DELETE FROM system_settings
        WHERE setting_key = 'admin_memory_policy'
        """
    )

    print("⚠️ Removed admin_memory_policy setting from system_settings")
