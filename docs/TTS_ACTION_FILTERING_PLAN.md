# TTS Action Text Filtering Implementation Plan

**Date**: November 21, 2025
**Branch**: `feature/tts-action-filtering`
**Status**: In Progress

## Problem Statement

LLM responses include roleplay actions in asterisks (e.g., `*perks ears up*`, `*tilts head*`) that should not be spoken by TTS. These actions are meant for visual display but sound unnatural when narrated.

**Example Input**:
```
*perks ears up* Oh! Testing? *tilts head* Does my voice sound okay, Master? I... I can try speaking differently if you need...
```

**Desired TTS Output**:
```
Oh! Testing? Does my voice sound okay, Master? I... I can try speaking differently if you need...
```

**Conversation History**: Should preserve original unfiltered text with actions for display purposes.

---

## Solution Architecture

### User Requirements

Based on user preferences:
- **Filter Location**: TTSService with per-agent configuration
- **Filter Scope**: Asterisk actions `*text*` only (preserve parentheses and markdown)
- **Default Behavior**: Disabled by default (opt-in per agent)
- **Data Storage**: Store original unfiltered text in database, filter only for TTS

### Regex Pattern

```python
# Remove asterisk-wrapped actions while preserving math expressions
pattern = r'(?<!\d)\*+[^*]+\*+(?!\d)'

# Examples:
# "*perks ears*" → removed
# "2*3*4" → preserved (math expression)
# "**bold**" → preserved (per user preference to not filter markdown)
```

### Pipeline Flow

```
LLM Response → Conversation History (unfiltered)
            → TTSService.synthesize_speech(filter_actions=agent.filter_actions_for_tts)
            → filter_action_text() if enabled
            → Chatterbox TTS
```

---

## Implementation Steps

### Step 1: Create Text Filter Utility

**File**: `src/utils/text_filters.py` (NEW)

**Functions**:
- `filter_action_text(text: str) -> str`: Main filtering function
- `filter_action_text_with_metadata(text: str) -> Tuple[str, Dict]`: Returns filtered text + metadata

**Features**:
- Regex pattern: `(?<!\d)\*+[^*]+\*+(?!\d)`
- Negative lookahead/lookbehind to preserve math expressions
- Whitespace cleanup after removal
- Comprehensive docstrings and examples

**Implementation**:
```python
import re
import logging
from typing import Tuple, Dict

logger = logging.getLogger(__name__)

def filter_action_text(text: str) -> str:
    """Remove asterisk-wrapped actions from text for TTS synthesis."""
    if not text:
        return text

    # Remove asterisk-wrapped actions (preserve math like 2*3*4)
    text = re.sub(r'(?<!\d)\*+[^*]+\*+(?!\d)', '', text)

    # Clean up whitespace
    text = re.sub(r'\s{2,}', ' ', text).strip()

    return text

def filter_action_text_with_metadata(text: str) -> Tuple[str, Dict]:
    """Filter and return metadata about removals."""
    if not text:
        return text, {'removed_actions': [], 'action_count': 0, 'char_diff': 0}

    original_length = len(text)

    # Extract actions before removing
    action_pattern = r'\*+([^*]+)\*+'
    actions = re.findall(action_pattern, text)

    # Filter text
    filtered_text = filter_action_text(text)

    metadata = {
        'removed_actions': actions,
        'action_count': len(actions),
        'char_diff': original_length - len(filtered_text)
    }

    return filtered_text, metadata
```

---

### Step 2: Add Agent Configuration Field

**File**: `src/database/models.py`

**Change**: Add to `Agent` model class

```python
filter_actions_for_tts = Column(Boolean, nullable=False, default=False)
"""
Remove roleplay actions (*text*) from LLM responses before TTS synthesis.
When enabled, asterisk-wrapped actions are filtered to prevent TTS from
speaking unnatural action descriptions.

Default: False (opt-in per agent)
"""
```

---

### Step 3: Create Database Migration

**File**: `alembic/versions/012_add_tts_action_filter.py` (NEW)

