# VoxBridge n8n Webhook & Session Analysis Report

**Analysis Date:** October 21, 2025  
**Codebase:** VoxBridge Discord Voice Bot  
**Scope:** n8n webhook integration, user session management, state storage  
**Purpose:** Multi-agent support planning and architecture review

---

## Executive Summary

VoxBridge currently implements a **single-speaker-lock model** where only ONE user can be actively transcribed and processed at a time. This single-threaded model is built into the architecture at the core level and represents a fundamental constraint for simultaneous multi-agent processing. 

### Current Limitations for Multi-Agent Support:
1. **Global Speaker Lock** - Only one user can hold the `active_speaker` lock (SpeakerManager singleton)
2. **Single n8n Webhook Call** - Each transcription triggers exactly one webhook call (no branching to multiple agents)
3. **Global State** - All user context stored in instance variables of single SpeakerManager object
4. **No Session Tracking** - No multi-user session store; user identity only used in payload
5. **No Agent Routing** - No mechanism to route different transcriptions to different n8n agents/workflows

---

## Part 1: n8n Webhook Configuration & Calling

### 1.1 Webhook Configuration

**File:** `src/speaker_manager.py:52-68`

```python
# Webhook selection logic (test mode support)
n8n_webhook_prod = os.getenv('N8N_WEBHOOK_URL')
n8n_webhook_test = os.getenv('N8N_WEBHOOK_TEST_URL')
test_mode = os.getenv('N8N_TEST_MODE', 'false').lower() == 'true'

if test_mode and n8n_webhook_test:
    self.n8n_webhook_url = n8n_webhook_test
elif test_mode and not n8n_webhook_test:
    self.n8n_webhook_url = n8n_webhook_prod
else:
    self.n8n_webhook_url = n8n_webhook_prod
```

**Configuration Source:** `.env` file
```env
N8N_WEBHOOK_URL=https://n8n-tunnel.iamjohnbuck.com/webhook/16a9d95c-dfa2-41f1-93a4-13f05d3b8fbe
N8N_WEBHOOK_TEST_URL=https://n8n-tunnel.iamjohnbuck.com/webhook-test/16a9d95c-dfa2-41f1-93a4-13f05d3b8fbe
N8N_TEST_MODE=false
```

**Key Points:**
- Static URL per bot instance (no per-user routing)
- Single webhook call per transcription
- Test mode support but only at startup (requires restart to change)
- URL passed down from `SpeakerManager` to `StreamingResponseHandler`

### 1.2 Webhook Call Mechanism

**File:** `src/speaker_manager.py:258-293`

