"""
Admin Routes

Admin-only endpoints for user management and system administration.
"""

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, UserRole, UserFact
from src.database.session import get_db_session
from src.dependencies.auth import require_admin
from src.services.auth_service import get_auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


# =============================================================================
# Request/Response Models
# =============================================================================


class UserListResponse(BaseModel):
    """Response model for user list."""
    id: str
    email: str | None
    username: str | None
    display_name: str | None
    role: str
    is_active: bool
    memory_extraction_enabled: bool
    created_at: datetime
    last_login_at: datetime | None
    facts_count: int = 0

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request model for updating a user."""
    role: str | None = Field(None, pattern="^(admin|user)$")
    is_active: bool | None = None
    display_name: str | None = Field(None, max_length=100)


class UserStatsResponse(BaseModel):
    """Response model for user statistics."""
    total_users: int
    active_users: int
    admin_count: int
    users_with_facts: int


class ResetPasswordRequest(BaseModel):
    """Request model for resetting a user's password."""
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password (minimum 8 characters)"
    )


class MessageResponse(BaseModel):
    """Simple message response."""
    message: str


# =============================================================================
# Admin User Endpoints
# =============================================================================


@router.get("/users", response_model=list[UserListResponse])
async def list_users(
    admin: Annotated[User, Depends(require_admin)],
):
    """
    List all users with their fact counts.

    Admin-only endpoint.
    """
    async with get_db_session() as db:
        # Get users with fact counts via subquery
        fact_count_subq = (
            select(UserFact.user_id, func.count(UserFact.id).label('facts_count'))
            .group_by(UserFact.user_id)
            .subquery()
        )

        result = await db.execute(
            select(
                User,
                func.coalesce(fact_count_subq.c.facts_count, 0).label('facts_count')
            )
            .outerjoin(fact_count_subq, User.id == fact_count_subq.c.user_id)
            .order_by(User.created_at.desc())
        )
        rows = result.all()

        users = []
        for row in rows:
            user = row[0]
            facts_count = row[1]
            users.append(UserListResponse(
                id=str(user.id),
                email=user.email,
                username=user.username,
                display_name=user.display_name,
                role=user.role.value if user.role else 'user',
                is_active=user.is_active,
                memory_extraction_enabled=user.memory_extraction_enabled,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
                facts_count=facts_count,
            ))

        logger.info(f"📋 Admin {admin.username} listed {len(users)} users")
        return users


@router.get("/users/stats", response_model=UserStatsResponse)
async def get_user_stats(
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Get user statistics.

    Admin-only endpoint.
    """
    async with get_db_session() as db:
        # Total users
        total_result = await db.execute(select(func.count(User.id)))
        total_users = total_result.scalar() or 0

        # Active users
        active_result = await db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        active_users = active_result.scalar() or 0

        # Admin count
        admin_result = await db.execute(
            select(func.count(User.id)).where(User.role == UserRole.ADMIN)
        )
        admin_count = admin_result.scalar() or 0

        # Users with facts
        users_with_facts_result = await db.execute(
            select(func.count(func.distinct(UserFact.user_id)))
        )
        users_with_facts = users_with_facts_result.scalar() or 0

        return UserStatsResponse(
            total_users=total_users,
            active_users=active_users,
            admin_count=admin_count,
            users_with_facts=users_with_facts,
        )


@router.get("/users/{user_id}", response_model=UserListResponse)
async def get_user(
    user_id: UUID,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Get a specific user by ID.

    Admin-only endpoint.
    """
    async with get_db_session() as db:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Get fact count
        fact_result = await db.execute(
            select(func.count(UserFact.id)).where(UserFact.user_id == user_id)
        )
        facts_count = fact_result.scalar() or 0

        return UserListResponse(
            id=str(user.id),
            email=user.email,
            username=user.username,
            display_name=user.display_name,
            role=user.role.value if user.role else 'user',
            is_active=user.is_active,
            memory_extraction_enabled=user.memory_extraction_enabled,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            facts_count=facts_count,
        )


@router.patch("/users/{user_id}", response_model=UserListResponse)
async def update_user(
    user_id: UUID,
    request: UserUpdateRequest,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Update a user's role, status, or display name.

    Admin-only endpoint.
    """
    async with get_db_session() as db:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Prevent admin from demoting themselves
        if user.id == admin.id and request.role == 'user':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote yourself from admin"
            )

        # Prevent admin from deactivating themselves
        if user.id == admin.id and request.is_active == False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate your own account"
            )

        # Apply updates
        if request.role is not None:
            user.role = UserRole(request.role)
        if request.is_active is not None:
            user.is_active = request.is_active
        if request.display_name is not None:
            user.display_name = request.display_name

        await db.commit()
        await db.refresh(user)

        # Get fact count
        fact_result = await db.execute(
            select(func.count(UserFact.id)).where(UserFact.user_id == user_id)
        )
        facts_count = fact_result.scalar() or 0

        logger.info(f"👤 Admin {admin.username} updated user {user.username}: role={user.role.value}, is_active={user.is_active}")

        return UserListResponse(
            id=str(user.id),
            email=user.email,
            username=user.username,
            display_name=user.display_name,
            role=user.role.value if user.role else 'user',
            is_active=user.is_active,
            memory_extraction_enabled=user.memory_extraction_enabled,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            facts_count=facts_count,
        )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Delete a user and all their data.

    Admin-only endpoint. Cannot delete yourself.
    """
    async with get_db_session() as db:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Prevent admin from deleting themselves
        if user.id == admin.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )

        username = user.username
        await db.delete(user)
        await db.commit()

        logger.warning(f"🗑️ Admin {admin.username} deleted user {username}")

        return {"message": f"User {username} deleted successfully"}


@router.post("/users/{user_id}/reset-password", response_model=MessageResponse)
async def reset_user_password(
    user_id: UUID,
    request: ResetPasswordRequest,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Reset a user's password.

    Admin-only endpoint. Cannot reset your own password via this endpoint
    (use /api/auth/change-password instead).

    Args:
        user_id: Target user's UUID
        request: New password
        admin: Current admin user (from JWT)

    Returns:
        Success message

    Raises:
        400: Trying to reset own password
        404: User not found
    """
    # Prevent admin from resetting their own password via this endpoint
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reset your own password via admin endpoint. Use /api/auth/change-password instead."
        )

    auth_service = get_auth_service()

    async with get_db_session() as db:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Hash and update password
        user.password_hash = auth_service.hash_password(request.new_password)
        await db.commit()

        logger.warning(f"🔑 Admin {admin.username} reset password for user {user.username}")

        return MessageResponse(message=f"Password reset successfully for user {user.username}")
