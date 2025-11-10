# Unified Conversation Threading

**Phase 6.X Feature** - Implemented: October 29, 2025
**Status**: ✅ Complete

## Overview

Unified conversation threading allows Discord voice input and web interface input to share the same conversation thread. Users can now:

1. Open a conversation in the web interface
2. Join Discord voice channel (linked to that conversation)
3. Speak in Discord → messages saved to the conversation
4. Type/speak in web UI → messages saved to the same conversation
5. See all messages in a unified conversation thread

## Architecture Design

### Design Decisions

Based on user requirements:

1. **Multi-user conversations**: Allow both Discord user IDs and `web_user_default` in same session
2. **Explicit linking**: Only link when `session_id` is passed from frontend (not automatic)
3. **Guild isolation**: One active session per guild at a time, but multiple sessions per guild over time

### Database Schema

Added `discord_guild_id` to `sessions` table:

```sql
-- Migration: 20251029_1600_007_add_discord_guild_id_to_sessions.py
ALTER TABLE sessions ADD COLUMN discord_guild_id VARCHAR(100);
CREATE INDEX ix_sessions_discord_guild_id ON sessions(discord_guild_id);
```

**Purpose**: Track which Discord guild is currently linked to a session.

### Component Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Flow                                │
└─────────────────────────────────────────────────────────────────┘

1. User opens web UI, selects conversation (session_id: "abc-123")
2. User clicks "Join Voice" → Discord channel selector modal
3. User selects Discord server + channel
4. Frontend sends: POST /api/plugins/discord/voice/join
   {
     agent_id: "...",
     guild_id: 123456789,
     channel_id: 987654321,
     session_id: "abc-123"  // ← LINKED TO WEB CONVERSATION
   }

5. Discord plugin:
   - Joins voice channel
   - Stores mapping: guild_session_mapping[guild_id] = session_id
   - Updates database: sessions.discord_guild_id = guild_id

6. User speaks in Discord:
   - Plugin checks: mapped_session_id = guild_session_mapping[guild_id]
   - If mapped, uses that session (no new session created)
   - Transcription → LLM → TTS all use the mapped session

7. Web UI shows:
   - Badge: "🔗 Linked to conversation"
   - Discord messages appear in conversation thread
   - Web messages appear in same thread

8. User leaves Discord voice:
   - Clears mapping: guild_session_mapping.pop(guild_id)
   - Updates database: sessions.discord_guild_id = NULL
```

## Implementation Details

### Backend Changes

#### 1. Database Model (`src/database/models.py`)

```python
class Session(Base):
    # ... existing fields ...

    # Discord Integration (Phase 6.X: Unified Conversation Threading)
    discord_guild_id = Column(String(100), nullable=True, index=True)
```

#### 2. Discord Plugin (`src/plugins/discord_plugin.py`)

**Added session mapping**:

```python
def __init__(self):
    # ... existing code ...

    # Phase 6.X: Unified Conversation Threading
    self.guild_session_mapping: Dict[int, str] = {}  # guild_id → session_id
```

**Updated join_voice_channel()**:

```python
async def join_voice_channel(
    self,
    guild_id: int,
    channel_id: int,
    session_id: Optional[str] = None  # ← NEW PARAMETER
) -> Dict[str, Any]:
    # ... connect to voice ...

    # Store session mapping if provided
    if session_id:
        self.guild_session_mapping[guild_id] = session_id
        logger.info(f"🔗 Linked guild {guild_id} to session {session_id[:8]}...")

        # Update database
        await db.execute(
            update(Session)
            .where(Session.id == UUID(session_id))
            .values(discord_guild_id=str(guild_id))
        )
```

**Updated _handle_user_speaking()**:

```python
async def _handle_user_speaking(self, user, audio_stream, voice_client):
    # Check if guild is mapped to existing session
    guild_id = voice_client.guild.id
    mapped_session_id = self.guild_session_mapping.get(guild_id)

    if mapped_session_id:
        # Use mapped session (unified conversation)
        session_id = mapped_session_id
        logger.info(f"🔗 Using mapped session {session_id[:8]}... (unified conversation)")
    else:
        # Create new session (legacy behavior)
        session_id = str(uuid.uuid4())
        logger.info(f"📝 Created new session {session_id[:8]}...")

    # Continue with existing session logic...
