# VoxBridge Logging & Testing Infrastructure Plan

**Branch**: `feature/logging-and-testing-infrastructure`
**Status**: In Progress
**Created**: 2025-11-20

## 🎯 Objective

Fix unstable interactions and AI response rendering issues by establishing comprehensive logging, testing infrastructure, and race condition fixes.

## 📊 Problems Identified

1. **AI responses not rendering until page refresh** (3 race conditions in cache/query lifecycle)
2. **Zero frontend test coverage** (backend has 90%+, frontend has 0%)
3. **Missing database persistence confirmation** (frontend guesses when saves complete)
4. **Insufficient logging in critical paths** (6 major gaps identified)

---

## 🗓️ Phase 1: Foundation - Logging Infrastructure

### 1.1 Create New Branch

```bash
git checkout -b feature/logging-and-testing-infrastructure
git push -u origin feature/logging-and-testing-infrastructure
```

### 1.2 Backend: Add Database Persistence Logging

**File**: `src/services/conversation_service.py`

**Changes**:
- Add timing logs for `add_message()` method
- Log database transaction duration
- Add correlation IDs to all messages

**New Logs**:
```python
logger.info(f"💾 [DB_SAVE_START] Saving message (role={role}, session={session_id}, correlation_id={correlation_id})")
logger.info(f"💾 [DB_SAVE_COMPLETE] Message saved (id={message_id}, duration={duration_ms}ms, correlation_id={correlation_id})")
```

### 1.3 Backend: Add Message Saved Confirmation Event

**File**: `src/voice/webrtc_handler.py`

**Changes**:
- Add new WebSocket event: `message_saved`
- Emit after database commit completes
- Include correlation_id for tracing

**New Event**:
```python
await ws_manager.broadcast({
    "event": "message_saved",
    "data": {
        "message_id": str(message.id),
        "session_id": str(session_id),
        "role": role,
        "correlation_id": correlation_id,
        "timestamp": time.time()
    }
})
```

### 1.4 Frontend: Instrument React Query Lifecycle

**File**: `frontend/src/pages/VoxbridgePage.tsx`

**Changes**:
- Add logging to `useQuery` queryFn, onSuccess, onError callbacks
- Monitor `dataUpdatedAt` with useEffect
- Log `setQueryData()` and `invalidateQueries()` calls
- Add correlation ID tracking

**New Logs** (7 new log points):
```typescript
// Query start
logger.debug('🔄 [QUERY_START] Fetching messages', { sessionId, timestamp: Date.now() });

// Query complete
logger.debug('✅ [QUERY_COMPLETE] Fetched messages', { count, duration });

// Cache update (setQueryData)
logger.debug('💾 [CACHE_SET] Updated cache with setQueryData', { oldCount, newCount, correlationId });

// Query invalidation
logger.debug('🔄 [QUERY_INVALIDATE] Invalidating messages query', { sessionId, correlationId });

// Cache update detected (dataUpdatedAt change)
logger.debug('📦 [CACHE_UPDATED] Cache reflected new data', { messagesCount, dataUpdatedAt });

// Message render
logger.trace('[MESSAGE_RENDER]', { messageId, role, reactKey, isStreaming, isPending });
```

### 1.5 Backend: Add WebSocket Delivery Confirmation

**File**: `src/api/server.py` (ConnectionManager class)

**Changes**:
- Log individual client send success/failure
- Add message size and serialization time
- Track correlation IDs through WebSocket delivery

**New Logs**:
```python
logger.debug(f"📤 [WS_SEND_START] Sending {event_type} to client {client_id} (size={size}bytes, correlation_id={correlation_id})")
logger.debug(f"✅ [WS_SEND_SUCCESS] Client {client_id} received {event_type} (duration={duration_ms}ms)")
```

**Deliverables**:
- ✅ 4 files modified with enhanced logging
- ✅ Correlation IDs added to AI response flow
- ✅ Database persistence confirmation events
- ✅ React Query lifecycle fully instrumented
- ✅ All logs Claude-accessible via Docker logs and `/api/frontend-logs`

---

## 🧪 Phase 2: Frontend Testing Setup

### 2.1 Install Frontend Testing Dependencies

**File**: `frontend/package.json`

**New Dependencies**:
```json
{
  "devDependencies": {
    "@testing-library/react": "^14.1.2",
    "@testing-library/jest-dom": "^6.1.5",
    "@testing-library/user-event": "^14.5.1",
    "@vitest/ui": "^1.0.4",
    "vitest": "^1.0.4",
    "jsdom": "^23.0.1"
  }
}
```

### 2.2 Create Vitest Configuration

**File**: `frontend/vitest.config.ts` (NEW)

```typescript
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: ['node_modules/', 'src/__tests__/']
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  }
});
```

### 2.3 Create Test Setup File

**File**: `frontend/src/__tests__/setup.ts` (NEW)

```typescript
import '@testing-library/jest-dom';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// Clean up after each test
afterEach(() => {
  cleanup();
});

// Mock WebSocket
global.WebSocket = vi.fn();

// Mock ResizeObserver (required for React components)
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));
```

