"""Add per-agent memory preferences

Revision ID: 023
Revises: 022
Create Date: 2025-11-25

Creates user_agent_memory_settings table for per-agent memory control.
Enables users to configure memory scope (global vs agent-specific) on a per-agent basis.

Hierarchy (Two-Tier):
1. Admin Policy (allow_agent_specific_memory_globally) - Hard constraint from system_settings
2. Per-Agent User Preference (user_agent_memory_settings) - Falls back to Agent.memory_scope

Backwards Compatibility:
- Keeps User.allow_agent_specific_memory column for transition period
- resolve_memory_scope() function checks:
  1. Admin policy (system_settings.admin_memory_policy)
  2. Per-agent user preference (user_agent_memory_settings) - NEW
  3. Global user toggle (User.allow_agent_specific_memory) - DEPRECATED
  4. Agent default (Agent.memory_scope)

Migration Strategy:
- New table: user_agent_memory_settings
- Unique constraint: (user_id, agent_id)
- Indexes: user_id, agent_id for query performance
- Cascade delete: Remove preferences when user or agent deleted
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create user_agent_memory_settings table for per-agent memory preferences.
    """
    # Create user_agent_memory_settings table
    op.create_table(
        'user_agent_memory_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.String(255), sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('allow_agent_specific_memory', sa.Boolean, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        # Unique constraint: One preference per user-agent pair
        sa.UniqueConstraint('user_id', 'agent_id', name='uq_user_agent_memory_settings')
    )

    # Create indexes for performance
    op.create_index('idx_user_agent_memory_user', 'user_agent_memory_settings', ['user_id'])
    op.create_index('idx_user_agent_memory_agent', 'user_agent_memory_settings', ['agent_id'])

    # DO NOT drop User.allow_agent_specific_memory column yet
    # It will serve as fallback during transition period
    # Will be removed in future migration after users migrate to per-agent preferences


def downgrade():
    """
    Drop user_agent_memory_settings table.

    WARNING: This destroys all per-agent memory preferences.
    Users will fall back to global toggle (User.allow_agent_specific_memory).
    """
    op.drop_index('idx_user_agent_memory_agent', 'user_agent_memory_settings')
    op.drop_index('idx_user_agent_memory_user', 'user_agent_memory_settings')
    op.drop_table('user_agent_memory_settings')
