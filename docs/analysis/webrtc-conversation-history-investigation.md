# WebRTC Conversation History Investigation

**Date**: 2025-11-05
**Issue**: WebRTC audio chat is not populating the conversation history area
**Status**: Root cause identified - Missing WebSocket event broadcasts

---

## Executive Summary

**Problem**: WebRTC voice chat is correctly capturing audio, transcribing, and generating AI responses, BUT the conversation history UI is not updating with messages.

**Root Cause**: WebRTC handler (`webrtc_handler.py`) sends events ONLY to the `/ws/voice` WebSocket connection (the active voice session), but does NOT broadcast to the `/ws/events` WebSocket (the global event stream that the conversation history UI listens to).

**Discord Works Because**: The Discord plugin broadcasts ALL conversation events to `/ws/events` via the global `ws_manager`, which the frontend `VoxbridgePage` component listens to.

**Fix Required**: WebRTC handler must broadcast events to the global WebSocket manager (`ws_manager`) in addition to sending events to the voice WebSocket connection.

---

## Architecture Overview

### Two Separate WebSocket Connections

VoxBridge uses **two different WebSocket endpoints** for different purposes:

1. **`/ws/events`** (Global Event Stream)
   - **Purpose**: Real-time notifications for ALL conversation activity (Discord + WebRTC)
   - **Listeners**: `VoxbridgePage.tsx` conversation history component
   - **Connection Manager**: `ws_manager` (ConnectionManager singleton in `server.py`)
   - **Events**: `partial_transcript`, `final_transcript`, `ai_response_chunk`, `ai_response_complete`, `metrics_updated`, etc.
   - **Scope**: Broadcasts to ALL connected frontend clients

2. **`/ws/voice`** (WebRTC Voice Session)
   - **Purpose**: Bidirectional audio streaming for active voice chat session
   - **Listeners**: `useWebRTCAudio` hook (active recording session only)
   - **Connection**: Direct WebSocket connection per voice session
   - **Events**: Same as above PLUS `tts_start`, `tts_complete`, binary audio chunks
   - **Scope**: Session-specific, dies when voice session ends

### Event Flow Comparison

```
┌─────────────────────────────────────────────────────────────────┐
│                     DISCORD PLUGIN (WORKING)                    │
└─────────────────────────────────────────────────────────────────┘

User speaks in Discord
    ↓
AudioReceiver → STTService → Transcription
    ↓
[Line 1271] ws_manager.broadcast({
    "event": "partial_transcript",
    "data": { "userId": user_id, "text": text }
})
    ↓
Frontend /ws/events listener receives event
    ↓
VoxbridgePage handleMessage() updates conversation state
    ↓
✅ Conversation history updates in real-time


┌─────────────────────────────────────────────────────────────────┐
│                  WEBRTC HANDLER (NOT WORKING)                   │
└─────────────────────────────────────────────────────────────────┘

User speaks in browser
    ↓
useWebRTCAudio → /ws/voice → WebRTCVoiceHandler → STTService
    ↓
[Line 450] websocket.send_json({
    "event": "partial_transcript",
    "data": { "text": text }
})
    ↓
❌ ONLY sent to /ws/voice connection (voice session)
❌ NOT broadcast to /ws/events (global event stream)
    ↓
Frontend /ws/events listener NEVER receives event
    ↓
❌ Conversation history NEVER updates
```

---

## Detailed Code Analysis

### 1. Frontend Conversation Display (`VoxbridgePage.tsx`)

**How Conversation History Works**:

```typescript
// Lines 462-465: Listens to /ws/events for real-time updates
const { isConnected: wsConnected } = useWebSocket('/ws/events', {
  onMessage: handleMessage
});

// Lines 322-460: handleMessage() processes Discord events
const handleMessage = useCallback((message: any) => {
  // ...

  // Line 359: Handle partial_transcript
  else if (message.event === 'partial_transcript') {
    setPartialTranscript(message.data.text);
    setVoicePartialTranscript(message.data.text);
  }

  // Line 369: Handle final_transcript
  else if (message.event === 'final_transcript') {
    setPartialTranscript('');
    setVoicePartialTranscript('');

    // Lines 384-393: Save to database
    if (activeSessionId && message.data.text) {
      api.addMessage(activeSessionId, {
        role: 'user',
        content: message.data.text,
      }).then(() => {
        queryClient.invalidateQueries({ queryKey: ['messages', activeSessionId] });
      });
    }
  }

  // Line 394: Handle ai_response_chunk
  else if (message.event === 'ai_response_chunk') {
    // Lines 397-428: Update conversation with streaming chunks
    queryClient.setQueryData(['messages', activeSessionId], (oldData) => {
      // Append to existing assistant message or create new one
    });
  }

  // Line 429: Handle ai_response_complete
  else if (message.event === 'ai_response_complete') {
    // Lines 443-452: Save final AI message to database
    if (activeSessionId && message.data.text) {
      api.addMessage(activeSessionId, {
        role: 'assistant',
        content: message.data.text,
      });
    }
  }
}, [activeSessionId, queryClient]);
```

