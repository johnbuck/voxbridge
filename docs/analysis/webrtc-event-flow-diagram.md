# WebRTC Event Flow Diagram

Visual representation of WebSocket event flow for Discord vs WebRTC.

---

## Current Architecture (WebRTC NOT WORKING)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Browser)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │            VoxbridgePage Component (Lines 1-1337)         │    │
│  ├───────────────────────────────────────────────────────────┤    │
│  │                                                            │    │
│  │  Conversation History (Lines 1190-1310)                   │    │
│  │  ├─ Displays messages from database query                 │    │
│  │  ├─ Shows streaming chunks                                │    │
│  │  └─ Updates via handleMessage() callback                  │    │
│  │                                                            │    │
│  │  ┌──────────────────────────────────────────────┐         │    │
│  │  │  useWebSocket('/ws/events') (Lines 462-465)  │         │    │
│  │  │  onMessage: handleMessage()                  │         │    │
│  │  └────────────────┬─────────────────────────────┘         │    │
│  │                   │                                        │    │
│  │                   │ Listens for:                           │    │
│  │                   │ • partial_transcript                   │    │
│  │                   │ • final_transcript                     │    │
│  │                   │ • ai_response_chunk                    │    │
│  │                   │ • ai_response_complete                 │    │
│  │                   │ • metrics_updated                      │    │
│  │                   │                                        │    │
│  └───────────────────┼────────────────────────────────────────┘    │
│                      │                                             │
│  ┌───────────────────┼────────────────────────────────────────┐    │
│  │ useWebRTCAudio Hook (Lines 304-318)                       │    │
│  │                   │                                        │    │
│  │  ┌────────────────▼──────────────────────────┐            │    │
│  │  │  Separate WebSocket: /ws/voice            │            │    │
│  │  │  onMessage: handleWebRTCAudioMessage()    │            │    │
│  │  └────────────────┬──────────────────────────┘            │    │
│  │                   │                                        │    │
│  │                   │ Listens for:                           │    │
│  │                   │ • partial_transcript                   │    │
│  │                   │ • final_transcript                     │    │
│  │                   │ • ai_response_chunk                    │    │
│  │                   │ • ai_response_complete                 │    │
│  │                   │ • tts_start / tts_complete             │    │
│  │                   │ • Binary audio chunks                  │    │
│  │                   │                                        │    │
│  └───────────────────┼────────────────────────────────────────┘    │
│                      │                                             │
│                      │ Sends: Binary Opus audio                   │
│                      │                                             │
└──────────────────────┼─────────────────────────────────────────────┘
                       │
                       │
┌──────────────────────┼─────────────────────────────────────────────┐
│                      │         BACKEND (FastAPI)                   │
├──────────────────────┼─────────────────────────────────────────────┤
│                      │                                             │
│  ┌───────────────────▼────────────────────────────┐                │
│  │  /ws/voice WebSocket Handler                  │                │
│  │  (server.py Lines 1104-1159)                  │                │
│  │                                                │                │
│  │  ┌──────────────────────────────────────────┐ │                │
│  │  │  WebRTCVoiceHandler                      │ │                │
│  │  │  (webrtc_handler.py)                     │ │                │
│  │  │                                          │ │                │
│  │  │  Events sent via:                        │ │                │
│  │  │  self.websocket.send_json({})            │ │                │
│  │  │                                          │ │                │
│  │  │  • _send_partial_transcript() (L447)    │ │                │
│  │  │  • _send_final_transcript() (L460)      │ │                │
│  │  │  • _send_ai_response_chunk() (L473)     │ │                │
│  │  │  • _send_ai_response_complete() (L486)  │ │                │
│  │  │                                          │ │                │
│  │  │  ❌ NO ws_manager.broadcast() calls     │ │                │
│  │  └──────────────────────────────────────────┘ │                │
│  └────────────────────────────────────────────────┘                │
│                      ▲                                             │
│                      │                                             │
│                      │ Events go ONLY to /ws/voice connection     │
│                      │ (NOT to global event stream)                │
│                      │                                             │
│  ┌───────────────────┴────────────────────────────┐                │
│  │  /ws/events WebSocket Manager                 │                │
│  │  (server.py Lines 1010-1103)                  │                │
│  │                                                │                │
│  │  ConnectionManager.broadcast():               │                │
│  │  ├─ Sends to ALL connected /ws/events clients │                │
│  │  └─ Used by Discord plugin ✅                 │                │
│  │                                                │                │
│  │  ❌ WebRTC does NOT call broadcast()          │                │
│  │                                                │                │
│  └────────────────────────────────────────────────┘                │
│                      ▲                                             │
│                      │                                             │
│                      │ Discord broadcasts all events here ✅       │
│                      │                                             │
│  ┌───────────────────┴────────────────────────────┐                │
│  │  Discord Plugin                                │                │
│  │  (discord_plugin.py)                           │                │
│  │                                                │                │
│  │  Events sent via:                              │                │
│  │  ws_manager.broadcast({})                      │                │
│  │                                                │                │
│  │  • partial_transcript (L1271) ✅               │                │
│  │  • final_transcript (L1306) ✅                 │                │
│  │  • ai_response_chunk (L1742) ✅                │                │
│  │  • ai_response_complete (L1964) ✅             │                │
│  │  • metrics_updated (L2135) ✅                  │                │
│  │                                                │                │
│  └────────────────────────────────────────────────┘                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

