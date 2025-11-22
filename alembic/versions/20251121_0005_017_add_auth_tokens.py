"""add auth tokens for WebRTC users

Revision ID: 017
Revises: 016
Create Date: 2025-11-21 00:05:00.000000

Description:
    Add authentication token columns to users table for WebRTC user auth.

    Design:
    - auth_token: Secure random token (256-bit) for stateless authentication
    - token_created_at: Token creation timestamp
    - last_login_at: Track user activity

    WebRTC authentication flow:
    1. User enters name → server creates User + generates token
    2. Frontend stores token in localStorage
    3. Token sent with all WebSocket/API requests
    4. Backend validates token and retrieves user_id

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add auth_token columns to users table for WebRTC authentication.

    Fields:
    - auth_token: Random token for stateless auth (nullable for Discord users)
    - token_created_at: When token was generated
    - last_login_at: Last successful authentication
    """
    # Add auth_token column to users table
    op.add_column('users', sa.Column('auth_token', sa.String(255), unique=True, nullable=True))
    op.add_column('users', sa.Column('token_created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))

    # Create index for fast token lookup
    op.create_index('idx_users_auth_token', 'users', ['auth_token'])

    print("✅ Added auth_token columns to users table for WebRTC authentication")


def downgrade() -> None:
    """
    Remove auth_token columns from users table.

    Warning: This will invalidate all WebRTC user sessions.
    """
    op.drop_index('idx_users_auth_token')
    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'token_created_at')
    op.drop_column('users', 'auth_token')

    print("⚠️ Removed auth_token columns from users table (WebRTC auth disabled)")
