# Testing and Logging Strategy
## VoxBridge Frontend - Conversation Area Troubleshooting Guide

**Last Updated:** November 20, 2025
**Purpose:** Comprehensive guide for troubleshooting conversation flow bugs using tests and logs

---

## Table of Contents

1. [Test Coverage Overview](#test-coverage-overview)
2. [Logging Architecture](#logging-architecture)
3. [Troubleshooting Common Issues](#troubleshooting-common-issues)
4. [Test Execution Guide](#test-execution-guide)
5. [Log Analysis Patterns](#log-analysis-patterns)
6. [Adding New Tests](#adding-new-tests)
7. [Adding New Logs](#adding-new-logs)

---

## 1. Test Coverage Overview

### **Integration Tests** (`src/pages/__tests__/VoxbridgePage.test.tsx`)

✅ **All 5 tests passing** (100% success rate)

| Test # | Test Name | What It Tests | Coverage |
|--------|-----------|---------------|----------|
| 1 | `should render AI response without page refresh` | Basic WebSocket → React Query → UI flow | Session selection, message loading, AI response streaming, database sync |
| 2 | `should display streaming AI response chunks correctly` | Streaming chunk aggregation and display | Chunk-by-chunk streaming, visual indicators, streaming → DB transition |
| 3 | `should handle race condition between cache update and database refetch` | Race condition handling | Rapid event sequence, debounced invalidation, no duplicates |
| 4 | `should smoothly transition from streaming to database message` | Optimistic → database transition | Streaming chunks cleared on DB save, seamless UI transition |
| 5 | `should handle service error events gracefully` | Error handling and recovery | Error display, system recovery, continued functionality |

### **Test Architecture**

```
VoxbridgePage.test.tsx (Integration Tests)
├─► WebSocketMock (src/__tests__/mocks/WebSocketMock.ts)
│   └─► Simulates backend WebSocket events
├─► React Testing Library (renderWithProviders)
│   └─► Full React + React Query + Router setup
└─► Vitest (test runner)
    └─► Fast, parallel execution
```

### **Test Coverage Gaps (Future Work)**

- [ ] Discord voice connection flow (join/leave channel)
- [ ] TTS audio playback lifecycle
- [ ] Session switching mid-conversation
- [ ] WebSocket reconnection handling
- [ ] Error recovery after LLM timeout
- [ ] Multiple rapid user inputs (stress test)
- [ ] Network latency simulation

---

## 2. Logging Architecture

### **Tiered Logging System** (`src/utils/logger.ts`)

VoxBridge uses a 5-level logging system:

| Level | Priority | Use Case | Example |
|-------|----------|----------|---------|
| **TRACE** | 0 (Lowest) | Raw data dumps, every loop iteration | Audio chunk contents, WebSocket raw frames |
| **DEBUG** | 1 | State changes, checkpoints, detailed flow | "setStreamingChunks updated", "Query invalidated" |
| **INFO** | 2 (Default) | Important operational events | "Connected to WebSocket", "Session selected" |
| **WARN** | 3 | Recoverable errors, fallbacks | "Reconnecting after disconnect", "Missing optional field" |
| **ERROR** | 4 (Highest) | Failures, exceptions | "WebSocket connection failed", "LLM timeout" |

### **Environment Variables**

Set in `frontend/.env` to control log verbosity:

```bash
# Global log level (applies to all modules)
VITE_LOG_LEVEL=INFO

# Module-specific overrides
VITE_LOG_LEVEL_WEBRTC=DEBUG    # WebRTC audio hook
VITE_LOG_LEVEL_WEBSOCKET=DEBUG # WebSocket connections
VITE_LOG_LEVEL_UI=INFO         # UI components (VoxbridgePage)
VITE_LOG_LEVEL_API=WARN        # API client
```

**Production Recommendation:** `INFO` (default)
**Development Recommendation:** `DEBUG` for active modules
**Troubleshooting Recommendation:** `TRACE` for specific module

### **Log Categories (Emoji Prefixes)**

Logs use emoji prefixes for easy filtering:

| Emoji | Category | Log Filter Command |
|-------|----------|-------------------|
| 🎤 | Listening (STT) | `grep "🎤" logs.txt` |
| 💭 | AI Thinking | `grep "💭" logs.txt` |
| 🌊 | Streaming (LLM) | `grep "🌊" logs.txt` |
| 📡 | WebSocket Events | `grep "📡" logs.txt` |
| 🔄 | React Query Invalidation | `grep "🔄" logs.txt` |
| 💾 | Database Operations | `grep "💾" logs.txt` |
| 🧹 | Cleanup Operations | `grep "🧹" logs.txt` |
| 📦 | Cache Updates | `grep "📦" logs.txt` |
| 📝 | Pending Messages | `grep "📝" logs.txt` |
| 🏁 | Event Completion | `grep "🏁" logs.txt` |
| ✅ | Success | `grep "✅" logs.txt` |
| ⚠️ | Warnings | `grep "⚠️" logs.txt` |
| 🚨 | Critical Errors | `grep "🚨" logs.txt` |

### **Correlation IDs**

All conversation turns include correlation IDs for tracing:

```javascript
// Example log with correlation ID:
🌊 [STREAMING_AI] Adding chunk to streamingChunks {
  correlationId: "abc-123",
  chunkText: "Hello! How can I help?",
  timestamp: 1700000000000
}
```

**Filter logs by correlation ID:**
```bash
grep "abc-123" logs.txt
```

---

## 3. Troubleshooting Common Issues

### **Issue #1: Speech Bubble Not Appearing**

**Symptoms:**
- User speaks, but no speech bubble shows up
- Or: AI response doesn't appear after user speaks

**Debug Steps:**

1. **Check WebSocket connection:**
   ```bash
   grep "📡.*WS EVENT" logs.txt | tail -20
   ```
   Should see: `partial_transcript`, `final_transcript`, `ai_response_chunk` events

2. **Check if session is selected:**
   ```bash
   grep "activeSessionId" logs.txt | tail -5
   ```
   Should NOT be `null`

3. **Check React Query invalidation:**
   ```bash
   grep "🔄.*QUERY" logs.txt | tail -10
   ```
   Should see invalidation after `message_saved` events

4. **Check for stale closure bug:**
   ```bash
   grep "activeSessionId" logs.txt | grep "null"
   ```
   If you see `activeSessionId: null` when events arrive, stale closure bug!

**Common Causes:**
- No session selected (`activeSessionId = null`)
- WebSocket disconnected
- Stale closure in `handleMessage` callback
- React Query not invalidating

---

### **Issue #2: Duplicate Speech Bubbles**

**Symptoms:**
- Two identical messages appear (streaming + database)
- Speech bubble flickers or remounts

**Debug Steps:**

1. **Check streaming cleanup:**
   ```bash
   grep "🧹.*STREAMING_CLEANUP" logs.txt
   ```
   Should see cleanup logs after `message_saved` events

2. **Check React keys:**
   Open browser DevTools → React Components → inspect message elements
   - Keys should be stable: `user-pending` → `user-123`
   - Keys should NOT change mid-transition

3. **Check message_saved timing:**
   ```bash
   grep -A 2 "message_saved" logs.txt | grep "streamingChunks"
   ```
   Chunks should be cleared BEFORE query refetch

**Common Causes:**
- `streamingChunks` not cleared in `message_saved` handler
- React keys changing (causing remount)
- Race condition: refetch happens before cleanup

---

### **Issue #3: Messages Not Updating (Stale Data)**

**Symptoms:**
- New messages arrive via WebSocket but don't appear in UI
- Have to refresh page to see new messages

**Debug Steps:**

1. **Check query invalidation:**
   ```bash
   grep "debouncedInvalidateQueries" logs.txt | tail -10
   ```
   Should see invalidation calls after `message_saved` events

2. **Check React Query cache:**
   Open browser DevTools → React Query DevTools
   - Check `['messages', sessionId]` query
   - Verify `dataUpdatedAt` timestamp changes

3. **Check debounce timing:**
   ```bash
   grep "🔄" logs.txt | tail -20
   ```
   Should see invalidation within 100ms of `message_saved`

**Common Causes:**
- Debounce clearing invalidation calls
- activeSessionId doesn't match message session_id
- React Query cache not updating

---

### **Issue #4: AI Response Stuck in "Thinking" State**

**Symptoms:**
- 💭 "AI is thinking..." indicator never stops
- No AI response appears

**Debug Steps:**

1. **Check for ai_response_complete event:**
   ```bash
   grep "ai_response_complete" logs.txt | tail -5
   ```
   Should see event within 5-10 seconds of final_transcript

2. **Check LLM timeout:**
   ```bash
   grep "LLM_TIMEOUT" logs.txt
   ```
   If present, backend LLM request timed out (>120s)

3. **Check service errors:**
   ```bash
   grep "service_error" logs.txt | tail -10
   ```
   May show LLM provider failures

**Common Causes:**
- Backend LLM timeout (>120s)
- LLM provider API failure
- Missing `ai_response_complete` handler
- `setIsVoiceAIGenerating(false)` not called

---

### **Issue #5: Streaming Chunks Not Appearing**

**Symptoms:**
- AI response appears all at once (not streaming)
- Or: Chunks arrive but don't display

**Debug Steps:**

1. **Check chunk events:**
   ```bash
   grep "🌊.*STREAMING_AI" logs.txt
   ```
   Should see multiple chunk logs with increasing text length

2. **Check streaming state:**
   ```bash
   grep "setIsStreaming" logs.txt
   ```
   Should be `setIsStreaming(true)` when chunks arrive

3. **Check Discord handler:**
   ```bash
   grep "ai_response_chunk.*Discord" logs.txt
   ```
   Discord handler should process chunks (not skip them)

**Common Causes:**
- Discord `handleMessage` not processing `ai_response_chunk` events
- `setStreamingChunks` not called
- `displayMessages` not including streaming message

---

## 4. Test Execution Guide

### **Run All Integration Tests**

```bash
cd /home/wiley/Docker/voxbridge/frontend
npm test -- VoxbridgePage.test.tsx --run
```

**Expected Output:**
```
✓ VoxbridgePage (5 tests) 1651ms
  ✓ should render AI response without page refresh 381ms
  ✓ should display streaming AI response chunks correctly 315ms
  ✓ should handle race condition between cache update and database refetch 378ms
  ✓ should smoothly transition from streaming to database message
  ✓ should handle service error events gracefully

Test Files  1 passed (1)
     Tests  5 passed (5)
```

### **Run Specific Test**

```bash
npm test -- VoxbridgePage.test.tsx -t "should render AI response"
```

### **Run Tests with Coverage**

```bash
npm test -- VoxbridgePage.test.tsx --coverage
```

### **Watch Mode (Re-run on Changes)**

```bash
npm test -- VoxbridgePage.test.tsx
```

---

## 5. Log Analysis Patterns

### **Normal Conversation Turn (Complete Flow)**

Expected log sequence for one conversation turn:

```
1. User starts speaking:
   🎤 LISTENING (WebRTC) Started (partial: "Hello...")

2. Partial transcripts stream:
   📝 [PENDING_USER] Setting pendingUserTranscript (partial)

3. User stops speaking:
   🎤 LISTENING (WebRTC) Stopped (final: "Hello")
   📝 [PENDING_USER] Setting pendingUserTranscript (final)

4. Backend saves user message:
   💾 [DB_CONFIRMED] Received message_saved event
   🔄 [QUERY] Invalidating messages query

5. DB refetch completes:
   📦 [CACHE_UPDATED] Cache reflected new data
   🧹 [AUTO_CLEAR] DB message loaded - clearing pendingUserTranscript

6. AI starts generating:
   💭 THINKING (WebRTC) Started (session: session-456)

7. AI streams response:
   🌊 [STREAMING_AI] Adding chunk to streamingChunks
   🌊 [STREAMING_AI] Updated streamingChunks (totalChunks: 1)
   🌊 [STREAMING_AI] Adding chunk to streamingChunks
   🌊 [STREAMING_AI] Updated streamingChunks (totalChunks: 2)

8. AI completes:
   🏁 [AI_COMPLETE] Starting ai_response_complete handler
   💭 THINKING (WebRTC) Complete (duration: 2340ms)

9. Backend saves AI message:
   💾 [DB_CONFIRMED] Received message_saved event
   🧹 [STREAMING_CLEANUP] Clearing streaming chunks
   🔄 [QUERY] Invalidating messages query

10. DB refetch completes:
    📦 [CACHE_UPDATED] Cache reflected new data

TOTAL TIME: ~6-10 seconds per turn
```

### **Error Pattern: Stale Closure Bug**

```
❌ BAD PATTERN:
📡 WS EVENT partial_transcript { sessionId: "session-456" }
  handleMessage called with activeSessionId: null  ← STALE!
  ⚠️ Skipping cache update (no activeSessionId)

✅ GOOD PATTERN:
📡 WS EVENT partial_transcript { sessionId: "session-456" }
  handleMessage called with activeSessionId: "session-456"  ← CORRECT!
  ✅ Processing message for session-456
```

### **Error Pattern: Race Condition (Duplicates)**

```
❌ BAD PATTERN:
🌊 [STREAMING_AI] Updated streamingChunks (totalChunks: 3)
💾 [DB_CONFIRMED] Received message_saved
🔄 [QUERY] Invalidating messages query  ← Refetch happens FIRST
📦 [CACHE_UPDATED] Cache reflected new data
🧹 [STREAMING_CLEANUP] Clearing chunks  ← Cleanup happens SECOND
Result: Both streaming + DB message visible briefly

✅ GOOD PATTERN:
🌊 [STREAMING_AI] Updated streamingChunks (totalChunks: 3)
💾 [DB_CONFIRMED] Received message_saved
🧹 [STREAMING_CLEANUP] Clearing chunks  ← Cleanup happens FIRST
🔄 [QUERY] Invalidating messages query  ← Refetch happens SECOND
📦 [CACHE_UPDATED] Cache reflected new data
Result: Seamless transition, no duplicates
```

---

## 6. Adding New Tests

### **Test Template**

```typescript
it('should [describe behavior]', async () => {
  const user = userEvent.setup();
  renderWithProviders();

  // Wait for sessions to load
  await waitFor(() => {
    expect(api.getSessions).toHaveBeenCalled();
  });

  // Select the session
  const sessionElements = await screen.findAllByText('Test Session');
  await user.click(sessionElements[0]);

  // Wait for messages to load
  await waitFor(() => {
    expect(api.getSessionMessages).toHaveBeenCalledWith('session-456');
  });

  // YOUR TEST LOGIC HERE

  // Example: Emit WebSocket event
  await act(async () => {
    mockWebSocket.emitPartialTranscript('Test text');
  });

  // Example: Wait for UI update
  await waitFor(() => {
    expect(screen.getByText('Test text')).toBeInTheDocument();
  });
});
```

### **Best Practices**

1. **Always wrap WebSocket events in `act()`:**
   ```typescript
   await act(async () => {
     mockWebSocket.emitAIResponseChunk('chunk');
   });
   ```

2. **Use 200ms wait after message_saved (accounts for 100ms debounce):**
   ```typescript
   await act(async () => {
     mockWebSocket.emitMessageSaved('1', 'session-456', 'user');
     await new Promise(resolve => setTimeout(resolve, 200));
   });
   ```

3. **Update mocks BEFORE emitting message_saved:**
   ```typescript
   vi.mocked(api.getSessionMessages).mockResolvedValue(updatedMessages);
   await act(async () => {
     mockWebSocket.emitMessageSaved(...);
   });
   ```

4. **Use stable assertions (avoid flakiness):**
   ```typescript
   // ❌ BAD: Sensitive to timing
   expect(screen.getByText('Loading...')).not.toBeInTheDocument();

   // ✅ GOOD: Wait for expected state
   await waitFor(() => {
     expect(screen.getByText('Message')).toBeInTheDocument();
   });
   ```

---

## 7. Adding New Logs

### **When to Add Logs**

Add logs at these critical points:

1. **State Transitions:**
   ```typescript
   logger.debug('🎤 LISTENING Started', { sessionId });
   logger.debug('💭 THINKING Started', { sessionId });
   logger.debug('🔊 SPEAKING Started', { messageId });
   ```

2. **External Events:**
   ```typescript
   logger.debug('📡 WS EVENT', message.event, {
     sessionId: message.data.session_id
   });
   ```

3. **Cache Operations:**
   ```typescript
   logger.debug('🔄 QUERY Invalidating messages query', {
     sessionId,
     reason: 'message_saved'
   });
   ```

4. **Data Mutations:**
   ```typescript
   logger.debug('🌊 [STREAMING_AI] Adding chunk', {
     chunkLength: text.length,
     totalChunks: streamingChunks.length + 1
   });
   ```

5. **Error Conditions:**
   ```typescript
   logger.error('🚨 [LLM_TIMEOUT] AI generating for >120s', {
     elapsed,
     sessionId
   });
   ```

### **Log Format Guidelines**

```typescript
// Structure:
logger.level('EMOJI [CATEGORY] Action', { context })

// Examples:
logger.debug('🎤 [STT] Started listening', { sessionId, timestamp })
logger.info('✅ [CACHE] Updated with 5 new messages', { count: 5 })
logger.warn('⚠️ [RECONNECT] Attempting reconnect (3/5)', { attempt: 3 })
logger.error('🚨 [TIMEOUT] LLM timeout after 125s', { duration: 125000 })
```

### **Context Object Best Practices**

```typescript
// ✅ GOOD: Include key identifiers
logger.debug('Processing message', {
  sessionId: activeSessionId,
  messageId: message.id,
  correlationId: message.data.correlation_id,
  timestamp: Date.now()
});

// ❌ BAD: Missing context
logger.debug('Processing message');

// ✅ GOOD: Truncate long strings
logger.debug('Chunk received', {
  text: chunk.substring(0, 50) + '...',
  length: chunk.length
});

// ❌ BAD: Log entire message (spam)
logger.debug('Chunk received', { fullText: veryLongString });
```

---

## 8. Quick Reference Commands

### **Test Commands**
```bash
# Run all tests
npm test -- VoxbridgePage.test.tsx --run

# Run single test
npm test -- VoxbridgePage.test.tsx -t "streaming"

# Watch mode
npm test -- VoxbridgePage.test.tsx
```

### **Log Filtering**
```bash
# View conversation flow logs
grep -E "🎤|💭|🌊|🔊" logs.txt

# View WebSocket events
grep "📡" logs.txt

# View cache operations
grep -E "🔄|📦|💾" logs.txt

# View errors only
grep "🚨\|ERROR" logs.txt

# Follow specific correlation ID
grep "abc-123" logs.txt
```

### **Environment Variables**
```bash
# Enable debug logs for WebRTC
export VITE_LOG_LEVEL_WEBRTC=DEBUG
npm run dev

# Enable debug logs globally
export VITE_LOG_LEVEL=DEBUG
npm run dev
```

---

## Summary

This guide provides comprehensive troubleshooting tools:

✅ **5 Integration Tests** covering core conversation flows
✅ **88+ Logging Statements** with emoji-based categorization
✅ **5 Log Levels** (TRACE → ERROR) for granular control
✅ **Correlation IDs** for tracing events across system
✅ **Step-by-step Troubleshooting** for common issues
✅ **Log Pattern Analysis** for identifying bugs
✅ **Test & Log Templates** for adding coverage

**Next Steps:**
1. Add missing test coverage (Discord flow, TTS, session switching)
2. Implement frontend log aggregation dashboard
3. Add performance benchmarks (latency tracking)
4. Create automated log analysis tool

---

**Questions or Issues?**
Consult [AGENTS.md](../../../AGENTS.md) for architecture details or [README.md](../README.md) for setup instructions.
