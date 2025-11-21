---
description: Debug streaming response flow
---

Debug VoxBridge streaming response system to analyze sentence splitting, chunk processing, and TTS generation.

Execute the following command to view streaming-related logs:

```bash
docker logs voxbridge-api --tail 300 | grep -E "(🌊|streaming|chunk|sentence|TTS|clause)"
```

This will:
- Show last 300 log lines (streaming can be verbose)
- Filter for streaming-related events
- Display chunk processing, sentence detection, TTS calls

**Streaming flow tracked:**
1. **Chunk received** - Raw chunks from n8n webhook
2. **Sentence detection** - When complete sentences are identified
3. **Clause splitting** - If USE_CLAUSE_SPLITTING=true
4. **TTS generation** - When TTS API is called for each sentence
5. **Audio playback** - When audio starts playing in Discord

Expected output example:
```
🌊 Chunk received (42 chars): "Hello! How can I help you today?"
🌊 Complete sentence detected: "Hello!"
🌊 Sending to TTS: "Hello!" (6 chars)
🔊 Playing TTS audio (sentence 1)
🌊 Complete sentence detected: "How can I help you today?"
🌊 Sending to TTS: "How can I help you today?" (27 chars)
🔊 Playing TTS audio (sentence 2)
```

**For real-time streaming debug:**
```bash
docker logs voxbridge-api --follow | grep -E "(🌊|streaming)"
```

**To analyze specific aspects:**
```bash
# Sentence splitting only
docker logs voxbridge-api --tail 300 | grep "sentence detected"

# TTS calls only
docker logs voxbridge-api --tail 300 | grep "Sending to TTS"

# Buffer state
docker logs voxbridge-api --tail 300 | grep "buffer"
```

**Common issues to look for:**
- ❌ Chunks arriving but no sentences detected → Check sentence splitting logic
- ❌ Sentences detected but no TTS calls → Check Chatterbox connection
- ❌ TTS calls but no audio playback → Check Discord voice connection
