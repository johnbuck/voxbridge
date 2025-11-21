# Silence Detection Fix - Implementation Plan
**Date:** 2025-11-06
**Lead:** voxbridge-lead
**Status:** Planning Phase

---

## Problem Statement

**User Report**: After starting to speak, the microphone continues listening forever instead of detecting silence and stopping.

**Expected Behavior**:
- User speaks into microphone
- WebRTC captures audio and sends to WhisperX
- User stops speaking
- After silence threshold (600ms default), microphone should stop listening
- Transcription should be finalized

**Actual Behavior**:
- User speaks into microphone
- WebRTC captures audio and sends to WhisperX
- User stops speaking
- **Microphone continues listening indefinitely** ❌

---

## Investigation Plan

### Phase 1: Understand Current Implementation (30 min)

**Tasks**:
1. Review WebRTC handler silence detection logic (`src/voice/webrtc_handler.py`)
2. Review WhisperX server VAD (Voice Activity Detection) implementation
3. Review frontend audio controls (`frontend/src/hooks/useWebRTCAudio.ts`)
4. Identify where silence detection should trigger
5. Check backend logs for silence detection events

**Key Questions**:
- Where is silence detection implemented? (Frontend? Backend? WhisperX?)
- What triggers the "stop listening" event?
- Are silence detection events being logged?
- Is the frontend waiting for a backend signal, or managing its own state?

**Agent**: `Explore` agent with "very thorough" mode

---

### Phase 2: Create Diagnostic Tests (45 min)

**Tasks**:
1. Write unit tests for silence detection logic
2. Write integration tests for WebRTC silence detection flow
3. Write E2E tests that simulate speech → silence → finalization
4. Add extensive logging to identify where silence detection fails

**Test Scenarios**:
- **Test 1**: Continuous speech for 2s → 1s silence → should finalize
- **Test 2**: Multiple speech bursts with pauses → should continue listening
- **Test 3**: Long silence (5s+) → should timeout and finalize
- **Test 4**: Frontend microphone state vs backend listening state

**Agent**: `integration-test-writer` agent

---

### Phase 3: Root Cause Analysis (30 min)

**Tasks**:
1. Run diagnostic tests and analyze failures
2. Add debug logging to WebRTC handler
3. Monitor WebSocket messages between frontend/backend
4. Check if WhisperX is sending silence/VAD events
5. Verify frontend is receiving and handling stop events

**Expected Root Causes** (hypotheses):
1. **Frontend issue**: MediaRecorder not stopping when backend signals
2. **Backend issue**: Silence detection logic not triggering
3. **WhisperX issue**: VAD not detecting silence correctly
4. **WebSocket issue**: Stop events not being sent/received
5. **State management issue**: Frontend/backend state desync

**Agent**: `general-purpose` agent with detailed logging analysis

---

### Phase 4: Implement Fix (60 min)

**Based on root cause, implement one of these fixes**:

#### Fix Option A: Frontend MediaRecorder State Management
**If**: Frontend not stopping MediaRecorder when backend signals end
**Solution**:
- Add WebSocket listener for `transcript_final` or `silence_detected` event
- Stop MediaRecorder and close WebSocket connection
- Update UI to show "Finished listening" state

#### Fix Option B: Backend Silence Detection Logic
**If**: Backend not detecting silence correctly
**Solution**:
- Review `SILENCE_THRESHOLD_MS` environment variable (default: 600ms)
- Add VAD (Voice Activity Detection) logic to WebRTC handler
- Implement timeout logic for max speaking time
- Send explicit "stop listening" WebSocket event to frontend

#### Fix Option C: WhisperX VAD Integration
**If**: WhisperX not sending VAD events
**Solution**:
- Check WhisperX server VAD configuration
- Enable VAD in WhisperX transcription session
- Forward VAD events from WhisperX to frontend via WebSocket
- Add silence detection callback in STTService

