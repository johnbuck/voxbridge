# WebRTC Conversation History Fix - Implementation Plan

**Issue**: WebRTC chat not populating conversation history
**Root Cause**: Missing WebSocket broadcasts to global event stream
**Solution**: Add dual-channel event publishing (voice session + global broadcast)

---

## Changes Required

### File: `src/voice/webrtc_handler.py`

**Total Lines Changed**: ~50 lines (4 methods + imports)
**Complexity**: Low (additive changes only)
**Risk**: Minimal (no breaking changes)

---

## Change 1: Add Import for WebSocket Manager

**Location**: Line 36 (after existing imports)

**Add**:
```python
from datetime import datetime  # Add if not already present
```

**Purpose**: Required for timestamp field in broadcast events

---

## Change 2: Update `_send_partial_transcript()` Method

**Location**: Lines 447-458

**Before**:
```python
async def _send_partial_transcript(self, text: str):
    """Send partial transcript event to browser"""
    try:
        await self.websocket.send_json({
            "event": "partial_transcript",
            "data": {
                "text": text,
                "session_id": str(self.session_id)
            }
        })
    except Exception as e:
        logger.error(f"❌ Error sending partial transcript: {e}")
```

**After**:
```python
async def _send_partial_transcript(self, text: str):
    """Send partial transcript event to browser and broadcast to global event stream"""
    try:
        # Send to voice WebSocket (existing - for real-time voice session display)
        await self.websocket.send_json({
            "event": "partial_transcript",
            "data": {
                "text": text,
                "session_id": str(self.session_id)
            }
        })

        # Broadcast to global event stream (NEW - for conversation history updates)
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
            logger.debug(f"📡 Broadcast partial transcript to {len(ws_manager.active_connections)} client(s)")
        except Exception as broadcast_error:
            # Don't fail voice session if broadcast fails
            logger.warning(f"⚠️ Failed to broadcast partial transcript: {broadcast_error}")

    except Exception as e:
        logger.error(f"❌ Error sending partial transcript: {e}")
```

**Changes**:
1. Added `ws_manager.broadcast()` call after direct send
2. Added `userId`, `timestamp` fields to match Discord format
3. Added try/except for broadcast errors (non-critical)
4. Added debug logging for broadcast confirmation

---

## Change 3: Update `_send_final_transcript()` Method

**Location**: Lines 460-471

**Before**:
```python
async def _send_final_transcript(self, text: str):
    """Send final transcript event to browser"""
    try:
        await self.websocket.send_json({
            "event": "final_transcript",
            "data": {
                "text": text,
                "session_id": str(self.session_id)
            }
        })
    except Exception as e:
        logger.error(f"❌ Error sending final transcript: {e}")
```

**After**:
```python
async def _send_final_transcript(self, text: str):
    """Send final transcript event to browser and broadcast to global event stream"""
    try:
        # Send to voice WebSocket (existing - for real-time voice session display)
        await self.websocket.send_json({
            "event": "final_transcript",
            "data": {
                "text": text,
                "session_id": str(self.session_id)
            }
        })

        # Broadcast to global event stream (NEW - for conversation history updates)
        try:
            from src.api import get_ws_manager
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
            logger.info(f"📡 Broadcast final transcript to {len(ws_manager.active_connections)} client(s)")
        except Exception as broadcast_error:
            # Don't fail voice session if broadcast fails
            logger.warning(f"⚠️ Failed to broadcast final transcript: {broadcast_error}")

    except Exception as e:
        logger.error(f"❌ Error sending final transcript: {e}")
```

**Changes**:
1. Added `ws_manager.broadcast()` call after direct send
2. Added `userId`, `timestamp` fields to match Discord format
3. Added try/except for broadcast errors (non-critical)
4. Added info logging for broadcast confirmation

---

## Change 4: Update `_send_ai_response_chunk()` Method

**Location**: Lines 473-484

**Before**:
```python
async def _send_ai_response_chunk(self, text: str):
    """Send AI response chunk event to browser"""
    try:
        await self.websocket.send_json({
            "event": "ai_response_chunk",
            "data": {
                "text": text,
                "session_id": str(self.session_id)
            }
        })
    except Exception as e:
        logger.error(f"❌ Error sending AI response chunk: {e}")
```

**After**:
```python
async def _send_ai_response_chunk(self, text: str):
    """Send AI response chunk event to browser and broadcast to global event stream"""
    try:
        # Send to voice WebSocket (existing - for real-time voice session display)
        await self.websocket.send_json({
            "event": "ai_response_chunk",
            "data": {
                "text": text,
                "session_id": str(self.session_id)
            }
        })

        # Broadcast to global event stream (NEW - for conversation history streaming updates)
        try:
            from src.api import get_ws_manager
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
            logger.debug(f"📡 Broadcast AI chunk to {len(ws_manager.active_connections)} client(s)")
        except Exception as broadcast_error:
            # Don't fail voice session if broadcast fails
            logger.warning(f"⚠️ Failed to broadcast AI response chunk: {broadcast_error}")

    except Exception as e:
        logger.error(f"❌ Error sending AI response chunk: {e}")
```

