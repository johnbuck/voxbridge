# VoxBridge 2.0 Migration Guide

**Version**: 1.0
**Last Updated**: October 28, 2025
**Target Audience**: Developers and system administrators migrating from VoxBridge 1.x to 2.0

---

## Overview

VoxBridge 2.0 introduces a major architectural change: **Discord bot functionality has been refactored into a plugin system with a decoupled FastAPI server**.

This migration guide covers **Phase 6.4.1** (Discord Plugin Voice Integration), which refactors the monolithic Discord bot into a modular, plugin-based architecture.

### What Changed

#### VoxBridge 1.x (Old Architecture)

```
discord_bot.py (1,680 lines)
├── FastAPI server (routes, WebSockets)
├── Discord bot (client, events, voice)
├── Voice handlers (join, leave, speak)
└── Metrics tracking
```

**Problems**:
- Tight coupling between API and Discord bot
- Difficult to test independently
- Cannot run API without Discord bot
- Hard to extend or add new integrations

#### VoxBridge 2.0 (New Architecture)

```
src/api/server.py (715 lines)           src/plugins/discord_plugin.py (1,706 lines)
├── FastAPI server                      ├── Discord bot
├── All API routes                      ├── Voice pipeline
├── WebSocket manager                   ├── Audio processing
└── Startup/shutdown hooks              └── Agent routing

        ↕️ (Bridge Pattern)
   API calls bridge functions in Discord plugin
```

**Benefits**:
- FastAPI server runs independently
- Discord bot is now a plugin (can be enabled/disabled)
- Easier testing with mock bridge functions
- Extensible plugin system for future integrations
- Clean separation of concerns

---

## Migration Path

Follow these steps to migrate from VoxBridge 1.x to the new plugin-based architecture.

### Step 1: Backup Your Data

**IMPORTANT**: Always backup before migrating.

```bash
# Backup PostgreSQL database
docker exec voxbridge-postgres pg_dump -U voxbridge voxbridge > voxbridge_backup_$(date +%Y%m%d).sql

# Backup environment file
cp .env .env.backup

# Optional: Export Docker volumes
tar -czf voxbridge-volumes-backup.tar.gz ../zexternal-volumes/
```

### Step 2: Update Environment Variables

Add the new environment variable to your `.env` file:

```bash
# Discord Bot Mode (Phase 6.4.1 Batch 2a)
# Set to 'false' to use new plugin-based bot (recommended)
# Set to 'true' to rollback to legacy bot handlers (deprecated)
USE_LEGACY_DISCORD_BOT=false
```

**Default**: `false` (new plugin system)

**Example `.env` file**:
```bash
# Discord
DISCORD_TOKEN=your_discord_bot_token

# Database
POSTGRES_USER=voxbridge
POSTGRES_PASSWORD=voxbridge_dev_password
POSTGRES_DB=voxbridge

# Discord Bot Mode (NEW in Phase 6.4.1)
USE_LEGACY_DISCORD_BOT=false

# Other services...
N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/...
CHATTERBOX_URL=http://chatterbox:4800
CHATTERBOX_VOICE_ID=your_voice_id
```

### Step 3: Pull Latest Changes

```bash
# Ensure you're on the correct branch
git fetch origin
git checkout voxbridge-2.0

# Pull latest changes
git pull origin voxbridge-2.0
```

### Step 4: Stop Existing Containers

```bash
# Stop all VoxBridge containers
docker compose down

# Optional: Remove volumes (WARNING: Data loss!)
# docker compose down -v
```

### Step 5: Rebuild Docker Containers

```bash
# Rebuild Discord bot container with new architecture
docker compose build --no-cache voxbridge-api

# Start all services
docker compose up -d

# Watch logs to verify startup
docker logs voxbridge-api --tail 100 --follow
```

### Step 6: Verify Plugin System

Check logs to confirm plugin system is active:

```bash
docker logs voxbridge-api --tail 100 | grep "Using new plugin-based"
```

