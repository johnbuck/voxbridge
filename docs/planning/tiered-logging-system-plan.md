# Tiered Logging System Implementation Plan

**Date**: November 8, 2025
**Status**: Phase 1 in progress
**Goal**: Replace scattered debug flags with industry-standard tiered logging system

---

## Problem Statement

Currently, VoxBridge uses ad-hoc boolean flags for debug logging:
- `DEBUG_LOGGING = true` in VoxbridgePage.tsx
- `DEBUG_WEBRTC_HOOK = true` in useWebRTCAudio.ts
- Scattered `logger.info()` vs `logger.debug()` calls without consistent strategy
- No way to control verbosity per module at runtime
- Difficult to troubleshoot production issues without overwhelming logs

**User Request**: "I don't want to remove debug logs. I want to establish logical tiers of flags for debug logging so that we can turn them on and off as needed."

---

## Design Principles

1. **Industry Standard**: Align with Python `logging` module's level system
2. **Per-Module Control**: Enable/disable logging for specific subsystems
3. **Preserve Conventions**: Keep emoji logging for visual categorization
4. **Backward Compatible**: Gradual migration without breaking existing code
5. **Environment-Driven**: Configure via environment variables (12-factor app)
6. **Performance**: Zero overhead when log level disabled

---

## Logging Levels (5-Tier System)

### TRACE (Level 5)
**Use Case**: Ultra-verbose debugging, raw data inspection
**When to Use**:
- Raw audio chunk dumps
- Every iteration of a loop
- Complete WebSocket message payloads
- Byte-level data inspection

**Examples**:
```python
logger.trace("🔍 Raw audio chunk: %d bytes: %s", len(chunk), chunk[:50])
logger.trace("🔍 WebSocket message: %s", json.dumps(msg))
```

### DEBUG (Level 10)
**Use Case**: Detailed debugging, checkpoints, state changes
**When to Use**:
- Pipeline checkpoints (5-checkpoint system)
- State transitions
- Function entry/exit
- Important variable values

**Examples**:
```python
logger.debug("🎙️ [WS_RECV] Received %d bytes (chunk #%d)", len(data), chunk_num)
logger.debug("✅ [DECODE] Decoded %d frames → %d bytes PCM", frame_count, pcm_bytes)
```

### INFO (Level 20) - DEFAULT
**Use Case**: Standard operational messages
**When to Use**:
- Connection established/closed
- Operation completed successfully
- Configuration loaded
- Milestone events

**Examples**:
```python
logger.info("✅ Connected to WhisperX server")
logger.info("🏁 Buffer limit reached - finalizing utterance")
logger.info("🚀 Logging system initialized (global level: INFO)")
```

### WARN (Level 30)
**Use Case**: Warnings, recoverable errors, fallbacks
**When to Use**:
- Retry attempts
- Fallback mechanisms triggered
- Deprecated API usage
- Suboptimal conditions

**Examples**:
```python
logger.warning("⚠️ Retrying connection (attempt 2/3)")
logger.warning("⏳ [DECODE] Incomplete WebM data, buffering...")
logger.warning("⚠️ WhisperX not responding, using fallback STT")
```

### ERROR (Level 40)
**Use Case**: Errors, exceptions, failures
**When to Use**:
- Exceptions caught
- Operations failed
- Data corruption detected
- Unrecoverable errors

**Examples**:
```python
logger.error("❌ Failed to decode audio: %s", error)
logger.error("❌ Error in audio loop: %s", exc_info=True)
logger.error("❌ Database connection lost")
```

---

## Phase 1: Backend Python Logging System

### 1.1 Create `src/config/logging_config.py`

**Features**:
- Custom TRACE level (5) registration
- `get_log_level(module_name)` - Parse environment variables
- `configure_logging()` - Initialize at startup
- `get_logger(__name__)` - Module-scoped logger factory
- Module name mapping (src.voice → voxbridge.voice)

**Environment Variables**:
```bash
# Global default
LOG_LEVEL=INFO

# Per-module overrides
LOG_LEVEL_VOICE=DEBUG      # src.voice.webrtc_handler
LOG_LEVEL_STT=DEBUG        # src.services.stt_service
LOG_LEVEL_LLM=INFO         # src.services.llm_service
LOG_LEVEL_TTS=WARN         # src.services.tts_service
LOG_LEVEL_CONVERSATION=INFO # src.services.conversation_service
LOG_LEVEL_DISCORD=INFO     # src.plugins.discord_plugin
LOG_LEVEL_WEBRTC=DEBUG     # src.voice.webrtc_handler (alias)
```

### 1.2 Update Entry Point (`src/discord_bot.py`)