**Changes**:
1. Added `ws_manager.broadcast()` call after direct send
2. Added `userId`, `timestamp` fields to match Discord format
3. Added try/except for broadcast errors (non-critical)
4. Added debug logging for broadcast confirmation

---

## Change 5: Update `_send_ai_response_complete()` Method

**Location**: Lines 486-497

**Before**:
```python
async def _send_ai_response_complete(self, text: str):
    """Send AI response complete event to browser"""
    try:
        await self.websocket.send_json({
            "event": "ai_response_complete",
            "data": {
                "text": text,
                "session_id": str(self.session_id)
            }
        })
    except Exception as e:
        logger.error(f"❌ Error sending AI response complete: {e}")
```

**After**:
```python
async def _send_ai_response_complete(self, text: str):
    """Send AI response complete event to browser and broadcast to global event stream"""
    try:
        # Send to voice WebSocket (existing - for real-time voice session display)
        await self.websocket.send_json({
            "event": "ai_response_complete",
            "data": {
                "text": text,
                "session_id": str(self.session_id)
            }
        })

        # Broadcast to global event stream (NEW - for conversation history final message)
        try:
            from src.api import get_ws_manager
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
            logger.info(f"📡 Broadcast AI response complete to {len(ws_manager.active_connections)} client(s)")
        except Exception as broadcast_error:
            # Don't fail voice session if broadcast fails
            logger.warning(f"⚠️ Failed to broadcast AI response complete: {broadcast_error}")

    except Exception as e:
        logger.error(f"❌ Error sending AI response complete: {e}")
```

**Changes**:
1. Added `ws_manager.broadcast()` call after direct send
2. Added `userId`, `timestamp` fields to match Discord format
3. Added try/except for broadcast errors (non-critical)
4. Added info logging for broadcast confirmation

---

## Change 6: Add Metrics Broadcast After AI Response

**Location**: After line 437 (after saving AI message to database)

**Add**:
```python
            # Broadcast metrics update to frontend (matches Discord plugin behavior)
            try:
                from src.api import get_ws_manager
                ws_manager = get_ws_manager()
                metrics_snapshot = self.metrics.get_metrics()
                await ws_manager.broadcast({
                    "event": "metrics_updated",
                    "data": metrics_snapshot
                })
                logger.debug(f"📡 Broadcast metrics update to {len(ws_manager.active_connections)} client(s)")
            except Exception as broadcast_error:
                logger.warning(f"⚠️ Failed to broadcast metrics: {broadcast_error}")
```

**Purpose**: Ensures StatusSummary metrics update in real-time after conversation turn

---

## Testing Checklist

### Test 1: Partial Transcript Display

**Steps**:
1. Open VoxbridgePage in browser
2. Click microphone button to start recording
3. Speak into microphone

**Expected**:
- ✅ `STTWaitingIndicator` shows live transcription
- ✅ Browser console shows: `[WebSocket] Received message: {event: "partial_transcript", data: {...}}`
- ✅ Backend logs show: `📡 Broadcast partial transcript to 1 client(s)`

**Verify**:
```bash
# Check backend logs
docker logs voxbridge-api --tail 50 | grep "Broadcast partial transcript"
```

---

### Test 2: Final Transcript in Conversation History

**Steps**:
1. Continue from Test 1
2. Stop speaking (silence detection triggers after 600ms)

**Expected**:
- ✅ Blue user message bubble appears in conversation history
- ✅ Message text matches what was spoken
- ✅ Browser console shows: `[WebSocket] Received message: {event: "final_transcript", data: {...}}`
- ✅ Backend logs show: `📡 Broadcast final transcript to 1 client(s)`

**Verify**:
```bash
# Check backend logs
docker logs voxbridge-api --tail 50 | grep "Broadcast final transcript"

# Check database
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "SELECT role, content FROM conversations ORDER BY timestamp DESC LIMIT 5;"
```

---

### Test 3: AI Response Streaming

**Steps**:
1. Continue from Test 2
2. Wait for AI to generate response

**Expected**:
- ✅ `AIGeneratingIndicator` shows thinking animation
- ✅ `StreamingMessageDisplay` shows AI response streaming character-by-character
- ✅ Purple assistant bubble builds up in real-time
- ✅ Browser console shows multiple: `{event: "ai_response_chunk", data: {...}}`
- ✅ Backend logs show: `📡 Broadcast AI chunk to 1 client(s)` (multiple times)

**Verify**:
```bash
# Check backend logs
docker logs voxbridge-api --tail 100 | grep "Broadcast AI chunk"
```

---

### Test 4: AI Response in Conversation History

**Steps**:
1. Continue from Test 3
2. Wait for AI response to complete

**Expected**:
- ✅ Final purple assistant message appears in conversation history
- ✅ Message text matches streamed response
- ✅ Browser console shows: `{event: "ai_response_complete", data: {...}}`
- ✅ Backend logs show: `📡 Broadcast AI response complete to 1 client(s)`
- ✅ TTS audio plays (if speaker not muted)

