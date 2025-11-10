# WebRTC Audio Capture - Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Browser (React Frontend)                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────┐     │
│  │                    VoiceChatPage.tsx                          │     │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────┐ │     │
│  │  │ Conversation    │  │ AudioControls    │  │ Permission   │ │     │
│  │  │ List            │  │ Component        │  │ Error Banner │ │     │
│  │  └─────────────────┘  └──────────────────┘  └──────────────┘ │     │
│  │                                                               │     │
│  │  ┌────────────────────────────────────────────────────────┐  │     │
│  │  │         Message List with Streaming Support            │  │     │
│  │  │  • User messages (blue)                                │  │     │
│  │  │  • Assistant messages (purple)                         │  │     │
│  │  │  • Partial transcript (faded, live updates)            │  │     │
│  │  └────────────────────────────────────────────────────────┘  │     │
│  └───────────────────────────────────────────────────────────────┘     │
│                              ↕                                          │
│  ┌───────────────────────────────────────────────────────────────┐     │
│  │                 useWebRTCAudio Hook                           │     │
│  │  • getUserMedia() - Microphone access                         │     │
│  │  • MediaRecorder - Opus encoding                             │     │
│  │  • WebSocket - Binary audio streaming                        │     │
│  │  • Auto-reconnect logic                                      │     │
│  │  • Error handling                                            │     │
│  └───────────────────────────────────────────────────────────────┘     │
│                              ↕                                          │
│  ┌───────────────────────────────────────────────────────────────┐     │
│  │                   WebSocket Client                            │     │
│  │  ws://localhost:4900/ws/voice                                │     │
│  │  • Send: Audio chunks (binary, 100ms intervals)              │     │
│  │  • Receive: JSON events (transcripts, AI responses)          │     │
│  └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                              ↕ WebSocket (Binary + JSON)
┌─────────────────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI + WebSocket)                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────┐     │
│  │            WebSocket Handler: /ws/voice                       │     │
│  │  • Accept connection                                          │     │
│  │  • Receive audio chunks (binary)                              │     │
│  │  • Send JSON events (partial/final transcripts, AI responses) │     │
│  └───────────────────────────────────────────────────────────────┘     │
│                              ↕                                          │
│  ┌───────────────────────────────────────────────────────────────┐     │
│  │                 Audio Processing Pipeline                     │     │
│  │                                                               │     │
│  │  1. Decode Opus/WebM audio                                    │     │
│  │     ↓                                                         │     │
│  │  2. Buffer audio chunks                                       │     │
│  │     ↓                                                         │     │
│  │  3. Send to WhisperX (streaming)                              │     │
│  │     ↓                                                         │     │
│  │  4. Receive partial transcripts → Send to client              │     │
│  │     ↓                                                         │     │
│  │  5. Detect silence → Send final transcript                    │     │
│  │     ↓                                                         │     │
│  │  6. Call LLM (OpenRouter/Local/n8n)                           │     │
│  │     ↓                                                         │     │
│  │  7. Stream AI response chunks → Send to client                │     │
│  │     ↓                                                         │     │
│  │  8. Send completion event                                     │     │
│  │     ↓                                                         │     │
│  │  9. Save messages to PostgreSQL                               │     │
│  │                                                               │     │
│  └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                              ↕ WebSocket (Binary)
┌─────────────────────────────────────────────────────────────────────────┐
│                       WhisperX Server (GPU)                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  • Receive audio stream                                                │
│  • Transcribe with WhisperX model                                      │
│  • Return partial transcripts (real-time)                              │
│  • Detect silence → Return final transcript                            │
│  • GPU-accelerated (RTX 5060 Ti)                                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

```
User speaks → Microphone
                ↓
         getUserMedia()
                ↓
         MediaRecorder (Opus)
                ↓
    100ms audio chunks (binary)
                ↓
    WebSocket.send(ArrayBuffer)
                ↓
    Backend receives audio chunk
                ↓
         Decode Opus audio
                ↓
    Forward to WhisperX server
                ↓
         ┌──────────────┐
         │  WhisperX    │
         │  Processing  │
         └──────────────┘
         ↓              ↓
   Partial          Silence
   Transcript       Detected
         ↓              ↓
    Send via WS    Final Transcript
         ↓              ↓
    Update UI      Save to DB
    (live text)         ↓
                   Call LLM
                        ↓
                   Stream chunks
                        ↓
                   Send via WS
                        ↓
                   Update UI
                   (word-by-word)
                        ↓
                   Completion event
                        ↓
                   Save to DB
                        ↓
                   TTS (optional)
```

## Component Hierarchy

