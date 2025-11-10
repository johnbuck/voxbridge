# Discord Plugin Finalization - Completion Plan

**Created**: October 28, 2025 23:07 UTC
**Orchestrator**: voxbridge-2.0-orchestrator
**Priority**: CRITICAL - User blocked
**Estimated Duration**: 1-2 hours

---

## Problem Statement

**Current State**:
- ✅ DiscordPlugin class exists (81KB, src/plugins/discord_plugin.py)
- ✅ PluginManager exists (22KB, src/services/plugin_manager.py)
- ✅ Plugin UI exists (PluginsPage.tsx)
- ✅ Plugin API endpoints exist (/api/plugins, /api/plugins/stats)
- ❌ **BUT: No plugins are actually loaded**
- ❌ discord_bot.py doesn't initialize PluginManager
- ❌ No agents have Discord plugin configuration
- ❌ Discord bot still runs as monolithic app

**Gap**: The plugin infrastructure exists but Discord bot is not using it. Phase 6.4 created the DiscordPlugin class but never integrated it into the bot startup sequence.

**User Expectation**: Discord bot should appear as a plugin in the /plugins UI and be managed through the plugin system.

---

## Completion Tasks

### Task 1: Analyze DiscordPlugin Integration Requirements
**Owner**: voxbridge-2.0-orchestrator (self)
**Duration**: 15 minutes

**Actions**:
1. Read DiscordPlugin class (src/plugins/discord_plugin.py)
2. Identify what configuration it expects
3. Understand how it hooks into bot events
4. Document initialization requirements

**Deliverables**:
- List of required Discord plugin config fields
- Initialization sequence documented
- Integration points identified

---

### Task 2: Design Discord Plugin Configuration Schema
**Owner**: database-architect (sub-agent)
**Duration**: 15 minutes

**Brief for Sub-Agent**:
```
Design Discord plugin configuration schema for agent.plugins JSONB field.

**Requirements**:
1. Support Discord bot token (encrypted)
2. Support voice channel settings (join on startup, auto-reconnect)
3. Support Discord-specific settings (command prefix, admin roles)
4. Must work with PluginManager.initialize_agent_plugins()

**Constraints**:
- Schema must be stored in agent.plugins JSONB
- Must include "enabled": true/false flag
- Bot token MUST be encrypted using PluginEncryption
- Schema should be extensible for future Discord features

**Deliverables**:
1. JSON schema example
2. Explanation of each field
3. Encryption approach for bot_token
```

**Expected Output**:
```json
{
  "discord": {
    "enabled": true,
    "bot_token_encrypted": "encrypted_token_here",
    "auto_join_voice": true,
    "command_prefix": "!",
    "admin_roles": [],
    "status_message": "VoxBridge AI Assistant"
  }
}
```

---

### Task 3: Update Default Agent with Discord Plugin Config
**Owner**: voxbridge-2.0-orchestrator (self)
**Duration**: 10 minutes

**Actions**:
1. Use database-architect schema from Task 2
2. Encrypt Discord token using PluginEncryption
3. Update "Auren (Default)" agent with Discord plugin config
4. Execute SQL UPDATE statement

**SQL**:
```sql
UPDATE agents
SET plugins = {
  "discord": {
    "enabled": true,
    "bot_token_encrypted": "<encrypted_token>",
    "auto_join_voice": true,
    "command_prefix": "!",
    "status_message": "VoxBridge AI Assistant"
  }
}::jsonb
WHERE name = 'Auren (Default)';
```

**Verification**:
```sql
SELECT id, name, plugins FROM agents WHERE name = 'Auren (Default)';
```

---

### Task 4: Integrate PluginManager into discord_bot.py
**Owner**: extension-builder (sub-agent)
**Duration**: 30 minutes

**Brief for Sub-Agent**:
```
Integrate PluginManager into discord_bot.py to load Discord plugin at startup.

**Current State**:
- discord_bot.py is a monolithic bot (1200+ lines)
- No PluginManager import or initialization
- Bot runs directly via discord.Client

**Target State**:
- PluginManager initialized in startup sequence
- Default agent loaded with Discord plugin
- Discord plugin handles all bot events
- Existing functionality preserved

**Integration Points**:
1. Import PluginManager from src.services.plugin_manager
2. Initialize PluginManager in startup (@app.on_event("startup"))
3. Load default agent (Auren) with Discord plugin
4. Pass bot instance to Discord plugin
5. Let plugin handle on_ready, on_message, on_voice_state_update events

**Requirements**:
- Must preserve existing bot functionality
- Must not break voice chat, STT, TTS
- Must maintain backward compatibility
- Plugin should handle all Discord events

**Deliverables**:
1. Modified discord_bot.py with PluginManager integration
2. Preserve all existing features (voice, STT, TTS, n8n webhooks)
3. Add logging: "🔌 Loaded Discord plugin for agent {agent_name}"
```

