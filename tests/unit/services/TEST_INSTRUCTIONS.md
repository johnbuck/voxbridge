# Service Unit Tests - Test Instructions

## Overview

Comprehensive unit tests for VoxBridge 2.0 service layer components. This document provides instructions for running, debugging, and extending the test suite.

## Test Coverage Summary

| Service | Test File | Test Count | Coverage Target |
|---------|-----------|------------|-----------------|
| **ConversationService** | `test_conversation_service.py` | **25 tests** | 90%+ |
| **STTService** | `test_stt_service.py` | **27 tests** | 90%+ |
| **LLMService** | `test_llm_service.py` | **23 tests** | 90%+ |
| **TTSService** | `test_tts_service.py` | **24 tests** | 90%+ |
| **TOTAL** | - | **99 tests** | 90%+ |

## Running Tests

### Run All Service Tests

```bash
# From VoxBridge root directory
pytest tests/unit/services/ -v
```

### Run Specific Service Tests

```bash
# ConversationService tests
pytest tests/unit/services/test_conversation_service.py -v

# STTService tests
pytest tests/unit/services/test_stt_service.py -v

# LLMService tests
pytest tests/unit/services/test_llm_service.py -v

# TTSService tests
pytest tests/unit/services/test_tts_service.py -v
```

### Run Specific Test

```bash
# Run single test by name
pytest tests/unit/services/test_conversation_service.py::test_init_with_defaults -v

# Run all tests matching pattern
pytest tests/unit/services/ -k "test_init" -v
```

### Run with Coverage Report

```bash
# Terminal coverage report
pytest tests/unit/services/ -v --cov=src.services --cov-report=term-missing

# HTML coverage report (opens in browser)
pytest tests/unit/services/ --cov=src.services --cov-report=html
open htmlcov/index.html

# Coverage for specific service
pytest tests/unit/services/test_conversation_service.py \
  --cov=src.services.conversation_service \
  --cov-report=term-missing
```

## Test Organization

### ConversationService Tests (25 tests)

**File**: `tests/unit/services/test_conversation_service.py`

**Test Categories**:
1. **Initialization** (4 tests)
   - Default parameters
   - Custom TTL and context size
   - Service lifecycle (start/stop)
   - Idempotent start

2. **Session Management** (3 tests)
   - Create new session
   - Load existing session
   - Agent not found error

3. **Context Management** (4 tests)
   - Empty context
   - Context with messages
   - Context limiting
   - System prompt inclusion

4. **Message Management** (2 tests)
   - Add user message
   - Add message with metadata

5. **Cache Management** (3 tests)
   - Cache hit
   - Cache TTL expiration
   - Background cleanup task

6. **Agent Configuration** (1 test)
   - Get agent config for session

7. **Concurrency** (2 tests)
   - Concurrent access to same session (locking)
   - Multiple sessions concurrently

8. **Error Handling** (1 test)
   - Graceful degradation on database errors

9. **Cleanup** (5 tests)
   - End session
   - Clear specific session cache
   - Clear all cache
   - Get active sessions
   - Update session activity

### STTService Tests (27 tests)

**File**: `tests/unit/services/test_stt_service.py`

**Test Categories**:
1. **Initialization** (3 tests)
   - Default parameters
   - Custom URL
   - Custom retry/timeout parameters

2. **Connection Management** (5 tests)
   - Successful connection
   - Retry with exponential backoff
   - Max retries exceeded
   - Already connected (idempotent)
   - Clean disconnection

3. **Audio Streaming** (4 tests)
   - Send audio successfully
   - Send when not connected
   - Connection loss during send
   - Bytearray conversion

4. **Callback System** (5 tests)
   - Register callback
   - Partial transcript callback
   - Final transcript callback
   - Callback error handling
   - Error message callback

5. **Status Monitoring** (2 tests)
   - Connection status check
   - Detailed connection status

6. **Metrics** (2 tests)
   - Service-wide metrics
   - Transcription tracking

7. **Concurrency** (1 test)
   - Multiple simultaneous sessions

8. **Reconnection** (1 test)
   - Reconnection attempt

9. **Cleanup** (4 tests)
   - Graceful shutdown
   - Invalid JSON handling
   - Custom URL per session
   - Disconnect when no connection

### LLMService Tests (23 tests)

**File**: `tests/unit/services/test_llm_service.py`

