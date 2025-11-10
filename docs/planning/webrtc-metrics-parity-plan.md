# WebRTC Performance Metrics Parity Implementation Plan

**Date**: November 8, 2025
**Branch**: `feature/webrtc-metrics-parity`
**Status**: In Progress

## Overview

This plan addresses the 86% metrics gap between Discord bot and WebRTC handler. Currently, Discord tracks 21 unique performance metrics across the voice pipeline, while WebRTC only tracks 3 metrics.

## Problem Statement

**Discord Bot Metrics**: 21 tracked metrics
- Phase 1 (Speech → Transcription): 4 metrics
- Phase 2 (AI Processing): 3 metrics
- Phase 3 (TTS Generation): 3 metrics
- Phase 4 (Audio Playback): 2 metrics
- End-to-End: 2 metrics
- Streaming-Specific: 4 metrics
- Counters: 3 metrics

**WebRTC Handler Metrics**: 3 tracked metrics
- `tts_queue_latency` ✅
- `tts_first_byte_latency` ✅
- `time_to_first_audio` ✅

**Gap**: 18 missing metrics (86% incomplete)

## Missing Metrics Analysis

### High Priority (User-Visible - Must Add)

**Phase 1: Speech → Transcription (4 metrics)**
1. `whisper_connection_latency` - User speaks → WhisperX connected
2. `first_partial_transcript_latency` - Connected → first partial transcript
3. `transcription_duration` - First partial → final transcript
4. `silence_detection_latency` - Last audio → silence detected

**Phase 2: AI Processing (3 metrics)**
5. `ai_generation_latency` - LLM request sent → response received
6. `response_parsing_latency` - Response received → text extracted
7. `n8n_first_chunk_latency` - Time to first LLM chunk (streaming)

**Phase 3: TTS Generation (1 metric)**
8. `tts_generation_latency` - TTS request → audio download complete

**End-to-End (1 metric)**
9. `total_pipeline_latency` - User speaks → audio complete

**Counters (2 metrics)**
10. `transcript_count` - Total transcripts processed
11. `error_count` - Total errors encountered

### Low Priority (N/A for WebRTC)

**Phase 4: Audio Playback**
- `audio_playback_latency` - N/A (browser handles playback)
- `ffmpeg_processing_latency` - N/A (no FFmpeg in browser)

**Streaming-Specific**
- Sentence-level streaming metrics (future enhancement)

## Implementation Plan

### Phase 1: Add Missing Timestamp Tracking

**File**: `src/voice/webrtc_handler.py`
**Location**: `__init__` method (line ~119)

**Current State**:
```python
self.t_start = time.time()
self.t_first_audio = None
self.t_first_transcript = None
self.t_llm_complete = None
```

**Add**:
```python
# Phase 1: Speech → Transcription
self.t_whisper_connected = None     # WhisperX connection time
self.t_first_partial = None         # First partial transcript received
self.t_transcription_complete = None # Final transcript ready

# Phase 2: AI Processing
self.t_ai_start = None              # LLM generation start
self.t_ai_complete = None           # LLM generation complete

# Phase 3+: TTS & Pipeline
self.t_audio_complete = None        # TTS audio streaming complete
```

### Phase 2: Record Phase 1 Metrics (Speech → Transcription)

**Metric 1: WhisperX Connection Latency**

**File**: `src/voice/webrtc_handler.py`
**Location**: After WhisperX connection established (~line 255)

```python
# After successful connection
self.t_whisper_connected = time.time()
latency_s = self.t_whisper_connected - self.t_start
self.metrics.record_whisper_connection_latency(latency_s)
logger.info(f"⏱️ LATENCY [WebRTC - WhisperX Connection]: {latency_s * 1000:.2f}ms")
```

**Metric 2: First Partial Transcript Latency**

**Location**: In `on_transcript` callback (~line 230)

```python
# On first partial transcript
if self.t_first_partial is None:
    self.t_first_partial = time.time()
    if self.t_whisper_connected:
        latency_s = self.t_first_partial - self.t_whisper_connected
        self.metrics.record_first_partial_transcript_latency(latency_s)
        logger.info(f"⏱️ LATENCY [WebRTC - First Partial]: {latency_s * 1000:.2f}ms")
```