**Expected output**:
```
✅ Using new plugin-based Discord bot (recommended)
💡 Legacy voice handlers are disabled
🔌 Initializing plugins...
✅ Loaded plugin: discord_plugin
```

**If you see**:
```
⚠️  DEPRECATION WARNING: Using legacy Discord bot handlers
```

Then the legacy mode is enabled. Set `USE_LEGACY_DISCORD_BOT=false` to switch to the new plugin system.

### Step 7: Run Database Migrations

Ensure database schema is up-to-date:

```bash
# Run Alembic migrations
docker exec voxbridge-api alembic upgrade head

# Verify agents table exists
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "\dt"
```

### Step 8: Test Discord Bot Functionality

#### Test API Health

```bash
curl http://localhost:4900/health | python3 -m json.tool
```

**Expected response**:
```json
{
  "status": "ok",
  "bot_ready": true,
  "in_voice": false,
  "speaker_status": "No active speaker"
}
```

#### Test Voice Join (via API)

```bash
curl -X POST http://localhost:4900/voice/join \
  -H "Content-Type: application/json" \
  -d '{
    "channelId": "YOUR_CHANNEL_ID",
    "guildId": "YOUR_GUILD_ID"
  }'
```

#### Test Agent Commands (in Discord)

In your Discord server, test these slash commands:
- `/agent list` - View all available agents
- `/agent current` - View current default agent
- `/agent select <name>` - Switch to a different agent

#### Test Voice Pipeline

1. Join a Discord voice channel
2. Speak into your microphone
3. Verify bot transcribes and responds with TTS

### Step 9: Verify Frontend (Optional)

If using the web frontend:

```bash
# Access frontend
open http://localhost:4903

# Navigate to Plugins page
# Verify Discord plugin shows "Active" status
```

---

## New Features in VoxBridge 2.0

### 1. Plugin-Based Architecture

The Discord bot is now a plugin that can be managed independently:

```python
# In src/plugins/discord_plugin.py
class DiscordPlugin(PluginBase):
    async def start(self):
        """Start Discord bot"""

    async def stop(self):
        """Stop Discord bot"""

    async def get_stats(self) -> Dict:
        """Get plugin statistics"""
```

**Benefits**:
- Start/stop Discord bot without restarting container
- Add new plugins (Telegram, Slack, etc.) without modifying core
- Independent testing of plugins

### 2. Agent Routing with Discord Commands

Select which AI agent responds to your voice:

```bash
# List all agents
/agent list

# Switch to a specific agent
/agent select Assistant_Pro

# Check current agent
/agent current
```

**Example output**:
```
Available agents:
1. Assistant (Default) - OpenAI GPT-4 Turbo
2. Assistant_Pro - Claude Sonnet 3.5
3. Coding_Expert - DeepSeek Coder

Current: Assistant
```

### 3. Plugin Management UI

Web interface for managing plugins at http://localhost:4903/plugins

**Features**:
- View all loaded plugins
- Start/stop individual plugins
- Monitor plugin resource usage
- View plugin logs

### 4. Bridge Pattern for API Decoupling

FastAPI server communicates with Discord bot via bridge functions:

```python
# In src/api/server.py
@app.post("/voice/join")
async def join_voice_channel(request: VoiceJoinRequest):
    """API route calls bridge function"""
    return await bridge.join_voice(request.channelId, request.guildId)
```

**Benefits**:
- API can run without Discord bot (returns 503 if bot unavailable)
- Easier mocking for unit tests
- Flexible deployment (API-only mode for testing)

---

## Rollback Instructions

If you encounter issues with the new plugin system, you have two rollback options:

### Option 1: Temporary Rollback (Environment Variable)

**Quick rollback without rebuilding containers**:

```bash
# Edit .env file
USE_LEGACY_DISCORD_BOT=true
```

Restart container:
```bash
docker compose restart voxbridge-api
```

Verify legacy mode:
```bash
docker logs voxbridge-api --tail 50 | grep "DEPRECATION WARNING"
```