```
VoiceChatPage
├── ConversationList
│   ├── Conversation items
│   └── New conversation button
│
├── Header
│   ├── Sidebar toggle
│   ├── Session info (title, agent)
│   └── AudioControls
│       ├── Connection badge
│       └── Microphone button
│
├── Conversation View (ScrollArea)
│   ├── Message bubbles
│   │   ├── User messages (left)
│   │   └── Assistant messages (right)
│   └── Partial transcript (faded, live)
│
└── Permission Error Banner (conditional)

Hooks Used:
├── useWebRTCAudio (custom)
├── useQuery (messages, sessions, agents)
├── useQueryClient (cache mutations)
└── useToastHelpers (error notifications)
```

## WebSocket Message Flow

```
Client                          Server
  │                               │
  │  Connect ws://host/ws/voice   │
  ├──────────────────────────────>│
  │                               │
  │  { event: "session_init",     │
  │    session_id: "..." }        │
  ├──────────────────────────────>│
  │                               │
  │  Audio chunk (binary)         │
  ├──────────────────────────────>│
  │  Audio chunk (binary)         │
  ├──────────────────────────────>│
  │  Audio chunk (binary)         │
  ├──────────────────────────────>│
  │                               │
  │  { event: "partial_transcript"│
  │    data: { text: "Hello..." }}│
  │<────────────────────────────┤
  │                               │
  │  Audio chunk (binary)         │
  ├──────────────────────────────>│
  │  Audio chunk (binary)         │
  ├──────────────────────────────>│
  │                               │
  │  { event: "partial_transcript"│
  │    data: { text: "Hello, I.." │
  │<────────────────────────────┤
  │                               │
  │  [User stops speaking]        │
  │                               │
  │  { event: "final_transcript"  │
  │    data: { text: "Hello, I am"│
  │           "testing..." }}     │
  │<────────────────────────────┤
  │                               │
  │  [LLM processing...]          │
  │                               │
  │  { event: "ai_response_chunk" │
  │    data: { text: "Hi " }}     │
  │<────────────────────────────┤
  │                               │
  │  { event: "ai_response_chunk" │
  │    data: { text: "there! " }} │
  │<────────────────────────────┤
  │                               │
  │  { event: "ai_response_chunk" │
  │    data: { text: "I heard.." }}│
  │<────────────────────────────┤
  │                               │
  │  { event: "ai_response_complete"│
  │    data: { text: "Full text.."}}│
  │<────────────────────────────┤
  │                               │
```

## State Management

```
VoiceChatPage State:
├── sidebarOpen: boolean
├── activeSessionId: string | null
├── newConversationDialogOpen: boolean
├── isSpeakerMuted: boolean
└── partialTranscript: string

useWebRTCAudio State:
├── isMuted: boolean
├── connectionState: 'connecting' | 'connected' | 'disconnected' | 'error'
├── permissionError: string | null
└── isRecording: boolean

React Query Cache:
├── sessions: Session[]
├── agents: Agent[]
└── messages: Message[]
```

