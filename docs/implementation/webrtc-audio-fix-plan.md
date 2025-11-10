# WebRTC Audio Streaming Fix - Implementation Plan
**Date:** 2025-11-06
**Lead:** voxbridge-lead
**Status:** In Progress
**Branch:** feature/sentence-level-streaming

## 🎯 Executive Summary

Fix WebRTC audio streaming to WhisperX by implementing dual-format audio support (Opus + PCM paths). This ensures browser voice chat works while maintaining full Discord plugin compatibility.

## 🔍 Root Cause Analysis

### Current Issue
WhisperX server fails with `❌ Opus decode error: b'buffer too small'` when processing WebRTC audio.

### Technical Root Cause
**Audio format mismatch between Discord and WebRTC paths:**

| Source | Format | Frame Structure | WhisperX Expectation |
|--------|--------|----------------|---------------------|
| **Discord** ✅ | Raw Opus frames | 20ms frames (960 samples each) | Match: Single 960-sample frames |
| **WebRTC** ❌ | WebM/OGG containers | 100ms chunks (5x 20ms frames bundled) | Mismatch: Expects single frames |

**The Problem:**
- Browser `MediaRecorder` produces WebM/OGG containers with multiple Opus frames bundled
- PyAV's `bytes(packet)` extracts packets containing 5x frames + metadata
- WhisperX Opus decoder expects exactly one 20ms frame per call (`frame_size=960`)
- Result: "buffer too small" error - decoder receives wrong packet structure

## 🏗️ Architecture Solution

### Dual-Format Audio Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                     WhisperX Server                              │
│  ┌────────────────────┐          ┌──────────────────────┐       │
│  │  Opus Path         │          │  PCM Path (NEW)      │       │
│  │  (Discord)         │          │  (WebRTC)            │       │
│  │  - 20ms frames     │          │  - Any size chunks   │       │
│  │  - Opus decoder    │          │  - No Opus decode    │       │
│  │  - opuslib.Decoder │          │  - Direct PCM input  │       │
│  └────────────────────┘          └──────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
           ↑                                    ↑
           │                                    │
    Discord Plugin                      WebRTC Handler
    (Raw Opus frames)                   (PCM via PyAV decode)
```

### Why This Approach Works
1. **Discord Path:** Unchanged - continues using Opus decoder for raw frames
2. **WebRTC Path:** New - PyAV fully decodes WebM→PCM (bypasses Opus mismatch)
3. **WhisperX:** Accepts both formats via format indicator in control message
4. **Compatibility:** Zero breaking changes to existing Discord functionality

## 📋 Implementation Phases

### **Phase 1: WhisperX Server - Add PCM Support**
**File:** `src/whisper_server.py`
**Effort:** 2 hours
**Risk:** Low

**Changes:**
1. Add `audio_format` parameter to `TranscriptionSession.__init__()` (default: 'opus')
2. Conditionally initialize Opus decoder only for 'opus' format
3. Add PCM audio path in `add_audio()` that bypasses Opus decoding
4. Update `handle_client()` to parse format from 'start' message
5. Add format logging for debugging

**Key Code:**
```python
class TranscriptionSession:
    def __init__(self, websocket, user_id, audio_format='opus'):
        self.audio_format = audio_format  # NEW: 'opus' or 'pcm'

        if audio_format == 'opus':
            # Existing Discord path
            self.opus_decoder = opuslib.Decoder(48000, 2)
        else:
            # NEW: PCM path - no decoder
            self.opus_decoder = None

    async def add_audio(self, audio_chunk):
        if self.audio_format == 'opus':
            # EXISTING: Decode Opus → PCM (Discord)
            pcm_data = self.opus_decoder.decode(bytes(audio_chunk), frame_size=960)
        else:
            # NEW: Already PCM (WebRTC)
            pcm_data = audio_chunk

        # Rest unchanged
        self.session_buffer.extend(pcm_data)
        self.processing_buffer.extend(pcm_data)
```

**Testing:**
- Unit test: PCM format initialization
- Unit test: Opus format backward compatibility
- Integration test: Mock WebSocket with both formats

---

### **Phase 2: WebRTC Handler - Decode WebM → PCM**
**File:** `src/voice/webrtc_handler.py`
**Effort:** 1 hour
**Risk:** Low

**Changes:**
1. Replace `_extract_opus_packets()` with `_extract_pcm_audio()`
2. Use PyAV `container.decode()` instead of `container.demux()`
3. Convert `AudioFrame` to raw PCM bytes via `frame.to_ndarray().tobytes()`
4. Update `_audio_loop()` to call new extraction method
5. Pass `audio_format='pcm'` to `stt_service.send_audio()`

**Key Code:**
```python
def _extract_pcm_audio(self) -> bytes:
    """
    Fully decode WebM/OGG to PCM audio (48kHz stereo, 16-bit)

    Uses PyAV to decode containers to raw PCM, bypassing Opus frame issues.
    Returns raw PCM bytes ready for WhisperX (no Opus decoding needed).
    """
    if not self.webm_buffer:
        return b''

    try:
        buffer = BytesIO(bytes(self.webm_buffer))
        container = av.open(buffer, 'r')
        audio_stream = container.streams.audio[0]

        pcm_chunks = []

        # DECODE packets to PCM frames (not just demux)
        for frame in container.decode(audio_stream):
            # Convert AudioFrame to raw PCM bytes (48kHz stereo int16)
            # frame.to_ndarray() returns numpy array, tobytes() converts to raw bytes
            pcm_bytes = frame.to_ndarray().tobytes()
            pcm_chunks.append(pcm_bytes)

        container.close()
        self.webm_buffer.clear()

        return b''.join(pcm_chunks)

    except av.error.InvalidDataError:
        # Incomplete data - keep buffering
        logger.debug(f"⏳ Incomplete WebM data, buffering... ({len(self.webm_buffer)} bytes)")
        return b''
    except Exception as e:
        logger.warning(f"⚠️ WebM decode error: {type(e).__name__}: {e}")
        self.webm_buffer.clear()
        return b''