**Result**:
❌ WebRTC events NEVER reach /ws/events listeners
❌ VoxbridgePage.handleMessage() NEVER called for WebRTC
❌ Conversation history NEVER updates
```

---

## Fixed Architecture (WebRTC WORKING)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Browser)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │            VoxbridgePage Component (Lines 1-1337)         │    │
│  ├───────────────────────────────────────────────────────────┤    │
│  │                                                            │    │
│  │  Conversation History (Lines 1190-1310)                   │    │
│  │  ├─ Displays messages from database query                 │    │
│  │  ├─ Shows streaming chunks                                │    │
│  │  └─ Updates via handleMessage() callback                  │    │
│  │                                                            │    │
│  │  ┌──────────────────────────────────────────────┐         │    │
│  │  │  useWebSocket('/ws/events') (Lines 462-465)  │         │    │
│  │  │  onMessage: handleMessage()                  │         │    │
│  │  └────────────────┬─────────────────────────────┘         │    │
│  │                   │                                        │    │
│  │                   │ Receives:                              │    │
│  │                   │ • partial_transcript ✅ NOW WORKING    │    │
│  │                   │ • final_transcript ✅ NOW WORKING      │    │
│  │                   │ • ai_response_chunk ✅ NOW WORKING     │    │
│  │                   │ • ai_response_complete ✅ NOW WORKING  │    │
│  │                   │ • metrics_updated ✅ NOW WORKING       │    │
│  │                   │                                        │    │
│  └───────────────────┼────────────────────────────────────────┘    │
│                      │                                             │
│  ┌───────────────────┼────────────────────────────────────────┐    │
│  │ useWebRTCAudio Hook (Lines 304-318)                       │    │
│  │                   │                                        │    │
│  │  ┌────────────────▼──────────────────────────┐            │    │
│  │  │  Separate WebSocket: /ws/voice            │            │    │
│  │  │  onMessage: handleWebRTCAudioMessage()    │            │    │
│  │  └────────────────┬──────────────────────────┘            │    │
│  │                   │                                        │    │
│  │                   │ Receives (ALSO):                       │    │
│  │                   │ • partial_transcript                   │    │
│  │                   │ • final_transcript                     │    │
│  │                   │ • ai_response_chunk                    │    │
│  │                   │ • ai_response_complete                 │    │
│  │                   │ • tts_start / tts_complete             │    │
│  │                   │ • Binary audio chunks                  │    │
│  │                   │                                        │    │
│  └───────────────────┼────────────────────────────────────────┘    │
│                      │                                             │
│                      │ Sends: Binary Opus audio                   │
│                      │                                             │
└──────────────────────┼─────────────────────────────────────────────┘
                       │
                       │
┌──────────────────────┼─────────────────────────────────────────────┐
│                      │         BACKEND (FastAPI)                   │
├──────────────────────┼─────────────────────────────────────────────┤
│                      │                                             │
│  ┌───────────────────▼────────────────────────────┐                │
│  │  /ws/voice WebSocket Handler                  │                │
│  │  (server.py Lines 1104-1159)                  │                │
│  │                                                │                │
│  │  ┌──────────────────────────────────────────┐ │                │
│  │  │  WebRTCVoiceHandler                      │ │                │
│  │  │  (webrtc_handler.py)                     │ │                │
│  │  │                                          │ │                │
│  │  │  Events sent via DUAL PATH:             │ │                │
│  │  │                                          │ │                │
│  │  │  1️⃣ self.websocket.send_json({})        │ │                │
│  │  │     (to voice session client)           │ │                │
│  │  │                                          │ │                │
│  │  │  2️⃣ ws_manager.broadcast({}) ✅ NEW     │ │                │
│  │  │     (to all /ws/events clients)         │ │                │
│  │  │                                          │ │                │
│  │  │  Methods:                                │ │                │
│  │  │  • _send_partial_transcript() (L447)    │ │                │
│  │  │  • _send_final_transcript() (L460)      │ │                │
│  │  │  • _send_ai_response_chunk() (L473)     │ │                │
│  │  │  • _send_ai_response_complete() (L486)  │ │                │
│  │  │                                          │ │                │
│  │  └─────────────────┬────────────────────────┘ │                │
│  └────────────────────┼──────────────────────────┘                │
│                       │                                            │
│                       │ Broadcasts to:                             │
│                       │                                            │
│  ┌────────────────────▼───────────────────────────┐                │
│  │  /ws/events WebSocket Manager                 │                │
│  │  (server.py Lines 1010-1103)                  │                │
│  │                                                │                │
│  │  ConnectionManager.broadcast():               │                │
│  │  ├─ Sends to ALL connected /ws/events clients │                │
│  │  ├─ Used by Discord plugin ✅                 │                │
│  │  └─ NOW used by WebRTC handler ✅ NEW         │                │
│  │                                                │                │
│  │  ✅ WebRTC NOW calls broadcast() on all events│                │
│  │                                                │                │
│  └────────────────────────────────────────────────┘                │
│                      ▲                                             │
│                      │                                             │
│                      │ Both Discord AND WebRTC broadcast here ✅  │
│                      │                                             │
│  ┌───────────────────┴────────────────────────────┐                │
│  │  Discord Plugin                                │                │
│  │  (discord_plugin.py)                           │                │
│  │                                                │                │
│  │  Events sent via:                              │                │
│  │  ws_manager.broadcast({})                      │                │
│  │                                                │                │
│  │  • partial_transcript (L1271) ✅               │                │
│  │  • final_transcript (L1306) ✅                 │                │
│  │  • ai_response_chunk (L1742) ✅                │                │
│  │  • ai_response_complete (L1964) ✅             │                │
│  │  • metrics_updated (L2135) ✅                  │                │
│  │                                                │                │
│  └────────────────────────────────────────────────┘                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

**Result**:
✅ WebRTC events REACH /ws/events listeners
✅ VoxbridgePage.handleMessage() CALLED for WebRTC
✅ Conversation history UPDATES in real-time
✅ Identical behavior to Discord plugin
```

