# Singleton Service Pattern Fix - Multi-Turn Conversation Restoration

**Date**: 2025-11-26
**Status**: PLANNED (Not yet implemented)
**Priority**: CRITICAL
**Branch**: `feature/memory-system`
**Issue**: Multi-turn conversations broken after factory pattern implementation

---

## Executive Summary

**Problem**: After implementing the async factory pattern for MemoryService initialization, multi-turn conversations are broken. Users can only have ONE exchange with agents before conversation history is lost.

**Root Cause**: WebRTC handler creates a NEW ConversationService instance for EVERY WebSocket connection, each with an empty conversation cache (`self._cache`), instead of using the global singleton.

**Solution**: Implement dependency injection pattern to pass the global ConversationService singleton to WebRTC handlers via FastAPI's Depends() mechanism.

**Impact**:
- ✅ Restores multi-turn conversation functionality
- ✅ Preserves memory access (factory pattern for MemoryService)
- ✅ Follows modern FastAPI best practices (2024)
- ✅ Improves testability and maintainability

**Effort**: ~1 hour (30-45 min implementation, 15-20 min testing)

---

## Root Cause Analysis

### Architecture Background

**ConversationService Design** (src/services/conversation_service.py:140):
```python
class ConversationService:
    def __init__(self, ...):
        self._cache: Dict[str, CachedContext] = {}  # IN-MEMORY instance variable
        self._cache_ttl = timedelta(minutes=cache_ttl_minutes)
        # ...
```

**Key Design Decision**: ConversationService uses an in-memory cache to store conversation context per session. This cache is an **instance variable**, not a class variable or external store.

**Implication**: If you create multiple ConversationService instances, each has its own isolated cache. Sessions cached in Instance A are NOT visible to Instance B.

### What Went Wrong

**Before Factory Pattern** (working multi-turn):
```python
# Global singleton created once at module load
conversation_service = ConversationService()

# WebRTC handler used global singleton
class WebRTCVoiceHandler:
    async def handle(self):
        # Access global singleton - all connections share same cache
        context = await conversation_service.get_conversation_context(session_id)
```

**After Factory Pattern** (broken multi-turn):
```python
# src/api/server.py:525 - Global singleton created at startup
conversation_service = await create_conversation_service()

# src/voice/webrtc_handler.py:188 - NEW instance per connection ❌
class WebRTCVoiceHandler:
    async def _initialize_services(self):
        # Creates NEW instance with EMPTY cache
        self.conversation_service = await create_conversation_service()
```

**Timeline of Events**:
1. User connects via WebSocket → WebRTCVoiceHandler created
2. Handler calls `_initialize_services()` → NEW ConversationService created
3. User sends message → Cached in handler's private ConversationService instance
4. User disconnects → Handler destroyed, cache lost
5. User reconnects → NEW handler with NEW ConversationService with EMPTY cache
6. **Result**: Conversation history lost, multi-turn broken

**Evidence from Logs**:
```
# Database shows multi-turn conversations existed before factory pattern
⚠️ [DB_QUERY] Found 15 assistant messages in session 2e6c716a-e0ba-480c-b4a9-51af5f1fc1e9!
⚠️ [DB_QUERY] Found 10 assistant messages in session 7fa4de4b-f257-467a-bff8-777d7b5c1bb6!
⚠️ [DB_QUERY] Found 8 assistant messages in session afe7a61e-af45-449d-951d-3a975731c552!
```

These sessions show 8-15 exchanges worked BEFORE factory pattern changes.

### Why This Wasn't Caught

1. **Unit Tests**: Test ConversationService in isolation with mocked sessions
2. **Integration Tests**: Don't test multiple WebSocket reconnections
3. **Manual Testing Focus**: Tested MemoryService initialization, not multi-turn flow
4. **Factory Pattern Context**: Changes were framed as "initialization fix" not "service lifecycle change"

---

## Recommended Solution: Dependency Injection Pattern

### Architecture Decision