## Audio Processing Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    Audio Capture (Browser)                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Microphone                                                 │
│      ↓                                                      │
│  getUserMedia({ audio: {                                   │
│    channelCount: 1,        // Mono                         │
│    sampleRate: 16000,      // 16kHz                        │
│    echoCancellation: true,                                 │
│    noiseSuppression: true,                                 │
│    autoGainControl: true                                   │
│  }})                                                        │
│      ↓                                                      │
│  MediaStream                                                │
│      ↓                                                      │
│  MediaRecorder({                                            │
│    mimeType: 'audio/webm;codecs=opus'  // Preferred        │
│  })                                                         │
│      ↓                                                      │
│  ondataavailable (every 100ms)                              │
│      ↓                                                      │
│  Blob → ArrayBuffer                                         │
│      ↓                                                      │
│  WebSocket.send(ArrayBuffer)                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│              Audio Processing (Backend)                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Receive ArrayBuffer                                        │
│      ↓                                                      │
│  Decode Opus/WebM                                           │
│      ↓                                                      │
│  Resample to 16kHz mono (if needed)                         │
│      ↓                                                      │
│  Accumulate chunks                                          │
│      ↓                                                      │
│  Forward to WhisperX                                        │
│      ↓                                                      │
│  Receive transcription                                      │
│      ↓                                                      │
│  Detect silence (VAD)                                       │
│      ↓                                                      │
│  Send partial or final transcript                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Error Handling Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Error Scenarios                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Microphone Permission Denied (NotAllowedError)             │
│      ↓                                                      │
│  setPermissionError("Microphone access denied...")          │
│      ↓                                                      │
│  toast.error("Audio Error", permissionError)                │
│      ↓                                                      │
│  Display error banner in UI                                 │
│                                                             │
│  ─────────────────────────────────────────────              │
│                                                             │
│  No Microphone Found (NotFoundError)                        │
│      ↓                                                      │
│  setPermissionError("No microphone found...")               │
│      ↓                                                      │
│  toast.error("Audio Error", permissionError)                │
│                                                             │
│  ─────────────────────────────────────────────              │
│                                                             │
│  WebSocket Disconnected                                     │
│      ↓                                                      │
│  setConnectionState('disconnected')                         │
│      ↓                                                      │
│  Clear audio buffer                                         │
│      ↓                                                      │
│  Attempt reconnect (max 5 times, 3s interval)               │
│      ↓                                                      │
│  If successful: setConnectionState('connected')             │
│  If failed: setConnectionState('error')                     │
│                                                             │
│  ─────────────────────────────────────────────              │
│                                                             │
│  MediaRecorder Error                                        │
│      ↓                                                      │
│  Stop recording                                             │
│      ↓                                                      │
│  setPermissionError("Audio recording error")                │
│      ↓                                                      │
│  toast.error("Audio Error", error)                          │
│      ↓                                                      │
│  Clean up resources                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Lifecycle Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                Component Lifecycle                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  VoiceChatPage Mount                                        │
│      ↓                                                      │
│  Load sessions, agents (React Query)                        │
│      ↓                                                      │
│  Auto-select first session                                  │
│      ↓                                                      │
│  useWebRTCAudio initializes                                 │
│  (autoStart: false - waits for user)                        │
│      ↓                                                      │
│  User clicks microphone button                              │
│      ↓                                                      │
│  Call getUserMedia()                                        │
│      ↓                                                      │
│  ┌───────────────────┐                                     │
│  │ Permission granted │                                     │
│  └───────────────────┘                                     │
│      ↓                                                      │
│  Start MediaRecorder                                        │
│      ↓                                                      │
│  Connect WebSocket                                          │
│      ↓                                                      │
│  setIsMuted(false)                                          │
│  setIsRecording(true)                                       │
│  setConnectionState('connected')                            │
│      ↓                                                      │
│  User speaks                                                │
│      ↓                                                      │
│  Audio chunks → WebSocket (every 100ms)                     │
│      ↓                                                      │
│  Receive partial transcripts → Update UI                    │
│      ↓                                                      │
│  Receive final transcript → Save to DB                      │
│      ↓                                                      │
│  Receive AI response chunks → Stream to UI                  │
│      ↓                                                      │
│  Receive completion → Save to DB                            │
│      ↓                                                      │
│  User clicks microphone button again                        │
│      ↓                                                      │
│  Stop MediaRecorder                                         │
│      ↓                                                      │
│  Disconnect WebSocket                                       │
│      ↓                                                      │
│  setIsMuted(true)                                           │
│  setIsRecording(false)                                      │
│  setConnectionState('disconnected')                         │
│      ↓                                                      │
│  Component Unmount                                          │
│      ↓                                                      │
│  Cleanup: Stop all tracks, close WebSocket, clear timers    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Technology Stack

```
Frontend:
├── React 19 (UI library)
├── TypeScript (type safety)
├── Vite (build tool)
├── TanStack Query (data fetching)
├── Lucide React (icons)
├── Tailwind CSS (styling)
└── shadcn/ui (component library)

Browser APIs:
├── getUserMedia() (microphone access)
├── MediaRecorder (audio encoding)
├── WebSocket (binary streaming)
└── Web Audio API (future: waveform)

Backend (To Be Implemented):
├── FastAPI (Python web framework)
├── WebSocket (binary + JSON)
├── WhisperX (speech-to-text)
├── LLM Provider (OpenRouter/Local/n8n)
├── PostgreSQL (message storage)
└── SQLAlchemy (ORM)
```

## File Structure

```
frontend/
├── src/
│   ├── hooks/
│   │   ├── useWebRTCAudio.ts        ← Core audio capture logic
│   │   └── useWebSocket.ts          ← Generic WebSocket hook
│   │
│   ├── components/
│   │   ├── AudioControls.tsx        ← Mic button + status badge
│   │   ├── ConversationList.tsx     ← Session sidebar
│   │   └── ui/
│   │       ├── button.tsx
│   │       ├── badge.tsx
│   │       ├── toast.tsx
│   │       └── ...
│   │
│   ├── pages/
│   │   └── VoiceChatPage.tsx        ← Main voice chat UI
│   │
│   ├── services/
│   │   └── api.ts                   ← API client (sessions, messages)
│   │
│   └── types/
│       └── webrtc.ts                ← TypeScript types
│
├── docs/
│   ├── WEBRTC_TESTING.md            ← Testing guide
│   └── WEBRTC_ARCHITECTURE.md       ← This file
│
├── WEBRTC_README.md                 ← Complete overview
├── WEBRTC_INTEGRATION.md            ← Integration guide
├── WEBRTC_SUMMARY.md                ← Quick summary
└── mock-voice-server.js             ← Mock WebSocket server
```

---

**Visual Reference**: This architecture diagram provides a complete overview of the WebRTC audio capture implementation for VoxBridge 2.0 Phase 4 Web Voice Interface.