---

## Event Flow Timeline (WebRTC Fixed)

```
TIME    EVENT                           WEBRTC HANDLER                     FRONTEND
═══════════════════════════════════════════════════════════════════════════════════

T+0s    User speaks in browser
        ↓
        Binary Opus audio sent          ← useWebRTCAudio.sendAudioChunk()

T+0.1s  Audio decoded & transcribed
        ↓
        Partial transcript ready        → _send_partial_transcript(text)
                                           ├─ 1️⃣ self.websocket.send_json()
                                           │     ↓
                                           │     useWebRTCAudio receives
                                           │     ↓
                                           │     STTWaitingIndicator updates
                                           │
                                           └─ 2️⃣ ws_manager.broadcast() ✅ NEW
                                                 ↓
                                                 VoxbridgePage.handleMessage()
                                                 ↓
                                                 setVoicePartialTranscript(text)
                                                 ↓
                                                 Real-time transcript display ✅

T+2.0s  User stops speaking
        ↓
        Silence detected (600ms)
        ↓
        Final transcript ready          → _send_final_transcript(text)
                                           ├─ 1️⃣ self.websocket.send_json()
                                           │     ↓
                                           │     useWebRTCAudio receives
                                           │     ↓
                                           │     Clears partial transcript
                                           │
                                           └─ 2️⃣ ws_manager.broadcast() ✅ NEW
                                                 ↓
                                                 VoxbridgePage.handleMessage()
                                                 ↓
                                                 api.addMessage(user, text)
                                                 ↓
                                                 queryClient.invalidateQueries()
                                                 ↓
                                                 Blue user bubble appears ✅

T+2.5s  LLM generates first chunk
        ↓
        AI response chunk ready         → _send_ai_response_chunk(chunk)
                                           ├─ 1️⃣ self.websocket.send_json()
                                           │     ↓
                                           │     useWebRTCAudio receives
                                           │     ↓
                                           │     Buffers for TTS
                                           │
                                           └─ 2️⃣ ws_manager.broadcast() ✅ NEW
                                                 ↓
                                                 VoxbridgePage.handleMessage()
                                                 ↓
                                                 queryClient.setQueryData()
                                                 ↓
                                                 StreamingMessageDisplay shows chunk ✅

T+3.0s  More chunks arrive              (Repeat for each chunk)
        ↓                                   ↓
        Streaming continues...              Purple bubble updates in real-time ✅

T+5.0s  LLM finishes
        ↓
        AI response complete            → _send_ai_response_complete(text)
                                           ├─ 1️⃣ self.websocket.send_json()
                                           │     ↓
                                           │     useWebRTCAudio receives
                                           │     ↓
                                           │     Plays TTS audio
                                           │
                                           └─ 2️⃣ ws_manager.broadcast() ✅ NEW
                                                 ↓
                                                 VoxbridgePage.handleMessage()
                                                 ↓
                                                 api.addMessage(assistant, text)
                                                 ↓
                                                 queryClient.invalidateQueries()
                                                 ↓
                                                 Final purple bubble in history ✅

T+5.1s  Metrics updated                 → ws_manager.broadcast() ✅ NEW
                                                 ↓
                                                 VoxbridgePage.handleMessage()
                                                 ↓
                                                 StatusSummary updates metrics ✅

═══════════════════════════════════════════════════════════════════════════════════
RESULT: Full conversation visible in real-time, identical to Discord behavior ✅
```

---

## Key Architectural Insight

**VoxBridge uses DUAL WebSocket channels**:

1. **Session-Specific** (`/ws/voice`):
   - One connection per active voice session
   - Handles bidirectional audio + transcription events
   - Used by `useWebRTCAudio` hook
   - Dies when user closes voice chat

2. **Global Event Stream** (`/ws/events`):
   - Persistent connection for all frontend instances
   - Receives ALL conversation events (Discord + WebRTC)
   - Used by `VoxbridgePage` for conversation history
   - Stays alive across page navigation

**The Fix**: WebRTC must broadcast to BOTH channels (just like Discord does)

**Why This Works**:
- Voice session events (TTS, audio chunks) stay session-specific
- Conversation events (transcripts, AI responses) reach global listeners
- Frontend receives duplicate events (both channels) but handles gracefully
- No conflicts because handlers have different responsibilities

**Design Pattern**: Pub/Sub with dual subscriptions
- WebRTC publishes to `/ws/voice` (direct send) + `/ws/events` (broadcast)
- Frontend subscribes to both channels with separate handlers
- Each handler processes events relevant to its scope