### 2.4 Create WebSocket Mock

**File**: `frontend/src/__tests__/mocks/WebSocketMock.ts` (NEW)

**Mock Features**:
- Simulate WebSocket connection lifecycle
- Emit test events (partial_transcript, ai_response_complete, etc.)
- Capture sent messages for assertions

### 2.5 Create First Test Suite

**File**: `frontend/src/pages/__tests__/VoxbridgePage.test.tsx` (NEW)

**Test Cases**:
1. ✅ AI response renders without refresh
2. ✅ Streaming chunks display correctly
3. ✅ Race condition handling (cache update vs. refetch)
4. ✅ Optimistic UI transitions (streaming → database)
5. ✅ Error handling (service error events)

**Deliverables**:
- ✅ Vitest + React Testing Library configured
- ✅ 5 test cases for VoxbridgePage rendering
- ✅ WebSocket mock for event simulation
- ✅ Test coverage reporting (HTML + console)

---

## 🐛 Phase 3: Fix Race Conditions

### 3.1 Race Condition #1: Wait for Database Confirmation

**File**: `frontend/src/pages/VoxbridgePage.tsx`

**Current Problem**:
```typescript
// ai_response_complete handler
queryClient.setQueryData(...);  // Optimistic update
queryClient.invalidateQueries(...);  // Immediate refetch (race!)
```

**Fix**:
```typescript
// ai_response_complete handler
case 'ai_response_complete':
  // Store correlation ID and pending state
  setPendingAIResponse({ text: message.data.text, correlationId: message.data.correlation_id });
  break;

// NEW: message_saved handler
case 'message_saved':
  // Database confirmed - now safe to update cache
  if (message.data.correlation_id === pendingAIResponse?.correlationId) {
    queryClient.setQueryData(...);  // Add message
    queryClient.invalidateQueries(...);  // Refetch to get DB ID
    setPendingAIResponse(null);
  }
  break;
```

### 3.2 Race Condition #2: Synchronize Streaming Chunks Cleanup

**File**: `frontend/src/pages/VoxbridgePage.tsx`

**Current Problem**:
```typescript
// useEffect clears chunks when DB message appears (timing-dependent)
useEffect(() => {
  if (hasStreamingInDB) {
    setStreamingChunks([]);  // May clear before cache update reflects
  }
}, [messages, streamingChunks]);
```

**Fix**:
```typescript
// Clear chunks only after receiving message_saved event
case 'message_saved':
  if (message.data.role === 'assistant' && streamingChunks.length > 0) {
    setStreamingChunks([]);  // Guaranteed safe - DB is updated
  }
  break;
```

### 3.3 Race Condition #3: Debounce Query Invalidation

**File**: `frontend/src/pages/VoxbridgePage.tsx`

**Current Problem**:
```typescript
// Multiple invalidateQueries calls in rapid succession
queryClient.invalidateQueries(['messages', sessionId]);  // From final_transcript
queryClient.invalidateQueries(['messages', sessionId]);  // From ai_response_complete
```

**Fix**:
```typescript
// Debounced invalidation with 100ms delay
const debouncedInvalidate = useMemo(
  () => debounce(() => {
    queryClient.invalidateQueries(['messages', activeSessionId]);
  }, 100),
  [activeSessionId]
);
```

**Deliverables**:
- ✅ 3 race conditions eliminated
- ✅ Database confirmation event integrated
- ✅ Deterministic cache update flow
- ✅ Tests verify race condition fixes

---

## 📈 Phase 4: Performance Monitoring

### 4.1 Add End-to-End Latency Tracking

**Files**: Backend + Frontend

**New Metrics**:
- `ai_complete_to_db_save` - Backend database write latency
- `db_save_to_frontend_confirm` - WebSocket delivery latency
- `frontend_confirm_to_cache_update` - React Query cache update latency
- `cache_update_to_render` - React render cycle latency
- `total_ai_to_ui` - End-to-end latency (AI complete → UI visible)

**Implementation**:
```typescript
// Frontend: Track end-to-end latency
case 'ai_response_complete':
  const t0 = Date.now();
  // ... optimistic update

case 'message_saved':
  const t1 = Date.now();
  // ... cache update
  const latency = t1 - t0;
  logger.info(`⏱️ [E2E_LATENCY] AI response visible (${latency}ms)`);
  metrics_tracker.record_ai_to_ui_latency(latency);
  break;
```

### 4.2 Add Metrics Endpoint for Frontend

**File**: `src/api/server.py`

**New Endpoint**: `GET /api/metrics/frontend`

**Returns**:
```json
{
  "ai_to_ui_latency": { "avg": 245, "p50": 220, "p95": 380, "p99": 520 },
  "cache_update_duration": { "avg": 12, "p50": 10, "p95": 25, "p99": 45 },
  "websocket_delivery": { "avg": 8, "p50": 6, "p95": 15, "p99": 28 }
}
```