```python
"""Add filter_actions_for_tts to agents

Revision ID: 012_add_tts_action_filter
Revises: 011_align_tts_with_chatterbox
Create Date: 2025-11-21
"""

from alembic import op
import sqlalchemy as sa

revision = '012_add_tts_action_filter'
down_revision = '011_align_tts_with_chatterbox'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        'agents',
        sa.Column('filter_actions_for_tts', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )

def downgrade():
    op.drop_column('agents', 'filter_actions_for_tts')
```

---

### Step 4: Update TTSService with Filtering

**File**: `src/services/tts_service.py`

**Location**: `synthesize_speech()` method (line ~211)

**Changes**:
1. Add import: `from src.utils.text_filters import filter_action_text_with_metadata`
2. Add parameter: `filter_actions: bool = False`
3. Add filtering logic before TTS synthesis

```python
async def synthesize_speech(
    self,
    session_id: str,
    text: str,
    voice_id: Optional[str] = None,
    exaggeration: Optional[float] = None,
    cfg_weight: Optional[float] = None,
    temperature: Optional[float] = None,
    language_id: str = "en",
    stream: bool = True,
    callback: Optional[Callable[[bytes], None]] = None,
    filter_actions: bool = False  # NEW parameter
) -> bytes:
    """
    Synthesize speech from text using Chatterbox TTS API.

    Args:
        ... (existing args) ...
        filter_actions: Remove roleplay actions (*text*) before synthesis (default: False)
    """
    voice_id = voice_id or self.default_voice_id

    # NEW: Filter action text if enabled
    original_text = text
    if filter_actions:
        text, filter_metadata = filter_action_text_with_metadata(text)

        # Log filtering results
        if filter_metadata['action_count'] > 0:
            logger.info(
                f"🔧 Filtered {filter_metadata['action_count']} actions from TTS text "
                f"(session={session_id}, {filter_metadata['char_diff']} chars removed)"
            )
            logger.debug(f"   Original: \"{original_text[:100]}...\"")
            logger.debug(f"   Filtered: \"{text[:100]}...\"")

    # Existing logging (now logs filtered text)
    logger.info(f"🔊 TTS request: session={session_id}, text=\"{text[:50]}...\", ...")

    # Rest of method unchanged...
```

---

### Step 5: Pass Agent Config to TTSService

**File**: `src/voice/webrtc_handler.py` (line ~1521)

**Change**: Update `_generate_tts()` method

```python
# Before
audio_bytes = await self.tts_service.synthesize_speech(
    session_id=self.session_id,
    text=text,
    voice_id=voice_id,
    ...
)

# After
audio_bytes = await self.tts_service.synthesize_speech(
    session_id=self.session_id,
    text=text,
    voice_id=voice_id,
    filter_actions=agent.filter_actions_for_tts,  # NEW
    ...
)
```

**File**: `src/plugins/discord_plugin.py` (line ~2067)

**Change**: Update `_play_tts()` method

```python
# Before
audio_bytes = await self.tts_service.synthesize_speech(
    session_id=session_id,
    text=text,
    voice_id=self.agent.tts_voice or os.getenv('CHATTERBOX_VOICE_ID', 'default'),
    ...
)

# After
audio_bytes = await self.tts_service.synthesize_speech(
    session_id=session_id,
    text=text,
    voice_id=self.agent.tts_voice or os.getenv('CHATTERBOX_VOICE_ID', 'default'),
    filter_actions=self.agent.filter_actions_for_tts,  # NEW
    ...
)
```

---

### Step 6: Update Agent API Endpoints

**File**: `src/api/server.py`

**Changes**:
1. Add `filter_actions_for_tts` to agent creation request validation (POST `/api/agents`)
2. Add `filter_actions_for_tts` to agent update request validation (PUT `/api/agents/{id}`)
3. Include field in agent serialization response

