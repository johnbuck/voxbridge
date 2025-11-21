---
description: Show latency tracking logs
---

View latency measurement logs to analyze VoxBridge performance metrics.

Execute the following command to filter latency logs:

```bash
docker logs voxbridge-api --tail 200 | grep -E "(LATENCY|⏱️)"
```

This will:
- Show last 200 log lines
- Filter for latency-related logs only
- Display all timing measurements

**Latency metrics tracked:**
- STT (Speech-to-Text) duration
- n8n webhook response time
- TTS (Text-to-Speech) generation time
- Audio playback start time
- Thinking indicator duration
- End-to-end conversation latency

Expected output example:
```
⏱️ LATENCY [STT processing]: 245.32ms
⏱️ LATENCY [n8n response]: 1823.45ms
⏱️ LATENCY [TTS generation]: 156.78ms
⏱️ LATENCY [thinking indicator → n8n webhook]: 1.23ms
⏱️ LATENCY [thinking indicator duration]: 2.145s
```

**For real-time monitoring:**
```bash
docker logs voxbridge-api --follow | grep -E "(LATENCY|⏱️)"
```

**To analyze specific metric:**
```bash
docker logs voxbridge-api --tail 500 | grep "thinking indicator"
```
