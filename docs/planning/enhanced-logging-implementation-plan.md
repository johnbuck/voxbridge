# Enhanced Logging Implementation Plan for VoxBridge Audio Pipeline

**Date**: November 8, 2025
**Issue**: VoxBridge stops listening after time + long silence
**Symptoms**: Microphone indicator active but no transcription, silent failure
**Recovery**: Stop/start microphone button works

---

## **Root Cause Investigation Results**

Comprehensive codebase analysis identified **26 critical silent failure points** across 6 major areas where audio input can fail without logging visibility.

---

## **Phase 1: CRITICAL Watchdogs & Error Detection**
*Priority: Highest - Likely root causes of the bug*

### 1.1 MediaRecorder ondataavailable Watchdog (useWebRTCAudio.ts)
**Problem**: Microphone indicator active but no audio chunks being generated
**Location**: `frontend/src/hooks/useWebRTCAudio.ts`
**Changes**:
- Add `lastChunkTimeRef` to track chunk timing (line 111)
- Update ondataavailable to record timestamp (line 369)
- Implement 2-second watchdog useEffect that detects if ondataavailable stops firing
- Alert when >5 seconds without chunks
- Log MediaRecorder state, WebSocket state when frozen

### 1.2 Audio Loop Exit Detection (webrtc_handler.py)
**Problem**: Backend loop exits silently, frontend stays active
**Location**: `src/voice/webrtc_handler.py`
**Changes**:
- Log when loop enters with `is_active` state (line 289)
- Enhanced WebSocketDisconnect handler with chunk count (line 376)
- Enhanced exception handler with state dump (line 378)
- Warning when loop exits in finally block (line 384)

### 1.3 Frontend State Conflict Validation (VoxbridgePage.tsx)
**Problem**: Invalid state combinations go undetected
**Location**: `frontend/src/pages/VoxbridgePage.tsx`
**Changes**:
- New useEffect to detect impossible state combos
- Auto-fix `disconnected && isListening`
- Warn on `isListening && isBotSpeaking`
- Warn on `isStreaming && !isVoiceAIGenerating`

---

## **Phase 2: State Transitions & Flow Logging**
*Priority: High - Visibility into state machine behavior*

### 2.1 Bot Speaking Discard Tracking (webrtc_handler.py)
**Problem**: Audio silently discarded for extended periods
**Location**: `src/voice/webrtc_handler.py`
**Changes**:
- Add `discarded_chunks_count` counter at init (line 103)
- Track discards with counter in bot speaking check (line 298)
- Warning after 50 chunks (~5 seconds of discarding)
- Log when bot finishes speaking with total discard count

### 2.2 Silence Detection Calculation Logging (webrtc_handler.py)
**Problem**: Can't diagnose why silence detection doesn't trigger
**Location**: `src/voice/webrtc_handler.py`
**Changes**:
- Log silence duration every 1 second at TRACE level (line 748)
- Log audio amplitude checks for both silent and non-silent (line 353)
- Track utterance start time resets (line 710)

### 2.3 WhisperX Silent Disconnect Detection (stt_service.py)
**Problem**: WhisperX connection drops between transcripts
**Location**: `src/services/stt_service.py`
**Changes**:
- Track time since last message in receive loop (line 522)
- Warn if >10s gap between WhisperX messages
- Log exact format indicator message sent (line 272)
- Track finalize acknowledgment with flag (line 357)

### 2.4 LLM Timeout Progressive Warnings (llm_service.py + others)
**Problem**: 90s timeout hits suddenly with no early warning
**Location**: Multiple files
**Changes**:
- Add timeout warner task with 30s and 60s warnings (`src/services/llm_service.py` line 514)
- Detect suspiciously short first chunks (`src/voice/webrtc_handler.py` line 945)
- Track response growth rate and warn if stalled
- Frontend 120s safety timeout (`frontend/src/pages/VoxbridgePage.tsx` line 315)

---

## **Phase 3: Enhanced Diagnostics & Safety Nets**
*Priority: Medium - Additional visibility and recovery*

### 3.1 MediaRecorder State Transition Logging (useWebRTCAudio.ts)
**Location**: `frontend/src/hooks/useWebRTCAudio.ts`
**Changes**:
- Log MediaRecorder state before stop() calls (line 458)
- Track empty chunk frequency with counter (line 111, 386)
- Error after >10 consecutive empty chunks

### 3.2 Buffer Management Visibility (webrtc_handler.py)
**Location**: `src/voice/webrtc_handler.py`
**Changes**:
- Warn on forced finalization with chunk count + estimated duration (line 322)
- Log buffer cleared size and frame counter reset (line 333)