**Deliverables**:
- ✅ 5 new latency metrics
- ✅ Frontend metrics endpoint
- ✅ Real-time performance visibility

---

## 📝 Phase 5: Documentation & Validation

### 5.1 Create Logging Guide

**File**: `docs/LOGGING_GUIDE.md` (NEW)

**Contents**:
- How to use tiered logging system (TRACE/DEBUG/INFO/WARN/ERROR)
- Environment variable reference (LOG_LEVEL_*, VITE_LOG_LEVEL_*)
- Correlation ID usage patterns
- Log format standards
- How Claude accesses logs (Docker logs, /api/frontend-logs)

### 5.2 Create Testing Guide

**File**: `frontend/README.testing.md` (NEW)

**Contents**:
- Running frontend tests (`npm test`)
- Writing new test cases
- WebSocket event mocking patterns
- Coverage reporting (`npm run test:coverage`)

### 5.3 Update CLAUDE.md

**File**: `voxbridge/CLAUDE.md`

**Additions**:
- Logging architecture overview
- How to enable debug logs for troubleshooting
- Testing commands for frontend/backend
- Debugging guide for race conditions

### 5.4 Validation Tests

**Test Plan**:
1. ✅ Run all backend tests (`./test.sh tests/`)
2. ✅ Run all frontend tests (`npm test`)
3. ✅ Manual testing: AI responses render without refresh
4. ✅ Manual testing: No flickering or disappearing messages
5. ✅ Manual testing: Logs are Claude-accessible via Docker logs
6. ✅ Check test coverage (frontend should be >70%)

**Deliverables**:
- ✅ 3 documentation files
- ✅ All tests passing (backend + frontend)
- ✅ Manual validation complete
- ✅ Logs verified Claude-accessible

---

## 📦 Summary

### Files to Modify (Backend)

1. `src/services/conversation_service.py` - Add DB timing logs + correlation IDs
2. `src/voice/webrtc_handler.py` - Add message_saved event
3. `src/api/server.py` - Add WS delivery logs + frontend metrics endpoint

### Files to Modify (Frontend)

1. `frontend/src/pages/VoxbridgePage.tsx` - Instrument React Query + fix race conditions
2. `frontend/package.json` - Add testing dependencies
3. `frontend/vitest.config.ts` - NEW vitest config
4. `frontend/src/__tests__/setup.ts` - NEW test setup
5. `frontend/src/__tests__/mocks/WebSocketMock.ts` - NEW WebSocket mock
6. `frontend/src/pages/__tests__/VoxbridgePage.test.tsx` - NEW test suite

### Files to Create (Documentation)

1. `docs/LOGGING_GUIDE.md` - Logging architecture and usage
2. `frontend/README.testing.md` - Frontend testing guide
3. Update `voxbridge/CLAUDE.md` - Add debugging section

### Expected Outcomes

- ✅ AI responses render immediately (no refresh needed)
- ✅ Zero race conditions in cache/query lifecycle
- ✅ Frontend test coverage >70%
- ✅ All logs Claude-accessible via Docker logs
- ✅ End-to-end latency visibility (<300ms target)
- ✅ Comprehensive debugging capabilities

---

## Progress Tracking

### Phase 1: Foundation - Logging Infrastructure
- [x] 1.1 Create new branch
- [ ] 1.2 Add database persistence logging
- [ ] 1.3 Add message_saved confirmation event
- [ ] 1.4 Instrument React Query lifecycle
- [ ] 1.5 Add WebSocket delivery confirmation

### Phase 2: Frontend Testing Setup
- [ ] 2.1 Install frontend testing dependencies
- [ ] 2.2 Create Vitest configuration
- [ ] 2.3 Create test setup file
- [ ] 2.4 Create WebSocket mock
- [ ] 2.5 Create first test suite

### Phase 3: Fix Race Conditions
- [ ] 3.1 Fix race condition #1 - Database confirmation
- [ ] 3.2 Fix race condition #2 - Streaming chunks cleanup
- [ ] 3.3 Fix race condition #3 - Debounced invalidation

### Phase 4: Performance Monitoring
- [ ] 4.1 Add end-to-end latency tracking
- [ ] 4.2 Add metrics endpoint for frontend

### Phase 5: Documentation & Validation
- [ ] 5.1 Create logging guide
- [ ] 5.2 Create testing guide
- [ ] 5.3 Update CLAUDE.md
- [ ] 5.4 Run validation tests

---

## Notes

- All logs use emoji prefixes for easy filtering (🎤 voice, 📡 network, ⏱️ latency, 🌊 streaming, 💭 AI, ✅ success, ❌ error, ⚠️ warning, 🔍 debug)
- Correlation IDs enable end-to-end tracing of messages through the system
- Frontend logs are batched and sent to backend via `/api/frontend-logs` endpoint
- All logs are accessible to Claude via Docker logs (`docker logs voxbridge-discord`)
- Tests use Vitest (frontend) and Pytest (backend) for consistent testing experience
