# Phase 4 Batch 1: Code Changes Reference

**Quick reference for reviewing actual code modifications**

---

## File 1: `src/discord_bot.py`

### Modified: `startup_services()` function (lines 390-436)

```python
@app.on_event("startup")
async def startup_services():
    """Start background service tasks"""
    logger.info("🚀 Starting VoxBridge services...")

    # Start existing services
    await conversation_service.start()
    await plugin_manager.start_resource_monitoring()

    # NEW Phase 4 Batch 1: Initialize plugins for all agents
    try:
        from src.services.agent_service import AgentService

        logger.info("🔌 Initializing plugins for all agents...")
        agents = await AgentService.get_all_agents()

        if not agents:
            logger.info("  ℹ️  No agents found - plugins will be initialized when agents are created")

        initialized_count = 0
        failed_count = 0

        for agent in agents:
            if agent.plugins:
                logger.info(f"  🔌 Initializing plugins for agent '{agent.name}'...")
                results = await plugin_manager.initialize_agent_plugins(agent)

                for plugin_type, success in results.items():
                    if success:
                        status = "✅"
                        initialized_count += 1
                        logger.info(f"    {status} {plugin_type} plugin initialized")
                    else:
                        status = "❌"
                        failed_count += 1
                        logger.error(f"    {status} {plugin_type} plugin failed to initialize")

        if initialized_count > 0:
            logger.info(f"✅ Initialized {initialized_count} plugins across {len(agents)} agents")
        if failed_count > 0:
            logger.warning(f"⚠️  {failed_count} plugins failed to initialize")

    except Exception as e:
        logger.error(f"❌ Error during plugin initialization: {e}", exc_info=True)
        # Don't crash app - continue startup even if plugins fail

    logger.info("✅ VoxBridge services started")
```

**What Changed**:
- Added plugin initialization loop after starting services
- Queries all agents from database
- Initializes plugins for each agent with enabled plugins
- Comprehensive logging with success/failure tracking
- Graceful error handling - doesn't crash app

---

## File 2: `src/services/agent_service.py`

### Modified: `create_agent()` method (lines 115-142)

**BEFORE** (old ending):
```python
            session.add(agent)
            await session.commit()
            await session.refresh(agent)

        return agent
```

**AFTER** (new ending):
```python
            session.add(agent)
            await session.commit()
            await session.refresh(agent)

        # NEW Phase 4 Batch 1: Initialize plugins if enabled
        if plugins:
            logger.info(f"🔌 Initializing plugins for new agent '{agent.name}'...")
            from src.services.plugin_manager import get_plugin_manager

            plugin_manager = get_plugin_manager()

            try:
                results = await plugin_manager.initialize_agent_plugins(agent)

                for plugin_type, success in results.items():
                    status = "✅" if success else "❌"
                    logger.info(f"  {status} {plugin_type}: {'Success' if success else 'Failed'}")

                # Invalidate default agent cache
                plugin_manager.invalidate_agent_cache()

            except Exception as e:
                logger.error(f"❌ Plugin initialization failed for agent '{agent.name}': {e}", exc_info=True)
                # Don't rollback agent creation - plugins can be initialized later

        logger.info(f"✅ Created agent: {agent.name} (ID: {agent.id})")

        return agent
```

**What Changed**:
- Added plugin initialization after agent creation
- Logs success/failure for each plugin type
- Invalidates default agent cache
- Doesn't rollback agent creation if plugins fail

---

### Modified: `update_agent()` method (lines 189-335)

**Key Changes** (focusing on plugin handling):

**Added at line 289-305**:
```python
            # NEW Phase 4 Batch 1: Handle plugin config updates
            plugins_changed = False
            if plugins is not None:
                # Encrypt sensitive plugin fields before updating
                encrypted_plugins = {}
                for plugin_type, plugin_config in plugins.items():
                    try:
                        encrypted_plugins[plugin_type] = PluginEncryption.encrypt_config(
                            plugin_type, plugin_config
                        )
                    except PluginEncryptionError as e:
                        logger.warning(f"⚠️ Could not encrypt {plugin_type} plugin config: {e}")
                        # Fall back to unencrypted if encryption fails
                        encrypted_plugins[plugin_type] = plugin_config

                agent.plugins = encrypted_plugins
                plugins_changed = True
```