```

**Updated leave_voice_channel()**:

```python
async def leave_voice_channel(self, guild_id: int):
    # ... cleanup audio receiver ...

    # Clear session mapping
    session_id = self.guild_session_mapping.pop(guild_id, None)
    if session_id:
        logger.info(f"🔓 Unlinked guild {guild_id} from session {session_id[:8]}...")

        # Update database
        await db.execute(
            update(Session)
            .where(Session.id == UUID(session_id))
            .values(discord_guild_id=None)
        )
```

#### 3. API Routes (`src/routes/discord_plugin_routes.py`)

```python
class VoiceJoinRequest(BaseModel):
    agent_id: str
    guild_id: int
    channel_id: int
    session_id: Optional[str] = None  # ← NEW FIELD
```

#### 4. Plugin Manager (`src/services/plugin_manager.py`)

```python
async def discord_join_voice(
    self,
    agent_id: UUID,
    guild_id: int,
    channel_id: int,
    session_id: Optional[str] = None  # ← NEW PARAMETER
) -> Dict[str, Any]:
    plugin = self.get_discord_plugin_by_agent(agent_id)
    return await plugin.join_voice_channel(guild_id, channel_id, session_id)
```

### Frontend Changes

#### 1. API Client (`frontend/src/services/api.ts`)

```typescript
async joinChannel(
  agentId: string,
  channelId: string,
  guildId: string,
  sessionId?: string | null  // ← NEW PARAMETER
): Promise<{ success: boolean; message: string }> {
  const sessionIdField = sessionId ? `,"session_id":"${sessionId}"` : '';
  const body = `{"agent_id":"${agentId}","channel_id":${channelId},"guild_id":${guildId}${sessionIdField}}`;

  return this.request('/api/plugins/discord/voice/join', {
    method: 'POST',
    body: body,
  });
}
```

#### 2. VoxbridgePage (`frontend/src/pages/VoxbridgePage.tsx`)

**Pass activeSessionId when joining**:

```typescript
const handleChannelSelected = useCallback(async (guildId: string, channelId: string) => {
  // Pass activeSessionId for unified conversation threading
  await api.joinChannel(activeAgent.id, channelId, guildId, activeSessionId);

  // Show appropriate toast
  if (activeSessionId) {
    toast.success('Joined voice channel (linked to active conversation)');
  } else {
    toast.success('Joined voice channel');
  }
}, [activeAgent, activeSessionId, toast]);
```

**Show link indicator**:

```tsx
{discordInVoice && activeSessionId && (
  <Badge variant="outline" className="text-xs bg-green-500/20 text-green-400 border-green-500/50">
    🔗 Linked to conversation
  </Badge>
)}
```

## Usage Examples

### Example 1: Link Discord to Existing Web Conversation

```
1. User creates web conversation with "Auren" agent
   - Session ID: "550e8400-e29b-41d4-a716-446655440000"
   - User types: "Hello Auren"
   - Auren responds: "Hello! How can I help you?"

2. User clicks "Join Voice" button
   - Selects Discord server: "My Server" (guild_id: 123456789)
   - Selects channel: "General" (channel_id: 987654321)
   - Frontend sends session_id with join request

3. User speaks in Discord: "What's the weather like?"
   - Discord plugin uses session "550e8400..."
   - Transcription saved to session
   - LLM generates response (same agent)
   - TTS plays in Discord

4. Web UI shows:
   - "🔗 Linked to conversation" badge
   - Message list:
     - user (web): "Hello Auren"
     - assistant: "Hello! How can I help you?"
     - user (Discord ID 123): "What's the weather like?"
     - assistant: "It's sunny and 75°F..."
```

### Example 2: Create New Discord Conversation

```
1. User clicks "Join Voice" without active conversation
   - activeSessionId = null
   - Frontend sends: { agent_id, guild_id, channel_id, session_id: null }

2. Discord plugin joins voice
   - No mapping stored (guild_session_mapping empty)

