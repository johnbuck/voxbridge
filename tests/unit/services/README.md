# VoxBridge 2.0 Service Unit Tests

Comprehensive unit test suite for VoxBridge 2.0 service layer components.

## Quick Start

```bash
# Run all service tests
pytest tests/unit/services/ -v

# Run with coverage report
pytest tests/unit/services/ --cov=src.services --cov-report=term-missing

# Run specific service tests
pytest tests/unit/services/test_conversation_service.py -v
```

## Test Files

| Service | File | Tests | Lines | Coverage Target |
|---------|------|-------|-------|-----------------|
| **ConversationService** | [test_conversation_service.py](./test_conversation_service.py) | 25 | 1,128 | 90%+ |
| **STTService** | [test_stt_service.py](./test_stt_service.py) | 27 | 784 | 90%+ |
| **LLMService** | [test_llm_service.py](./test_llm_service.py) | 23 | 742 | 90%+ |
| **TTSService** | [test_tts_service.py](./test_tts_service.py) | 24 | 735 | 90%+ |
| **TOTAL** | **4 files** | **99 tests** | **3,389 lines** | **90%+** |

## Documentation

- **[TEST_INSTRUCTIONS.md](./TEST_INSTRUCTIONS.md)** - Complete testing guide (571 lines)
  - Running tests (all commands)
  - Test organization (breakdown by category)
  - Debugging techniques
  - Mocking strategies
  - Common patterns
  - CI/CD integration
  - Troubleshooting
  - Extending tests

- **[SUMMARY.md](./SUMMARY.md)** - Implementation summary (419 lines)
  - Test coverage overview
  - Deliverables
  - Testing philosophy
  - Key patterns
  - Metrics & quality
  - Next steps

## Test Categories (99 total)

### ConversationService (25 tests)
- Initialization (4)
- Session Management (3)
- Context Management (4)
- Message Management (2)
- Cache Management (3)
- Agent Configuration (1)
- Concurrency (2)
- Error Handling (1)
- Cleanup (5)

### STTService (27 tests)
- Initialization (3)
- Connection Management (5)
- Audio Streaming (4)
- Callback System (5)
- Status Monitoring (2)
- Metrics (2)
- Concurrency (1)
- Reconnection (1)
- Cleanup (4)

### LLMService (23 tests)
- Initialization (4)
- Provider Routing (2)
- Streaming (3)
- Fallback Logic (4)
- Health Monitoring (3)
- Error Handling (4)
- Cleanup (3)

### TTSService (24 tests)
- Initialization (3)
- Synthesis (5)
- Health Monitoring (2)
- Voice Management (2)
- Metrics (3)
- Cancellation (3)
- Error Handling (3)
- Cleanup (3)

## Test Coverage by Type

- **Initialization Tests**: 14 tests
- **Core Functionality**: 31 tests
- **Error Handling**: 15 tests
- **Edge Cases**: 12 tests
- **Concurrency**: 6 tests
- **Cleanup**: 21 tests

## Shared Fixtures

All tests can use fixtures from `../../conftest.py`:

### Database Fixtures
- `mock_db_session` - Mock SQLAlchemy async session
- `mock_agent` - Mock Agent model
- `mock_session_model` - Mock Session model
- `mock_conversation` - Mock Conversation model

### Service Fixtures
- `mock_llm_provider` - Mock LLM provider
- `mock_whisperx_connection` - Mock WhisperX WebSocket
- `mock_httpx_client` - Mock httpx AsyncClient

## Example Usage

```python
@pytest.mark.asyncio
async def test_conversation_service():
    """Test ConversationService with mocked database"""
    service = ConversationService()

    session_id = str(uuid4())
    agent_id = str(uuid4())

    with patch('src.services.conversation_service.get_db_session') as mock_db:
        # Mock database session
        mock_db_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_db_ctx

        # Configure mock behavior
        mock_db_ctx.execute = AsyncMock(return_value=mock_result)
        mock_db_ctx.commit = AsyncMock()

        # Test service
        session = await service.get_or_create_session(
            session_id=session_id,
            user_id="test_user",
            agent_id=agent_id
        )

        assert session_id in service._cache
```

## Running Specific Tests

```bash
# Run all ConversationService tests
pytest tests/unit/services/test_conversation_service.py -v

# Run specific test
pytest tests/unit/services/test_conversation_service.py::test_init_with_defaults -v

# Run all tests matching pattern
pytest tests/unit/services/ -k "test_init" -v

# Run with print statements visible
pytest tests/unit/services/ -s

# Run until first failure
pytest tests/unit/services/ -x

# Show slowest tests
pytest tests/unit/services/ --durations=10
```

## Coverage Reports

```bash
# Terminal coverage report
pytest tests/unit/services/ --cov=src.services --cov-report=term-missing

# HTML coverage report (opens in browser)
pytest tests/unit/services/ --cov=src.services --cov-report=html
open htmlcov/index.html

# Coverage for specific service
pytest tests/unit/services/test_conversation_service.py \
  --cov=src.services.conversation_service \
  --cov-report=term-missing
```

## Development Workflow

1. **Make changes** to service code
2. **Run relevant tests** to verify behavior
3. **Check coverage** to ensure adequate testing
4. **Add new tests** if coverage gaps exist
5. **Update documentation** if test categories change

## Test Quality Standards

All tests follow these standards:

- ✅ Clear, descriptive test names
- ✅ Docstrings explaining what is tested
- ✅ All external dependencies mocked
- ✅ Tests are isolated (no shared state)
- ✅ Tests cover happy path and error cases
- ✅ Tests run in < 1 second
- ✅ Tests pass consistently (not flaky)
- ✅ Coverage reports show new code is covered

## Troubleshooting

### Import Errors

```bash
# Ensure you're in VoxBridge root directory
cd /home/wiley/Docker/voxbridge

# Install test dependencies
pip install -r requirements-test.txt
```

### Async Warnings

- Ensure all async functions have `await` when called
- Add `@pytest.mark.asyncio` to async tests
- Use `AsyncMock()` for async methods, not `MagicMock()`

### Database Errors

- Tests should NOT connect to real database
- Verify all `get_db_session()` calls are mocked
- Check `patch` paths match import paths

## CI/CD Integration

### GitHub Actions

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

## Related Documentation

- **[VoxBridge AGENTS.md](../../../AGENTS.md)** - Comprehensive architecture guide
- **[VoxBridge CLAUDE.md](../../../CLAUDE.md)** - Quick reference for Claude Code
- **[Testing Framework Summary](../../TESTING_FRAMEWORK_SUMMARY.md)** - Overall testing approach
- **[Test Results](../../TEST_RESULTS.md)** - Historical test results

## Contributing

When adding new tests:

1. Follow existing test patterns
2. Add tests to appropriate file
3. Update test counts in this README
4. Ensure tests pass: `pytest tests/unit/services/your_test.py -v`
5. Check coverage: `pytest tests/unit/services/ --cov=src.services`

## Questions?

See **[TEST_INSTRUCTIONS.md](./TEST_INSTRUCTIONS.md)** for comprehensive testing guide.

---

**Last Updated**: 2025-10-27
**VoxBridge Version**: 2.0 (Phase 5.8)
**Test Suite Version**: 1.0
**Status**: ✅ Complete
