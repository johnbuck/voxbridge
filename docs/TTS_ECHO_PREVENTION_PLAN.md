# TTS Echo Prevention Implementation Plan
**Phase 1: Quick Wins (Options A + B + E)**

**Date**: November 20, 2025
**Status**: Approved - Ready for Implementation
**Expected Improvement**: 70-80% reduction in TTS echo false positives
**Effort**: 1-2 days (8-12 hours)

---

## Overview
Implement three complementary solutions to reduce TTS echo false positives by 70-80% while preserving user interrupt capability with 500ms detection latency.

**Selected Approach**: Phase 1 Quick Wins (A+B+E combination)
**Priority**: Balanced (500ms interrupt delay OK, <10% false positive target)
**Cleanup**: Revert frontend filter (not needed for this issue)

---

## Step 1: Revert Frontend Late Partial Filter
**Goal**: Remove the `hasFinalizedCurrentTurn` logic that doesn't address TTS echo

**Files**:
- `frontend/src/pages/VoxbridgePage.tsx`

**Changes**:
1. Remove state variables (lines 93-94):
   - `hasFinalizedCurrentTurn`
   - `finalizationTimestampRef`

2. Remove filter logic from WebRTC partial_transcript handler (lines 432-447)

3. Remove filter logic from WebRTC final_transcript handler (lines 479-481)

4. Remove filter logic from Discord partial_transcript handler (lines 851-866)

5. Remove filter logic from Discord final_transcript handler (lines 879-881)

**Result**: Clean codebase, ready for proper TTS echo solution

---

## Step 2: Option A - Enhanced WebRTC Echo Cancellation
**Goal**: Verify and enhance browser's built-in AEC

**Files**:
- `frontend/src/hooks/useWebRTCAudio.ts`

**Changes**:

### 2a. Enhance audio constraints (lines 373-381):
```typescript
const stream = await navigator.mediaDevices.getUserMedia({
  audio: {
    channelCount: 2,
    sampleRate: 48000,
    echoCancellation: { ideal: true },    // Force enable
    noiseSuppression: { ideal: true },
    autoGainControl: { ideal: true },
  },
});
```

### 2b. Verify AEC is active (after getUserMedia):
```typescript
const audioTrack = stream.getAudioTracks()[0];
const settings = audioTrack.getSettings();

logger.info('🎧 Audio constraints applied:', {
  echoCancellation: settings.echoCancellation,
  noiseSuppression: settings.noiseSuppression,
  autoGainControl: settings.autoGainControl,
});

if (!settings.echoCancellation) {
  logger.warn('⚠️ Echo cancellation not supported by browser!');
}
```

**Expected Improvement**: 20-30% reduction in echo

---

## Step 3: Option E - Audio Ducking (Microphone Gain Reduction)
**Goal**: Reduce microphone gain to 20% during TTS playback

**Files**:
- `frontend/src/hooks/useWebRTCAudio.ts`

**Changes**:

### 3a. Add Web Audio API gain node (after MediaStream creation):
```typescript
// State for audio ducking
const audioContextRef = useRef<AudioContext | null>(null);
const gainNodeRef = useRef<GainNode | null>(null);
const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);

// After getUserMedia, before MediaRecorder
const audioContext = new AudioContext();
const source = audioContext.createMediaStreamSource(stream);
const gainNode = audioContext.createGain();
const destination = audioContext.createMediaStreamDestination();

gainNode.gain.value = 1.0;  // Normal gain initially

source.connect(gainNode);
gainNode.connect(destination);

// Store refs
audioContextRef.current = audioContext;
gainNodeRef.current = gainNode;
sourceNodeRef.current = source;

// Use destination.stream for MediaRecorder (not original stream)
const mediaRecorder = new MediaRecorder(destination.stream, { ... });
```

### 3b. React to bot_speaking_state_changed events (in WebSocket onmessage):
```typescript
if (message.event === 'bot_speaking_state_changed') {
  const isSpeaking = message.data.is_speaking;

  if (gainNodeRef.current) {
    if (isSpeaking) {
      // Duck to 20% during TTS
      logger.info('🔉 Ducking microphone gain to 20% (TTS playing)');
      gainNodeRef.current.gain.setTargetAtTime(
        0.2,
        audioContextRef.current!.currentTime,
        0.1  // 100ms smooth transition
      );
    } else {
      // Restore full gain after TTS
      logger.info('🔊 Restoring microphone gain to 100% (TTS complete)');
      gainNodeRef.current.gain.setTargetAtTime(
        1.0,
        audioContextRef.current!.currentTime,
        0.1
      );
    }
  }
}
```