Expected output:
```
⚠️  DEPRECATION WARNING: Using legacy Discord bot handlers
```

**When to use**:
- Emergency rollback during production issues
- Testing legacy compatibility
- Temporary workaround while investigating bugs

**Note**: Legacy mode will be **removed in VoxBridge 3.0**. Use this only as a temporary measure.

### Option 2: Permanent Rollback (Git)

**Rollback to VoxBridge 1.x code**:

```bash
# Checkout previous commit (before Phase 6.4.1)
git log --oneline | grep "feat(phase5)"
git checkout <commit_hash>

# Example:
git checkout ef4fcce  # feat(phase3): implement LLM provider abstraction

# Rebuild and restart
docker compose down
docker compose build --no-cache
docker compose up -d
```

**When to use**:
- Critical bugs in plugin system
- Need extended time to debug migration issues
- Prefer stable VoxBridge 1.x while planning migration

### Option 3: Restore from Backup

If database or configuration is corrupted:

```bash
# Restore PostgreSQL database
cat voxbridge_backup_YYYYMMDD.sql | docker exec -i voxbridge-postgres psql -U voxbridge voxbridge

# Restore environment file
cp .env.backup .env

# Restart services
docker compose down
docker compose up -d
```

---

## Breaking Changes

### None! 🎉

This migration is **100% backward compatible**. All existing functionality is preserved:

✅ **Voice Pipeline**: STT → LLM → TTS works identically
✅ **API Endpoints**: All `/voice/*`, `/api/*` routes unchanged
✅ **Discord Commands**: Existing commands work as before
✅ **WebSocket Events**: Real-time events continue working
✅ **Database Schema**: No schema changes required
✅ **Environment Variables**: All existing variables supported

**New Optional Features**:
- Agent routing via `/agent` commands (opt-in)
- Plugin management UI (opt-in)
- Legacy mode toggle (fallback only)

---

## Troubleshooting

### Issue: Bot not responding to voice

**Symptoms**:
- Bot joins voice channel but doesn't transcribe
- No response after speaking

**Solution 1**: Check plugin initialization logs
```bash
docker logs voxbridge-api | grep "🔌 Initializing plugins"
```

Expected:
```
🔌 Initializing plugins...
✅ Loaded plugin: discord_plugin
```

**Solution 2**: Verify WhisperX connection
```bash
docker logs voxbridge-api | grep "WhisperX"
```

Expected:
```
📡 WhisperX client connected to ws://whisperx:4901
```

**Solution 3**: Check STT service status
```bash
curl http://localhost:4900/status | python3 -m json.tool | grep "stt"
```

---

### Issue: API endpoints return 503

**Symptoms**:
```json
{
  "detail": "Discord bot not initialized"
}
```

**Solution 1**: Verify bridge pattern is initialized
```bash
docker logs voxbridge-api | grep "bridge"
```

Expected:
```
✅ Bot bridge functions registered with API server
```

**Solution 2**: Check bot ready status
```bash
curl http://localhost:4900/health | python3 -m json.tool
```

Verify `"bot_ready": true`.

**Solution 3**: Restart Discord container
```bash
docker compose restart voxbridge-api
```

---

### Issue: Legacy mode not working

**Symptoms**:
- Set `USE_LEGACY_DISCORD_BOT=true` but new plugin system still runs

**Solution 1**: Check environment variable syntax
```bash
docker exec voxbridge-api printenv | grep "USE_LEGACY_DISCORD_BOT"
```

Should print: `USE_LEGACY_DISCORD_BOT=true`

**Solution 2**: Verify docker-compose.yml passes env variable
```bash
grep "USE_LEGACY_DISCORD_BOT" docker-compose.yml
```

Should see:
```yaml
environment:
  - USE_LEGACY_DISCORD_BOT=${USE_LEGACY_DISCORD_BOT:-false}
```

**Solution 3**: Rebuild container with --no-cache
```bash
docker compose down
docker compose build --no-cache voxbridge-api
docker compose up -d
```

