# WebRTC Conversation UX Issues - Root Cause Analysis

**Date:** 2025-11-07  
**Scope:** VoxBridge WebRTC voice interface (browser → backend)  
**Focus:** 4 critical UX bugs affecting conversation flow  

---

## Executive Summary

This analysis identifies **4 architectural gaps** causing UX degradation in WebRTC voice conversations:

1. **AI Speaking Fails (TTS Playback)** - Race condition between event processing and audio buffer state
2. **Listening Indicator Persists** - Missing state cleanup after mic disconnection
3. **Transcript Truncation** - Overwriting transcript storage pattern (lost partials)
4. **30s Polling Too Slow** - Insufficient polling for real-time message updates

### Impact Severity
- **High**: Issue #1 (TTS failure prevents voice response)
- **Medium**: Issues #2, #3 (confusion, data loss)
- **Low**: Issue #4 (minor latency degradation)

---

## Issue 1: AI Speaking Doesn't Work Sometimes

### Observed Behavior
TTS audio fails to play intermittently despite:
- Backend sending `tts_complete` event ✅
- Frontend receiving `tts_complete` event ✅
- `audioPlayback.completeAudio()` being called ✅
- No JavaScript errors in console ❌

### Root Cause Analysis

**File:** `frontend/src/pages/VoxbridgePage.tsx` (lines 293-310)

```typescript
case 'tts_complete':
  console.log(`✅ TTS complete (${message.data.duration_s?.toFixed(2)}s)`);
  
  // Play buffered TTS audio if not muted
  if (!isSpeakerMuted) {
    console.log('🔍 DEBUG: Calling audioPlayback.completeAudio()...');
    try {
      await audioPlayback.completeAudio();  // ⚠️ RACE CONDITION!
    } catch (error) {
      console.error('🔍 DEBUG: completeAudio() threw error:', error);
    }
  }
```

**File:** `frontend/src/hooks/useAudioPlayback.ts` (lines 125-135)

```typescript
const completeAudio = useCallback(async () => {
  console.log(`🔍 DEBUG: completeAudio() called, ${audioChunksRef.current.length} chunks buffered`);
  
  if (audioChunksRef.current.length === 0) {  // ⚠️ SILENT FAILURE!
    console.warn('⚠️ No audio chunks buffered');
    return;  // Exits silently - no error thrown
  }
  
  await playAudioChunks(audioChunksRef.current);
  audioChunksRef.current = [];
}, [playAudioChunks]);
```

### Why It Happens

**Race Condition Sequence:**
1. Backend sends binary audio chunks via WebSocket (`websocket.send_bytes()`)
2. Backend immediately sends `tts_complete` JSON event
3. Frontend receives `tts_complete` **before all binary chunks arrive** (network buffering)
4. `completeAudio()` called with empty `audioChunksRef.current` array
5. Function exits silently (logs warning but throws no error)
6. Binary chunks arrive **after** playback attempt (orphaned in buffer)

**Evidence from Backend:** `src/voice/webrtc_handler.py` (lines 1100-1152)

```python
async def on_audio_chunk(chunk: bytes):
    # Stream chunk to browser as binary WebSocket frame
    if self.is_active:
        await self.websocket.send_bytes(chunk)  # ⬅️ Binary frame sent
        total_bytes += len(chunk)

# After synthesis completes...
if self.is_active:
    await self.websocket.send_json({  # ⬅️ JSON event sent immediately
        "event": "tts_complete",
        "data": {
            "session_id": self.session_id,
            "duration_s": total_latency_s
        }
    })
```

**Network Layer Issue:**
- Binary WebSocket frames (`send_bytes()`) and text frames (`send_json()`) use **different TCP buffers**
- Python's `send_bytes()` may buffer multiple chunks before flushing
- `send_json()` flushes immediately (smaller payload)
- Frontend receives JSON event before all binary frames arrive

### Discord Comparison

**Discord WORKS because:**
- TTS audio plays **directly in Discord voice channel** (no browser playback)
- Backend controls playback timing (no race condition with frontend)
- No dependency on WebSocket binary frame ordering

**File:** `src/plugins/discord_plugin.py` - TTS synthesis sends audio **directly to Discord voice sink**:

