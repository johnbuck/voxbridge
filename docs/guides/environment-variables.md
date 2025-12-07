# Environment Variables Guide

Complete reference for all VoxBridge environment variables.

---

## Required Variables

These must be set for VoxBridge to function:

| Variable | Description | Example |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Discord bot token | `MTIz...` |
| `N8N_WEBHOOK_URL` | n8n webhook for AI responses | `https://n8n.example.com/webhook/...` |
| `CHATTERBOX_URL` | Chatterbox TTS API URL | `http://chatterbox:4800` |
| `CHATTERBOX_VOICE_ID` | Voice ID for TTS | `default` |

---

## Database (VoxBridge 2.0)

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `voxbridge` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `voxbridge_dev_password` | PostgreSQL password |
| `POSTGRES_DB` | `voxbridge` | PostgreSQL database name |
| `DATABASE_URL` | (auto-constructed) | Full connection string (overrides above) |
| `OPENROUTER_API_KEY` | - | OpenRouter API key for LLM provider |
| `LOCAL_LLM_BASE_URL` | - | Local LLM endpoint (e.g., `http://localhost:11434/v1`) |

---

## Security (API Key Encryption)

| Variable | Description |
|----------|-------------|
| `ENCRYPTION_KEY` | Passphrase for encrypting sensitive API keys (Azure, etc.) |

**Notes**:
- If not set, API keys are stored in plaintext (not recommended for production)
- Falls back to `PLUGIN_ENCRYPTION_KEY` for backward compatibility
- Used by: `src/utils/encryption.py`

---

## Discord Bot Mode

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_LEGACY_DISCORD_BOT` | `false` | Toggle between new plugin-based bot and legacy handlers |

**Values**:
- `false` (recommended) - Uses new plugin system
- `true` - Re-enables legacy Discord bot handlers (deprecated)

**Note**: Legacy mode will be removed in VoxBridge 3.0. See [docs/MIGRATION_GUIDE.md](../MIGRATION_GUIDE.md).

---

## Optional (with defaults)

| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPER_SERVER_URL` | `ws://whisperx:4901` | WhisperX WebSocket URL |
| `SILENCE_THRESHOLD_MS` | `600` | Silence detection threshold (ms) |
| `MAX_SPEAKING_TIME_MS` | `45000` | Maximum speaking time (45s) |
| `USE_STREAMING` | `true` | Enable streaming responses |
| `USE_CLAUSE_SPLITTING` | `true` | Split on clauses for lower latency |
| `USE_THINKING_INDICATORS` | `true` | Play thinking sound during AI processing |
| `THINKING_INDICATOR_PROBABILITY` | `0.8` | Probability of playing indicator (0.0-1.0) |

---

## Streaming Configuration

These settings control LLM response streaming and TTS chunking. Can be configured via:
1. **Environment variables** (default values, restored on container restart)
2. **Frontend settings page** (runtime overrides at http://localhost:4903/settings/chatterbox)

| Variable | Default | Description |
|----------|---------|-------------|
| `STREAMING_ENABLED` | `true` | Enable LLM response streaming |
| `STREAMING_CHUNKING_STRATEGY` | `sentence` | How to chunk responses: `sentence`, `paragraph`, `word`, `fixed` |
| `STREAMING_MIN_CHUNK_LENGTH` | `10` | Minimum chunk length before TTS synthesis (5-200 chars) |
| `STREAMING_MAX_CONCURRENT_TTS` | `3` | Maximum concurrent TTS synthesis requests (1-8) |
| `STREAMING_ERROR_STRATEGY` | `retry` | Error handling: `skip`, `retry`, `fallback` |
| `STREAMING_INTERRUPTION_STRATEGY` | `graceful` | Interruption handling: `immediate`, `graceful`, `drain` |

**Note**: Runtime changes via frontend persist until container restart, then environment defaults are restored.

---

## WhisperX Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPERX_MODEL` | `small` | Model size: `tiny`, `base`, `small`, `medium`, `large-v2` |
| `WHISPERX_DEVICE` | `auto` | Device selection: `auto`, `cuda`, `cpu` |
| `WHISPERX_COMPUTE_TYPE` | `float16` | Computation type: `float16` (GPU), `int8` (CPU) |
| `WHISPERX_BATCH_SIZE` | `16` | Batch size for transcription |

---

## Memory Summarization

Background worker that clusters semantically similar old facts and summarizes them using an LLM.

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_SUMMARIZATION` | `true` | Enable/disable summarization |
| `SUMMARIZATION_INTERVAL_HOURS` | `24` | Background worker interval (hours) |
| `SUMMARIZATION_MIN_AGE_DAYS` | `7` | Only summarize facts older than this |
| `SUMMARIZATION_MIN_CLUSTER_SIZE` | `3` | Minimum facts to form a cluster |
| `SUMMARIZATION_MAX_CLUSTER_SIZE` | `8` | Maximum facts per cluster |
| `SUMMARIZATION_SIMILARITY_THRESHOLD` | `0.6` | Embedding similarity threshold (0.0-1.0) |
| `SUMMARIZATION_LLM_PROVIDER` | `local` | LLM provider: `local`, `openrouter` |
| `SUMMARIZATION_LLM_MODEL` | `gpt-oss:20b` | Model for summarization |
| `LOCAL_LLM_BASE_URL` | `http://ollama:11434/v1` | Ollama endpoint on pinkleberry_bridge network |

**Manual Trigger**:
```bash
curl -X POST http://localhost:4900/api/summarization/run | python3 -m json.tool
```

---

## Example .env File

```bash
# Required
DISCORD_TOKEN=your_discord_token_here
N8N_WEBHOOK_URL=https://n8n.example.com/webhook/voxbridge
CHATTERBOX_URL=http://chatterbox:4800
CHATTERBOX_VOICE_ID=default

# Database
POSTGRES_USER=voxbridge
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=voxbridge

# LLM Providers (optional)
OPENROUTER_API_KEY=your_openrouter_key
LOCAL_LLM_BASE_URL=http://ollama:11434/v1

# Security (recommended for production)
ENCRYPTION_KEY=your_encryption_passphrase

# Streaming (defaults shown)
STREAMING_ENABLED=true
STREAMING_CHUNKING_STRATEGY=sentence
STREAMING_MIN_CHUNK_LENGTH=10
STREAMING_MAX_CONCURRENT_TTS=3

# WhisperX (defaults shown)
WHISPERX_MODEL=small
WHISPERX_DEVICE=auto
WHISPERX_COMPUTE_TYPE=float16
```

---

## Related Files

- `.env.example` - Template with all variables
- `docker-compose.yml` - Default values and service configuration
- `src/config/streaming.py` - Streaming configuration dataclass
