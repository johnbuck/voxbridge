"""
Unit tests for LLM provider factory.

Tests provider creation, environment variable handling, and configuration.
"""

import pytest
import os
from unittest.mock import patch, MagicMock

from src.llm.factory import LLMProviderFactory
from src.llm.openrouter import OpenRouterProvider
from src.llm.local_llm import LocalLLMProvider


# ============================================================
# OpenRouter Provider Creation Tests
# ============================================================


@pytest.mark.unit
def test_create_openrouter_with_api_key():
    """Test creating OpenRouter provider with explicit API key"""
    # ACT
    provider = LLMProviderFactory.create_provider(
        provider_name="openrouter",
        api_key="test_api_key_123",
    )

    # ASSERT
    assert isinstance(provider, OpenRouterProvider)
    assert provider.api_key == "test_api_key_123"
    assert provider.base_url == "https://openrouter.ai/api/v1"


@pytest.mark.unit
def test_create_openrouter_with_env_variable():
    """Test creating OpenRouter provider with environment variable"""
    # ARRANGE
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "env_api_key_456"}):
        # ACT
        provider = LLMProviderFactory.create_provider(provider_name="openrouter")

        # ASSERT
        assert isinstance(provider, OpenRouterProvider)
        assert provider.api_key == "env_api_key_456"


@pytest.mark.unit
def test_create_openrouter_missing_api_key():
    """Test OpenRouter creation fails without API key"""
    # ARRANGE
    with patch.dict(os.environ, {}, clear=True):
        # ACT & ASSERT
        with pytest.raises(ValueError) as exc_info:
            LLMProviderFactory.create_provider(provider_name="openrouter")

        assert "OpenRouter API key not found" in str(exc_info.value)
        assert "OPENROUTER_API_KEY" in str(exc_info.value)


@pytest.mark.unit
def test_create_openrouter_with_custom_base_url():
    """Test creating OpenRouter with custom base URL"""
    # ACT
    provider = LLMProviderFactory.create_provider(
        provider_name="openrouter",
        api_key="test_key",
        base_url="https://custom.openrouter.ai/api/v1",
    )

    # ASSERT
    assert isinstance(provider, OpenRouterProvider)
    assert provider.base_url == "https://custom.openrouter.ai/api/v1"


@pytest.mark.unit
def test_create_openrouter_case_insensitive():
    """Test provider name is case-insensitive"""
    # ACT
    provider1 = LLMProviderFactory.create_provider(
        provider_name="OPENROUTER",
        api_key="test_key",
    )
    provider2 = LLMProviderFactory.create_provider(
        provider_name="OpenRouter",
        api_key="test_key",
    )
    provider3 = LLMProviderFactory.create_provider(
        provider_name="openrouter",
        api_key="test_key",
    )

    # ASSERT
    assert isinstance(provider1, OpenRouterProvider)
    assert isinstance(provider2, OpenRouterProvider)
    assert isinstance(provider3, OpenRouterProvider)


# ============================================================
# Local LLM Provider Creation Tests
# ============================================================


@pytest.mark.unit
def test_create_local_with_base_url():
    """Test creating Local LLM provider with explicit base URL"""
    # ACT
    provider = LLMProviderFactory.create_provider(
        provider_name="local",
        base_url="http://localhost:11434/v1",
    )

    # ASSERT
    assert isinstance(provider, LocalLLMProvider)
    assert provider.base_url == "http://localhost:11434/v1"


@pytest.mark.unit
def test_create_local_with_env_variable():
    """Test creating Local LLM provider with environment variable"""
    # ARRANGE
    with patch.dict(os.environ, {"LOCAL_LLM_BASE_URL": "http://localhost:8000/v1"}):
        # ACT
        provider = LLMProviderFactory.create_provider(provider_name="local")

        # ASSERT
        assert isinstance(provider, LocalLLMProvider)
        assert provider.base_url == "http://localhost:8000/v1"