**Metric 3: Transcription Duration**

**Location**: After transcription finalized (~line 243)

```python
# After final transcript ready
self.t_transcription_complete = time.time()
if self.t_first_partial:
    duration_s = self.t_transcription_complete - self.t_first_partial
    self.metrics.record_transcription_duration(duration_s)
    logger.info(f"⏱️ LATENCY [WebRTC - Transcription Duration]: {duration_s * 1000:.2f}ms")
```

**Metric 4: Silence Detection Latency**

**Location**: In silence detection logic (~line 590)

```python
# When silence detected
if silence_detected:
    latency_ms = (time.time() - self.last_audio_time) * 1000
    self.metrics.record_silence_detection_latency(latency_ms / 1000)
    logger.info(f"⏱️ LATENCY [WebRTC - Silence Detection]: {latency_ms:.2f}ms")
```

### Phase 3: Record Phase 2 Metrics (AI Processing)

**Metric 5: AI Generation Latency**

**File**: `src/voice/webrtc_handler.py`
**Location**: Around LLM generation (~lines 934, 1058)

```python
# Before LLM generation
self.t_ai_start = time.time()

# After LLM generation complete
self.t_ai_complete = time.time()
latency_s = self.t_ai_complete - self.t_ai_start
self.metrics.record_ai_generation_latency(latency_s)
logger.info(f"⏱️ LATENCY [WebRTC - AI Generation]: {latency_s * 1000:.2f}ms")
```

**Metric 6: Response Parsing Latency**

**Location**: After LLM response parsing

```python
# After extracting text from LLM response
t_parsing_start = time.time()
# ... parsing logic ...
t_parsing_complete = time.time()
latency_ms = (t_parsing_complete - t_parsing_start) * 1000
self.metrics.record_response_parsing_latency(latency_ms / 1000)
logger.info(f"⏱️ LATENCY [WebRTC - Response Parsing]: {latency_ms:.2f}ms")
```

**Metric 7: N8N First Chunk Latency** (if streaming enabled)

**Location**: On first LLM chunk received

```python
# On first streaming chunk
if first_chunk:
    latency_s = time.time() - self.t_ai_start
    self.metrics.record_n8n_first_chunk_latency(latency_s)
    logger.info(f"⏱️ LATENCY [WebRTC - First LLM Chunk]: {latency_s * 1000:.2f}ms")
```

### Phase 4: Record Phase 3 Metrics (TTS Generation)

**Metric 8: TTS Generation Latency**

**File**: `src/voice/webrtc_handler.py`
**Location**: After TTS complete (~line 1242)

```python
# Track TTS start/complete times
t_tts_start = time.time()
# ... TTS synthesis ...
t_tts_complete = time.time()
latency_s = t_tts_complete - t_tts_start
self.metrics.record_tts_generation_latency(latency_s)
logger.info(f"⏱️ LATENCY [WebRTC - TTS Generation]: {latency_s * 1000:.2f}ms")
```

### Phase 5: Record End-to-End Metrics

**Metric 9: Total Pipeline Latency**

**Location**: After TTS audio streaming complete (~line 1270)

```python
# After all TTS audio sent
self.t_audio_complete = time.time()
total_latency = self.t_audio_complete - self.t_start
self.metrics.record_total_pipeline_latency(total_latency)
logger.info(f"⏱️ LATENCY [WebRTC - Total Pipeline]: {total_latency * 1000:.2f}ms")
```

**Metric 10: Transcript Count**

**Location**: After successful transcription processing (~line 860)

```python
# After conversation turn complete
self.metrics.record_transcript()
```

**Metric 11: Error Count**

**Location**: In error handlers throughout file

```python
# In exception handlers
except Exception as e:
    self.metrics.record_error()
    logger.error(f"Error: {e}")
```

### Phase 6: Fix WebSocket Broadcasting

