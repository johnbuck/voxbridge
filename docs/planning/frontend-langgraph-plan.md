# VoxBridge Frontend + LangGraph Agent System - Implementation Plan

**Created:** October 21, 2025
**Status:** In Progress - Frontend Foundation Complete
**Project Location:** `/home/wiley/Docker/voxbridge`

---

## ✅ Progress Summary

### Completed
1. **Frontend Foundation**
   - ✅ Created React 19 + Vite + TypeScript project at `/home/wiley/Docker/voxbridge/frontend`
   - ✅ Installed base dependencies (190 packages)
   - ✅ Copied shadcn/ui configuration from Chatterbox TTS
   - ✅ Project using "new-york" style with Tailwind CSS v4

### Next Immediate Steps
2. Complete Chatterbox theme integration
3. Install additional dependencies (shadcn components, React Query, Wouter, etc.)
4. Create backend API endpoints
5. Build monitoring dashboard layout

---

## Project Overview

Building a **comprehensive web frontend** for VoxBridge (port 4901) with **Chatterbox-inspired styling**, followed by implementing a **LangChain/LangGraph-based agent system** as an alternative to n8n webhooks.

### User Requirements (From Q&A)
- **Frontend Focus**: Both monitoring AND controls equally
- **Agent Framework**: LangChain/LangGraph (Python-based)
- **Multi-Agent UI**: Prepare architecture for future expansion (single agent first)
- **Authentication**: No auth (localhost only for development)

---

## Part 1: VoxBridge Frontend (Port 4901)

### Tech Stack
- ✅ **Framework**: React 19 + TypeScript + Vite
- ✅ **Styling**: Tailwind CSS v4 + shadcn/ui (New York style)
- **State**: React Query + React Hooks
- **Real-time**: WebSocket + Server-Sent Events
- **Audio**: Web Audio API
- **Icons**: Lucide React
- **Theme**: Dark mode default (matching Chatterbox aesthetic)

### Architecture
```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/              # shadcn/ui components (Button, Card, etc.)
│   │   ├── dashboard/       # Dashboard sections
│   │   │   ├── ConnectionStatus.tsx
│   │   │   ├── ActiveSpeaker.tsx
│   │   │   ├── TranscriptionFeed.tsx
│   │   │   ├── ResponseStream.tsx
│   │   │   └── MetricsPanel.tsx
│   │   ├── voice/           # Voice controls
│   │   │   ├── ChannelSelector.tsx
│   │   │   ├── VoiceControls.tsx
│   │   │   └── TTSTest.tsx
│   │   ├── agents/          # Agent management (future)
│   │   │   ├── AgentSelector.tsx
│   │   │   ├── SessionViewer.tsx
│   │   │   └── ToolUsageDisplay.tsx
│   │   └── theme-toggle.tsx
│   ├── hooks/               # Custom React hooks
│   │   ├── useWebSocket.ts
│   │   ├── useVoiceControls.ts
│   │   ├── useTranscription.ts
│   │   └── useMetrics.ts
│   ├── services/            # API client
│   │   └── api.ts
│   ├── pages/               # Route pages
│   │   └── Dashboard.tsx
│   ├── lib/
│   │   └── utils.ts         # cn() utility
│   ├── types/
│   │   └── index.ts
│   └── styles/
│       ├── globals.css
│       └── shadcn.css
├── public/
├── docker/
│   └── Dockerfile
├── package.json
├── tsconfig.json
├── vite.config.ts
└── components.json          # ✅ Already created
```

### Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  VoxBridge Dashboard         [Dark Mode Toggle]  [Status: Ready]│
├──────────────────┬────────────────────────┬──────────────────────┤
│                  │                        │                      │
│  LEFT PANEL      │   CENTER PANEL         │    RIGHT PANEL       │
│  (Voice Controls)│   (Live Transcription) │   (Response Stream)  │
│                  │                        │                      │
│  ┌────────────┐  │  ┌──────────────────┐  │  ┌────────────────┐ │
│  │ Connections│  │  │ Active Speaker   │  │  │ n8n Response   │ │
│  │  Discord ✓ │  │  │ User: 12345678   │  │  │ Streaming...   │ │
│  │  WhisperX ✓│  │  │ Duration: 3.2s   │  │  │                │ │
│  │  Chatterbox✓│  │  │ [Progress Bar]   │  │  │ "The weather   │ │
│  │  n8n ✓     │  │  └──────────────────┘  │  │  today is..."  │ │
│  └────────────┘  │                        │  │                │ │
│                  │  ┌──────────────────┐  │  │ TTS Queue: 3   │ │
│  ┌────────────┐  │  │ Live Transcript  │  │  │ ┌────────────┐ │ │
│  │ Channel    │  │  │                  │  │  │ │ Sentence 1 │ │ │
│  │ [Dropdown] │  │  │ "Hello, what..." │  │  │ │ Sentence 2 │ │ │
│  │            │  │  │ (partial)        │  │  │ │ Sentence 3 │ │ │
│  │ [Join]     │  │  │                  │  │  │ └────────────┘ │ │
│  │ [Leave]    │  │  │ "Hello, what is  │  │  └────────────────┘ │
│  └────────────┘  │  │  the time?"      │  │                      │
│                  │  │ (final - bold)   │  │  ┌────────────────┐ │
│  ┌────────────┐  │  └──────────────────┘  │  │ Failed Retry   │ │
│  │ TTS Test   │  │                        │  │ [Empty]        │ │
│  │ [Input]    │  │  ┌──────────────────┐  │  └────────────────┘ │
│  │ [Speak]    │  │  │ Silence: 0.5s    │  │                      │
│  └────────────┘  │  │ [Timer graphic]  │  │                      │
│                  │  └──────────────────┘  │                      │
└──────────────────┴────────────────────────┴──────────────────────┘
│                     BOTTOM PANEL                                 │
│                     (Metrics & Logs)                             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Latency Graph [========    ] 450ms avg                     │ │
│  │ Queue Depth: Audio: 5 | TTS: 3 | Playback: 1              │ │
│  │ Recent Errors: [Empty - All systems operational]           │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Key Features

#### 1. **Connection Status Header**
- Real-time connection indicators (Discord, WhisperX, Chatterbox, n8n)
- Color-coded: Green=ready, Yellow=loading, Red=error
- Animated pulse for processing states

#### 2. **Left Panel: Voice Controls**
```tsx
<Card>
  <CardHeader>
    <CardTitle>Voice Controls</CardTitle>
  </CardHeader>
  <CardContent>
    {/* Channel Selector */}
    <Select>
      <option>Guild 1 → Channel A</option>
      <option>Guild 1 → Channel B</option>
    </Select>

    {/* Join/Leave Buttons */}
    <Button onClick={handleJoin}>Join Channel</Button>
    <Button onClick={handleLeave}>Leave Channel</Button>

    {/* Force Unlock */}
    <Button variant="destructive">Force Unlock Speaker</Button>

    {/* TTS Test */}
    <Textarea placeholder="Test TTS..." />
    <Button onClick={handleTestTTS}>Speak</Button>
  </CardContent>
</Card>
```

#### 3. **Center Panel: Live Transcription**
```tsx
<Card>
  <CardHeader>
    <CardTitle>Active Speaker</CardTitle>
  </CardHeader>
  <CardContent>
    {/* Speaker Info */}
    <div className="flex items-center gap-3">
      <Avatar userId={speaker.userId} />
      <div>
        <p className="font-medium">{speaker.userId}</p>
        <p className="text-sm text-muted-foreground">
          Speaking for {duration}s
        </p>
      </div>
    </div>

    {/* Progress Bar (0-45s max speaking time) */}
    <Progress value={(duration / 45) * 100} />

    {/* Live Transcript */}
    <div className="mt-4 space-y-2">
      {/* Partial (fading) */}
      <p className="text-muted-foreground italic">
        {partialTranscript}
      </p>

      {/* Final (bold) */}
      <p className="font-semibold">
        {finalTranscript}
      </p>
    </div>

    {/* Silence Timer */}
    <div className="mt-4 text-sm">
      Silence: {silenceDuration}ms / 800ms
    </div>
  </CardContent>
</Card>
```