**Key Insight**: The conversation history component (`VoxbridgePage.tsx`) listens ONLY to `/ws/events` for conversation updates. It does NOT listen to `/ws/voice` because that's a session-specific connection managed by `useWebRTCAudio` hook.

### 2. Discord Plugin WebSocket Events (`discord_plugin.py`)

**Discord broadcasts to BOTH channels**:

```python
# Lines 1268-1278: Partial transcript
from src.api import get_ws_manager
ws_manager = get_ws_manager()
await ws_manager.broadcast({
    "event": "partial_transcript",
    "data": {
        "userId": user_id,
        "username": username,
        "text": text,
        "timestamp": datetime.now().isoformat()
    }
})

# Lines 1303-1315: Final transcript
await ws_manager.broadcast({
    "event": "final_transcript",
    "data": {
        "userId": user_id,
        "username": username,
        "text": text,
        "timestamp": datetime.now().isoformat()
    }
})

# Lines 1739-1750: AI response chunk
await ws_manager.broadcast({
    "event": "ai_response_chunk",
    "data": {
        "userId": user_id,
        "username": username,
        "text": chunk,
        "timestamp": datetime.now().isoformat()
    }
})

# Lines 1961-1973: AI response complete
await ws_manager.broadcast({
    "event": "ai_response_complete",
    "data": {
        "userId": user_id,
        "username": username,
        "text": full_response,
        "timestamp": datetime.now().isoformat()
    }
})

# Lines 2132-2138: Metrics update
await ws_manager.broadcast({
    "event": "metrics_updated",
    "data": metrics_snapshot
})
```

**Discord sends 5 critical events**:
1. `partial_transcript` - Real-time transcription updates
2. `final_transcript` - Complete transcription
3. `ai_response_chunk` - Streaming AI response
4. `ai_response_complete` - AI response finished
5. `metrics_updated` - Performance metrics

**All broadcast via `ws_manager.broadcast()` → reaches `/ws/events` listeners**

### 3. WebRTC Handler Events (`webrtc_handler.py`)

**WebRTC sends to voice WebSocket ONLY**:

```python
# Lines 447-458: Partial transcript
async def _send_partial_transcript(self, text: str):
    await self.websocket.send_json({  # ❌ ONLY to /ws/voice
        "event": "partial_transcript",
        "data": {
            "text": text,
            "session_id": str(self.session_id)
        }
    })

# Lines 460-471: Final transcript
async def _send_final_transcript(self, text: str):
    await self.websocket.send_json({  # ❌ ONLY to /ws/voice
        "event": "final_transcript",
        "data": {
            "text": text,
            "session_id": str(self.session_id)
        }
    })

# Lines 473-484: AI response chunk
async def _send_ai_response_chunk(self, text: str):
    await self.websocket.send_json({  # ❌ ONLY to /ws/voice
        "event": "ai_response_chunk",
        "data": {
            "text": text,
            "session_id": str(self.session_id)
        }
    })

# Lines 486-497: AI response complete
async def _send_ai_response_complete(self, text: str):
    await self.websocket.send_json({  # ❌ ONLY to /ws/voice
        "event": "ai_response_complete",
        "data": {
            "text": text,
            "session_id": str(self.session_id)
        }
    })
```

**WebRTC sends to `self.websocket` (the voice session WebSocket)**

**WebRTC DOES NOT broadcast to `ws_manager`**

**Result**: `/ws/events` listeners never receive WebRTC events, so conversation history never updates.

---

## Event Format Comparison

### Discord Plugin Events

```json
{
  "event": "partial_transcript",
  "data": {
    "userId": "123456789",
    "username": "JohnDoe",
    "text": "Hello there",
    "timestamp": "2025-11-05T10:30:00.000Z"
  }
}
```

### WebRTC Handler Events (Current)