**Test Categories**:
1. **Initialization** (4 tests)
   - OpenRouter only
   - Local LLM only
   - Both providers
   - Fallback disabled

2. **Provider Routing** (2 tests)
   - Route to OpenRouter
   - Route to local LLM

3. **Streaming** (3 tests)
   - Streaming with async callback
   - Non-streaming (buffered)
   - Synchronous callback

4. **Fallback Logic** (4 tests)
   - Fallback OpenRouter → Local on transient error
   - No fallback on authentication error
   - Fallback disabled via config
   - No fallback for local provider

5. **Health Monitoring** (3 tests)
   - Get all provider status
   - Test individual provider health
   - Health check failure

6. **Error Handling** (4 tests)
   - Timeout error
   - Rate limit error
   - Connection error
   - Provider unavailable

7. **Cleanup** (3 tests)
   - Close all providers
   - Async context manager
   - Callback errors don't crash

### TTSService Tests (24 tests)

**File**: `tests/unit/services/test_tts_service.py`

**Test Categories**:
1. **Initialization** (3 tests)
   - Default parameters
   - Custom URL
   - Custom voice and timeout

2. **Synthesis** (5 tests)
   - Streaming with callback
   - Buffered (return bytes)
   - Custom voice and speed
   - Speed clamping (0.5-2.0)
   - Chatterbox unavailable (graceful)

3. **Health Monitoring** (2 tests)
   - Health check success
   - Health check failure

4. **Voice Management** (2 tests)
   - Get available voices
   - Voice retrieval failure

5. **Metrics** (3 tests)
   - Get all metrics
   - Get session-specific metrics
   - Metrics history limit

6. **Cancellation** (3 tests)
   - Cancel active TTS
   - Cancel when no active session
   - New synthesis cancels previous

7. **Error Handling** (3 tests)
   - HTTP error from Chatterbox
   - Timeout error
   - Cancellation during synthesis

8. **Cleanup** (3 tests)
   - Close HTTP client
   - Close cancels active TTS
   - Lazy client initialization

## Debugging Failed Tests

### Show Print Statements

```bash
pytest tests/unit/services/test_conversation_service.py -s
```

### Show Full Traceback

```bash
pytest tests/unit/services/ -v --tb=long
```

### Run Until First Failure

```bash
pytest tests/unit/services/ -x
```

### Run Only Failed Tests (from last run)

```bash
pytest tests/unit/services/ --lf
```

### Verbose Async Debugging

```bash
pytest tests/unit/services/ -vv --log-cli-level=DEBUG
```

## Mocking Strategy

### Database Mocking

All service tests mock database access using `patch('src.services.<service>.get_db_session')`:

```python
with patch('src.services.conversation_service.get_db_session') as mock_db:
    mock_db_ctx = AsyncMock()
    mock_db.return_value.__aenter__.return_value = mock_db_ctx

    # Configure mock behavior
    mock_db_ctx.execute = AsyncMock(return_value=mock_result)
    mock_db_ctx.commit = AsyncMock()
```

### Network Mocking

Network operations (WebSocket, HTTP) are mocked to avoid external dependencies:

```python
# WebSocket mocking
with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
    mock_ws = AsyncMock()
    mock_connect.return_value = mock_ws
    # Test code

# HTTP client mocking
mock_client = AsyncMock()
mock_client.get = AsyncMock(return_value=mock_response)
service._client = mock_client
```

### Provider Mocking (LLMService)

LLM providers are mocked using `LLMProviderFactory`:

```python
with patch('src.services.llm_service.LLMProviderFactory.create_provider') as mock_factory:
    mock_provider = AsyncMock(spec=LLMProvider)

    async def mock_stream(*args, **kwargs):
        yield "Test"
        yield " response"

    mock_provider.generate_stream = mock_stream
    mock_factory.return_value = mock_provider
```

## Shared Fixtures

All tests can use fixtures from `tests/conftest.py`:

### Database Fixtures

- `mock_db_session` - Mock database session
- `mock_agent` - Mock Agent model
- `mock_session_model` - Mock Session model
- `mock_conversation` - Mock Conversation model

### Service Fixtures

- `mock_llm_provider` - Mock LLM provider
- `mock_whisperx_connection` - Mock WhisperX WebSocket
- `mock_httpx_client` - Mock httpx AsyncClient

### Example Usage