#### 4. **Right Panel: Response Stream**
```tsx
<Card>
  <CardHeader>
    <CardTitle>AI Response</CardTitle>
  </CardHeader>
  <CardContent>
    {/* Streaming Response */}
    <div className="prose dark:prose-invert">
      {streamingChunks.map(chunk => (
        <p key={chunk.id}>{chunk.text}</p>
      ))}
    </div>

    {/* TTS Queue */}
    <div className="mt-4">
      <h4 className="font-medium">TTS Queue ({queue.length})</h4>
      {queue.map(sentence => (
        <div className="flex items-center justify-between p-2 border rounded">
          <span>{sentence.text.substring(0, 40)}...</span>
          <Badge>{sentence.status}</Badge>
        </div>
      ))}
    </div>

    {/* Failed Sentences */}
    {failedSentences.length > 0 && (
      <div className="mt-4">
        <h4 className="font-medium text-destructive">Failed Retries</h4>
        {failedSentences.map(sentence => (
          <div className="p-2 border border-destructive rounded">
            {sentence.text}
            <Button size="sm" onClick={() => retry(sentence)}>
              Retry
            </Button>
          </div>
        ))}
      </div>
    )}
  </CardContent>
</Card>
```

#### 5. **Bottom Panel: Metrics**
```tsx
<Card>
  <CardContent>
    {/* Latency Graph (Recharts) */}
    <LineChart data={latencyData}>
      <Line dataKey="latency" stroke="var(--primary)" />
    </LineChart>

    {/* Queue Depths */}
    <div className="flex gap-4">
      <Badge>Audio Queue: {audioQueueSize}</Badge>
      <Badge>TTS Queue: {ttsQueueSize}</Badge>
      <Badge>Playback Queue: {playbackQueueSize}</Badge>
    </div>

    {/* Error Log */}
    <ScrollArea className="h-24">
      {errors.map(error => (
        <div className="text-sm text-destructive">
          [{error.timestamp}] {error.message}
        </div>
      ))}
    </ScrollArea>
  </CardContent>
</Card>
```

### New Backend API Endpoints

**Add to `src/discord_bot.py`:**

```python
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import asyncio

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4901"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/channels")
async def get_available_channels():
    """List all available voice channels"""
    channels = []
    for guild in bot.guilds:
        voice_channels = [
            {
                "id": str(channel.id),
                "name": channel.name,
                "userCount": len(channel.members)
            }
            for channel in guild.voice_channels
        ]
        channels.append({
            "id": str(guild.id),
            "name": guild.name,
            "channels": voice_channels
        })
    return {"guilds": channels}

@app.get("/api/transcripts")
async def get_recent_transcripts(limit: int = 10):
    """Get recent transcriptions"""
    # TODO: Implement with database
    return {"transcripts": []}

@app.get("/api/metrics")
async def get_metrics():
    """Get performance metrics"""
    return {
        "latency": {"avg": 450, "p50": 400, "p95": 800, "p99": 1200},
        "transcriptCount": 156,
        "errorRate": 0.02,
        "uptime": time.time() - app.state.start_time
    }

@app.post("/api/config")
async def update_config(config: dict):
    """Update runtime configuration"""
    # Update speaker_manager settings
    if "SILENCE_THRESHOLD_MS" in config:
        speaker_manager.silence_threshold_ms = config["SILENCE_THRESHOLD_MS"]
    if "USE_STREAMING" in config:
        speaker_manager.use_streaming = config["USE_STREAMING"]
    return {"success": True}

@app.post("/api/speaker/unlock")
async def force_unlock_speaker():
    """Force unlock current speaker"""
    previous = speaker_manager.active_speaker
    speaker_manager.active_speaker = None
    speaker_manager.lock_start_time = None
    return {"success": True, "previousSpeaker": previous}

@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """Real-time event stream"""
    await websocket.accept()

    try:
        while True:
            # Send status updates every second
            status = speaker_manager.get_status()
            await websocket.send_json({
                "event": "status_update",
                "data": status,
                "timestamp": datetime.now().isoformat()
            })
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()
```

