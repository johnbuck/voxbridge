# Streaming Configuration with Chunking Strategies

**Status**: ✅ Implemented (October 2025)
**Latency Improvement**: ~68% reduction (from ~6.8s to ~2-3s)
**Branch**: `feature/sentence-level-streaming` (legacy name, kept for compatibility)

## Overview

Streaming configuration is a major optimization that processes and plays AI responses chunk-by-chunk with configurable chunking strategies (sentence/paragraph/word/fixed) instead of waiting for the complete response. This dramatically reduces perceived latency and creates a more natural, conversational experience.

### Key Metrics

**Before (Full Response Buffering):**
- Total latency: ~6.8 seconds
- LLM generation: ~4-5s
- TTS synthesis: ~1-2s
- User waits until entire response is generated and synthesized

**After (Streaming with Chunking):**
- First chunk latency: ~2-3 seconds
- LLM chunk streaming: continuous
- TTS synthesis: parallel (up to 3 concurrent)
- Audio playback: sequential FIFO
- Subsequent chunks: near-instant (already synthesized)

**Improvement**: 68% reduction in time-to-first-audio

## Architecture Components

### 1. SentenceParser (`src/services/sentence_parser.py`)

Smart sentence boundary detection with edge case handling.

**Features:**
- Detects sentence endings (`.`, `!`, `?`)
- Handles abbreviations (Mr., Dr., e.g., etc.)
- Handles numbers (1.5, 3.14, $1,000.00)
- Handles initials (J.K. Rowling)
- Handles ellipsis (...)
- Minimum chunk length buffering (prevents very short chunks)
- Incremental chunk processing (for LLM streaming)

**Usage:**
```python
from src.services.sentence_parser import SentenceParser

parser = SentenceParser(min_chunk_length=10)

# Process incremental chunks (from LLM streaming)
sentences = parser.add_chunk("Hello world! ")
# Returns: ["Hello world!"]

sentences = parser.add_chunk("How are you? ")
# Returns: ["How are you?"]

# Get final incomplete sentence
final = parser.finalize()
# Returns any remaining buffered text
```

**Edge Cases Handled:**

| Input | Expected Output | Reason |
|-------|----------------|---------|
| `"Hello Mr. Smith."` | `["Hello Mr. Smith."]` | Mr. is abbreviation |
| `"Pi is 3.14. Great!"` | `["Pi is 3.14.", "Great!"]` | Decimal number |
| `"J.K. Rowling wrote it."` | `["J.K. Rowling wrote it."]` | Initials |
| `"I think... maybe."` | `["I think... maybe."]` | Ellipsis continuation |
| `"Hi. How are you?"` | `["Hi. How are you?"]` | Short sentence buffered |

### 2. TTSQueueManager (`src/services/tts_queue_manager.py`)

Manages concurrent TTS synthesis with semaphore-based limiting.

**Features:**
- Async queue with worker pool
- Semaphore-based concurrency control (default: 3 concurrent)
- Per-sentence metadata tracking
- Cancellation strategies (cancel_all, cancel_pending, cancel_after)
- Error callbacks
- Metrics tracking (enqueued, completed, failed, cancelled)

**Architecture:**
```
[Sentence Queue] → [Worker Pool (3)] → [TTS Service]
                      ↓ Semaphore Limit
                    [Audio Bytes + Metadata]
                      ↓ Callback
                   [Audio Playback Queue]
```

**Usage:**
```python
from src.services.tts_queue_manager import TTSQueueManager

async def on_tts_complete(audio_bytes: bytes, metadata: dict):
    # Audio is ready, enqueue to playback
    await playback_queue.enqueue_audio(audio_bytes, metadata)

async def on_tts_error(error: Exception, metadata: dict):
    logger.error(f"TTS failed: {error}")

manager = TTSQueueManager(
    max_concurrent=3,
    tts_service=tts_service,
    on_complete=on_tts_complete,
    on_error=on_tts_error
)

await manager.start()

# Enqueue sentences as they're detected
task_id = await manager.enqueue_sentence(
    sentence="Hello world!",
    session_id="session-123",
    voice_id="voice-456",
    speed=1.0,
    metadata={"user_id": "user-789"}
)
```

**Cancellation Strategies:**

| Strategy | Behavior | Use Case |
|----------|----------|----------|
| `cancel_all()` | Cancel all pending tasks | Immediate stop |
| `cancel_pending()` | Cancel pending, keep active | Finish current sentence |
| `cancel_after(N)` | Keep N tasks, cancel rest | Drain a few more sentences |

### 3. AudioPlaybackQueue (`src/services/audio_playback_queue.py`)

