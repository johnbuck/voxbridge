---
description: Rebuild and restart VoxBridge containers
---

Completely rebuild VoxBridge Docker containers from scratch (no cache) and restart all services.

Execute the following commands to rebuild:

```bash
docker compose down && docker compose build --no-cache && docker compose up -d
```

This will:
1. **Stop all containers** (`docker compose down`)
   - Stops voxbridge-api, voxbridge-whisperx, voxbridge-frontend
   - Removes containers (but keeps volumes)
2. **Rebuild all images** (`docker compose build --no-cache`)
   - Rebuilds from Dockerfile without using cache
   - Pulls latest base images
   - Reinstalls all dependencies
3. **Start containers** (`docker compose up -d`)
   - Starts all services in detached mode
   - Containers run in background

**When to use:**
- After changing Dockerfile or requirements files
- When dependencies need to be updated
- When build cache is corrupted
- When switching Python versions
- For clean slate rebuild

**Warning:** This process takes ~5-10 minutes depending on internet speed and CPU.

**To verify rebuild:**
```bash
# Check container status
docker compose ps

# Check logs
docker logs voxbridge-api --tail 50

# Check health
curl http://localhost:4900/health | python3 -m json.tool
```

**Faster alternatives:**
- **Rebuild single service:** `docker compose up -d --build voxbridge-api`
- **Restart without rebuild:** `docker compose restart voxbridge-api`
- **Rebuild with cache:** `docker compose build` (without `--no-cache`)