The webhook is called from `_send_to_n8n()` method after transcription finalization:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True
)
async def _send_to_n8n(self, transcript: str) -> None:
    """Send transcript to n8n webhook with automatic retry"""
    
    payload = {
        'text': transcript,
        'userId': self.active_speaker,
        'timestamp': datetime.now().isoformat(),
        'useStreaming': self.use_streaming
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        if self.use_streaming:
            await self._handle_streaming_response(client, payload)
        else:
            response = await client.post(self.n8n_webhook_url, json=payload)
            response.raise_for_status()
```

**Key Points:**
- **Retry logic:** 3 attempts with exponential backoff (1-10s)
- **Payload format:** Simple JSON with text, userId, timestamp, streaming flag
- **Called once per transcription:** Not called multiple times or to multiple endpoints
- **Streaming vs Non-streaming:** Branching logic for response handling

### 1.3 Webhook Payload Structure

```json
{
    "text": "hello world",              // Transcribed speech
    "userId": "12345678",              // Discord user ID (only identifier)
    "timestamp": "2025-10-21T14:00:00", // ISO timestamp
    "useStreaming": true               // Whether to expect streaming response
}
```

**Missing for Multi-Agent:**
- No `agentId` field
- No `agentType` field
- No `conversationId` field
- No `sessionId` field
- No routing information

---

## Part 2: User Sessions & Context Management

### 2.1 Current Session Model

**Architecture:** NO explicit session management

The current implementation treats each transcription as an isolated event:

1. User speaks → new WhisperClient created
2. Audio streamed → transcribed
3. Finalization triggered → webhook called
4. Session ended → WhisperClient closed, speaker lock released

**No persistent session tracking between turns.**

### 2.2 User Identification

**File:** `src/discord_bot.py:130, src/speaker_manager.py:92`

```python
# In AudioReceiver.write()
user_id = str(user.id)  # Discord user ID as string

# In SpeakerManager.on_speaking_start()
self.active_speaker = user_id
self.lock_start_time = time.time()
```

**How Discord Users Are Identified:**
- Source: Discord voice event (user object)
- Format: Discord user ID as string (e.g., "12345678")
- Scope: Per-turn only (no cross-turn tracking)
- Storage: In-memory in SpeakerManager instance variable

### 2.3 State Storage Architecture

**Global State Variables in SpeakerManager:**

```python
class SpeakerManager:
    def __init__(self):
        # Speaker lock state
        self.active_speaker: Optional[str] = None          # Current speaker ID
        self.lock_start_time: Optional[float] = None       # When lock acquired
        self.last_audio_time: Optional[float] = None       # For silence detection
        
        # WhisperX connection (ONE per SpeakerManager)
        self.whisper_client: Optional[WhisperClient] = None
        
        # Task management
        self.timeout_task: Optional[asyncio.Task] = None
        self.silence_task: Optional[asyncio.Task] = None
        
        # Voice integration
        self.voice_connection = None                       # Discord voice client
        self.streaming_handler = None                      # Response handler
        self.audio_receiver = None                         # Audio sink
```

**Key Characteristics:**
- **Singleton Pattern:** One SpeakerManager instance per bot (line 69, discord_bot.py)
- **Global per-channel scope:** Lock applies to entire voice channel
- **Per-user scope (limited):** Only userId, lock times stored
- **Ephemeral:** No persistence between bot restarts
- **Memory-based:** No database or file storage

### 2.4 Per-User State Tracking

**Very Minimal:**

```python
# Only stored during active transcription
payload = {
    'text': transcript,
    'userId': self.active_speaker,      # Only user identifier
    'timestamp': datetime.now().isoformat(),
    'useStreaming': self.use_streaming
}
```

**NOT Tracked:**
- User preferences or settings
- Conversation history
- Previous contexts
- User roles or permissions
- Multi-turn memory
- Session context

---

## Part 3: State Storage (Per-User vs Global)

### 3.1 Storage Breakdown

| Type | Storage Location | Scope | Lifetime | Purpose |
|------|------------------|-------|----------|---------|
| **Active Speaker ID** | `self.active_speaker` | Global | Single transcription | Mutex lock |
| **Lock Time** | `self.lock_start_time` | Global | Single transcription | Timeout tracking |
| **Audio Buffers** | `AudioReceiver.user_buffers` | Per-user | During speaking | Opus audio queue |
| **WhisperX Session** | `TranscriptionSession` (in whisperx) | Per-user | During transcription | Audio accumulation |
| **Streaming Chunks** | `StreamingResponseHandler.buffer` | Per-response | During n8n response | Text buffering |

### 3.2 WhisperX Server Sessions

**File:** `src/whisper_server.py:181-407`

```python
class TranscriptionSession:
    """Per-user transcription session at WhisperX server level"""
    
    def __init__(self, websocket, user_id):
        self.websocket = websocket
        self.user_id = user_id
        
        # Dual buffer system
        self.session_buffer = bytearray()     # Complete audio
        self.processing_buffer = bytearray()  # Real-time chunks
        
        self.language = 'en'
        self.is_active = True
        self.opus_decoder = opuslib.Decoder(48000, 2)
```

**Key Points:**
- WhisperX creates ONE TranscriptionSession PER WebSocket connection
- NOT PER USER - per connection (one user = one connection = one session)
- Local scope within `handle_client()` async function
- Sessions cleaned up when WebSocket closes

### 3.3 No Global Session Database

```
❌ No Redis for session storage
❌ No Database for user context
❌ No File-based session store
❌ No Distributed cache
✅ Only in-memory instance variables
```

---

## Part 4: Discord User Identification & Tracking

### 4.1 How Discord Users Are Identified

**Source Code:** `src/discord_bot.py:119-143`

```python
class AudioReceiver(voice_recv.AudioSink):
    def write(self, user, data: voice_recv.VoiceData):
        if not user:
            return
        
        user_id = str(user.id)  # Extract Discord user ID
        
        # Create buffer for this user
        if user_id not in self.user_buffers:
            logger.info(f"📥 New audio stream from user {user_id}")
            self.user_buffers[user_id] = asyncio.Queue(maxsize=max_queue_size)
```

**Identification Method:**
1. Discord.py library provides `user` object in VoiceData
2. Extract `user.id` (Discord's unique user identifier)
3. Convert to string for use as dict key
4. Used throughout pipeline: logs, WebSocket payload, lock checking

**Constraints:**
- Per-guild scope only (different in different Discord servers)
- Only accessible during voice connection
- No persistent mapping beyond current session
- No user context/metadata available in bot code

### 4.2 User Tracking Across Transcriptions

**PROBLEM:** No tracking mechanism

```python
# Transcription 1
user_id = "111"
transcript = "hello"
# → Sent to n8n, unlocked

# Transcription 2
user_id = "111"  # Same user
transcript = "how are you"
# → Completely separate transaction, no context from transcription 1
```

**What's Lost:**
- Conversation history
- Previous user intents
- Multi-turn context
- User state changes

---

## Part 5: Multi-Agent Blocking Factors

### 5.1 PRIMARY BLOCKER: Global Speaker Lock

**File:** `src/speaker_manager.py:86-107`

```python
async def on_speaking_start(self, user_id: str, audio_stream) -> bool:
    """Handle user starting to speak"""
    
    # BLOCKER 1: Only one speaker allowed
    if self.active_speaker:
        logger.info(f"🔇 Ignoring {user_id} - {self.active_speaker} is currently speaking")
        return False
    
    # Lock to this speaker (GLOBAL STATE)
    self.active_speaker = user_id
    self.lock_start_time = time.time()
    
    # BLOCKER 2: One WhisperX client per SpeakerManager
    await self._start_transcription(user_id, audio_stream)
```

**Impact:**
- Only 1 user can be transcribed at a time
- Other speakers completely ignored (not queued)
- Cannot process multiple transcriptions in parallel
- Cannot route to different agents simultaneously

### 5.2 SECONDARY BLOCKER: Single Webhook Endpoint

**File:** `src/speaker_manager.py:258-289`

```python
# One webhook URL per bot instance
self.n8n_webhook_url = n8n_webhook_prod  # Static, never changes

# Called once per transcription
async def _send_to_n8n(self, transcript: str) -> None:
    # POST to SINGLE webhook
    response = await client.post(self.n8n_webhook_url, json=payload)
```

**Impact:**
- Cannot route same transcript to multiple agents
- Cannot branch to different workflows
- Single point of failure
- No agent selection logic

### 5.3 TERTIARY BLOCKER: No Session/Conversation Context

**File:** `src/speaker_manager.py:272-277`

```python
payload = {
    'text': transcript,
    'userId': self.active_speaker,      # Only user ID
    'timestamp': datetime.now().isoformat(),
    'useStreaming': self.use_streaming
}
```

**Impact:**
- No `conversationId` to link multiple turns
- No `sessionId` to track multi-agent sessions
- No agent selection information
- No context routing rules

### 5.4 QUATERNARY BLOCKER: No Per-User Session Store

**Architecture:**
```
No database ← No way to track per-user preferences
No Redis ← No distributed session cache
No file store ← No persistence between restarts
```

**Impact:**
- Cannot remember user preferences across restarts
- Cannot store multi-turn conversation history
- Cannot implement user-specific routing logic
- Cannot scale to multiple bot instances

---

## Part 6: Detailed Call Flow

### 6.1 Current Single-Agent Flow

```
┌─────────────────────────────────────────────────────────────┐
│ User speaks in Discord voice channel                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ AudioReceiver.write() - Gets Opus packets                   │
│ - Extracts Discord user_id                                 │
│ - Creates asyncio.Queue per user                           │
│ - Starts audio stream generator                            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ SpeakerManager.on_speaking_start(user_id, stream)           │
│ - CHECK LOCK: if active_speaker exists, IGNORE and return  │
│ - ACQUIRE LOCK: self.active_speaker = user_id              │
│ - Create WhisperClient (NEW for each transcription)         │
│ - Start silence detection timer                            │
│ - Start timeout timer (45s max)                            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ SpeakerManager._stream_audio()                              │
│ - Send Opus chunks to WhisperX WebSocket                    │
│ - Update silence detection timer                           │
│ - Run until audio stops or timeout                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴──────────────┐
         ▼                            ▼
    SILENCE (800ms)           OR   TIMEOUT (45s)
         │                            │
         └─────────────┬──────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ SpeakerManager._finalize_transcription()                    │
│ - Call WhisperX.finalize() → get final transcript          │
│ - Close WhisperX connection                                │
│ - RELEASE LOCK: self.active_speaker = None                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ SpeakerManager._send_to_n8n(transcript)                     │
│ - Build payload:                                           │
│   {                                                        │
│     "text": transcript,                                    │
│     "userId": user_id,  ← ONLY user identifier            │
│     "timestamp": ISO_TIME,                                │
│     "useStreaming": true/false                            │
│   }                                                        │
│ - POST to SINGLE n8n webhook URL                          │
│ - Retry 3 times on network errors                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴──────────────┐
         ▼                            ▼
  STREAMING MODE              NON-STREAMING MODE
  (default: true)             (streaming disabled)
         │                            │
         ▼                            ▼
  Receive chunked           Receive full response
  HTTP response             (200 OK with JSON)
  (text/event-stream          │
   or text/plain)              │
         │                      │
         ▼                      │
  StreamingResponseHandler │
  - Extract sentences          │
  - Buffer incomplete ones     │
  - Send to Chatterbox TTS    │
  - Play in Discord voice     │
         │                      │
         └──────────┬───────────┘
                    │
                    ▼
           ✅ Response complete
           Ready for next speaker
```

### 6.2 Current Architecture Constraints

1. **Linear Processing:** Each step waits for previous (no parallelism)
2. **Blocking Lock:** Second speaker completely ignored during first speaker
3. **Single Destination:** All transcripts go to one webhook
4. **No Branching:** Cannot send same transcript to multiple agents
5. **No Context:** No conversation state passed between turns

---

## Part 7: Streaming Response Handler

### 7.1 Streaming Response Processing

**File:** `src/streaming_handler.py:36-545`

```python
class StreamingResponseHandler:
    def __init__(self, voice_client, user_id: str, options: dict = None):
        self.voice_client = voice_client
        self.user_id = user_id  # Only user identifier stored
        self.buffer = ''
        self.sentence_queue = []
        
        # Configuration (environment-based, not per-user)
        self.use_clause_splitting = os.getenv('USE_CLAUSE_SPLITTING', 'true')
        self.use_parallel_processing = os.getenv('USE_PARALLEL_TTS', 'true')
```

**Response Handling:**

```python
async def _handle_streaming_response(self, client: httpx.AsyncClient, payload: dict):
    """Handle streaming response from n8n webhook"""
    
    # Check response Content-Type
    if 'text/event-stream' in content_type:
        # SSE mode: Process server-sent events
        async for line in response.aiter_lines():
            if line.startswith('data: '):
                await handler.on_chunk(chunk_data)
    
    elif 'text/plain' in content_type:
        # Text streaming mode: Process chunks
        async for chunk in response.aiter_text():
            await handler.on_chunk(chunk)
    
    else:
        # JSON mode: Process full response
        data = json.loads(await response.aread())
        await handler.on_chunk(data['content'])
```

**Key Point:** No per-user routing or agent selection here - just response processing

### 7.2 Sentence Buffering

```python
def _extract_sentences(self) -> list[str]:
    """Extract complete sentences from buffer"""
    sentences = []
    
    # Split on delimiters (. ! ? etc.)
    for match in self.sentence_delimiters.finditer(self.buffer):
        end_index = match.end()
        sentence = self.buffer[last_index:end_index].strip()
        
        # Only add if long enough
        if len(sentence) >= self.min_sentence_length:
            sentences.append(sentence)
    
    # Keep incomplete sentence in buffer
    self.buffer = self.buffer[last_index:].strip()
    return sentences
```

**Features:**
- Parallel or sequential TTS generation
- Retry logic per sentence
- Continues on failed sentences (doesn't crash)

---

## Part 8: Environment Configuration

### 8.1 Configuration Loading Points

**File:** `.env` (loaded at startup only)

```env
# Single webhook (no per-user/agent variants)
N8N_WEBHOOK_URL=https://...
N8N_WEBHOOK_TEST_URL=https://...
N8N_TEST_MODE=false  # Requires restart to change

# Speaker management (global, not per-user)
SILENCE_THRESHOLD_MS=800
MAX_SPEAKING_TIME_MS=45000

# Streaming (global, not per-user)
USE_STREAMING=true
USE_CLAUSE_SPLITTING=true
USE_PARALLEL_TTS=false

# No per-user config possible
```

### 8.2 Configuration Access Pattern

```python
# In SpeakerManager.__init__()
self.silence_threshold_ms = int(os.getenv('SILENCE_THRESHOLD_MS', '800'))
self.n8n_webhook_url = os.getenv('N8N_WEBHOOK_URL')

# In StreamingResponseHandler.__init__()
self.chatterbox_url = os.getenv('CHATTERBOX_URL', 'http://localhost:4800/v1')
```

**Limitations:**
- All read at initialization time
- Cannot change per-user
- Cannot change at runtime
- Cannot route based on environment

---

## Part 9: Webhook Integration Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                   CURRENT FLOW                               │
│         (Single Agent, No Multi-User Routing)               │
└──────────────────────────────────────────────────────────────┘

Discord User speaks
    ↓
AudioReceiver.write(user, opus_data)
    ↓
user_id extracted (only identifier)
    ↓
user_buffers[user_id] created
    ↓
on_speaking_start(user_id, stream)
    ├─ if active_speaker exists:
    │   └─ IGNORE this speaker, return False
    └─ else:
        └─ Lock: active_speaker = user_id
           ├─ Create WhisperClient (single instance)
           ├─ Stream audio to WhisperX
           ├─ Silence/timeout timers
           └─ Wait for finalization
               │
               ├─ finalize() called
               ├─ Get transcript
               └─ Unlock: active_speaker = None
                   │
                   └─ _send_to_n8n(transcript)
                       ├─ Build payload:
                       │  {
                       │    "text": transcript,
                       │    "userId": user_id,
                       │    "timestamp": ...,
                       │    "useStreaming": true
                       │  }
                       │
                       └─ POST to single webhook
                           ├─ Retry 3x on network error
                           └─ Receive response
                               ├─ if streaming: chunked
                               ├─ if not: full JSON
                               └─ StreamingResponseHandler
                                   ├─ Extract sentences
                                   ├─ Buffer incomplete
                                   ├─ Send to Chatterbox TTS
                                   └─ Play in Discord

Next speaker ready (if queue exists)
```

---

## Part 10: What Would Prevent Multi-Agent Support

### 10.1 Architecture Blockers (Cannot Fix Without Redesign)

| Blocker | Current Impl | Issue | Impact |
|---------|-------------|-------|--------|
| **Single Speaker Lock** | `self.active_speaker` (singleton) | Can't process 2+ speakers in parallel | Agents can't work simultaneously |
| **Single Webhook URL** | `self.n8n_webhook_url` (static) | Can't route to multiple agents | All transcripts go to one place |
| **No Session Context** | Only `userId` in payload | Can't link multi-turn conversations | Each turn is isolated |
| **Global SpeakerManager** | One instance per bot | Can't have per-agent manager | No agent isolation |
| **In-Memory Only** | No database/cache | Can't track across restarts | No persistence |

### 10.2 Software Limitations (Would Require Code Changes)

1. **No Agent Routing Logic**
   - No way to determine which agent should handle a transcription
   - No field in payload to specify agent
   - No branching logic in webhook sending

2. **No Multi-Agent Support**
   - Can't send to multiple webhooks
   - Can't fork based on content
   - Can't queue concurrent requests

3. **No Session Management**
   - No persistent session store (database/cache)
   - No conversation history tracking
   - No multi-turn state
   - No user preferences

4. **No Distributed Support**
   - One bot instance = one speaker lock
   - Can't scale to multiple bots
   - No service discovery
   - No load balancing

---

## Part 11: Data Flow Summary Table

| Component | Current Implementation | Storage | Scope | Lifetime |
|-----------|----------------------|---------|-------|----------|
| **User ID** | `str(user.id)` from Discord | In-memory dict key | Per-turn | Transcription duration |
| **Speaker Lock** | `self.active_speaker` | SpeakerManager instance | Global | Single transcription |
| **Webhook URL** | `os.getenv('N8N_WEBHOOK_URL')` | Environment variable | Global | Bot instance lifetime |
| **Payload** | JSON dict with text/userId/timestamp | HTTP POST body | Single request | Request duration |
| **WhisperX Session** | `TranscriptionSession` per connection | WebSocket server memory | Per-user | Connection lifetime |
| **Audio Buffers** | `asyncio.Queue` per user | Discord bot memory | Per-user | Speaking duration |
| **Streaming Response** | `StreamingResponseHandler` instance | Async handler memory | Per-response | Response duration |
| **Configuration** | `.env` file values | Environment variables | Global | Bot startup |

---

## Part 12: Key Code Locations Reference

### Critical Files

| File | Lines | Purpose |
|------|-------|---------|
| `src/speaker_manager.py` | 34-107 | Speaker lock acquisition/release |
| `src/speaker_manager.py` | 258-293 | Webhook call with retry |
| `src/speaker_manager.py` | 295-433 | Streaming response handling |
| `src/discord_bot.py` | 107-228 | Audio receiver, user identification |
| `src/discord_bot.py` | 65-69 | SpeakerManager singleton |
| `src/whisper_client.py` | 45-94 | WebSocket connection per transcription |
| `src/whisper_server.py` | 181-407 | Per-connection session in WhisperX |
| `src/streaming_handler.py` | 85-134 | Sentence extraction & buffering |
| `.env` | All | Configuration source |

### Lock Acquisition/Release

```python
# Acquisition - src/speaker_manager.py:86-92
if self.active_speaker:
    return False  # IGNORED
self.active_speaker = user_id

# Release - src/speaker_manager.py:434-443
self.active_speaker = None
self.lock_start_time = None
```

### Webhook Call

```python
# src/speaker_manager.py:258-289
payload = {
    'text': transcript,
    'userId': self.active_speaker,
    'timestamp': datetime.now().isoformat(),
    'useStreaming': self.use_streaming
}
response = await client.post(self.n8n_webhook_url, json=payload)
```

---

## Part 13: Recommendations for Multi-Agent Support

### 13.1 Minimal Changes (Single Agent Only)

Currently supports:
- One n8n workflow
- One webhook endpoint
- Sequential speaker processing
- Limited to single agent scenarios

### 13.2 For True Multi-Agent Support Would Require

1. **Session Management Layer**
   - Add database (PostgreSQL) or cache (Redis)
   - Track user→agent mapping
   - Store conversation history

2. **Agent Routing Service**
   - New component to route transcripts
   - Query which agent should handle input
   - Send to appropriate webhook(s)

3. **Parallel Processing**
   - Replace speaker lock with per-user queues
   - Multiple WhisperClients running
   - Concurrent n8n webhook calls

4. **Context Management**
   - Pass sessionId, conversationId in payloads
   - Retrieve context before sending to n8n
   - Maintain multi-turn state

5. **Distributed Architecture**
   - Multiple bot instances
   - Shared session store
   - Load balancing
   - Service discovery

---

## Conclusion

VoxBridge is a **single-speaker, single-agent system** by architectural design. The speaker lock, singleton SpeakerManager, static webhook URL, and lack of session management make it fundamentally incompatible with simultaneous multi-agent operations.

**For multi-agent support, core architectural changes would be necessary:**
- Replace single speaker lock with per-user queue system
- Implement session/context database
- Add agent routing logic
- Support multiple concurrent webhook calls
- Add distributed state management

The current implementation is well-suited for single-speaker scenarios and provides good performance for that use case, but scaling to multi-agent would require significant architectural redesign.

