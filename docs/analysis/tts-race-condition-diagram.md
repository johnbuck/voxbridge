# TTS Playback Race Condition - Visual Diagram

## Current Behavior (Broken)

```
Backend (Python)                Network Layer              Frontend (TypeScript)
==============                  =============               =====================

TTS Synthesis Complete
     |
     v
Generate Audio Chunks
     |
     |---> websocket.send_bytes(chunk1) --> [TCP Buffer A] 
     |---> websocket.send_bytes(chunk2) --> [TCP Buffer A]
     |---> websocket.send_bytes(chunk3) --> [TCP Buffer A]  (buffering...)
     |
     v
Send "tts_complete" event
     |
     |---> websocket.send_json({event: "tts_complete"}) --> [TCP Buffer B] --> ARRIVES FIRST!
                                                                                      |
                                                                                      v
                                                                              handleMessage()
                                                                                      |
                                                                                      v
                                                                              audioPlayback.completeAudio()
                                                                                      |
                                                                                      v
                                                                              Check audioChunksRef.current
                                                                                      |
                                                                                      v
                                                                              ❌ EMPTY! (chunks haven't arrived yet)
                                                                                      |
                                                                                      v
                                                                              Return early (silent failure)
     
     (Time passes...)
     
                                                     [TCP Buffer A] --> chunk1 arrives --> orphaned ❌
                                                     [TCP Buffer A] --> chunk2 arrives --> orphaned ❌  
                                                     [TCP Buffer A] --> chunk3 arrives --> orphaned ❌
```

**Problem:** JSON event (small, text frame) arrives before binary frames (large, separate buffer).

---

## Fixed Behavior (Wait Loop)

```
Backend (Python)                Network Layer              Frontend (TypeScript)
==============                  =============               =====================

TTS Synthesis Complete
     |
     v
Generate Audio Chunks
     |
     |---> websocket.send_bytes(chunk1) --> [TCP Buffer A] 
     |---> websocket.send_bytes(chunk2) --> [TCP Buffer A]
     |---> websocket.send_bytes(chunk3) --> [TCP Buffer A]  (buffering...)
     |
     v
Send "tts_complete" event
     |
     |---> websocket.send_json({event: "tts_complete"}) --> [TCP Buffer B] --> ARRIVES FIRST!
                                                                                      |
                                                                                      v
                                                                              handleMessage()
                                                                                      |
                                                                                      v
                                                                              ✅ START WAIT LOOP (max 500ms)
                                                                                      |
                                                                                      v
                                                                              while (chunks.length === 0 && elapsed < 500ms)
                                                                                      |
                                                                                      v
                                                                              await sleep(50ms)
                                                                                      |
     (50ms passes...)                                                                v
                                                     [TCP Buffer A] --> chunk1 arrives --> addAudioChunk(chunk1) ✅
                                                     [TCP Buffer A] --> chunk2 arrives --> addAudioChunk(chunk2) ✅
                                                     [TCP Buffer A] --> chunk3 arrives --> addAudioChunk(chunk3) ✅
                                                                                      |
                                                                                      v
                                                                              ✅ chunks.length > 0!
                                                                                      |
                                                                                      v
                                                                              audioPlayback.completeAudio()
                                                                                      |
                                                                                      v
                                                                              ✅ Audio plays successfully! 🔊
```

**Solution:** Frontend waits for chunks to arrive before attempting playback.

---

## Alternative Fix (Backend Delay)

```
Backend (Python)                Network Layer              Frontend (TypeScript)
==============                  =============               =====================

TTS Synthesis Complete
     |
     v
Generate Audio Chunks
     |
     |---> websocket.send_bytes(chunk1) --> [TCP Buffer A] --> arrives --> addAudioChunk(chunk1) ✅
     |---> websocket.send_bytes(chunk2) --> [TCP Buffer A] --> arrives --> addAudioChunk(chunk2) ✅
     |---> websocket.send_bytes(chunk3) --> [TCP Buffer A] --> arrives --> addAudioChunk(chunk3) ✅
     |
     v
✅ await asyncio.sleep(0.2)  # Wait for WebSocket buffer flush
     |
     v
Send "tts_complete" event
     |
     |---> websocket.send_json({event: "tts_complete"}) --> [TCP Buffer B] --> arrives
                                                                                      |
                                                                                      v
                                                                              handleMessage()
                                                                                      |
                                                                                      v
                                                                              audioPlayback.completeAudio()
                                                                                      |
                                                                                      v
                                                                              ✅ chunks.length > 0 (already arrived)
                                                                                      |
                                                                                      v
                                                                              ✅ Audio plays successfully! 🔊
```

**Trade-off:** Adds artificial 200ms delay to every TTS playback (even when not needed).

---

## Why Discord Doesn't Have This Issue

```
Discord Bot (Python)            Discord Voice API          Discord Client
================                =================           ==============

TTS Synthesis Complete
     |
     v
Generate Audio Chunks
     |
     |---> voice_sink.write(pcm_audio) --> Discord Voice Gateway --> Plays in voice channel ✅
     |
     v
DONE! (No WebSocket events to frontend)
```

**Key Difference:** Discord plays audio server-side (no race condition with frontend).

---

## Recommendation

**Use frontend wait loop:**
- More robust (handles variable network delays)
- No artificial delays when chunks arrive quickly
- Provides user feedback if chunks never arrive (timeout + error toast)

**Avoid backend delay:**
- Adds latency to every playback (bad UX)
- 200ms may not be enough for slow networks
- Hides the problem instead of solving it