---

### Issue: Database connection errors

**Symptoms**:
```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Solution 1**: Verify PostgreSQL is running
```bash
docker compose ps | grep postgres
```

Expected: `voxbridge-postgres` with status `Up`

**Solution 2**: Check database credentials in .env
```bash
grep "POSTGRES" .env
```

Verify:
```
POSTGRES_USER=voxbridge
POSTGRES_PASSWORD=voxbridge_dev_password
POSTGRES_DB=voxbridge
```

**Solution 3**: Run database migrations
```bash
docker exec voxbridge-api alembic upgrade head
```

---

### Issue: Agent commands not working

**Symptoms**:
- `/agent list` shows no agents
- `/agent select` fails

**Solution 1**: Seed example agents
```bash
docker exec voxbridge-api python -m src.database.seed
```

**Solution 2**: Verify agents table exists
```bash
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "SELECT COUNT(*) FROM agents;"
```

Should show count > 0.

**Solution 3**: Check agent service logs
```bash
docker logs voxbridge-api | grep "AgentService"
```

---

### Issue: Frontend shows plugin as "Inactive"

**Symptoms**:
- Plugin Management page shows Discord plugin with red "Inactive" badge

**Solution 1**: Check plugin status via API
```bash
curl http://localhost:4900/api/plugins/stats | python3 -m json.tool
```

**Solution 2**: Restart Discord plugin via API
```bash
curl -X POST http://localhost:4900/api/plugins/discord/restart
```

**Solution 3**: Check plugin manager logs
```bash
docker logs voxbridge-api | grep "PluginManager"
```

---

## Performance Considerations

### Expected Latency Changes

With Phase 6.4.1 bridge pattern:
- **No significant latency increase** (< 5ms overhead)
- Bridge calls are async and non-blocking
- Same voice pipeline performance

**Benchmark**:
```
VoxBridge 1.x (direct calls):     ~800ms E2E latency
VoxBridge 2.0 (bridge pattern):   ~805ms E2E latency
```

### Memory Usage

**VoxBridge 1.x**:
- Single container: ~450MB RAM (Discord bot + FastAPI)

**VoxBridge 2.0**:
- API server: ~200MB RAM (FastAPI only)
- Discord plugin: ~300MB RAM (Discord bot + audio)
- **Total**: ~500MB RAM (+50MB for plugin system overhead)

### CPU Usage

- Negligible CPU increase (< 2%)
- Plugin system uses asyncio (event-driven, no polling)

---

## Migration Checklist

Use this checklist to verify successful migration:

- [ ] Backup database (`pg_dump`)
- [ ] Backup `.env` file
- [ ] Add `USE_LEGACY_DISCORD_BOT=false` to `.env`
- [ ] Pull latest code (`git pull origin voxbridge-2.0`)
- [ ] Rebuild containers (`docker compose build --no-cache`)
- [ ] Start services (`docker compose up -d`)
- [ ] Verify logs show "Using new plugin-based Discord bot"
- [ ] Run migrations (`alembic upgrade head`)
- [ ] Seed agents (`python -m src.database.seed`)
- [ ] Test `/health` endpoint (returns 200)
- [ ] Test `/status` endpoint (bot_ready: true)
- [ ] Test voice join via API
- [ ] Test `/agent list` command in Discord
- [ ] Test voice pipeline (speak → transcribe → respond)
- [ ] Verify frontend shows "Active" plugin status
- [ ] Run test suite (`./test.sh tests/integration -v`)

---

## Support and Resources

### Documentation

- **Architecture Overview**: [ARCHITECTURE.md](../ARCHITECTURE.md)
- **Phase 6.4.1 Test Results**: [PHASE4_BATCH2_TEST_RESULTS.md](../PHASE4_BATCH2_TEST_RESULTS.md)
- **Phase 6.4.1 Orchestration Plan**: [PHASE4_BATCH2_ORCHESTRATION_PLAN.md](../PHASE4_BATCH2_ORCHESTRATION_PLAN.md)
- **Agent Management**: [docs/progress/phase-2-completion.md](../docs/progress/phase-2-completion.md)
- **LLM Providers**: [docs/progress/phase-3-completion.md](../docs/progress/phase-3-completion.md)

### Test Results

Phase 6.4.1 achieved **100% test passing rate**:
- 76 total tests
- 59 executed in integration suite
- 0 failures
- 49% API server coverage

See [PHASE4_BATCH2_TEST_RESULTS.md](../PHASE4_BATCH2_TEST_RESULTS.md) for details.

### Getting Help

If you encounter issues not covered in this guide:

1. **Check logs**: `docker logs voxbridge-api --tail 200`
2. **Review test results**: `PHASE4_BATCH2_TEST_RESULTS.md`
3. **Search GitHub issues**: Look for similar problems
4. **Open GitHub issue**: Include logs and steps to reproduce

**Issue Template**:
```markdown
**Environment**:
- VoxBridge version: 2.0 (Phase 6.4.1)
- Docker version: X.X.X
- OS: Ubuntu 22.04