**Pattern**: Singleton with Dependency Injection (FastAPI Depends)

**Rationale**:
- ✅ **Modern Best Practice**: Matches 2024 FastAPI patterns (lifespan events + DI)
- ✅ **Web Research Validation**: Aligns with async service lifecycle research findings
- ✅ **Industry Standard**: Similar to Open WebUI, LangChain, LangGraph patterns
- ✅ **Testability**: Built-in dependency override support
- ✅ **Scalability**: Easy to add more singleton services
- ✅ **Minimal Changes**: Leverages existing global singleton (~25 lines)

**Alternatives Considered**:
1. **Service Registry Pattern**: More complex, overkill for 4 services
2. **FastAPI app.state**: Less explicit, harder to test
3. **Global imports**: Couples modules tightly, testing nightmare
4. **Revert factory pattern**: Loses MemoryService async initialization fix

### Implementation Steps

**Step 1: Add Dependency Provider** (src/api/server.py)
```python
def get_conversation_service() -> ConversationService:
    """
    Dependency injection provider for ConversationService singleton.

    Returns the global ConversationService instance initialized at startup.
    Raises RuntimeError if accessed before startup (safety check).

    Usage:
        @app.websocket("/ws/voice")
        async def endpoint(
            websocket: WebSocket,
            service: ConversationService = Depends(get_conversation_service)
        ):
            # service is the global singleton
    """
    if conversation_service is None:
        raise RuntimeError(
            "ConversationService not initialized. "
            "This indicates startup_services() was not called."
        )
    return conversation_service
```

**Step 2: Refactor WebSocket Endpoint** (src/api/server.py)
```python
@app.websocket("/ws/voice")
async def websocket_voice_endpoint(
    websocket: WebSocket,
    conv_service: ConversationService = Depends(get_conversation_service)  # ← NEW: Inject singleton
):
    """
    WebSocket endpoint for browser voice streaming (VoxBridge 2.0 Phase 4)

    CRITICAL: Uses dependency injection to receive the global ConversationService
    singleton. This ensures all WebSocket connections share the same conversation
    cache, enabling multi-turn conversations.
    """
    # Validate query params
    user_id = websocket.query_params.get('user_id')
    session_id_str = websocket.query_params.get('session_id')

    # ... existing validation code ...

    logger.info(f"✅ WebSocket voice connection established: user={user_id}, session={session_id}")

    # Create handler with injected singleton
    handler = WebRTCVoiceHandler(
        websocket=websocket,
        user_id=user_id,
        session_id=session_id,
        conversation_service=conv_service  # ← NEW: Pass injected singleton
    )
    await handler.start()
```

**Step 3: Update WebRTC Handler Constructor** (src/voice/webrtc_handler.py)
```python
class WebRTCVoiceHandler:
    """
    Handles WebRTC voice streaming from browser (VoxBridge 2.0 + Audio Fix)

    CRITICAL CHANGE: ConversationService is now INJECTED via dependency injection
    instead of being created per-handler. This ensures conversation cache persistence
    across WebSocket reconnections, enabling multi-turn conversations.
    """

    def __init__(
        self,
        websocket: WebSocket,
        user_id: str,
        session_id: UUID,
        conversation_service: ConversationService  # ← NEW: Inject singleton
    ):
        """
        Initialize WebRTC voice handler

        Args:
            websocket: FastAPI WebSocket connection
            user_id: User identifier (browser session ID)
            session_id: Active session ID for this conversation
            conversation_service: INJECTED ConversationService singleton (shared across all handlers)
        """
        self.websocket = websocket
        self.user_id = user_id
        self.session_id = str(session_id)
        self.is_active = True

        # CRITICAL: Use injected singleton instead of creating new instance
        self.conversation_service = conversation_service  # ← CHANGED: Accept injected singleton

        # Service instances (initialized async in _initialize_services)
        # ConversationService is now set above, others created in _initialize_services
        self.stt_service = None
        self.llm_service = None
        self.tts_service = None

        # ... rest of initialization unchanged ...
```