```python
# Discord sends audio directly to voice channel (no WebSocket dependency)
audio_sink.write(audio_bytes)
```

### Proposed Fix

**Strategy:** Wait for audio chunks with timeout + fallback

**File:** `frontend/src/pages/VoxbridgePage.tsx` (lines 293-310)

```typescript
case 'tts_complete':
  console.log(`✅ TTS complete (${message.data.duration_s?.toFixed(2)}s)`);
  
  if (!isSpeakerMuted) {
    // ✅ FIX: Wait for audio chunks with timeout
    const MAX_WAIT_MS = 500;  // 500ms should be enough for network buffering
    const startTime = Date.now();
    
    while (audioChunksRef.current.length === 0 && (Date.now() - startTime) < MAX_WAIT_MS) {
      await new Promise(resolve => setTimeout(resolve, 50));  // Poll every 50ms
    }
    
    if (audioChunksRef.current.length === 0) {
      console.error('❌ TTS complete but no audio chunks received after 500ms');
      toast.error('Audio playback failed', 'No audio data received');
    } else {
      await audioPlayback.completeAudio();
    }
  }
```

**Alternative Fix (Backend):** Add delay before sending `tts_complete`

```python
# After synthesis completes...
await asyncio.sleep(0.2)  # 200ms delay for WebSocket buffer flush

if self.is_active:
    await self.websocket.send_json({
        "event": "tts_complete",
        ...
    })
```

### Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| **Frontend wait loop** | No backend changes needed | Adds latency to playback start |
| **Backend delay** | Simple fix | Artificial delay reduces responsiveness |
| **Reorder events** | Proper sequencing | Requires refactoring WebSocket send order |

**Recommendation:** **Frontend wait loop** (more robust, no artificial delays)

---

## Issue 2: Listening Indicator Appears When It Shouldn't

### Observed Behavior
"Listening..." indicator shows even when:
- Microphone is muted/disabled ❌
- User is not speaking ❌
- WebSocket connection is closed ❌

### Root Cause Analysis

**File:** `frontend/src/pages/VoxbridgePage.tsx` (lines 214-225)

```typescript
case 'partial_transcript':
  // Only show listening indicator if we have actual transcript text AND connection is active
  if (message.data.text && connectionState === 'connected') {
    if (!listeningStartTimeRef.current) {
      logUIEvent('🎤', 'LISTENING (WebRTC)', ...);
      listeningStartTimeRef.current = Date.now();
    }
    
    setVoicePartialTranscript(message.data.text);
    setIsListening(true);  // ⚠️ Set to true, never cleared!
  }
  break;
```

**Problem:** `setIsListening(true)` is called on partial transcript, but **never cleared** when:
1. Mic is toggled off
2. WebSocket disconnects
3. Transcription ends without final transcript

**File:** `frontend/src/hooks/useWebRTCAudio.ts` (lines 463-489)

```typescript
const stop = useCallback(() => {
  log('🛑 stop() called - stopping audio capture');
  
  // Stop MediaRecorder
  if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
    mediaRecorderRef.current.stop();
  }
  
  // Stop media stream tracks
  if (mediaStreamRef.current) {
    mediaStreamRef.current.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  }
  
  disconnectWebSocket();
  
  setIsMuted(true);
  setIsRecording(false);
  // ⚠️ MISSING: Does NOT notify parent to clear isListening!
}, [disconnectWebSocket]);
```

### Why It Happens

**State Management Gap:**
- `isListening` lives in `VoxbridgePage.tsx` (parent component)
- `stop()` lives in `useWebRTCAudio.ts` (child hook)
- **No callback** from hook to parent when recording stops
- Parent only clears `isListening` on `final_transcript` event (which may never arrive if mic stops mid-stream)

### Discord Comparison

**Discord WORKS because:**

**File:** `frontend/src/pages/VoxbridgePage.tsx` (lines 410-432)

