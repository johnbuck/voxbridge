---
description: Tail Discord bot logs (filtered)
---

View real-time logs from the VoxBridge Discord bot container, filtered to remove noisy health check requests.

Execute the following command to tail logs:

```bash
docker logs voxbridge-api --tail 100 --follow | grep -v "GET /health"
```

This will:
- Show last 100 log lines (`--tail 100`)
- Follow new logs in real-time (`--follow`)
- Filter out health check requests (`grep -v "GET /health"`)

**Log emoji guide:**
- 🎤 Voice/audio events
- 📡 Network/webhook events
- ⏱️ Latency measurements
- 🌊 Streaming responses
- 💭 Thinking indicators
- 🔊 TTS playback
- ✅ Success events
- ❌ Error events

**To stop:** Press `Ctrl+C`

**Variations:**
- More lines: `--tail 200` or `--tail 500`
- No filtering: Remove `| grep -v "GET /health"`
- Specific events: `| grep "LATENCY"` or `| grep "🌊"`
