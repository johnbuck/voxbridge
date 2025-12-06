"""
Authentication Dependencies

FastAPI dependencies for JWT-based authentication and role-based access control.
"""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, UserRole
from src.database.session import get_db_session
from src.services.auth_service import get_auth_service

logger = logging.getLogger(__name__)

# HTTP Bearer token extractor
security = HTTPBearer(auto_error=True)
optional_security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> User:
    """
    Dependency to get the current authenticated user.

    Extracts JWT from Authorization header, validates it, and returns the user.

    Raises:
        HTTPException 401: If token is missing, invalid, or expired
        HTTPException 401: If user not found or inactive

    Usage:
        @router.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"message": f"Hello {user.username}!"}
    """
    auth_service = get_auth_service()
    token = credentials.credentials

    # Decode and validate token
    payload = auth_service.decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    async with get_db_session() as db:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(optional_security)],
) -> User | None:
    """
    Dependency to get the current user if authenticated, None otherwise.

    Useful for endpoints that behave differently for authenticated vs anonymous users.

    Usage:
        @router.get("/public")
        async def public_route(user: User | None = Depends(get_optional_user)):
            if user:
                return {"message": f"Hello {user.username}!"}
            return {"message": "Hello anonymous!"}
    """
    if not credentials:
        return None

    auth_service = get_auth_service()
    token = credentials.credentials

    payload = auth_service.decode_token(token)
    if not payload or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    async with get_db_session() as db:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Dependency to require admin role.

    Chains with get_current_user to first authenticate, then check role.

    Raises:
        HTTPException 403: If user is not an admin

    Usage:
        @router.post("/admin-only")
        async def admin_route(user: User = Depends(require_admin)):
            return {"message": "Admin access granted!"}
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
