# TTS Playback on Mic Off - Bug Fix Plan

**Date**: November 8, 2025
**Branch**: `feature/tts-playback-mic-off-fix`
**Status**: ✅ **SUPERSEDED** - Replaced by Discord-Style Persistent Connection Architecture

## Problem Statement

When a user clicks the microphone OFF while AI is generating a response, the TTS audio gets cancelled and won't play. This violates user expectations - clicking mic OFF should mean "stop listening to me" but the AI should still finish speaking.

## Root Cause Analysis

### Current Behavior Flow

```
User clicks mic OFF
  ↓
toggleMute() → stop()
  ↓
disconnectWebSocket() (useWebRTCAudio.ts:492)
  ↓
WebSocket.close()
  ↓
Backend: _cleanup() triggered
  ↓
self.is_active = False (webrtc_handler.py:1440)
  ↓
TTS audio chunks skipped (line 1323: if self.is_active)
  ↓
❌ No audio reaches browser
```

### Code Evidence

**Frontend Issue** (`frontend/src/hooks/useWebRTCAudio.ts:469-505`):
```typescript
const stop = useCallback(() => {
  // Stop MediaRecorder + media stream
  if (mediaRecorderRef.current) {
    mediaRecorderRef.current.stop();
  }
  if (mediaStreamRef.current) {
    mediaStreamRef.current.getTracks().forEach((track) => track.stop());
  }

  // ❌ PROBLEM: Disconnects WebSocket immediately
  disconnectWebSocket();  // Line 492 - TOO EARLY!

  setIsMuted(true);
  setIsRecording(false);
}, [disconnectWebSocket, onRecordingStop]);
```

**Backend Issue** (`src/voice/webrtc_handler.py:1322-1330`):
```python
async def on_audio_chunk(chunk: bytes):
    # ❌ PROBLEM: Won't send if WebSocket closed
    if self.is_active:  # Line 1323
        await self.websocket.send_bytes(chunk)
        total_bytes += len(chunk)
```

### Why This Is a Bug

1. **User Expectation**: "Mic OFF" = "Stop listening to me" (input), NOT "Stop the AI from speaking" (output)
2. **Broken UX**: User can't stop their mic without cancelling the AI's response
3. **Contradicts Design**: Code comments (line 222-224) indicate multi-turn mode should keep connection open

## Solution Design

### Approach: Deferred WebSocket Disconnect

**Key Insight**: Separate "stop microphone input" from "close connection"

**New State Machine**:
1. **Listening (Mic ON)**: Recording audio + WebSocket open
2. **Muted (Mic OFF, TTS pending)**: NOT recording + WebSocket open (receiving TTS)
3. **Disconnected**: NOT recording + WebSocket closed (user left page or explicitly stopped)

### State Tracking

Add new state variable to track pending TTS:
- `isPendingTTS: boolean` - True when AI is generating/streaming response
- Set to `true` when `ai_response_start` received
- Set to `false` when `tts_complete` received

### Implementation Plan

## Phase 1: Frontend State Management

**File**: `frontend/src/hooks/useWebRTCAudio.ts`

### 1.1: Add TTS State Tracking (Lines ~50-60)

```typescript
// Add new state
const [isPendingTTS, setIsPendingTTS] = useState(false);
```

### 1.2: Update WebSocket Event Handlers (Lines ~150-230)

**Track TTS Start** (around line 200):
```typescript
case 'ai_response_start':
  setIsPendingTTS(true);  // TTS pipeline starting
  logger.info('🤖 AI response started - TTS pending');
  break;
```

**Track TTS Complete** (around line 222):
```typescript
case 'tts_complete':
  setIsPendingTTS(false);  // TTS finished
  logger.info('✅ TTS complete - no longer pending');

  // If user previously clicked mic OFF, now safe to disconnect
  if (isMuted && disconnectPending) {
    logger.info('🔌 Deferred disconnect - executing now');
    disconnectWebSocket();
  }
  break;
```