**Expected Changes**:
- Add PluginManager import
- Add plugin_manager global variable
- Initialize in startup event
- Load default agent's Discord plugin
- Keep all existing /api/* endpoints working

---

### Task 5: Test Discord Plugin Loading
**Owner**: voxbridge-2.0-orchestrator (self)
**Duration**: 15 minutes

**Test Plan**:
1. Restart discord bot container
2. Check logs for "🔌 Loaded Discord plugin"
3. Verify bot connects to Discord gateway
4. Check /api/plugins endpoint shows Discord plugin
5. Check /plugins UI shows Discord plugin card
6. Test voice chat still works
7. Test STT/TTS still works

**Success Criteria**:
- ✅ Bot starts without errors
- ✅ Discord plugin appears in /api/plugins
- ✅ Plugin shows in UI with "running" status
- ✅ Resource usage displayed (CPU%, RAM)
- ✅ Voice chat functional
- ✅ STT/TTS functional
- ✅ All existing features working

**Failure Recovery**:
- If bot fails to start: Revert changes, analyze error logs
- If plugin not loaded: Check agent.plugins configuration
- If voice broken: Check event routing in DiscordPlugin

---

### Task 6: Update Documentation
**Owner**: api-documenter (sub-agent)
**Duration**: 15 minutes

**Brief for Sub-Agent**:
```
Update VoxBridge documentation to reflect Discord plugin integration.

**Files to Update**:
1. docs/progress/voxbridge-2.0-progress.md
   - Update Phase 6.4 status to actually complete
   - Add "Discord Plugin Integration" section
   - Document configuration schema

2. CLAUDE.md
   - Add "Discord Plugin" section
   - Document how to configure Discord plugin for agents
   - Add troubleshooting for plugin issues

3. AGENTS.md
   - Update plugin section with Discord plugin example
   - Document PluginManager integration

**Deliverables**:
1. Updated progress document with accurate completion status
2. CLAUDE.md with Discord plugin configuration guide
3. AGENTS.md with plugin architecture updates
```

---

### Task 7: Git Commit and Progress Update
**Owner**: voxbridge-2.0-orchestrator (self)
**Duration**: 10 minutes

**Actions**:
1. Review all changes made
2. Create comprehensive git commit
3. Update progress document with completion status
4. Report final status to user

**Commit Message**:
```
feat(phase6.4): finalize Discord plugin integration

Complete Discord plugin migration by:
- Adding Discord plugin config to default agent
- Integrating PluginManager into discord_bot.py startup
- Loading Discord plugin for all bot events
- Verifying plugin appears in /plugins UI

This completes Phase 6.4: Discord Plugin, enabling:
- Discord bot as a managed plugin
- Plugin lifecycle control via UI
- Resource monitoring for Discord plugin
- Foundation for multi-agent Discord bots

Fixes: Discord plugin infrastructure existed but wasn't integrated
Result: Discord bot now runs as a plugin, visible in /plugins UI

Phase 6.4 now ACTUALLY complete. 🎉
```

---

## Risk Mitigation

### Risk 1: Breaking Existing Functionality
**Mitigation**:
- Preserve all existing event handlers
- Test voice/STT/TTS after changes
- Keep rollback plan ready

### Risk 2: Plugin Not Loading
**Mitigation**:
- Validate agent.plugins schema before loading
- Add detailed error logging
- Check PluginEncryption works correctly

### Risk 3: Performance Degradation
**Mitigation**:
- PluginManager adds minimal overhead
- Resource monitor tracks actual usage
- Profile if needed

---

## Success Metrics

**Phase 6.4 is complete when**:
1. ✅ Discord bot initializes PluginManager at startup
2. ✅ Default agent has Discord plugin configured
3. ✅ Discord plugin loaded and running
4. ✅ /api/plugins returns Discord plugin with "running" status
5. ✅ /plugins UI shows Discord plugin card with resource usage
6. ✅ Voice chat, STT, TTS all functional
7. ✅ Bot responds to commands as before
8. ✅ No performance degradation
9. ✅ Documentation updated
10. ✅ Committed to git

---

## Timeline

**Total Duration**: 1-2 hours

| Task | Duration | Start | Dependencies |
|------|----------|-------|--------------|
| Task 1: Analysis | 15 min | Now | None |
| Task 2: Schema Design | 15 min | After Task 1 | Task 1 |
| Task 3: Agent Config | 10 min | After Task 2 | Task 2 |
| Task 4: Bot Integration | 30 min | After Task 3 | Task 3 |
| Task 5: Testing | 15 min | After Task 4 | Task 4 |
| Task 6: Documentation | 15 min | Parallel with Task 5 | Task 4 |
| Task 7: Commit | 10 min | After all | All |

**Expected Completion**: October 28, 2025 at ~23:30 UTC

---

## User Approval

**Ready to execute this plan?**

This plan will:
- ✅ Actually integrate Discord as a plugin (not just create the class)
- ✅ Make Discord bot appear in /plugins UI
- ✅ Preserve all existing functionality
- ✅ Complete Phase 6.4 properly
- ✅ Be done in 1-2 hours

**User confirmation needed before proceeding.**
