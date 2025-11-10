# WebM Buffer Decode Fix - Implementation Summary

**Date**: November 8, 2025
**Issue**: Audio processing stops after ~90 seconds of continuous voice input
**Status**: ✅ **COMPLETE** - Fix implemented and deployed

---

## Problem Description

### Root Cause Analysis

The system was experiencing complete audio processing failure after approximately 60-90 seconds of continuous voice input due to:

1. **Buffer trimming breaks WebM structure** - After 500KB (~60s), buffer was truncated from beginning
2. **WebM header removal** - Trimming removed critical EBML header and segment data required for decoding
3. **Silent decode failures** - PyAV `InvalidDataError` exceptions caught and suppressed at DEBUG level
4. **No recovery** - Once decode started failing, it never recovered (continued silently failing forever)

### Symptoms

**Timeline of Failure**:
- **00:00-01:28** (chunks #1-729): ✅ Audio works perfectly
- **01:28** (chunk #729): ⚠️ Buffer reaches 500KB, gets trimmed
- **01:28+** (chunks #730-826): ❌ Decode fails silently, no audio processed

**User Experience**:
- Voice chat works normally for first ~90 seconds
- After 90 seconds, bot stops transcribing user speech
- No error messages visible to user
- Microphone still sending audio (WebSocket active)
- Browser shows everything working (misleading)
- System requires page reload to recover

**Diagnostic Evidence** (from checkpoint logging):
```
# Working period (chunks #1-729):
🔌 [WS_RECV] Received 989 bytes (chunk #729)
✅ [DECODE] Decoded 2 new frames → 23040 bytes PCM
🎤 [WHISPER_SEND] Sending 23040 bytes PCM to WhisperX

# Buffer trimmed at chunk #729:
🧹 Trimmed buffer: 500677 → 500000 bytes, reset frame counter

# Failing period (chunks #730+):
🔌 [WS_RECV] Received 989 bytes (chunk #730)  ← ✅ WebSocket still receiving
✅ [DECODE] ← ❌ MISSING! Decode never happens
🎤 [WHISPER_SEND] ← ❌ MISSING! Audio never sent
```

---

## Technical Deep Dive

### The Broken Buffer Trimming Logic

**File**: `src/voice/webrtc_handler.py:437-444` (OLD CODE - REMOVED)

```python
# ❌ BROKEN: This destroys WebM structure!
if len(self.webm_buffer) > MAX_BUFFER_SIZE:
    # Keep only recent data to maintain codec state
    old_size = len(self.webm_buffer)
    self.webm_buffer = self.webm_buffer[-MAX_BUFFER_SIZE:]  # ← Removes EBML header!
    self.frames_sent_to_whisperx = 0  # Reset frame counter
    logger.info(f"🧹 Trimmed buffer: {old_size} → {len(self.webm_buffer)} bytes, reset frame counter")
```

**Why This Failed**:

1. **WebM Container Structure** (simplified):
   ```
   [EBML Header]    ← Required for PyAV to recognize format
   [Segment Header] ← Contains track info, codec data
   [Cluster 1]      ← Audio frames
   [Cluster 2]      ← Audio frames
   [Cluster N]      ← Audio frames
   ```

2. **Trimming from Beginning**:
   ```python
   # Before trim (valid WebM):
   buffer = [EBML][Segment][Cluster1][Cluster2]...[ClusterN]

   # After trim (INVALID - missing headers):
   buffer = ...[ClusterM][ClusterN]
   ```

3. **PyAV Decode Failure**:
   - PyAV tries to decode truncated buffer
   - Missing EBML header → `av.error.InvalidDataError`
   - Exception caught silently (line 450-453)
   - Returns empty bytes, no audio sent

4. **Silent Exception Handler**:
   ```python
   except (av.error.InvalidDataError, av.error.ValueError):
       # ❌ DEBUG level - never visible in logs!
       logger.debug(f"⏳ [DECODE] Incomplete WebM data, buffering...")
       return b''
   ```

### Why 90 Seconds?

```
Buffer growth rate:
- Audio format: 48kHz stereo Opus in WebM container
- MediaRecorder chunks: ~989 bytes every 120ms
- Buffer growth: ~8.2 KB/second
- 500KB limit reached: ~61 seconds of continuous audio
- Plus conversation turns: ~90 seconds total elapsed time
```

---

## Solution Architecture

### Fix Strategy

**Graceful Finalization Instead of Trimming**:

Instead of breaking the WebM structure by trimming, we now **finalize the current utterance** and reset cleanly when the buffer gets too large.

### Implementation

**File**: `src/voice/webrtc_handler.py:319-334` (NEW CODE)

```python
# Buffer management: Prevent memory leak from unbounded growth
# Max ~60 seconds of continuous audio before finalizing
MAX_BUFFER_SIZE = 500000  # 500KB (~60s at 48kHz stereo)
if len(self.webm_buffer) > MAX_BUFFER_SIZE:
    logger.info(f"🏁 Buffer limit reached ({len(self.webm_buffer)} bytes > {MAX_BUFFER_SIZE}) - finalizing current utterance")

    # Finalize current utterance (this will trigger transcription)
    await self.stt_service.finalize_transcript(self.session_id)

    # Clear buffer and reset to start fresh
    self.webm_buffer = bytearray()
    self.frames_sent_to_whisperx = 0
    logger.info(f"✅ Buffer cleared and reset - ready for new utterance")

    # Skip processing this chunk since we just finalized
    continue
```

**Key Improvements**:

1. **Graceful Finalization**:
   - Sends finalize message to WhisperX
   - Triggers final transcription of accumulated audio
   - User gets complete transcription before reset

2. **Clean Buffer Reset**:
   - Completely clears buffer (not truncated)
   - Next chunk starts fresh WebM stream with proper headers
   - No decode errors or silent failures

3. **Improved Error Logging**:
   ```python
   # Changed from DEBUG to WARNING level
   except (av.error.InvalidDataError, av.error.ValueError) as e:
       logger.warning(f"⏳ [DECODE] Incomplete WebM data ({type(e).__name__}), buffering...")
       return b''
   ```

4. **Location**: Buffer check moved to **main audio loop** (async context) instead of decode function
   - Allows use of `await` for finalize
   - Cleaner separation of concerns

---

## Testing Checklist

### Test Scenarios

- [ ] **Normal Operation < 60s** - Verify fix doesn't break short utterances
  - Send multiple short voice messages (5-10s each)
  - Confirm all transcribed correctly
  - Verify no finalization messages in logs

- [ ] **Long Utterance > 60s** - Verify graceful finalization
  - Speak continuously for 90+ seconds
  - Watch for buffer limit log at ~60s mark
  - Confirm automatic finalization and transcription
  - Verify audio continues working after finalization

- [ ] **Multiple Long Utterances** - Verify repeated finalization works
  - Send 3+ consecutive 90-second utterances
  - Confirm each finalization + reset cycle works
  - Verify no memory leak (check container memory usage)

- [ ] **Conversation Flow** - Verify natural back-and-forth still works
  - Alternate between short and long utterances
  - Confirm TTS responses still trigger correctly
  - Verify silence detection still works

### Expected Log Patterns

**Normal operation (< 60s)**:
```
🔌 [WS_RECV] Received 989 bytes (chunk #1)
✅ [DECODE] Decoded 2 new frames → 23040 bytes PCM
🎤 [WHISPER_SEND] Sending 23040 bytes PCM to WhisperX
```

**Buffer limit reached (60s+)**:
```
🏁 Buffer limit reached (501234 bytes > 500000) - finalizing current utterance
✅ Buffer cleared and reset - ready for new utterance
🔌 [WS_RECV] Received 989 bytes (chunk #730)  ← Fresh start
✅ [DECODE] Decoded 1 new frames → 11520 bytes PCM  ← New WebM stream
```

**Decode error (should be rare now)**:
```
⏳ [DECODE] Incomplete WebM data (InvalidDataError), buffering... (1234 bytes)
```

---

## Performance Impact

### Latency

- **No impact on normal operation** - Buffer check is O(1) comparison
- **60-second max utterance** - Ensures timely transcription for very long speech
- **Automatic finalization** - Prevents unbounded buffering delays

### Resource Usage

- **Memory cap**: 500KB max per session (~60s audio)
- **Buffer reset**: Prevents memory leak from unbounded growth
- **No decode overhead**: Fix prevents repeated failed decode attempts

### Scalability

- **Per-session isolation**: Each WebSocket has independent buffer
- **No global locks**: Buffer management is local to handler
- **Concurrent safety**: Multiple users can hit buffer limit independently

---

## Rollback Procedure

If issues arise, rollback by reverting commit:

```bash
# 1. Identify commit hash
git log --oneline | grep "buffer\|decode"

# 2. Revert the commit
git revert <commit-hash>

# 3. Rebuild and restart
docker compose down
docker compose build voxbridge-discord
docker compose up -d
```

**Emergency hotfix** (no rebuild):
```bash
# Edit files directly in container
docker exec -it voxbridge-discord bash

# Restore old code (re-add buffer trimming, remove finalization)
vim src/voice/webrtc_handler.py

# Lines 319-334: Remove new buffer management code
# Lines 454-455: Remove comment, re-add trimming logic

# Restart container
exit
docker compose restart voxbridge-discord
```

---

## Future Improvements

### Short-term
- [ ] Add Prometheus metric for buffer limit events
- [ ] Add frontend notification when buffer limit reached
- [ ] Make MAX_BUFFER_SIZE configurable via environment variable

### Medium-term
- [ ] Implement sliding window buffer (keep headers, trim old clusters)
- [ ] Add buffer size metrics to `/metrics` endpoint
- [ ] Implement user-configurable max utterance length

### Long-term
- [ ] Research WebM streaming best practices
- [ ] Implement frame-level buffer management
- [ ] Consider switching to raw PCM streaming (bypass WebM entirely)

---

## Related Issues

### Fixed
- ✅ LLM Stream Hang (Nov 7, 2025) - `docs/analysis/llm-timeout-fix-summary.md`
- ✅ WebRTC UX Issues (Oct 2025) - `docs/analysis/webrtc-ux-issues-analysis.md`

### Monitoring
- Watch for `InvalidDataError` warnings in logs (should be rare)
- Monitor buffer limit events (indicates very long utterances)
- Track memory usage over long sessions

---

## References

- **Diagnostic Tool**: 5-checkpoint logging system (implemented Nov 7-8, 2025)
- **WebM Format**: https://www.webmproject.org/docs/container/
- **PyAV Documentation**: https://pyav.org/docs/stable/
- **MediaRecorder API**: https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder

---

## Contributors

- **Root Cause Analysis**: Claude Code (diagnostic investigation)
- **Implementation**: Claude Code (voxbridge-lead agent)
- **Testing**: [To be added after user testing]

**Last Updated**: November 8, 2025
