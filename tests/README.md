# VoxBridge Testing Framework

Comprehensive testing suite for VoxBridge with unit tests, integration tests, and end-to-end tests.

## Quick Start

### Install Test Dependencies

```bash
# Install test requirements
pip install -r requirements-test.txt
```

### Run Tests

```bash
# Run all tests
pytest

# Run only unit tests (fast)
pytest tests/unit -v

# Run only integration tests
pytest tests/integration -v

# Run with coverage report
pytest --cov=. --cov-report=html
```

## Test Organization

### Directory Structure

```
tests/
├── unit/                   # Unit tests (fully mocked, fast)
│   ├── test_whisper_client.py
│   ├── test_speaker_manager.py
│   ├── test_streaming_handler.py
│   └── test_audio_receiver.py
│
├── integration/            # Integration tests (mock servers)
│   ├── test_api_endpoints.py
│   ├── test_whisperx_integration.py
│   ├── test_chatterbox_integration.py
│   └── test_n8n_integration.py
│
├── e2e/                    # End-to-end tests (real services)
│   ├── test_full_pipeline.py
│   └── test_n8n_real.py
│
├── mocks/                  # Mock servers and utilities
│   ├── mock_discord.py
│   ├── mock_whisperx_server.py
│   ├── mock_n8n_server.py
│   └── mock_chatterbox_server.py
│
├── fixtures/               # Test data and fixtures
│   ├── audio_samples.py
│   ├── transcript_samples.py
│   └── tts_samples.py
│
└── utils/                  # Test utilities
    ├── helpers.py
    └── assertions.py
```

## Test Markers

Use pytest markers to run specific test categories:

```bash
# Run only unit tests
pytest -m unit

# Run integration tests
pytest -m integration

# Run end-to-end tests (requires services running)
pytest -m e2e

# Run tests requiring n8n
pytest -m n8n

# Skip slow tests
pytest -m "not slow"
```

### Available Markers

- `unit` - Fast unit tests with full mocking
- `integration` - Integration tests with mock servers
- `e2e` - End-to-end tests requiring real services
- `n8n` - Tests requiring real n8n instance
- `slow` - Tests taking > 1 second
- `whisperx` - Tests requiring WhisperX server
- `chatterbox` - Tests requiring Chatterbox TTS server
- `discord` - Tests requiring Discord mocking

## Mock Servers

### WhisperX Mock Server

```python
import pytest

@pytest.mark.asyncio
async def test_whisperx_connection():
    from tests.mocks.mock_whisperx_server import create_mock_whisperx_server

    async with create_mock_whisperx_server() as port:
        # Server is running on ws://localhost:{port}
        client = WhisperClient()
        await client.connect(user_id="test", url=f"ws://localhost:{port}")
        assert client.is_connected
```

### n8n Mock Server

```python
@pytest.mark.asyncio
async def test_n8n_webhook():
    from tests.mocks.mock_n8n_server import create_mock_n8n_server

    async with create_mock_n8n_server() as base_url:
        # Server is running at {base_url}/webhook/test
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/webhook/test",
                json={"text": "Hello", "userId": "123"}
            )
            assert response.status_code == 200
```

### Chatterbox Mock Server

```python
@pytest.mark.asyncio
async def test_chatterbox_tts():
    from tests.mocks.mock_chatterbox_server import create_mock_chatterbox_server

    async with create_mock_chatterbox_server() as base_url:
        # Server is running at {base_url}/audio/speech/stream/upload
        async with httpx.AsyncClient() as client:
            async with client.stream(
                'POST',
                f"{base_url}/audio/speech/stream/upload",
                data={"input": "Test", "voice": "default"}
            ) as response:
                chunks = []
                async for chunk in response.aiter_bytes():
                    chunks.append(chunk)
                assert len(chunks) > 0
```

## Fixtures

### Component Fixtures

```python
def test_whisper_client(whisper_client):
    """Use whisper_client fixture"""
    assert whisper_client is not None

def test_speaker_manager(speaker_manager):
    """Use speaker_manager fixture"""
    assert speaker_manager.active_speaker is None

def test_streaming_handler(streaming_handler):
    """Use streaming_handler fixture"""
    assert streaming_handler.buffer == ''
```

### Mock Discord Fixtures

```python
def test_voice_client(mock_discord_voice_client):
    """Use mock Discord voice client"""
    mock_discord_voice_client.play(audio_source)
    assert mock_discord_voice_client.is_playing()

def test_user(mock_discord_user):
    """Use mock Discord user"""
    assert mock_discord_user.id == 123456789
```

### Test Data Fixtures

```python
def test_audio_data(sample_audio_opus):
    """Use sample Opus audio"""
    assert len(sample_audio_opus) > 0

def test_transcript(sample_transcript):
    """Use sample transcript"""
    assert isinstance(sample_transcript, str)
```

## Writing Tests

### Unit Test Example