**Added at line 310-334** (after commit):
```python
        # NEW Phase 4 Batch 1: Restart plugins if config changed
        if plugins_changed:
            logger.info(f"🔄 Plugin config changed for agent '{agent.name}' - restarting plugins...")
            from src.services.plugin_manager import get_plugin_manager

            plugin_manager = get_plugin_manager()

            try:
                # Stop existing plugins
                stop_results = await plugin_manager.stop_agent_plugins(agent.id)
                for plugin_type, success in stop_results.items():
                    logger.info(f"  🛑 Stopped {plugin_type}: {'Success' if success else 'Failed'}")

                # Reinitialize with new config
                init_results = await plugin_manager.initialize_agent_plugins(agent)
                for plugin_type, success in init_results.items():
                    status = "✅" if success else "❌"
                    logger.info(f"  {status} Restarted {plugin_type}: {'Success' if success else 'Failed'}")

                # Invalidate default agent cache
                plugin_manager.invalidate_agent_cache()

            except Exception as e:
                logger.error(f"❌ Plugin restart failed for agent '{agent.name}': {e}", exc_info=True)

        return agent
```

**What Changed**:
- Track if plugins configuration changed
- Stop existing plugins before reinitialization
- Reinitialize plugins with new config
- Invalidate default agent cache
- Agent update succeeds even if plugin restart fails

---

### Modified: `delete_agent()` method (lines 385-414)

**BEFORE** (old ending):
```python
        async with get_db_session() as session:
            result = await session.execute(select(Agent).where(Agent.id == agent_id))
            agent = result.scalar_one_or_none()

            if not agent:
                return False

            await session.delete(agent)
            await session.commit()

            return True
```

**AFTER** (new ending):
```python
        async with get_db_session() as session:
            result = await session.execute(select(Agent).where(Agent.id == agent_id))
            agent = result.scalar_one_or_none()

            if not agent:
                return False

            await session.delete(agent)
            await session.commit()

        # NEW Phase 4 Batch 1: Invalidate default agent cache after deletion
        from src.services.plugin_manager import get_plugin_manager

        plugin_manager = get_plugin_manager()
        plugin_manager.invalidate_agent_cache()

        return True
```

**What Changed**:
- Invalidate default agent cache after agent deletion

---

## File 3: `src/services/plugin_manager.py`

### Modified: `__init__()` method (lines 51-67)

**BEFORE**:
```python
    def __init__(self):
        """Initialize Plugin Manager"""
        # Active plugin instances: {agent_id: {plugin_type: plugin_instance}}
        self.active_plugins: Dict[UUID, Dict[str, PluginBase]] = {}

        # Track plugin errors for monitoring
        self.error_counts: Dict[str, int] = {}

        # Resource monitor (singleton)
        self.resource_monitor = get_resource_monitor()

        logger.info("🔌 PluginManager initialized")
```

**AFTER**:
```python
    def __init__(self):
        """Initialize Plugin Manager"""
        # Active plugin instances: {agent_id: {plugin_type: plugin_instance}}
        self.active_plugins: Dict[UUID, Dict[str, PluginBase]] = {}

        # Track plugin errors for monitoring
        self.error_counts: Dict[str, int] = {}

        # Resource monitor (singleton)
        self.resource_monitor = get_resource_monitor()

        # NEW Phase 4 Batch 1: Default agent cache
        self._default_agent_id: Optional[UUID] = None
        self._default_agent_cache_time: Optional[float] = None
        self._agent_cache_ttl: float = 300.0  # 5 minutes

        logger.info("🔌 PluginManager initialized")
```

**What Changed**:
- Added cache state variables for default agent caching

---

### Added: `get_default_agent_id()` method (lines 571-611)

```python
    async def get_default_agent_id(self) -> Optional[UUID]:
        """
        Get default agent ID with caching for low latency.

        Phase 4 Batch 1: Cached in-memory, refreshes every 5 minutes

        Returns:
            Default agent UUID or None
        """
        import time

        # Check cache
        if self._default_agent_id and self._default_agent_cache_time:
            age = time.time() - self._default_agent_cache_time
            if age < self._agent_cache_ttl:
                return self._default_agent_id

        # Cache miss - query database
        from src.services.agent_service import AgentService

        try:
            default_agent = await AgentService.get_default_agent()
            if default_agent:
                self._default_agent_id = default_agent.id
                self._default_agent_cache_time = time.time()
                logger.info(f"📌 Cached default agent: {default_agent.name} (ID: {default_agent.id})")
                return default_agent.id
            else:
                # No default agent - return first agent with Discord plugin
                agents = await AgentService.get_all_agents()
                for agent in agents:
                    if agent.plugins.get('discord', {}).get('enabled'):
                        self._default_agent_id = agent.id
                        self._default_agent_cache_time = time.time()
                        logger.info(f"📌 No default agent - using first Discord agent: {agent.name}")
                        return agent.id

                return None
        except Exception as e:
            logger.error(f"❌ Error getting default agent: {e}", exc_info=True)
            return None
```

**What It Does**:
- Check cache (5-minute TTL) for instant return
- On cache miss, query database for default agent
- Fallback to first Discord-enabled agent if no default
- Log cache operations for debugging

