# Phase 5: Core Voice Pipeline Refactor - Implementation Plan

**Status**: 🟡 In Progress
**Start Date**: October 28, 2025
**Estimated Duration**: 2-3 days
**Complexity**: HIGH (Major architectural refactor)

---

## 🎯 Objective

Transform VoxBridge from a Discord-centric architecture to a modular, session-based system with standalone core services that support multiple input/output channels simultaneously.

---

## 📊 Current Architecture (Problems)

```
discord_bot.py (1200+ lines)
  ├── speaker_manager.py (800+ lines) → Global speaker lock (Discord-only)
  ├── whisper_client.py (350+ lines) → Discord-coupled STT
  └── streaming_handler.py (700+ lines) → Hard-coded n8n webhooks
```

**Critical Issues**:
- ❌ Global speaker lock (only 1 Discord user can speak at a time)
- ❌ Tightly coupled to Discord voice channels
- ❌ Hard-coded n8n webhooks (no per-agent configuration)
- ❌ Cannot support multiple concurrent web users
- ❌ WebRTC and Discord share same voice pipeline (coupling)
- ❌ No session-based routing (everything is Discord-centric)

---

## 🎯 Target Architecture (Solution)

```
src/services/
  ├── conversation_service.py  # Session management (multi-user, in-memory cache)
  ├── stt_service.py           # WhisperX abstraction (input-agnostic)
  ├── llm_service.py           # LLM routing (provider-agnostic)
  └── tts_service.py           # Chatterbox abstraction (output-agnostic)

Voice Inputs (Parallel):
  ├── Discord Extension → conversation_service
  └── WebRTC Handler → conversation_service

Voice Outputs (Parallel):
  ├── Discord Voice Channel
  └── Browser WebRTC Audio
```

**Benefits**:
- ✅ Multiple concurrent sessions (Discord + multiple web users)
- ✅ Input-agnostic (Discord, WebRTC, future: Twilio, Telegram)
- ✅ Output-agnostic (Discord, Browser, future: phone, Alexa)
- ✅ Standalone core services (no Discord dependency)
- ✅ Prepares for Phase 6 (Extension System)
- ✅ Session-based routing (UUID-based, not speaker lock)

---

## 🏗️ Service Abstraction Layer Design

### Service Dependencies

```
ConversationService (foundation)
    ↓
LLMService (depends on ConversationService)
    ↓
[WebRTC Handler / Discord Bot] (consumers)
    ↓
STTService (standalone) → TranscriptChunk
TTSService (standalone) ← VoiceSettings
```

### Service Summary

| Service | Lines (Est.) | Purpose | Key Features |
|---------|-------------|---------|--------------|
| **ConversationService** | ~400 | Session management + caching | In-memory TTL cache (15 min), agent config loading, conversation persistence |
| **STTService** | ~350 | WhisperX abstraction | Streaming transcription, VAD (600ms), auto-reconnect |
| **LLMService** | ~300 | LLM provider routing | OpenRouter/Local/n8n routing, context injection, fallback chain |
| **TTSService** | ~250 | Chatterbox abstraction | Streaming WAV synthesis, voice settings, health checks |
| **Total** | **~1,300** | | |

---

## 📐 Detailed Service Designs

### 1. ConversationService

**Purpose**: Manage conversation sessions with in-memory context caching, session lifecycle, and agent configuration loading.

**Key Features**:
- Session-based routing (UUID session IDs)
- In-memory conversation context cache (TTL-based, default 15 minutes)
- Support multiple concurrent sessions (async/await, NO queues)
- Load context from PostgreSQL conversations table
- Cache conversation history (last N messages, default 20)
- TTL-based cache expiration with background cleanup
- Agent configuration loading from database