**Step 4: Refactor Service Initialization** (src/voice/webrtc_handler.py)
```python
    async def _initialize_services(self):
        """
        Initialize service instances (NON-singleton services only).

        CRITICAL CHANGE: ConversationService is NO LONGER created here.
        It's injected via constructor to ensure singleton pattern.

        Only per-handler services (STT, LLM, TTS) are created here.
        These services don't maintain state across requests, so per-instance is fine.
        """
        logger.info("🏭 Initializing per-handler services...")

        # ConversationService already injected in constructor - DO NOT create new instance
        # OLD CODE (REMOVED):
        # from src.services.factory import create_conversation_service
        # self.conversation_service = await create_conversation_service()

        # Create per-handler services (these are stateless or per-connection)
        self.stt_service = STTService(error_callback=self._handle_service_error)
        self.llm_service = LLMService(error_callback=self._handle_service_error)
        self.tts_service = TTSService(error_callback=self._handle_service_error)

        logger.info("✅ Per-handler services initialized successfully")
```

**Step 5: Update start() Method** (src/voice/webrtc_handler.py)
```python
    async def start(self):
        """
        Start handling audio stream

        Main loop:
        0. Initialize per-handler services (STT, LLM, TTS)
           NOTE: ConversationService already injected via constructor
        1. Accept WebSocket connection
        2. ConversationService already started at app startup (shared singleton)
        3. Connect to STTService
        4. Receive audio chunks
        5. Process transcripts
        6. Handle disconnection
        """
        try:
            logger.info(f"[START] Step 0: Initializing per-handler services...")
            # Initialize only per-handler services (ConversationService already injected)
            await self._initialize_services()
            logger.info(f"[START] ✅ Step 0 complete: Per-handler services initialized")

            # NOTE: ConversationService.start() already called at app startup
            # We're using the shared singleton, so no need to start it again
            logger.info(f"[START] ✅ Using global ConversationService singleton (already started)")

            logger.info(f"[START] Step 2: Validating session...")
            # ... rest of start() method unchanged ...
```

---

## Risks and Gotchas

### CRITICAL RISK 1: Breaking Change for Handler Instantiation

**Risk**: WebRTC handler signature changed - any code creating handlers manually will break.

**Impact**: Medium
**Probability**: Low (only websocket endpoint creates handlers)

**Affected Code**:
- `src/api/server.py:1389` - WebSocket endpoint (MUST update)
- Any test code creating WebRTCVoiceHandler instances (MUST update)

**Mitigation**:
```python
# OLD CODE (will break):
handler = WebRTCVoiceHandler(websocket, user_id, session_id)

# NEW CODE (required):
handler = WebRTCVoiceHandler(websocket, user_id, session_id, conversation_service)
```

**Detection**: Python will raise `TypeError: missing 1 required positional argument: 'conversation_service'`

**Fix**: Update all handler instantiations to pass `conversation_service` parameter.

### CRITICAL RISK 2: Startup Order Dependency

**Risk**: If WebSocket endpoint accessed BEFORE `startup_services()` completes, `conversation_service` will be None.

**Impact**: High (service crash)
**Probability**: Very Low (FastAPI guarantees startup event runs before accepting requests)

**Affected Code**:
- `src/api/server.py:get_conversation_service()` - Dependency provider

**Mitigation**:
```python
def get_conversation_service() -> ConversationService:
    if conversation_service is None:
        # Clear error message for debugging
        raise RuntimeError(
            "ConversationService not initialized. "
            "This indicates startup_services() was not called or failed. "
            "Check startup logs for initialization errors."
        )
    return conversation_service
```

**Detection**: RuntimeError with clear message on first WebSocket connection attempt

**Prevention**: FastAPI's `@app.on_event("startup")` runs BEFORE accepting HTTP/WebSocket connections

### RISK 3: Discord Plugin Inconsistency

**Risk**: Discord plugin still creates per-plugin ConversationService instances (src/plugins/discord_plugin.py:448), creating architectural inconsistency.