### 3.3 Frontend Safety Timeouts (VoxbridgePage.tsx)
**Location**: `frontend/src/pages/VoxbridgePage.tsx`
**Changes**:
- 10s timeout for pending transcript placeholder (line 282)
- Re-entrance detection for WebSocket message handler (line 485)
- Handler duration warnings (>100ms processing time)

---

## **Phase 4: Cross-Cutting Improvements**
*Priority: Low - Code quality and maintainability*

### 4.1 Exception Handling Pattern
- Log exception type + traceback everywhere
- Add done callbacks to all async tasks
- Replace generic `except Exception` handlers with specific types

### 4.2 State Transition Pattern
- Log all boolean flag transitions (is_finalizing, isListening, etc.)
- Format: `🔄 [STATE] flag_name: old → new (context)`
- Apply consistently across all files

### 4.3 Add TRACE Log Level (NEW)
**Location**: `src/config/logging_config.py`
**Changes**:
- Implement custom TRACE level (5) below DEBUG (10)
- Add to logging module via `addLevelName`
- Add `trace()` method to Logger class
- Use for high-frequency events (silence checks every 100ms, amplitude checks)
- Enable via `LOG_LEVEL=TRACE` or `LOG_LEVEL_VOICE=TRACE`

---

## **Implementation Strategy**

### Batch 1: Critical Watchdogs (1-2 hours)
**Files**:
- `frontend/src/hooks/useWebRTCAudio.ts` (watchdog)
- `src/voice/webrtc_handler.py` (loop exit)
- `frontend/src/pages/VoxbridgePage.tsx` (state conflicts)

**Goal**: Catch the most likely root causes

### Batch 2: State & Flow (2-3 hours)
**Files**:
- `src/voice/webrtc_handler.py` (bot speaking, silence)
- `src/services/stt_service.py` (WhisperX disconnect)
- `src/services/llm_service.py` + `src/voice/webrtc_handler.py` (LLM timeouts)
- `frontend/src/pages/VoxbridgePage.tsx` (frontend LLM timeout)

**Goal**: Understand state machine behavior

### Batch 3: Safety Nets (1-2 hours)
**Files**:
- `frontend/src/hooks/useWebRTCAudio.ts` (state logging, empty chunks)
- `src/voice/webrtc_handler.py` (buffer management)
- `frontend/src/pages/VoxbridgePage.tsx` (safety timeouts)

**Goal**: Prevent/detect edge cases

### Batch 4: Code Quality (optional)
**Files**: All service files + handlers
**Goal**: Improve maintainability

---

## **Testing Plan**

After each batch:
1. **Reproduce the bug** - Let system run until it stops listening
2. **Analyze logs** - Grep for `ERROR|WARN|WATCHDOG|STATE_CONFLICT`
3. **Identify root cause** - Trace backwards from last successful checkpoint
4. **Verify fix** - Confirm stop/start mic recovers + logs show recovery path

---

## **Expected Log Output**

### If MediaRecorder stops:
```
🚨 [WATCHDOG] MediaRecorder ondataavailable stopped firing! Last chunk: 8234ms ago
   - MediaRecorder state: recording
   - WebSocket state: 1 (OPEN)
```

### If backend loop exits:
```
🛑 [AUDIO_LOOP] Exited main loop (is_active=False, chunks_received=532)
```

### If state conflict:
```
🚨 [STATE_CONFLICT] Invalid: disconnected but isListening true!
```

### If bot speaking too long:
```
⚠️ [STATE] Bot speaking for extended period - 73 chunks discarded
```

### If WhisperX disconnect:
```
⚠️ [STT] Long gap between WhisperX messages: 12.3s (session=abc-123)
```

### If LLM timeout approaching:
```
⏱️ LLM generation taking longer than expected (30s elapsed)
⏱️ LLM generation slow (60s elapsed) - approaching timeout
```

---

## **Detailed Implementation Guide**

### Batch 1, Item 1.1: MediaRecorder Watchdog

**File**: `frontend/src/hooks/useWebRTCAudio.ts`

**Step 1**: Add ref after line 111
```typescript
const lastChunkTimeRef = useRef<number | null>(null);
```

**Step 2**: Update ondataavailable at line 369
```typescript
lastChunkTimeRef.current = Date.now(); // Track last chunk time
logger.info(`[${timestamp}] [MediaRecorder] 📤 Audio chunk available: ${event.data.size} bytes, connected=${wsRef.current?.readyState === WebSocket.OPEN}`);
```