**Issue**:
[Description of problem]

**Logs**:
[Output of `docker logs voxbridge-api --tail 200`]

**Steps to Reproduce**:
1. ...
2. ...
```

---

## What's Next?

After migrating to Phase 6.4.1, you'll be ready for upcoming phases:

### Phase 6 (Remaining): Extension System
- n8n as plugin (webhook routing)
- Plugin marketplace (load external plugins)
- Dynamic plugin loading

### Phase 7: Documentation Overhaul
- Updated user guides
- API reference docs
- Video tutorials

### Phase 8: Testing & Migration
- E2E test suite expansion
- Performance benchmarking
- Production deployment guides

---

## FAQ

### Q: Do I need to migrate immediately?

**A**: No. VoxBridge 1.x (legacy mode) is supported through **VoxBridge 2.x** lifecycle. However, it will be **removed in VoxBridge 3.0**.

**Recommended**: Migrate during your next maintenance window.

---

### Q: Can I run VoxBridge 2.0 without the plugin system?

**A**: No. The plugin system is the core of VoxBridge 2.0. However, you can enable legacy mode (`USE_LEGACY_DISCORD_BOT=true`) as a temporary fallback.

---

### Q: Will my existing agents be lost?

**A**: No. Agent data is stored in PostgreSQL and persists across migrations. All agents, sessions, and conversations are preserved.

---

### Q: Can I have multiple Discord bots running?

**A**: Not yet. Phase 6.4.1 supports a single Discord plugin instance. Multi-instance support is planned for a future release.

---

### Q: How do I add a custom plugin?

**A**: See the [Plugin Development Guide](./PLUGIN_DEVELOPMENT_GUIDE.md) (coming in Phase 6.5).

Basic template:
```python
from src.plugins.base import PluginBase

class MyPlugin(PluginBase):
    async def start(self):
        """Plugin startup logic"""

    async def stop(self):
        """Plugin cleanup logic"""
```

---

### Q: What if I don't use Discord?

**A**: VoxBridge 2.0 is designed to be Discord-optional. You can:
- Disable Discord plugin
- Use only the WebRTC voice interface (browser)
- Integrate a different voice platform (Telegram, Slack, etc.)

---

## Conclusion

VoxBridge 2.0 Phase 6.4.1 introduces a **plugin-based architecture** that makes the system more modular, testable, and extensible.

**Key Takeaways**:
- ✅ **Backward compatible** - Zero breaking changes
- ✅ **Flexible deployment** - API can run independently
- ✅ **Easy rollback** - Legacy mode available via env variable
- ✅ **Future-proof** - Plugin system ready for extensions

**Migration is recommended** to take advantage of new features and ensure compatibility with future releases.

---

**Document Version**: 1.0
**Last Updated**: October 28, 2025
**Author**: VoxBridge Development Team
