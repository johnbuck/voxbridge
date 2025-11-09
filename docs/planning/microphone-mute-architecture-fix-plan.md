# Microphone Mute Architecture Fix - Research & Implementation Plan

**Date**: November 8, 2025
**Branch**: `feature/tts-playback-mic-off-fix` (to be updated)
**Status**: Planning

---

## Executive Summary

**Problem**: The microphone mute functionality has too many responsibilities. When the user clicks "Mic OFF", it's affecting:
- AI responses (shouldn't be affected)
- WebSocket connections (shouldn't be affected)
- Already transcribed messages (shouldn't be affected)
- TTS playback (shouldn't be affected)

**Root Cause**: `isMuted` state is checked in the WebSocket auto-reconnect logic, causing the WebSocket to not reconnect when the mic is muted. This breaks multi-turn conversations and causes AI responses to be lost.

**Solution**: Microphone mute should ONLY affect audio capture. Everything else (WebSocket, message processing, TTS) should be completely independent.

---

## Web Best Practices Research

### Industry Standards (Discord, Zoom, Google Meet, Teams)

When you mute your microphone in professional voice chat apps:

✅ **What DOES happen**:
- Stops sending audio to other participants
- Generates silence frames (not empty - actual silent audio)
- Device activity indicators turn off (mic light)

❌ **What DOES NOT happen**:
- Does NOT stop receiving audio from others
- Does NOT disconnect from the call
- Does NOT affect ongoing server processing
- Does NOT clear already received messages
- Does NOT stop displaying conversation updates

### MDN Web API Standard

**Official Recommendation**: Use `MediaStreamTrack.enabled` property for mute/unmute

```typescript
// MDN-recommended approach
audioTrack.enabled = false;  // Mute (generates silence frames)
audioTrack.enabled = true;   // Unmute
```

**Key Points**:
- `enabled = false` → Track outputs silence frames (every sample = 0)
- `enabled` controls OUTPUT of the track only
- Does NOT affect WebSocket, application state, or other audio playback
- Updates device activity indicators automatically

### User Mental Model

**When user clicks "Mute Mic"**, they expect:
1. **To stop broadcasting their voice** → Stop sending audio ✅
2. **To continue hearing others** → Keep receiving audio ✅
3. **To stay in the conversation** → WebSocket stays connected ✅
4. **Already spoken words remain visible** → No clearing transcripts ✅
5. **To unmute and speak again immediately** → Quick toggle, no reconnection ✅

**Mental Model**: "Mic OFF" = "Stop listening to me", NOT "End conversation"

---

## Current Architecture Analysis

### The Three Independent Audio Paths

```
┌─────────────────────────────────────────────────────────────┐
│                    VoxBridge Audio Architecture             │
└─────────────────────────────────────────────────────────────┘

PATH 1: MICROPHONE INPUT (Affected by mic mute)
┌────────────────────────────────────────────────────────────┐
│ getUserMedia() → MediaStream → MediaRecorder               │
│         ↓                             ↓                    │
│   track.enabled = !isMuted    Captures audio chunks        │
│                                       ↓                    │
│                        Send to WebSocket (ws.send)         │
└────────────────────────────────────────────────────────────┘
    ✅ CHECK isMuted HERE: Only send audio when unmuted


PATH 2: WEBSOCKET MESSAGING (Independent of mic mute)
┌────────────────────────────────────────────────────────────┐
│ WebSocket (/ws/voice) - Bidirectional Message Channel     │
│         ↓                             ↑                    │
│  Receive Events:              Send Audio:                  │
│  • partial_transcript         • Binary audio chunks        │
│  • final_transcript          (from PATH 1)                 │
│  • ai_response_chunk                                       │
│  • ai_response_complete                                    │
│  • tts_complete                                            │
│         ↓                                                  │
│  Process ALL events regardless of mic state                │
└────────────────────────────────────────────────────────────┘
    ❌ NEVER CHECK isMuted HERE: Always process messages


PATH 3: AUDIO OUTPUT/TTS (Independent of mic mute)
┌────────────────────────────────────────────────────────────┐
│ Receive binary audio (TTS) via WebSocket                  │
│         ↓                                                  │
│ Create Audio element (HTML5 Audio)                         │
│         ↓                                                  │
│ Set volume based on SPEAKER mute (not mic mute!)          │
│         ↓                                                  │
│ audio.play()                                               │
└────────────────────────────────────────────────────────────┘
    ❌ NEVER CHECK mic isMuted HERE: Use speaker mute instead
```

### Responsibility Matrix

| Component | Checks Mic Mute? | Checks Speaker Mute? | Checks Connection? |
|-----------|------------------|----------------------|--------------------|
| MediaRecorder | ✅ YES | ❌ NO | ❌ NO |
| Audio Chunk Sender | ✅ YES | ❌ NO | ✅ YES |
| WebSocket Handler | ❌ NO | ❌ NO | ✅ YES |
| Message Processor | ❌ NO | ❌ NO | ⚠️ MAYBE (UI only) |
| TTS Audio Player | ❌ NO | ✅ YES | ❌ NO |
| UI Components | ✅ YES | ✅ YES | ✅ YES |

---

## Critical Violations Found

### VIOLATION #1: WebSocket Auto-Reconnect Checks isMuted ⚠️

**Location**: `frontend/src/hooks/useWebRTCAudio.ts:285`

```typescript
// ❌ CURRENT (WRONG):
ws.onclose = (event) => {
  if (
    reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS &&
    !isMuted // ❌ WRONG: Prevents reconnect when mic is muted
  ) {
    // reconnect...
  }
};
```

**Problem**:
- If WebSocket disconnects while mic is muted, it will NEVER reconnect
- AI responses in progress will be lost
- TTS audio won't play
- User can't see conversation updates
- Multi-turn conversations break

**Impact**: **HIGH** - This is the primary bug causing the system freeze

**Fix**:
```typescript
// ✅ CORRECT:
ws.onclose = (event) => {
  // Always reconnect - mic state is independent of connection
  if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
    // reconnect...
  }
};
```

---

### VIOLATION #2: Dependency Array Pollution

**Location**: `frontend/src/hooks/useWebRTCAudio.ts:307, 484`

```typescript
// ❌ CURRENT (WRONG):
const connectWebSocket = useCallback(() => {
  // ...connection logic (doesn't use isMuted)
}, [sessionId, isMuted, onMessage, ...]);  // ❌ isMuted causes re-creation
//              ^^^^^^^^
```

**Problem**:
- `connectWebSocket` doesn't use `isMuted` in its body
- Including it causes function re-creation on every mute toggle
- Can trigger React effects unnecessarily
- Potential performance issues

**Impact**: **MEDIUM** - Unnecessary re-renders, code smell

**Fix**:
```typescript
// ✅ CORRECT:
const connectWebSocket = useCallback(() => {
  // ...connection logic
}, [sessionId, onMessage, ...]);  // ✅ Removed isMuted
```

---

### VIOLATION #3: Mixed Responsibilities in start()

**Location**: `frontend/src/hooks/useWebRTCAudio.ts:330-484`

```typescript
// ❌ CURRENT (WRONG):
const start = useCallback(async () => {
  // 1. Request microphone
  const stream = await getUserMedia();

  // 2. Create MediaRecorder
  const recorder = new MediaRecorder(stream);

  // 3. Connect WebSocket
  connectWebSocket();  // ❌ WRONG: Mixes mic and WebSocket concerns

  // 4. Unmute
  setIsMuted(false);
}, [...]);
```

**Problem**:
- `start()` is called by `toggleMute()` to unmute
- But it ALSO creates WebSocket (heavy operation)
- Every mute/unmute cycle might create new WebSocket
- Inconsistent with `stop()` which keeps WebSocket alive

**Impact**: **MEDIUM** - Architectural debt, confusion

**Fix**: Separate `startMicrophone()` from `startSession()`

---

## Detailed Behavior Specification

### When User Clicks MIC OFF:

```typescript
// ✅ CORRECT BEHAVIOR
function muteMicrophone() {
  // 1. Disable audio track (generates silence)
  mediaStream.getAudioTracks().forEach(track => {
    track.enabled = false;
  });

  // 2. Stop MediaRecorder (stop capturing)
  if (mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
  }

  // 3. Update UI state
  setIsMuted(true);

  // ❌ DO NOT:
  // - Disconnect WebSocket
  // - Stop processing incoming messages
  // - Pause TTS audio
  // - Clear transcripts
  // - Disable auto-reconnect
}
```

### When User Clicks MIC ON:

```typescript
// ✅ CORRECT BEHAVIOR
function unmuteMicrophone() {
  // 1. Enable audio track
  mediaStream.getAudioTracks().forEach(track => {
    track.enabled = true;
  });

  // 2. Start MediaRecorder
  if (mediaRecorder.state === 'inactive') {
    mediaRecorder.start(timeslice);
  }

  // 3. Update UI state
  setIsMuted(false);

  // ❌ DO NOT:
  // - Create new WebSocket (already connected)
  // - Request new permissions (already granted)
  // - Clear conversation
}
```

---

## Implementation Plan

### Phase 1: Critical Fix (Priority 1) ⚡

**Goal**: Remove `!isMuted` check from WebSocket auto-reconnect

**Files Modified**:
- `frontend/src/hooks/useWebRTCAudio.ts`

**Changes**:
```diff
  ws.onclose = (event) => {
    logger.info('🔌 WebSocket CLOSED');
    setConnectionState('disconnected');

    if (
      reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS &&
-     !isMuted
    ) {
      reconnectAttemptsRef.current += 1;
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connectWebSocket();
      }, RECONNECT_INTERVAL);
    }
  };
```

**Testing**:
1. Start conversation, speak to AI
2. Click mic OFF while AI is responding
3. Disconnect WiFi briefly (trigger WebSocket close)
4. Reconnect WiFi
5. **Expected**: WebSocket auto-reconnects, AI response continues
6. **Verify**: Logs show "🔄 Reconnecting..." regardless of mute state

**Impact**: Fixes the primary bug - AI responses work when mic is muted

---

### Phase 2: Dependency Cleanup (Priority 2) 🧹

**Goal**: Remove `isMuted` from all dependency arrays where it's not used

**Files Modified**:
- `frontend/src/hooks/useWebRTCAudio.ts`

**Changes**:
```diff
  const connectWebSocket = useCallback(() => {
    // ...
- }, [connectWebSocket, timeslice, onError, sessionId, isMuted, connectionState]);
+ }, [connectWebSocket, timeslice, onError, sessionId, connectionState]);

  const start = useCallback(async () => {
    // ...
- }, [connectWebSocket, timeslice, onError, sessionId, isMuted, connectionState]);
+ }, [connectWebSocket, timeslice, onError, sessionId, connectionState]);

  useEffect(() => {
    // ...
- }, [autoStart, sessionId, start, disconnectWebSocket]);
+ }, [autoStart, sessionId, start, disconnectWebSocket]);
```

**Testing**:
1. Toggle mic on/off rapidly 10 times
2. **Expected**: No excessive WebSocket reconnections
3. **Verify**: Check React DevTools Profiler - reduced re-renders

**Impact**: Performance improvement, cleaner code

---

### Phase 3: Architecture Refactor (Priority 3) 🏗️

**Goal**: Separate microphone control from session control

**Files Modified**:
- `frontend/src/hooks/useWebRTCAudio.ts`

**New Function Structure**:

```typescript
// Microphone control (affected by mute)
const startMicrophone = useCallback(async () => {
  // Only handle mic, assume WebSocket already connected
  if (!mediaStreamRef.current) {
    const stream = await getUserMedia();
    mediaStreamRef.current = stream;
  }

  mediaStreamRef.current.getAudioTracks().forEach(track => {
    track.enabled = true;
  });

  if (mediaRecorderRef.current?.state === 'inactive') {
    mediaRecorderRef.current.start(timeslice);
  }

  setIsMuted(false);
  setIsRecording(true);
}, [timeslice]);

const stopMicrophone = useCallback(() => {
  // Only stop mic, leave WebSocket alone
  if (mediaRecorderRef.current?.state !== 'inactive') {
    mediaRecorderRef.current.stop();
  }

  mediaStreamRef.current?.getAudioTracks().forEach(track => {
    track.enabled = false;
  });

  setIsMuted(true);
  setIsRecording(false);
}, []);

// Session control (lifecycle management)
const startSession = useCallback(async () => {
  await startMicrophone();
  connectWebSocket();
}, [startMicrophone, connectWebSocket]);

const endSession = useCallback(() => {
  stopMicrophone();
  disconnectWebSocket();
}, [stopMicrophone, disconnectWebSocket]);

// Simple toggle (for UI button)
const toggleMute = useCallback(() => {
  if (isMuted) {
    startMicrophone();  // ✅ Only affects mic
  } else {
    stopMicrophone();   // ✅ Only affects mic
  }
}, [isMuted, startMicrophone, stopMicrophone]);
```

**Backward Compatibility**:
- Keep `start()` and `stop()` as aliases initially
- Deprecate them in favor of new functions
- Update calling code gradually

**Testing**:
1. Use new `toggleMute()` - should only affect mic
2. Use `startSession()` for initial connection - should start both
3. Use `endSession()` when leaving page - should stop both
4. **Verify**: Clear separation of concerns in logs

**Impact**: Cleaner architecture, easier to maintain

---

### Phase 4: UI Clarity (Priority 4) 🎨

**Goal**: Update UI indicators to be independent of mic state

**Files Modified**:
- `frontend/src/pages/VoxbridgePage.tsx`

**Changes**:
```diff
  {/* TTS Pending Indicator */}
- {isMuted && isPendingTTS && (
+ {isPendingTTS && (
    <div className="text-xs text-amber-500 flex items-center gap-1">
      <Volume2 className="w-3 h-3 animate-pulse" />
-     AI is speaking - mic off
+     {isMuted ? 'AI is speaking - mic off' : 'AI is speaking'}
    </div>
  )}
```

**Testing**:
1. Start conversation with mic ON
2. While AI is speaking, verify indicator shows "AI is speaking"
3. Click mic OFF during AI speech
4. **Expected**: Indicator updates to "AI is speaking - mic off"
5. **Verify**: TTS continues playing normally

**Impact**: Better UX, clearer messaging

---

## Testing Plan

### Test 1: Basic Mute/Unmute
1. Click mic ON → Start speaking → Click mic OFF
2. **Expected**: Mic stops, WebSocket stays connected
3. Click mic ON again
4. **Expected**: Mic starts, no reconnection needed

### Test 2: Mute During Partial Transcript Streaming
1. Click mic ON, start speaking continuously
2. **While speaking**, click mic OFF
3. **Expected**:
   - Partial transcripts stop appearing (no new audio sent)
   - Already received partials remain visible
   - No system freeze
   - No state conflicts in console

### Test 3: Mute During AI Response Streaming
1. Complete a question, let AI start responding
2. **While AI chunks streaming**, click mic OFF
3. **Expected**:
   - AI response continues streaming
   - TTS audio plays normally
   - WebSocket stays connected
   - No freeze

### Test 4: Mute During TTS Playback
1. Complete a question, wait for TTS to start playing
2. **During TTS audio**, click mic OFF
3. **Expected**:
   - TTS audio continues playing (speaker mute is separate)
   - Mic stops capturing
   - Can unmute and ask follow-up immediately

### Test 5: WebSocket Disconnect While Muted
1. Click mic OFF
2. Trigger network disconnect (airplane mode 5 seconds)
3. Reconnect network
4. **Expected**:
   - WebSocket auto-reconnects (regardless of mute)
   - Logs show "🔄 Reconnecting..."
   - No "muted" check blocking reconnect

### Test 6: Multi-Turn Conversation
1. Ask question 1 → Click mic OFF → AI responds → TTS plays
2. Click mic ON → Ask question 2 → Click mic OFF → AI responds
3. Repeat 5 times
4. **Expected**:
   - Seamless conversation flow
   - No reconnections between turns
   - No state conflicts
   - No freezes

---

## Success Criteria

- ✅ No system freeze when clicking mic OFF at any point
- ✅ AI responses complete even when mic is muted
- ✅ TTS audio plays regardless of mic state
- ✅ WebSocket auto-reconnects even when muted
- ✅ Multi-turn conversations work smoothly
- ✅ No "STATE_CONFLICT" warnings in console
- ✅ Clean separation: mic control independent of session control
- ✅ Performance: Reduced unnecessary re-renders

---

## Rollback Plan

If critical issues arise after Phase 1:

1. **Immediate**: Revert the `!isMuted` check removal
2. **Workaround**: Tell users to keep mic ON during AI responses
3. **Investigation**: Add detailed logging to understand why reconnect is needed
4. **Long-term**: Consider alternative architectures

If issues arise after Phase 3 refactor:

1. Keep the refactored functions as internal
2. Don't deprecate `start()`/`stop()` yet
3. Use feature flag to toggle between old/new architecture
4. Gradual migration over multiple releases

---

## Timeline Estimate

- **Phase 1 (Critical)**: 30 minutes (1 line change + testing)
- **Phase 2 (Cleanup)**: 15 minutes (dependency array fixes)
- **Phase 3 (Refactor)**: 2 hours (new functions + backward compat)
- **Phase 4 (UI)**: 15 minutes (UI text updates)

**Total**: ~3 hours for complete implementation

**Recommended Approach**:
- Do Phase 1 immediately (critical fix)
- Test thoroughly
- Do Phase 2 in same PR
- Phase 3 and 4 can be separate PRs for better review

---

## Related Documentation

- [Original Bug Report](./tts-playback-on-mic-off-fix-plan.md) - Initial approach (deferred disconnect)
- [WebRTC Fixes Session](../WEBRTC_FIXES_SESSION_SUMMARY.md) - Related WebSocket fixes
- [MDN: MediaStreamTrack.enabled](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/enabled) - Official API docs
- [VoxBridge Architecture](../../ARCHITECTURE.md) - System overview

---

## Conclusion

The microphone mute functionality has too many responsibilities due to a single `!isMuted` check in the WebSocket auto-reconnect logic. This causes the system to freeze when the mic is turned off during conversation because:

1. WebSocket won't reconnect when muted
2. AI responses are lost
3. TTS audio can't be received
4. Multi-turn conversations break

**The fix is simple**: Remove `!isMuted` from the reconnect condition. Microphone state should ONLY control audio capture, not WebSocket connectivity or message processing.

**Expected outcome**: After fixing, clicking "Mic OFF" will behave like Discord/Zoom/Meet - it just mutes your microphone, everything else continues normally.
