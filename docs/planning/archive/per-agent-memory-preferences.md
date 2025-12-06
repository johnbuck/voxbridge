> **📁 ARCHIVED**: This document describes a future enhancement (Phase 9) that has not yet been implemented.
> For current memory system status, see [memory-system-enhancements.md](../memory-system-enhancements.md).
> **Last Updated**: November 25, 2025

# Per-Agent Memory Preferences Implementation Plan

**Date**: November 25, 2025
**Branch**: `feature/memory-system`
**Status**: Planning (Future Phase 9)
**Priority**: High (Core UX improvement)

---

## Executive Summary

Refactor VoxBridge's memory hierarchy to enable **per-agent user control** instead of global user toggle. Users will configure memory scope (global vs agent-specific) on a per-agent basis, providing fine-grained control over which agents have access to private vs shared memories.

### Current State

**Three-Tier Hierarchy (Global User Control)**:
```
Tier 1: Admin Policy → allow_agent_specific_memory_globally (system-wide on/off)
Tier 2: User Global Toggle → User.allow_agent_specific_memory (applies to ALL agents)
Tier 3: Agent Default → Agent.memory_scope (exists but NOT exposed in UI)
```

**Problems**:
- Users can only enable/disable agent-specific memory for ALL agents globally
- No way to configure "Agent A: private, Agent B: global"
- Agent.memory_scope column exists in database but never exposed in UI
- Mismatch between user mental model and actual capabilities

### Target State

**Two-Tier Hierarchy (Per-Agent User Control)**:
```
Tier 1: Admin Policy → allow_agent_specific_memory_globally (system-wide on/off)
Tier 2: Per-Agent User Preference → UserAgentMemorySetting.allow_agent_specific_memory
         ↳ Falls back to Agent.memory_scope if user hasn't set preference
```

**Benefits**:
- ✅ Users control memory scope per agent
- ✅ Agent.memory_scope exposed in UI as default/fallback
- ✅ Memory scope badges on agent cards
- ✅ Simpler hierarchy (Admin → Per-Agent User → Agent Default)
- ✅ Matches user mental model: "Personal assistant needs private memory, tech support bot uses shared knowledge"

---

## Architecture Changes

### Database Schema

#### New Table: `user_agent_memory_settings`

```sql
CREATE TABLE user_agent_memory_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    allow_agent_specific_memory BOOLEAN NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_user_agent_memory_settings UNIQUE (user_id, agent_id)
);

CREATE INDEX idx_user_agent_memory_user ON user_agent_memory_settings(user_id);
CREATE INDEX idx_user_agent_memory_agent ON user_agent_memory_settings(agent_id);
```

**Purpose**: Store per-agent memory preferences for each user.

**Key Properties**:
- Unique constraint prevents duplicate preferences
- Cascade delete when user or agent deleted
- Absence of row = user hasn't set preference (use agent default)

#### Deprecated Column: `User.allow_agent_specific_memory`

**Migration Strategy**: Keep for backwards compatibility during transition period
- Check per-agent preference first
- Fall back to global toggle if no per-agent preference exists
- Log deprecation warnings
- Remove in future release (migration period: 1-2 releases)

#### Exposed Column: `Agent.memory_scope`