### 1.3: Refactor `stop()` Function (Lines 469-505)

**Before**:
```typescript
const stop = useCallback(() => {
  // Stop recording
  if (mediaRecorderRef.current) {
    mediaRecorderRef.current.stop();
  }
  if (mediaStreamRef.current) {
    mediaStreamRef.current.getTracks().forEach((track) => track.stop());
  }

  disconnectWebSocket();  // ❌ TOO EARLY

  setIsMuted(true);
  setIsRecording(false);
}, [disconnectWebSocket, onRecordingStop]);
```

**After**:
```typescript
const [disconnectPending, setDisconnectPending] = useState(false);

const stop = useCallback(() => {
  logger.info('🛑 stop() called - stopping microphone input');

  // ALWAYS stop microphone input (user wants to stop talking)
  if (mediaRecorderRef.current) {
    mediaRecorderRef.current.stop();
  }
  if (mediaStreamRef.current) {
    mediaStreamRef.current.getTracks().forEach((track) => track.stop());
  }

  setIsMuted(true);
  setIsRecording(false);
  onRecordingStop?.();

  // ✅ FIX: Only disconnect if NO pending TTS
  if (isPendingTTS) {
    logger.info('⏳ TTS in progress - deferring WebSocket disconnect');
    setDisconnectPending(true);  // Mark for later
  } else {
    logger.info('🔌 No pending TTS - disconnecting immediately');
    disconnectWebSocket();
  }
}, [isPendingTTS, disconnectWebSocket, onRecordingStop]);
```

### 1.4: Update Return Values (Line ~520)

```typescript
return {
  // ... existing returns
  isPendingTTS,  // Export for UI indicators
};
```

## Phase 2: UI Feedback

**File**: `frontend/src/pages/VoxbridgePage.tsx`

### 2.1: Show TTS Pending Indicator (Lines 820-850)

When `isMuted && isPendingTTS`:
- Show visual indicator: "AI is speaking... (mic muted)"
- Prevent user confusion about why WebSocket is still open
- Optional: Add "Stop AI" button if user wants to cancel

```tsx
{isMuted && isPendingTTS && (
  <div className="text-xs text-amber-500 flex items-center gap-1">
    <Volume2 className="w-3 h-3 animate-pulse" />
    AI is speaking... (mic muted)
  </div>
)}
```

## Phase 3: Backend Robustness (Optional)

**File**: `src/voice/webrtc_handler.py`

### 3.1: Handle Partial Disconnect Gracefully

Current code already handles this well:
- Line 1323: `if self.is_active` check prevents sending to closed connection
- Line 1367: `if self.is_active` check before sending completion event

**Optional Enhancement**: Add explicit logging when TTS completes but connection closed:
```python
if not self.is_active:
    logger.warning(f"⚠️ TTS completed but connection closed - {total_bytes} bytes generated but not sent")
```

## Testing Plan

### Manual Testing

**Test 1: Basic Flow (Happy Path)**
1. Start conversation (mic ON)
2. Speak to AI
3. Stop speaking (silence detected)
4. Click mic OFF while AI is thinking/speaking
5. **Expected**: AI audio still plays, then connection closes
6. **Verify**: Check logs for "TTS in progress - deferring WebSocket disconnect"

**Test 2: Rapid Mic Toggle**
1. Start conversation
2. Speak briefly
3. Click mic OFF → ON → OFF rapidly
4. **Expected**: WebSocket stays open until TTS completes
5. **Verify**: No connection errors, audio plays correctly

**Test 3: Page Close (Cleanup)**
1. Start conversation
2. Speak to AI
3. Close browser tab while TTS pending
4. **Expected**: WebSocket closes immediately (cleanup)
5. **Verify**: No hanging connections in backend logs

**Test 4: No TTS Pending**
1. Click mic ON
2. Click mic OFF immediately (before speaking)
3. **Expected**: WebSocket disconnects immediately
4. **Verify**: No deferred disconnect message

### Edge Cases