```json
{
  "event": "partial_transcript",
  "data": {
    "text": "Hello there",
    "session_id": "abc-123-def-456"
  }
}
```

**Key Differences**:
1. Discord includes `userId`, `username`, `timestamp`
2. WebRTC includes `session_id` but NOT `userId` or `username`
3. WebRTC missing `timestamp` field

**Frontend Compatibility**:
- `VoxbridgePage.tsx` expects `message.data.text` (both have ✅)
- Frontend does NOT require `userId` or `username` for conversation display
- Frontend uses `activeSessionId` for message routing, NOT event's `session_id`

**Conclusion**: Event format differences are minor and won't break functionality.

---

## Root Cause Summary

**WebRTC Handler Issues**:

1. **Missing Global Broadcast** ❌
   - WebRTC sends events ONLY to voice WebSocket (`self.websocket.send_json()`)
   - Does NOT broadcast to global WebSocket manager (`ws_manager.broadcast()`)
   - Frontend `/ws/events` listener never receives events
   - Conversation history never updates

2. **Database Saves Work** ✅
   - Lines 327-336: User message saved to database
   - Lines 427-437: AI message saved to database
   - API polling (`refetchInterval: 2000`) eventually picks up messages
   - BUT real-time updates missing

3. **Frontend Message Handler Ready** ✅
   - `handleMessage()` in `VoxbridgePage.tsx` handles both Discord and WebRTC events
   - Lines 152-280: `handleWebRTCAudioMessage()` processes voice session events
   - Lines 322-460: `handleMessage()` processes global event stream events
   - Both handlers ready, just missing events from WebRTC

---

## Fix Plan

### Phase 1: Add Global WebSocket Broadcasts to WebRTC Handler

**File**: `src/voice/webrtc_handler.py`

**Changes Required**:

1. **Import WebSocket Manager**:
   ```python
   # Add to imports (line 36)
   from src.api import get_ws_manager
   ```

2. **Store User ID for Events**:
   ```python
   # Line 64: Add user_id to class attributes
   self.user_id = user_id
   ```

3. **Broadcast Partial Transcript**:
   ```python
   # Lines 447-458: Update _send_partial_transcript()
   async def _send_partial_transcript(self, text: str):
       # Send to voice WebSocket (existing)
       await self.websocket.send_json({
           "event": "partial_transcript",
           "data": {
               "text": text,
               "session_id": str(self.session_id)
           }
       })

       # NEW: Broadcast to global event stream
       try:
           ws_manager = get_ws_manager()
           await ws_manager.broadcast({
               "event": "partial_transcript",
               "data": {
                   "userId": self.user_id,
                   "text": text,
                   "session_id": str(self.session_id),
                   "timestamp": datetime.now().isoformat()
               }
           })
       except Exception as e:
           logger.error(f"❌ Failed to broadcast partial transcript: {e}")
   ```

4. **Broadcast Final Transcript**:
   ```python
   # Lines 460-471: Update _send_final_transcript()
   async def _send_final_transcript(self, text: str):
       # Send to voice WebSocket (existing)
       await self.websocket.send_json({
           "event": "final_transcript",
           "data": {
               "text": text,
               "session_id": str(self.session_id)
           }
       })

       # NEW: Broadcast to global event stream
       try:
           ws_manager = get_ws_manager()
           await ws_manager.broadcast({
               "event": "final_transcript",
               "data": {
                   "userId": self.user_id,
                   "text": text,
                   "session_id": str(self.session_id),
                   "timestamp": datetime.now().isoformat()
               }
           })
       except Exception as e:
           logger.error(f"❌ Failed to broadcast final transcript: {e}")
   ```

5. **Broadcast AI Response Chunk**:
   ```python
   # Lines 473-484: Update _send_ai_response_chunk()
   async def _send_ai_response_chunk(self, text: str):
       # Send to voice WebSocket (existing)
       await self.websocket.send_json({
           "event": "ai_response_chunk",
           "data": {
               "text": text,
               "session_id": str(self.session_id)
           }
       })

       # NEW: Broadcast to global event stream
       try:
           ws_manager = get_ws_manager()
           await ws_manager.broadcast({
               "event": "ai_response_chunk",
               "data": {
                   "userId": self.user_id,
                   "text": text,
                   "session_id": str(self.session_id),
                   "timestamp": datetime.now().isoformat()
               }
           })
       except Exception as e:
           logger.error(f"❌ Failed to broadcast AI response chunk: {e}")
   ```

