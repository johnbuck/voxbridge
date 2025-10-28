"""
Unit tests for PluginEncryption

Tests encryption/decryption of sensitive plugin configuration fields,
error handling, custom plugin registration, and utility functions.
"""
from __future__ import annotations

import pytest
import os
from unittest.mock import patch, MagicMock
from cryptography.fernet import Fernet, InvalidToken

from src.plugins.encryption import (
    PluginEncryption,
    PluginEncryptionError,
    encrypt_plugin_config,
    decrypt_plugin_config
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def valid_encryption_key():
    """Generate a valid Fernet encryption key for testing"""
    return Fernet.generate_key().decode()


@pytest.fixture
def setup_encryption_key(valid_encryption_key):
    """Set up PLUGIN_ENCRYPTION_KEY environment variable and clean up after test"""
    with patch.dict(os.environ, {'PLUGIN_ENCRYPTION_KEY': valid_encryption_key}):
        # Clear cached Fernet instance before each test
        PluginEncryption._fernet = None
        yield valid_encryption_key
        # Clean up cached instance after test
        PluginEncryption._fernet = None


@pytest.fixture
def discord_config():
    """Sample Discord plugin configuration"""
    return {
        "enabled": True,
        "bot_token": "MTIzNDU2Nzg5MDEyMzQ1Njc4OTA.GaBcDe.fGhIjKlMnOpQrStUvWxYz",
        "channels": ["1234567890", "0987654321"],
        "prefix": "!"
    }


@pytest.fixture
def n8n_config():
    """Sample n8n plugin configuration"""
    return {
        "enabled": True,
        "webhook_url": "https://n8n.example.com/webhook/abc123?apiKey=secret_key_here",
        "timeout": 30
    }


@pytest.fixture
def slack_config():
    """Sample Slack plugin configuration with multiple sensitive fields"""
    return {
        "enabled": True,
        "bot_token": "fake-slack-bot-token-for-testing",
        "signing_secret": "fake-signing-secret-12345",
        "app_token": "fake-slack-app-token-67890",
        "channels": ["general", "random"]
    }


# ============================================================
# Basic Encryption/Decryption Tests
# ============================================================

@pytest.mark.unit
def test_encrypt_discord_config(setup_encryption_key, discord_config):
    """Test encrypt_config() with discord plugin (bot_token field)"""
    encrypted = PluginEncryption.encrypt_config("discord", discord_config)

    # Verify non-sensitive fields are unchanged
    assert encrypted["enabled"] == discord_config["enabled"]
    assert encrypted["channels"] == discord_config["channels"]
    assert encrypted["prefix"] == discord_config["prefix"]

    # Verify bot_token is encrypted
    assert encrypted["bot_token"] != discord_config["bot_token"]
    assert encrypted["bot_token"].startswith(PluginEncryption.ENCRYPTED_MARKER)


@pytest.mark.unit
def test_decrypt_discord_config(setup_encryption_key, discord_config):
    """Test decrypt_config() with discord plugin"""
    # First encrypt
    encrypted = PluginEncryption.encrypt_config("discord", discord_config)

    # Then decrypt
    decrypted = PluginEncryption.decrypt_config("discord", encrypted)

    # Verify all fields match original
    assert decrypted == discord_config


@pytest.mark.unit
def test_round_trip_encryption_decryption(setup_encryption_key, discord_config):
    """Test round-trip encryption/decryption (encrypt then decrypt = original)"""
    encrypted = PluginEncryption.encrypt_config("discord", discord_config)
    decrypted = PluginEncryption.decrypt_config("discord", encrypted)

    # Verify decrypted matches original exactly
    assert decrypted == discord_config

    # Verify encrypted is different
    assert encrypted != discord_config
    assert encrypted["bot_token"] != discord_config["bot_token"]


@pytest.mark.unit
def test_encrypt_n8n_config(setup_encryption_key, n8n_config):
    """Test n8n plugin (webhook_url field)"""
    encrypted = PluginEncryption.encrypt_config("n8n", n8n_config)

    # Verify non-sensitive fields unchanged
    assert encrypted["enabled"] == n8n_config["enabled"]
    assert encrypted["timeout"] == n8n_config["timeout"]

    # Verify webhook_url is encrypted
    assert encrypted["webhook_url"] != n8n_config["webhook_url"]
    assert encrypted["webhook_url"].startswith(PluginEncryption.ENCRYPTED_MARKER)


@pytest.mark.unit
def test_encrypt_slack_config_multiple_fields(setup_encryption_key, slack_config):
    """Test slack plugin (multiple sensitive fields: bot_token, signing_secret, app_token)"""
    encrypted = PluginEncryption.encrypt_config("slack", slack_config)

    # Verify non-sensitive fields unchanged
    assert encrypted["enabled"] == slack_config["enabled"]
    assert encrypted["channels"] == slack_config["channels"]

    # Verify all sensitive fields are encrypted
    assert encrypted["bot_token"] != slack_config["bot_token"]
    assert encrypted["bot_token"].startswith(PluginEncryption.ENCRYPTED_MARKER)

    assert encrypted["signing_secret"] != slack_config["signing_secret"]
    assert encrypted["signing_secret"].startswith(PluginEncryption.ENCRYPTED_MARKER)

    assert encrypted["app_token"] != slack_config["app_token"]
    assert encrypted["app_token"].startswith(PluginEncryption.ENCRYPTED_MARKER)


@pytest.mark.unit
def test_decrypt_slack_config_multiple_fields(setup_encryption_key, slack_config):
    """Test decrypting slack plugin with multiple sensitive fields"""
    encrypted = PluginEncryption.encrypt_config("slack", slack_config)
    decrypted = PluginEncryption.decrypt_config("slack", encrypted)

    # Verify all fields match original
    assert decrypted == slack_config


# ============================================================
# Edge Cases Tests
# ============================================================

@pytest.mark.unit
def test_encryption_of_already_encrypted_values(setup_encryption_key, discord_config):
    """Test encryption of already encrypted values (should skip re-encryption)"""
    # First encryption
    encrypted_once = PluginEncryption.encrypt_config("discord", discord_config)

    # Second encryption (should skip)
    encrypted_twice = PluginEncryption.encrypt_config("discord", encrypted_once)

    # Verify encrypted value is unchanged (not double-encrypted)
    assert encrypted_once["bot_token"] == encrypted_twice["bot_token"]

    # Verify still starts with marker
    assert encrypted_twice["bot_token"].startswith(PluginEncryption.ENCRYPTED_MARKER)


@pytest.mark.unit
def test_decryption_of_non_encrypted_values(setup_encryption_key):
    """Test decryption of non-encrypted values (should pass through unchanged)"""
    unencrypted_config = {
        "enabled": True,
        "bot_token": "plain_text_token",  # Not encrypted
        "channels": ["123"]
    }

    decrypted = PluginEncryption.decrypt_config("discord", unencrypted_config)

    # Verify config unchanged (non-encrypted values passed through)
    assert decrypted == unencrypted_config


@pytest.mark.unit
def test_empty_none_values_skip_encryption(setup_encryption_key):
    """Test empty/None values (should skip encryption)"""
    config_with_empty = {
        "enabled": True,
        "bot_token": None,  # None value
        "channels": []
    }

    encrypted = PluginEncryption.encrypt_config("discord", config_with_empty)

    # Verify None value is unchanged (not encrypted)
    assert encrypted["bot_token"] is None

    # Test empty string
    config_with_empty_string = {
        "enabled": True,
        "bot_token": "",  # Empty string
    }

    encrypted_empty = PluginEncryption.encrypt_config("discord", config_with_empty_string)

    # Verify empty string is unchanged
    assert encrypted_empty["bot_token"] == ""


@pytest.mark.unit
def test_plugin_type_with_no_sensitive_fields(setup_encryption_key):
    """Test plugin type with no sensitive fields (should return unchanged config)"""
    unknown_plugin_config = {
        "enabled": True,
        "some_field": "some_value",
        "another_field": 123
    }

    # Use a plugin type not in SENSITIVE_FIELDS
    encrypted = PluginEncryption.encrypt_config("unknown_plugin", unknown_plugin_config)

    # Verify config is returned unchanged (copy, but same values)
    assert encrypted == unknown_plugin_config

    # Verify it's a copy, not the same object
    assert encrypted is not unknown_plugin_config


# ============================================================
# Error Handling Tests
# ============================================================

@pytest.mark.unit
def test_missing_encryption_key_environment_variable():
    """Test missing PLUGIN_ENCRYPTION_KEY environment variable"""
    # Clear cached Fernet instance
    PluginEncryption._fernet = None

    with patch.dict(os.environ, {}, clear=True):
        # Remove PLUGIN_ENCRYPTION_KEY from environment
        os.environ.pop('PLUGIN_ENCRYPTION_KEY', None)

        config = {"enabled": True, "bot_token": "secret"}

        # encrypt_config should return unencrypted config (graceful degradation)
        encrypted = PluginEncryption.encrypt_config("discord", config)
        assert encrypted == config

        # decrypt_config should also pass through
        decrypted = PluginEncryption.decrypt_config("discord", config)
        assert decrypted == config


@pytest.mark.unit
def test_invalid_encryption_key_format():
    """Test invalid encryption key format"""
    # Clear cached Fernet instance
    PluginEncryption._fernet = None

    with patch.dict(os.environ, {'PLUGIN_ENCRYPTION_KEY': 'invalid_key_format'}):
        config = {"enabled": True, "bot_token": "secret"}

        # Should return unencrypted config (graceful degradation)
        encrypted = PluginEncryption.encrypt_config("discord", config)
        assert encrypted == config


@pytest.mark.unit
def test_decryption_with_wrong_key():
    """Test decryption with wrong key (InvalidToken error)"""
    # Encrypt with first key
    key1 = Fernet.generate_key().decode()
    with patch.dict(os.environ, {'PLUGIN_ENCRYPTION_KEY': key1}):
        PluginEncryption._fernet = None
        config = {"enabled": True, "bot_token": "secret"}
        encrypted = PluginEncryption.encrypt_config("discord", config)

    # Try to decrypt with different key
    key2 = Fernet.generate_key().decode()
    with patch.dict(os.environ, {'PLUGIN_ENCRYPTION_KEY': key2}):
        PluginEncryption._fernet = None

        with pytest.raises(PluginEncryptionError) as exc_info:
            PluginEncryption.decrypt_config("discord", encrypted)

        assert "Invalid token" in str(exc_info.value)
        assert "wrong encryption key" in str(exc_info.value)


@pytest.mark.unit
def test_plugin_encryption_error_exception():
    """Test PluginEncryptionError exceptions"""
    # Test exception can be raised and caught
    with pytest.raises(PluginEncryptionError) as exc_info:
        raise PluginEncryptionError("Test error message")

    assert "Test error message" in str(exc_info.value)


# ============================================================
# Custom Plugin Registration Tests
# ============================================================

@pytest.mark.unit
def test_register_sensitive_fields_for_custom_plugin(setup_encryption_key):
    """Test register_sensitive_fields() for custom plugin types"""
    # Register custom plugin
    custom_fields = {"api_key", "oauth_secret"}
    PluginEncryption.register_sensitive_fields("my_custom_plugin", custom_fields)

    # Verify fields were registered
    assert "my_custom_plugin" in PluginEncryption.SENSITIVE_FIELDS
    assert PluginEncryption.SENSITIVE_FIELDS["my_custom_plugin"] == custom_fields

    # Test encryption works with custom plugin
    custom_config = {
        "enabled": True,
        "api_key": "secret_api_key_123",
        "oauth_secret": "oauth_secret_456",
        "public_field": "not_secret"
    }

    encrypted = PluginEncryption.encrypt_config("my_custom_plugin", custom_config)

    # Verify sensitive fields encrypted
    assert encrypted["api_key"].startswith(PluginEncryption.ENCRYPTED_MARKER)
    assert encrypted["oauth_secret"].startswith(PluginEncryption.ENCRYPTED_MARKER)
    assert encrypted["public_field"] == "not_secret"

    # Clean up
    del PluginEncryption.SENSITIVE_FIELDS["my_custom_plugin"]


@pytest.mark.unit
def test_encryption_decryption_of_custom_plugin_after_registration(setup_encryption_key):
    """Test encryption/decryption of custom plugin after registration"""
    # Register custom plugin
    PluginEncryption.register_sensitive_fields("payment_gateway", {"merchant_id", "private_key"})

    config = {
        "enabled": True,
        "merchant_id": "merchant_12345",
        "private_key": "pk_live_abcdefghijklmnop",
        "webhook_url": "https://example.com/webhook"
    }

    # Encrypt
    encrypted = PluginEncryption.encrypt_config("payment_gateway", config)

    # Verify encrypted
    assert encrypted["merchant_id"].startswith(PluginEncryption.ENCRYPTED_MARKER)
    assert encrypted["private_key"].startswith(PluginEncryption.ENCRYPTED_MARKER)
    assert encrypted["webhook_url"] == config["webhook_url"]  # Not sensitive

    # Decrypt
    decrypted = PluginEncryption.decrypt_config("payment_gateway", encrypted)

    # Verify matches original
    assert decrypted == config

    # Clean up
    del PluginEncryption.SENSITIVE_FIELDS["payment_gateway"]


@pytest.mark.unit
def test_register_sensitive_fields_merges_existing_plugin():
    """Test registering fields for existing plugin type merges with existing fields"""
    # Discord already has 'bot_token' as sensitive field
    original_fields = PluginEncryption.SENSITIVE_FIELDS["discord"].copy()

    # Register additional field
    PluginEncryption.register_sensitive_fields("discord", {"new_secret_field"})

    # Verify both old and new fields are present
    assert "bot_token" in PluginEncryption.SENSITIVE_FIELDS["discord"]
    assert "new_secret_field" in PluginEncryption.SENSITIVE_FIELDS["discord"]

    # Restore original state
    PluginEncryption.SENSITIVE_FIELDS["discord"] = original_fields


# ============================================================
# Utility Functions Tests
# ============================================================

@pytest.mark.unit
def test_is_field_encrypted_for_encrypted_value(setup_encryption_key, discord_config):
    """Test is_field_encrypted() for encrypted vs non-encrypted values"""
    # Encrypt config
    encrypted = PluginEncryption.encrypt_config("discord", discord_config)

    # Test encrypted field
    is_encrypted = PluginEncryption.is_field_encrypted(
        "discord",
        "bot_token",
        encrypted["bot_token"]
    )
    assert is_encrypted is True


@pytest.mark.unit
def test_is_field_encrypted_for_non_encrypted_value():
    """Test is_field_encrypted() returns False for non-encrypted values"""
    is_encrypted = PluginEncryption.is_field_encrypted(
        "discord",
        "bot_token",
        "plain_text_token"
    )
    assert is_encrypted is False


@pytest.mark.unit
def test_is_field_encrypted_for_non_sensitive_field():
    """Test is_field_encrypted() returns False for non-sensitive fields"""
    # Even if value has encrypted marker, non-sensitive field returns False
    fake_encrypted_value = f"{PluginEncryption.ENCRYPTED_MARKER}abc123"

    is_encrypted = PluginEncryption.is_field_encrypted(
        "discord",
        "channels",  # Not a sensitive field
        fake_encrypted_value
    )
    assert is_encrypted is False


@pytest.mark.unit
def test_is_field_encrypted_for_non_string_value():
    """Test is_field_encrypted() returns False for non-string values"""
    is_encrypted = PluginEncryption.is_field_encrypted(
        "discord",
        "bot_token",
        123  # Integer, not string
    )
    assert is_encrypted is False


@pytest.mark.unit
def test_encrypted_marker_detection(setup_encryption_key, discord_config):
    """Test ENCRYPTED_MARKER detection"""
    encrypted = PluginEncryption.encrypt_config("discord", discord_config)

    # Verify marker is present
    assert PluginEncryption.ENCRYPTED_MARKER in encrypted["bot_token"]
    assert encrypted["bot_token"].startswith(PluginEncryption.ENCRYPTED_MARKER)

    # Verify non-encrypted field doesn't have marker
    assert PluginEncryption.ENCRYPTED_MARKER not in str(discord_config["bot_token"])


# ============================================================
# Key Generation Tests
# ============================================================

@pytest.mark.unit
def test_generate_key_returns_valid_fernet_key():
    """Test generate_key() returns valid Fernet key"""
    key = PluginEncryption.generate_key()

    # Verify key is a string
    assert isinstance(key, str)

    # Verify key can be used to create Fernet instance
    try:
        fernet = Fernet(key.encode())
        # Test encryption/decryption works
        encrypted = fernet.encrypt(b"test")
        decrypted = fernet.decrypt(encrypted)
        assert decrypted == b"test"
    except Exception as e:
        pytest.fail(f"Generated key is invalid: {e}")


@pytest.mark.unit
def test_generate_key_creates_unique_keys():
    """Test generate_key() creates unique keys each time"""
    key1 = PluginEncryption.generate_key()
    key2 = PluginEncryption.generate_key()

    # Verify keys are different
    assert key1 != key2


# ============================================================
# Convenience Functions Tests
# ============================================================

@pytest.mark.unit
def test_encrypt_plugin_config_convenience_wrapper(setup_encryption_key, discord_config):
    """Test encrypt_plugin_config() convenience wrapper"""
    # Use convenience function
    encrypted = encrypt_plugin_config("discord", discord_config)

    # Verify it works the same as class method
    assert encrypted["bot_token"].startswith(PluginEncryption.ENCRYPTED_MARKER)
    assert encrypted["enabled"] == discord_config["enabled"]


@pytest.mark.unit
def test_decrypt_plugin_config_convenience_wrapper(setup_encryption_key, discord_config):
    """Test decrypt_plugin_config() convenience wrapper"""
    # Encrypt first
    encrypted = encrypt_plugin_config("discord", discord_config)

    # Use convenience function to decrypt
    decrypted = decrypt_plugin_config("discord", encrypted)

    # Verify it works
    assert decrypted == discord_config


# ============================================================
# Fernet Instance Caching Tests
# ============================================================

@pytest.mark.unit
def test_fernet_instance_caching(setup_encryption_key):
    """Test Fernet instance is cached after first creation"""
    # Clear cache
    PluginEncryption._fernet = None

    # First call creates instance
    fernet1 = PluginEncryption._get_fernet()

    # Second call returns cached instance
    fernet2 = PluginEncryption._get_fernet()

    # Verify same instance
    assert fernet1 is fernet2


# ============================================================
# Integration Tests (Multiple Plugins)
# ============================================================

@pytest.mark.unit
def test_encrypt_multiple_plugin_types(setup_encryption_key, discord_config, n8n_config, slack_config):
    """Test encrypting multiple different plugin types"""
    # Encrypt each plugin
    encrypted_discord = PluginEncryption.encrypt_config("discord", discord_config)
    encrypted_n8n = PluginEncryption.encrypt_config("n8n", n8n_config)
    encrypted_slack = PluginEncryption.encrypt_config("slack", slack_config)

    # Verify each has correct fields encrypted
    assert encrypted_discord["bot_token"].startswith(PluginEncryption.ENCRYPTED_MARKER)
    assert encrypted_n8n["webhook_url"].startswith(PluginEncryption.ENCRYPTED_MARKER)
    assert encrypted_slack["bot_token"].startswith(PluginEncryption.ENCRYPTED_MARKER)
    assert encrypted_slack["signing_secret"].startswith(PluginEncryption.ENCRYPTED_MARKER)

    # Decrypt and verify
    decrypted_discord = PluginEncryption.decrypt_config("discord", encrypted_discord)
    decrypted_n8n = PluginEncryption.decrypt_config("n8n", encrypted_n8n)
    decrypted_slack = PluginEncryption.decrypt_config("slack", encrypted_slack)

    assert decrypted_discord == discord_config
    assert decrypted_n8n == n8n_config
    assert decrypted_slack == slack_config


@pytest.mark.unit
def test_all_predefined_plugin_types_have_sensitive_fields():
    """Test all predefined plugin types in SENSITIVE_FIELDS"""
    predefined_plugins = ['discord', 'n8n', 'slack', 'telegram', 'whatsapp', 'api']

    for plugin_type in predefined_plugins:
        assert plugin_type in PluginEncryption.SENSITIVE_FIELDS
        assert len(PluginEncryption.SENSITIVE_FIELDS[plugin_type]) > 0


# ============================================================
# Type Conversion Tests
# ============================================================

@pytest.mark.unit
def test_encryption_converts_non_string_to_string(setup_encryption_key):
    """Test encryption converts non-string values to string before encrypting"""
    config = {
        "enabled": True,
        "bot_token": 123456789,  # Integer token (unusual but possible)
    }

    encrypted = PluginEncryption.encrypt_config("discord", config)

    # Should be encrypted (converted to string first)
    assert encrypted["bot_token"].startswith(PluginEncryption.ENCRYPTED_MARKER)

    # Decrypt should return string representation
    decrypted = PluginEncryption.decrypt_config("discord", encrypted)
    assert decrypted["bot_token"] == "123456789"  # String now


# ============================================================
# Config Immutability Tests
# ============================================================

@pytest.mark.unit
def test_encrypt_config_does_not_modify_original(setup_encryption_key, discord_config):
    """Test encrypt_config() does not modify the original config dict"""
    original_bot_token = discord_config["bot_token"]

    # Encrypt (should create copy)
    encrypted = PluginEncryption.encrypt_config("discord", discord_config)

    # Verify original is unchanged
    assert discord_config["bot_token"] == original_bot_token

    # Verify encrypted is different object
    assert encrypted is not discord_config


@pytest.mark.unit
def test_decrypt_config_does_not_modify_original(setup_encryption_key, discord_config):
    """Test decrypt_config() does not modify the original config dict"""
    # First encrypt
    encrypted = PluginEncryption.encrypt_config("discord", discord_config)
    original_encrypted_token = encrypted["bot_token"]

    # Decrypt (should create copy)
    decrypted = PluginEncryption.decrypt_config("discord", encrypted)

    # Verify encrypted config is unchanged
    assert encrypted["bot_token"] == original_encrypted_token

    # Verify decrypted is different object
    assert decrypted is not encrypted