**Class Signature**:
```python
@dataclass
class CachedContext:
    session: Session              # SQLAlchemy Session model
    agent: Agent                  # SQLAlchemy Agent model
    messages: List[Conversation]  # Recent conversation history
    last_activity: datetime       # Last cache access time
    expires_at: datetime          # When to evict from cache
    lock: asyncio.Lock            # Concurrent access control

class ConversationService:
    def __init__(self, cache_ttl_minutes: int = 15, max_context_messages: int = 20):
        self._cache: Dict[str, CachedContext] = {}
        self._cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self._max_context = max_context_messages
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start background cache cleanup task"""

    async def stop(self) -> None:
        """Stop background tasks"""

    async def get_or_create_session(
        self, session_id: str, user_id: str, agent_id: str, channel_type: str = "webrtc"
    ) -> Session

    async def get_conversation_context(
        self, session_id: str, limit: int = 10, include_system_prompt: bool = True
    ) -> List[Message]

    async def add_message(
        self, session_id: str, role: str, content: str, metadata: Optional[Dict] = None
    ) -> Message

    async def get_agent_config(self, session_id: str) -> Agent

    async def update_session_activity(self, session_id: str) -> None

    async def end_session(self, session_id: str, persist: bool = True) -> None

    async def clear_cache(self, session_id: Optional[str] = None) -> None

    async def get_active_sessions(self) -> List[str]
```

**Design Patterns**:
- **Cache-Aside Pattern**: Check cache first, load from DB on miss
- **TTL-based Expiration**: Automatic cleanup of inactive sessions
- **Async Locks**: Per-session locks prevent race conditions
- **Repository Pattern**: Encapsulates database access logic

**Configuration**:
```python
CONVERSATION_CACHE_TTL_MINUTES = int(os.getenv('CONVERSATION_CACHE_TTL_MINUTES', '15'))
MAX_CONTEXT_MESSAGES = int(os.getenv('MAX_CONTEXT_MESSAGES', '20'))
CACHE_CLEANUP_INTERVAL_SECONDS = int(os.getenv('CACHE_CLEANUP_INTERVAL_SECONDS', '60'))
```

**Error Handling**:
- Database errors → Return empty context (graceful degradation)
- Cache corruption → Clear and reload from database
- Concurrent access → Per-session locks with timeout
- Memory pressure → LRU eviction if cache exceeds max size

---

### 2. STTService

**Purpose**: Abstract WhisperX STT with input-agnostic interface supporting streaming transcription, silence detection, and automatic reconnection.

**Key Features**:
- WebSocket connection to WhisperX server
- Input-agnostic (works with Discord audio, WebRTC audio, future: phone calls)
- Streaming transcription (partial + final)
- Silence detection (VAD with configurable threshold, default 600ms)
- Error handling and reconnection logic (exponential backoff)
- Health check with background monitoring

**Class Signature**:
```python
class TranscriptType(Enum):
    PARTIAL = "partial"      # Interim result (may change)
    FINAL = "final"          # Confirmed segment
    SILENCE = "silence"      # Silence detected (end of utterance)

@dataclass
class TranscriptChunk:
    text: str
    type: TranscriptType
    confidence: float
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    language: Optional[str] = None
    metadata: Optional[dict] = None

@dataclass
class STTConfig:
    whisper_url: str
    model: str = "small"
    language: str = "en"
    silence_threshold_ms: int = 600
    max_speaking_time_ms: int = 45000
    reconnect_attempts: int = 5
    reconnect_delay: float = 2.0

class STTService:
    def __init__(self, config: STTConfig):
        self._config = config
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._connected = False

    async def connect(self) -> None

    async def disconnect(self) -> None

    async def transcribe_stream(
        self,
        audio_iterator: AsyncIterator[bytes],
        on_partial: Optional[Callable[[TranscriptChunk], None]] = None,
        on_final: Optional[Callable[[TranscriptChunk], None]] = None,
        on_silence: Optional[Callable[[], None]] = None
    ) -> AsyncIterator[TranscriptChunk]

    async def transcribe_complete(self, audio: bytes, return_timestamps: bool = False) -> str

    async def health_check(self) -> bool

    @property
    def is_connected(self) -> bool
```