**File**: `src/voice/webrtc_handler.py`
**Location**: After metrics recording (~line 1082)

**Current Implementation** (Partial Metrics):
```python
await ws_manager.broadcast({
    "event": "metrics_update",  # Wrong event name
    "data": {
        "session_id": str(self.session_id),
        "llm_latency_s": latency_s,
        "llm_provider": agent.llm_provider,
        "llm_model": agent.llm_model
    }  # Only partial data
})
```

**New Implementation** (Full Metrics Snapshot):
```python
# Get full metrics snapshot from global tracker
metrics_snapshot = self.metrics.get_metrics()

await ws_manager.broadcast({
    "event": "metrics_updated",  # Match Discord event name
    "data": metrics_snapshot     # Full snapshot with all 21 metrics
})

logger.info("📊 Broadcast full metrics snapshot to frontend")
```

**Broadcast Location**: After recording `total_pipeline_latency` (end of conversation turn)

## Testing Plan

### Unit Tests

**File**: `tests/unit/test_webrtc_handler.py`

1. Run existing 28 WebRTC tests to ensure no regressions
2. Verify new timestamp attributes are initialized
3. Verify metrics are recorded at correct lifecycle points
4. Verify WebSocket broadcasts contain full snapshot

```bash
./test.sh tests/unit/test_webrtc_handler.py -v
```

### Integration Tests

**File**: `tests/integration/test_webrtc_integration.py`

1. Test full voice pipeline with mock services
2. Verify all 21 metrics are populated
3. Verify metrics appear in correct order
4. Verify WebSocket events are broadcast

```bash
./test.sh tests/integration/test_webrtc_integration.py -v
```

### Manual Testing

1. Start VoxBridge services: `docker compose up -d`
2. Open frontend: http://localhost:4903
3. Navigate to VoxBridge page
4. Click microphone button and speak
5. Verify metrics appear in MetricsPanel in real-time
6. Compare WebRTC metrics with Discord metrics (should be identical structure)

**Expected Result**: All 21 metrics visible in frontend with proper values

## Files Modified

**Primary File**:
- `src/voice/webrtc_handler.py` (~50-60 lines added/modified)

**Documentation**:
- `docs/planning/webrtc-metrics-parity-plan.md` (this file)

## Success Criteria

1. ✅ WebRTC handler tracks all 21 metrics (same as Discord)
2. ✅ Metrics are broadcast via WebSocket after each conversation turn
3. ✅ Frontend MetricsPanel displays WebRTC metrics identically to Discord
4. ✅ All existing WebRTC tests pass (28 tests, 100% passing)
5. ✅ No performance regression (latency overhead < 1ms per metric)

## Estimated Effort

**Implementation**: 1-2 hours
**Testing**: 30 minutes
**Documentation**: 15 minutes

**Total**: ~2-3 hours

## References

**Analysis Document**: Provided by Plan agent (November 8, 2025)

**Key Files**:
- Discord implementation: `src/plugins/discord_plugin.py` (lines 163, 1066-2150)
- MetricsTracker class: `src/api/server.py` (lines 52-401)
- Frontend display: `frontend/src/components/MetricsPanel.tsx`
- WebRTC handler: `src/voice/webrtc_handler.py`

**Related Documentation**:
- [ARCHITECTURE.md](../ARCHITECTURE.md) - VoxBridge architecture overview
- [WEBRTC_FIXES_SESSION_SUMMARY.md](../WEBRTC_FIXES_SESSION_SUMMARY.md) - Recent WebRTC fixes
- [voxbridge-2.0-transformation-plan.md](../architecture/voxbridge-2.0-transformation-plan.md) - VoxBridge 2.0 plan

## Notes

- This plan aligns with VoxBridge 2.0 Phase 5 (Service Layer Architecture)
- Metrics are stored in global singleton `MetricsTracker` shared between Discord and WebRTC
- No database changes required (metrics are in-memory only)
- WebSocket event name must match Discord: `"metrics_updated"` (not `"metrics_update"`)
- Frontend already supports all 21 metrics (no frontend changes needed)