```

**Testing:**
- Unit test: WebM decoding to PCM
- Unit test: Buffer management (incomplete data)
- Unit test: Error handling (invalid containers)
- Integration test: End-to-end WebRTC audio flow

---

### **Phase 3: STTService - Format Routing**
**File:** `src/services/stt_service.py`
**Effort:** 30 minutes
**Risk:** Low

**Changes:**
1. Add `audio_format` parameter to `send_audio()` (default: 'opus')
2. Send format indicator in 'start' message to WhisperX
3. Track format per connection to send only once
4. Update method signature and docstrings

**Key Code:**
```python
async def send_audio(
    self,
    session_id: str,
    audio_data: bytes,
    audio_format: str = 'opus'  # NEW: 'opus' (Discord) or 'pcm' (WebRTC)
) -> bool:
    """
    Send audio data to WhisperX with format indicator

    Args:
        session_id: Session identifier
        audio_data: Raw audio bytes (Opus frames or PCM samples)
        audio_format: 'opus' for Discord raw frames, 'pcm' for decoded audio

    Returns:
        True if sent successfully, False otherwise
    """
    conn = self.connections.get(session_id)

    if not conn or conn.ws.closed:
        logger.warning(f"⚠️ No active connection for session {session_id}")
        return False

    try:
        # Send format on first audio (if not already sent)
        if not hasattr(conn, 'format_sent'):
            logger.info(f"📡 Sending audio format to WhisperX: {audio_format}")
            await conn.ws.send(json.dumps({
                'type': 'start',
                'userId': session_id,
                'audio_format': audio_format  # NEW: Format flag
            }))
            conn.format_sent = True
            conn.audio_format = audio_format

        # Send binary audio data
        await conn.ws.send(audio_data)
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send audio: {e}")
        return False