6. **Broadcast AI Response Complete**:
   ```python
   # Lines 486-497: Update _send_ai_response_complete()
   async def _send_ai_response_complete(self, text: str):
       # Send to voice WebSocket (existing)
       await self.websocket.send_json({
           "event": "ai_response_complete",
           "data": {
               "text": text,
               "session_id": str(self.session_id)
           }
       })

       # NEW: Broadcast to global event stream
       try:
           ws_manager = get_ws_manager()
           await ws_manager.broadcast({
               "event": "ai_response_complete",
               "data": {
                   "userId": self.user_id,
                   "text": text,
                   "session_id": str(self.session_id),
                   "timestamp": datetime.now().isoformat()
               }
           })
       except Exception as e:
           logger.error(f"❌ Failed to broadcast AI response complete: {e}")
   ```

7. **Broadcast Metrics Update** (After AI Response):
   ```python
   # Line 438: After saving AI message to database
   # Broadcast metrics update (matching Discord plugin behavior)
   try:
       ws_manager = get_ws_manager()
       metrics_snapshot = self.metrics.get_metrics()
       await ws_manager.broadcast({
           "event": "metrics_updated",
           "data": metrics_snapshot
       })
   except Exception as e:
       logger.error(f"❌ Failed to broadcast metrics: {e}")
   ```

### Phase 2: Frontend Verification (No Changes Needed)

**File**: `frontend/src/pages/VoxbridgePage.tsx`

**Existing Code Works**:
- Lines 462-465: Already listening to `/ws/events`
- Lines 322-460: `handleMessage()` already handles all events
- Lines 359-393: Processes `partial_transcript` and `final_transcript`
- Lines 394-428: Processes `ai_response_chunk`
- Lines 429-452: Processes `ai_response_complete`

**No changes needed** - frontend is ready to receive WebRTC events once broadcasts are added.

### Phase 3: Testing Checklist

**Test Scenario**: WebRTC voice chat conversation

1. ✅ **Partial Transcript Display**:
   - Speak into browser microphone
   - Verify `STTWaitingIndicator` shows live transcription
   - Check browser console for `/ws/events` message: `{event: "partial_transcript"}`

2. ✅ **Final Transcript in Conversation History**:
   - Stop speaking (silence detection)
   - Verify blue user message bubble appears in conversation history
   - Check message content matches what was spoken

3. ✅ **AI Response Streaming**:
   - Verify `StreamingMessageDisplay` shows AI response chunks in real-time
   - Check browser console for `/ws/events` messages: `{event: "ai_response_chunk"}`

4. ✅ **AI Response in Conversation History**:
   - Wait for AI response to complete
   - Verify purple assistant message bubble appears in conversation history
   - Check message content matches streamed response

5. ✅ **Metrics Update**:
   - Verify `StatusSummary` metrics update after conversation turn
   - Check browser console for `/ws/events` message: `{event: "metrics_updated"}`

6. ✅ **Multiple Conversation Turns**:
   - Have a multi-turn conversation
   - Verify all messages appear in chronological order
   - Verify no duplicates (messages saved once via database, displayed once)

---

## Code Snippets

### Before (WebRTC - Not Working)

```python
# src/voice/webrtc_handler.py (Line 447)
async def _send_partial_transcript(self, text: str):
    """Send partial transcript event to browser"""
    try:
        await self.websocket.send_json({  # ❌ ONLY to voice WebSocket
            "event": "partial_transcript",
            "data": {
                "text": text,
                "session_id": str(self.session_id)
            }
        })
    except Exception as e:
        logger.error(f"❌ Error sending partial transcript: {e}")
```

### After (WebRTC - Fixed)

```python
# src/voice/webrtc_handler.py (Line 447)
async def _send_partial_transcript(self, text: str):
    """Send partial transcript event to browser and broadcast to all clients"""
    try:
        # Send to voice WebSocket (existing behavior)
        await self.websocket.send_json({
            "event": "partial_transcript",
            "data": {
                "text": text,
                "session_id": str(self.session_id)
            }
        })

        # NEW: Broadcast to global event stream (matches Discord behavior)
        try:
            from src.api import get_ws_manager
            ws_manager = get_ws_manager()
            await ws_manager.broadcast({
                "event": "partial_transcript",
                "data": {
                    "userId": self.user_id,
                    "text": text,
                    "session_id": str(self.session_id),
                    "timestamp": datetime.now().isoformat()
                }
            })
        except Exception as broadcast_error:
            logger.error(f"❌ Failed to broadcast partial transcript: {broadcast_error}")

    except Exception as e:
        logger.error(f"❌ Error sending partial transcript: {e}")
```