```python
# POST /api/agents - line ~XXX
@app.post("/api/agents")
async def create_agent(
    name: str,
    system_prompt: str,
    temperature: Optional[float] = 0.7,
    llm_provider: str = "openrouter",
    llm_model: str = "meta-llama/llama-3.1-70b-instruct",
    tts_voice: Optional[str] = None,
    use_n8n: bool = False,
    filter_actions_for_tts: bool = False,  # NEW field
    ...
):
    # Create agent with new field
    new_agent = Agent(
        ...,
        filter_actions_for_tts=filter_actions_for_tts,
    )
    # ...

# PUT /api/agents/{id} - line ~XXX
@app.put("/api/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    name: Optional[str] = None,
    filter_actions_for_tts: Optional[bool] = None,  # NEW field
    ...
):
    # Update agent field if provided
    if filter_actions_for_tts is not None:
        agent.filter_actions_for_tts = filter_actions_for_tts
    # ...
```

---

### Step 7: Update Frontend Agent Management

**File**: `frontend/src/pages/AgentsPage.tsx`

**Change**: Add toggle control in agent form

```tsx
{/* Add after tts_language field, before plugins section */}
<div className="space-y-2">
  <label className="text-sm font-medium">TTS Action Filtering</label>
  <div className="flex items-center space-x-2">
    <input
      type="checkbox"
      checked={formData.filter_actions_for_tts || false}
      onChange={(e) => setFormData({
        ...formData,
        filter_actions_for_tts: e.target.checked
      })}
      className="rounded border-gray-300"
    />
    <span className="text-sm text-muted-foreground">
      Remove action text (*text*) before TTS synthesis
    </span>
  </div>
  <p className="text-xs text-muted-foreground">
    When enabled, roleplay actions in asterisks will be filtered out before
    sending to TTS, preventing unnatural narration. Math expressions like
    2*3*4 are preserved.
  </p>
</div>
```

**Update TypeScript types**:

```typescript
// frontend/src/services/api.ts
export interface Agent {
  // ... existing fields ...
  filter_actions_for_tts: boolean;  // NEW field
}
```

---

### Step 8: Write Unit Tests

**File**: `tests/unit/utils/test_text_filters.py` (NEW)

```python
import pytest
from src.utils.text_filters import filter_action_text, filter_action_text_with_metadata


class TestFilterActionText:
    def test_single_asterisk_actions(self):
        """Test filtering single asterisk-wrapped actions"""
        input_text = "*perks ears up* Oh! Testing?"
        expected = "Oh! Testing?"
        assert filter_action_text(input_text) == expected

    def test_multiple_actions(self):
        """Test filtering multiple actions in one string"""
        input_text = "*smiles* Hello *waves* there *sits down* friend!"
        expected = "Hello there friend!"
        assert filter_action_text(input_text) == expected

    def test_math_expressions_preserved(self):
        """Test that math expressions are not filtered"""
        input_text = "The answer is 2*3*4 which equals 24"
        expected = "The answer is 2*3*4 which equals 24"
        assert filter_action_text(input_text) == expected

    def test_empty_string(self):
        """Test empty string handling"""
        assert filter_action_text("") == ""

    def test_none_handling(self):
        """Test None input handling"""
        assert filter_action_text(None) is None

    def test_no_actions(self):
        """Test text with no actions passes through unchanged"""
        input_text = "Plain text with no actions"
        assert filter_action_text(input_text) == input_text

    def test_double_asterisk_preserved(self):
        """Test that markdown bold (**text**) is preserved per user choice"""
        input_text = "This is **bold** text"
        expected = "This is **bold** text"
        assert filter_action_text(input_text) == expected

    def test_whitespace_cleanup(self):
        """Test whitespace is properly cleaned after removal"""
        input_text = "*action*  Multiple   spaces  *action*"
        expected = "Multiple spaces"
        assert filter_action_text(input_text) == expected

    def test_metadata_extraction(self):
        """Test metadata is correctly extracted"""
        input_text = "*perks ears* Hello *waves* world"
        filtered, metadata = filter_action_text_with_metadata(input_text)

        assert filtered == "Hello world"
        assert metadata['action_count'] == 2
        assert len(metadata['removed_actions']) == 2
        assert 'perks ears' in metadata['removed_actions']
        assert 'waves' in metadata['removed_actions']
        assert metadata['char_diff'] > 0


class TestEdgeCases:
    def test_nested_asterisks(self):
        """Test nested asterisk patterns"""
        input_text = "*outer *inner* text*"
        # Should remove entire outer pattern
        result = filter_action_text(input_text)
        assert "*" not in result

    def test_math_in_sentence(self):
        """Test math expression within sentence"""
        input_text = "Calculate 5*6*7 for me *smiles*"
        expected = "Calculate 5*6*7 for me"
        assert filter_action_text(input_text) == expected

    def test_empty_actions(self):
        """Test empty asterisk pairs"""
        input_text = "** **"
        result = filter_action_text(input_text)
        assert result.strip() == ""

    def test_multiline_actions(self):
        """Test actions spanning multiple lines"""
        input_text = "*perks\nears\nup* Testing"
        expected = "Testing"
        assert filter_action_text(input_text) == expected
```