**Design Patterns**:
- **Adapter Pattern**: Wraps WhisperX WebSocket protocol
- **Observer Pattern**: Callbacks for event notification (partial, final, silence)
- **Strategy Pattern**: Supports both streaming and complete transcription modes
- **Circuit Breaker**: Automatic reconnection with exponential backoff

**Configuration**:
```python
WHISPER_SERVER_URL = os.getenv('WHISPER_SERVER_URL', 'ws://whisperx:4901')
WHISPERX_MODEL = os.getenv('WHISPERX_MODEL', 'small')
WHISPERX_LANGUAGE = os.getenv('WHISPERX_LANGUAGE', 'en')
SILENCE_THRESHOLD_MS = int(os.getenv('SILENCE_THRESHOLD_MS', '600'))
MAX_SPEAKING_TIME_MS = int(os.getenv('MAX_SPEAKING_TIME_MS', '45000'))
```

**Error Handling**:
- Connection failures → Exponential backoff reconnection (5 attempts)
- Malformed transcripts → Skip invalid chunks, continue processing
- Audio format errors → Validate chunk size, log warnings
- Timeout handling → Set WebSocket read timeout, trigger reconnection
- Graceful degradation → Return empty transcripts if WhisperX unavailable

---

### 3. LLMService

**Purpose**: Route LLM requests to appropriate providers (OpenRouter, Local, n8n) with conversation context injection and agent configuration support.

**Key Features**:
- Use existing LLM provider factory from Phase 3 (`src/llm/factory.py`)
- Conversation context injection (load from ConversationService cache)
- Agent configuration support (temperature, model, system prompt)
- Streaming response support
- n8n webhook fallback (if agent.use_n8n = true)
- Error handling with graceful degradation
- Fallback chain: Primary → n8n → Local

**Class Signature**:
```python
class ResponseFormat(Enum):
    STREAMING = "streaming"
    COMPLETE = "complete"

@dataclass
class LLMConfig:
    default_temperature: float = 0.7
    default_max_tokens: int = 1000
    streaming_enabled: bool = True
    n8n_fallback_enabled: bool = True
    timeout_seconds: int = 60
    retry_attempts: int = 3
    retry_delay: float = 1.0

class LLMService:
    def __init__(
        self,
        conversation_service: ConversationService,
        config: LLMConfig,
        provider_factory: Optional[LLMProviderFactory] = None
    ):
        self._conversation_service = conversation_service
        self._config = config
        self._provider_factory = provider_factory or LLMProviderFactory()

    async def generate_response(
        self,
        session_id: str,
        user_message: str,
        stream: bool = True,
        context_limit: int = 10,
        **kwargs  # Override agent settings
    ) -> AsyncIterator[str]

    async def generate_response_complete(
        self, session_id: str, user_message: str, context_limit: int = 10, **kwargs
    ) -> str

    async def cancel_generation(self, session_id: str) -> bool
```

**Design Patterns**:
- **Strategy Pattern**: Swappable LLM providers via `BaseLLMProvider` interface
- **Dependency Injection**: Accepts `ConversationService` and `LLMProviderFactory`
- **Factory Pattern**: Uses `LLMProviderFactory` to instantiate providers
- **Chain of Responsibility**: Fallback chain (primary → n8n → local)
- **Retry Pattern**: Exponential backoff retry on transient errors

**Configuration**:
```python
DEFAULT_LLM_TEMPERATURE = float(os.getenv('DEFAULT_LLM_TEMPERATURE', '0.7'))
DEFAULT_LLM_MAX_TOKENS = int(os.getenv('DEFAULT_LLM_MAX_TOKENS', '1000'))
LLM_STREAMING_ENABLED = os.getenv('LLM_STREAMING_ENABLED', 'true').lower() == 'true'
N8N_FALLBACK_ENABLED = os.getenv('N8N_FALLBACK_ENABLED', 'true').lower() == 'true'
LLM_TIMEOUT_SECONDS = int(os.getenv('LLM_TIMEOUT_SECONDS', '60'))
```

