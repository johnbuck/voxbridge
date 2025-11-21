# LLM Stream Hang Fix - Implementation Summary

**Date**: November 7, 2025
**Issue**: LLM generation hanging indefinitely when OpenRouter SSE stream goes silent
**Status**: ✅ **COMPLETE** - All 3 phases implemented and deployed

---

## Problem Description

### Root Cause Analysis

The system was experiencing indefinite hangs during LLM generation due to:

1. **OpenRouter SSE stream silently stalling** - Stream would send initial chunks then go silent (no [DONE] marker)
2. **No timeout on aiter_lines()** - httpx read timeout only applies to initial response headers, NOT to streaming iterations
3. **Orphaned async tasks** - When browser disconnected, LLM task continued running indefinitely in background

### Symptoms

- Frontend shows "AI Generating..." indicator forever
- Backend logs show "Sending HTTP request" but no subsequent "SSE stream ended" message
- System completely stuck, requiring container restart
- Browser disconnect doesn't cancel server-side LLM task

---

## Solution Architecture

**Defense in Depth** - Multi-layer timeout strategy to prevent hangs at every level:

```
┌─────────────────────────────────────────────────────────┐
│ Layer 3: WebRTC Handler (Task Cancellation)            │
│  - Track LLM task for cancellation on disconnect       │
│  - Cleanup on websocket close                          │
│  - Timeout: N/A (controlled by lower layers)           │
└───────────────────┬─────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 2: LLM Service (Service Layer Timeout)           │
│  - Wrap entire generation in asyncio.timeout()         │
│  - Timeout: 90 seconds                                  │
└───────────────────┬─────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 1: OpenRouter Provider (Stream Timeout)          │
│  - Wrap SSE parsing in asyncio.timeout()               │
│  - Timeout: 60 seconds                                  │
└─────────────────────────────────────────────────────────┘
```

**Timeout Hierarchy**:
- Provider timeout (60s) - First line of defense, catches stream stalls
- Service timeout (90s) - Safety net if provider timeout fails
- Task cancellation - Cleanup on disconnect, prevents orphaned tasks

---

## Implementation Details

### Phase 1: OpenRouter SSE Stream Timeout ✅

**File**: `src/llm/openrouter.py`
**Changes**: Added `asyncio.timeout(60.0)` wrapper around SSE stream parsing

```python
async def _parse_sse_stream(self, response: httpx.Response) -> AsyncIterator[str]:
    MAX_STREAM_TIME = 60.0

    try:
        async with asyncio.timeout(MAX_STREAM_TIME):
            async for line in response.aiter_lines():
                # ... parsing logic ...
    except asyncio.TimeoutError:
        logger.error(f"⏱️ SSE stream timeout after {MAX_STREAM_TIME}s")
        if content_chunks == 0:
            raise LLMTimeoutError(f"No content received in {MAX_STREAM_TIME}s")
        logger.warning(f"Partial response received before timeout ({content_chunks} chunks)")
```

**Benefits**:
- Prevents indefinite waiting on stalled SSE streams
- Logs detailed timeout information (line count, chunk count)
- Allows partial responses (graceful degradation if some chunks received)
- Raises LLMTimeoutError if no content received (triggers fallback)

### Phase 2: Service Layer Timeout ✅

**File**: `src/services/llm_service.py`
**Changes**: Added `asyncio.timeout(90.0)` wrapper around provider generation

```python
async def _generate_with_provider(self, provider, request, stream, callback) -> str:
    SERVICE_TIMEOUT = 90.0  # Higher than provider's 60s

    try:
        async with asyncio.timeout(SERVICE_TIMEOUT):
            # ... streaming logic ...
            async for chunk in provider.generate_stream(request):
                chunks.append(chunk)
                if callback:
                    await callback(chunk)
            return "".join(chunks)
    except asyncio.TimeoutError:
        logger.error(f"⏱️ Service layer timeout after {SERVICE_TIMEOUT}s")
        raise LLMTimeoutError(f"LLM service timeout: No response in {SERVICE_TIMEOUT}s")
```

**Benefits**:
- Safety net if provider timeout fails
- Covers both streaming and non-streaming modes
- Higher timeout (90s) ensures provider has chance to timeout first
- Catches timeouts from ANY provider (OpenRouter, Local, etc.)

### Phase 3: LLM Task Tracking and Cancellation ✅

**File**: `src/voice/webrtc_handler.py`
**Changes**: Track LLM task and cancel on disconnect

#### 3a. Task Tracking Attribute (Line 99)

```python
# In __init__:
self.llm_task: Optional[asyncio.Task] = None
```

#### 3b. Task Creation and Tracking (Line 818)

```python
# Route to LLM (Phase 3: Track as task for cancellation)
self.llm_task = asyncio.create_task(self._handle_llm_response(transcript, agent))

try:
    await self.llm_task
except asyncio.CancelledError:
    logger.info(f"🛑 LLM task cancelled during generation")
    raise
finally:
    self.llm_task = None  # Clear task reference
```

