# Discord Plugin UX Architecture Plan

**Created**: October 28, 2025 23:18 UTC
**Status**: NEEDS IMPLEMENTATION
**Priority**: HIGH - Blocks user adoption

---

## Current Problems

### 1. No UI for Plugin Configuration ❌
**Problem**: Users cannot configure Discord plugin through the UI.

**Current Reality**:
- Agent form (`AgentForm.tsx`) doesn't expose `plugins` field
- Had to manually update database to add Discord plugin to "Auren (Default)"
- No way to add Discord bot token through UI
- No way to enable/disable Discord plugin per agent

**User Experience**: Unusable - requires database access and Python scripting

---

### 2. /discord-bot Route is Ambiguous ❌
**Problem**: `/discord-bot` page assumes monolithic architecture, but Discord is now a plugin.

**Current State**:
- `/discord-bot` shows voice controls for "the bot"
- But there's no longer "the bot" - each agent can have its own Discord bot
- Voice controls (join/leave) should be per-plugin, not global
- Speaker lock is global state, not per-Discord-bot

**User Confusion**:
- "Which Discord bot am I controlling?"
- "How do I control voice for Agent A vs Agent B if both have Discord plugins?"

---

### 3. Plugin Lifecycle Management Missing ❌
**Problem**: Users can see plugins in `/plugins` UI but can't create/configure them.

**Current State**:
- `/plugins` page shows running plugins ✅
- Can theoretically start/stop plugins via API ✅
- But can't ADD Discord plugin to an agent ❌
- Can't configure bot token ❌
- Can't set channels, auto_join, etc. ❌

---

## Architectural Vision

### Multi-Agent Discord Bot System

**Design Principle**: Each agent is independent with its own optional Discord bot.

```
Agent "Auren"
└── Discord Plugin (enabled)
    ├── Bot Token: MTIzNDU2...
    ├── Bot Instance: Auren#8659
    ├── Voice Channel: General
    └── Auto-join: true

Agent "TechSupport"
└── Discord Plugin (enabled)
    ├── Bot Token: MTc4OTAx...
    ├── Bot Instance: TechSupport#1234
    ├── Voice Channel: Support
    └── Auto-join: false

Agent "Creative Writer"
└── No Discord Plugin (disabled)
```

**Key Insight**: Discord is just ONE plugin type. The architecture should support ANY plugin (Discord, Telegram, Slack, n8n, etc.)

---

## Recommended UX Solutions

### Solution 1: Add Plugin Configuration to Agent Form ⭐ **RECOMMENDED**

**Approach**: Extend `AgentForm.tsx` with "Plugins" accordion section.

**UI Mockup**:
```
┌────────────────────────────────────────┐
│ Create New Agent                     │
├────────────────────────────────────────┤
│ Name: Auren                            │
│ System Prompt: [...]                   │
│ LLM Provider: OpenRouter               │
│ ...                                    │
│                                        │
│ ▼ Plugins (Optional)                   │
│   ┌──────────────────────────────────┐ │
│   │ □ Discord Bot                    │ │
│   │   When enabled, this agent will  │ │
│   │   connect to Discord as a bot.   │ │
│   │                                  │ │
│   │   ☑ Enable Discord Plugin        │ │
│   │                                  │ │
│   │   Bot Token: *******************│ │
│   │   [Get Token from Discord Dev]   │ │
│   │                                  │ │
│   │   ☑ Auto-join voice channels     │ │
│   │   Command Prefix: !              │ │
│   │   Allowed Channels: (optional)   │ │
│   └──────────────────────────────────┘ │
│                                        │
│   ┌──────────────────────────────────┐ │
│   │ □ n8n Webhook (Coming Soon)      │ │
│   └──────────────────────────────────┘ │
│                                        │
│ [Cancel]  [Save Agent]                │
└────────────────────────────────────────┘
```

**Implementation**:
1. Add plugin configuration state to AgentForm
2. Add "Plugins" section with collapsible plugin cards
3. Each plugin type (Discord, n8n, etc.) is a toggle + config form
4. On submit, include `plugins` object in AgentCreateRequest
5. Backend already supports this - just need frontend

**Benefits**:
- ✅ Users can configure plugins when creating/editing agents
- ✅ No database manipulation required
- ✅ Self-service plugin management
- ✅ Extensible to future plugins (n8n, Telegram, Slack)