**Changes**:
```python
# OLD:
import logging
logging.basicConfig(level=logging.INFO, format='...')

# NEW:
from src.config.logging_config import configure_logging
configure_logging(default_level="INFO")
```

### 1.3 Migrate High-Priority Files

**Priority 1** (Voice Pipeline):
- `src/voice/webrtc_handler.py` (590 lines)
  - Replace: `import logging; logger = logging.getLogger(__name__)`
  - With: `from src.config.logging_config import get_logger; logger = get_logger(__name__)`
  - Convert: `logger.info()` → `logger.debug()` for checkpoints
  - Convert: Temporary debug prints → `logger.trace()`

**Priority 2** (Services):
- `src/services/stt_service.py` (586 lines)
- `src/services/llm_service.py` (499 lines)
- `src/services/tts_service.py` (614 lines)
- `src/services/conversation_service.py` (643 lines)

**Priority 3** (Plugins):
- `src/plugins/discord_plugin.py` (1,706 lines)

### 1.4 Update Environment Files

Add to `.env.example`:
```bash
# Logging Configuration
LOG_LEVEL=INFO
# LOG_LEVEL_VOICE=DEBUG
# LOG_LEVEL_STT=DEBUG
# LOG_LEVEL_LLM=INFO
# LOG_LEVEL_TTS=WARN
# LOG_LEVEL_CONVERSATION=INFO
# LOG_LEVEL_DISCORD=INFO
```

---

## Phase 2: Frontend TypeScript Logging System

### 2.1 Create `frontend/src/utils/logger.ts`

**Features**:
- LogLevel enum (TRACE=0, DEBUG=1, INFO=2, WARN=3, ERROR=4)
- Logger class with level filtering
- Module-scoped logger factory
- Environment variable parsing (import.meta.env.VITE_LOG_LEVEL_*)
- Console styling with emoji preservation

**Environment Variables**:
```bash
# Global default
VITE_LOG_LEVEL=INFO

# Per-module overrides
VITE_LOG_LEVEL_WEBRTC=DEBUG    # useWebRTCAudio hook
VITE_LOG_LEVEL_WEBSOCKET=DEBUG # WebSocket connections
VITE_LOG_LEVEL_UI=INFO         # UI components
VITE_LOG_LEVEL_API=INFO        # API client
```

**API Design**:
```typescript
import { createLogger } from '@/utils/logger';

const logger = createLogger('useWebRTCAudio');
logger.trace('🔍 Audio chunk:', chunk);
logger.debug('🎙️ Microphone started');
logger.info('✅ Connected to WebSocket');
logger.warn('⚠️ Reconnecting...');
logger.error('❌ Connection failed:', error);
```

### 2.2 Migrate Frontend Files

**Priority 1** (WebRTC):
- `frontend/src/hooks/useWebRTCAudio.ts` (344 lines)
  - Replace: `if (DEBUG_WEBRTC_HOOK) console.log(...)`
  - With: `logger.debug(...)`
  - Replace: Checkpoint logs → `logger.trace()`

**Priority 2** (UI Components):
- `frontend/src/pages/VoxbridgePage.tsx`
  - Replace: `if (DEBUG_LOGGING) console.log(...)`
  - With: `logger.debug(...)`

### 2.3 Update Environment Files

Add to `frontend/.env.example`:
```bash
# Logging Configuration
VITE_LOG_LEVEL=INFO
# VITE_LOG_LEVEL_WEBRTC=DEBUG
# VITE_LOG_LEVEL_WEBSOCKET=DEBUG
# VITE_LOG_LEVEL_UI=INFO
```

---

## Phase 3: Runtime Configuration UI (FUTURE - NOT IN INITIAL IMPLEMENTATION)

**Deferred to future work**. Would include:
- Settings page for log level control
- Real-time updates without restart
- Log level persistence in localStorage
- Download logs feature

**Rationale for Skipping**:
- Environment variables sufficient for dev/production
- Adds complexity to initial implementation
- Can be added incrementally later

---

## Migration Strategy

### Backward Compatibility

1. **Keep Existing Logs**: Don't remove working log statements
2. **Add New Levels**: Introduce `logger.trace()` and `logger.debug()` incrementally
3. **No Breaking Changes**: Existing `logger.info()` continues working
4. **Gradual Migration**: Migrate file-by-file, test each change

### Testing Plan

1. **Unit Tests**: Test logging_config.py functions
   - `test_get_log_level()` - Environment variable parsing
   - `test_configure_logging()` - Initialization
   - `test_module_name_mapping()` - Module overrides

2. **Integration Tests**: Verify log output at different levels
   - Set `LOG_LEVEL_VOICE=TRACE`, verify all logs appear
   - Set `LOG_LEVEL_VOICE=ERROR`, verify only errors appear
   - Set per-module overrides, verify isolation

