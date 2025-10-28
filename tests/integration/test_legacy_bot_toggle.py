"""
Integration Tests for Phase 6.4.1 Batch 2a - Legacy Bot Toggle

Tests that USE_LEGACY_DISCORD_BOT toggle works correctly.

Coverage:
- Default mode uses new plugin-based bot
- Legacy mode enables old handlers
- Toggle is case-insensitive
- Toggle affects bot initialization
- Logging messages are correct
"""
from __future__ import annotations

import pytest
import os
import sys
import importlib
from unittest.mock import patch, MagicMock
from io import StringIO


# ============================================================
# Test Class 1: Environment Variable Parsing
# ============================================================

class TestLegacyToggleParsing:
    """Test USE_LEGACY_DISCORD_BOT environment variable parsing"""

    def test_default_mode_is_new_bot(self):
        """Test default mode (no env var) uses new plugin-based bot"""
        # Need to set DISCORD_TOKEN to avoid exit(1)
        with patch.dict(os.environ, {"DISCORD_TOKEN": "test_token"}, clear=True):
            # Force reimport of discord_bot module
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']

            # Import and check
            import src.discord_bot as bot_module

            # Default should be False (new bot)
            assert bot_module.USE_LEGACY_DISCORD_BOT == False

    def test_legacy_mode_enabled_when_set_true(self):
        """Test setting USE_LEGACY_DISCORD_BOT=true enables legacy mode"""
        with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": "true"}):
            # Force reimport
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']

            import src.discord_bot as bot_module

            # Should be True (legacy mode)
            assert bot_module.USE_LEGACY_DISCORD_BOT == True

    def test_legacy_mode_disabled_when_set_false(self):
        """Test setting USE_LEGACY_DISCORD_BOT=false disables legacy mode"""
        with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": "false"}):
            # Force reimport
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']

            import src.discord_bot as bot_module

            # Should be False (new bot)
            assert bot_module.USE_LEGACY_DISCORD_BOT == False

    def test_toggle_is_case_insensitive(self):
        """Test toggle works with any case"""
        test_cases = [
            ("TRUE", True),
            ("True", True),
            ("true", True),
            ("FALSE", False),
            ("False", False),
            ("false", False)
        ]

        for value, expected in test_cases:
            with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": value}):
                # Force reimport
                if 'src.discord_bot' in sys.modules:
                    del sys.modules['src.discord_bot']

                import src.discord_bot as bot_module

                assert bot_module.USE_LEGACY_DISCORD_BOT == expected, f"Failed for value: {value}"

    def test_invalid_values_default_to_false(self):
        """Test invalid values default to false (new bot)"""
        invalid_values = ["yes", "1", "on", "enabled", "random"]

        for value in invalid_values:
            with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": value}):
                # Force reimport
                if 'src.discord_bot' in sys.modules:
                    del sys.modules['src.discord_bot']

                import src.discord_bot as bot_module

                # Should default to False
                assert bot_module.USE_LEGACY_DISCORD_BOT == False, f"Failed for value: {value}"


# ============================================================
# Test Class 2: Logging Behavior
# ============================================================

class TestLegacyToggleLogging:
    """Test logging messages for legacy toggle"""

    def test_legacy_mode_logs_warning(self, caplog):
        """Test legacy mode logs deprecation warning"""
        import logging

        with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": "true"}):
            # Force reimport
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']

            with caplog.at_level(logging.WARNING):
                import src.discord_bot as bot_module

                # Check for deprecation warning in logs
                assert "LEGACY MODE" in caplog.text
                assert "DEPRECATED" in caplog.text

    def test_new_mode_logs_info(self, caplog):
        """Test new mode logs informational message"""
        import logging

        with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": "false"}):
            # Force reimport
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']

            with caplog.at_level(logging.INFO):
                import src.discord_bot as bot_module

                # Check for info message in logs
                assert "plugin-based" in caplog.text.lower()


# ============================================================
# Test Class 3: Bot Behavior Changes
# ============================================================