**Impact**: Low (Discord multi-turn still works because each plugin is long-lived)
**Probability**: High (Discord plugin not updated in this fix)

**Current State**:
- WebRTC: Uses global singleton (after this fix)
- Discord: Uses per-plugin instance (unchanged)

**Architectural Implications**:
- WebRTC conversation cache is GLOBAL (all browser users share)
- Discord conversation cache is PER-PLUGIN (each agent has isolated cache)

**Decision Required**: Should Discord plugin also use global singleton OR keep per-plugin instances?

**Recommendation**: Keep per-plugin instances for Discord, use singleton for WebRTC. Rationale:
- Discord plugins are long-lived (entire bot lifetime)
- WebRTC handlers are short-lived (per-connection)
- Per-plugin caching allows agent isolation
- Document architectural difference in CLAUDE.md

### RISK 4: Testing Requires Dependency Override

**Risk**: Existing tests that mock ConversationService may need updates to use FastAPI's dependency override system.

**Impact**: Medium (test suite may fail)
**Probability**: Medium (depends on test coverage)

**Affected Tests**:
- Any test creating WebRTCVoiceHandler directly
- Integration tests for `/ws/voice` endpoint

**Mitigation**:
```python
# Unit tests - pass mock directly
mock_service = Mock(spec=ConversationService)
handler = WebRTCVoiceHandler(mock_ws, "user1", uuid4(), mock_service)

# Integration tests - override dependency
from src.api.server import app, get_conversation_service

app.dependency_overrides[get_conversation_service] = lambda: mock_service
async with TestClient(app) as client:
    async with client.websocket_connect("/ws/voice?user_id=test&session_id=...") as ws:
        # Test code here
```

**Detection**: Test failures with `TypeError: missing 1 required positional argument`

### RISK 5: Memory Service Still Uses Factory Pattern

**Risk**: ConversationService singleton has MemoryService, but MemoryService initialization still uses async factory at startup.

**Impact**: None (this is intentional and correct)
**Probability**: N/A (architectural decision)

**Why This is Correct**:
- MemoryService requires async database config fetch (`await get_global_embedding_config()`)
- Cannot use `asyncio.run()` during app startup (event loop already running)
- Factory pattern solves this: `memory_service = await create_conversation_service()`
- ConversationService receives initialized MemoryService via dependency injection

**Flow**:
1. App startup → Event loop running
2. Call `conversation_service = await create_conversation_service()`
3. Factory fetches DB config: `db_config = await get_global_embedding_config()`
4. Factory creates MemoryService: `memory_service = MemoryService(db_config)`
5. Factory creates ConversationService: `ConversationService(memory_service=memory_service)`
6. Global singleton stored: `conversation_service = ...`
7. WebSocket connections inject singleton: `Depends(get_conversation_service)`

**Conclusion**: Factory pattern + dependency injection work together harmoniously.

### RISK 6: Conversation Cache Size Unbounded

**Risk**: Global singleton means ALL WebRTC sessions share ONE cache. Heavy usage could exhaust memory.

**Impact**: Medium (memory leak potential)
**Probability**: Low (15-minute TTL + cleanup task mitigates)

**Current Mitigation**:
- Cache TTL: 15 minutes (configurable via `CONVERSATION_CACHE_TTL_MINUTES`)
- Background cleanup task: Runs every 5 minutes
- Max context messages: 20 per session (limits cache entry size)

**Monitoring**:
```python
# Add metrics endpoint to track cache size
@app.get("/api/metrics/conversation-cache")
async def get_cache_metrics(service: ConversationService = Depends(get_conversation_service)):
    return {
        "active_sessions": len(service._cache),
        "cache_ttl_minutes": service._cache_ttl.total_seconds() / 60,
        "max_context_messages": service._max_context
    }
```

**Future Enhancement**: Add cache size limits (e.g., max 1000 sessions, LRU eviction)

### GOTCHA 1: FastAPI Depends() Only Works in Route Functions