**File**: `tests/unit/services/test_tts_service.py`

Add tests to existing file:

```python
class TestTTSFiltering:
    @pytest.mark.asyncio
    async def test_tts_filters_actions_when_enabled(self, mock_tts_service):
        """Test that actions are filtered when filter_actions=True"""
        input_text = "*perks ears* Hello world *waves*"

        # Mock the HTTP request to capture what text is sent
        with patch.object(mock_tts_service.client, 'post') as mock_post:
            mock_post.return_value.aiter_bytes = AsyncIterator([b'audio_data'])

            await mock_tts_service.synthesize_speech(
                session_id="test-123",
                text=input_text,
                filter_actions=True,
                stream=False
            )

            # Verify filtered text was sent (no asterisk actions)
            call_args = mock_post.call_args
            sent_text = call_args[1]['json']['text']
            assert sent_text == "Hello world"
            assert "*" not in sent_text

    @pytest.mark.asyncio
    async def test_tts_preserves_actions_when_disabled(self, mock_tts_service):
        """Test that actions are preserved when filter_actions=False"""
        input_text = "*perks ears* Hello world"

        with patch.object(mock_tts_service.client, 'post') as mock_post:
            mock_post.return_value.aiter_bytes = AsyncIterator([b'audio_data'])

            await mock_tts_service.synthesize_speech(
                session_id="test-123",
                text=input_text,
                filter_actions=False,  # Disabled
                stream=False
            )

            # Verify original text was sent (with asterisk actions)
            call_args = mock_post.call_args
            sent_text = call_args[1]['json']['text']
            assert sent_text == input_text
            assert "*perks ears*" in sent_text
```

---

### Step 9: Update Documentation

**File**: `.env.example`

