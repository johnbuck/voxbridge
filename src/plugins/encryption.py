"""
Plugin Configuration Encryption

Encrypts sensitive fields in plugin configurations before storing in database.
Uses Fernet symmetric encryption (cryptography library).

Security Design:
- Encryption key stored in environment variable (PLUGIN_ENCRYPTION_KEY)
- Each plugin type defines which fields are sensitive
- Transparent encryption/decryption in service layer
- User never sees encrypted values in UI

Usage:
    from src.plugins.encryption import PluginEncryption

    # Before saving to database
    encrypted_config = PluginEncryption.encrypt_config("discord", {
        "enabled": True,
        "bot_token": "MTIzNDU2...",  # Will be encrypted
        "channels": ["1234567890"]    # Won't be encrypted
    })

    # After loading from database
    decrypted_config = PluginEncryption.decrypt_config("discord", encrypted_config)
"""

import os
import logging
from typing import Dict, Any, Set
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class PluginEncryptionError(Exception):
    """Raised when encryption/decryption fails"""
    pass


class PluginEncryption:
    """
    Handles encryption/decryption of sensitive plugin configuration fields.

    Sensitive fields are defined per plugin type. Only these fields are encrypted;
    other fields remain in plaintext for queryability and debugging.

    Example sensitive fields:
    - discord: bot_token
    - n8n: webhook_url (may contain API keys)
    - slack: bot_token, signing_secret
    - telegram: bot_token
    """

    # Define sensitive fields per plugin type
    # These fields will be encrypted before storing in database
    SENSITIVE_FIELDS: Dict[str, Set[str]] = {
        'discord': {'bot_token'},
        'n8n': {'webhook_url'},  # May contain API keys in URL
        'slack': {'bot_token', 'signing_secret', 'app_token'},
        'telegram': {'bot_token'},
        'whatsapp': {'api_key', 'phone_number'},
        'api': {'api_key', 'api_secret', 'oauth_token'},
    }

    # Marker to identify encrypted values (prevents double encryption)
    ENCRYPTED_MARKER = '__encrypted__:'

    # Cached Fernet instance (avoid recreating on every call)
    _fernet = None

    @classmethod
    def _get_fernet(cls) -> Fernet:
        """
        Get or create Fernet cipher instance.

        Encryption key is read from PLUGIN_ENCRYPTION_KEY environment variable.
        Key must be 32 url-safe base64-encoded bytes (generate with Fernet.generate_key()).

        Returns:
            Fernet instance

        Raises:
            PluginEncryptionError: If encryption key not configured or invalid
        """
        if cls._fernet is not None:
            return cls._fernet

        # Read encryption key from environment
        encryption_key = os.getenv('PLUGIN_ENCRYPTION_KEY')

        if not encryption_key:
            raise PluginEncryptionError(
                "PLUGIN_ENCRYPTION_KEY environment variable not set. "
                "Generate a key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        try:
            cls._fernet = Fernet(encryption_key.encode())
            return cls._fernet
        except Exception as e:
            raise PluginEncryptionError(f"Invalid PLUGIN_ENCRYPTION_KEY: {e}")

    @classmethod
    def encrypt_config(cls, plugin_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encrypt sensitive fields in plugin configuration.

        Args:
            plugin_type: Plugin type (e.g., "discord", "n8n")
            config: Plugin configuration dict

        Returns:
            Dict with sensitive fields encrypted

        Example:
            config = {
                "enabled": True,
                "bot_token": "MTIzNDU2...",
                "channels": ["1234567890"]
            }

            encrypted = PluginEncryption.encrypt_config("discord", config)
            # {
            #     "enabled": True,
            #     "bot_token": "__encrypted__:gAAAAABf...",
            #     "channels": ["1234567890"]
            # }
        """
        # Get sensitive fields for this plugin type
        sensitive_fields = cls.SENSITIVE_FIELDS.get(plugin_type, set())

        if not sensitive_fields:
            # No sensitive fields for this plugin type
            return config.copy()

        # Get Fernet cipher
        try:
            fernet = cls._get_fernet()
        except PluginEncryptionError as e:
            logger.warning(f"⚠️ Plugin encryption disabled: {e}")
            return config.copy()  # Return unencrypted if key not configured

        # Encrypt sensitive fields
        encrypted_config = config.copy()

        for field in sensitive_fields:
            if field in encrypted_config:
                value = encrypted_config[field]

                # Skip if already encrypted
                if isinstance(value, str) and value.startswith(cls.ENCRYPTED_MARKER):
                    continue

                # Skip if None or empty
                if not value:
                    continue

                try:
                    # Convert value to string, encrypt, and add marker
                    value_str = str(value)
                    encrypted_bytes = fernet.encrypt(value_str.encode())
                    encrypted_config[field] = f"{cls.ENCRYPTED_MARKER}{encrypted_bytes.decode()}"

                    logger.debug(f"🔒 Encrypted field '{field}' for plugin type '{plugin_type}'")

                except Exception as e:
                    logger.error(f"❌ Failed to encrypt field '{field}': {e}")
                    raise PluginEncryptionError(f"Encryption failed for field '{field}': {e}")

        return encrypted_config

    @classmethod
    def decrypt_config(cls, plugin_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypt sensitive fields in plugin configuration.

        Args:
            plugin_type: Plugin type (e.g., "discord", "n8n")
            config: Plugin configuration dict (may contain encrypted fields)

        Returns:
            Dict with sensitive fields decrypted

        Example:
            encrypted_config = {
                "enabled": True,
                "bot_token": "__encrypted__:gAAAAABf...",
                "channels": ["1234567890"]
            }

            decrypted = PluginEncryption.decrypt_config("discord", encrypted_config)
            # {
            #     "enabled": True,
            #     "bot_token": "MTIzNDU2...",
            #     "channels": ["1234567890"]
            # }
        """
        # Get sensitive fields for this plugin type
        sensitive_fields = cls.SENSITIVE_FIELDS.get(plugin_type, set())

        if not sensitive_fields:
            # No sensitive fields for this plugin type
            return config.copy()

        # Get Fernet cipher
        try:
            fernet = cls._get_fernet()
        except PluginEncryptionError as e:
            logger.warning(f"⚠️ Plugin decryption disabled: {e}")
            return config.copy()  # Return as-is if key not configured

        # Decrypt sensitive fields
        decrypted_config = config.copy()

        for field in sensitive_fields:
            if field in decrypted_config:
                value = decrypted_config[field]

                # Skip if not encrypted
                if not isinstance(value, str) or not value.startswith(cls.ENCRYPTED_MARKER):
                    continue

                try:
                    # Remove marker and decrypt
                    encrypted_str = value[len(cls.ENCRYPTED_MARKER):]
                    decrypted_bytes = fernet.decrypt(encrypted_str.encode())
                    decrypted_config[field] = decrypted_bytes.decode()

                    logger.debug(f"🔓 Decrypted field '{field}' for plugin type '{plugin_type}'")

                except InvalidToken:
                    logger.error(f"❌ Invalid encryption token for field '{field}' (wrong key or corrupted data)")
                    raise PluginEncryptionError(
                        f"Decryption failed for field '{field}': Invalid token (wrong encryption key?)"
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to decrypt field '{field}': {e}")
                    raise PluginEncryptionError(f"Decryption failed for field '{field}': {e}")

        return decrypted_config

    @classmethod
    def is_field_encrypted(cls, plugin_type: str, field_name: str, value: Any) -> bool:
        """
        Check if a field value is encrypted.

        Args:
            plugin_type: Plugin type
            field_name: Field name
            value: Field value

        Returns:
            bool: True if value is encrypted, False otherwise

        Example:
            is_encrypted = PluginEncryption.is_field_encrypted(
                "discord",
                "bot_token",
                "__encrypted__:gAAAAABf..."
            )
            # True
        """
        sensitive_fields = cls.SENSITIVE_FIELDS.get(plugin_type, set())

        if field_name not in sensitive_fields:
            return False

        if not isinstance(value, str):
            return False

        return value.startswith(cls.ENCRYPTED_MARKER)

    @classmethod
    def register_sensitive_fields(cls, plugin_type: str, fields: Set[str]) -> None:
        """
        Register sensitive fields for a custom plugin type.

        Allows third-party plugins to declare which fields should be encrypted.

        Args:
            plugin_type: Plugin type identifier
            fields: Set of field names to encrypt

        Example:
            # In your custom plugin:
            PluginEncryption.register_sensitive_fields(
                "my_custom_plugin",
                {"api_key", "oauth_secret"}
            )
        """
        if plugin_type in cls.SENSITIVE_FIELDS:
            logger.warning(
                f"⚠️ Plugin type '{plugin_type}' already has sensitive fields registered, merging"
            )
            cls.SENSITIVE_FIELDS[plugin_type].update(fields)
        else:
            cls.SENSITIVE_FIELDS[plugin_type] = set(fields)

        logger.info(f"🔒 Registered sensitive fields for plugin '{plugin_type}': {fields}")

    @classmethod
    def generate_key(cls) -> str:
        """
        Generate a new Fernet encryption key.

        Returns:
            str: Base64-encoded encryption key (32 bytes)

        Example:
            key = PluginEncryption.generate_key()
            print(f"Add to .env: PLUGIN_ENCRYPTION_KEY={key}")
        """
        return Fernet.generate_key().decode()


# Convenience functions for common operations
def encrypt_plugin_config(plugin_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Encrypt plugin configuration (convenience wrapper)"""
    return PluginEncryption.encrypt_config(plugin_type, config)


def decrypt_plugin_config(plugin_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Decrypt plugin configuration (convenience wrapper)"""
    return PluginEncryption.decrypt_config(plugin_type, config)