**Current State**: Exists in database, used by backend, NOT exposed in UI
**Target State**: Exposed in API responses and agent creation/editing UI
**Values**: `'global'` | `'agent'`
**Purpose**: Default memory scope for agent (applies when user hasn't set preference)

---

## Backend Implementation

### Phase 1: Database Models

**File**: `src/database/models.py`

**Add New Model**:
```python
class UserAgentMemorySetting(Base):
    """Per-agent memory preferences for users"""
    __tablename__ = "user_agent_memory_settings"

    id = Column(UUID, primary_key=True, server_default=text('gen_random_uuid()'))
    user_id = Column(String(255), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(UUID, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    allow_agent_specific_memory = Column(Boolean, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="agent_memory_settings")
    agent = relationship("Agent", back_populates="user_memory_settings")

    __table_args__ = (
        UniqueConstraint('user_id', 'agent_id', name='uq_user_agent_memory_settings'),
        Index('idx_user_agent_memory_user', 'user_id'),
        Index('idx_user_agent_memory_agent', 'agent_id'),
    )
```

**Update Existing Models**:
```python
# User model
agent_memory_settings = relationship("UserAgentMemorySetting", back_populates="user", cascade="all, delete-orphan")

# Agent model
user_memory_settings = relationship("UserAgentMemorySetting", back_populates="agent", cascade="all, delete-orphan")
```

### Phase 2: Memory Service Refactor

**File**: `src/services/memory_service.py`

**New Function**: `resolve_memory_scope()`

```python
async def resolve_memory_scope(
    user_id: str,
    agent_id: UUID,
    agent: Agent
) -> tuple[str, Optional[UUID]]:
    """
    Resolve final memory scope using two-tier hierarchy:
    1. Admin global policy (can force global)
    2. Per-agent user preference (or agent default if not set)

    Returns:
        tuple[scope, fact_agent_id]:
            - ('global', None) for global scope
            - ('agent', agent_id) for agent-specific scope
    """
    # Tier 1: Admin global policy
    admin_allows = await get_admin_memory_policy()
    if not admin_allows:
        return 'global', None

    # Tier 2: Per-agent user preference
    async with get_async_session() as session:
        # Check for explicit user preference
        user_pref = await session.execute(
            select(UserAgentMemorySetting)
            .where(
                UserAgentMemorySetting.user_id == user_id,
                UserAgentMemorySetting.agent_id == agent_id
            )
        )
        user_pref = user_pref.scalar_one_or_none()

        if user_pref is not None:
            # User has explicitly set preference
            if user_pref.allow_agent_specific_memory:
                return 'agent', agent_id
            else:
                return 'global', None

        # BACKWARDS COMPATIBILITY: Check global toggle
        # TODO: Remove after migration period
        user = await session.get(User, user_id)
        if user and not user.allow_agent_specific_memory:
            logger.warning(
                f"User {user_id} using deprecated global toggle. "
                f"Migrate to per-agent preferences."
            )
            return 'global', None

        # Fall back to agent default
        if agent.memory_scope == "agent":
            return 'agent', agent_id
        else:
            return 'global', None
```

**Update Memory Extraction** (lines 591-663):
```python
# OLD: Three-tier hierarchy checks
if not admin_allows_agent_memory:
    mem_user_id = user_id
    fact_agent_id = None
elif not user.allow_agent_specific_memory:
    mem_user_id = user_id
    fact_agent_id = None
elif agent.memory_scope == "global":
    mem_user_id = user_id
    fact_agent_id = None
else:
    mem_user_id = f"{user_id}:{agent_id}"
    fact_agent_id = agent_id

# NEW: Use resolve_memory_scope()
scope, fact_agent_id = await resolve_memory_scope(user_id, agent_id, agent)
mem_user_id = f"{user_id}:{agent_id}" if scope == 'agent' else user_id
```

**Update Manual Fact Creation** (memory_routes.py lines 220-330):
```python
# Check admin policy + per-agent preference before creating fact
scope, fact_agent_id = await resolve_memory_scope(user_id, agent_id, agent)

# If user requested 'agent' scope but resolved to 'global', warn
if request_data.scope == 'agent' and scope == 'global':
    logger.warning(
        f"User {user_id} requested agent-specific memory for agent {agent_id}, "
        f"but admin policy or user preference forced global scope"
    )
```

**Update Memory Retrieval** (lines 664-720):
```python
# OLD: Check agent.memory_scope directly
if agent.memory_scope == "global":
    mem_user_id = user_id
else:
    mem_user_id = f"{user_id}:{agent_id}"

# NEW: Use resolve_memory_scope()
scope, _ = await resolve_memory_scope(user_id, agent_id, agent)
mem_user_id = f"{user_id}:{agent_id}" if scope == 'agent' else user_id
```

### Phase 3: API Endpoints

**New File**: `src/routes/user_agent_settings_routes.py`

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class UserAgentMemorySettingResponse(BaseModel):
    id: str
    user_id: str
    agent_id: str
    allow_agent_specific_memory: bool
    created_at: str
    updated_at: str

class UserAgentMemorySettingUpdate(BaseModel):
    allow_agent_specific_memory: bool

@router.get("/api/memory/users/{user_id}/agents/{agent_id}/settings")
async def get_user_agent_memory_setting(
    user_id: str,
    agent_id: str
) -> Optional[UserAgentMemorySettingResponse]:
    """
    Get user's memory preference for specific agent.
    Returns None (404) if user hasn't set preference (uses agent default).
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(UserAgentMemorySetting)
            .where(
                UserAgentMemorySetting.user_id == user_id,
                UserAgentMemorySetting.agent_id == agent_id
            )
        )
        setting = result.scalar_one_or_none()

        if setting is None:
            raise HTTPException(status_code=404, detail="No preference set for this agent")

        return UserAgentMemorySettingResponse(**setting.__dict__)

@router.put("/api/memory/users/{user_id}/agents/{agent_id}/settings")
async def update_user_agent_memory_setting(
    user_id: str,
    agent_id: str,
    data: UserAgentMemorySettingUpdate
) -> UserAgentMemorySettingResponse:
    """
    Set user's memory preference for specific agent.
    Creates new row or updates existing.
    """
    async with get_async_session() as session:
        # Check if preference exists
        result = await session.execute(
            select(UserAgentMemorySetting)
            .where(
                UserAgentMemorySetting.user_id == user_id,
                UserAgentMemorySetting.agent_id == agent_id
            )
        )
        setting = result.scalar_one_or_none()

        if setting:
            # Update existing
            setting.allow_agent_specific_memory = data.allow_agent_specific_memory
            setting.updated_at = func.now()
        else:
            # Create new
            setting = UserAgentMemorySetting(
                user_id=user_id,
                agent_id=agent_id,
                allow_agent_specific_memory=data.allow_agent_specific_memory
            )
            session.add(setting)

        await session.commit()
        await session.refresh(setting)

        return UserAgentMemorySettingResponse(**setting.__dict__)

@router.delete("/api/memory/users/{user_id}/agents/{agent_id}/settings")
async def reset_user_agent_memory_setting(user_id: str, agent_id: str):
    """
    Reset user's memory preference for specific agent.
    Deletes row, causing fallback to agent default.
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(UserAgentMemorySetting)
            .where(
                UserAgentMemorySetting.user_id == user_id,
                UserAgentMemorySetting.agent_id == agent_id
            )
        )
        setting = result.scalar_one_or_none()

        if setting:
            await session.delete(setting)
            await session.commit()
            return {"message": "Preference reset to agent default"}
        else:
            raise HTTPException(status_code=404, detail="No preference to delete")

