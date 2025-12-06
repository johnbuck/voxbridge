"""
Authentication Routes

Endpoints for user registration, login, token refresh, and user info.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, UserRole
from src.database.session import get_db_session
from src.dependencies.auth import get_current_user
from src.services.auth_service import get_auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["authentication"])

# For refresh token extraction
refresh_security = HTTPBearer(auto_error=True)


# =============================================================================
# Request/Response Models
# =============================================================================


class RegisterRequest(BaseModel):
    """Request body for user registration."""

    email: EmailStr = Field(..., description="User's email address")
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Username (alphanumeric and underscores only)"
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (minimum 8 characters)"
    )
    display_name: str | None = Field(
        None,
        max_length=100,
        description="Optional display name"
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username must be alphanumeric (underscores allowed)")
        return v.lower()  # Normalize to lowercase


class LoginRequest(BaseModel):
    """Request body for user login."""

    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")


class TokenResponse(BaseModel):
    """Response containing JWT tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token expiry in seconds")


class UserResponse(BaseModel):
    """Response containing user information."""

    id: str
    email: str | None
    username: str | None
    display_name: str | None
    role: str
    is_active: bool
    memory_extraction_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


# =============================================================================
# Auth Endpoints
# =============================================================================


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """
    Register a new user account.

    Creates a new user with email/password credentials and returns JWT tokens.
    The first registered user is automatically assigned the admin role.

    Args:
        request: Registration details (email, username, password)

    Returns:
        TokenResponse with access and refresh tokens

    Raises:
        400: Email or username already exists
    """
    auth_service = get_auth_service()

    async with get_db_session() as db:
        # Check if email or username already exists
        result = await db.execute(
            select(User).where(
                or_(
                    User.email == request.email,
                    User.username == request.username
                )
            )
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            if existing_user.email == request.email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )

        # Check if this is the first authenticated user (make them admin)
        # Only count users with password_hash (not legacy Discord/WebRTC users)
        result = await db.execute(
            select(User).where(User.password_hash.isnot(None)).limit(1)
        )
        is_first_auth_user = result.scalar_one_or_none() is None

        # Create new user
        user = User(
            email=request.email,
            username=request.username,
            password_hash=auth_service.hash_password(request.password),
            display_name=request.display_name or request.username,
            role=UserRole.ADMIN if is_first_auth_user else UserRole.USER,
            is_active=True,
            memory_extraction_enabled=False,  # Opt-in by default
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info(
            f"📝 New user registered: {user.username} (role={user.role.value})"
        )

        # Generate tokens
        tokens = auth_service.create_token_pair(
            user_id=str(user.id),
            role=user.role.value
        )

        return TokenResponse(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            expires_in=auth_service.settings.access_token_expire_minutes * 60
        )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return JWT tokens.

    Accepts either username or email in the username field.

    Args:
        request: Login credentials (username/email, password)

    Returns:
        TokenResponse with access and refresh tokens

    Raises:
        401: Invalid credentials
    """
    auth_service = get_auth_service()

    async with get_db_session() as db:
        # Find user by username or email
        result = await db.execute(
            select(User).where(
                or_(
                    User.username == request.username.lower(),
                    User.email == request.username.lower()
                )
            )
        )
        user = result.scalar_one_or_none()

        if not user or not user.password_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not auth_service.verify_password(request.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is disabled",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"🔐 User logged in: {user.username}")

        # Generate tokens
        tokens = auth_service.create_token_pair(
            user_id=str(user.id),
            role=user.role.value
        )

        return TokenResponse(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            expires_in=auth_service.settings.access_token_expire_minutes * 60
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(refresh_security)],
):
    """
    Refresh access token using a refresh token.

    Args:
        credentials: Authorization header with refresh token

    Returns:
        TokenResponse with new access and refresh tokens

    Raises:
        401: Invalid or expired refresh token
    """
    auth_service = get_auth_service()
    token = credentials.credentials

    # Decode refresh token
    payload = auth_service.decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "refresh":
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

    # Fetch user to get current role (might have changed)
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
            detail="Account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug(f"🔄 Token refreshed for user: {user.username}")

    # Generate new tokens
    tokens = auth_service.create_token_pair(
        user_id=str(user.id),
        role=user.role.value
    )

    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_in=auth_service.settings.access_token_expire_minutes * 60
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Get current authenticated user's information.

    Args:
        user: Current user (from JWT)

    Returns:
        UserResponse with user details
    """
    return UserResponse(
        id=str(user.id),
        email=user.email,
        username=user.username,
        display_name=user.display_name,
        role=user.role.value,
        is_active=user.is_active,
        memory_extraction_enabled=user.memory_extraction_enabled,
        created_at=user.created_at,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Logout current user.

    Note: Since JWTs are stateless, this endpoint doesn't invalidate the token.
    The client should discard the tokens. For true token invalidation,
    implement a token blacklist (Redis) in a future phase.

    Args:
        user: Current user (from JWT)

    Returns:
        Success message
    """
    logger.info(f"👋 User logged out: {user.username}")
    return MessageResponse(message="Successfully logged out")


class ChangePasswordRequest(BaseModel):
    """Request body for changing password."""

    current_password: str = Field(..., description="Current password")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password (minimum 8 characters)"
    )


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    request: ChangePasswordRequest,
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Change current user's password.

    Requires verification of current password before allowing change.

    Args:
        request: Current and new password
        user: Current user (from JWT)

    Returns:
        Success message

    Raises:
        400: Current password is incorrect
        400: User has no password set (OAuth-only user)
    """
    auth_service = get_auth_service()

    # Check if user has a password (not OAuth-only)
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change password for accounts without password authentication"
        )

    # Verify current password
    if not auth_service.verify_password(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Hash new password and update
    async with get_db_session() as db:
        result = await db.execute(
            select(User).where(User.id == user.id)
        )
        db_user = result.scalar_one_or_none()

        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        db_user.password_hash = auth_service.hash_password(request.new_password)
        await db.commit()

    logger.info(f"🔑 Password changed for user: {user.username}")
    return MessageResponse(message="Password changed successfully")