### Dependencies to Install

```bash
cd frontend

# Core dependencies
npm install @tanstack/react-query wouter
npm install lucide-react class-variance-authority clsx tailwind-merge
npm install recharts  # For charts

# shadcn/ui components (manual copy from Chatterbox)
# Button, Card, Input, Select, Slider, Dialog, Toast, Badge, Progress, ScrollArea, Avatar

# Audio visualization (optional)
npm install react-audio-visualize

# Dev dependencies
npm install -D @types/node
```

### Environment Variables

**Create `frontend/.env`:**

```env
VITE_API_URL=http://localhost:4900
VITE_WS_URL=ws://localhost:4900
```

### Docker Configuration

**Create `frontend/docker/Dockerfile`:**

```dockerfile
# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Custom nginx config for SPA routing
RUN echo 'server { \
    listen 4901; \
    root /usr/share/nginx/html; \
    index index.html; \
    location / { \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 4901

CMD ["nginx", "-g", "daemon off;"]
```

**Update `docker-compose.yml`:**

```yaml
services:
  # ... existing services ...

  voxbridge-frontend:
    build:
      context: ./frontend
      dockerfile: docker/Dockerfile
    container_name: voxbridge-frontend
    restart: unless-stopped
    ports:
      - "4901:4901"
    networks:
      - bot-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4901"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Implementation Timeline

**Week 1: Foundation + Monitoring**
- ✅ Day 1: Set up React + Vite + TypeScript
- ✅ Day 1: Copy Chatterbox configuration
- Day 2: Install dependencies and create base layout
- Day 2-3: Build connection status and live transcription display
- Day 3: Create backend API endpoints

**Week 2: Controls + Response Stream**
- Day 4-5: Channel selector and voice controls
- Day 5: TTS testing interface
- Day 6: Response stream visualization
- Day 6-7: Metrics panel with graphs

**Week 3: Polish + Docker**
- Day 8: Runtime config editor
- Day 9: Error handling and loading states
- Day 10: Docker configuration and deployment
- Day 10: Testing and documentation

---

## Part 2: Built-in Agent System (LangChain/LangGraph)

### Architecture

```
src/
├── agents/
│   ├── __init__.py
│   ├── base_agent.py          # Abstract base agent
│   ├── langgraph_agent.py     # LangGraph implementation
│   ├── graph_builder.py       # Graph construction utilities
│   ├── tools/                 # Agent tools
│   │   ├── __init__.py
│   │   ├── web_search.py      # Tavily/DuckDuckGo search
│   │   ├── calculator.py      # Math operations
│   │   ├── code_executor.py   # Safe code execution
│   │   └── custom_tools.py    # User-defined tools
│   ├── nodes/                 # LangGraph nodes
│   │   ├── __init__.py
│   │   ├── classifier.py      # Intent classification
│   │   ├── responder.py       # LLM response generation
│   │   ├── tool_executor.py   # Tool execution logic
│   │   └── formatter.py       # TTS formatting
│   ├── presets/               # Preset agent configs
│   │   ├── __init__.py
│   │   ├── general_assistant.py
│   │   ├── technical_support.py
│   │   └── creative_writer.py
│   └── memory/                # Memory systems
│       ├── __init__.py
│       ├── conversation.py    # Conversation history
│       ├── vector_store.py    # Vector memory (Chroma)
│       └── entity_tracker.py  # Entity extraction
├── database/
│   └── agent_store.py         # Agent configuration DB
└── routing/
    ├── agent_selector.py      # n8n vs built-in routing
    └── strategy.py            # Routing strategies