---

### Solution 2: Deprecate or Transform /discord-bot Route

**Option A: Deprecate and Redirect** (Simplest)
- Remove `/discord-bot` from navigation
- Redirect `/discord-bot` → `/plugins`
- All Discord management happens in `/plugins` UI
- **Rationale**: Discord is no longer special - it's just a plugin

**Option B: Transform to "Discord Plugin Setup Helper"** (Most User-Friendly)
- Rename to "Discord Bot Setup"
- Becomes a wizard/guide for:
  1. Creating Discord bot in Discord Developer Portal
  2. Getting bot token
  3. Inviting bot to server
  4. Configuring agent with Discord plugin
- Links to `/agents` form with Discord plugin pre-selected
- **Rationale**: Discord setup is complex - help users through it

**Option C: Aggregate Discord Plugin Dashboard**
- Show ALL Discord plugin instances across all agents
- Table view: Agent Name | Bot Name | Voice Channel | Status | Actions
- Actions: Join Voice, Leave Voice, View Logs
- **Rationale**: Power users managing multiple Discord bots need overview

**Recommendation**: **Option B** (Setup Helper) for best UX, with link to `/plugins` for management.

---

### Solution 3: Enhance /plugins Page with Configuration

**Approach**: Add "Configure" button to each plugin card that opens modal.

**UI Flow**:
```
/plugins page shows Discord plugin card:

┌─────────────────────────────────┐
│ Discord Plugin                  │
│ Agent: Auren (Default)          │
│ Status: ● Running               │
│ CPU: 0.0% | RAM: 105 MB         │
│                                 │
│ [Configure] [Restart] [Stop]    │
└─────────────────────────────────┘

Click "Configure" → Opens modal:

┌────────────────────────────────┐
│ Configure Discord Plugin       │
├────────────────────────────────┤
│ Agent: Auren (Default)         │
│                                │
│ Bot Token: *****************   │
│ ☑ Auto-join voice channels     │
│ Command Prefix: !              │
│ Allowed Channels: (optional)   │
│                                │
│ [Cancel]  [Save & Restart]     │
└────────────────────────────────┘
```

**Implementation**:
1. Add `onConfigure` handler to PluginStatusCard
2. Create PluginConfigModal component
3. Fetch plugin config from agent.plugins
4. Update agent via PUT /api/agents/{id}
5. Restart plugin to apply changes

**Benefits**:
- ✅ In-place configuration
- ✅ No need to go to /agents page
- ✅ Immediate feedback (restart applies changes)

---

## Implementation Priority

### Phase 1: Enable Self-Service (Critical)
**Duration**: 2-3 hours

1. **Add Plugins Section to AgentForm** ✅ **HIGH PRIORITY**
   - Add Discord plugin toggle + config fields
   - Submit plugins object to backend
   - Test create/edit flows

2. **Update API Types**
   - Add `plugins` to AgentCreateRequest type
   - Add plugin configuration interfaces

3. **Documentation**
   - Update CLAUDE.md with plugin configuration guide
   - Add screenshots to docs

**Success Criteria**:
- User can enable Discord plugin when creating agent
- User can configure bot token through UI
- No database access required

---

### Phase 2: Improve /discord-bot Page (Nice to Have)
**Duration**: 1-2 hours

**Option**: Transform to "Discord Bot Setup Wizard"
- Step-by-step guide for Discord bot creation
- Bot token validation
- Server invitation link generator
- Redirect to agent creation with Discord plugin pre-filled

**Success Criteria**:
- Non-technical users can set up Discord bot
- No external documentation needed

---

### Phase 3: Plugin Configuration Modal (Enhancement)
**Duration**: 1-2 hours

**Feature**: "Configure" button on plugin cards in `/plugins`
- Opens modal with plugin-specific settings
- Save applies changes and restarts plugin
- Eliminates need to go to /agents page

**Success Criteria**:
- Users can reconfigure plugins without leaving /plugins page
- Changes apply immediately with plugin restart

---

## Voice Controls Architecture

**Current Problem**: Voice controls are global, but should be per-Discord-plugin.

### Proposed Solution: Discord Plugin-Specific Controls