```python
import pytest
from whisper_client import WhisperClient

@pytest.mark.unit
@pytest.mark.asyncio
async def test_whisper_client_connect():
    """Test WhisperClient connection"""
    client = WhisperClient()

    # Mock WebSocket
    with patch('websockets.connect') as mock_connect:
        mock_ws = AsyncMock()
        mock_connect.return_value = mock_ws

        await client.connect("test_user")

        assert client.is_connected
        mock_ws.send.assert_called_once()
```

### Integration Test Example

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_whisperx_transcription(mock_whisperx_server):
    """Test WhisperX transcription with mock server"""
    from tests.fixtures.audio_samples import get_sample_opus_audio

    client = WhisperClient()
    client.whisper_server_url = f"ws://localhost:{mock_whisperx_server}"

    await client.connect("test_user")
    await client.send_audio(get_sample_opus_audio())
    transcript = await client.finalize()

    assert len(transcript) > 0
```

### End-to-End Test Example

```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_pipeline():
    """Test complete STT -> n8n -> TTS pipeline"""
    # Requires WhisperX, Chatterbox, and n8n running

    # 1. Send audio to WhisperX
    # 2. Get transcript
    # 3. Send to n8n
    # 4. Get response
    # 5. Generate TTS
    # 6. Verify audio output

    pass  # Implementation
```

## Test Utilities

### Wait for Condition

```python
from tests.utils.helpers import wait_for_condition, assert_eventually

# Wait for condition
success = await wait_for_condition(
    lambda: client.is_connected,
    timeout=2.0
)
assert success

# Assert eventually
await assert_eventually(
    lambda: len(results) > 0,
    timeout=1.0,
    message="No results received"
)
```

### Measure Execution Time

```python
from tests.utils.helpers import TimedContext

async with TimedContext() as timer:
    await some_operation()

assert timer.elapsed < 1.0, f"Too slow: {timer.elapsed}s"
```

### Collect Async Iterator

```python
from tests.utils.helpers import collect_async_iterator

chunks = await collect_async_iterator(response.aiter_bytes())
assert len(chunks) > 0
```

## Running End-to-End Tests

E2E tests require real services running. Start services with Docker Compose:

```bash
# Start WhisperX and Chatterbox
cd /home/wiley/Docker/voxbridge
docker compose up -d

# Run E2E tests (excluding real n8n tests)
pytest tests/e2e -v --ignore=tests/e2e/test_n8n_real.py
```

### Running Real n8n Tests

1. Ensure n8n is running with the test workflow installed
2. Set environment variable:
   ```bash
   export N8N_WEBHOOK_URL="http://localhost:5678/webhook/voxbridge-test"
   ```
3. Run tests:
   ```bash
   pytest tests/e2e/test_n8n_real.py -v -m n8n
   ```

## CI/CD Integration

Tests run automatically on GitHub Actions:

- **Unit tests**: Run on every push
- **Integration tests**: Run on every push
- **E2E tests**: Run on pull requests (may need self-hosted runner for GPU)

View workflow: `.github/workflows/test.yml`

## Coverage Reports

Generate coverage reports:

```bash
# HTML coverage report
pytest --cov=. --cov-report=html
open htmlcov/index.html

# Terminal coverage report
pytest --cov=. --cov-report=term-missing

# XML coverage report (for CI)
pytest --cov=. --cov-report=xml
```

## Debugging Tests

### Run with verbose output

```bash
pytest -vv
```

### Run specific test

```bash
pytest tests/unit/test_whisper_client.py::test_connect_success -v
```

### Run with print statements

```bash
pytest -s
```

### Run with debugger

```bash
pytest --pdb
```

### Show local variables on failure

```bash
pytest -l
```

## Detailed Documentation

For comprehensive testing documentation, see:

- **[Testing Framework Summary](TESTING_FRAMEWORK_SUMMARY.md)** - Complete testing framework implementation details, architecture, and design decisions
- **[Integration Test Summary](INTEGRATION_TEST_SUMMARY.md)** - Integration test results with latency benchmarks (16ms TTS TTFB, 244ms full conversation loop)
- **[Test Results & Coverage](TEST_RESULTS.md)** - Comprehensive test results showing 61% coverage with 86 unit tests and 16 integration tests passing

## Best Practices

1. **Keep unit tests fast** - Use mocks, no I/O
2. **Test one thing per test** - Clear, focused tests
3. **Use descriptive names** - `test_whisper_client_reconnects_on_failure`
4. **Arrange-Act-Assert** - Clear test structure
5. **Use fixtures** - Share common setup
6. **Mark tests appropriately** - Use pytest markers
7. **Clean up resources** - Use async context managers
8. **Assert meaningful messages** - Help debugging

## Troubleshooting

### Tests hang indefinitely

- Check for missing `await` keywords
- Use `pytest-timeout`: `pytest --timeout=10`
- Check for unclosed resources

### Mock server connection refused

- Ensure server is fully started (increase `await asyncio.sleep(0.5)` in server startup)
- Check port conflicts
- Use different ports for parallel test runs

### Coverage not working

- Install `pytest-cov`: `pip install pytest-cov`
- Check `.coveragerc` or `pytest.ini` configuration
- Ensure source paths are correct

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [httpx testing](https://www.python-httpx.org/async/)
- [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/)
