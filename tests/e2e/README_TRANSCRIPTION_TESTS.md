# WebRTC Transcription Accuracy E2E Tests

Comprehensive end-to-end tests that validate the complete WebRTC audio pipeline produces **accurate transcriptions** (not garbage/corrupted text).

## Overview

These tests validate that:
1. **WebM → PCM decoding** produces correct audio format
2. **WhisperX STT** receives valid audio data
3. **Transcriptions are accurate** (not gibberish like "oh", "Yeah.", etc.)
4. **Multi-chunk streaming** produces coherent results
5. **Silence detection** triggers finalization correctly

## Test Coverage

### `test_webrtc_transcription_accuracy.py`

**Test 1: Known Audio Produces Correct Transcript**
- Validates known audio transcribes to expected content
- Uses TTS-generated audio with predictable text
- Fuzzy matching to handle WhisperX variations
- Detects garbage transcriptions

**Test 2: Transcription Not Corrupted**
- Validates PCM format doesn't produce garbage
- Catches audio format bugs (planar vs interleaved)
- Checks for known corruption patterns

**Test 3: Multi-Chunk Streaming Coherent Transcript**
- Streams 20+ WebM chunks
- Validates buffer accumulation works correctly
- Checks codec state is maintained

**Test 4: Silence Detection Triggers Finalization**
- Validates silence threshold works
- Checks transcript finalization occurs
- Tests LLM routing after finalization

## Prerequisites

### Required Services

**Option A: Mocked WhisperX (No GPU Required)**
```bash
# No services needed - tests use mocked STT responses
pytest tests/e2e/test_webrtc_transcription_accuracy.py -v
```

**Option B: Real WhisperX (GPU Required)**
```bash
# Start WhisperX server
docker compose up -d voxbridge-whisperx

# Wait for model to load (first run: 2-5 minutes)
docker logs voxbridge-whisperx --tail 50 --follow

# Run tests with real WhisperX
pytest tests/e2e/test_webrtc_transcription_accuracy.py -v --use-real-whisperx
```

### Optional: Generate Audio Fixtures

For more realistic testing, generate audio fixtures using Chatterbox TTS:

```bash
# Start Chatterbox TTS server
cd ../chatterbox-tts-api
docker compose up -d

# Generate audio fixtures
python -m tests.fixtures.tts_audio_generator

# This creates:
# - tests/fixtures/audio/hello_world.webm
# - tests/fixtures/audio/what_time_is_it.webm
# - tests/fixtures/audio/long_sentence.webm
# - tests/fixtures/audio/test_phrase.webm
```

## Running Tests

### Quick Start (Mocked WhisperX)

```bash
# Run all transcription accuracy tests
pytest tests/e2e/test_webrtc_transcription_accuracy.py -v

# Run specific test
pytest tests/e2e/test_webrtc_transcription_accuracy.py::TestWebRTCTranscriptionAccuracy::test_known_audio_produces_correct_transcript -v

# Run with output visible
pytest tests/e2e/test_webrtc_transcription_accuracy.py -v -s
```

### With Real WhisperX (GPU)

```bash
# Start services
docker compose up -d voxbridge-whisperx

# Wait for WhisperX to be ready
curl http://localhost:4902/health

# Run tests with real STT
pytest tests/e2e/test_webrtc_transcription_accuracy.py -v --use-real-whisperx
```

### Test Markers

```bash
# Run only E2E tests
pytest -m e2e tests/e2e/test_webrtc_transcription_accuracy.py -v

# Run only async tests
pytest -m asyncio tests/e2e/test_webrtc_transcription_accuracy.py -v
```

## Expected Output

### Test 1: Known Audio

```
🎯 TRANSCRIPTION ACCURACY TEST
   Session: 12345678-1234-5678-1234-567812345678
   Expected content: "hello world"
   Using real WhisperX: False

   Decoding WebM audio (2,345 bytes)...
   ✅ Decoded to 192,000 bytes PCM
   Sending PCM to WhisperX...

   📋 Partial: "hello"
   📝 FINAL: "hello world"

   📊 RESULTS:
   Transcripts received: 2
   Final transcript: "hello world"
   ✅ Transcription accuracy validated
```

### Test 2: Corruption Check

```
🎯 CORRUPTION TEST
   Validating PCM format produces clean transcripts

   ✅ PCM validation passed (384,000 bytes)
   Transcript: "this is a test of the transcription system"

   📊 RESULTS:
   ✅ No corruption detected (9 clean words)
```

### Test 3: Multi-Chunk Streaming

```
🎯 MULTI-CHUNK STREAMING TEST
   Streaming 25 WebM chunks...

   📊 STREAMING RESULTS:
   Chunks sent: 25
   Chunks decoded: 25
   Success rate: 100.0%
   Total PCM: 480,000 bytes
   PCM chunks to STT: 5
   ✅ Multi-chunk streaming validated
```

### Test 4: Silence Detection

```
🎯 SILENCE DETECTION TEST
   Sending audio chunk...
   Waiting for silence detection (300ms)...

   📊 RESULTS:
   Finalization triggered: True
   ✅ Silence detection validated
```

## Troubleshooting

### Issue: "No transcripts received"

**Cause**: WhisperX not running or not reachable

**Fix**:
```bash
# Check WhisperX status
docker ps | grep whisperx

# Check WhisperX logs
docker logs voxbridge-whisperx --tail 50

# Restart WhisperX
docker compose restart voxbridge-whisperx
```

### Issue: "Transcription is garbage"