@pytest.mark.unit
def test_create_local_default_base_url():
    """Test Local LLM provider uses default Ollama URL if not specified"""
    # ARRANGE
    with patch.dict(os.environ, {}, clear=True):
        # ACT
        provider = LLMProviderFactory.create_provider(provider_name="local")

        # ASSERT
        assert isinstance(provider, LocalLLMProvider)
        assert provider.base_url == "http://localhost:11434/v1"


@pytest.mark.unit
def test_create_local_with_api_key():
    """Test creating Local LLM provider with optional API key"""
    # ACT
    provider = LLMProviderFactory.create_provider(
        provider_name="local",
        base_url="http://localhost:1234/v1",
        api_key="optional_key",
    )

    # ASSERT
    assert isinstance(provider, LocalLLMProvider)
    assert provider.api_key == "optional_key"


@pytest.mark.unit
def test_create_local_case_insensitive():
    """Test local provider name is case-insensitive"""
    # ACT
    provider1 = LLMProviderFactory.create_provider(
        provider_name="LOCAL",
        base_url="http://localhost:11434/v1",
    )
    provider2 = LLMProviderFactory.create_provider(
        provider_name="Local",
        base_url="http://localhost:11434/v1",
    )

    # ASSERT
    assert isinstance(provider1, LocalLLMProvider)
    assert isinstance(provider2, LocalLLMProvider)


# ============================================================
# Invalid Provider Tests
# ============================================================


@pytest.mark.unit
def test_create_invalid_provider():
    """Test factory raises ValueError for unknown provider"""
    # ACT & ASSERT
    with pytest.raises(ValueError) as exc_info:
        LLMProviderFactory.create_provider(
            provider_name="invalid_provider",
            api_key="test_key",
        )

    assert "Unknown LLM provider" in str(exc_info.value)
    assert "invalid_provider" in str(exc_info.value)
    assert "openrouter" in str(exc_info.value)
    assert "local" in str(exc_info.value)


@pytest.mark.unit
def test_create_empty_provider_name():
    """Test factory raises ValueError for empty provider name"""
    # ACT & ASSERT
    with pytest.raises(ValueError) as exc_info:
        LLMProviderFactory.create_provider(
            provider_name="",
            api_key="test_key",
        )

    assert "Unknown LLM provider" in str(exc_info.value)


@pytest.mark.unit
def test_create_whitespace_provider_name():
    """Test factory handles whitespace in provider name"""
    # ACT
    provider = LLMProviderFactory.create_provider(
        provider_name="  openrouter  ",
        api_key="test_key",
    )

    # ASSERT
    assert isinstance(provider, OpenRouterProvider)


# ============================================================
# Agent Configuration Tests
# ============================================================


@pytest.mark.unit
def test_create_from_agent_config_openrouter():
    """Test creating provider from agent configuration (OpenRouter)"""
    # ACT
    provider, model = LLMProviderFactory.create_from_agent_config(
        llm_provider="openrouter",
        llm_model="anthropic/claude-3.5-sonnet",
        api_key="test_key",
    )

    # ASSERT
    assert isinstance(provider, OpenRouterProvider)
    assert model == "anthropic/claude-3.5-sonnet"
    assert provider.api_key == "test_key"


@pytest.mark.unit
def test_create_from_agent_config_local():
    """Test creating provider from agent configuration (Local LLM)"""
    # ACT
    provider, model = LLMProviderFactory.create_from_agent_config(
        llm_provider="local",
        llm_model="llama3:8b",
        base_url="http://localhost:11434/v1",
    )

    # ASSERT
    assert isinstance(provider, LocalLLMProvider)
    assert model == "llama3:8b"
    assert provider.base_url == "http://localhost:11434/v1"


@pytest.mark.unit
def test_create_from_agent_config_with_env():
    """Test agent config creation uses environment variables"""
    # ARRANGE
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "env_key"}):
        # ACT
        provider, model = LLMProviderFactory.create_from_agent_config(
            llm_provider="openrouter",
            llm_model="gpt-4",
        )

        # ASSERT
        assert isinstance(provider, OpenRouterProvider)
        assert provider.api_key == "env_key"
        assert model == "gpt-4"