@router.get("/api/memory/users/{user_id}/agents/settings")
async def get_all_user_agent_memory_settings(user_id: str):
    """
    Get all per-agent memory preferences for user.
    Includes agents where user has set explicit preference.
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(UserAgentMemorySetting)
            .where(UserAgentMemorySetting.user_id == user_id)
        )
        settings = result.scalars().all()

        return [UserAgentMemorySettingResponse(**s.__dict__) for s in settings]
```

**Update Agent Endpoints** (src/api/server.py):

```python
# GET /api/agents/{id} - Include memory_scope in response
@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    # ... existing logic ...
    return {
        "id": str(agent.id),
        "name": agent.name,
        "system_prompt": agent.system_prompt,
        "memory_scope": agent.memory_scope,  # ADD THIS
        # ... other fields
    }

# PUT /api/agents/{id} - Allow updating memory_scope
@app.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, agent_data: AgentUpdate):
    # ... existing logic ...
    if agent_data.memory_scope is not None:
        agent.memory_scope = agent_data.memory_scope
    # ... rest of update logic

# POST /api/agents - Include memory_scope in creation
@app.post("/api/agents")
async def create_agent(agent_data: AgentCreate):
    agent = Agent(
        name=agent_data.name,
        system_prompt=agent_data.system_prompt,
        memory_scope=agent_data.memory_scope or 'agent',  # Default to 'agent'
        # ... other fields
    )
    # ... rest of creation logic
```

---

## Frontend Implementation

### Phase 4: TypeScript Interfaces

**File**: `frontend/src/services/api.ts`

```typescript
export interface Agent {
  id: string;
  name: string;
  system_prompt: string;
  temperature?: number;
  llm_provider: string;
  llm_model: string;
  tts_voice?: string;
  memory_scope: 'global' | 'agent';  // ADD THIS
  // ... other fields
}

export interface UserAgentMemorySetting {
  id: string;
  user_id: string;
  agent_id: string;
  allow_agent_specific_memory: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentMemoryConfig {
  agent: Agent;
  user_preference: UserAgentMemorySetting | null;
  effective_scope: 'global' | 'agent';
  source: 'user_preference' | 'agent_default' | 'admin_override';
}
```

**File**: `frontend/src/services/memory.ts`

```typescript
const USER_ID = 'discord:123456789'; // TODO: Replace with actual user ID

export async function getUserAgentMemorySetting(
  agentId: string
): Promise<UserAgentMemorySetting | null> {
  try {
    const res = await fetch(
      `${API_URL}/api/memory/users/${USER_ID}/agents/${agentId}/settings`
    );
    if (res.status === 404) return null;
    if (!res.ok) throw new Error('Failed to get user agent memory setting');
    return res.json();
  } catch (error) {
    console.error('Error fetching user agent memory setting:', error);
    return null;
  }
}

export async function updateUserAgentMemorySetting(
  agentId: string,
  allowAgentSpecificMemory: boolean
): Promise<UserAgentMemorySetting> {
  const res = await fetch(
    `${API_URL}/api/memory/users/${USER_ID}/agents/${agentId}/settings`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ allow_agent_specific_memory: allowAgentSpecificMemory })
    }
  );
  if (!res.ok) throw new Error('Failed to update user agent memory setting');
  return res.json();
}

export async function resetUserAgentMemorySetting(agentId: string): Promise<void> {
  const res = await fetch(
    `${API_URL}/api/memory/users/${USER_ID}/agents/${agentId}/settings`,
    { method: 'DELETE' }
  );
  if (!res.ok && res.status !== 404) {
    throw new Error('Failed to reset user agent memory setting');
  }
}

export async function getAgentMemoryConfig(agent: Agent): Promise<AgentMemoryConfig> {
  const userPref = await getUserAgentMemorySetting(agent.id);
  const adminPolicy = await getAdminMemoryPolicy();

  let effective_scope: 'global' | 'agent';
  let source: 'user_preference' | 'agent_default' | 'admin_override';

  if (!adminPolicy?.policy?.allow_agent_specific_memory_globally) {
    effective_scope = 'global';
    source = 'admin_override';
  } else if (userPref) {
    effective_scope = userPref.allow_agent_specific_memory ? 'agent' : 'global';
    source = 'user_preference';
  } else {
    effective_scope = agent.memory_scope;
    source = 'agent_default';
  }

  return { agent, user_preference: userPref, effective_scope, source };
}
```

### Phase 5: Agent Form UI

**File**: `frontend/src/components/AgentForm.tsx`

**Add Memory Scope Field** (after System Prompt, before Advanced Settings):

```typescript
import { Globe, Lock, Info } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

// In component state
const [memoryScope, setMemoryScope] = useState<'global' | 'agent'>(
  agent?.memory_scope || 'agent'
);

// In form JSX
<div className="space-y-2">
  <div className="flex items-center gap-2">
    <Label htmlFor="memory-scope">Memory Scope (Default)</Label>
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Info className="h-4 w-4 text-muted-foreground cursor-help" />
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <p className="text-xs">
            Determines how memories are stored by default. Users can override
            this setting for their own conversations with this agent.
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  </div>

  <Select value={memoryScope} onValueChange={setMemoryScope}>
    <SelectTrigger id="memory-scope">
      <SelectValue />
    </SelectTrigger>
    <SelectContent>
      <SelectItem value="agent">
        <div className="flex items-center gap-2">
          <Lock className="h-4 w-4" />
          <div>
            <div className="font-medium">Agent-Specific (Recommended)</div>
            <div className="text-xs text-muted-foreground">
              Private memories per user
            </div>
          </div>
        </div>
      </SelectItem>
      <SelectItem value="global">
        <div className="flex items-center gap-2">
          <Globe className="h-4 w-4" />
          <div>
            <div className="font-medium">Global</div>
            <div className="text-xs text-muted-foreground">
              Shared memories across all users
            </div>
          </div>
        </div>
      </SelectItem>
    </SelectContent>
  </Select>

  <p className="text-xs text-muted-foreground">
    {memoryScope === 'agent' ? (
      <>
        <Lock className="inline h-3 w-3 mr-1" />
        Each user's conversations will have private memories specific to this agent
      </>
    ) : (
      <>
        <Globe className="inline h-3 w-3 mr-1" />
        All users will share the same knowledge base for this agent
      </>
    )}
  </p>
</div>

// Include in form submission
const handleSubmit = async () => {
  const agentData = {
    // ... existing fields
    memory_scope: memoryScope,
  };
  // ... rest of submission logic
};
```

### Phase 6: Agent Card - Per-Agent Memory Toggle

**File**: `frontend/src/components/AgentCard.tsx`

**Add Memory Badge** (in agent card header):

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as memoryApi from '@/services/memory';

// Fetch user preference + admin policy
const { data: memoryConfig } = useQuery({
  queryKey: ['agentMemoryConfig', agent.id],
  queryFn: () => memoryApi.getAgentMemoryConfig(agent),
});

// Badge display
<Badge variant={memoryConfig?.effective_scope === 'agent' ? 'default' : 'secondary'}>
  {memoryConfig?.effective_scope === 'agent' ? (
    <>
      <Lock className="h-3 w-3 mr-1" />
      Private
    </>
  ) : (
    <>
      <Globe className="h-3 w-3 mr-1" />
      Global
    </>
  )}
</Badge>

// Tooltip explaining source
<TooltipProvider>
  <Tooltip>
    <TooltipTrigger asChild>
      <Info className="h-4 w-4 text-muted-foreground cursor-help ml-1" />
    </TooltipTrigger>
    <TooltipContent>
      <p className="text-xs">
        {memoryConfig?.source === 'admin_override' && (
          'Admin has disabled agent-specific memory globally'
        )}
        {memoryConfig?.source === 'user_preference' && (
          'You customized memory scope for this agent'
        )}
        {memoryConfig?.source === 'agent_default' && (
          `Using agent default: ${agent.memory_scope}`
        )}
      </p>
    </TooltipContent>
  </Tooltip>
</TooltipProvider>
```

**Add Memory Toggle** (in expanded agent details):

```typescript
// In AgentCard expanded section or agent edit modal
const queryClient = useQueryClient();

const updateMemoryPrefMutation = useMutation({
  mutationFn: (enabled: boolean) =>
    memoryApi.updateUserAgentMemorySetting(agent.id, enabled),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['agentMemoryConfig', agent.id] });
    toast.success(
      'Memory preference updated',
      `${agent.name} will now use ${enabled ? 'private' : 'global'} memories`
    );
  },
});

const resetMemoryPrefMutation = useMutation({
  mutationFn: () => memoryApi.resetUserAgentMemorySetting(agent.id),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['agentMemoryConfig', agent.id] });
    toast.success('Reset to agent default', `Using ${agent.memory_scope} memory scope`);
  },
});

<div className="border-t pt-4 mt-4">
  <Label className="text-sm font-medium">Your Memory Preference</Label>
  <div className="flex items-center justify-between mt-2">
    <div className="space-y-0.5 flex-1">
      <p className="text-sm">Agent-Specific Memory for {agent.name}</p>
      <p className="text-xs text-muted-foreground">
        {memoryConfig?.user_preference ? (
          memoryConfig.user_preference.allow_agent_specific_memory ? (
            <>
              <Lock className="inline h-3 w-3 mr-1" />
              Private memories for this agent only
            </>
          ) : (
            <>
              <Globe className="inline h-3 w-3 mr-1" />
              Shared global memories only
            </>
          )
        ) : (
          <>Using agent default: {agent.memory_scope}</>
        )}
      </p>
    </div>

    <div className="flex items-center gap-2">
      {memoryConfig?.user_preference && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => resetMemoryPrefMutation.mutate()}
          disabled={resetMemoryPrefMutation.isPending}
          title="Reset to agent default"
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      )}

      <Switch
        checked={memoryConfig?.effective_scope === 'agent'}
        onCheckedChange={(checked) => updateMemoryPrefMutation.mutate(checked)}
        disabled={
          memoryConfig?.source === 'admin_override' ||
          updateMemoryPrefMutation.isPending
        }
      />
    </div>
  </div>

  {memoryConfig?.source === 'admin_override' && (
    <Alert variant="warning" className="mt-2">
      <AlertTriangle className="h-4 w-4" />
      <AlertDescription className="text-xs">
        Admin has disabled agent-specific memory globally.
        Contact your administrator to enable per-agent memory control.
      </AlertDescription>
    </Alert>
  )}
</div>
```

### Phase 7: Deprecate User Global Toggle

**File**: `frontend/src/pages/settings/MemorySettingsPage.tsx`

**Replace Agent-Specific Memory Card** (lines 199-249):

```typescript
{/* OLD: Agent-Specific Memory Toggle Card */}
{/* DELETE lines 199-249 */}

{/* NEW: Per-Agent Memory Management Link */}
<Card>
  <CardHeader>
    <div className="flex items-center gap-2">
      <Brain className="h-5 w-5" />
      <CardTitle>Agent-Specific Memory</CardTitle>
    </div>
    <CardDescription>
      Manage memory preferences per agent
    </CardDescription>
  </CardHeader>
  <CardContent className="space-y-4">
    <p className="text-sm text-muted-foreground">
      Memory preferences are now managed per-agent instead of globally.
      Configure whether each agent stores private memories or uses shared
      knowledge in the Agents page.
    </p>

    <Link href="/agents">
      <Button variant="outline" className="w-full gap-2">
        <Settings className="h-4 w-4" />
        Manage Per-Agent Memory Settings
      </Button>
    </Link>

    <div className="pt-2 border-t">
      <p className="text-xs text-muted-foreground">
        <strong>How it works:</strong>
        <br />
        • Each agent has a default memory scope (global or agent-specific)
        <br />
        • You can override this default for your own conversations
        <br />
        • Private memories are specific to you + that agent
        <br />
        • Global memories are shared across all users
      </p>
    </div>
  </CardContent>
</Card>
```

### Phase 8: Update Admin Panel

**File**: `frontend/src/pages/settings/AdminMemorySettingsPage.tsx`

**Update Three-Tier Hierarchy Card** (lines 196-256):

```typescript
{/* OLD: Three-Tier Hierarchy Explanation */}
{/* REPLACE with NEW: Two-Tier Hierarchy */}

<Card>
  <CardHeader>
    <div className="flex items-center gap-2">
      <Info className="h-5 w-5" />
      <CardTitle>Two-Tier Memory Hierarchy</CardTitle>
    </div>
    <CardDescription>
      How admin policy and user preferences interact
    </CardDescription>
  </CardHeader>
  <CardContent className="space-y-4">
    <div className="space-y-3">
      {/* Tier 1: Admin Global Policy */}
      <div className="flex items-start gap-3">
        <div className="flex h-6 w-6 items-center justify-center rounded-full bg-red-100 text-red-700 text-xs font-bold flex-shrink-0">
          1
        </div>
        <div>
          <p className="text-sm font-medium">Admin Global Policy (Highest Priority)</p>
          <p className="text-xs text-muted-foreground">
            System-wide on/off switch. When disabled, ALL memories forced to global
            regardless of user or agent preferences.
          </p>
        </div>
      </div>

      {/* Tier 2: Per-Agent User Preference */}
      <div className="flex items-start gap-3">
        <div className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex-shrink-0">
          2
        </div>
        <div>
          <p className="text-sm font-medium">Per-Agent User Preference (Configurable)</p>
          <p className="text-xs text-muted-foreground">
            Users control memory scope per agent. Falls back to agent default
            (memory_scope field) if user hasn't set explicit preference.
          </p>
        </div>
      </div>
    </div>

    <div className="pt-2 border-t">
      <p className="text-xs text-muted-foreground">
        <strong>Enforcement Principle:</strong> Admin policy acts as a hard constraint
        that cannot be overridden. Users configure memory per-agent, with agent defaults
        serving as fallback when no user preference is set.
      </p>
    </div>
  </CardContent>
</Card>
```

---

## Database Migration

**File**: `alembic/versions/023_per_agent_memory_preferences.py`

```python
"""Add per-agent memory preferences