#### Fix Option D: Hybrid Approach (Most Likely)
**If**: Multiple components involved
**Solution**:
1. **WhisperX**: Enable VAD and send silence events
2. **STTService**: Listen for VAD events and trigger callbacks
3. **WebRTCVoiceHandler**: Detect silence, send WebSocket event to frontend
4. **Frontend**: Listen for stop event, stop MediaRecorder, close connection

**Agent**: Depends on root cause - `frontend-developer`, `voxbridge-lead`, or `general-purpose`

---

### Phase 5: Write Comprehensive Tests (45 min)

**Tasks**:
1. Write unit tests for all silence detection code paths
2. Write integration tests for complete silence flow
3. Write E2E tests with real WhisperX + VAD
4. Test edge cases (very short speech, very long speech, intermittent speech)

**Coverage Goals**:
- 95%+ coverage for silence detection code
- All test scenarios from Phase 2 passing
- E2E validation with real WhisperX

**Agent**: `unit-test-writer` + `integration-test-writer` + `e2e-test-writer`

---

### Phase 6: Validation (30 min)

**Tasks**:
1. Run full test suite (unit + integration + E2E)
2. Manual testing with browser microphone
3. Verify silence threshold behavior (600ms default)
4. Test with different silence thresholds
5. Verify frontend UI updates correctly

**Success Criteria**:
- ✅ All tests passing (95%+ coverage)
- ✅ Microphone stops listening after silence threshold
- ✅ Transcription finalizes correctly
- ✅ Frontend UI shows "Finished listening" state
- ✅ No indefinite listening after user stops speaking

**Agent**: `general-purpose` agent for manual validation + test runner

---

## Implementation Timeline

| Phase | Duration | Agent | Status |
|-------|----------|-------|--------|
| Phase 1: Investigation | 30 min | Explore (very thorough) | 🟡 Pending |
| Phase 2: Diagnostic Tests | 45 min | integration-test-writer | 🟡 Pending |
| Phase 3: Root Cause Analysis | 30 min | general-purpose | 🟡 Pending |
| Phase 4: Implement Fix | 60 min | TBD (depends on root cause) | 🟡 Pending |
| Phase 5: Comprehensive Tests | 45 min | Multiple test agents | 🟡 Pending |
| Phase 6: Validation | 30 min | general-purpose | 🟡 Pending |
| **Total** | **4h 0min** | | |

---

## Risk Assessment

### High Risk
- **Complex interaction** between frontend, backend, WhisperX, and WebSocket events
- **State management** across multiple components
- **VAD accuracy** - false positives/negatives in silence detection

### Medium Risk
- **Test reliability** - E2E tests with real microphone input hard to automate
- **Browser compatibility** - MediaRecorder behavior varies across browsers
- **Threshold tuning** - 600ms may not be optimal for all use cases

### Low Risk
- **Backend implementation** - well-tested service layer
- **WhisperX integration** - proven to work correctly
- **Logging** - comprehensive logging already in place

---

## Rollback Plan

If fix causes regressions:

1. **Revert code changes**:
   ```bash
   git checkout src/voice/webrtc_handler.py
   git checkout frontend/src/hooks/useWebRTCAudio.ts
   git checkout src/services/stt_service.py
   ```

2. **Rebuild containers**:
   ```bash
   docker compose down
   docker compose build --no-cache
   docker compose up -d
   ```

3. **Verify rollback**:
   ```bash
   docker logs voxbridge-api --tail 100
   ```

---

## Next Steps

1. ✅ Create this plan
2. 🟡 Launch Explore agent to investigate current implementation
3. 🟡 Launch integration-test-writer to create diagnostic tests
4. 🟡 Analyze root cause based on investigation + test results
5. 🟡 Implement fix based on root cause
6. 🟡 Write comprehensive tests
7. 🟡 Validate with full test suite + manual testing

---

## Notes

- User explicitly stated: "I don't test. you test with agents"
- All validation must be done via automated tests + agent verification
- Must deliver working solution with proper planning (this document)
- Follow voxbridge-lead role: coordinate agents, make decisions, surface results
