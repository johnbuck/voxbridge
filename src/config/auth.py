"""
Authentication Configuration

Environment-based settings for JWT tokens and password hashing.
"""

import os
import secrets
from dataclasses import dataclass


@dataclass
class AuthSettings:
    """Authentication configuration loaded from environment variables."""

    # JWT Configuration
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int

    @classmethod
    def from_env(cls) -> "AuthSettings":
        """Load settings from environment variables."""
        return cls(
            # Generate a secure random key if not provided (development only!)
            # In production, AUTH_SECRET_KEY MUST be set to a persistent value
            secret_key=os.getenv(
                "AUTH_SECRET_KEY",
                secrets.token_urlsafe(32)  # 256-bit random key for development
            ),
            algorithm=os.getenv("AUTH_ALGORITHM", "HS256"),
            access_token_expire_minutes=int(os.getenv("AUTH_ACCESS_TOKEN_EXPIRE_MINUTES", "30")),
            refresh_token_expire_days=int(os.getenv("AUTH_REFRESH_TOKEN_EXPIRE_DAYS", "7")),
        )


# Global settings instance (lazy-loaded)
_settings: AuthSettings | None = None


def get_auth_settings() -> AuthSettings:
    """Get or create the global auth settings instance."""
    global _settings
    if _settings is None:
        _settings = AuthSettings.from_env()
    return _settings