**Issue**: `Depends()` only works in FastAPI route functions (HTTP endpoints, WebSocket endpoints). Cannot use in regular Python functions.

**Example**:
```python
# ✅ WORKS - Route function
@app.websocket("/ws/voice")
async def endpoint(service: ConversationService = Depends(get_conversation_service)):
    pass

# ❌ FAILS - Regular function
async def helper_function(service: ConversationService = Depends(get_conversation_service)):
    pass  # Depends() has no effect here
```

**Workaround**: Pass dependency as regular parameter from route to helper:
```python
@app.websocket("/ws/voice")
async def endpoint(service: ConversationService = Depends(get_conversation_service)):
    await helper_function(service)  # Pass explicitly

async def helper_function(service: ConversationService):  # Regular parameter
    # Use service
```

### GOTCHA 2: Global Variable Must Be Declared at Module Level

**Issue**: `conversation_service` must be declared as global at module level for dependency provider to access it.

**Current Code** (src/api/server.py):
```python
# Module-level globals (accessible to dependency providers)
conversation_service: Optional[ConversationService] = None
memory_service: Optional[MemoryService] = None
plugin_manager = PluginManager()

# Dependency provider can access globals
def get_conversation_service() -> ConversationService:
    if conversation_service is None:  # ← Accesses module-level global
        raise RuntimeError("Not initialized")
    return conversation_service
```

**Anti-Pattern** (would NOT work):
```python
# ❌ Would NOT work - variable scoped to function
@app.on_event("startup")
async def startup_services():
    conversation_service = await create_conversation_service()  # Local variable
    # Provider cannot access this

def get_conversation_service() -> ConversationService:
    return conversation_service  # ← NameError: 'conversation_service' is not defined
```

**Fix**: Use `global` keyword in startup function:
```python
@app.on_event("startup")
async def startup_services():
    global conversation_service  # ← Declare we're modifying module-level global
    conversation_service = await create_conversation_service()
```

### GOTCHA 3: Type Hints Must Match Exactly

**Issue**: Dependency provider return type MUST match the type hint in route function parameter.

**Example**:
```python
# Provider return type
def get_conversation_service() -> ConversationService:  # ← Must match
    return conversation_service

# Route parameter type hint
async def endpoint(
    service: ConversationService = Depends(get_conversation_service)  # ← Must match
):
    pass
```

**Common Mistake**:
```python
# ❌ Provider returns Optional
def get_conversation_service() -> Optional[ConversationService]:
    return conversation_service

# ✅ Route expects non-Optional
async def endpoint(
    service: ConversationService = Depends(get_conversation_service)  # Type mismatch
):
    pass
```

**Fix**: Provider should return non-Optional and raise exception if None:
```python
def get_conversation_service() -> ConversationService:  # Non-Optional
    if conversation_service is None:
        raise RuntimeError("Not initialized")
    return conversation_service  # Guaranteed non-None
```

---

## Testing Strategy

### Unit Tests

**Test 1: Dependency Provider Validates Initialization**
```python
def test_get_conversation_service_before_startup():
    """Test that provider raises error if accessed before startup"""
    # Reset global
    import src.api.server as server
    server.conversation_service = None

    with pytest.raises(RuntimeError, match="not initialized"):
        server.get_conversation_service()
```

**Test 2: Handler Uses Injected Service**
```python
async def test_webrtc_handler_uses_injected_service():
    """Test that handler uses the injected ConversationService instance"""
    mock_service = Mock(spec=ConversationService)
    mock_websocket = Mock(spec=WebSocket)

    handler = WebRTCVoiceHandler(
        websocket=mock_websocket,
        user_id="test_user",
        session_id=uuid4(),
        conversation_service=mock_service
    )

    # Verify handler is using the injected instance
    assert handler.conversation_service is mock_service
    assert handler.conversation_service is not None
```