```

### LangGraph State & Graph

**State Definition:**

```python
from typing import TypedDict, List, Optional, Annotated
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    """State for LangGraph agent"""

    # Messages
    messages: Annotated[List[BaseMessage], operator.add]

    # User context
    user_id: str
    conversation_id: str
    turn_number: int

    # Agent routing
    intent: Optional[str]
    agent_type: str  # "general" | "technical" | "creative"

    # Tool execution
    tools_used: List[str]
    tool_results: dict

    # Response
    final_response: Optional[str]
    tts_ready: bool
```

**Graph Structure:**

```python
from langgraph.graph import StateGraph, END

def create_agent_graph():
    """Build LangGraph state machine"""

    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("classifier", classify_intent)
    workflow.add_node("tool_selector", select_tools)
    workflow.add_node("llm_responder", generate_response)
    workflow.add_node("tool_executor", execute_tools)
    workflow.add_node("formatter", format_for_tts)

    # Add edges
    workflow.set_entry_point("classifier")

    workflow.add_conditional_edges(
        "classifier",
        route_by_intent,
        {
            "general": "llm_responder",
            "needs_tools": "tool_selector"
        }
    )

    workflow.add_edge("tool_selector", "tool_executor")
    workflow.add_edge("tool_executor", "llm_responder")
    workflow.add_edge("llm_responder", "formatter")
    workflow.add_edge("formatter", END)

    return workflow.compile()
```

**Example Flow:**

```
User: "What's the weather in Tokyo?"
    ↓
[Classifier Node]
  → intent: "needs_tools" (requires web search)
    ↓
[Tool Selector Node]
  → selected_tools: ["web_search"]
    ↓
[Tool Executor Node]
  → web_search("weather Tokyo") → "22°C, sunny"
    ↓
[LLM Responder Node]
  → "The weather in Tokyo is currently 22°C and sunny."
    ↓
[Formatter Node]
  → Split into sentences for TTS
    ↓
Output: ["The weather in Tokyo is currently 22°C and sunny."]
```

### Agent Presets

**General Assistant:**

```python
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

class GeneralAssistant:
    """General purpose conversational agent"""

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
        self.tools = ["web_search", "calculator"]

        self.system_prompt = """You are a helpful voice assistant.
        Keep responses concise and natural for text-to-speech.
        Limit responses to 2-3 sentences unless more detail is requested."""

    async def respond(self, state: AgentState):
        # Use LLM with tools
        response = await self.llm.ainvoke(
            state["messages"],
            tools=self.tools
        )
        return {"final_response": response.content}
```

**Technical Support:**

```python
class TechnicalSupport:
    """Technical troubleshooting agent"""

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
        self.tools = ["web_search", "code_executor"]

        self.system_prompt = """You are a technical support specialist.
        Provide clear, step-by-step solutions for technical problems.
        When providing code, explain what it does in simple terms."""
```

### Routing Logic

**Update `src/routing/agent_selector.py`:**

```python
from src.agents.langgraph_agent import LangGraphAgent
from src.speaker_manager import SpeakerManager

