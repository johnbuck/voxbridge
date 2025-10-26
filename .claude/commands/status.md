---
description: Check VoxBridge services health and metrics
---

Check the health and status of all VoxBridge services and display current performance metrics.

Execute the following commands to check status:

```bash
# Check health status
curl -s http://localhost:4900/health | python3 -m json.tool

# Check detailed metrics
curl -s http://localhost:4900/metrics | python3 -m json.tool

# Check Docker container status
docker compose ps
```

## Health Endpoint Output

Expected response from `/health`:
```json
{
  "status": "ok",
  "botReady": true,
  "inVoiceChannel": true,
  "speakerLocked": false,
  "activeSpeaker": null,
  "timestamp": "2025-10-26T12:34:56.789Z"
}
```

**Status fields:**
- `status`: Overall health ("ok" or "error")
- `botReady`: Discord bot is connected and ready
- `inVoiceChannel`: Bot is in a voice channel
- `speakerLocked`: Someone is currently speaking
- `activeSpeaker`: Discord user ID of current speaker (null if none)

## Metrics Endpoint Output

Expected response from `/metrics`:
```json
{
  "uptime": 3600.5,
  "totalRequests": 42,
  "activeConnections": 1,
  "latencyMetrics": {
    "stt": { "min": 120.5, "max": 450.2, "avg": 245.8, "samples": 25 },
    "tts": { "min": 80.1, "max": 200.5, "avg": 125.3, "samples": 25 },
    "n8n": { "min": 500.0, "max": 2500.0, "avg": 1200.5, "samples": 25 },
    "thinkingIndicatorDuration": { "min": 0.5, "max": 3.2, "avg": 1.8, "samples": 20 }
  }
}
```

**Metrics tracked:**
- Uptime in seconds
- Total API requests processed
- Active WebSocket connections
- Latency statistics (min/max/avg/samples)

## Container Status

Expected output from `docker compose ps`:
```
NAME                     STATUS         PORTS
voxbridge-discord        Up 2 hours     0.0.0.0:4900->4900/tcp
voxbridge-whisperx       Up 2 hours     0.0.0.0:4901->4901/tcp, 0.0.0.0:4902->4902/tcp
voxbridge-frontend       Up 2 hours     0.0.0.0:4903->80/tcp
```

**Status should be:**
- "Up X hours/minutes" for healthy services
- "Exit 1" or "Restarting" indicates problems

## Troubleshooting

**If health check fails:**
1. Check Docker logs: `docker logs voxbridge-discord --tail 50`
2. Verify Discord token: Check .env file
3. Verify network: `docker network ls | grep bot-network`

**If metrics show high latency:**
1. Check STT latency → May need smaller WhisperX model
2. Check TTS latency → Verify Chatterbox is running
3. Check n8n latency → n8n workflow may be slow

**If containers are down:**
1. Check logs: `docker logs voxbridge-discord --tail 100`
2. Restart: `docker compose restart`
3. Rebuild if needed: See `/rebuild` command