**Test 3: Service Initialization Skip**
```python
async def test_initialize_services_skips_conversation_service():
    """Test that _initialize_services no longer creates ConversationService"""
    mock_service = Mock(spec=ConversationService)
    mock_websocket = Mock(spec=WebSocket)

    handler = WebRTCVoiceHandler(
        websocket=mock_websocket,
        user_id="test_user",
        session_id=uuid4(),
        conversation_service=mock_service
    )

    # Store reference to verify it doesn't change
    original_service = handler.conversation_service

    await handler._initialize_services()

    # Verify ConversationService wasn't replaced
    assert handler.conversation_service is original_service

    # Verify other services were initialized
    assert handler.stt_service is not None
    assert handler.llm_service is not None
    assert handler.tts_service is not None
```

### Integration Tests

**Test 4: Multi-Turn Conversation Persistence**
```python
@pytest.mark.integration
async def test_multi_turn_conversation_via_webrtc():
    """
    Test that conversation history persists across multiple exchanges
    in the same WebSocket connection.

    This is the CRITICAL test that validates the singleton pattern fix.
    """
    from src.api.server import app
    from fastapi.testclient import TestClient

    # Create test session
    session_id = uuid4()
    user_id = "test_user"

    async with TestClient(app) as client:
        # Connect via WebSocket
        ws_url = f"/ws/voice?session_id={session_id}&user_id={user_id}"
        async with client.websocket_connect(ws_url) as websocket:

            # Turn 1: Send first message
            await websocket.send_bytes(audio_chunk_1)

            # Receive transcript + AI response
            event_1 = await websocket.receive_json()
            assert event_1["event"] == "final_transcript"

            response_1 = await websocket.receive_json()
            assert response_1["event"] == "ai_response_chunk"

            # Turn 2: Send second message (should have context from Turn 1)
            await websocket.send_bytes(audio_chunk_2)

            event_2 = await websocket.receive_json()
            assert event_2["event"] == "final_transcript"

            response_2 = await websocket.receive_json()
            assert response_2["event"] == "ai_response_chunk"

            # CRITICAL: Verify agent's response references previous context
            # This proves conversation history was maintained
            response_text = response_2["data"]["text"].lower()
            assert any(keyword in response_text for keyword in [
                "you mentioned", "you said", "earlier", "before", "previous"
            ]), "Agent should reference previous conversation turn"
```

**Test 5: Cross-Connection Session Isolation**
```python
@pytest.mark.integration
async def test_session_isolation_across_connections():
    """
    Test that different sessions are properly isolated even when using
    the same global ConversationService singleton.

    This validates that the singleton pattern doesn't leak context
    between unrelated sessions.
    """
    from src.api.server import app
    from fastapi.testclient import TestClient

    session_1 = uuid4()
    session_2 = uuid4()
    user_id = "test_user"

    async with TestClient(app) as client:
        # Connection 1: Session 1
        ws_url_1 = f"/ws/voice?session_id={session_1}&user_id={user_id}"
        async with client.websocket_connect(ws_url_1) as ws1:
            await ws1.send_bytes(audio_chunk_secret)
            event_1 = await ws1.receive_json()
            # Session 1 has "secret" message

        # Connection 2: Session 2 (different session, same singleton)
        ws_url_2 = f"/ws/voice?session_id={session_2}&user_id={user_id}"
        async with client.websocket_connect(ws_url_2) as ws2:
            await ws2.send_bytes(audio_chunk_normal)
            event_2 = await ws2.receive_json()

            # CRITICAL: Session 2 should NOT see Session 1's "secret"
            response_text = event_2["data"]["text"].lower()
            assert "secret" not in response_text, \
                "Session isolation failed - leaked context from different session"
```

### Manual Testing Checklist

- [ ] **Test 1: Single-Turn Conversation**
  - Connect to `/ws/voice` via browser
  - Send audio message
  - Verify AI response received

- [ ] **Test 2: Multi-Turn Conversation (CRITICAL)**
  - Stay connected after Test 1
  - Send second audio message
  - Verify AI response references first message
  - Example: "What's my favorite color?" → "Blue" → "What did I just say?" → "You said your favorite color is blue"