3. User speaks in Discord
   - Plugin creates NEW session (legacy behavior)
   - Session ID: "new-uuid-456"
   - Works as before (not linked to web)
```

## Testing

### Manual Testing Steps

1. **Test linked conversation**:
   ```
   ✅ Create web conversation
   ✅ Join Discord voice with active conversation
   ✅ Speak in Discord
   ✅ Verify messages appear in web conversation
   ✅ Type in web, verify same conversation thread
   ✅ Check "🔗 Linked" badge appears
   ```

2. **Test unlinked conversation**:
   ```
   ✅ Join Discord without active conversation
   ✅ Speak in Discord
   ✅ Verify new session created (not linked)
   ```

3. **Test leave/rejoin**:
   ```
   ✅ Leave Discord voice
   ✅ Verify "🔗 Linked" badge disappears
   ✅ Verify discord_guild_id cleared in database
   ✅ Rejoin Discord
   ✅ Verify can link to new conversation
   ```

4. **Test multi-user conversation**:
   ```
   ✅ Web user: "web_user_default"
   ✅ Discord user: "303805850844266506"
   ✅ Both appear in same session
   ✅ Messages from both users visible
   ```

### Database Verification

```sql
-- Check session linking
SELECT
  id,
  user_id,
  title,
  discord_guild_id,
  session_type
FROM sessions
WHERE discord_guild_id IS NOT NULL;

-- Check conversation messages
SELECT
  c.role,
  c.content,
  s.user_id,
  s.discord_guild_id
FROM conversations c
JOIN sessions s ON c.session_id = s.id
WHERE s.id = '550e8400-e29b-41d4-a716-446655440000'
ORDER BY c.timestamp;
```

## Files Modified

### Backend
1. `src/database/models.py` - Added `discord_guild_id` column to Session model
2. `alembic/versions/20251029_1600_007_add_discord_guild_id_to_sessions.py` - Migration script
3. `src/plugins/discord_plugin.py` - Session mapping logic (140 lines changed)
4. `src/routes/discord_plugin_routes.py` - Accept optional session_id parameter
5. `src/services/plugin_manager.py` - Pass session_id to Discord plugin

### Frontend
6. `frontend/src/services/api.ts` - Add session_id parameter to joinChannel()
7. `frontend/src/pages/VoxbridgePage.tsx` - Pass activeSessionId, show link badge

**Total Changes**: ~200 lines across 7 files

## Migration

### Running the Migration

```bash
# Apply migration
docker exec voxbridge-discord alembic upgrade head

# Verify
docker exec voxbridge-postgres psql -U voxbridge -d voxbridge -c "\d sessions"
```

### Rollback (if needed)

```bash
# Rollback migration
docker exec voxbridge-discord alembic downgrade -1

# This will:
# - Drop ix_sessions_discord_guild_id index
# - Drop discord_guild_id column
```

## Benefits

1. **Unified user experience**: Single conversation thread across Discord and web
2. **Context preservation**: Full conversation history available in both interfaces
3. **Explicit control**: User decides when to link Discord to conversation
4. **Multi-source input**: Support both voice (Discord) and text (web) in same thread
5. **Guild isolation**: Each Discord server can have separate conversation
6. **Backward compatible**: Existing Discord-only behavior preserved when no session_id provided

## Limitations

1. **One guild per session**: A session can only link to one Discord guild at a time
2. **Multi-user display**: Frontend shows all messages but doesn't distinguish Discord users visually (shows IDs)
3. **No auto-link**: Discord doesn't automatically link to web conversation (user must explicitly join with active session)

## Future Enhancements

1. **User avatars**: Show Discord user avatars in web conversation
2. **Multi-guild support**: Allow session to span multiple Discord guilds
3. **Auto-link option**: Optional setting to automatically link Discord to most recent conversation
4. **Discord message sync**: Fetch Discord messages sent while not in voice channel
5. **Link indicator in conversation list**: Show which conversations are currently linked to Discord

## Related Documentation

- [VoxBridge 2.0 Transformation Plan](../architecture/voxbridge-2.0-transformation-plan.md)
- [Discord Plugin Documentation](../../src/plugins/discord_plugin.py)
- [Session Management](../../src/services/conversation_service.py)