```typescript
else if (message.event === 'partial_transcript') {
  setPartialTranscript(message.data.text);
  
  // Start listening animation indicator (unified experience)
  if (!isListening && message.data.text) {  // ✅ Checks isListening BEFORE setting
    setIsListening(true);
    listeningStartTimeRef.current = Date.now();
  }
  setVoicePartialTranscript(message.data.text);
  
} else if (message.event === 'final_transcript') {
  // Clear analytics state
  setActiveSpeaker(null);
  setPartialTranscript('');
  
  // Stop listening animation
  setIsListening(false);  // ✅ ALWAYS clears on final transcript
  listeningStartTimeRef.current = null;
  setVoicePartialTranscript('');
```

**Key Difference:**
- Discord **always** receives `final_transcript` event (backend guarantees it)
- WebRTC may **not** receive `final_transcript` if mic stops before finalization

### Proposed Fix

**Strategy:** Clear listening state on ALL termination events

**File:** `frontend/src/hooks/useWebRTCAudio.ts` (add callback parameter)

```typescript
export interface UseWebRTCAudioOptions {
  // ... existing options
  onRecordingStop?: () => void;  // ✅ NEW: Callback when recording stops
}

const stop = useCallback(() => {
  log('🛑 stop() called - stopping audio capture');
  
  // ... existing stop logic
  
  setIsMuted(true);
  setIsRecording(false);
  
  // ✅ FIX: Notify parent to clear UI state
  if (options.onRecordingStop) {
    options.onRecordingStop();
  }
}, [disconnectWebSocket, options]);
```

**File:** `frontend/src/pages/VoxbridgePage.tsx` (use callback)

```typescript
const {
  isMuted,
  toggleMute,
  connectionState,
  permissionError,
  isRecording,
} = useWebRTCAudio({
  sessionId: activeSessionId,
  onMessage: handleWebRTCAudioMessage,
  onBinaryMessage: handleBinaryMessage,
  onError: handleAudioError,
  onServiceError: handleServiceError,
  onRecordingStop: () => {  // ✅ NEW: Clear listening state
    setIsListening(false);
    setVoicePartialTranscript('');
    listeningStartTimeRef.current = null;
  },
  autoStart: false,
  timeslice: 100,
});
```

### Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| **Callback pattern** | Clean separation of concerns | Adds callback parameter |
| **Ref sharing** | Direct state access | Tight coupling, violates encapsulation |
| **Event emitter** | Flexible multi-listener | Overkill for single callback |

**Recommendation:** **Callback pattern** (standard React pattern, minimal overhead)

---

## Issue 3: Transcripts Cutting Off First Part

### Observed Behavior
User says: "Hello, how are you today?"  
Transcript shows: "how are you today?" (missing "Hello")

### Root Cause Analysis

**File:** `src/voice/webrtc_handler.py` (lines 221-225)

```python
if not is_final:
    # Partial transcript
    logger.info(f"📝 [TRANSCRIPT] Storing PARTIAL in self.current_transcript: \"{text}\"")
    self.current_transcript = text  # ⚠️ OVERWRITES previous partial!
    await self._send_partial_transcript(text)
else:
    # Final transcript
    prev_transcript = self.current_transcript
    logger.info(f"✅ [TRANSCRIPT] Storing FINAL in self.current_transcript: \"{text}\"")
    self.current_transcript = text  # ⚠️ OVERWRITES previous partials!
```

### Why It Happens

**WhisperX Partial Transcript Behavior:**
- Sends **incremental** partials, not cumulative
- Partial #1: "Hello"
- Partial #2: "how are you"
- Partial #3: "today"
- Final: "how are you today" (may exclude early words with low confidence)

**Backend Storage Pattern:**
- `self.current_transcript = text` **OVERWRITES** previous value
- Early partials ("Hello") are **lost** when later partials arrive
- Final transcript may **not include** early low-confidence words

**Evidence from Logs (diagnostics added in code):**

```python
# Line 232-236 (diagnostic check)
if prev_transcript and prev_transcript != text:
    logger.warning(f"⚠️ [TRANSCRIPT] FINAL differs from previous PARTIAL!")
    logger.warning(f"   - Previous PARTIAL: \"{prev_transcript}\"")
    logger.warning(f"   - Current FINAL:    \"{text}\"")
```

This diagnostic **confirms** the overwrite pattern causes data loss.

### Discord Comparison

**Discord WORKS because:**

**File:** `src/plugins/discord_plugin.py` - Uses **accumulative** transcript buffer

