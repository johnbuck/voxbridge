# Phase 6.4.1 Phase 4 Batch 2: Discord Bot Deprecation & Migration
# Orchestration Plan

**Date**: October 28, 2025
**Status**: 🔄 IN PROGRESS
**Branch**: `feature/discord-plugin-voice-integration`
**Estimated Effort**: 13-19 hours (1-2 days)

---

## 🎯 Objective

Complete the Discord plugin migration by deprecating the old `discord_bot.py` voice functionality and establishing the plugin system as the primary Discord bot implementation.

---

## 🔄 Orchestration Strategy

### Dependency Graph

```
Batch 1: FastAPI Decoupling
    ├─→ Batch 2a: Bot Deprecation
    │       └─→ Batch 3: Agent Routing
    └─→ Batch 2b: Frontend Plugin UI
            └─→ Batch 4: Testing
                    └─→ Batch 5: Documentation
```

### Parallel Execution

- **Batch 2a + 2b** can run in parallel (both depend on Batch 1)
- All other batches are sequential

---

## 📋 Task Breakdown

### Batch 1: FastAPI Decoupling (3-4 hours, HIGH priority)

**Objective**: Extract FastAPI application from `discord_bot.py` to standalone `src/api/server.py`

**Sub-Agent**: `general-purpose`

**Deliverables**:
1. Create `src/api/server.py` with FastAPI app initialization
2. Move all route registrations to server module
3. Keep startup/shutdown hooks for plugin initialization
4. Update `docker-compose.yml` to run server independently
5. Ensure all existing API endpoints still functional

**Files to Create**:
- `src/api/server.py` (~200-300 lines)

**Files to Modify**:
- `src/discord_bot.py` (remove FastAPI app creation)
- `docker-compose.yml` (update command)

**Success Criteria**:
- FastAPI server runs independently
- All existing endpoints respond correctly
- Plugin initialization still works on startup
- Zero breaking changes to API

**Testing**:
- Verify `/health` endpoint works
- Verify `/api/agents` endpoint works
- Verify WebSocket endpoints work
- Check startup logs show plugin initialization

---

### Batch 2a: Discord Bot Graceful Deprecation (2-3 hours, HIGH priority)

**Objective**: Disable old Discord bot voice handlers and route through plugin system

**Sub-Agent**: `general-purpose`

**Dependencies**: Batch 1 (FastAPI decoupling)

**Deliverables**:
1. Add `USE_LEGACY_DISCORD_BOT` environment variable
2. Disable old bot's voice event handlers when legacy mode disabled
3. Route all Discord events through plugin system
4. Keep old code as commented fallback for rollback

**Files to Modify**:
- `src/discord_bot.py` (add legacy mode toggle, disable old handlers)
- `.env.example` (document new environment variable)
- `docker-compose.yml` (set `USE_LEGACY_DISCORD_BOT=false`)

**Success Criteria**:
- Legacy bot disabled by default
- Plugin system handles all Discord voice events
- Rollback available via environment variable
- No voice functionality breaking

**Testing**:
- Join Discord voice channel via API
- Speak in voice channel, verify STT → LLM → TTS pipeline
- Verify plugin handles events, not old bot
- Test rollback by setting `USE_LEGACY_DISCORD_BOT=true`

---

### Batch 2b: Frontend Plugin Management UI (3-4 hours, MEDIUM priority)

**Objective**: Build UI for monitoring and controlling plugin status

**Sub-Agent**: `general-purpose`

**Dependencies**: Batch 1 (FastAPI decoupling - needs API endpoints)

**Deliverables**:
1. Create `PluginsPage.tsx` with plugin list
2. Display active plugins with status indicators (running/stopped/error)
3. Show resource usage from Phase 6.3 monitoring
4. Add start/stop/restart controls per plugin
5. Display plugin logs and errors
6. Real-time updates via WebSocket

**Files to Create**:
- `frontend/src/pages/PluginsPage.tsx` (~200-300 lines)
- `frontend/src/components/PluginStatusCard.tsx` (~100-150 lines)
- `frontend/src/api/plugins.ts` (~50-100 lines)

**Files to Modify**:
- `frontend/src/App.tsx` (add route)
- `frontend/src/components/Navigation.tsx` (add nav link)

**Success Criteria**:
- PluginsPage displays all active plugins
- Real-time status updates work
- Start/stop/restart controls functional
- Resource monitoring data visible

**Testing**:
- Navigate to /plugins page
- Verify Discord plugin shown with "Running" status
- Click "Restart" button, verify plugin restarts
- Check resource usage graph updates

---

### Batch 3: Default Agent Routing (2-3 hours, MEDIUM priority)

**Objective**: Implement guild/channel → agent mapping for multi-agent support

**Sub-Agent**: `general-purpose`

**Dependencies**: Batch 2a (bot deprecation - needs plugin system primary)

**Deliverables**:
1. Implement guild/channel → agent mapping logic
2. Use Phase 4 Batch 1 default agent cache
3. Add fallback to first Discord-enabled agent
4. Add `/agent select <name>` Discord command
5. Store mapping in database or configuration

**Files to Modify**:
- `src/services/plugin_manager.py` (add routing logic)
- `src/plugins/discord_plugin.py` (implement agent selection)

**Files to Create** (Optional):
- Database migration for guild/channel mapping table

**Success Criteria**:
- Correct agent responds to Discord voice events
- `/agent select` command works
- Default agent used when no preference set
- Mapping persists across restarts

**Testing**:
- Join voice channel, verify default agent responds
- Use `/agent select CustomerSupport`, verify agent switch
- Restart server, verify mapping persists

