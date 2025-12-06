"""
Authentication Service

Handles password hashing and JWT token operations.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.config.auth import AuthSettings, get_auth_settings

logger = logging.getLogger(__name__)


class AuthService:
    """
    Authentication service for password hashing and JWT management.

    Usage:
        auth_service = AuthService()

        # Hash a password
        hashed = auth_service.hash_password("mypassword")

        # Verify a password
        if auth_service.verify_password("mypassword", hashed):
            print("Password correct!")

        # Create tokens
        access_token = auth_service.create_access_token(user_id="uuid", role="user")
        refresh_token = auth_service.create_refresh_token(user_id="uuid")

        # Decode/verify tokens
        payload = auth_service.decode_token(access_token)
        if payload and payload.get("type") == "access":
            print(f"User ID: {payload['sub']}")
    """

    def __init__(self, settings: AuthSettings | None = None):
        """
        Initialize the auth service.

        Args:
            settings: Optional AuthSettings. If not provided, loads from environment.
        """
        self.settings = settings or get_auth_settings()
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(self, password: str) -> str:
        """
        Hash a password using bcrypt.

        Args:
            password: Plain text password

        Returns:
            Bcrypt-hashed password string
        """
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.

        Args:
            plain_password: Plain text password to verify
            hashed_password: Bcrypt hash to verify against

        Returns:
            True if password matches, False otherwise
        """
        try:
            return self.pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            logger.warning(f"Password verification failed: {e}")
            return False

    def create_access_token(
        self,
        user_id: str,
        role: str,
        extra_claims: dict[str, Any] | None = None
    ) -> str:
        """
        Create a short-lived access token.

        Args:
            user_id: User's UUID as string
            role: User's role (admin/user)
            extra_claims: Optional additional claims to include

        Returns:
            JWT access token string
        """
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=self.settings.access_token_expire_minutes
        )
        payload = {
            "sub": user_id,
            "role": role,
            "type": "access",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }
        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(
            payload,
            self.settings.secret_key,
            algorithm=self.settings.algorithm
        )

    def create_refresh_token(self, user_id: str) -> str:
        """
        Create a long-lived refresh token.

        Args:
            user_id: User's UUID as string

        Returns:
            JWT refresh token string
        """
        expire = datetime.now(timezone.utc) + timedelta(
            days=self.settings.refresh_token_expire_days
        )
        payload = {
            "sub": user_id,
            "type": "refresh",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }

        return jwt.encode(
            payload,
            self.settings.secret_key,
            algorithm=self.settings.algorithm
        )

    def decode_token(self, token: str) -> dict[str, Any] | None:
        """
        Decode and validate a JWT token.

        Args:
            token: JWT token string

        Returns:
            Token payload dict if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                self.settings.secret_key,
                algorithms=[self.settings.algorithm]
            )
            return payload
        except JWTError as e:
            logger.debug(f"Token decode failed: {e}")
            return None

    def create_token_pair(self, user_id: str, role: str) -> dict[str, str]:
        """
        Create both access and refresh tokens.

        Args:
            user_id: User's UUID as string
            role: User's role (admin/user)

        Returns:
            Dict with 'access_token' and 'refresh_token'
        """
        return {
            "access_token": self.create_access_token(user_id, role),
            "refresh_token": self.create_refresh_token(user_id),
        }


# Global service instance (lazy-loaded)
_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    """Get or create the global auth service instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
