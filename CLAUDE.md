# CLAUDE.md - VoxBridge

Quick reference for Claude Code when working with VoxBridge.

## Quick Links

| Resource | Description |
|----------|-------------|
| [AGENTS.md](./AGENTS.md) | Comprehensive architecture and patterns |
| [docs/ROADMAP.md](docs/ROADMAP.md) | VoxBridge 3.0 roadmap |
| [docs/changelog/](docs/changelog/) | Completed phases and history |
| [docs/guides/](docs/guides/) | Detailed guides (memory, env vars) |

---

## Critical Architecture Decision: Single Unified Voice Interface

**VoxBridge uses ONE unified interface at the root path ("/") for ALL voice interactions:**

- **VoxbridgePage.tsx** (`frontend/src/pages/VoxbridgePage.tsx`) is the ONLY voice interface
- Handles BOTH Discord voice chat AND browser WebRTC voice chat
- Real-time WebSocket connections: `/ws/events` (Discord) and `/ws/voice` (WebRTC)

**Navigation:**
- `/` - VoxbridgePage (Voice Chat + Analytics)
- `/agents` - AgentsPage (AI Agent Management)
- `/knowledge` - KnowledgePage (RAG Collections + Graph)
- `/settings` - SettingsPage (Service Configuration)

---

## Current Status

**VoxBridge 2.0**: Complete (Nov 2025) - See [changelog](docs/changelog/voxbridge-2.0-phases.md)
**Phase 3.1 (RAG)**: Complete (Dec 2025) - Knowledge graph + hybrid search
**VoxBridge 3.0**: In progress - See [ROADMAP.md](docs/ROADMAP.md)
**Test Coverage**: 99 tests passing, 90%+ coverage

---

## Quick Start

```bash
# Start all services
docker compose up -d

# Watch logs (filtered)
docker logs voxbridge-api --tail 100 --follow | grep -v "GET /health"

# Rebuild after changes
docker compose down && docker compose build --no-cache && docker compose up -d

# Run tests
./test.sh tests/unit -v --cov=src --cov-report=term-missing
```

---

## Architecture Overview

**Six-Container Setup:**
- `postgres` (5432) - PostgreSQL 15 + pgvector
- `neo4j` (7474, 7687) - Graph database for knowledge graphs
- `voxbridge-whisperx` (4901, 4902) - WhisperX STT server (GPU)
- `voxbridge-api` (4900) - Discord.py bot + FastAPI
- `voxbridge-rag` (4910) - RAG service (hybrid search, Graphiti)
- `voxbridge-frontend` (4903) - React dashboard

**Service Layer (4 core services):**
- `ConversationService` - Session management + caching
- `STTService` - WhisperX abstraction
- `LLMService` - LLM provider routing (OpenRouter/Local)
- `TTSService` - Chatterbox abstraction

**Memory System:** Dual-table architecture (Mem0 vectors + relational metadata)
See [Memory System Guide](docs/guides/memory-system.md) for details.

---

## Key Files

### Core Application
- `src/api/server.py` - FastAPI application (routes, WebSocket, lifecycle)
- `src/plugins/discord_plugin.py` - Plugin-based Discord bot
- `src/whisper_server.py` - WhisperX STT server

### Services
- `src/services/conversation_service.py` - Session management
- `src/services/stt_service.py` - WhisperX abstraction
- `src/services/llm_service.py` - LLM provider routing
- `src/services/tts_service.py` - Chatterbox abstraction
- `src/services/memory_service.py` - Mem0 integration

### Voice
- `src/voice/webrtc_handler.py` - WebRTC voice handler

### Database
- `src/database/models.py` - SQLAlchemy ORM models
- `src/database/session.py` - Async session management

### LLM Providers
- `src/llm/base.py` - Abstract LLMProvider
- `src/llm/openrouter.py` - OpenRouter.ai provider
- `src/llm/local_llm.py` - Local LLM provider (Ollama, vLLM)
- `src/llm/factory.py` - Provider factory

### Frontend
- `frontend/src/pages/VoxbridgePage.tsx` - Main voice interface
- `frontend/src/pages/AgentsPage.tsx` - Agent management
- `frontend/src/pages/KnowledgePage.tsx` - RAG collections + graph
- `frontend/src/components/GraphView.tsx` - Knowledge graph visualization
- `frontend/src/services/knowledge.ts` - RAG service API client
- `frontend/src/hooks/useWebRTCAudio.ts` - WebRTC audio hook

### RAG Service (`rag/`)
- `rag/src/main.py` - FastAPI RAG application
- `rag/src/routes/collection_routes.py` - Collection CRUD endpoints
- `rag/src/routes/search.py` - Hybrid search endpoints
- `rag/src/routes/graph.py` - Graph visualization endpoints
- `rag/src/services/retrieval.py` - Hybrid retrieval engine
- `rag/src/services/storage.py` - Vector + graph storage
- `rag/src/services/entity_extractor.py` - Graphiti entity extraction