class AgentSelector:
    """Route between n8n and built-in agents"""

    def __init__(self, session_store, speaker_manager: SpeakerManager):
        self.session_store = session_store
        self.speaker_manager = speaker_manager

        # Built-in agent
        self.langgraph_agent = LangGraphAgent()

    async def route_transcript(self, user_id: str, transcript: str):
        """Route to appropriate agent"""

        # Get user session
        session = await self.session_store.get_or_create_session(user_id)

        # Check user preference
        use_builtin = os.getenv('USE_BUILTIN_AGENTS', 'false').lower() == 'true'

        if session.get('agent_type') == 'builtin' or use_builtin:
            # Use LangGraph agent
            logger.info(f"🤖 Routing to built-in LangGraph agent")
            response = await self.langgraph_agent.process(
                user_id=user_id,
                transcript=transcript,
                conversation_id=session['conversation_id']
            )

            # Play TTS response
            await self.speaker_manager.streaming_handler.on_chunk(response)

        else:
            # Use n8n webhook (existing flow)
            logger.info(f"📤 Routing to n8n webhook")
            await self.speaker_manager._send_to_n8n(transcript)
```

### Memory Integration

**Conversation Memory:**

```python
from langchain.memory import ConversationBufferMemory
from langchain_community.chat_message_histories import PostgresChatMessageHistory

class ConversationManager:
    """Manage conversation history with PostgreSQL"""

    def __init__(self, session_store):
        self.session_store = session_store

    async def get_memory(self, conversation_id: str):
        """Get conversation memory for LangChain"""

        # Get history from PostgreSQL
        history = PostgresChatMessageHistory(
            connection_string=os.getenv('DATABASE_URL'),
            session_id=str(conversation_id)
        )

        memory = ConversationBufferMemory(
            chat_memory=history,
            return_messages=True,
            memory_key="chat_history"
        )

        return memory
```

**Vector Memory (Chroma):**

```python
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

class VectorMemory:
    """Vector store for semantic memory"""

    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
        self.vector_store = Chroma(
            collection_name="voxbridge_memory",
            embedding_function=self.embeddings,
            persist_directory="./data/chroma"
        )

    async def add_memory(self, conversation_id: str, text: str, metadata: dict):
        """Add to vector memory"""
        self.vector_store.add_texts(
            texts=[text],
            metadatas=[{
                "conversation_id": conversation_id,
                **metadata
            }]
        )

    async def search_memory(self, query: str, limit: int = 5):
        """Search vector memory"""
        results = self.vector_store.similarity_search(query, k=limit)
        return results
```

### Dependencies

**Add to `pyproject.toml`:**

```toml
[project.dependencies]
# ... existing dependencies ...

# LangChain ecosystem
langchain = "^0.3.0"
langchain-core = "^0.3.0"
langgraph = "^0.2.0"
langchain-openai = "^0.2.0"
langchain-anthropic = "^0.2.0"
langchain-community = "^0.3.0"

# Tools
tavily-python = "^0.5.0"  # Web search

# Vector store
chromadb = "^0.5.0"
langchain-chroma = "^0.2.0"

# Optional: Other LLMs
# langchain-google-genai = "^2.0.0"
```

### Environment Variables

**Update `.env`:**

```env
# Built-in Agent System
USE_BUILTIN_AGENTS=true
DEFAULT_AGENT_TYPE=builtin  # builtin | n8n

# LLM Configuration
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEFAULT_LLM_PROVIDER=openai  # openai | anthropic | google

# Tool Configuration
TAVILY_API_KEY=tvly-...
ENABLE_CODE_EXECUTION=false
ENABLE_WEB_SEARCH=true