**Verify**:
```bash
# Check backend logs
docker logs voxbridge-api --tail 50 | grep "Broadcast AI response complete"

# Check database
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "SELECT role, content FROM conversations ORDER BY timestamp DESC LIMIT 5;"
```

---

### Test 5: Metrics Update

**Steps**:
1. Continue from Test 4
2. Observe StatusSummary card

**Expected**:
- ✅ Metrics update immediately after conversation turn
- ✅ Response time, total conversations, avg latency all update
- ✅ Browser console shows: `{event: "metrics_updated", data: {...}}`
- ✅ Backend logs show: `📡 Broadcast metrics update to 1 client(s)`

**Verify**:
```bash
# Check backend logs
docker logs voxbridge-api --tail 50 | grep "Broadcast metrics"
```

---

### Test 6: Multi-Turn Conversation

**Steps**:
1. Have a 3-turn conversation:
   - Turn 1: "What is the capital of France?"
   - Turn 2: "What is its population?"
   - Turn 3: "Tell me about the Eiffel Tower"

**Expected**:
- ✅ All 6 messages appear in conversation history (3 user + 3 assistant)
- ✅ Messages in correct chronological order
- ✅ No duplicate messages
- ✅ All messages persist across page refresh (database backed)
- ✅ Real-time updates for each turn

**Verify**:
```bash
# Check all messages in database
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "SELECT role, LEFT(content, 50) as content_preview, timestamp FROM conversations ORDER BY timestamp DESC LIMIT 10;"
```

---

### Test 7: Multiple Frontend Clients

**Steps**:
1. Open VoxbridgePage in two browser tabs
2. Start voice chat in Tab 1
3. Observe Tab 2

**Expected**:
- ✅ Tab 2 conversation history updates in real-time
- ✅ Both tabs show identical conversation
- ✅ Backend logs show: `Broadcast ... to 2 client(s)`

**Verify**:
```bash
# Check broadcast count
docker logs voxbridge-api --tail 50 | grep "Broadcast.*to.*client"
```

---

### Test 8: Conversation Persistence

**Steps**:
1. Have a conversation
2. Close browser tab
3. Reopen VoxbridgePage
4. Select same conversation from sidebar

**Expected**:
- ✅ Full conversation history loads from database
- ✅ All messages visible
- ✅ Conversation continues where it left off

**Verify**:
```bash
# Check conversation count
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "SELECT COUNT(*) FROM conversations;"
```

---

## Rollback Plan

If issues arise after deployment:

1. **Immediate Rollback** (< 5 minutes):
   ```bash
   git checkout HEAD~1 src/voice/webrtc_handler.py
   docker compose restart voxbridge-api
   ```

2. **Disable Broadcasting** (temporary fix):
   - Wrap all `ws_manager.broadcast()` calls in `if os.getenv('ENABLE_WEBRTC_BROADCAST', 'true') == 'true':`
   - Set `ENABLE_WEBRTC_BROADCAST=false` in `.env`
   - Restart service

3. **Logs to Check**:
   ```bash
   # Check for broadcast errors
   docker logs voxbridge-api --tail 200 | grep -E "(broadcast|❌|⚠️)"

   # Check WebSocket connection count
   docker logs voxbridge-api --tail 200 | grep "WebSocket.*client"
   ```

---

## Performance Considerations

**Broadcast Overhead**:
- Each event now broadcasts to all `/ws/events` clients
- Typical frontend: 1-2 clients per user
- Overhead: ~1ms per broadcast (negligible)

**Network Traffic**:
- Events sent twice (voice session + broadcast)
- Typical conversation: ~50 events (25 partial + 5 final + 20 AI chunks)
- Extra traffic: ~5KB per conversation turn
- Impact: Minimal (< 1% bandwidth increase)

**Error Handling**:
- Broadcast errors are caught and logged (non-critical)
- Voice session continues even if broadcast fails
- Conversation history falls back to database polling (2s interval)

---

## Success Criteria

1. ✅ WebRTC conversation history populates in real-time
2. ✅ User messages appear after transcription
3. ✅ AI responses stream character-by-character
4. ✅ Metrics update after each conversation turn
5. ✅ No duplicate messages
6. ✅ No performance degradation
7. ✅ Identical UX to Discord plugin
8. ✅ All tests pass (8/8 checklist)

---

## Estimated Time

**Implementation**: 30 minutes
**Testing**: 45 minutes
**Total**: 1.5 hours

---

## Risk Assessment

**Risk Level**: **LOW**

**Reasons**:
1. Additive changes only (no deletions)
2. Error handling prevents cascade failures
3. Voice session unaffected if broadcast fails
4. Frontend already handles duplicate events
5. Rollback plan available
6. Matches proven Discord plugin pattern

**Mitigation**:
- Test with single client before multi-client
- Monitor logs during first 10 conversations
- Keep rollback script ready
- Test across multiple sessions

---

## Next Steps

1. Implement changes in `webrtc_handler.py`
2. Run unit tests (ensure no regressions)
3. Manual testing with checklist
4. Monitor logs for 24 hours
5. Document final results
6. Update ARCHITECTURE.md

**Ready to proceed?** ✅