- [ ] **Test 3: Memory Access**
  - Create user fact: "My favorite food is pizza"
  - Ask agent: "What's my favorite food?"
  - Verify agent responds with "pizza" (memory retrieval works)

- [ ] **Test 4: Disconnect and Reconnect**
  - Complete Test 2 (multi-turn conversation)
  - Disconnect WebSocket
  - Reconnect with SAME session_id
  - Send new message
  - Verify conversation history maintained (can reference earlier turns)

- [ ] **Test 5: Different Session Isolation**
  - Create session A, have conversation
  - Create session B (different session_id)
  - Verify session B does NOT see session A's history

- [ ] **Test 6: Cache Cleanup**
  - Wait 15+ minutes after Test 2
  - Verify cache entry expired (check metrics endpoint)
  - Reconnect - should load from database instead of cache

---

## Rollback Plan

### Option 1: Immediate Rollback (Safest)

**When to Use**: Critical production issue, multi-turn AND memory both broken

**Steps**:
```bash
# Revert to before factory pattern
git revert HEAD~7..HEAD  # Revert last 7 commits (factory pattern changes)
docker compose restart voxbridge-api

# OR checkout specific commit
git checkout <commit-hash-before-factory>
docker compose restart voxbridge-api
```

**Impact**: Loses MemoryService async initialization fix, reverts to old event loop conflict

### Option 2: Partial Rollback (Medium Risk)

**When to Use**: Dependency injection breaks, but want to keep factory pattern for MemoryService

**Steps**:
```bash
# Revert only dependency injection changes
git revert <dependency-injection-commit>
docker compose restart voxbridge-api
```

**Impact**: Multi-turn still broken, but memory access preserved

### Option 3: Forward Fix (Lowest Risk)

**When to Use**: Dependency injection works but has bugs

**Steps**:
1. Add debug logging to track service instances
2. Verify singleton is being used correctly
3. Check startup order
4. Fix bugs in place

**Debugging**:
```python
# Add to WebRTCVoiceHandler.__init__
logger.info(f"🔍 DEBUG: ConversationService instance ID: {id(conversation_service)}")

# Add to dependency provider
logger.info(f"🔍 DEBUG: Injecting ConversationService instance ID: {id(conversation_service)}")

# Compare IDs - should match if singleton pattern working
```

---

## Success Criteria

### Functional Requirements

- ✅ **Multi-Turn Conversations**: User can have 2+ exchanges with agent in same session
- ✅ **Memory Access**: Agents can retrieve user facts during conversations
- ✅ **Session Isolation**: Different sessions don't leak context
- ✅ **Cache Persistence**: Conversation history survives WebSocket reconnections
- ✅ **Startup Safety**: Service fails fast if accessed before initialization

### Non-Functional Requirements

- ✅ **Performance**: No latency regression (singleton is faster than new instances)
- ✅ **Memory**: Cache cleanup prevents unbounded growth
- ✅ **Testability**: Dependency override works in tests
- ✅ **Maintainability**: Clear dependency chain, no hidden globals
- ✅ **Scalability**: Pattern extends to future singleton services

### Validation Tests

```bash
# 1. Run unit tests
./test.sh tests/unit/test_webrtc_handler.py -v

# 2. Run integration tests
./test.sh tests/integration/test_webrtc_multiturn.py -v

# 3. Manual browser test (multi-turn)
# - Open http://localhost:4903
# - Select "Yui" agent
# - Start voice chat
# - Say "My name is Alice"
# - Agent responds
# - Say "What's my name?"
# - Agent should say "Alice" (proves multi-turn works)

# 4. Check logs for singleton confirmation
docker logs voxbridge-api | grep "ConversationService instance ID"
# Should see SAME ID across multiple WebSocket connections
```

---

## Documentation Updates

### Files to Update