Sequential FIFO audio playback with Discord voice integration.

**Features:**
- FIFO (First-In-First-Out) ordering
- Sequential playback (one at a time)
- Interruption strategies (immediate, graceful, drain)
- Discord voice client integration (FFmpegPCMAudio)
- Gap-free transitions
- Completion callbacks
- Metrics tracking (total_queued, total_played, total_interrupted)

**Architecture:**
```
[Audio Queue] → [Playback Worker] → [Discord Voice Client]
                      ↓ Sequential (one at a time)
                  [FFmpegPCMAudio]
                      ↓ Discord voice channel
                   [Audio Output]
```

**Usage:**
```python
from src.services.audio_playback_queue import AudioPlaybackQueue

async def on_playback_complete(metadata: dict):
    logger.info(f"Finished playing: {metadata.get('sentence')}")

async def on_playback_error(error: Exception, metadata: dict):
    logger.error(f"Playback failed: {error}")

queue = AudioPlaybackQueue(
    voice_client=discord_voice_client,
    on_complete=on_playback_complete,
    on_error=on_playback_error
)

await queue.start()

# Enqueue audio as it's synthesized
chunk_id = await queue.enqueue_audio(
    audio_bytes=audio_data,
    metadata={"sentence": "Hello world!", "task_id": task_id}
)
```

**Interruption Strategies:**

| Strategy | Behavior | Audio Experience |
|----------|----------|-----------------|
| `immediate` | Stop now, clear all | Hard cut-off |
| `graceful` | Finish current, clear rest | Natural sentence end |
| `drain` | Play 1-2 more, clear rest | Brief continuation |

### 4. Discord Plugin Integration (`src/plugins/discord_plugin.py`)

Full integration of streaming components into Discord voice pipeline.

**Flow:**
```
[User Speaking] → [WhisperX STT] → [LLM Provider]
                                      ↓ Streaming chunks
                                [SentenceParser]
                                      ↓ Complete sentences
                                [TTSQueueManager]
                                      ↓ Concurrent synthesis (3x)
                                [AudioPlaybackQueue]
                                      ↓ Sequential FIFO
                              [Discord Voice Channel]
```

**Key Integration Points:**

1. **LLM Chunk Callback** (`_on_llm_chunk`)
   - Receives streaming chunks from LLM
   - Feeds to SentenceParser
   - Enqueues detected sentences to TTS

2. **TTS Completion Callback** (`_on_tts_sentence_complete`)
   - Receives synthesized audio
   - Enqueues to AudioPlaybackQueue
   - Tracks sentence-to-audio latency

3. **User Interruption Handler** (`_handle_interruption`)
   - Detects when user starts speaking
   - Applies interruption strategy
   - Cancels TTS queue and/or playback

4. **Error Handler** (`_on_tts_sentence_error`)
   - Handles TTS failures
   - Applies error recovery strategy
   - Tracks retry counts and fallback state

## Error Handling Strategies

### Strategy: Skip

**Behavior**: Continue to next sentence on error

```python
self.error_strategy = 'skip'

# TTS fails on sentence 2
# → Log error, continue to sentence 3
```

**Use Case**: Non-critical responses where continuity matters

### Strategy: Retry

**Behavior**: Retry failed sentence up to N times (default: 2)

```python
self.error_strategy = 'retry'
self.max_retries = 2

# TTS fails on sentence 2
# → Retry sentence 2 (attempt 2)
# → If still fails, retry again (attempt 3)
# → If still fails, skip
```

**Use Case**: Transient errors (network glitches, temporary service issues)

### Strategy: Fallback

**Behavior**: Cancel all remaining sentences on error

```python
self.error_strategy = 'fallback'

# TTS fails on sentence 2
# → Cancel sentences 3, 4, 5, ...
# → Stop streaming for this response
```

**Use Case**: Critical errors where partial responses are problematic

### Per-Task Retry Tracking

Retry counts are tracked per task_id to prevent infinite retries:

```python
self.sentence_retry_counts: Dict[str, int] = {}  # task_id → retry_count
self.fallback_triggered: Dict[str, bool] = {}  # session_id → fallback_triggered

# On error
retry_count = self.sentence_retry_counts.get(task_id, 0)
if retry_count < self.max_retries:
    retry_count += 1
    self.sentence_retry_counts[task_id] = retry_count
    # Re-enqueue with same task_id
```

## User Interruption Handling

### Detection

Interruption is detected when:
1. User starts speaking (triggers `_handle_user_speaking()`)
2. TTS queue has pending sentences OR
3. Audio playback queue is actively playing

