"""
Encryption utilities for API keys and sensitive data.

Uses Fernet symmetric encryption from the cryptography library.
The encryption key is stored in the ENCRYPTION_KEY environment variable.
Falls back to PLUGIN_ENCRYPTION_KEY for backward compatibility.
"""

import os
import base64
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Salt for key derivation (fixed, but still provides protection)
# In a production system, this could be stored separately
_KEY_SALT = b'voxbridge_encryption_salt_v1'


def _get_encryption_key() -> Optional[bytes]:
    """
    Get the encryption key from environment variables.

    Tries ENCRYPTION_KEY first, then PLUGIN_ENCRYPTION_KEY for compatibility.
    If neither is set, returns None (encryption disabled).

    Returns:
        32-byte key suitable for Fernet, or None if not configured
    """
    key_value = os.getenv("ENCRYPTION_KEY") or os.getenv("PLUGIN_ENCRYPTION_KEY")

    if not key_value:
        return None

    # Derive a proper 32-byte key from the passphrase
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_KEY_SALT,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(key_value.encode()))


def encrypt_api_key(plaintext: str) -> str:
    """
    Encrypt an API key for storage.

    If encryption is not configured (no ENCRYPTION_KEY), returns the plaintext
    with a warning logged. This allows the system to work without encryption
    in development, while production should always have the key set.

    Args:
        plaintext: The API key to encrypt

    Returns:
        Encrypted string (base64-encoded) or original plaintext if encryption disabled
    """
    if not plaintext:
        return plaintext

    key = _get_encryption_key()
    if not key:
        logger.warning("⚠️ ENCRYPTION_KEY not set - storing API key in plaintext (not recommended)")
        return plaintext

    try:
        fernet = Fernet(key)
        encrypted = fernet.encrypt(plaintext.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f"❌ Failed to encrypt API key: {e}")
        raise ValueError(f"Encryption failed: {e}")


def decrypt_api_key(ciphertext: str) -> str:
    """
    Decrypt an encrypted API key.

    Handles both encrypted values and legacy plaintext values:
    - If decryption succeeds, returns the decrypted value
    - If decryption fails with InvalidToken, assumes it's legacy plaintext
    - If encryption is disabled, returns the value as-is

    Args:
        ciphertext: The encrypted API key (or legacy plaintext)

    Returns:
        Decrypted API key
    """
    if not ciphertext:
        return ciphertext

    key = _get_encryption_key()
    if not key:
        # No encryption configured, return as-is (assume plaintext)
        return ciphertext

    try:
        fernet = Fernet(key)
        decrypted = fernet.decrypt(ciphertext.encode())
        return decrypted.decode()
    except InvalidToken:
        # This might be a legacy plaintext value stored before encryption was enabled
        logger.warning("⚠️ API key appears to be plaintext (legacy) - returning as-is")
        return ciphertext
    except Exception as e:
        logger.error(f"❌ Failed to decrypt API key: {e}")
        raise ValueError(f"Decryption failed: {e}")


def is_encryption_configured() -> bool:
    """Check if encryption is properly configured."""
    return _get_encryption_key() is not None