1. **CLAUDE.md** - Add singleton pattern to "Modification Patterns" section
2. **ARCHITECTURE.md** - Document WebRTC vs Discord service lifecycle differences
3. **tests/README.md** - Add dependency override examples
4. **src/api/server.py** - Inline comments explaining dependency provider
5. **src/voice/webrtc_handler.py** - Docstring explaining injection pattern

### Key Points to Document

- **Why Singleton**: Conversation cache must persist across connections
- **Why Not Singleton for Discord**: Per-plugin instances allow agent isolation
- **Testing Pattern**: How to override dependencies in tests
- **Startup Order**: ConversationService must initialize before WebSocket accepts connections
- **Future Services**: Template for adding more singleton services

---

## Future Considerations

### Potential Enhancements

1. **Cache Size Monitoring**
   - Add Prometheus metrics for cache size
   - Alert if cache exceeds 1000 sessions
   - Dashboard showing active sessions by agent

2. **Cache Persistence** (Optional)
   - Save cache to Redis on shutdown
   - Restore cache on startup
   - Enables zero-downtime deployments

3. **Service Registry Pattern** (If Needed)
   - Implement if service count grows beyond 10
   - Centralized dependency management
   - Dynamic service discovery

4. **Health Checks**
   - Add `/health/services` endpoint
   - Check ConversationService singleton exists
   - Verify cache cleanup task running
   - Monitor memory usage

### Migration Path for Discord Plugin

**Decision Point**: Should Discord plugin also use singleton?

**Current State**: Per-plugin instances (each agent has own ConversationService)

**Option A: Keep Per-Plugin** (Recommended)
- ✅ Agent isolation (each agent's conversations cached separately)
- ✅ No architectural changes needed
- ⚠️ Inconsistent with WebRTC pattern

**Option B: Migrate to Singleton**
- ✅ Consistent architecture
- ❌ Breaks agent isolation
- ❌ All Discord agents share same cache

**Recommendation**: Keep per-plugin for Discord, document architectural difference:

```markdown
## Service Lifecycle Patterns

VoxBridge uses TWO different service lifecycle patterns:

1. **WebRTC (Global Singleton)**:
   - ONE ConversationService for ALL browser users
   - Conversation cache is GLOBAL
   - Rationale: Handlers are short-lived (per-connection)

2. **Discord (Per-Plugin Instance)**:
   - ONE ConversationService PER agent
   - Conversation cache is PER-AGENT
   - Rationale: Plugins are long-lived (entire bot lifetime)
```

---

## Conclusion

**Status**: Ready for implementation

**Confidence**: High (well-researched, industry-validated pattern)

**Risk**: Low-Medium (breaking change for handler signature, but contained)

**Recommendation**: Proceed with implementation following steps 1-6, then test thoroughly using manual checklist.

**Next Steps**:
1. Review this document with team
2. Get approval to proceed
3. Implement changes in order
4. Run test suite
5. Manual validation
6. Commit with descriptive message
7. Update documentation

---

## References

### Web Research

- **FastAPI Dependency Injection**: https://fastapi.tiangolo.com/tutorial/dependencies/
- **FastAPI Lifespan Events**: https://fastapi.tiangolo.com/advanced/events/
- **Async Service Patterns**: https://www.elastic.co/blog/async-patterns-building-python-service
- **Singleton in AIO-HTTP**: https://blog.davidvassallo.me/2020/04/02/singleton-patterns-in-pythons-aio-http/
- **Python Dependency Injector**: https://python-dependency-injector.ets-labs.org/

### Internal Documentation

- **Factory Pattern Implementation**: `docs/planning/memory-access-factory-pattern.md`
- **WebRTC Handler**: `src/voice/webrtc_handler.py`
- **API Server**: `src/api/server.py`
- **ConversationService**: `src/services/conversation_service.py`

### Related Issues

- **Issue**: Multi-turn conversations broken
- **Root Cause**: Per-connection service instantiation
- **Previous Fix**: Factory pattern for MemoryService (preserved in this solution)

---

**Document Version**: 1.0
**Author**: VoxBridge Team + Claude Code
**Last Updated**: 2025-11-26