```python
# Discord accumulates partial transcripts
self.partial_transcripts.append(text)

# Final transcript combines ALL partials
final_text = ' '.join(self.partial_transcripts)
self.partial_transcripts = []
```

**Key Difference:**
- Discord **accumulates** partials in a list
- WebRTC **overwrites** with latest partial (loses history)

### Proposed Fix

**Strategy:** Accumulate partial transcripts OR trust WhisperX final

**Option A:** Accumulate partials (Discord pattern)

```python
class WebRTCVoiceHandler:
    def __init__(self, ...):
        # ... existing init
        self.partial_transcripts = []  # ✅ NEW: Accumulate partials
        self.current_transcript = ""
        
    async def on_transcript(text: str, is_final: bool, metadata: Dict):
        if not is_final:
            # Partial transcript - accumulate
            self.partial_transcripts.append(text)
            combined = ' '.join(self.partial_transcripts)
            self.current_transcript = combined
            await self._send_partial_transcript(combined)
        else:
            # Final transcript - use WhisperX final OR combined partials
            if text:
                self.current_transcript = text  # Trust WhisperX final
            else:
                # Fallback to combined partials if final is empty
                self.current_transcript = ' '.join(self.partial_transcripts)
            
            self.partial_transcripts = []  # Clear for next turn
```

**Option B:** Trust WhisperX final only (simpler)

```python
async def on_transcript(text: str, is_final: bool, metadata: Dict):
    if not is_final:
        # Show partial in UI but don't store permanently
        await self._send_partial_transcript(text)
    else:
        # Only store final transcript
        self.current_transcript = text
```

### Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| **Accumulate partials** | No data loss, comprehensive transcript | May include low-confidence words |
| **Trust final only** | Clean, high-confidence text | May lose early words if WhisperX excludes them |
| **Hybrid** (use both) | Best of both worlds | Complex logic, potential duplicates |

**Recommendation:** **Accumulate partials** (matches Discord behavior, prevents data loss)

### Additional Investigation Needed

**File:** `src/services/stt_service.py` - Check WhisperX partial behavior

```python
# Line 558-568 (partial transcript handling)
elif msg_type == 'partial':
    text = data.get('text', '')
    if text:
        logger.info(f"🔄 STT Partial (session={session_id}): \"{text}\"")
        if connection.callback:
            await connection.callback(text, False, metadata)
```

**Question:** Does WhisperX send:
1. **Incremental** partials? ("Hello" → "how" → "are")
2. **Cumulative** partials? ("Hello" → "Hello how" → "Hello how are")

**Action:** Add WhisperX logging to confirm partial transcript structure:

```python
logger.info(f"🔍 WhisperX partial structure check:")
logger.info(f"   - Raw text: \"{text}\"")
logger.info(f"   - Length: {len(text)} chars")
logger.info(f"   - Word count: {len(text.split())}")
```

---

## Issue 4: 30s Polling Too Slow

### Observed Behavior
After AI responds, message appears in UI **10-20 seconds later** (negative UX).

### Root Cause Analysis

**File:** `frontend/src/pages/VoxbridgePage.tsx` (lines 150-187)

```typescript
// Fetch messages for active session
const { data: messages = [], isLoading: isLoadingMessages } = useQuery<Message[]>({
  queryKey: ['messages', activeSessionId],
  queryFn: async () => {
    if (!activeSessionId) return [];
    
    const result = await api.getSessionMessages(activeSessionId);
    return result;
  },
  enabled: !!activeSessionId,
  refetchInterval: 30000, // ⚠️ Poll every 30 seconds (too slow!)
});
```

### Why It Happens

**Intended Design:**
- WebSocket provides **real-time** updates via `invalidateQueries()`
- Polling (30s) is **backup** to catch any missed events

**Reality:**
- WebSocket events **do** trigger invalidation (lines 241-244, 467-469)
- BUT: Query refetch may **not execute** immediately due to React Query caching
- 30s polling is fallback, but users perceive it as primary mechanism

**Evidence from Code:**

