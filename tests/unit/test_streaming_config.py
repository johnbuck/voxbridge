"""
Unit tests for streaming configuration.

Tests the StreamingConfig dataclass, configuration loading from environment variables,
and the API endpoint for fetching streaming config.
"""

import os
import pytest
from fastapi.testclient import TestClient
from src.config.streaming import (
    StreamingConfig,
    load_streaming_config,
    get_streaming_config,
    is_streaming_enabled,
)
from src.api.server import app


class TestStreamingConfig:
    """Test StreamingConfig dataclass and validation."""

    def test_default_config(self):
        """Test default configuration values."""
        config = StreamingConfig()

        assert config.enabled is True
        assert config.chunking_strategy == 'sentence'
        assert config.min_chunk_length == 10
        assert config.max_concurrent_tts == 3
        assert config.error_strategy == 'retry'
        assert config.interruption_strategy == 'graceful'

    def test_custom_config(self):
        """Test custom configuration values."""
        config = StreamingConfig(
            enabled=False,
            chunking_strategy='paragraph',
            min_chunk_length=20,
            max_concurrent_tts=5,
            error_strategy='skip',
            interruption_strategy='immediate',
        )

        assert config.enabled is False
        assert config.chunking_strategy == 'paragraph'
        assert config.min_chunk_length == 20
        assert config.max_concurrent_tts == 5
        assert config.error_strategy == 'skip'
        assert config.interruption_strategy == 'immediate'

    def test_validation_min_chunk_length_too_small(self):
        """Test validation rejects min_chunk_length < 5."""
        config = StreamingConfig(min_chunk_length=3)

        with pytest.raises(ValueError, match="min_chunk_length must be between 5 and 200"):
            config.validate()

    def test_validation_min_chunk_length_too_large(self):
        """Test validation rejects min_chunk_length > 200."""
        config = StreamingConfig(min_chunk_length=250)

        with pytest.raises(ValueError, match="min_chunk_length must be between 5 and 200"):
            config.validate()

    def test_validation_max_concurrent_tts_too_small(self):
        """Test validation rejects max_concurrent_tts < 1."""
        config = StreamingConfig(max_concurrent_tts=0)

        with pytest.raises(ValueError, match="max_concurrent_tts must be between 1 and 8"):
            config.validate()

    def test_validation_max_concurrent_tts_too_large(self):
        """Test validation rejects max_concurrent_tts > 8."""
        config = StreamingConfig(max_concurrent_tts=10)

        with pytest.raises(ValueError, match="max_concurrent_tts must be between 1 and 8"):
            config.validate()

    def test_validation_invalid_error_strategy(self):
        """Test validation rejects invalid error_strategy."""
        config = StreamingConfig(error_strategy='invalid')  # type: ignore

        with pytest.raises(ValueError, match="error_strategy must be"):
            config.validate()

    def test_validation_invalid_interruption_strategy(self):
        """Test validation rejects invalid interruption_strategy."""
        config = StreamingConfig(interruption_strategy='invalid')  # type: ignore

        with pytest.raises(ValueError, match="interruption_strategy must be"):
            config.validate()

    def test_validation_invalid_chunking_strategy(self):
        """Test validation rejects invalid chunking_strategy."""
        config = StreamingConfig(chunking_strategy='invalid')  # type: ignore

        with pytest.raises(ValueError, match="chunking_strategy must be"):
            config.validate()

    def test_validation_valid_config(self):
        """Test validation passes for valid config."""
        config = StreamingConfig(
            enabled=True,
            chunking_strategy='word',
            min_chunk_length=15,
            max_concurrent_tts=4,
            error_strategy='fallback',
            interruption_strategy='drain',
        )

        # Should not raise
        config.validate()


