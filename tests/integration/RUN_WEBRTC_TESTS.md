# Quick Reference: Running WebRTC Integration Tests

## Test File
`tests/integration/test_webrtc_audio_format.py`

## Prerequisites
- Docker containers running (`docker compose up -d`)
- PyAV installed in container (already in `requirements-bot.txt`)
- Database migrations applied

## Quick Commands

### Run All Tests (Recommended)
```bash
docker exec voxbridge-api ./test.sh tests/integration/test_webrtc_audio_format.py -v
```

### Run Specific Test Class
```bash
# P0: End-to-end flow (3 tests)
docker exec voxbridge-api ./test.sh tests/integration/test_webrtc_audio_format.py::TestWebRTCEndToEnd -v

# P0: Format routing (2 tests)
docker exec voxbridge-api ./test.sh tests/integration/test_webrtc_audio_format.py::TestFormatRouting -v

# P0: Concurrent formats (2 tests)
docker exec voxbridge-api ./test.sh tests/integration/test_webrtc_audio_format.py::TestConcurrentFormats -v

# P1: Error handling (3 tests)
docker exec voxbridge-api ./test.sh tests/integration/test_webrtc_audio_format.py::TestWebRTCErrors -v

# P2: Performance (2 tests)
docker exec voxbridge-api ./test.sh tests/integration/test_webrtc_audio_format.py::TestWebRTCLatency -v
```

### Run Single Test
```bash
docker exec voxbridge-api ./test.sh \
  tests/integration/test_webrtc_audio_format.py::TestWebRTCEndToEnd::test_browser_to_transcript_pcm_format -v
```

### Run with Print Statements
```bash
docker exec voxbridge-api ./test.sh tests/integration/test_webrtc_audio_format.py -v -s
```

### Generate Coverage Report
```bash
docker exec voxbridge-api ./test.sh tests/integration/test_webrtc_audio_format.py \
  --cov=src/voice/webrtc_handler \
  --cov=src/services/stt_service \
  --cov-report=html \
  --cov-report=term-missing
```

View coverage:
```bash
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Expected Output

### Success (All Passing)
```
============================================================ test session starts =============================================================
collected 12 items

tests/integration/test_webrtc_audio_format.py::TestWebRTCEndToEnd::test_browser_to_transcript_pcm_format PASSED                      [  8%]
tests/integration/test_webrtc_audio_format.py::TestWebRTCEndToEnd::test_webm_decode_to_transcription PASSED                          [ 16%]
tests/integration/test_webrtc_audio_format.py::TestWebRTCEndToEnd::test_full_conversation_loop_webrtc PASSED                         [ 25%]
tests/integration/test_webrtc_audio_format.py::TestFormatRouting::test_format_indicator_sent_on_first_audio PASSED                   [ 33%]
tests/integration/test_webrtc_audio_format.py::TestFormatRouting::test_pcm_format_reaches_whisperx PASSED                            [ 41%]
tests/integration/test_webrtc_audio_format.py::TestConcurrentFormats::test_discord_and_webrtc_concurrent PASSED                      [ 50%]
tests/integration/test_webrtc_audio_format.py::TestConcurrentFormats::test_format_isolation_between_sessions PASSED                  [ 58%]
tests/integration/test_webrtc_audio_format.py::TestWebRTCErrors::test_corrupted_webm_error_recovery PASSED                           [ 66%]
tests/integration/test_webrtc_audio_format.py::TestWebRTCErrors::test_incomplete_webm_buffering PASSED                               [ 75%]
tests/integration/test_webrtc_audio_format.py::TestWebRTCErrors::test_browser_disconnect_cleanup PASSED                              [ 83%]
tests/integration/test_webrtc_audio_format.py::TestWebRTCLatency::test_webm_decode_latency_under_100ms PASSED                        [ 91%]
tests/integration/test_webrtc_audio_format.py::TestWebRTCLatency::test_end_to_end_latency_under_2s PASSED                            [100%]

============================================================ 12 passed in 3.45s ==============================================================
```

## Test Categories

| Priority | Category | Tests | Description |
|----------|----------|-------|-------------|
| P0 | End-to-End | 3 | Complete WebRTC flow validation |
| P0 | Format Routing | 2 | PCM format indicator validation |
| P0 | Concurrent | 2 | Discord + WebRTC isolation |
| P1 | Error Handling | 3 | Corrupted/incomplete WebM recovery |
| P2 | Performance | 2 | Latency benchmarks |
| **TOTAL** | - | **12** | - |

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'av'`
**Solution**: PyAV not installed in container
```bash
docker exec voxbridge-api pip install av
```

### Issue: Database connection errors
**Solution**: Ensure PostgreSQL container is running
```bash
docker compose ps voxbridge-postgres
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "SELECT 1;"
```

### Issue: Mock WhisperX server not starting
**Solution**: Check port availability
```bash
docker exec voxbridge-api netstat -tuln | grep 14901
```

### Issue: Tests hang indefinitely
**Solution**: Check for deadlocks in async code
```bash
# Add timeout to pytest
docker exec voxbridge-api ./test.sh tests/integration/test_webrtc_audio_format.py -v --timeout=30
```

## Debugging

### View Test Logs
```bash
docker exec voxbridge-api ./test.sh tests/integration/test_webrtc_audio_format.py -v -s --log-cli-level=DEBUG
```

### Run Tests Outside Docker (Local Development)
```bash
# Ensure dependencies installed
pip install -r requirements-bot.txt -r requirements-test.txt

# Run tests
pytest tests/integration/test_webrtc_audio_format.py -v
```

## Performance Benchmarks

Expected latencies (from test assertions):
- **WebM decode**: <100ms per frame
- **Browser → Transcript**: <500ms
- **End-to-end**: <2s (decode + STT + LLM + TTS)

## Next Steps

1. **Run tests**: Verify all 12 tests pass
2. **Review coverage**: Ensure >95% coverage on WebRTC path
3. **Fix failures**: Debug any failing tests
4. **Integrate CI/CD**: Add to automated test pipeline
5. **Deploy**: Merge to production

## Resources

- **Test Report**: `TEST_RESULTS_WEBRTC_INTEGRATION.md`
- **Implementation Summary**: `INTEGRATION_TEST_IMPLEMENTATION_SUMMARY.md`
- **Test File**: `tests/integration/test_webrtc_audio_format.py`
- **Fixtures**: `tests/fixtures/audio_samples.py`
- **Mocks**: `tests/mocks/mock_whisperx_server.py`

---

**Quick Start**: `docker exec voxbridge-api ./test.sh tests/integration/test_webrtc_audio_format.py -v`