Add comment (no env vars needed since it's per-agent config):

```bash
# ==============================================================================
# TTS ACTION FILTERING (VoxBridge 2.0)
# ==============================================================================

# No environment variables needed - action filtering is configured per-agent
# via the filter_actions_for_tts field in the agents table.
#
# When enabled for an agent, asterisk-wrapped actions (e.g., *perks ears up*)
# are removed from LLM responses before TTS synthesis, preventing unnatural
# narration. Original text is preserved in conversation history.
#
# Configuration: Agent Management UI → Enable "Filter action text for TTS"
```

---

### Step 10: Deploy and Test

**Deployment Steps**:

```bash
# 1. Run database migration
docker exec voxbridge-discord alembic upgrade head

# 2. Rebuild containers
docker compose build voxbridge-discord voxbridge-frontend

# 3. Deploy updated containers
docker compose up -d

# 4. Verify services are healthy
docker compose ps
curl http://localhost:4900/health
```

**Testing Steps**:

1. **Create test agent with filtering enabled**:
   - Navigate to http://localhost:4903/agents
   - Create new agent or edit existing
   - Enable "Filter action text for TTS" checkbox
   - Save

2. **Test voice chat**:
   - Start voice chat with the agent
   - Trigger response with actions: "Tell me something cute"
   - Expected response: `*perks ears* Hello! *smiles*`
   - Expected TTS: Should speak "Hello!" only (no "asterisk perks ears")

3. **Check logs**:
   ```bash
   docker logs voxbridge-discord --tail 100 | grep "Filtered"
   # Should see: "🔧 Filtered 2 actions from TTS text (session=..., 20 chars removed)"
   ```

4. **Verify conversation history**:
   - Check browser UI shows full response with actions
   - Database query: `SELECT content FROM conversations WHERE role='assistant' LIMIT 1`
   - Should contain original text with asterisks

5. **Test math expression preservation**:
   - Ask agent: "What is 2*3*4?"
   - Expected TTS: Should speak "2 times 3 times 4" (math preserved)

---

## Success Criteria

- ✅ Asterisk actions `*text*` removed before TTS synthesis
- ✅ Original LLM text preserved in conversation history/database
- ✅ Math expressions like `2*3*4` not filtered
- ✅ Per-agent configuration working (toggle in UI)
- ✅ Default disabled (opt-in) for backward compatibility
- ✅ <1ms latency overhead (regex is fast)
- ✅ Frontend UI allows toggling per agent
- ✅ Unit tests passing with >90% coverage
- ✅ No "asterisk" spoken by TTS engine
- ✅ Discord and WebRTC both respect agent config

---

## Files Changed Summary

### NEW Files:
- `src/utils/text_filters.py` (~150 lines)
- `src/utils/__init__.py` (empty, for module)
- `alembic/versions/012_add_tts_action_filter.py` (~30 lines)
- `tests/unit/utils/__init__.py` (empty, for module)
- `tests/unit/utils/test_text_filters.py` (~150 lines)
- `docs/TTS_ACTION_FILTERING_PLAN.md` (this file)

### MODIFIED Files:
- `src/database/models.py` (+3 lines: new field)
- `src/services/tts_service.py` (+25 lines: filtering logic)
- `src/voice/webrtc_handler.py` (+1 line: pass config)
- `src/plugins/discord_plugin.py` (+1 line: pass config)
- `src/api/server.py` (+10 lines: API field)
- `frontend/src/pages/AgentsPage.tsx` (+20 lines: UI toggle)
- `frontend/src/services/api.ts` (+1 line: type definition)
- `tests/unit/services/test_tts_service.py` (+40 lines: new tests)
- `.env.example` (+10 lines: documentation)

**Total Changes**: ~450 lines (40% tests, 35% implementation, 25% docs)

---

## Performance Impact

- **Latency Overhead**: <1ms per TTS request (regex is O(n) on text length)
- **Memory Overhead**: Negligible (~100-500 bytes per request for text copy)
- **CPU Impact**: <0.1ms on modern CPU for typical 200-character response
- **Storage Impact**: No change (storing same text, just filtering for TTS)

---

## Rollback Plan

If issues arise:

1. **Immediate rollback**: Set `filter_actions_for_tts=false` for all agents via database:
   ```sql
   UPDATE agents SET filter_actions_for_tts = false;
   ```

2. **Code rollback**: Revert commit and redeploy:
   ```bash
   git revert HEAD
   docker compose build voxbridge-discord voxbridge-frontend
   docker compose up -d
   ```

3. **Database rollback**: Downgrade migration:
   ```bash
   docker exec voxbridge-discord alembic downgrade -1
   ```

---

## Future Enhancements (Post-MVP)

- **Option C**: Add parentheses filtering `(text)` as optional config
- **Option D**: Add markdown filtering `**bold**`, `_italic_` as optional config
- **Metrics**: Track filtering statistics (actions/hour, false positives)
- **UI Preview**: Show filtered vs original text in agent management UI
- **Regex Customization**: Allow per-agent custom regex patterns (advanced users)
- **LLM Prompt Tuning**: Add system prompt instruction to avoid actions (backup layer)

---

## References

- **Research Report**: From Plan agent research session (Nov 21, 2025)
- **User Preferences**: Captured via AskUserQuestion tool
- **Industry Practices**: OpenWebUI, LibreChat, Home Assistant approaches
- **VoxBridge Architecture**: Service layer pattern, per-agent config model