class TestLoadStreamingConfig:
    """Test loading configuration from environment variables."""

    def test_load_defaults_when_no_env_vars(self, monkeypatch):
        """Test loading returns defaults when no environment variables set."""
        # Clear all relevant env vars
        for var in [
            'STREAMING_ENABLED',
            'STREAMING_CHUNKING_STRATEGY',
            'STREAMING_MIN_CHUNK_LENGTH',
            'STREAMING_MAX_CONCURRENT_TTS',
            'STREAMING_ERROR_STRATEGY',
            'STREAMING_INTERRUPTION_STRATEGY',
        ]:
            monkeypatch.delenv(var, raising=False)

        config = load_streaming_config()

        assert config.enabled is True
        assert config.chunking_strategy == 'sentence'
        assert config.min_chunk_length == 10
        assert config.max_concurrent_tts == 3
        assert config.error_strategy == 'retry'
        assert config.interruption_strategy == 'graceful'

    def test_load_enabled_from_env_true(self, monkeypatch):
        """Test loading enabled=True from environment."""
        monkeypatch.setenv('STREAMING_ENABLED', 'true')

        config = load_streaming_config()
        assert config.enabled is True

    def test_load_enabled_from_env_false(self, monkeypatch):
        """Test loading enabled=False from environment."""
        monkeypatch.setenv('STREAMING_ENABLED', 'false')

        config = load_streaming_config()
        assert config.enabled is False

    def test_load_enabled_from_env_1(self, monkeypatch):
        """Test loading enabled=True from environment (numeric 1)."""
        monkeypatch.setenv('STREAMING_ENABLED', '1')

        config = load_streaming_config()
        assert config.enabled is True

    def test_load_enabled_from_env_yes(self, monkeypatch):
        """Test loading enabled=True from environment (yes)."""
        monkeypatch.setenv('STREAMING_ENABLED', 'yes')

        config = load_streaming_config()
        assert config.enabled is True

    def test_load_chunking_strategy_from_env(self, monkeypatch):
        """Test loading chunking_strategy from environment."""
        monkeypatch.setenv('STREAMING_CHUNKING_STRATEGY', 'paragraph')

        config = load_streaming_config()
        assert config.chunking_strategy == 'paragraph'

    def test_load_min_chunk_length_from_env(self, monkeypatch):
        """Test loading min_chunk_length from environment."""
        monkeypatch.setenv('STREAMING_MIN_CHUNK_LENGTH', '25')

        config = load_streaming_config()
        assert config.min_chunk_length == 25

    def test_load_max_concurrent_tts_from_env(self, monkeypatch):
        """Test loading max_concurrent_tts from environment."""
        monkeypatch.setenv('STREAMING_MAX_CONCURRENT_TTS', '5')

        config = load_streaming_config()
        assert config.max_concurrent_tts == 5

    def test_load_error_strategy_from_env(self, monkeypatch):
        """Test loading error_strategy from environment."""
        monkeypatch.setenv('STREAMING_ERROR_STRATEGY', 'skip')

        config = load_streaming_config()
        assert config.error_strategy == 'skip'

    def test_load_interruption_strategy_from_env(self, monkeypatch):
        """Test loading interruption_strategy from environment."""
        monkeypatch.setenv('STREAMING_INTERRUPTION_STRATEGY', 'immediate')

        config = load_streaming_config()
        assert config.interruption_strategy == 'immediate'

    def test_load_all_env_vars(self, monkeypatch):
        """Test loading all configuration from environment variables."""
        monkeypatch.setenv('STREAMING_ENABLED', 'false')
        monkeypatch.setenv('STREAMING_CHUNKING_STRATEGY', 'word')
        monkeypatch.setenv('STREAMING_MIN_CHUNK_LENGTH', '20')
        monkeypatch.setenv('STREAMING_MAX_CONCURRENT_TTS', '6')
        monkeypatch.setenv('STREAMING_ERROR_STRATEGY', 'fallback')
        monkeypatch.setenv('STREAMING_INTERRUPTION_STRATEGY', 'drain')

        config = load_streaming_config()

        assert config.enabled is False
        assert config.chunking_strategy == 'word'
        assert config.min_chunk_length == 20
        assert config.max_concurrent_tts == 6
        assert config.error_strategy == 'fallback'
        assert config.interruption_strategy == 'drain'

    def test_load_validates_config(self, monkeypatch):
        """Test that load_streaming_config validates the loaded config."""
        monkeypatch.setenv('STREAMING_MIN_CHUNK_LENGTH', '250')  # Invalid: > 200

        with pytest.raises(ValueError, match="min_chunk_length must be between 5 and 200"):
            load_streaming_config()