**Cause**: Audio format bug (planar vs interleaved PCM)

**Fix**: Check WebRTC handler planar audio conversion
```python
# In webrtc_handler.py line 324-325
if frame.format.is_planar:
    pcm_array = pcm_array.T  # Transpose required
```

### Issue: "Only X chunks decoded"

**Cause**: Buffer clearing bug or codec state issue

**Fix**: Check buffer accumulation strategy
```python
# In webrtc_handler.py line 263
self.webm_buffer.extend(webm_chunk)  # Accumulate ALL chunks

# Line 267
pcm_data = self._extract_new_pcm_audio()  # Extract only NEW frames
```

### Issue: "PyAV not installed"

**Fix**:
```bash
pip install av numpy
```

### Issue: "Chatterbox not available"

**Fix**:
```bash
# Start Chatterbox TTS
cd ../chatterbox-tts-api
docker compose up -d

# Verify
curl http://localhost:4123/health
```

## Test Architecture

### Audio Pipeline Flow

```
Browser MediaRecorder
   ↓ (WebM/Opus chunks, 100ms each)
WebSocket /ws/voice
   ↓ (Binary frames)
WebRTCVoiceHandler._audio_loop()
   ↓ (Buffer accumulation)
PyAV Decode (WebM → PCM)
   ↓ (Planar → Interleaved conversion)
STTService.send_audio(pcm_data, format='pcm')
   ↓ (WebSocket to WhisperX)
WhisperX Server (GPU/CPU)
   ↓ (Transcription)
Callback: on_transcript(text, is_final)
   ↓ (Validation)
TranscriptionValidator.is_valid_speech()
```

### Mock vs Real WhisperX

**Mocked Mode** (default):
- No GPU required
- Fast execution (< 1s per test)
- Predictable transcripts
- Tests pipeline logic only

**Real Mode** (`--use-real-whisperx`):
- Requires GPU (RTX 3080+)
- Slower execution (2-5s per test)
- Actual STT validation
- End-to-end accuracy testing

## Key Validation Logic

### TranscriptionValidator.is_valid_speech()

Detects garbage transcriptions:

```python
# Known garbage patterns
garbage_patterns = [
    'hmm', 'uhm', 'uh', 'um',  # Filler sounds
    'oh', 'yeah', 'ah', 'eh',  # Common garbage
    'music', 'static', 'inaudible'  # Noise
]

# Must have valid words
validity_ratio = len(valid_words) / len(words)
return validity_ratio >= 0.5  # 50% threshold
```

### TranscriptionValidator.contains_expected_content()

Fuzzy content matching:

```python
# Normalize text (lowercase, no punctuation)
expected_words = set(normalize(expected).split())
transcript_words = set(normalize(transcript).split())

# Count matching words
matching = expected_words.intersection(transcript_words)
match_ratio = len(matching) / len(expected_words)

return match_ratio >= threshold  # 50% default
```

## Adding New Test Cases

### 1. Add Audio Fixture

```python
# In KnownAudioSamples class
@staticmethod
def get_my_custom_audio() -> bytes:
    """Audio for custom test phrase"""
    # Option A: Generate with TTS
    generator = TTSAudioGenerator()
    return await generator.generate_webm("My custom phrase")

    # Option B: Load pre-generated
    return PreGeneratedAudioSamples._load_audio("custom.webm")

@staticmethod
def get_expected_transcript_my_custom() -> str:
    return "my custom phrase"
```

### 2. Add Test Case

```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_my_custom_scenario(
    self,
    mock_conversation_service,
    mock_stt_service,
    caplog
):
    """Test custom scenario"""
    # Load audio
    audio = KnownAudioSamples.get_my_custom_audio()
    expected = KnownAudioSamples.get_expected_transcript_my_custom()

    # Setup mocks
    # ... (copy from existing tests)

    # Process audio
    # ... (copy pipeline logic)

    # Validate
    validator = TranscriptionValidator()
    assert validator.contains_expected_content(transcript, expected)
```

## Performance Benchmarks

### Expected Latencies (Mocked)

- **Test 1 (Known Audio)**: < 0.5s
- **Test 2 (Corruption)**: < 0.3s
- **Test 3 (Multi-Chunk)**: < 1.0s
- **Test 4 (Silence)**: < 0.8s

### Expected Latencies (Real WhisperX)

- **Test 1 (Known Audio)**: 2-5s (GPU), 5-10s (CPU)
- **Test 2 (Corruption)**: 1-3s
- **Test 3 (Multi-Chunk)**: 3-8s
- **Test 4 (Silence)**: 2-5s

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: E2E Transcription Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install dependencies
        run: pip install -r requirements-test.txt

      - name: Run mocked tests (no GPU)
        run: |
          pytest tests/e2e/test_webrtc_transcription_accuracy.py -v
```

## Related Documentation

- [WebRTC Handler](../../src/voice/webrtc_handler.py) - Main audio processing logic
- [WhisperX Server](../../src/whisper_server.py) - STT server implementation
- [Audio Fixtures](../fixtures/audio_samples.py) - Audio generation utilities
- [Testing Framework](../README.md) - Overall testing guide

## Support

For issues or questions:
1. Check [CLAUDE.md](../../CLAUDE.md) for architecture context
2. Review [AGENTS.md](../../AGENTS.md) for development patterns
3. Inspect Docker logs: `docker logs voxbridge-whisperx --tail 100`
4. Enable debug logging: `caplog.set_level(logging.DEBUG)`