```typescript
// Line 241-244 (WebRTC final transcript)
if (activeSessionId) {
  logUIEvent('🔄', 'QUERY (WebRTC)', `Invalidating messages query (session: ${activeSessionId})`);
  queryClient.invalidateQueries({ queryKey: ['messages', activeSessionId] });
}

// Line 467-469 (Discord AI response complete)
if (activeSessionId) {
  logUIEvent('🔄', 'QUERY', `Invalidating messages query (session: ${activeSessionId})`);
  queryClient.invalidateQueries({ queryKey: ['messages', activeSessionId] });
}
```

**React Query Behavior:**
- `invalidateQueries()` marks query as stale
- Refetch **only happens** if:
  1. Component is mounted ✅
  2. Window is focused ✅
  3. Network is online ✅
  4. Query is not in `staleTime` grace period ❌ (default: 0ms, should refetch)

### Discord Comparison

**Discord WORKS FASTER because:**
- Same invalidation pattern (no difference)
- May **appear** faster due to visual feedback (streaming chunks)
- No actual difference in database polling behavior

### Proposed Fix

**Strategy:** Reduce polling interval for active conversations

**File:** `frontend/src/pages/VoxbridgePage.tsx` (lines 186)

```typescript
const { data: messages = [] } = useQuery<Message[]>({
  queryKey: ['messages', activeSessionId],
  queryFn: async () => {
    if (!activeSessionId) return [];
    return await api.getSessionMessages(activeSessionId);
  },
  enabled: !!activeSessionId,
  refetchInterval: isStreaming || isVoiceAIGenerating ? 2000 : 10000, // ✅ FIX: 2s during active, 10s idle
  staleTime: 0, // Force immediate refetch on invalidation
  refetchOnWindowFocus: true,
});
```

**Alternative Fix:** Force immediate refetch

```typescript
// In handleWebRTCAudioMessage (line 275-278)
case 'ai_response_complete':
  // Force immediate refetch instead of just invalidation
  await queryClient.refetchQueries({ queryKey: ['messages', activeSessionId] });
  break;
```

### Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| **Reduce interval (2s)** | Fast updates, low latency | Higher server load |
| **Force refetch** | Immediate updates | May skip React Query cache |
| **Increase to 5s** | Balanced | Still slower than desired |
| **Keep 30s + fix WS** | Minimal changes | Requires debugging WebSocket invalidation |

**Recommendation:** **Reduce to 5s** (balance of UX and server load)

### Additional Investigation Needed

**File:** `frontend/src/pages/VoxbridgePage.tsx` (lines 150-187)

Add diagnostics to verify invalidation:

```typescript
const { data: messages = [] } = useQuery<Message[]>({
  queryKey: ['messages', activeSessionId],
  queryFn: async () => {
    const fetchStart = Date.now();
    console.log(`[QUERY] Fetching messages at ${fetchStart}`);
    
    const result = await api.getSessionMessages(activeSessionId);
    
    const fetchEnd = Date.now();
    console.log(`[QUERY] Fetch complete in ${fetchEnd - fetchStart}ms, ${result.length} messages`);
    
    return result;
  },
  enabled: !!activeSessionId,
  refetchInterval: 5000, // ✅ CHANGED: 5s instead of 30s
  onSuccess: (data) => {
    console.log(`[QUERY] Query succeeded, ${data.length} messages`);
  },
  onError: (error) => {
    console.error(`[QUERY] Query failed:`, error);
  },
});
```

**Action:** Monitor logs to confirm:
1. `invalidateQueries()` is called ✅ (already logged)
2. Refetch actually executes ❓ (add logging)
3. Time between invalidation and refetch ❓ (measure latency)

---

## Unified Architectural Approach

### Problem Pattern Recognition

All 4 issues stem from **state synchronization gaps** between:
1. Frontend (React state, hooks, components)
2. Backend (Python async handlers, WebSocket events)
3. Network layer (TCP buffering, frame ordering)

### Recommended Solution: Event-Driven State Machine

Instead of patching each issue individually, implement a **unified state machine** for conversation flow:

```typescript
// Frontend state machine
type ConversationState = 
  | 'idle'           // Ready for user input
  | 'listening'      // User speaking
  | 'processing'     // STT → LLM
  | 'responding'     // TTS playback
  | 'error';         // Error state

const [conversationState, setConversationState] = useState<ConversationState>('idle');

// State transitions triggered by WebSocket events
switch (message.event) {
  case 'partial_transcript':
    if (conversationState === 'idle') {
      setConversationState('listening');
    }
    break;
    
  case 'final_transcript':
    setConversationState('processing');
    break;
    
  case 'ai_response_complete':
    setConversationState('responding');
    break;
    
  case 'tts_complete':
    setConversationState('idle');
    break;
    
  case 'error':
    setConversationState('error');
    break;
}
```

