"""
Unit tests for LLM type definitions and exceptions.

Tests LLMMessage, LLMRequest models and exception hierarchy.
"""

import pytest
from pydantic import ValidationError

from src.llm.types import (
    LLMMessage,
    LLMRequest,
    LLMError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMConnectionError,
    LLMAuthenticationError,
)


# ============================================================
# LLMMessage Tests
# ============================================================


@pytest.mark.unit
def test_llm_message_creation():
    """Test LLMMessage creation with valid data"""
    # ARRANGE & ACT
    message = LLMMessage(role="user", content="Hello world")

    # ASSERT
    assert message.role == "user"
    assert message.content == "Hello world"


@pytest.mark.unit
def test_llm_message_immutable():
    """Test LLMMessage is immutable (frozen)"""
    # ARRANGE
    message = LLMMessage(role="user", content="Hello")

    # ACT & ASSERT
    with pytest.raises(ValidationError):
        message.role = "assistant"


@pytest.mark.unit
def test_llm_message_all_roles():
    """Test LLMMessage with different role types"""
    # ARRANGE & ACT
    system_msg = LLMMessage(role="system", content="You are helpful")
    user_msg = LLMMessage(role="user", content="Hello")
    assistant_msg = LLMMessage(role="assistant", content="Hi there")

    # ASSERT
    assert system_msg.role == "system"
    assert user_msg.role == "user"
    assert assistant_msg.role == "assistant"


@pytest.mark.unit
def test_llm_message_empty_content():
    """Test LLMMessage with empty content (should be allowed)"""
    # ARRANGE & ACT
    message = LLMMessage(role="user", content="")

    # ASSERT
    assert message.content == ""


@pytest.mark.unit
def test_llm_message_missing_fields():
    """Test LLMMessage validation fails without required fields"""
    # ACT & ASSERT
    with pytest.raises(ValidationError):
        LLMMessage(role="user")  # Missing content

    with pytest.raises(ValidationError):
        LLMMessage(content="Hello")  # Missing role


# ============================================================
# LLMRequest Tests
# ============================================================


@pytest.mark.unit
def test_llm_request_creation():
    """Test LLMRequest creation with required fields"""
    # ARRANGE
    messages = [
        LLMMessage(role="system", content="You are helpful"),
        LLMMessage(role="user", content="Hello"),
    ]

    # ACT
    request = LLMRequest(
        messages=messages,
        model="gpt-4",
        temperature=0.7,
    )

    # ASSERT
    assert len(request.messages) == 2
    assert request.model == "gpt-4"
    assert request.temperature == 0.7
    assert request.max_tokens is None  # Optional field


@pytest.mark.unit
def test_llm_request_with_max_tokens():
    """Test LLMRequest with max_tokens specified"""
    # ARRANGE
    messages = [LLMMessage(role="user", content="Hello")]

    # ACT
    request = LLMRequest(
        messages=messages,
        model="gpt-4",
        temperature=0.5,
        max_tokens=1000,
    )

    # ASSERT
    assert request.max_tokens == 1000


@pytest.mark.unit
def test_llm_request_default_temperature():
    """Test LLMRequest uses default temperature if not specified"""
    # ARRANGE
    messages = [LLMMessage(role="user", content="Test")]

    # ACT
    request = LLMRequest(messages=messages, model="gpt-4")

    # ASSERT
    assert request.temperature == 0.7  # Default value


@pytest.mark.unit
def test_llm_request_temperature_validation():
    """Test LLMRequest temperature validation (0.0 to 2.0)"""
    # ARRANGE
    messages = [LLMMessage(role="user", content="Test")]

    # ACT & ASSERT - Valid temperatures
    request_low = LLMRequest(messages=messages, model="gpt-4", temperature=0.0)
    assert request_low.temperature == 0.0

    request_high = LLMRequest(messages=messages, model="gpt-4", temperature=2.0)
    assert request_high.temperature == 2.0

    # ACT & ASSERT - Invalid temperatures
    with pytest.raises(ValidationError):
        LLMRequest(messages=messages, model="gpt-4", temperature=-0.1)

    with pytest.raises(ValidationError):
        LLMRequest(messages=messages, model="gpt-4", temperature=2.1)


@pytest.mark.unit
def test_llm_request_max_tokens_validation():
    """Test LLMRequest max_tokens validation (must be >= 1)"""
    # ARRANGE
    messages = [LLMMessage(role="user", content="Test")]

    # ACT & ASSERT - Valid max_tokens
    request = LLMRequest(messages=messages, model="gpt-4", max_tokens=1)
    assert request.max_tokens == 1

    # ACT & ASSERT - Invalid max_tokens
    with pytest.raises(ValidationError):
        LLMRequest(messages=messages, model="gpt-4", max_tokens=0)

    with pytest.raises(ValidationError):
        LLMRequest(messages=messages, model="gpt-4", max_tokens=-1)