### Reference (Discord - Working)

```python
# src/plugins/discord_plugin.py (Line 1268)
from src.api import get_ws_manager
ws_manager = get_ws_manager()
logger.debug(f"📡 WebSocket: Broadcasting partial transcript to frontend")
await ws_manager.broadcast({
    "event": "partial_transcript",
    "data": {
        "userId": user_id,
        "username": username,
        "text": text,
        "timestamp": datetime.now().isoformat()
    }
})
```

---

## Expected Behavior After Fix

### WebRTC Voice Chat Flow (Post-Fix)

```
User speaks in browser
    ↓
WebRTC audio → /ws/voice → webrtc_handler.py
    ↓
Opus decode → STTService → Transcription
    ↓
webrtc_handler._send_partial_transcript(text):
  1. websocket.send_json() → /ws/voice connection (real-time voice session)
  2. ws_manager.broadcast() → /ws/events (global event stream) ✅ NEW
    ↓
Frontend receives event on BOTH channels:
  - useWebRTCAudio receives on /ws/voice → updates STTWaitingIndicator
  - VoxbridgePage receives on /ws/events → updates conversation history ✅ NEW
    ↓
Silence detected → Final transcript
    ↓
webrtc_handler._send_final_transcript(text):
  1. websocket.send_json() → /ws/voice connection
  2. ws_manager.broadcast() → /ws/events ✅ NEW
    ↓
Frontend VoxbridgePage.handleMessage():
  - Saves user message to database via API
  - Invalidates query cache
  - Message appears in conversation history ✅ WORKING
    ↓
LLM generates response with streaming
    ↓
webrtc_handler._send_ai_response_chunk(chunk):
  1. websocket.send_json() → /ws/voice connection
  2. ws_manager.broadcast() → /ws/events ✅ NEW
    ↓
Frontend receives chunk on BOTH channels:
  - useWebRTCAudio receives on /ws/voice → buffers TTS audio
  - VoxbridgePage receives on /ws/events → updates conversation with streaming text ✅ NEW
    ↓
AI response completes
    ↓
webrtc_handler._send_ai_response_complete(full_response):
  1. websocket.send_json() → /ws/voice connection
  2. ws_manager.broadcast() → /ws/events ✅ NEW
    ↓
Frontend VoxbridgePage.handleMessage():
  - Saves AI message to database via API
  - Invalidates query cache
  - Message appears in conversation history ✅ WORKING
  - Plays TTS audio
    ↓
✅ Complete conversation visible in history
✅ Identical behavior to Discord plugin
```

---

## Implementation Priority

1. **HIGH PRIORITY**: Add `ws_manager.broadcast()` calls to all 4 event methods
   - `_send_partial_transcript()`
   - `_send_final_transcript()`
   - `_send_ai_response_chunk()`
   - `_send_ai_response_complete()`

2. **MEDIUM PRIORITY**: Add metrics broadcast after AI response (line 438)
   - Ensures metrics update in real-time (matches Discord behavior)

3. **LOW PRIORITY**: Add `timestamp` field to all events
   - Consistency with Discord events
   - Useful for debugging

---

## Expected Results

**After implementing the fix**:
1. ✅ WebRTC conversation history populates in real-time
2. ✅ User messages appear after transcription
3. ✅ AI responses stream character-by-character
4. ✅ Metrics update after each conversation turn
5. ✅ Identical UX to Discord plugin conversation
6. ✅ No duplicates (database save + real-time display work together)

**Estimated Time**: 30 minutes (straightforward refactor)

**Risk Level**: LOW (additive change, no breaking modifications)

**Testing Required**: Full conversation flow (speak → transcribe → AI response → display)

---

## Conclusion

The WebRTC conversation history issue is caused by a **missing broadcast layer**. WebRTC handler sends events only to the voice WebSocket connection (`/ws/voice`), but the conversation history UI listens to the global event stream (`/ws/events`).

**Fix**: Add `ws_manager.broadcast()` calls to all event methods in `webrtc_handler.py`, matching the Discord plugin's proven pattern.

**Impact**: Enables real-time conversation history updates for WebRTC voice chat, bringing it to feature parity with Discord plugin.

**Next Steps**: Implement Phase 1 changes and verify with Phase 3 testing checklist.