---

### Added: `invalidate_agent_cache()` method (lines 613-621)

```python
    def invalidate_agent_cache(self):
        """
        Invalidate default agent cache.

        Phase 4 Batch 1: Call this when agents are created/updated/deleted
        """
        self._default_agent_id = None
        self._default_agent_cache_time = None
        logger.info("🔄 Invalidated default agent cache")
```

**What It Does**:
- Clear cached agent ID and timestamp
- Force next call to `get_default_agent_id()` to query database

---

## Testing Examples

### Test 1: Verify Startup Plugin Initialization

```bash
# Start VoxBridge
docker compose up -d

# Check logs for plugin initialization
docker logs voxbridge-discord --tail 100 | grep -E "(🚀|🔌|✅|❌)"

# Expected output:
# 🚀 Starting VoxBridge services...
# 🔌 Initializing plugins for all agents...
#   🔌 Initializing plugins for agent 'CustomerSupport'...
#     ✅ discord plugin initialized
#     ✅ n8n plugin initialized
# ✅ Initialized 6 plugins across 3 agents
# ✅ VoxBridge services started
```

---

### Test 2: Verify Agent Creation Plugin Hook

```bash
# Create agent with Discord plugin
curl -X POST http://localhost:4900/api/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TestAgent",
    "system_prompt": "You are a helpful assistant",
    "plugins": {
      "discord": {
        "enabled": true,
        "bot_token": "YOUR_BOT_TOKEN"
      }
    }
  }'

# Check logs
docker logs voxbridge-discord --tail 50 | grep -E "(🔌|✅|❌)"

# Expected output:
# 🔌 Initializing plugins for new agent 'TestAgent'...
#   ✅ discord: Success
# ✅ Created agent: TestAgent (ID: 1234-5678-9abc-def0)
# 🔄 Invalidated default agent cache
```

---

### Test 3: Verify Agent Update Plugin Restart

```bash
# Update agent plugin config
curl -X PUT http://localhost:4900/api/agents/{agent_id} \
  -H "Content-Type: application/json" \
  -d '{
    "plugins": {
      "discord": {
        "enabled": false
      }
    }
  }'

# Check logs
docker logs voxbridge-discord --tail 50 | grep -E "(🔄|🛑|✅|❌)"

# Expected output:
# 🔄 Plugin config changed for agent 'TestAgent' - restarting plugins...
#   🛑 Stopped discord: Success
#   ✅ Restarted discord: Success
# 🔄 Invalidated default agent cache
```

---

### Test 4: Verify Default Agent Cache Performance

```python
# In Python console or test script
import asyncio
import time
from src.services.plugin_manager import get_plugin_manager

async def test_cache():
    manager = get_plugin_manager()

    # First call - cache miss (slow)
    t1 = time.time()
    agent_id = await manager.get_default_agent_id()
    duration1 = (time.time() - t1) * 1000
    print(f"First call (cache miss): {duration1:.2f}ms")
    print(f"Agent ID: {agent_id}")

    # Second call - cache hit (fast)
    t2 = time.time()
    agent_id = await manager.get_default_agent_id()
    duration2 = (time.time() - t2) * 1000
    print(f"Second call (cache hit): {duration2:.2f}ms")
    print(f"Agent ID: {agent_id}")

    # Performance improvement
    print(f"Speedup: {duration1 / duration2:.0f}x faster")

asyncio.run(test_cache())

# Expected output:
# First call (cache miss): 15.23ms
# Agent ID: 1234-5678-9abc-def0
# Second call (cache hit): 0.002ms
# Agent ID: 1234-5678-9abc-def0
# Speedup: 7615x faster
```

---

## Summary of Changes

| File | Lines Added | Lines Modified | New Methods |
|------|-------------|----------------|-------------|
| `src/discord_bot.py` | 47 | 1 | 0 |
| `src/services/agent_service.py` | 94 | 3 | 0 |
| `src/services/plugin_manager.py` | 63 | 1 | 2 |
| **Total** | **204** | **5** | **2** |

**New Methods**:
1. `PluginManager.get_default_agent_id()` - Cached agent selection
2. `PluginManager.invalidate_agent_cache()` - Cache invalidation

**Modified Methods**:
1. `discord_bot.startup_services()` - Plugin auto-initialization
2. `AgentService.create_agent()` - Plugin initialization hook
3. `AgentService.update_agent()` - Plugin restart hook
4. `AgentService.delete_agent()` - Cache invalidation hook
5. `PluginManager.__init__()` - Cache state variables

---

## Validation

All files pass Python syntax validation:

```bash
python3 -m py_compile src/discord_bot.py src/services/agent_service.py src/services/plugin_manager.py
# ✅ No errors
```