@pytest.mark.unit
def test_llm_request_immutable():
    """Test LLMRequest is immutable (frozen)"""
    # ARRANGE
    messages = [LLMMessage(role="user", content="Test")]
    request = LLMRequest(messages=messages, model="gpt-4")

    # ACT & ASSERT
    with pytest.raises(ValidationError):
        request.temperature = 1.5


@pytest.mark.unit
def test_llm_request_missing_fields():
    """Test LLMRequest validation fails without required fields"""
    # ARRANGE
    messages = [LLMMessage(role="user", content="Test")]

    # ACT & ASSERT
    with pytest.raises(ValidationError):
        LLMRequest(model="gpt-4")  # Missing messages

    with pytest.raises(ValidationError):
        LLMRequest(messages=messages)  # Missing model


@pytest.mark.unit
def test_llm_request_empty_messages():
    """Test LLMRequest with empty message list"""
    # ACT - Should allow empty list (validation happens at provider level)
    request = LLMRequest(messages=[], model="gpt-4")

    # ASSERT
    assert len(request.messages) == 0


# ============================================================
# Exception Hierarchy Tests
# ============================================================


@pytest.mark.unit
def test_llm_error_base_exception():
    """Test LLMError is base exception"""
    # ACT
    error = LLMError("Test error")

    # ASSERT
    assert isinstance(error, Exception)
    assert str(error) == "Test error"


@pytest.mark.unit
def test_llm_timeout_error_inheritance():
    """Test LLMTimeoutError inherits from LLMError"""
    # ACT
    error = LLMTimeoutError("Request timeout")

    # ASSERT
    assert isinstance(error, LLMError)
    assert isinstance(error, Exception)
    assert str(error) == "Request timeout"


@pytest.mark.unit
def test_llm_rate_limit_error_inheritance():
    """Test LLMRateLimitError inherits from LLMError"""
    # ACT
    error = LLMRateLimitError("Rate limit exceeded")

    # ASSERT
    assert isinstance(error, LLMError)
    assert isinstance(error, Exception)


@pytest.mark.unit
def test_llm_connection_error_inheritance():
    """Test LLMConnectionError inherits from LLMError"""
    # ACT
    error = LLMConnectionError("Connection failed")

    # ASSERT
    assert isinstance(error, LLMError)
    assert isinstance(error, Exception)


@pytest.mark.unit
def test_llm_authentication_error_inheritance():
    """Test LLMAuthenticationError inherits from LLMError"""
    # ACT
    error = LLMAuthenticationError("Invalid API key")

    # ASSERT
    assert isinstance(error, LLMError)
    assert isinstance(error, Exception)


@pytest.mark.unit
def test_exception_catching():
    """Test exceptions can be caught via base LLMError"""
    # ACT & ASSERT
    try:
        raise LLMTimeoutError("Timeout")
    except LLMError as e:
        assert str(e) == "Timeout"

    try:
        raise LLMRateLimitError("Rate limit")
    except LLMError as e:
        assert str(e) == "Rate limit"

    try:
        raise LLMConnectionError("Connection error")
    except LLMError as e:
        assert str(e) == "Connection error"

    try:
        raise LLMAuthenticationError("Auth error")
    except LLMError as e:
        assert str(e) == "Auth error"


# ============================================================
# Integration Tests (Types Working Together)
# ============================================================


@pytest.mark.unit
def test_llm_request_with_conversation_history():
    """Test LLMRequest with multi-turn conversation"""
    # ARRANGE
    messages = [
        LLMMessage(role="system", content="You are a helpful assistant"),
        LLMMessage(role="user", content="What is 2+2?"),
        LLMMessage(role="assistant", content="4"),
        LLMMessage(role="user", content="And 3+3?"),
    ]

    # ACT
    request = LLMRequest(
        messages=messages,
        model="gpt-4",
        temperature=0.5,
        max_tokens=100,
    )

    # ASSERT
    assert len(request.messages) == 4
    assert request.messages[0].role == "system"
    assert request.messages[1].role == "user"
    assert request.messages[2].role == "assistant"
    assert request.messages[3].role == "user"


@pytest.mark.unit
def test_llm_request_dict_serialization():
    """Test LLMRequest can be converted to dict for API calls"""
    # ARRANGE
    messages = [LLMMessage(role="user", content="Test")]
    request = LLMRequest(messages=messages, model="gpt-4", temperature=0.8)

    # ACT
    request_dict = request.model_dump()

    # ASSERT
    assert request_dict["model"] == "gpt-4"
    assert request_dict["temperature"] == 0.8
    assert len(request_dict["messages"]) == 1
    assert request_dict["messages"][0]["role"] == "user"
    assert request_dict["messages"][0]["content"] == "Test"