**Edge Case 1: TTS Error During Deferred State**
- If TTS synthesis fails while disconnect deferred
- **Expected**: `tts_complete` or error event triggers disconnect
- **Verify**: Connection doesn't hang forever

**Edge Case 2: Multiple Conversations**
1. Complete 1st conversation (TTS plays)
2. Click mic OFF
3. Click mic ON again (2nd conversation)
4. **Expected**: New conversation starts, old defer state cleared
5. **Verify**: No state pollution between conversations

## Files Modified

### Frontend (3 files)
1. **`frontend/src/hooks/useWebRTCAudio.ts`**
   - Add `isPendingTTS` state
   - Add `disconnectPending` state
   - Update WebSocket event handlers (ai_response_start, tts_complete)
   - Refactor `stop()` function to defer disconnect
   - Export `isPendingTTS` in return value

2. **`frontend/src/pages/VoxbridgePage.tsx`**
   - Add UI indicator for "AI speaking (mic muted)" state
   - Optional: Add "Stop AI" button

3. **`frontend/src/types/webrtc.ts`**
   - Update return type to include `isPendingTTS: boolean`

### Backend (optional logging enhancement)
4. **`src/voice/webrtc_handler.py`**
   - Add warning log when TTS completes with closed connection (line ~1370)

## Success Criteria - ✅ ALL MET (Alternative Solution)

- ✅ User can click mic OFF without cancelling AI's TTS audio
- ✅ TTS audio plays completely even when mic is muted
- ✅ WebSocket stays connected (better than closing after TTS - persistent like Discord)
- ✅ No errors in console/logs during normal flow
- ✅ Multi-turn conversations still work (mic ON → OFF → ON)
- ✅ Page close/refresh properly cleans up (no leaks)

---

## ✅ ACTUAL IMPLEMENTATION - Discord-Style Persistent Connection

**Decision**: The original "deferred disconnect" approach was superseded by a more comprehensive architectural solution.

**Why**: Instead of deferring disconnect until TTS completes, we implemented a Discord-style persistent connection where:
- WebSocket **never disconnects** on mic mute (stays open indefinitely)
- Mic mute only affects microphone audio capture
- User explicitly disconnects via "Leave Voice" button or component unmount
- Lower latency (no reconnection delay when unmuting)
- Simpler logic (no state tracking for deferred disconnect)

**Implementation**: See commit 610f368 - `refactor: implement Discord-style persistent WebSocket connection for voice chat`

**Files Modified**:
1. `frontend/src/hooks/useWebRTCAudio.ts` - New lifecycle functions
2. `frontend/src/components/AudioControls.tsx` - Removed connection state display
3. `frontend/src/components/ConversationList.tsx` - Added "Leave Voice" button
4. `src/whisper_server.py` - Enhanced buffer tracking logging

**Result**: This solution achieves all the original goals PLUS additional benefits (lower latency, better UX, simpler code).

**Original Plan Below** (for historical reference - not implemented as written)

## Rollback Plan

If issues arise:
1. Revert frontend changes to `useWebRTCAudio.ts`
2. Original behavior: mic OFF = immediate disconnect
3. No backend changes needed (already handles gracefully)

## Timeline Estimate

- **Research**: ✅ Complete
- **Implementation**: 1-2 hours
  - Phase 1 (Frontend state): 45 minutes
  - Phase 2 (UI feedback): 15 minutes
  - Phase 3 (Backend logging): 10 minutes
- **Testing**: 30 minutes
- **Documentation**: 15 minutes

**Total**: ~2-3 hours

## References

- [WebRTC Fixes Session Summary](../WEBRTC_FIXES_SESSION_SUMMARY.md) - Related WebSocket lifecycle fixes
- [useWebRTCAudio Hook](../../frontend/src/hooks/useWebRTCAudio.ts) - Audio capture and WebSocket management
- [WebRTC Handler](../../src/voice/webrtc_handler.py) - Backend WebSocket handler and TTS streaming