### 3c. Cleanup on unmount:
```typescript
useEffect(() => {
  return () => {
    if (audioContextRef.current) {
      audioContextRef.current.close();
    }
  };
}, []);
```

**Expected Improvement**: 30-40% reduction in echo amplitude

---

## Step 4: Option B - Minimum Speech Duration Filtering
**Goal**: Require 500ms continuous speech before transcription

**Files**:
- `src/voice/webrtc_handler.py`
- `src/whisper_server.py`
- `.env.example`

**Changes**:

### 4a. Add configuration (webrtc_handler.py __init__):
```python
# VAD enhancement settings
self.min_speech_duration_ms = int(os.getenv('MIN_SPEECH_DURATION_MS', '500'))
self.speech_energy_threshold = int(os.getenv('SPEECH_ENERGY_THRESHOLD', '300'))
self.audio_energy_buffer = []  # Track recent energy levels
```

### 4b. Add energy detection method (webrtc_handler.py):
```python
def _has_sufficient_speech_energy(self, pcm_data: bytes) -> bool:
    """Check if audio has sustained speech-level energy"""
    samples = np.frombuffer(pcm_data, dtype=np.int16)
    energy = int(np.abs(samples).mean())

    self.audio_energy_buffer.append(energy)

    # Require 500ms of sustained energy (5 chunks * 100ms)
    if len(self.audio_energy_buffer) < 5:
        return False

    # Check average energy over last 500ms
    avg_energy = np.mean(self.audio_energy_buffer[-5:])

    if avg_energy > self.speech_energy_threshold:
        logger.debug(f"✅ Sufficient speech energy: {avg_energy:.0f} (threshold: {self.speech_energy_threshold})")
        return True
    else:
        logger.debug(f"❌ Insufficient energy: {avg_energy:.0f} < {self.speech_energy_threshold}")
        return False
```

### 4c. Apply filter in audio processing loop:
```python
# Before sending audio to WhisperX
if not self._has_sufficient_speech_energy(pcm_data):
    # Not enough energy - likely silence or quiet echo
    continue

# Clear buffer after finalization
self.audio_energy_buffer.clear()
```

### 4d. WhisperX VAD Tuning (CORRECT IMPLEMENTATION)

**Note**: The parameters `vad_filter`, `min_speech_duration_ms`, and `speech_pad_ms` do NOT exist in WhisperX's Python API. VAD configuration MUST be done at model loading time via `whisperx.load_model()`, NOT during transcription via `model.transcribe()`.

**File**: `src/whisper_server.py`

**Add configuration** (after line 41):
```python
# WhisperX VAD configuration (TTS echo prevention)
WHISPERX_VAD_ONSET = float(os.getenv('WHISPERX_VAD_ONSET', '0.600'))
WHISPERX_VAD_OFFSET = float(os.getenv('WHISPERX_VAD_OFFSET', '0.450'))
```

**✅ CORRECT: Add vad_options to load_model()** (line 126):
```python
model = whisperx.load_model(
    WHISPERX_MODEL,
    device=device,
    compute_type=compute_type,
    vad_options={
        "vad_onset": WHISPERX_VAD_ONSET,    # Speech start threshold (0.0-1.0)
        "vad_offset": WHISPERX_VAD_OFFSET   # Speech end threshold (0.0-1.0)
    }
)
```

**❌ WRONG: Do NOT pass vad_options to transcribe()**:
```python
# DON'T DO THIS - Will cause "unexpected keyword argument" error
result = model.transcribe(
    audio,
    batch_size=WHISPERX_BATCH_SIZE,
    language=self.language,
    vad_options={...}  # ❌ NOT SUPPORTED
)
```

**Parameters**:
- `vad_onset`: 0.0-1.0 (default: 0.500) - Higher = less sensitive, filters quieter sounds
- `vad_offset`: 0.0-1.0 (default: 0.363) - Higher = ends speech detection earlier

**Why**: WhisperX stores VAD parameters in the model at initialization (`model._vad_params`). They cannot be changed per-transcription.

