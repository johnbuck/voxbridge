# VoxBridge Roadmap

**Vision**: AI Voice Agent Framework for smart home, automation, and companion experiences

**Last Updated**: 2025-12-07
**Current Status**: VoxBridge 2.0 Complete, Phase 3.1 (RAG) Complete

---

## Core Philosophy

VoxBridge is designed as a **pluggable AI voice agent framework** that:
- Integrates with Home Assistant, n8n, Open WebUI, and other platforms
- Supports pluggable TTS/STT providers (user's choice)
- Enables AI companion experiences with memory, emotion, and personality
- Optional Live2D/VTuber avatar support

---

## Completed Features (VoxBridge 2.0)

### Core Platform
- Multi-agent system with configurable personalities
- Service-oriented architecture (Conversation, STT, LLM, TTS services)
- PostgreSQL database with Alembic migrations
- WebRTC browser voice interface
- Discord voice integration
- Plugin architecture (extensible)

### Memory System (AI Companion Foundation)
- Long-term fact memory with Mem0 + pgvector
- Memory banks (Personal, Work, Health, Interests, Relationships)
- Temporal awareness (auto-expiring temporary states)
- Deduplication and intelligent pruning
- Background summarization

### User System
- JWT authentication with Admin/User roles
- Per-user memory isolation
- User timezone preferences
- Account settings UI

### LLM Providers
- OpenRouter.ai (cloud)
- Local LLM (Ollama, vLLM, LM Studio)
- n8n webhook fallback
- Provider management UI

### RAG & Knowledge System (Phase 3.1 - Completed Dec 2025)
- **voxbridge-rag** containerized service (port 4910)
- Document ingestion (PDF, DOCX, TXT, MD, code files)
- Web page scraping
- Semantic chunking with configurable sizes
- Hybrid search (pgvector + BM25 + Graphiti graph traversal)
- Cross-encoder reranking (BAAI/bge-reranker-base)
- Collections system with per-agent binding
- Source citations in responses
- Neo4j/Graphiti knowledge graph integration
- Graph visualization (React Flow)
- Entity relationship browser
- Knowledge Base UI (frontend)

---

## Phase 7 & 8: Completion (Pending)

| Phase | Description | Priority |
|-------|-------------|----------|
| Phase 7 | Documentation overhaul (ARCHITECTURE.md, CLAUDE.md) | Low |
| Phase 8 | Test file reorganization, maintain 90%+ coverage | Low |

---

## VoxBridge 3.0 Roadmap

### Tier 1: Pluggable Audio Providers

**Goal**: Let users choose their preferred TTS and STT solutions

#### Pluggable STT (Speech-to-Text)

| Provider | Type | Status |
|----------|------|--------|
| WhisperX | Local (GPU) | Current |
| OpenAI Whisper API | Cloud | Planned |
| Deepgram | Cloud | Planned |
| Azure Speech | Cloud | Planned |
| Faster-Whisper | Local | Planned |
| Speech-to-Phrase (HA) | Local | Planned |

#### Pluggable TTS (Text-to-Speech)

| Provider | Type | Features | Status |
|----------|------|----------|--------|
| Chatterbox | Local (GPU) | Voice cloning | Current |
| **IndexTTS2** | Local (GPU) | Emotion control, duration control, 7 emotions | Planned |
| Zyphra Zonos | Local (GPU) | Expressive/emotional | Planned |
| OpenAI TTS | Cloud | High quality | Planned |
| ElevenLabs | Cloud | Expressive, cloning | Planned |
| Azure Speech | Cloud | Enterprise | Planned |
| Kokoro-82M | Local | Lightweight | Planned |
| Piper | Local (CPU) | Fast, lightweight | Planned |
| Coqui XTTS | Local (GPU) | Voice cloning | Planned |
| Hume AI Octave | Cloud | Emotion-aware | Planned |

**IndexTTS2 Highlights** ([GitHub](https://github.com/index-tts/index-tts)):
- 7 basic emotions: anger, happiness, fear, disgust, sadness, surprise, neutral
- Duration control for frame-accurate timing (game/video dubbing)
- Disentangled emotion from speaker identity
- Multilingual: Chinese, English, Japanese, and more
- Non-commercial open source (Bilibili)

#### Audio Processing

| Feature | Description | Status |
|---------|-------------|--------|
| Echo Cancellation | AI doesn't hear its own voice (speakerless mode) | Planned |
| Noise Suppression | Filter background noise | Planned |
| Voice Activity Detection | Improved silence detection | Partial |
| Barge-in/Interruption | User can interrupt AI mid-speech | Planned |

#### AI Vision Capabilities

| Feature | Description | Status |
|---------|-------------|--------|
| Screen Capture | See user's screen (with permission) | Planned |
| Video Understanding | Process video/webcam input | Planned |
| Image Analysis | Describe images, read text (OCR) | Planned |
| Multi-modal LLM | GPT-4V, Claude Vision, LLaVA | Planned |

#### Provider Architecture

```
src/providers/
  stt/
    base.py          # Abstract STTProvider
    whisperx.py      # Current implementation
    openai_whisper.py
    deepgram.py
    azure.py
  tts/
    base.py          # Abstract TTSProvider
    chatterbox.py    # Current implementation
    zonos.py         # Zyphra Zonos (expressive)
    openai_tts.py
    elevenlabs.py
    azure.py
    kokoro.py
    piper.py
  vision/
    base.py          # Abstract VisionProvider
    screen_capture.py
    webcam.py
    image_analysis.py
  audio/
    echo_cancellation.py
    noise_suppression.py
    vad.py           # Voice activity detection
```

---

### Tier 2: Platform Integrations

#### Home Assistant Integration

| Feature | Description |
|---------|-------------|
| Wyoming Protocol | HA voice assistant integration |
| Wake Word Support | "Hey VoxBridge" via openWakeWord/microWakeWord |
| Intent Recognition | HA entity/service control |
| Custom Sentences | User-defined voice commands |
| Satellite Support | ESP32-S3 voice hardware |

**Reference**: [Home Assistant Voice Control](https://www.home-assistant.io/voice_control/)

#### n8n Integration

| Feature | Description |
|---------|-------------|
| Webhook Triggers | Voice -> n8n workflow |
| Response Actions | n8n -> Voice response |
| Tool Calling | Agent function execution via n8n |
| Workflow Templates | Pre-built voice automation flows |

**Future Alternative**: [LangGraph](https://langchain-ai.github.io/langgraph/) for multi-agent orchestration
- See **Phase 3.13** for implementation roadmap (16 features)
- Enables complex agent graphs with state management
- Alternative to n8n for code-first workflows

#### Open WebUI Integration

| Feature | Description |
|---------|-------------|
| OpenAI-Compatible TTS API | `/v1/audio/speech` endpoint |
| OpenAI-Compatible STT API | `/v1/audio/transcriptions` endpoint |
| Model Listing | `/models` endpoint for provider discovery |
| Voice Chat Mode | Full duplex voice conversation |

**Reference**: [Open WebUI Custom TTS](https://github.com/open-webui/open-webui/discussions/12937)

#### Communication Integrations

| Platform | Features | Status |
|----------|----------|--------|
| Discord | Voice channels, DMs, server messages | Partial |
| Twilio | Phone calls, SMS messaging | Planned |
| Telegram | Voice messages, chat | Planned |
| Matrix | Federated messaging | Planned |
| Email | Send/receive via SMTP/IMAP | Planned |

**Capabilities**:
- Make outbound phone calls (via n8n + Twilio)
- Receive and respond to calls
- Send SMS/text messages
- Send Discord DMs and channel messages
- Voice-to-text transcription for messaging

#### Streaming Platform Integrations

| Platform | Features | Status |
|----------|----------|--------|
| **Twitch** | Chat interaction, TTS responses, alerts | Planned |
| **YouTube Live** | Live chat, super chat handling | Planned |
| **Kick** | Chat integration | Planned |
| **OBS** | Scene switching, source control | Planned |

**Twitch Features**:
- Read and respond to chat messages
- Voice TTS for chat messages
- Subscriber/donation alerts with voice
- Channel point redemptions -> voice actions
- Raid/host announcements
- Mod commands via voice
- OBS scene switching (game/chat/BRB)
- Stream title/category updates

**Reference**: [AI-VTUBER-Twitch-Companion](https://github.com/gaetan-warin/AI-VTUBER-Twitch-Companion), [Neuro-sama](https://en.wikipedia.org/wiki/Neuro-sama)

#### Gaming Integrations

| Game | Features | Status |
|------|----------|--------|
| Minecraft | Voice commands, chat, screen reading | Planned |
| World of Warcraft | Addon integration, voice macros | Planned |
| Generic Game Overlay | Voice assistant overlay | Planned |

#### TTRPG / Game Master Features

| Feature | Description | Status |
|---------|-------------|--------|
| **NPC Creation** | Generate voiced NPCs with personality | Planned |
| **NPC Voice Profiles** | Unique voice per character | Planned |
| **World Lore RAG** | Upload campaign docs for NPC knowledge | Planned |
| **Character Sheets** | Import D&D/Pathfinder character data | Planned |
| **Session Logging** | Record and summarize game sessions | Planned |
| **Dice Integration** | Voice-activated rolls with results | Planned |

**NPC System**:
- Create NPCs with name, personality, voice, and knowledge scope
- Each NPC only knows what's in their assigned "collection"
- Voice changes per character (different TTS voice/settings)
- Personality traits affect response style

#### RAG / Knowledge Management

| Feature | Description | Status |
|---------|-------------|--------|
| **Document Upload** | PDF, DOCX, TXT, MD ingestion | Planned |
| **Collections** | Organize documents into knowledge bases | Planned |
| **Per-Agent Collections** | Assign specific collections to agents | Planned |
| **Vector Search** | Semantic similarity retrieval | Partial (Mem0) |
| **Chunking Strategies** | Configurable document splitting | Planned |
| **Source Citations** | Reference source in responses | Planned |

**Collection Architecture**:
```
Agent: "Bartender Bob"
├── Collections: ["Tavern Lore", "Local Rumors"]
├── Voice: gruff_male_01
└── Personality: friendly, gossipy

Agent: "Mysterious Wizard"
├── Collections: ["Arcane Knowledge", "Quest Hooks"]
├── Voice: elderly_sage
└── Personality: cryptic, wise
```

#### Integration Architecture

```
src/integrations/
  communication/
    discord.py       # Extended Discord features
    twilio.py        # Phone calls + SMS
    telegram.py
    matrix.py
  gaming/
    minecraft.py     # RCON + mod integration
    wow_addon.py     # WeakAuras/addon bridge
    overlay.py       # Generic game overlay
  ttrpg/
    npc_manager.py   # NPC creation and management
    character_sheet.py  # D&D/PF2e import
    dice_roller.py   # Voice-activated dice
    session_logger.py  # Game session recording

src/knowledge/
  rag/
    ingestion.py     # Document upload and processing
    chunking.py      # Text splitting strategies
    collections.py   # Collection management
    retrieval.py     # Vector search with citations
  agent_knowledge.py # Per-agent collection binding
```

---

### Tier 3: AI Companion Features

Based on research into [AI companion apps](https://www.cyberlink.com/blog/trending-topics/3932/ai-companion-app) and [Hume AI](https://www.hume.ai/):

| Feature | Description | Status |
|---------|-------------|--------|
| Emotional Intelligence | Detect/respond to user emotions | Planned |
| Personality Profiles | Configurable companion personalities | Partial (agents) |
| Memory & Continuity | Remember conversations, preferences | Complete |
| Voice Customization | Clone voices, adjust tone | Complete |
| Proactive Engagement | Check-ins, reminders | Planned |
| Interactive Scenarios | Role-play, storytelling, games | Planned |
| Mood Tracking | Log emotional patterns over time | Planned |
| **Inner Thoughts** | AI reasoning visible but not spoken | Planned |
| **Translation** | Real-time voice translation | Planned |

#### AI Inner Thoughts System

Display AI's reasoning process without speaking it aloud:
- Show "thinking" text in UI while AI processes
- Configurable verbosity (silent, summary, detailed)
- Chain-of-thought display for complex reasoning
- Useful for debugging and transparency

#### Translation & Localization

| Feature | Description |
|---------|-------------|
| Real-time Voice Translation | Speak in one language, output in another |
| Multi-language TTS | Switch output language dynamically |
| Subtitle Generation | Real-time captions in multiple languages |
| Language Detection | Auto-detect user's spoken language |

#### Companion Architecture

```
src/companion/
  emotion_detector.py   # Sentiment analysis on user speech
  personality.py        # Personality trait system
  proactive.py          # Scheduled check-ins/reminders
  scenarios.py          # Interactive story/game engine
  inner_thoughts.py     # CoT display without TTS
  translation.py        # Real-time translation layer
```

---

### Tier 4: Avatar & VTuber Integration (Optional)

Based on [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) architecture:

#### Supported Avatar Formats

| Format | Description | Status |
|--------|-------------|--------|
| Live2D Cubism | 2D animated models (.model3.json) | Planned |
| VRoid/VRM | 3D humanoid models (.vrm) | Planned |
| PNG Tuber | Simple image-based avatars | Planned |
| Spine | 2D skeletal animation | Planned |

#### Avatar Features

| Feature | Description | Status |
|---------|-------------|--------|
| **Expression Control** | Map AI emotions -> facial expressions | Planned |
| **Emotion Mapping** | Detect emotion -> trigger expression | Planned |
| **Lip Sync** | Audio -> phoneme -> mouth shapes | Planned |
| **Idle Animations** | Blinking, breathing, fidgeting | Planned |
| **Model Animations** | Full body gestures, poses | Planned |
| **Screen Awareness** | Desktop companion mode | Planned |

#### Expression & Emotion System

```
Emotion Detection -> Expression Mapping -> Avatar Animation
     |                    |                    |
  "happy"           -> "smile"            -> trigger animation
  "thinking"        -> "ponder"           -> head tilt + blink
  "surprised"       -> "shock"            -> wide eyes + gasp
  "sad"             -> "frown"            -> droopy eyes
```

**16+ Standard Expressions**: neutral, happy, sad, angry, surprised,
thinking, embarrassed, smug, tired, excited, confused, worried,
determined, loving, playful, sleepy

#### Integration Options

1. **Embedded**: WebGL Live2D/VRM renderer in VoxBridge frontend
2. **VTube Studio**: WebSocket bridge (most popular)
3. **Warudo**: Integration for 3D VRM models
4. **Animaze**: FaceRig successor integration
5. **Plugin**: VTuber display as optional plugin

#### Avatar Architecture

```
src/plugins/
  avatar/
    base.py              # Abstract AvatarProvider
    live2d/
      renderer.py        # Cubism SDK WebGL wrapper
      model_loader.py    # .model3.json parser
    vroid/
      vrm_loader.py      # VRM/VRoid model loader
      three_renderer.py  # Three.js 3D renderer
    common/
      expression_map.py  # Emotion -> expression mapping
      lip_sync.py        # Audio -> viseme (28 phonemes)
      idle_behavior.py   # Autonomous animations
      gesture_system.py  # Full body animations
    bridges/
      vtube_studio.py    # VTube Studio WebSocket API
      warudo.py          # Warudo integration
```

---

## Implementation Priority Order

### Phase 3.1: RAG & Knowledge System (COMPLETE)
*Industry-standard GraphRAG with Graphiti knowledge graphs*

**Completed**: December 2025

**Research Context** (Jan 2025):
- Hybrid GraphRAG (vector + knowledge graph) is current best practice
- Zep/Graphiti achieves 94.8% accuracy (vs 93.4% MemGPT) on DMR benchmark
- 18.5% improvement on LongMemEval, 90% latency reduction
- Sources: [Zep Paper](https://arxiv.org/abs/2501.13956), [Neo4j RAG](https://neo4j.com/blog/developer/knowledge-graph-vs-vector-rag/)

#### Phase 3.1a: Graphiti Integration (Knowledge Graph Foundation) - COMPLETE
| # | Feature | Effort | Status |
|---|---------|--------|--------|
| 1 | Deploy Neo4j to docker-compose | Low | Done |
| 2 | Install Graphiti SDK | Low | Done |
| 3 | Configure Graphiti with PostgreSQL + Neo4j | Medium | Done |
| 4 | Entity extraction pipeline | Medium | Done |
| 5 | Temporal data model (bi-temporal) | Medium | Done |

#### Phase 3.1b: Hybrid Search & Retrieval - COMPLETE
| # | Feature | Effort | Status |
|---|---------|--------|--------|
| 6 | Hybrid search (vector + BM25 + graph traversal) | Medium | Done |
| 7 | Cross-encoder re-ranking | Medium | Done |
| 8 | MMR diversity (avoid repetitive results) | Low | Done |
| 9 | Temporal queries API | Medium | Done |

#### Phase 3.1c: Document RAG - COMPLETE
| # | Feature | Effort | Status |
|---|---------|--------|--------|
| 10 | Document upload (PDF, DOCX, TXT, MD) | Medium | Done |
| 11 | Chunking strategies (configurable) | Medium | Done |
| 12 | Collections system | Medium | Done |
| 13 | Per-agent collection binding | Low | Done |
| 14 | Source citations in responses | Low | Done |

#### Phase 3.1d: Visualization & Management - COMPLETE
| # | Feature | Effort | Status |
|---|---------|--------|--------|
| 15 | Graph visualization (React Flow) | High | Done |
| 16 | Entity relationship browser | Medium | Done |
| 17 | Knowledge graph export API | Low | Deferred

### Phase 3.2: AI Companion Features
*Personality, engagement, and transparency*

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 6 | Inner thoughts system (visible CoT) | Low | Debugging + transparency |
| 7 | Emotional intelligence (sentiment) | Medium | Empathetic responses |
| 8 | Proactive engagement (reminders) | Medium | Active companion |
| 9 | Mood tracking | Medium | Longitudinal emotional patterns |
| 10 | Interactive scenarios (role-play) | Medium | Engagement features |

### Phase 3.3: Provider Abstraction
*Unlocks all future provider additions*

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 11 | STT Provider base class + WhisperX adapter | Low | Foundation - enables all STT providers |
| 12 | TTS Provider base class + Chatterbox adapter | Low | Foundation - enables all TTS providers |
| 13 | Provider selection UI (frontend) | Low | User-facing control |
| 14 | Piper TTS provider | Low | Validate architecture, fast CPU fallback |

### Phase 3.4: Core Audio Quality
*Improves daily usability*

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 15 | Echo cancellation (speakerless mode) | Medium | Critical for speaker use |
| 16 | Barge-in/interruption support | Medium | Natural conversation flow |
| 17 | Voice Activity Detection improvements | Low | Reduce false triggers |

### Phase 3.5: Platform Integrations
*Enables smart home and tool ecosystem*

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 18 | Home Assistant Wyoming protocol | Medium | Smart home control |
| 19 | Open WebUI compatible API (`/v1/audio/*`) | Low | External tool integration |
| 20 | n8n tool calling (agent functions) | Low | Workflow automation |

### Phase 3.6: TTRPG & NPC System
*Builds on RAG foundation*

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 21 | NPC creation (name, personality, voice) | Medium | Character generation |
| 22 | NPC voice profiles | Low | Unique voice per character |
| 23 | Character sheet import (D&D/PF2e) | Medium | Game data integration |
| 24 | Session logging & summarization | Medium | Campaign continuity |
| 25 | Voice-activated dice rolls | Low | Gameplay enhancement |

### Phase 3.7: Communication Integrations
*Extend reach beyond voice*

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 26 | Discord DMs/messages (extend existing) | Low | Already have Discord |
| 27 | Twilio integration (calls + SMS) | Medium | Phone communication |
| 28 | Telegram bot | Medium | Popular messaging |

### Phase 3.8: Streaming & Content Creation
*VTuber/streamer use cases*

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 29 | Twitch chat integration | Medium | Streamer interaction |
| 30 | OBS scene control | Low | Stream automation |
| 31 | YouTube Live chat | Medium | Broader reach |
| 32 | Channel point redemptions | Low | Viewer engagement |

### Phase 3.9: AI Vision
*Multi-modal capabilities*

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 33 | Screen capture (with permission) | Medium | See user context |
| 34 | Image analysis (describe, OCR) | Medium | Visual understanding |
| 35 | Multi-modal LLM routing | Low | GPT-4V, Claude Vision |

### Phase 3.10: Expressive TTS
*Emotional voice output*

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 36 | IndexTTS2 provider (7 emotions) | Medium | Emotion-controlled |
| 37 | Zyphra Zonos provider | Medium | Expressive/natural |
| 38 | ElevenLabs provider | Low | Cloud backup, high quality |

### Phase 3.11: Avatar & VTuber (Optional)
*Visual representation*

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 39 | VTube Studio WebSocket bridge | Medium | Most popular integration |
| 40 | Emotion -> expression mapping | Medium | Reactive avatar |
| 41 | Lip sync (audio -> viseme) | High | Natural speech animation |
| 42 | Live2D embedded renderer | High | No external software |

### Phase 3.12: Gaming & Niche (Low Priority)
*Specialized use cases*

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 43 | Translation support | Medium | Multilingual users |
| 44 | Minecraft RCON integration | High | Gaming niche |
| 45 | WoW addon bridge | High | Gaming niche |

### Phase 3.13: LangGraph Agent Framework (Medium Priority)
*Code-first alternative to n8n workflows*

**Why LangGraph?**
- More control than n8n webhooks for complex agent logic
- State machine approach for multi-step reasoning
- Native Python integration (no webhook latency)
- Built-in tool calling and multi-agent orchestration

**Reference**: [docs/planning/frontend-langgraph-plan.md](docs/planning/frontend-langgraph-plan.md) (Part 2: Agent System)

#### Phase 3.13a: LangGraph Foundation
| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 46 | Install LangChain/LangGraph dependencies | Low | Foundation |
| 47 | Base agent interface (`src/agents/base_agent.py`) | Low | Abstraction layer |
| 48 | LangGraph state machine with classifier + responder nodes | Medium | Core orchestration |
| 49 | Routing logic (n8n vs built-in agent selection) | Medium | Hybrid mode support |

#### Phase 3.13b: Tool Calling
| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 50 | Web search tool (Tavily/DuckDuckGo) | Low | Common use case |
| 51 | Calculator tool | Low | Math operations |
| 52 | Code executor tool (sandboxed) | Medium | Technical support |
| 53 | Tool executor node in graph | Medium | Tool orchestration |

#### Phase 3.13c: Agent Presets & Memory
| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 54 | General Assistant preset | Low | Default personality |
| 55 | Technical Support preset | Low | Specialized agent |
| 56 | Creative Writer preset | Low | Specialized agent |
| 57 | PostgreSQL conversation history integration | Medium | LangChain memory |
| 58 | Vector memory (Chroma/pgvector) | Medium | Semantic recall |

#### Phase 3.13d: Frontend Integration
| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 59 | Agent selection UI | Low | User control |
| 60 | Tool usage visualization | Medium | Transparency |
| 61 | Memory/context viewer | Medium | Debugging |

---

## Quick Reference: Priority Matrix

| Priority | Feature | Effort | Impact |
|----------|---------|--------|--------|
| **High** | RAG collections system | Medium | High |
| **High** | AI Companion features | Medium | High |
| **High** | Pluggable STT providers | Medium | High |
| **High** | Pluggable TTS providers | Medium | High |
| **High** | Echo cancellation (speakerless) | Medium | High |
| **Medium** | Home Assistant Wyoming | Medium | High |
| **Medium** | Open WebUI compatible API | Low | Medium |
| **Medium** | TTRPG NPC system | Medium | Medium |
| **Medium** | AI Vision (screen capture) | Medium | High |
| **Medium** | Emotional intelligence | Medium | High |
| **Medium** | Inner thoughts system | Low | Medium |
| **Medium** | Twilio calling/SMS | Medium | Medium |
| **Medium** | Translation support | Medium | High |
| **Medium** | n8n enhanced integration | Low | Medium |
| **Medium** | Twitch/streaming integration | Medium | High |
| **Medium** | LangGraph agent framework | Medium | High |
| **Low** | Live2D/VRoid avatar support | High | Medium |
| **Low** | VTube Studio bridge | Medium | Low |
| **Low** | Gaming integrations (MC/WoW) | High | Low |

---

## Progress Summary

```
VoxBridge 2.0:        ████████████████████  100%
Memory System:        ████████████████████  100%
User Auth/RBAC:       ████████████████████  100%
RAG/Knowledge:        ████████████████████  100% (Phase 3.1 complete)
Pluggable Providers:  ░░░░░░░░░░░░░░░░░░░░  0%   (STT/TTS abstraction)
Platform Integrations:██░░░░░░░░░░░░░░░░░░  10%  (Discord done)
AI Companion:         ████░░░░░░░░░░░░░░░░  20%  (memory complete)
AI Vision:            ░░░░░░░░░░░░░░░░░░░░  0%
Communication:        ██░░░░░░░░░░░░░░░░░░  10%  (Discord done)
Streaming/Twitch:     ░░░░░░░░░░░░░░░░░░░░  0%
TTRPG/NPC:            ░░░░░░░░░░░░░░░░░░░░  0%
Avatar/VTuber:        ░░░░░░░░░░░░░░░░░░░░  0%
Translation:          ░░░░░░░░░░░░░░░░░░░░  0%
LangGraph Agents:     ░░░░░░░░░░░░░░░░░░░░  0%   (n8n alternative)
```

---

## Key Reference Links

- [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) - Live2D AI reference
- [Home Assistant Voice](https://www.home-assistant.io/voice_control/) - HA integration
- [Open WebUI TTS](https://github.com/open-webui/open-webui/discussions/12937) - Custom TTS API
- [Hume AI](https://www.hume.ai/) - Emotional AI reference
- [AI Companion Apps 2025](https://www.cyberlink.com/blog/trending-topics/3932/ai-companion-app) - Feature research
- [IndexTTS2](https://github.com/index-tts/index-tts) - Emotion-controlled TTS
- [AI-VTUBER-Twitch-Companion](https://github.com/gaetan-warin/AI-VTUBER-Twitch-Companion) - Twitch integration

---

## Superseded Documents

The following planning documents have been consolidated into this roadmap:

- `docs/architecture/voxbridge-2.0-transformation-plan.md` - VoxBridge 2.0 phases (completed)
- `docs/planning/archive/memory-system-enhancements.md` - Memory system (completed)
- `docs/planning/archive/user-auth-rbac-plan.md` - Auth system (completed)
- `docs/planning/frontend-langgraph-plan.md` - Part 1 complete (frontend), Part 2 → Phase 3.13
- `docs/architecture/multi-agent-implementation-plan.md` - Multi-agent (incorporated into 2.0)

These documents are retained for historical reference but this ROADMAP.md is the canonical source for future planning.