```python
@pytest.mark.asyncio
async def test_something(mock_agent, mock_session_model):
    """Test using shared fixtures"""
    assert mock_agent.name == "TestAgent"
    assert mock_session_model.agent == mock_agent
```

## Common Test Patterns

### Testing Async Methods

```python
@pytest.mark.asyncio
async def test_async_method():
    """All async tests need @pytest.mark.asyncio decorator"""
    service = MyService()
    result = await service.async_method()
    assert result is not None
```

### Testing Concurrency

```python
@pytest.mark.asyncio
async def test_concurrent_operations():
    """Test multiple concurrent operations"""
    service = MyService()

    tasks = [
        service.operation(i)
        for i in range(10)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Verify all succeeded
    assert all(isinstance(r, ExpectedType) for r in results)
```

### Testing Error Handling

```python
@pytest.mark.asyncio
async def test_error_handling():
    """Test graceful error handling"""
    service = MyService()

    with pytest.raises(SpecificError, match="error message pattern"):
        await service.failing_method()
```

### Testing Callbacks

```python
@pytest.mark.asyncio
async def test_callback():
    """Test callback invocation"""
    callback_calls = []

    async def callback(data):
        callback_calls.append(data)

    service = MyService()
    await service.method_with_callback(callback=callback)

    assert len(callback_calls) > 0
    assert callback_calls[0] == expected_value
```

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Run Service Unit Tests
  run: |
    pytest tests/unit/services/ -v --cov=src.services --cov-report=xml

- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
    flags: services
```

### Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

pytest tests/unit/services/ -x --tb=short
if [ $? -ne 0 ]; then
    echo "Service tests failed. Commit aborted."
    exit 1
fi
```

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError`:

```bash
# Ensure you're in the VoxBridge root directory
cd /home/wiley/Docker/voxbridge

# Install test dependencies
pip install -r requirements-test.txt
```

### Async Warnings

If you see "coroutine was never awaited":

- Ensure all async functions have `await` when called
- Add `@pytest.mark.asyncio` to async tests
- Use `AsyncMock()` for async methods, not `MagicMock()`

### Database Errors

If tests fail with database errors:

- Tests should NOT connect to real database
- Verify all `get_db_session()` calls are mocked
- Check `patch` paths match import paths

### Timeout Errors

If tests timeout:

- Reduce test timeouts in service initialization
- Mock external dependencies (don't make real network calls)
- Check for infinite loops or deadlocks

## Extending Tests

### Adding New Test

1. Choose appropriate test file
2. Add test function with descriptive name
3. Use `@pytest.mark.asyncio` for async tests
4. Mock external dependencies
5. Assert expected behavior
6. Update this document's test count

### Example New Test

```python
@pytest.mark.asyncio
async def test_new_feature():
    """Test description following existing patterns"""
    service = MyService()

    # Mock dependencies
    with patch('external.dependency') as mock_dep:
        mock_dep.return_value = expected_value

        # Execute test
        result = await service.new_feature()

        # Verify behavior
        assert result == expected_result
        mock_dep.assert_called_once()
```

## Performance Benchmarks

Run with timing information:

```bash
# Show slowest tests
pytest tests/unit/services/ --durations=10

# Profile test execution
pytest tests/unit/services/ --profile
```

## Test Markers

Use markers for selective test execution:

```bash
# Run only fast tests
pytest tests/unit/services/ -m "not slow"

# Run only integration-like tests
pytest tests/unit/services/ -m "integration"
```

## Getting Help

- **VoxBridge Documentation**: See `AGENTS.md` and `CLAUDE.md`
- **Pytest Documentation**: https://docs.pytest.org/
- **Async Testing**: https://pytest-asyncio.readthedocs.io/
- **Coverage.py**: https://coverage.readthedocs.io/

## Test Quality Checklist

Before committing new tests:

- [ ] Test has clear, descriptive name
- [ ] Test docstring explains what is tested
- [ ] All external dependencies are mocked
- [ ] Test is isolated (doesn't depend on other tests)
- [ ] Test covers both happy path and error cases
- [ ] Test runs in < 1 second
- [ ] Test passes consistently (not flaky)
- [ ] Coverage report shows new code is covered

---

**Last Updated**: 2025-10-27
**VoxBridge Version**: 2.0 (Phase 5.8)
**Test Suite Version**: 1.0