### 4e. Add environment variables (.env.example):
```bash
# Backend Energy Filtering (Option B - Layer 1)
MIN_SPEECH_DURATION_MS=500          # Require 500ms continuous speech
SPEECH_ENERGY_THRESHOLD=300         # Minimum amplitude for speech detection

# WhisperX VAD Tuning (Option B - Layer 2)
WHISPERX_VAD_ONSET=0.600           # Speech start threshold (default: 0.500)
WHISPERX_VAD_OFFSET=0.450          # Speech end threshold (default: 0.363)
```

**Expected Improvement**:
- Backend energy filtering: 40-50% reduction in brief echo/noise
- WhisperX VAD tuning: 10-20% additional reduction
- **Combined**: 50-70% total reduction

---

## Step 5: Rebuild and Deploy

**Frontend**:
```bash
docker compose build voxbridge-frontend
docker compose up -d voxbridge-frontend
```

**Backend**:
```bash
# Update .env with new parameters
docker compose build voxbridge-api whisperx
docker compose up -d voxbridge-api whisperx
```

---

## Step 6: Testing and Verification

### Test Scenario 1: Echo Prevention
1. Start voice chat
2. Speak: "Hello"
3. AI responds: "Hello! How can I help?"
4. Verify: No false "Hello" or "help" transcripts from TTS echo
5. Check browser logs for ducking messages: `🔉 Ducking microphone gain`

### Test Scenario 2: Interrupt Detection
1. AI is speaking (long response)
2. Interrupt mid-sentence: "Wait, stop"
3. Verify: Interrupt detected within 500ms
4. Check logs: Energy spike should trigger detection

### Test Scenario 3: Minimum Duration Filter
1. Make brief noise (cough, click)
2. Verify: Not transcribed (< 500ms duration)
3. Check logs: `❌ Insufficient energy` messages

### Metrics to Track:
- **False Positive Rate**: % of transcripts that are echoes (target: <10%)
- **Interrupt Latency**: Time to detect user interrupt (target: <500ms)
- **False Negative Rate**: % of real speech missed (target: <5%)

---

## Step 7: Tuning (If Needed)

### If too many false positives (echoes still getting through):
```bash
# Increase thresholds
SPEECH_ENERGY_THRESHOLD=400           # Was 300
MIN_SPEECH_DURATION_MS=700            # Was 500
DUCKING_GAIN=0.15                     # Was 0.2 (more aggressive)
```

### If interrupts are delayed/missed:
```bash
# Decrease thresholds
SPEECH_ENERGY_THRESHOLD=200           # Was 300
MIN_SPEECH_DURATION_MS=400            # Was 500
```

### Monitor logs:
```bash
# Check energy levels
docker logs voxbridge-api | grep "energy:"

# Check ducking activation
docker logs voxbridge-frontend --tail 100 | grep "Ducking"
```

---

## Success Criteria

✅ **False positive rate < 10%** (90% of transcripts are genuine user speech)
✅ **Interrupt latency < 500ms** (balanced UX)
✅ **User interrupts work reliably** (>95% detection rate)
✅ **No regression in normal speech detection** (false negatives < 5%)

---

## Rollback Plan

If Phase 1 causes issues:

1. **Revert frontend changes**: Restore original useWebRTCAudio.ts
2. **Revert backend changes**: Remove energy filtering from webrtc_handler.py
3. **Remove env variables**: Comment out new MIN_SPEECH_DURATION_MS settings
4. **Restart containers**: `docker compose restart`

---

## Next Steps (If Phase 1 Insufficient)

If false positive rate still >10% after tuning:

**Phase 2: Implement Option D (Smart Interrupt Detection)**
- Add multi-heuristic interrupt detector
- Track baseline energy + detect spikes
- Time-based grace period (300ms after TTS)
- Expected: 90-95% reduction in false positives

---

## Related Documentation

- **Research Report**: `docs/LATE_PARTIAL_TRANSCRIPT_FIX.md` (superseded by this plan)
- **Industry Best Practices**: See research report section 1
- **Current Implementation**: See research report section 2
- **Root Cause Analysis**: See research report section 3
- **Alternative Solutions**: See research report section 4 (Options C, D, F)

---

**Estimated Phase 1 Effort**: 1-2 days (8-12 hours)
**Expected Improvement**: 70-80% reduction in TTS echo false positives
**Risk Level**: Low (all changes are reversible, no breaking changes)