**Step 3**: Add watchdog useEffect after line 520
```typescript
// Watchdog: Detect if MediaRecorder stops sending chunks
useEffect(() => {
  if (!isRecording) return;

  const watchdog = setInterval(() => {
    if (lastChunkTimeRef.current) {
      const timeSinceLastChunk = Date.now() - lastChunkTimeRef.current;
      if (timeSinceLastChunk > 5000) { // 5 seconds without chunks
        logger.error(`🚨 [WATCHDOG] MediaRecorder ondataavailable stopped firing! Last chunk: ${timeSinceLastChunk}ms ago`);
        logger.error(`   - MediaRecorder state: ${mediaRecorderRef.current?.state}`);
        logger.error(`   - WebSocket state: ${wsRef.current?.readyState}`);
        logger.error(`   - isRecording: ${isRecording}`);
        logger.error(`   - isMuted: ${isMuted}`);
      }
    }
  }, 2000); // Check every 2 seconds

  return () => clearInterval(watchdog);
}, [isRecording, isMuted]);
```

### Batch 1, Item 1.2: Audio Loop Exit Detection

**File**: `src/voice/webrtc_handler.py`

**Step 1**: Add log at line 289 (start of while loop)
```python
logger.info(f"🎙️ [AUDIO_LOOP] Entering main loop (session={self.session_id}, is_active={self.is_active})")
```

**Step 2**: Enhance exception handlers at lines 376-378
```python
except WebSocketDisconnect:
    logger.info(f"🔌 Browser disconnected")
    logger.warn(f"⚠️ [AUDIO_LOOP] WebSocket disconnected at chunk #{self.chunks_received}, is_active={self.is_active}, session={self.session_id}")

except Exception as e:
    logger.error(f"❌ Error in audio loop: {e}", exc_info=True)
    logger.error(f"🚨 [AUDIO_LOOP] FATAL ERROR after {self.chunks_received} chunks, is_active={self.is_active}, session={self.session_id}")
```

**Step 3**: Add finally block after line 384
```python
finally:
    # Cancel silence monitoring
    logger.warn(f"🛑 [AUDIO_LOOP] Exited main loop (is_active={self.is_active}, chunks_received={self.chunks_received}, session={self.session_id})")
    if self.silence_task:
        self.silence_task.cancel()
```

### Batch 1, Item 1.3: Frontend State Conflict Validation

**File**: `frontend/src/pages/VoxbridgePage.tsx`

**Step 1**: Add useEffect after line 79 (state variable declarations)
```typescript
// State conflict detection
useEffect(() => {
  // Detect invalid state combinations
  if (isListening && isBotSpeaking) {
    logger.error('🚨 [STATE_CONFLICT] Invalid: isListening && isBotSpeaking both true!');
  }
  if (isListening && isVoiceAIGenerating) {
    logger.warn('⚠️ [STATE_CONFLICT] Unusual: isListening && isVoiceAIGenerating both true');
  }
  if (isStreaming && !isVoiceAIGenerating) {
    logger.warn('⚠️ [STATE_CONFLICT] Unusual: isStreaming true but isVoiceAIGenerating false');
  }
  if (connectionState === 'disconnected' && isListening) {
    logger.error('🚨 [STATE_CONFLICT] Invalid: disconnected but isListening true!');
    logger.info('🔧 [AUTO_FIX] Setting isListening to false');
    setIsListening(false); // Auto-fix
  }
}, [isListening, isBotSpeaking, isVoiceAIGenerating, isStreaming, connectionState]);
```

---

## **Success Criteria**

1. ✅ All 26 identified silent failure points have logging coverage
2. ✅ Can reproduce bug and see exact failure point in logs
3. ✅ Stop/start recovery path is logged and understandable
4. ✅ Production logs remain clean (INFO level)
5. ✅ Debug logs provide detailed diagnostics (DEBUG/TRACE level)

---

## **Related Issues**

- ✅ WebM Buffer Decode Fix (Nov 8, 2025) - `docs/analysis/webm-buffer-decode-fix-summary.md`
- ✅ LLM Stream Hang (Nov 7, 2025) - `docs/analysis/llm-timeout-fix-summary.md`
- ✅ Tiered Logging System (Nov 8, 2025) - `docs/planning/tiered-logging-system-plan.md`

---

**Last Updated**: November 8, 2025
**Implementation Status**: ✅ COMPLETE - All Batches 1-3 Implemented + TRACE Log Level

**Completion Summary**:
- ✅ Batch 1: Critical Watchdogs (3/3 items)
- ✅ Batch 2: State Transitions & Flow Logging (4/4 items)
- ✅ Batch 3: Enhanced Diagnostics & Safety Nets (3/3 items)
- ✅ Batch 4.3: TRACE Log Level (pre-existing)
- ⏭️ Batch 4.1-4.2: Deferred (code quality improvements, lower priority)