### Benefits of State Machine Approach

1. **Issue #1 (TTS Playback)**: State guards prevent race conditions
   - `tts_complete` only processed if `conversationState === 'responding'`
   - Audio chunks buffered during `responding` state, played after transition

2. **Issue #2 (Listening Indicator)**: State determines UI rendering
   - Indicator shows only when `conversationState === 'listening'`
   - State cleared on transition to any other state

3. **Issue #3 (Transcript Truncation)**: State tracks partial accumulation
   - Partials accumulated while `conversationState === 'listening'`
   - Cleared on transition to `processing`

4. **Issue #4 (Polling)**: State-aware polling intervals
   - Fast polling (2s) during `listening`, `processing`, `responding`
   - Slow polling (10s) during `idle`

---

## Implementation Priority

### Phase 1: Critical Fixes (1-2 days)
1. **Issue #1 (TTS Playback)** - Add frontend wait loop for audio chunks
2. **Issue #2 (Listening Indicator)** - Add `onRecordingStop` callback

### Phase 2: Data Integrity (2-3 days)
3. **Issue #3 (Transcript Truncation)** - Implement partial accumulation pattern

### Phase 3: Polish (1 day)
4. **Issue #4 (Polling)** - Reduce refetchInterval to 5s

### Phase 4: Architecture (3-5 days)
5. **State Machine Refactor** - Unify all state transitions

---

## Risk Assessment

### Low Risk (Phases 1-3)
- Isolated changes to specific components
- Backward compatible
- Easy to rollback

### Medium Risk (Phase 4)
- Major refactor of state management
- Potential for regressions in other areas
- Requires comprehensive testing

### Mitigation Strategy
1. Implement Phases 1-3 first (quick wins)
2. User testing after each phase
3. Phase 4 only if state management issues persist

---

## Testing Plan

### Manual Testing
- [ ] Test TTS playback 10 times in a row (verify 100% success rate)
- [ ] Test listening indicator with mic toggle
- [ ] Test transcript completeness with long utterances
- [ ] Test message polling during active conversation

### Automated Testing
- [ ] Add E2E test for TTS playback
- [ ] Add integration test for listening indicator lifecycle
- [ ] Add unit test for transcript accumulation
- [ ] Add test for polling interval switching

---

## Appendix: Code Locations Reference

### Frontend
- **VoxbridgePage.tsx** (lines 63-1395) - Main conversation UI
  - Lines 293-310: TTS complete handler (Issue #1)
  - Lines 214-225: Partial transcript handler (Issue #2)
  - Lines 186: Polling interval (Issue #4)

- **useWebRTCAudio.ts** (lines 98-548) - WebSocket + audio capture
  - Lines 463-489: Stop function (Issue #2)

- **useAudioPlayback.ts** (lines 29-158) - TTS audio playback
  - Lines 125-135: completeAudio function (Issue #1)

- **STTWaitingIndicator.tsx** (lines 1-87) - Listening indicator UI
  - Line 48: Conditional rendering based on isListening (Issue #2)

### Backend
- **webrtc_handler.py** (lines 1-1229) - WebRTC voice pipeline
  - Lines 203-239: Transcript callback (Issue #3)
  - Lines 1099-1152: TTS generation (Issue #1)
  - Lines 640-735: Silence monitor (Issue #3)

- **stt_service.py** (lines 1-696) - WhisperX abstraction
  - Lines 540-603: Message handler (Issue #3)

---

## Conclusion

The 4 WebRTC UX issues are **solvable with targeted fixes** (Phases 1-3), but a **state machine refactor** (Phase 4) would prevent future similar issues. Recommend implementing quick fixes first, then evaluating need for architectural changes based on user feedback.

**Estimated Total Effort:** 7-11 days (Phases 1-4)  
**Minimum Viable Fix:** 3-5 days (Phases 1-3 only)