**Error Handling**:
- Provider selection errors → Fall back to default provider
- Provider failures → Try fallback chain (n8n → local)
- Context building errors → Use empty context (system prompt only)
- Timeout handling → Wrap generation with asyncio.timeout
- Concurrent request management → Track active requests, allow cancellation

---

### 4. TTSService

**Purpose**: Abstract Chatterbox TTS API with output-agnostic interface supporting streaming WAV synthesis and agent-configured voice settings.

**Key Features**:
- HTTP client for Chatterbox TTS API
- Streaming WAV audio synthesis
- Voice configuration from agent (voice, rate, pitch)
- Output-agnostic (works with Discord, WebRTC, future: phone)
- Health check and error handling
- Batch synthesis support (parallel requests)

**Class Signature**:
```python
class AudioFormat(Enum):
    WAV = "wav"      # WAV container with PCM
    PCM = "pcm"      # Raw 16-bit PCM
    OPUS = "opus"    # Opus codec (future)

@dataclass
class TTSConfig:
    chatterbox_url: str
    default_voice: str = "auren_voice"
    default_rate: float = 1.0
    default_pitch: float = 1.0
    sample_rate: int = 24000
    timeout_seconds: int = 30
    chunk_size: int = 4096
    retry_attempts: int = 3
    retry_delay: float = 1.0

@dataclass
class VoiceSettings:
    voice: str
    rate: float = 1.0      # 0.5-2.0 (speed)
    pitch: float = 1.0     # 0.5-2.0 (pitch shift)
    volume: float = 1.0    # 0.0-2.0 (gain)

class TTSService:
    def __init__(self, config: TTSConfig):
        self._config = config
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None

    async def stop(self) -> None

    async def synthesize_stream(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        format: AudioFormat = AudioFormat.WAV
    ) -> AsyncIterator[bytes]

    async def synthesize_complete(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        format: AudioFormat = AudioFormat.WAV
    ) -> tuple[bytes, AudioMetadata]

    async def synthesize_batch(
        self, texts: list[str], voice_settings: Optional[VoiceSettings] = None
    ) -> AsyncIterator[tuple[int, bytes, AudioMetadata]]

    async def get_available_voices(self) -> list[str]

    async def health_check(self) -> bool
```

**Design Patterns**:
- **Adapter Pattern**: Wraps Chatterbox HTTP API with clean async interface
- **Strategy Pattern**: Supports multiple audio formats (WAV, PCM, Opus)
- **Iterator Pattern**: Streaming audio synthesis via async iterators
- **Builder Pattern**: `VoiceSettings` allows incremental configuration
- **Health Check Pattern**: Background task monitors service availability

**Configuration**:
```python
CHATTERBOX_URL = os.getenv('CHATTERBOX_URL', 'http://chatterbox:4800')
CHATTERBOX_VOICE_ID = os.getenv('CHATTERBOX_VOICE_ID', 'auren_voice')
TTS_RATE = float(os.getenv('TTS_RATE', '1.0'))
TTS_PITCH = float(os.getenv('TTS_PITCH', '1.0'))
TTS_SAMPLE_RATE = int(os.getenv('TTS_SAMPLE_RATE', '24000'))
```

**Error Handling**:
- HTTP errors → Retry with exponential backoff (3 attempts)
- Malformed audio → Validate WAV header, return empty audio on error
- Voice not found → Fall back to default voice
- Timeout handling → Set HTTP timeout via ClientTimeout
- Service unavailable → Return silent audio (graceful degradation)

---

## 📋 Implementation Tasks (10 Phases)

### Phase 5.1: Implement ConversationService ⏳
**Agent**: Manual implementation (foundation service)
**Duration**: 4-6 hours
**Deliverables**:
- `src/services/conversation_service.py` (~400 lines)
- In-memory cache with TTL
- Background cleanup task
- Session management
- Agent configuration loading

**Dependencies**:
- `src/database/models.py` (Phase 1)
- `src/database/session.py` (Phase 1)

---

