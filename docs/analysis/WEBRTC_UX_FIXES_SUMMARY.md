# WebRTC UX Issues - Quick Reference

**Analysis Date:** 2025-11-07  
**Full Report:** [webrtc-ux-issues-analysis.md](./webrtc-ux-issues-analysis.md)

---

## Issues Summary

| # | Issue | Severity | Root Cause | Fix Complexity |
|---|-------|----------|------------|----------------|
| 1 | TTS audio fails to play | HIGH | Race condition: `tts_complete` arrives before binary audio chunks | MEDIUM (frontend wait loop) |
| 2 | Listening indicator persists | MEDIUM | Missing state cleanup callback between hook and parent | LOW (add callback parameter) |
| 3 | Transcripts truncated | MEDIUM | Overwriting pattern loses early partials | MEDIUM (accumulate partials) |
| 4 | 30s polling too slow | LOW | Polling interval not optimized for active conversations | LOW (reduce to 5s) |

---

## Quick Fixes (Phase 1: 1-2 days)

### Fix #1: TTS Playback Race Condition

**File:** `frontend/src/pages/VoxbridgePage.tsx` (line 293)

```typescript
case 'tts_complete':
  if (!isSpeakerMuted) {
    // Wait for audio chunks (max 500ms)
    const MAX_WAIT_MS = 500;
    const startTime = Date.now();
    
    while (audioChunksRef.current.length === 0 && (Date.now() - startTime) < MAX_WAIT_MS) {
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    
    if (audioChunksRef.current.length === 0) {
      toast.error('Audio playback failed', 'No audio data received');
    } else {
      await audioPlayback.completeAudio();
    }
  }
```

**Why it works:** Waits for binary WebSocket frames to arrive before attempting playback.

---

### Fix #2: Listening Indicator Cleanup

**File:** `frontend/src/hooks/useWebRTCAudio.ts` (line 78)

```typescript
export interface UseWebRTCAudioOptions {
  // ... existing
  onRecordingStop?: () => void;  // NEW
}

const stop = useCallback(() => {
  // ... existing stop logic
  
  // Notify parent to clear UI state
  if (options.onRecordingStop) {
    options.onRecordingStop();
  }
}, [disconnectWebSocket, options]);
```

**File:** `frontend/src/pages/VoxbridgePage.tsx` (line 353)

```typescript
const { ... } = useWebRTCAudio({
  // ... existing options
  onRecordingStop: () => {
    setIsListening(false);
    setVoicePartialTranscript('');
    listeningStartTimeRef.current = null;
  },
});
```

**Why it works:** Callback pattern ensures parent state is cleared when recording stops.

---

## Phase 2 Fixes (2-3 days)

### Fix #3: Transcript Accumulation

**File:** `src/voice/webrtc_handler.py` (line 62)

```python
class WebRTCVoiceHandler:
    def __init__(self, ...):
        # ... existing
        self.partial_transcripts = []  # NEW: Accumulate partials
        
    async def on_transcript(text: str, is_final: bool, metadata: Dict):
        if not is_final:
            # Accumulate partial
            self.partial_transcripts.append(text)
            combined = ' '.join(self.partial_transcripts)
            self.current_transcript = combined
            await self._send_partial_transcript(combined)
        else:
            # Use WhisperX final OR combined partials
            self.current_transcript = text if text else ' '.join(self.partial_transcripts)
            self.partial_transcripts = []  # Clear for next turn
```

**Why it works:** Matches Discord's accumulation pattern, prevents data loss.

---

## Phase 3 Fixes (1 day)

### Fix #4: Polling Interval

**File:** `frontend/src/pages/VoxbridgePage.tsx` (line 186)

```typescript
const { data: messages = [] } = useQuery<Message[]>({
  queryKey: ['messages', activeSessionId],
  queryFn: async () => {
    if (!activeSessionId) return [];
    return await api.getSessionMessages(activeSessionId);
  },
  enabled: !!activeSessionId,
  refetchInterval: 5000, // CHANGED: 5s instead of 30s
  staleTime: 0,
  refetchOnWindowFocus: true,
});
```

**Why it works:** Balance between UX responsiveness and server load.

---

## Code Locations Quick Reference

### Frontend
- `frontend/src/pages/VoxbridgePage.tsx` - Main conversation UI
  - Line 293: TTS complete handler (Issue #1)
  - Line 214: Partial transcript handler (Issue #2)
  - Line 186: Polling interval (Issue #4)
  - Line 353: WebRTC audio hook usage (Issue #2)

- `frontend/src/hooks/useWebRTCAudio.ts` - Audio capture hook
  - Line 78: Options interface (Issue #2)
  - Line 463: Stop function (Issue #2)

- `frontend/src/hooks/useAudioPlayback.ts` - Audio playback hook
  - Line 125: completeAudio function (Issue #1)

### Backend
- `src/voice/webrtc_handler.py` - WebRTC pipeline
  - Line 62: Handler init (Issue #3)
  - Line 203: Transcript callback (Issue #3)
  - Line 1099: TTS generation (Issue #1)

---

## Testing Checklist

### Phase 1
- [ ] TTS playback: 10 consecutive successful plays
- [ ] Listening indicator: Toggle mic while speaking
- [ ] Listening indicator: Close WebSocket while listening

### Phase 2
- [ ] Transcript: Long utterance (10+ words)
- [ ] Transcript: Fast speech with multiple partials
- [ ] Transcript: Compare with Discord transcript accuracy

### Phase 3
- [ ] Polling: Measure time from AI response to UI update
- [ ] Polling: Verify 5s interval in browser network tab

---

## Recommended Implementation Order

1. **Fix #2 (Listening Indicator)** - Easiest, most visible UX improvement
2. **Fix #4 (Polling)** - One-line change, immediate impact
3. **Fix #1 (TTS Playback)** - Critical but requires careful testing
4. **Fix #3 (Transcript)** - Needs WhisperX behavior investigation first

**Total Estimated Time:** 4-6 days for all fixes