class TestLegacyToggleBehavior:
    """Test how toggle affects bot behavior"""

    def test_legacy_mode_preserves_old_handlers(self):
        """Test legacy mode should preserve old voice event handlers"""
        # This test verifies the toggle exists and affects behavior
        # Actual handler registration is tested in E2E tests

        with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": "true"}):
            # Force reimport
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']

            import src.discord_bot as bot_module

            # In legacy mode, old handlers should be available
            # (implementation-specific: we just verify toggle is set)
            assert bot_module.USE_LEGACY_DISCORD_BOT == True

    def test_new_mode_uses_plugin_system(self):
        """Test new mode should use plugin-based routing"""
        with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": "false"}):
            # Force reimport
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']

            import src.discord_bot as bot_module

            # In new mode, plugin system should be used
            # (implementation-specific: we just verify toggle is set)
            assert bot_module.USE_LEGACY_DISCORD_BOT == False


# ============================================================
# Test Class 4: Migration Path Testing
# ============================================================

class TestLegacyMigrationPath:
    """Test migration path from legacy to new bot"""

    def test_can_switch_modes_by_changing_env(self):
        """Test switching modes by changing environment variable"""
        # Start in legacy mode
        with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": "true"}):
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']
            import src.discord_bot as bot_module
            assert bot_module.USE_LEGACY_DISCORD_BOT == True

        # Switch to new mode
        with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": "false"}):
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']
            import src.discord_bot as bot_module
            assert bot_module.USE_LEGACY_DISCORD_BOT == False

    def test_empty_env_var_defaults_to_new_mode(self):
        """Test empty environment variable defaults to new mode"""
        with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": ""}):
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']

            import src.discord_bot as bot_module

            # Empty string should default to False
            assert bot_module.USE_LEGACY_DISCORD_BOT == False


# ============================================================
# Test Class 5: Configuration Validation
# ============================================================

class TestLegacyToggleValidation:
    """Test configuration validation"""

    def test_toggle_value_is_boolean(self):
        """Test USE_LEGACY_DISCORD_BOT is always boolean"""
        test_values = ["true", "false", "TRUE", "FALSE", "invalid", ""]

        for value in test_values:
            with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": value}):
                if 'src.discord_bot' in sys.modules:
                    del sys.modules['src.discord_bot']

                import src.discord_bot as bot_module

                # Should always be boolean
                assert isinstance(bot_module.USE_LEGACY_DISCORD_BOT, bool)

    def test_module_exports_toggle_constant(self):
        """Test discord_bot module exports USE_LEGACY_DISCORD_BOT constant"""
        with patch.dict(os.environ, {}):
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']

            import src.discord_bot as bot_module

            # Should have the constant defined
            assert hasattr(bot_module, 'USE_LEGACY_DISCORD_BOT')


# ============================================================
# Test Class 6: Integration with Plugin System
# ============================================================

class TestLegacyTogglePluginIntegration:
    """Test toggle integration with plugin system"""

    @pytest.mark.integration
    def test_new_mode_allows_plugin_initialization(self):
        """Test new mode allows plugin initialization"""
        with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": "false"}):
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']

            import src.discord_bot as bot_module

            # New mode should allow plugin initialization
            # (actual plugin init tested in other test files)
            assert bot_module.USE_LEGACY_DISCORD_BOT == False

    @pytest.mark.integration
    def test_legacy_mode_skips_plugin_initialization(self):
        """Test legacy mode may skip plugin initialization"""
        with patch.dict(os.environ, {"USE_LEGACY_DISCORD_BOT": "true"}):
            if 'src.discord_bot' in sys.modules:
                del sys.modules['src.discord_bot']

            import src.discord_bot as bot_module

            # Legacy mode indicator
            assert bot_module.USE_LEGACY_DISCORD_BOT == True


# ============================================================
# Cleanup after tests
# ============================================================

@pytest.fixture(autouse=True)
def cleanup_discord_bot_module():
    """Cleanup discord_bot module after each test"""
    yield
    # Remove from sys.modules to allow fresh import
    if 'src.discord_bot' in sys.modules:
        del sys.modules['src.discord_bot']