Revision ID: 023
Revises: 022
Create Date: 2025-11-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None

def upgrade():
    # Create user_agent_memory_settings table
    op.create_table(
        'user_agent_memory_settings',
        sa.Column('id', postgresql.UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.String(255), sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', postgresql.UUID, sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('allow_agent_specific_memory', sa.Boolean, nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('user_id', 'agent_id', name='uq_user_agent_memory_settings')
    )

    # Create indexes for performance
    op.create_index('idx_user_agent_memory_user', 'user_agent_memory_settings', ['user_id'])
    op.create_index('idx_user_agent_memory_agent', 'user_agent_memory_settings', ['agent_id'])

    # DO NOT drop User.allow_agent_specific_memory yet - keep for backwards compat
    # Will be removed in a future migration after transition period

def downgrade():
    op.drop_index('idx_user_agent_memory_agent', 'user_agent_memory_settings')
    op.drop_index('idx_user_agent_memory_user', 'user_agent_memory_settings')
    op.drop_table('user_agent_memory_settings')
```

**Migration Script** (Optional - for existing users):

**File**: `scripts/migrate_user_memory_preferences.py`

```python
"""
Migrate user global memory preferences to per-agent preferences.
Run once after deploying migration 023.

Usage:
    docker exec voxbridge-api python scripts/migrate_user_memory_preferences.py
"""

import asyncio
from src.database import get_async_session
from src.database.models import User, Agent, UserAgentMemorySetting
from sqlalchemy import select

async def migrate_global_preferences():
    """
    For users with allow_agent_specific_memory=False,
    create UserAgentMemorySetting rows for ALL agents
    with allow_agent_specific_memory=False.
    """
    async with get_async_session() as session:
        # Find users with global toggle disabled
        result = await session.execute(
            select(User).where(User.allow_agent_specific_memory == False)
        )
        users = result.scalars().all()

        print(f"Found {len(users)} users with global memory disabled")

        # Get all agents
        agents_result = await session.execute(select(Agent))
        agents = agents_result.scalars().all()

        print(f"Found {len(agents)} agents")

        migrated_count = 0

        for user in users:
            for agent in agents:
                # Check if preference already exists
                existing = await session.execute(
                    select(UserAgentMemorySetting).where(
                        UserAgentMemorySetting.user_id == user.user_id,
                        UserAgentMemorySetting.agent_id == agent.id
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    continue  # Skip if already exists

                # Create per-agent preference matching global setting
                setting = UserAgentMemorySetting(
                    user_id=user.user_id,
                    agent_id=agent.id,
                    allow_agent_specific_memory=False
                )
                session.add(setting)
                migrated_count += 1

        await session.commit()
        print(f"Migrated {migrated_count} user-agent preferences")

if __name__ == "__main__":
    asyncio.run(migrate_global_preferences())
```

---

## Testing Strategy

### Backend Tests

**New File**: `tests/unit/test_user_agent_memory_settings.py`

```python
import pytest
from src.services.memory_service import resolve_memory_scope
from src.database.models import Agent, UserAgentMemorySetting

@pytest.mark.asyncio
async def test_resolve_memory_scope_admin_disabled():
    """Admin policy forces global even if user/agent want agent-specific"""
    # Mock admin policy = False
    # Mock user pref = True, agent default = 'agent'
    # Result should be ('global', None)
    pass

@pytest.mark.asyncio
async def test_resolve_memory_scope_user_preference_exists():
    """User preference overrides agent default"""
    # Mock admin policy = True
    # Mock user pref = False (global)
    # Mock agent default = 'agent'
    # Result should be ('global', None)
    pass

@pytest.mark.asyncio
async def test_resolve_memory_scope_fallback_to_agent_default():
    """No user preference, falls back to agent default"""
    # Mock admin policy = True
    # Mock no user preference
    # Mock agent default = 'agent'
    # Result should be ('agent', agent_id)
    pass

@pytest.mark.asyncio
async def test_resolve_memory_scope_backwards_compat_global_toggle():
    """Backwards compat: check User.allow_agent_specific_memory"""
    # Mock admin policy = True
    # Mock no user per-agent preference
    # Mock User.allow_agent_specific_memory = False
    # Mock agent default = 'agent'
    # Result should be ('global', None)
    pass

# Test API endpoints
@pytest.mark.asyncio
async def test_get_user_agent_memory_setting_not_found():
    """GET returns 404 when no preference set"""
    pass

@pytest.mark.asyncio
async def test_update_user_agent_memory_setting_creates_new():
    """PUT creates new row if none exists"""
    pass

@pytest.mark.asyncio
async def test_update_user_agent_memory_setting_updates_existing():
    """PUT updates existing row"""
    pass

@pytest.mark.asyncio
async def test_delete_user_agent_memory_setting():
    """DELETE removes preference, falls back to agent default"""
    pass
```

### Frontend Tests

- Test AgentForm includes memory_scope field
- Test AgentCard displays memory badge
- Test per-agent memory toggle in agent editing
- Test admin policy warning disables toggle
- Test reset to default button

### Integration Tests

- Test end-to-end memory extraction with per-agent preferences
- Test memory retrieval uses correct namespace
- Test admin policy override of user preferences

---

## Git Commit Strategy

### Commit 1: Database Schema + Migration
- Add UserAgentMemorySetting model
- Create migration 023
- Update User and Agent relationships

### Commit 2: Backend - Memory Service Refactor
- Add resolve_memory_scope() function
- Update memory extraction logic
- Update manual fact creation logic
- Update memory retrieval logic

### Commit 3: Backend - API Endpoints
- Add user_agent_settings_routes.py
- Register new routes
- Update agent endpoints to expose memory_scope

### Commit 4: Frontend - TypeScript Interfaces
- Update Agent interface
- Add UserAgentMemorySetting interface
- Add API client functions

### Commit 5: Frontend - Agent Form UI
- Add memory_scope field to AgentForm.tsx
- Add Select dropdown with global/agent options
- Add tooltips and help text

### Commit 6: Frontend - Agent Card UI
- Add memory scope badge
- Add per-agent memory toggle
- Add reset to default button
- Add admin policy warning

### Commit 7: Frontend - Deprecate User Global Toggle
- Replace Agent-Specific Memory card in MemorySettingsPage
- Add link to Agents page for per-agent configuration
- Add explanation of new hierarchy

### Commit 8: Frontend - Update Admin Panel
- Update three-tier to two-tier hierarchy explanation
- Update enforcement principle description
- Remove outdated references

### Commit 9: Tests + Documentation
- Add backend unit tests
- Add frontend component tests
- Update CLAUDE.md
- Create migration guide

---

## Backwards Compatibility

### Transition Period (1-2 releases)

**Keep `User.allow_agent_specific_memory` column**:
- Check per-agent preference first
- Fall back to global toggle if no per-agent preference
- Log deprecation warnings when global toggle is used
- Provide migration script for existing users

### Future Release (Remove Global Toggle)

**Migration 024: Drop `User.allow_agent_specific_memory`**:
```python
def upgrade():
    op.drop_column('users', 'allow_agent_specific_memory')
```

**Prerequisites**:
- All users have migrated to per-agent preferences
- Deprecation warnings have been shown for at least 1 release
- Migration script has been run

---

## Success Criteria

### Must Have:
- ✅ Users can set memory scope per agent
- ✅ Agent.memory_scope exposed in UI
- ✅ Memory scope badges on agent cards
- ✅ Admin policy enforcement still works
- ✅ Backwards compatibility during transition
- ✅ No breaking changes to existing memory extraction/retrieval

### Nice to Have:
- Bulk operations (set all agents to global/agent-specific)
- Memory scope analytics (how many agents use each scope)
- Export per-agent memory preferences

---

## Risks & Mitigation

### Risk 1: Data Loss During Migration
**Mitigation**: Keep User.allow_agent_specific_memory as fallback, provide migration script

### Risk 2: Performance Impact of Per-Agent Queries
**Mitigation**: Add database indexes on user_id and agent_id

### Risk 3: User Confusion During Transition
**Mitigation**: Clear deprecation warnings, migration guide, link to Agents page

### Risk 4: Breaking Changes to Memory Extraction
**Mitigation**: Extensive unit tests, integration tests, backwards compatibility fallback

---

## Implementation Order

1. **Phase 1**: Database schema + migration ✅
2. **Phase 2**: Backend memory service refactor ✅
3. **Phase 3**: Backend API endpoints ✅
4. **Phase 4**: Frontend TypeScript interfaces ✅
5. **Phase 5**: Frontend agent form UI ✅
6. **Phase 6**: Frontend agent card UI ✅
7. **Phase 7**: Frontend deprecate user global toggle ✅
8. **Phase 8**: Frontend update admin panel ✅
9. **Phase 9**: Data migration strategy ✅
10. **Phase 10**: Testing ✅
11. **Phase 11**: Documentation ✅

---

## Resources

### Documentation:
- [VoxBridge Memory System](../../src/services/memory_service.py)
- [Admin Memory Policy](../architecture/admin-memory-policy.md)
- [Three-Tier Hierarchy](../../frontend/src/pages/settings/AdminMemorySettingsPage.tsx:196-256)

### Related Issues:
- Agent.memory_scope not exposed in UI
- No per-agent user preferences
- User global toggle too coarse-grained

### Dependencies:
- PostgreSQL with UUID support
- Alembic for migrations
- React Query for frontend data fetching
- shadcn/ui components

---

**Status**: Ready for Implementation
**Next Step**: Begin Phase 1 (Database Schema + Migration)