@pytest.mark.unit
def test_create_from_agent_config_override_env():
    """Test agent config explicit parameters override environment"""
    # ARRANGE
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "env_key"}):
        # ACT
        provider, model = LLMProviderFactory.create_from_agent_config(
            llm_provider="openrouter",
            llm_model="gpt-4",
            api_key="explicit_key",
        )

        # ASSERT
        assert isinstance(provider, OpenRouterProvider)
        assert provider.api_key == "explicit_key"  # Not env_key


@pytest.mark.unit
def test_create_from_agent_config_invalid_provider():
    """Test agent config creation fails with invalid provider"""
    # ACT & ASSERT
    with pytest.raises(ValueError) as exc_info:
        LLMProviderFactory.create_from_agent_config(
            llm_provider="nonexistent",
            llm_model="some-model",
        )

    assert "Unknown LLM provider" in str(exc_info.value)


# ============================================================
# Environment Variable Precedence Tests
# ============================================================


@pytest.mark.unit
def test_api_key_parameter_overrides_env():
    """Test explicit API key parameter takes precedence over environment"""
    # ARRANGE
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "env_key"}):
        # ACT
        provider = LLMProviderFactory.create_provider(
            provider_name="openrouter",
            api_key="param_key",
        )

        # ASSERT
        assert provider.api_key == "param_key"


@pytest.mark.unit
def test_base_url_parameter_overrides_env():
    """Test explicit base URL parameter takes precedence over environment"""
    # ARRANGE
    with patch.dict(os.environ, {"LOCAL_LLM_BASE_URL": "http://env:8000/v1"}):
        # ACT
        provider = LLMProviderFactory.create_provider(
            provider_name="local",
            base_url="http://param:9000/v1",
        )

        # ASSERT
        assert provider.base_url == "http://param:9000/v1"


@pytest.mark.unit
def test_multiple_env_variables():
    """Test factory works with multiple environment variables set"""
    # ARRANGE
    with patch.dict(
        os.environ,
        {
            "OPENROUTER_API_KEY": "openrouter_key",
            "LOCAL_LLM_BASE_URL": "http://localhost:11434/v1",
        },
    ):
        # ACT
        openrouter_provider = LLMProviderFactory.create_provider("openrouter")
        local_provider = LLMProviderFactory.create_provider("local")

        # ASSERT
        assert isinstance(openrouter_provider, OpenRouterProvider)
        assert openrouter_provider.api_key == "openrouter_key"

        assert isinstance(local_provider, LocalLLMProvider)
        assert local_provider.base_url == "http://localhost:11434/v1"


# ============================================================
# Edge Case Tests
# ============================================================


@pytest.mark.unit
def test_create_provider_with_none_values():
    """Test factory handles None values correctly"""
    # ARRANGE
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "env_key"}):
        # ACT
        provider = LLMProviderFactory.create_provider(
            provider_name="openrouter",
            api_key=None,  # Should fall back to environment
        )

        # ASSERT
        assert provider.api_key == "env_key"


@pytest.mark.unit
def test_create_provider_preserves_trailing_slash():
    """Test factory preserves custom base URL formatting"""
    # ACT
    provider = LLMProviderFactory.create_provider(
        provider_name="openrouter",
        api_key="test_key",
        base_url="https://custom.api.com/v1/",
    )

    # ASSERT
    # OpenRouter should preserve the URL as provided
    assert provider.base_url == "https://custom.api.com/v1/"


@pytest.mark.unit
def test_factory_is_static():
    """Test factory methods are static (no instance needed)"""
    # ACT & ASSERT - Should work without instantiating factory
    provider = LLMProviderFactory.create_provider(
        provider_name="openrouter",
        api_key="test_key",
    )

    assert isinstance(provider, OpenRouterProvider)

    # Test create_from_agent_config is also static
    provider2, model = LLMProviderFactory.create_from_agent_config(
        llm_provider="openrouter",
        llm_model="gpt-4",
        api_key="test_key",
    )

    assert isinstance(provider2, OpenRouterProvider)
    assert model == "gpt-4"