```python
has_queued_tts = self.tts_queue_manager.queue.qsize() > 0
has_active_playback = (
    guild_id in self.audio_playback_queues and
    self.audio_playback_queues[guild_id].queue.qsize() > 0
)

if has_queued_tts or has_active_playback:
    await self._handle_interruption(guild_id, user_id, username)
```

### Strategies

#### Immediate Interruption

**Effect**: Hard stop, clear everything

```python
await self.tts_queue_manager.cancel_all()
await self.audio_playback_queues[guild_id].stop_playback('immediate')
```

**Metrics**: Increments `interruption_count`

#### Graceful Interruption

**Effect**: Finish current sentence, cancel rest

```python
await self.tts_queue_manager.cancel_pending()
await self.audio_playback_queues[guild_id].stop_playback('graceful')
```

**User Experience**: Natural sentence completion before stopping

#### Drain Interruption

**Effect**: Play 1-2 more sentences, cancel rest

```python
await self.tts_queue_manager.cancel_after(num_to_keep=2)
await self.audio_playback_queues[guild_id].stop_playback('drain')
```

**User Experience**: Brief continuation, then stop

## Metrics and Monitoring

### New Streaming Metrics

Added to `MetricsTracker` (`src/api/server.py`):

**Latency Metrics:**
- `sentence_detection_latencies` - Time to detect sentence boundaries (ms)
- `sentence_tts_latencies` - TTS synthesis time per sentence (s)
- `audio_queue_wait_latencies` - Time waiting in audio queue (ms)
- `sentence_to_audio_latencies` - End-to-end sentence → audio (s)

**Counters:**
- `sentences_detected` - Total sentences detected from LLM chunks
- `sentences_synthesized` - Total sentences successfully synthesized
- `sentences_failed` - Total TTS failures
- `sentences_retried` - Total retry attempts
- `interruption_count` - Total user interruptions
- `streaming_sessions` - Total streaming sessions started

**Recording Metrics:**

```python
# Sentence detection
self.metrics.record_sentence_detection(latency_ms)

# TTS completion
self.metrics.record_sentence_tts(latency_s, success=True)

# Sentence-to-audio end-to-end
self.metrics.record_sentence_to_audio(latency_s)

# Streaming session start
self.metrics.record_streaming_session()
```

### Percentile Calculations

Metrics support percentile queries:

```python
stats = self.metrics.get_stats()

# Example output:
{
    "latencies": {
        "sentence_detection": {
            "avg": 2.5,
            "p50": 2.0,
            "p95": 5.0,
            "p99": 8.0,
            "count": 150
        },
        "sentence_tts": {
            "avg": 0.8,
            "p50": 0.7,
            "p95": 1.2,
            "p99": 1.5,
            "count": 145
        }
    },
    "counters": {
        "sentences_detected": 150,
        "sentences_synthesized": 145,
        "sentences_failed": 3,
        "sentences_retried": 2,
        "interruptions": 5,
        "streaming_sessions": 12
    }
}
```

## Configuration

### Environment Variables

```bash
# Streaming mode (default: true)
USE_STREAMING=true

# Clause splitting (default: true)
USE_CLAUSE_SPLITTING=true

# Chunking strategy (default: sentence)
# Options: sentence, paragraph, word, fixed
STREAMING_CHUNKING_STRATEGY=sentence

# Minimum chunk length (default: 10, range: 5-200)
STREAMING_MIN_CHUNK_LENGTH=10

# TTS concurrency (default: 3)
STREAMING_MAX_CONCURRENT_TTS=3

# Error handling
STREAMING_ERROR_STRATEGY=retry  # skip, retry, fallback

# Interruption handling
STREAMING_INTERRUPTION_STRATEGY=graceful  # immediate, graceful, drain
```

### Agent Configuration

Agents can override streaming settings:

```python
agent = Agent(
    name="Helpful Assistant",
    streaming_enabled=True,
    tts_voice="voice-123",
    tts_rate=1.0,
    tts_pitch=1.0
)
```

## Performance Characteristics

### Latency Breakdown

| Stage | Time | Cumulative | Notes |
|-------|------|-----------|-------|
| LLM first chunk | ~500ms | 500ms | From OpenRouter/Local LLM |
| Sentence detection | <10ms | 510ms | Regex parsing |
| TTS synthesis | ~800ms | 1310ms | Chatterbox API |
| Audio queuing | <5ms | 1315ms | Memory operation |
| Playback start | ~50ms | 1365ms | Discord voice setup |
| **First audio** | **~1.4s** | | **User hears first sentence** |

### Concurrency Benefits