**API Changes Needed**:
```
POST /api/plugins/discord/voice/join
{
  "agent_id": "uuid",
  "channel_id": "discord_channel_id",
  "guild_id": "discord_guild_id"
}

POST /api/plugins/discord/voice/leave
{
  "agent_id": "uuid"
}

GET /api/plugins/discord/voice/status
→ Returns voice status for ALL Discord plugins
```

**UI Changes**:
- `/plugins` page shows voice status per Discord plugin card
- Each Discord plugin card has Join/Leave buttons
- Speaker lock is per-plugin (multiple agents can talk simultaneously in different channels)

---

## User Association Flow

### How Users Should Associate Agent with Discord Bot

**Step 1: User Creates Agent**
```
User goes to /agents → Click "Create Agent"
Fills out name, system prompt, LLM settings
Scrolls to "Plugins" section
Toggles "Enable Discord Plugin"
Enters Discord bot token
Saves agent
```

**Step 2: System Automatically Loads Plugin**
```
On agent create/update:
  └─ Backend saves agent.plugins to database
     └─ PluginManager detects plugin config
        └─ Initializes Discord plugin
           └─ Bot connects to Discord
              └─ Plugin appears in /plugins UI as "running"
```

**Step 3: User Manages Plugin**
```
User goes to /plugins
Sees Discord plugin card with "running" status
Can stop/restart/configure as needed
```

---

## Technical Debt to Address

### 1. Agent API Doesn't Accept `plugins` Field
**Problem**: `POST /api/agents` and `PUT /api/agents/{id}` might not accept `plugins` field.

**Check**: Does AgentService.create_agent() accept plugins parameter?

**Fix**: Ensure agent API accepts and stores plugins field.

---

### 2. Frontend Types Missing Plugin Config
**Problem**: TypeScript types for Agent and AgentCreateRequest don't include `plugins`.

**Files to Update**:
- `frontend/src/services/api.ts` - Add `plugins?: Record<string, any>` to Agent type
- AgentForm.tsx - Add plugin state management

---

### 3. Plugin Encryption Handling
**Problem**: Bot tokens should be encrypted before storing in database.

**Current State**: Stored as plain text (security issue!)

**Fix**: Use PluginEncryption service:
```python
from src.plugins.encryption import PluginEncryption

# Encrypt before storing
encrypted_token = PluginEncryption.encrypt(bot_token, agent_id)
agent.plugins = {
  "discord": {
    "enabled": True,
    "bot_token_encrypted": encrypted_token,
    ...
  }
}
```

**Frontend Impact**: Frontend sends plain bot_token, backend encrypts before storing.

---

## Summary of Recommendations

### Immediate Actions (Do This First)
1. ✅ **Add Plugins section to AgentForm.tsx**
   - Discord plugin toggle + bot token input
   - Auto-join toggle, command prefix input

2. ✅ **Update backend to encrypt bot tokens**
   - Use PluginEncryption in AgentService.create_agent()
   - Decrypt when loading plugins

3. ✅ **Update API types**
   - Add `plugins` to Agent and AgentCreateRequest

4. ✅ **Test end-to-end flow**
   - Create agent with Discord plugin through UI
   - Verify plugin loads and bot connects
   - Verify appears in /plugins UI

### Future Enhancements
- Transform /discord-bot into setup wizard
- Add plugin configuration modal to /plugins page
- Add per-plugin voice controls
- Add plugin marketplace/templates

---

## Questions for User

1. **Plugin Configuration Location**: Should users configure plugins in:
   - Option A: Agent creation form (one-stop shop)
   - Option B: Separate /plugins/configure page
   - Option C: Both (create in agent form, edit in plugins page)

2. **/discord-bot Route**: What should happen to this page?
   - Option A: Deprecate and remove
   - Option B: Transform to Discord setup wizard
   - Option C: Keep as aggregate Discord dashboard

3. **Bot Token Input**: How should users provide bot tokens?
   - Option A: Text input (current, requires manual copy-paste from Discord Dev Portal)
   - Option B: OAuth flow (advanced, auto-registers bot)
   - Option C: File upload (.env file with token)

4. **Voice Controls**: Should voice controls be:
   - Option A: Per-plugin (each Discord bot controlled independently)
   - Option B: Global with agent selector dropdown
   - Option C: Both (global default + per-plugin override)

---

**Next Step**: Decide on UX approach, then implement Phase 1 to enable self-service plugin configuration.