### Phase 5.2: Implement STTService ⏳
**Agent**: Manual implementation
**Duration**: 3-4 hours
**Deliverables**:
- `src/services/stt_service.py` (~350 lines)
- WhisperX WebSocket client
- Streaming transcription
- VAD (silence detection)
- Auto-reconnect logic

**Dependencies**:
- Existing `src/whisper_client.py` (extract patterns)

---

### Phase 5.3: Implement LLMService ⏳
**Agent**: Manual implementation
**Duration**: 3-4 hours
**Deliverables**:
- `src/services/llm_service.py` (~300 lines)
- LLM provider routing
- Context injection
- Fallback chain
- Streaming support

**Dependencies**:
- `src/services/conversation_service.py` (Phase 5.1)
- `src/llm/factory.py` (Phase 3)

---

### Phase 5.4: Implement TTSService ⏳
**Agent**: Manual implementation
**Duration**: 3-4 hours
**Deliverables**:
- `src/services/tts_service.py` (~250 lines)
- Chatterbox HTTP client
- Streaming WAV synthesis
- Voice settings
- Health checks

**Dependencies**:
- Existing Chatterbox integration patterns

---

### Phase 5.5: Update WebRTC Handler ⏳
**Agent**: Manual refactoring
**Duration**: 2-3 hours
**Deliverables**:
- `src/voice/webrtc_handler.py` (modified)
- Use new services instead of direct coupling
- Remove WhisperX WebSocket client
- Remove LLM provider coupling
- Use conversation_service for session context

**Dependencies**:
- All 4 services (Phase 5.1-5.4)

---

### Phase 5.6: Update Discord Bot ⏳
**Agent**: Manual refactoring
**Duration**: 2-3 hours
**Deliverables**:
- `src/discord_bot.py` (modified)
- Use new services
- Remove speaker lock logic
- Use conversation_service for session management

**Dependencies**:
- All 4 services (Phase 5.1-5.4)

---

### Phase 5.7: Delete Old Files ⏳
**Agent**: Manual cleanup
**Duration**: 30 minutes
**Deliverables**:
- Delete `src/speaker_manager.py` (800 lines)
- Delete `src/whisper_client.py` (350 lines)
- Delete `src/streaming_handler.py` (700 lines)
- Total: ~1,850 lines removed

**Note**: Git tracks history, safe to delete

---

### Phase 5.8: Write Unit Tests ⏳
**Agent**: `unit-test-writer`
**Duration**: 4-6 hours
**Deliverables**:
- `tests/unit/test_conversation_service.py` (~400 lines, 20+ tests)
- `tests/unit/test_stt_service.py` (~350 lines, 15+ tests)
- `tests/unit/test_llm_service.py` (~300 lines, 15+ tests)
- `tests/unit/test_tts_service.py` (~250 lines, 15+ tests)
- Total: ~65+ new tests

**Coverage Target**: Maintain 88%+ overall coverage

---

### Phase 5.9: Integration Testing ⏳
**Agent**: `integration-test-writer`
**Duration**: 2-3 hours
**Deliverables**:
- `tests/integration/test_voice_pipeline.py` (end-to-end)
- Test WebRTC + services
- Test Discord + services
- Test concurrent sessions

**Coverage Target**: All critical paths tested

---

### Phase 5.10: Update Documentation ⏳
**Agent**: `api-documenter`
**Duration**: 2-3 hours
**Deliverables**:
- Update `ARCHITECTURE.md` - Rewrite "Current Implementation Status"
- Update `AGENTS.md` - Replace "Speaker Lock System" → "Session Management System"
- Update `CLAUDE.md` - Update "Key Files" section
- Create `docs/progress/phase-5-completion.md`

---

## 🎯 Success Criteria

Phase 5 is considered **complete** when:

- ✅ All 4 services implemented and working
- ✅ WebRTC handler uses new services (no direct coupling)
- ✅ Discord bot uses new services (no speaker lock)
- ✅ Old files deleted (speaker_manager, whisper_client, streaming_handler)
- ✅ Unit tests passing (65+ new tests, 88%+ coverage)
- ✅ Integration tests passing (end-to-end)
- ✅ Documentation updated (3 major files)
- ✅ Multiple concurrent sessions working (Discord + WebRTC)
- ✅ No regressions (all existing features still work)

---

## 📊 Metrics

**Code Changes**:
- Lines Added: ~1,300 (4 new services)
- Lines Removed: ~1,850 (3 old files)
- Net Change: **-550 lines** (code reduction!)
- New Tests: ~1,300 lines (65+ tests)

**Architecture Impact**:
- Before: Monolithic Discord-centric pipeline
- After: Modular session-based services
- Concurrent Sessions: 1 → Unlimited
- Input Channels: 1 (Discord) → 2+ (Discord, WebRTC, future)
- Output Channels: 1 (Discord) → 2+ (Discord, WebRTC, future)

---

## ⏱️ Timeline

```
Day 1 (Oct 28):
  - Phase 5.1: ConversationService (4-6 hours)
  - Phase 5.2: STTService (3-4 hours)

Day 2 (Oct 29):
  - Phase 5.3: LLMService (3-4 hours)
  - Phase 5.4: TTSService (3-4 hours)

Day 3 (Oct 30):
  - Phase 5.5: Update WebRTC Handler (2-3 hours)
  - Phase 5.6: Update Discord Bot (2-3 hours)
  - Phase 5.7: Delete old files (30 min)
  - Phase 5.8: Write unit tests (4-6 hours)

Day 4 (Oct 31, buffer):
  - Phase 5.9: Integration testing (2-3 hours)
  - Phase 5.10: Update documentation (2-3 hours)
  - Final verification and cleanup
```

**Total Estimated Time**: 2-3 days

---

## 🔗 Integration with Other Phases

### Phase 1: Core Infrastructure ✅
- Uses PostgreSQL for session/conversation persistence
- Uses SQLAlchemy async sessions
- Uses Agent, Session, Conversation models

### Phase 2: Agent Management ✅
- Loads agent configuration from database
- Uses agent settings (LLM provider, TTS voice, temperature)
- Supports per-agent configuration

### Phase 3: LLM Provider Abstraction ✅
- Uses LLMProviderFactory for provider instantiation
- Routes to OpenRouter/Local/n8n based on agent config
- Reuses existing provider implementations

### Phase 4: Web Voice Interface ✅
- WebRTC handler will use new services
- Removes direct WhisperX/LLM coupling
- Enables concurrent web users

### Phase 6: Extension System 🔜
- Discord bot becomes an extension
- Core services remain standalone
- n8n becomes an optional extension

---

## 🚧 Risks & Mitigations

### Risk 1: Breaking Changes
**Risk**: Refactoring may break existing Discord bot functionality
**Mitigation**: Keep both old and new code temporarily, verify before deletion
**Status**: Mitigated via git rollback (branch: voxbridge-2.0)

### Risk 2: Performance Degradation
**Risk**: In-memory cache may cause memory issues with many sessions
**Mitigation**: TTL-based eviction, configurable cache size, monitoring
**Status**: Mitigated via background cleanup task

### Risk 3: Integration Complexity
**Risk**: Wiring services together may reveal design issues
**Mitigation**: Incremental integration (WebRTC first, Discord second)
**Status**: Mitigated via phased rollout (5.5, 5.6)

### Risk 4: Test Coverage Drop
**Risk**: Deleting old files may reduce coverage
**Mitigation**: Write comprehensive tests BEFORE deletion
**Status**: Mitigated via Phase 5.8 (65+ new tests)

---

## 📝 Notes

- This is the most complex phase of VoxBridge 2.0 transformation
- Requires careful refactoring to avoid breaking changes
- Git branch protection ensures safe rollback if needed
- Incremental testing at each phase ensures stability
- Documentation updates are critical for maintainability

---

**Created**: October 28, 2025
**Last Updated**: October 28, 2025
**Status**: 🟡 Ready to Begin Implementation