**Without Concurrency** (sequential):
- 10 sentences × 800ms each = 8 seconds total

**With Concurrency** (3 concurrent):
- Batch 1 (3 sentences): 800ms
- Batch 2 (3 sentences): 800ms
- Batch 3 (3 sentences): 800ms
- Batch 4 (1 sentence): 800ms
- **Total: 3.2 seconds** (60% faster)

### Memory Usage

| Component | Memory | Notes |
|-----------|--------|-------|
| SentenceParser | ~1KB | Text buffer |
| TTSQueueManager | ~10KB | Queue + metadata |
| AudioPlaybackQueue | ~50KB per chunk | Audio data |
| **Total per session** | **~100KB** | Minimal overhead |

## Testing

### Test Coverage

- **Unit Tests**: 25 test classes, ~60 tests
  - `test_sentence_parser.py` - 11 classes, edge cases
  - `test_tts_queue_manager.py` - 7 classes, concurrency
  - `test_audio_playback_queue.py` - 7 classes, FIFO/interruption

- **Integration Tests**: 13 test classes, ~35 tests
  - `test_streaming_pipeline.py` - Full pipeline flow
  - `test_discord_streaming.py` - Discord integration

- **E2E Tests**: 8 test classes, ~20 tests
  - `test_streaming_e2e.py` - Real services (requires Docker)

### Running Tests

```bash
# Unit tests
./test.sh tests/unit/test_sentence_parser.py -v
./test.sh tests/unit/test_tts_queue_manager.py -v
./test.sh tests/unit/test_audio_playback_queue.py -v

# Integration tests (requires mocks)
./test.sh tests/integration/test_streaming_pipeline.py -v
./test.sh tests/integration/test_discord_streaming.py -v

# E2E tests (requires running services)
RUN_E2E_TESTS=1 ./test.sh tests/e2e/test_streaming_e2e.py -v

# All tests with coverage
./test.sh tests/ --cov=src --cov-report=html --cov-report=term
```

## Migration Guide

### From Full Response Buffering

**Before:**
```python
# Wait for complete LLM response
full_response = await llm_service.generate(prompt)

# Synthesize entire response
audio_bytes = await tts_service.synthesize(full_response)

# Play audio
await voice_client.play(audio_bytes)
```

**After:**
```python
# Initialize streaming components
parser = SentenceParser(min_chunk_length=10)
tts_manager = TTSQueueManager(max_concurrent=3, ...)
playback_queue = AudioPlaybackQueue(voice_client=vc, ...)

await tts_manager.start()
await playback_queue.start()

# Stream LLM response
async for chunk in llm_service.generate_stream(prompt):
    # Detect sentences
    sentences = parser.add_chunk(chunk)

    # Enqueue each sentence to TTS
    for sentence in sentences:
        await tts_manager.enqueue_sentence(
            sentence=sentence,
            session_id=session_id,
            voice_id=voice_id,
            speed=1.0
        )

# Get final sentence
final = parser.finalize()
if final:
    await tts_manager.enqueue_sentence(final, ...)
```

### Backward Compatibility

Legacy full-buffering mode is still supported:

```bash
USE_STREAMING=false  # Disable streaming mode
```

This reverts to the original behavior for testing/comparison.

## Known Limitations

1. **Sentence Detection**: May incorrectly split on some edge cases (URLs, custom abbreviations)
2. **TTS Concurrency**: Limited by Chatterbox API rate limits
3. **Audio Playback**: Sequential only (no concurrent multi-channel playback)
4. **Memory**: Audio chunks retained in queue until played (cleared after playback)

## Future Improvements

1. **Adaptive Concurrency**: Adjust TTS workers based on load
2. **Predictive Queueing**: Pre-synthesize common phrases
3. **Voice Cloning**: Per-agent voice customization
4. **Multilingual Support**: Language-specific sentence detection
5. **WebRTC Frontend**: Browser-based voice interface (partially implemented in Phase 4)

## References

- **Implementation Plan**: `docs/planning/sentence-level-streaming-plan.md`
- **Service Layer**: `docs/architecture/voxbridge-2.0-transformation-plan.md` (Phase 5)
- **WebRTC Integration**: Phase 4 (browser voice interface)
- **Testing Framework**: `tests/README.md`

## Support

For issues or questions:
- Check logs: `docker logs voxbridge-discord --tail 200 | grep -E "(🌊|streaming)"`
- View metrics: `curl http://localhost:4900/metrics | python3 -m json.tool`
- Run tests: `./test.sh tests/unit tests/integration -v`

---

**Last Updated**: October 2025
**Phase**: 10/10 Complete
**Status**: ✅ Production Ready