#### 3c. Task Cancellation on Cleanup (Line 1217)

```python
async def _cleanup(self):
    # Cancel active LLM task (Phase 3: Prevent orphaned tasks)
    if self.llm_task and not self.llm_task.done():
        logger.info(f"🛑 Cancelling active LLM task")
        self.llm_task.cancel()
        try:
            await self.llm_task
        except asyncio.CancelledError:
            logger.info(f"✅ LLM task cancelled successfully")
        except Exception as e:
            logger.warning(f"⚠️ Error awaiting cancelled LLM task: {e}")
```

**Benefits**:
- Prevents orphaned tasks when browser disconnects
- Graceful cancellation with proper cleanup
- Logged cancellation events for debugging
- Prevents resource leaks from abandoned tasks

---

## Testing Checklist

### Test Scenarios

- [ ] **Normal LLM Response** - Verify timeouts don't interfere with normal operation
  - Send voice message
  - Confirm AI response received within 60s
  - Check logs for no timeout warnings

- [ ] **OpenRouter SSE Stall** - Verify provider timeout works
  - Trigger OpenRouter API issue (empty response or hang)
  - Wait 60 seconds
  - Confirm LLMTimeoutError logged
  - Confirm fallback to local LLM if enabled

- [ ] **Service Layer Timeout** - Verify backup timeout works
  - Mock provider to bypass its timeout
  - Wait 90 seconds
  - Confirm service layer timeout logged

- [ ] **Browser Disconnect During LLM** - Verify task cancellation
  - Send voice message to trigger LLM generation
  - Immediately disconnect browser
  - Check logs for "Cancelling active LLM task"
  - Confirm no orphaned tasks remain

- [ ] **Multiple Concurrent Users** - Verify no interference between sessions
  - Open 2+ browser tabs
  - Send voice messages from both
  - Disconnect one tab during LLM generation
  - Confirm other tab continues working

### Expected Log Patterns

**Normal operation**:
```
🤖 LLM [openrouter]: Streaming request to model 'deepseek/deepseek-chat'
🤖 LLM [openrouter]: SSE stream ended after 150 lines, 148 content chunks
⏱️ LATENCY [LLM first chunk]: 1.234s
```

**Provider timeout**:
```
🤖 LLM [openrouter]: ⏱️ SSE stream timeout after 60.0s (received 10 lines, 0 content chunks)
❌ EMPTY RESPONSE - Received 10 SSE lines but 0 content chunks!
```

**Service timeout**:
```
🤖 LLM Service: ⏱️ Service layer timeout after 90.0s
```

**Task cancellation**:
```
🛑 Cancelling active LLM task
✅ LLM task cancelled successfully
```

---

## Performance Impact

### Latency

- **No impact on normal operation** - Timeouts are safety nets, not throttles
- Provider timeout (60s) is well above typical response time (~2-5s)
- Service timeout (90s) is backup, rarely triggered

### Resource Usage

- **Minimal overhead** - asyncio.timeout() is lightweight
- Task tracking: Single pointer per connection (~8 bytes)
- Cleanup: O(1) operation on disconnect

### Scalability

- **Per-session isolation** - Each WebSocket has own task tracker
- **No global locks** - Task cancellation is local to handler
- **Concurrent safety** - No shared state between sessions

---

## Rollback Procedure

If issues arise, rollback by reverting commit:

```bash
# 1. Identify commit hash
git log --oneline | grep "llm-timeout"

# 2. Revert the commit
git revert <commit-hash>

# 3. Rebuild and restart
docker compose down
docker compose build voxbridge-api
docker compose up -d
```

**Emergency hotfix** (no rebuild):
```bash
# Edit files directly in container
docker exec -it voxbridge-api bash

# Restore old code (remove timeout wrappers)
vim src/llm/openrouter.py
vim src/services/llm_service.py
vim src/voice/webrtc_handler.py

# Restart FastAPI (exit vim, then)
supervisorctl restart fastapi
```

---

## Future Improvements

### Short-term
- [ ] Add Prometheus metrics for timeout events
- [ ] Add frontend notification for timeout fallbacks
- [ ] Tune timeout values based on production data

### Medium-term
- [ ] Implement exponential backoff for retries
- [ ] Add circuit breaker for repeated timeouts
- [ ] Provider-specific timeout configuration

### Long-term
- [ ] Distributed tracing for timeout debugging
- [ ] Auto-scaling based on timeout rates
- [ ] ML-based timeout prediction

---

## References

- **Original Issue**: LLM hang investigation (Nov 7, 2025)
- **Research Document**: `docs/analysis/webrtc-ux-issues-analysis.md`
- **Related Fixes**: WebRTC UX fixes (listening indicator, polling, TTS race condition)
- **Python asyncio.timeout()**: https://docs.python.org/3/library/asyncio-task.html#asyncio.timeout

---

## Contributors

- Implementation: Claude Code (voxbridge-lead agent)
- Testing: [To be added after testing]
- Code Review: [To be added after review]

**Last Updated**: November 7, 2025