### Configuration
- `docker-compose.yml` - Container orchestration
- `src/config/streaming.py` - Streaming configuration
- `alembic/` - Database migrations

---

## Environment Variables

**Required:**
- `DISCORD_TOKEN` - Discord bot token
- `N8N_WEBHOOK_URL` - n8n webhook URL
- `CHATTERBOX_URL` - Chatterbox TTS API
- `CHATTERBOX_VOICE_ID` - Voice ID for TTS

**Database:**
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- `OPENROUTER_API_KEY` - OpenRouter API key (optional)
- `LOCAL_LLM_BASE_URL` - Local LLM endpoint (optional)

See [Environment Variables Guide](docs/guides/environment-variables.md) for complete reference.

---

## Common Commands

### Database
```bash
docker exec voxbridge-api alembic upgrade head           # Run migrations
docker exec voxbridge-api python -m src.database.seed   # Seed agents
docker exec -it voxbridge-postgres psql -U voxbridge -d voxbridge
```

### Docker
```bash
docker compose ps                                        # View status
docker logs voxbridge-api --tail 200 --follow          # View logs
docker compose restart voxbridge-api                    # Restart service
docker compose up -d --force-recreate --build voxbridge-api  # Rebuild
```

**Rebuild vs Restart:**
- **Rebuild**: Frontend changes, Dockerfile changes, dependency changes
- **Restart**: Backend code changes (volume-mounted)

### Debugging
```bash
curl http://localhost:4900/health | python3 -m json.tool
docker logs voxbridge-api --tail 200 | grep -E "(LATENCY|⏱️)"
docker logs voxbridge-api --tail 200 | grep -E "(🧠|🧵|memory)"
```

### Testing
```bash
./test.sh tests/unit/test_llm_types.py -v              # Specific file
./test.sh tests/unit -s                                 # With print output
./test.sh tests/integration -v                          # Integration tests
```

---

## API Endpoints

### Voice Control
- `POST /voice/join` - Join voice channel
- `POST /voice/leave` - Leave voice channel
- `POST /voice/speak` - Speak text via TTS

### Agent Management
- `GET /api/agents` - List agents
- `POST /api/agents` - Create agent
- `PUT /api/agents/{id}` - Update agent
- `DELETE /api/agents/{id}` - Delete agent

### Discord Plugin
- `GET /api/plugins/discord/voice/status/{agent_id}` - Voice status
- `POST /api/plugins/discord/voice/join` - Join channel
- `POST /api/plugins/discord/voice/leave` - Leave channel

### Monitoring
- `GET /health` - Health check
- `GET /status` - Detailed status
- `GET /metrics` - Performance metrics
- `GET /api/streaming-config` - Streaming config
- `WS /ws` - Real-time events
- `WS /ws/voice` - WebRTC voice

### RAG Service (port 4910, proxied at `/rag/`)
- `GET /api/collections` - List collections
- `POST /api/collections` - Create collection
- `DELETE /api/collections/{id}` - Delete collection
- `POST /api/collections/{id}/documents` - Upload document
- `POST /api/collections/{id}/documents/web` - Scrape URL
- `POST /api/collections/{id}/agents` - Link agent
- `POST /api/knowledge/search` - Hybrid search
- `GET /api/graph/stats` - Graph statistics
- `GET /api/graph/entities` - Search entities
- `GET /api/graph/subgraph` - Get graph visualization data

---

## Code Style

- **Logging:** Use emoji prefixes (🎤 voice, 📡 network, ⏱️ latency, 🌊 streaming, 💭 thinking)
- **Async:** Prefer `async/await` over callbacks
- **Error Handling:** Try/except with detailed logging
- **Type Hints:** Use Python type hints
- **Docstrings:** Use docstrings for public methods

---

## Anti-Patterns (AVOID)

- Don't remove emoji logging (used for filtering)
- Don't add `await` to sync functions
- Don't modify tests without running them
- Don't commit `.env` files
- Don't skip latency logging

---

## Documentation Links

| Document | Description |
|----------|-------------|
| [AGENTS.md](./AGENTS.md) | Architecture, patterns, guidelines |
| [README.md](./README.md) | User-facing setup guide |
| [docs/ROADMAP.md](docs/ROADMAP.md) | VoxBridge 3.0 roadmap |
| [docs/guides/memory-system.md](docs/guides/memory-system.md) | Memory architecture |
| [docs/guides/environment-variables.md](docs/guides/environment-variables.md) | All env vars |
| [docs/changelog/voxbridge-2.0-phases.md](docs/changelog/voxbridge-2.0-phases.md) | Phase history |
| [tests/README.md](tests/README.md) | Testing framework |

---

## Notes for Claude Code

- **Context Priority:** Read AGENTS.md for comprehensive patterns, this file for quick tasks
- **Extended Thinking:** Use "think hard" for complex refactoring
- **Testing First:** Always run relevant tests after code changes
- **Log Verification:** Check Docker logs to verify behavior