```

**Testing:**
- Unit test: Format parameter handling
- Unit test: Format flag sent only once per connection
- Unit test: Backward compatibility (default 'opus')

---

### **Phase 4: Discord Plugin - Verify No Changes**
**File:** `src/plugins/discord_plugin.py`
**Effort:** 15 minutes (verification only)
**Risk:** None (no changes)

**Verification:**
1. Confirm Discord plugin calls `stt_service.send_audio()` with raw Opus
2. Verify no `audio_format` parameter passed (defaults to 'opus')
3. Ensure backward compatibility maintained

**No code changes required** - Discord path uses default 'opus' format.

---

## 🧪 Testing Strategy

### Unit Tests (Priority: High)
**Agent:** unit-test-writer

**New Tests Required:**
1. **test_whisper_server_pcm.py** (25 tests)
   - PCM format initialization
   - Opus format backward compatibility
   - Format indicator parsing from 'start' message
   - PCM audio path (no Opus decode)
   - Opus audio path (existing)
   - Buffer management for both formats

2. **test_webrtc_pcm_decode.py** (15 tests)
   - WebM container decoding to PCM
   - PyAV frame extraction
   - Buffer accumulation logic
   - Incomplete data handling
   - Error recovery (invalid containers)
   - PCM byte format validation (48kHz, stereo, int16)

3. **test_stt_service_format.py** (10 tests)
   - Format parameter handling
   - Format flag sent once per connection
   - Default 'opus' format
   - Format persistence per connection
   - Error handling

**Total New Unit Tests:** 50 tests
**Target Coverage:** 95%+

### Integration Tests (Priority: High)
**Agent:** integration-test-writer

**New Tests Required:**
1. **test_webrtc_audio_pipeline.py**
   - End-to-end WebRTC audio flow (browser → WhisperX)
   - Mock WebSocket with WebM chunks
   - Verify PCM extraction and forwarding
   - Verify transcription events

2. **test_discord_regression.py**
   - Verify Discord Opus path unchanged
   - Ensure no regressions in Discord audio
   - Test dual-format concurrent processing

**Total Integration Tests:** 10 tests

### Manual Testing (Priority: Critical)
**Agent:** voxbridge-lead

**Test Scenarios:**
1. **Discord Plugin Regression**
   - Join Discord voice channel
   - Speak test phrases
   - Verify clean transcriptions (no Opus errors)
   - Check logs for format indicators

2. **WebRTC Streaming**
   - Open browser voice chat (http://localhost:4903)
   - Start microphone capture
   - Speak test phrases
   - Verify real-time partial transcripts
   - Verify final transcripts
   - Check logs for PCM format and no "buffer too small" errors

3. **Concurrent Usage**
   - Use Discord and WebRTC simultaneously
   - Verify both work independently
   - Check for resource leaks or conflicts

---

## 📊 Task Assignment

### Backend Implementation
**Agent:** voxbridge-lead (self)
**Tasks:**
- ✅ Phase 1: WhisperX PCM support
- ✅ Phase 2: WebRTC PCM decoding
- ✅ Phase 3: STTService format routing

### Unit Testing
**Agent:** unit-test-writer
**Tasks:**
- Write test_whisper_server_pcm.py (25 tests)
- Write test_webrtc_pcm_decode.py (15 tests)
- Write test_stt_service_format.py (10 tests)
- Achieve 95%+ coverage on new code

### Integration Testing
**Agent:** integration-test-writer
**Tasks:**
- Write test_webrtc_audio_pipeline.py (E2E WebRTC)
- Write test_discord_regression.py (Discord compatibility)
- Set up mock servers for testing
- Document test fixtures

### Test Review
**Agent:** test-reviewer
**Tasks:**
- Review test coverage after implementation
- Identify edge cases and gaps
- Validate test quality and assertions
- Suggest additional test scenarios

---

## ✅ Success Criteria

| Criteria | Metric | Target |
|----------|--------|--------|
| Discord Functionality | No regressions | 100% working |
| WebRTC Audio Streaming | No Opus errors | 0 errors |
| Real-time Transcription | Partial transcripts | < 2s latency |
| Final Transcription | Accuracy | > 95% match |
| Unit Test Coverage | Code coverage | > 95% |
| Integration Tests | Pass rate | 100% |
| Memory Usage | No leaks | Stable over 1hr |
| Performance | Latency impact | < 50ms added |

---

## 🚨 Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Discord plugin breaks | High | Extensive regression tests, no changes to Discord path |
| PyAV decoding issues | Medium | Robust error handling, buffer management, test with various audio formats |
| Performance degradation | Medium | Profile PyAV decode vs demux, monitor memory usage |
| Format detection fails | Low | Default to 'opus' for backward compatibility |
| WhisperX incompatibility | Low | Use standard PCM format (48kHz stereo int16) |

---

## 📈 Rollout Plan

### Development
1. Create feature branch (current: feature/sentence-level-streaming)
2. Implement backend changes (Phases 1-3)
3. Write unit tests
4. Run local testing

### Testing
1. Run unit test suite (target: 95%+ coverage)
2. Run integration tests
3. Manual Discord regression testing
4. Manual WebRTC streaming testing

### Deployment
1. Review code changes
2. Update documentation (CLAUDE.md, AGENTS.md)
3. Merge to main branch
4. Deploy to production
5. Monitor logs for 24 hours

### Rollback Plan
If issues arise:
1. Revert commits to restore Discord functionality
2. Disable WebRTC endpoint temporarily
3. Debug issues in separate branch
4. Re-test before re-deployment

---

## 📝 Documentation Updates

### Files to Update
1. **CLAUDE.md** - Add WebRTC audio architecture notes
2. **AGENTS.md** - Document dual-format audio support
3. **README.md** - Update WebRTC usage instructions
4. **docs/architecture/** - Add audio pipeline diagrams

### Code Documentation
1. Update docstrings for modified functions
2. Add inline comments for format handling logic
3. Update type hints for new parameters

---

## 🎯 Timeline

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: WhisperX | 2 hours | None |
| Phase 2: WebRTC | 1 hour | Phase 1 |
| Phase 3: STTService | 30 mins | Phase 1 |
| Unit Tests | 2 hours | Phases 1-3 |
| Integration Tests | 1 hour | Phases 1-3 |
| Manual Testing | 1 hour | All phases |
| Documentation | 30 mins | All phases |
| **Total** | **8 hours** | - |

---

## 📞 Communication Plan

### Status Updates
- Update todo list after each phase completion
- Log key milestones in implementation
- Report blockers immediately

### Issue Escalation
- Backend issues → voxbridge-lead
- Test failures → test-reviewer
- Architecture questions → voxbridge-lead

---

## 🔗 References

- **Root Cause Analysis:** WhisperX logs showing "buffer too small" errors
- **WhisperX Server:** `src/whisper_server.py:200-211` (Opus decoder initialization)
- **WebRTC Handler:** `src/voice/webrtc_handler.py:277-329` (Current Opus extraction)
- **STTService:** `src/services/stt_service.py` (Audio forwarding)
- **Discord Plugin:** `src/plugins/discord_plugin.py:234-236` (Raw Opus frames)

---

**Plan Status:** ✅ APPROVED - Ready for implementation
**Next Action:** Begin Phase 1 (WhisperX PCM support)