3. **Manual Testing**: Real-world scenarios
   - Start bot with `LOG_LEVEL=DEBUG`, check verbosity
   - Start bot with `LOG_LEVEL=WARN`, verify quiet operation
   - Enable `LOG_LEVEL_WEBRTC=TRACE`, verify WebRTC details

### Rollback Plan

If issues arise:
1. **Revert logging_config.py**: Delete file
2. **Restore old imports**: `import logging; logger = logging.getLogger(__name__)`
3. **Keep log statements**: No need to revert actual log calls (backward compatible)

---

## Implementation Order

### Batch 1: Core Infrastructure ✅
- [x] Create `src/config/logging_config.py`
- [ ] Update `src/discord_bot.py` entry point
- [ ] Test logging configuration

### Batch 2: Backend Migration
- [ ] Migrate `src/voice/webrtc_handler.py`
- [ ] Migrate `src/services/stt_service.py`
- [ ] Migrate `src/services/llm_service.py`
- [ ] Migrate `src/services/tts_service.py`
- [ ] Update `.env.example`

### Batch 3: Frontend Infrastructure
- [ ] Create `frontend/src/utils/logger.ts`
- [ ] Update `frontend/.env.example`

### Batch 4: Frontend Migration
- [ ] Migrate `frontend/src/hooks/useWebRTCAudio.ts`
- [ ] Migrate `frontend/src/pages/VoxbridgePage.tsx`
- [ ] Remove old debug flags

### Batch 5: Testing & Documentation
- [ ] Write unit tests for logging_config.py
- [ ] Manual testing across all log levels
- [ ] Update CLAUDE.md with logging guidelines
- [ ] Update README.md with environment variables

---

## Performance Considerations

### Zero Overhead When Disabled

```python
# ❌ BAD: String formatting happens even if log disabled
logger.debug(f"Audio chunk: {len(chunk)} bytes: {chunk}")

# ✅ GOOD: Lazy evaluation via % formatting
logger.debug("Audio chunk: %d bytes: %s", len(chunk), chunk)

# ✅ BETTER: Guard expensive operations
if logger.isEnabledFor(logging.DEBUG):
    logger.debug("Audio chunk: %s", expensive_serialization(chunk))
```

### Production Defaults

- Default `LOG_LEVEL=INFO` for production
- Default `LOG_LEVEL=DEBUG` for development
- Use `LOG_LEVEL=ERROR` for high-traffic services
- Use `LOG_LEVEL=TRACE` only for local debugging

---

## Documentation Updates

### CLAUDE.md Changes

Add to "Code Style" section:
```markdown
- **Logging Levels:**
  - `logger.trace()`: Raw data, every iteration
  - `logger.debug()`: Checkpoints, state changes
  - `logger.info()`: Connections, completions (default)
  - `logger.warning()`: Retries, fallbacks
  - `logger.error()`: Exceptions, failures
- **Logger Import:** `from src.config.logging_config import get_logger; logger = get_logger(__name__)`
- **Lazy Formatting:** Use `%` formatting for performance: `logger.debug("Value: %s", value)`
```

### README.md Changes

Add to "Environment Variables" section:
```markdown
**Logging Configuration:**
- `LOG_LEVEL` - Global log level (TRACE, DEBUG, INFO, WARN, ERROR) [default: INFO]
- `LOG_LEVEL_VOICE` - Override for voice module
- `LOG_LEVEL_STT` - Override for STT service
- `LOG_LEVEL_LLM` - Override for LLM service
- `LOG_LEVEL_TTS` - Override for TTS service
- `VITE_LOG_LEVEL` - Frontend global log level
- `VITE_LOG_LEVEL_WEBRTC` - Frontend WebRTC module
```

---

## Success Criteria

1. ✅ No more hardcoded `DEBUG_LOGGING` or `DEBUG_WEBRTC_HOOK` flags
2. ✅ Can control verbosity per module via environment variables
3. ✅ Existing log statements continue working (backward compatible)
4. ✅ Production logs are clean (INFO level shows only essential info)
5. ✅ Debug logs are comprehensive (DEBUG level shows checkpoints)
6. ✅ All tests pass after migration

---

## References

- **Python logging module**: https://docs.python.org/3/library/logging.html
- **12-factor app config**: https://12factor.net/config
- **Winston (Node.js logging)**: Similar tiered approach for frontend inspiration
- **VoxBridge emoji conventions**: CLAUDE.md "Code Style" section

---

**Last Updated**: November 8, 2025
**Next Steps**: Complete Batch 2 (Backend Migration)