# Memory Configuration
VECTOR_STORE=chroma  # chroma | qdrant
VECTOR_STORE_PATH=./data/chroma
CONVERSATION_MEMORY_LIMIT=10
```

### Implementation Timeline

**Week 1: LangGraph Foundation**
- Day 1-2: Install LangChain/LangGraph, create base agent interface
- Day 2-3: Build simple state graph with classifier and responder nodes
- Day 3: Test with single-turn conversations (no tools)

**Week 2: Tools + Multi-Agent**
- Day 4-5: Implement web search and calculator tools
- Day 5: Add tool executor node to graph
- Day 6: Create agent presets (general, technical, creative)
- Day 7: Implement routing logic (n8n vs built-in)

**Week 3: Memory + Context**
- Day 8-9: PostgreSQL conversation history integration
- Day 9: Vector memory setup with Chroma
- Day 10: Context window management
- Day 10: Test multi-turn conversations with memory

**Week 4: Frontend Integration**
- Day 11-12: Agent selection UI in frontend
- Day 12: Tool usage visualization
- Day 13: Memory/context viewer
- Day 14: End-to-end testing and polish

---

## Complete Timeline

### Frontend: ~1.5-2 weeks
- Week 1: Foundation + Monitoring (3-4 days)
- Week 2: Controls + Response Stream (3-4 days)
- Week 2-3: Polish + Docker (2-3 days)

### Agent System: ~2-3 weeks
- Week 1: LangGraph Foundation (3-4 days)
- Week 2: Tools + Multi-Agent (4 days)
- Week 3: Memory + Context (3-4 days)
- Week 4: Frontend Integration (4 days)

**Total: 4-5 weeks (~20-25 development days)**

---

## Success Criteria

### Frontend
- ✅ React + Vite + TypeScript project initialized
- ✅ Chatterbox shadcn/ui configuration copied
- ⏳ Real-time transcription display with <500ms latency
- ⏳ All connection statuses visible at a glance
- ⏳ Channel selector works with all Discord guilds
- ⏳ TTS testing functional
- ⏳ Matches Chatterbox aesthetic (dark mode, card-based)
- ⏳ Responsive on desktop and tablet

### Agent System
- ⏳ LangGraph agents respond within 3-5 seconds
- ⏳ Tool execution works (web search, calculator)
- ⏳ Conversation context preserved across turns
- ⏳ Seamless routing between n8n and built-in agents
- ⏳ Agent presets (general, technical, creative) functional
- ⏳ Frontend shows agent selection and tool usage

---

## Next Immediate Steps

1. ✅ **DONE**: Create React + Vite + TypeScript project
2. ✅ **DONE**: Copy components.json from Chatterbox
3. **TODO**: Create shadcn.css and globals.css with Chatterbox theme
4. **TODO**: Install additional dependencies (React Query, Wouter, Lucide, etc.)
5. **TODO**: Set up tsconfig.json with path aliases
6. **TODO**: Create base layout structure
7. **TODO**: Add backend API endpoints to discord_bot.py
8. **TODO**: Build connection status component
9. **TODO**: Implement WebSocket hook for real-time updates
10. **TODO**: Create live transcription display

---

## File Locations

### Existing
- VoxBridge project: `/home/wiley/Docker/voxbridge`
- Frontend project: `/home/wiley/Docker/voxbridge/frontend` ✅
- Chatterbox frontend (reference): `/home/wiley/Docker/chatterbox-tts-api/frontend`

### To Create
- Frontend styles: `/home/wiley/Docker/voxbridge/frontend/src/styles/`
- Frontend components: `/home/wiley/Docker/voxbridge/frontend/src/components/`
- Backend API updates: `/home/wiley/Docker/voxbridge/src/discord_bot.py`
- Agent system: `/home/wiley/Docker/voxbridge/src/agents/`
- Docker config: `/home/wiley/Docker/voxbridge/frontend/docker/Dockerfile`

---

## Commands Reference

```bash
# Frontend development
cd /home/wiley/Docker/voxbridge/frontend
npm install
npm run dev  # Runs on http://localhost:5173 (Vite default)

# Backend (Discord bot with API)
cd /home/wiley/Docker/voxbridge
docker compose up -d

# Install LangChain dependencies (when ready)
cd /home/wiley/Docker/voxbridge
pip install langchain langgraph langchain-openai tavily-python chromadb

# Build and deploy frontend container
docker compose build voxbridge-frontend
docker compose up -d voxbridge-frontend
# Access at http://localhost:4901
```

---

This plan is ready for execution! 🚀