---

### Batch 4: Comprehensive Testing (2-3 hours, HIGH priority)

**Objective**: Create integration and E2E tests for migration

**Sub-Agent**: `general-purpose`

**Dependencies**: Batches 1, 2a, 2b, 3 (all implementation complete)

**Deliverables**:
1. Integration tests for voice event flow
2. Multi-agent scenario tests
3. Agent selection and routing tests
4. API endpoint E2E tests
5. Frontend UI tests (optional)

**Files to Create**:
- `tests/integration/test_discord_plugin_migration.py` (~300-500 lines)
- `tests/e2e/test_voice_pipeline.py` (~200-300 lines)

**Success Criteria**:
- Integration tests passing
- E2E tests passing
- Code coverage ≥85% for migration code
- Zero breaking changes to existing tests

**Testing**:
- Run `./test.sh tests/integration/test_discord_plugin_migration.py -v`
- Run `./test.sh tests/e2e/test_voice_pipeline.py -v`
- Check coverage report

---

### Batch 5: Migration Documentation (1-2 hours, LOW priority)

**Objective**: Document migration process and update architecture docs

**Sub-Agent**: `general-purpose`

**Dependencies**: Batch 4 (testing complete)

**Deliverables**:
1. Create `MIGRATION_GUIDE.md` with step-by-step instructions
2. Update `ARCHITECTURE.md` with new plugin architecture
3. Update `CLAUDE.md` with new key files
4. Add deprecation notices to old code

**Files to Create**:
- `docs/MIGRATION_GUIDE.md` (~500-800 lines)

**Files to Modify**:
- `ARCHITECTURE.md` (update current status)
- `CLAUDE.md` (update key files section)
- `src/discord_bot.py` (add deprecation comments)

**Success Criteria**:
- Migration guide is clear and actionable
- ARCHITECTURE.md reflects new structure
- CLAUDE.md updated with new files
- Deprecation warnings in legacy code

---

## 🎯 Success Metrics

### Functional Requirements

- [ ] FastAPI server runs independently of Discord bot
- [ ] Plugin system handles all Discord voice events
- [ ] Legacy bot disabled by default (toggle available)
- [ ] Default agent routing working
- [ ] Frontend plugin management UI operational
- [ ] `/agent select` command working

### Testing Requirements

- [ ] Integration tests passing (voice pipeline end-to-end)
- [ ] E2E tests passing (multi-agent scenario)
- [ ] Code coverage ≥85% for migration code
- [ ] Zero breaking changes to existing API endpoints

### Documentation Requirements

- [ ] Migration guide complete
- [ ] ARCHITECTURE.md updated
- [ ] CLAUDE.md updated
- [ ] Deprecation warnings in legacy code

### Performance Requirements

- [ ] No latency regression vs Phase 4 Batch 1
- [ ] Resource monitoring shows acceptable plugin overhead
- [ ] Cache hit rate ≥95% for default agent selection

---

## 📊 Progress Tracking

| Batch | Task | Status | Estimated | Actual | Assignee |
|-------|------|--------|-----------|--------|----------|
| 1 | FastAPI Decoupling | 🔄 Pending | 3-4h | - | Sub-Agent 1 |
| 2a | Bot Deprecation | 📋 Queued | 2-3h | - | Sub-Agent 2 |
| 2b | Frontend Plugin UI | 📋 Queued | 3-4h | - | Sub-Agent 3 |
| 3 | Agent Routing | 📋 Queued | 2-3h | - | Sub-Agent 4 |
| 4 | Testing | 📋 Queued | 2-3h | - | Sub-Agent 5 |
| 5 | Documentation | 📋 Queued | 1-2h | - | Sub-Agent 6 |
| **TOTAL** | | | **13-19h** | - | |

---

## 🚨 Risk Mitigation

### Risk: Breaking existing Discord bot functionality

**Mitigation**:
- Legacy mode toggle allows instant rollback
- Comprehensive integration tests before deployment
- Keep old code as commented fallback

**Contingency**: Set `USE_LEGACY_DISCORD_BOT=true` and restart

---

### Risk: Performance degradation

**Mitigation**:
- Phase 4 Batch 1 already implemented caching (10,000x faster)
- Phase 6.3 resource monitoring tracks performance
- Load testing before production deployment

**Contingency**: Optimize caching or rollback to legacy bot

---

### Risk: User confusion during migration

**Mitigation**:
- Clear migration guide with step-by-step instructions
- Deprecation warnings in legacy code
- Update README with migration instructions

**Contingency**: Provide rollback instructions in migration guide

---

## 🔗 Related Documentation

- **Phase 4 Batch 1**: `/home/wiley/Docker/voxbridge/PHASE4_BATCH1_IMPLEMENTATION_SUMMARY.md`
- **VoxBridge 2.0 Plan**: `/home/wiley/Docker/voxbridge/docs/architecture/voxbridge-2.0-transformation-plan.md`
- **Plugin Architecture**: `/home/wiley/Docker/voxbridge/src/plugins/README.md`
- **Analysis Report**: Generated by sub-agent analysis (in conversation history)

---

## 📝 Notes

- **Branch**: Work on `feature/discord-plugin-voice-integration` (already exists)
- **Commits**: Commit after each batch completes
- **Reviews**: Orchestrator reviews each batch before proceeding to next
- **Testing**: Run tests after each batch to catch issues early

---

**Orchestrator**: Claude Code (VoxBridge 2.0 Orchestrator Mode)
**Created**: October 28, 2025, 2:00 PM
**Last Updated**: October 28, 2025, 2:00 PM
