"""Add user authentication fields

Revision ID: 028
Revises: 027
Create Date: 2025-12-05

Adds authentication fields to users table for JWT-based auth:
- email: Unique email for login
- username: Unique username for login
- password_hash: bcrypt hashed password
- role: User role enum (admin, user)
- is_active: Account status

Also makes user_id nullable (for users who register via email/password).
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = '028'
down_revision = '027'
branch_labels = None
depends_on = None


def upgrade():
    # Create the UserRole enum type
    op.execute("CREATE TYPE userrole AS ENUM ('admin', 'user')")

    # Add new authentication columns
    op.add_column('users', sa.Column('email', sa.String(255), unique=True, nullable=True))
    op.add_column('users', sa.Column('username', sa.String(100), unique=True, nullable=True))
    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('role', sa.Enum('admin', 'user', name='userrole'), server_default='user', nullable=False))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False))

    # Make user_id nullable (for users who register via email/password without Discord)
    op.alter_column('users', 'user_id', nullable=True)

    # Create indexes for efficient lookups
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_username', 'users', ['username'])


def downgrade():
    # Drop indexes
    op.drop_index('ix_users_username', table_name='users')
    op.drop_index('ix_users_email', table_name='users')

    # Make user_id NOT NULL again (may fail if NULL values exist)
    op.alter_column('users', 'user_id', nullable=False)

    # Drop columns
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'role')
    op.drop_column('users', 'password_hash')
    op.drop_column('users', 'username')
    op.drop_column('users', 'email')

    # Drop the enum type
    op.execute("DROP TYPE userrole")