class TestGetStreamingConfig:
    """Test singleton pattern for get_streaming_config."""

    def test_get_streaming_config_returns_singleton(self):
        """Test that get_streaming_config returns the same instance."""
        # Import the module to reset the singleton
        import importlib
        import src.config.streaming
        importlib.reload(src.config.streaming)
        from src.config.streaming import get_streaming_config

        config1 = get_streaming_config()
        config2 = get_streaming_config()

        assert config1 is config2

    def test_is_streaming_enabled(self, monkeypatch):
        """Test is_streaming_enabled convenience function."""
        # Reset singleton
        import importlib
        import src.config.streaming
        importlib.reload(src.config.streaming)
        from src.config.streaming import is_streaming_enabled

        monkeypatch.setenv('STREAMING_ENABLED', 'true')

        assert is_streaming_enabled() is True

    def test_is_streaming_disabled(self, monkeypatch):
        """Test is_streaming_enabled returns False when disabled."""
        # Reset singleton
        import importlib
        import src.config.streaming
        importlib.reload(src.config.streaming)
        from src.config.streaming import is_streaming_enabled

        monkeypatch.setenv('STREAMING_ENABLED', 'false')

        assert is_streaming_enabled() is False


class TestStreamingConfigAPI:
    """Test /api/streaming-config endpoint."""

    @pytest.fixture
    def client(self):
        """FastAPI test client."""
        return TestClient(app)

    def test_get_streaming_config_endpoint(self, client, monkeypatch):
        """Test GET /api/streaming-config returns current configuration."""
        # Reset singleton and set environment variables
        import importlib
        import src.config.streaming
        importlib.reload(src.config.streaming)

        monkeypatch.setenv('STREAMING_ENABLED', 'true')
        monkeypatch.setenv('STREAMING_CHUNKING_STRATEGY', 'paragraph')
        monkeypatch.setenv('STREAMING_MIN_CHUNK_LENGTH', '15')
        monkeypatch.setenv('STREAMING_MAX_CONCURRENT_TTS', '5')
        monkeypatch.setenv('STREAMING_ERROR_STRATEGY', 'skip')
        monkeypatch.setenv('STREAMING_INTERRUPTION_STRATEGY', 'immediate')

        response = client.get('/api/streaming-config')

        assert response.status_code == 200
        data = response.json()

        assert data['enabled'] is True
        assert data['chunking_strategy'] == 'paragraph'
        assert data['min_chunk_length'] == 15
        assert data['max_concurrent_tts'] == 5
        assert data['error_strategy'] == 'skip'
        assert data['interruption_strategy'] == 'immediate'

    def test_get_streaming_config_endpoint_defaults(self, client, monkeypatch):
        """Test GET /api/streaming-config returns defaults when no env vars."""
        # Reset singleton and clear environment variables
        import importlib
        import src.config.streaming
        importlib.reload(src.config.streaming)

        for var in [
            'STREAMING_ENABLED',
            'STREAMING_CHUNKING_STRATEGY',
            'STREAMING_MIN_CHUNK_LENGTH',
            'STREAMING_MAX_CONCURRENT_TTS',
            'STREAMING_ERROR_STRATEGY',
            'STREAMING_INTERRUPTION_STRATEGY',
        ]:
            monkeypatch.delenv(var, raising=False)

        response = client.get('/api/streaming-config')

        assert response.status_code == 200
        data = response.json()

        assert data['enabled'] is True
        assert data['chunking_strategy'] == 'sentence'
        assert data['min_chunk_length'] == 10
        assert data['max_concurrent_tts'] == 3
        assert data['error_strategy'] == 'retry'
        assert data['interruption_strategy'] == 'graceful'

    def test_update_streaming_config_endpoint(self, client, monkeypatch):
        """Test PUT /api/streaming-config updates runtime configuration."""
        # Reset singleton
        import importlib
        import src.config.streaming
        importlib.reload(src.config.streaming)

        # Clear env vars to use defaults
        for var in [
            'STREAMING_ENABLED',
            'STREAMING_CHUNKING_STRATEGY',
            'STREAMING_MIN_CHUNK_LENGTH',
            'STREAMING_MAX_CONCURRENT_TTS',
            'STREAMING_ERROR_STRATEGY',
            'STREAMING_INTERRUPTION_STRATEGY',
        ]:
            monkeypatch.delenv(var, raising=False)

        # Update configuration
        response = client.put('/api/streaming-config', json={
            'enabled': False,
            'chunking_strategy': 'fixed',
            'min_chunk_length': 20,
            'max_concurrent_tts': 6,
            'error_strategy': 'skip',
            'interruption_strategy': 'immediate',
        })

        assert response.status_code == 200
        data = response.json()

        assert data['enabled'] is False
        assert data['chunking_strategy'] == 'fixed'
        assert data['min_chunk_length'] == 20
        assert data['max_concurrent_tts'] == 6
        assert data['error_strategy'] == 'skip'
        assert data['interruption_strategy'] == 'immediate'

        # Verify GET returns updated config
        get_response = client.get('/api/streaming-config')
        assert get_response.status_code == 200
        get_data = get_response.json()

        assert get_data == data

    def test_update_streaming_config_partial(self, client, monkeypatch):
        """Test PUT /api/streaming-config with partial update."""
        # Reset singleton
        import importlib
        import src.config.streaming
        importlib.reload(src.config.streaming)

        for var in [
            'STREAMING_ENABLED',
            'STREAMING_CHUNKING_STRATEGY',
            'STREAMING_MIN_CHUNK_LENGTH',
            'STREAMING_MAX_CONCURRENT_TTS',
            'STREAMING_ERROR_STRATEGY',
            'STREAMING_INTERRUPTION_STRATEGY',
        ]:
            monkeypatch.delenv(var, raising=False)

        # Partial update (only min_chunk_length)
        response = client.put('/api/streaming-config', json={
            'min_chunk_length': 25,
        })

        assert response.status_code == 200
        data = response.json()

        # Updated field
        assert data['min_chunk_length'] == 25

        # Unchanged fields (defaults)
        assert data['enabled'] is True
        assert data['chunking_strategy'] == 'sentence'
        assert data['max_concurrent_tts'] == 3
        assert data['error_strategy'] == 'retry'
        assert data['interruption_strategy'] == 'graceful'

    def test_update_streaming_config_validation_error(self, client, monkeypatch):
        """Test PUT /api/streaming-config rejects invalid values."""
        # Reset singleton
        import importlib
        import src.config.streaming
        importlib.reload(src.config.streaming)

        for var in [
            'STREAMING_ENABLED',
            'STREAMING_CHUNKING_STRATEGY',
            'STREAMING_MIN_CHUNK_LENGTH',
            'STREAMING_MAX_CONCURRENT_TTS',
            'STREAMING_ERROR_STRATEGY',
            'STREAMING_INTERRUPTION_STRATEGY',
        ]:
            monkeypatch.delenv(var, raising=False)

        # Invalid min_chunk_length (> 200)
        response = client.put('/api/streaming-config', json={
            'min_chunk_length': 250,
        })

        assert response.status_code == 400
        assert 'min_chunk_length must be between 5 and 200' in response.json()['detail']

    def test_reset_streaming_config_endpoint(self, client, monkeypatch):
        """Test POST /api/streaming-config/reset restores environment defaults."""
        # Reset singleton and set environment variables
        import importlib
        import src.config.streaming
        importlib.reload(src.config.streaming)

        monkeypatch.setenv('STREAMING_ENABLED', 'true')
        monkeypatch.setenv('STREAMING_CHUNKING_STRATEGY', 'word')
        monkeypatch.setenv('STREAMING_MIN_CHUNK_LENGTH', '12')
        monkeypatch.setenv('STREAMING_MAX_CONCURRENT_TTS', '4')
        monkeypatch.setenv('STREAMING_ERROR_STRATEGY', 'fallback')
        monkeypatch.setenv('STREAMING_INTERRUPTION_STRATEGY', 'drain')

        # Update to different values
        update_response = client.put('/api/streaming-config', json={
            'chunking_strategy': 'paragraph',
            'min_chunk_length': 30,
            'error_strategy': 'skip',
        })
        assert update_response.status_code == 200

        # Reset to environment defaults
        reset_response = client.post('/api/streaming-config/reset')
        assert reset_response.status_code == 200
        data = reset_response.json()

        # Should match environment variables
        assert data['enabled'] is True
        assert data['chunking_strategy'] == 'word'
        assert data['min_chunk_length'] == 12
        assert data['max_concurrent_tts'] == 4
        assert data['error_strategy'] == 'fallback'
        assert data['interruption_strategy'] == 'drain'
