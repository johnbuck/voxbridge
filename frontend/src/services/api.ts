/**
 * VoxBridge API Client
 * Handles all communication with the backend FastAPI server
 */

// In production (served by nginx), use relative URLs
// In development, use VITE_API_URL or fallback to localhost
const API_BASE_URL = import.meta.env.PROD
  ? '' // Relative URLs in production (proxied by nginx)
  : (import.meta.env.VITE_API_URL || 'http://localhost:4900');

export interface HealthStatus {
  status: string;
  botReady: boolean;
  inVoiceChannel: boolean;
  speakerLocked: boolean;
  activeSpeaker: string | null;
  timestamp: string;
}

export interface DetailedStatus {
  bot: {
    username: string;
    id: string;
    ready: boolean;
  };
  voice: {
    connected: boolean;
    channelId: string | null;
    channelName: string | null;
    guildId: string | null;
    guildName: string | null;
  };
  speaker: {
    locked: boolean;
    activeSpeaker: string | null;
    speakingDuration: number | null;
    silenceDuration: number | null;
  };
  whisperx: {
    serverConfigured: boolean;
    serverUrl: string;
  };
  services: {
    chatterbox: boolean;
    chatterboxUrl: string;
    n8nWebhook: boolean;
    n8nWebhookUrl: string;
  };
  devices?: {
    whisperx: string;
    chatterbox: string;
  };
}

export interface VoiceChannel {
  id: string;
  name: string;
  userCount: number;
}

export interface Guild {
  id: string;
  name: string;
  channels: VoiceChannel[];
}

export interface Transcript {
  userId: string;
  text: string;
  timestamp: string;
  isFinal: boolean;
}

export interface LatencyStats {
  avg: number;
  p50: number;
  p95: number;
  p99: number;
}

export interface Metrics {
  // Legacy metrics
  latency: LatencyStats;
  n8nResponseLatency: LatencyStats;
  n8nFirstChunkLatency: LatencyStats;
  ttsFirstByteLatency: LatencyStats;

  // Phase 1: Speech → Transcription (seconds)
  whisperConnectionLatency: LatencyStats;
  firstPartialTranscriptLatency: LatencyStats;
  transcriptionDuration: LatencyStats;
  silenceDetectionLatency: LatencyStats;  // milliseconds

  // Phase 2: AI Processing (seconds)
  aiGenerationLatency: LatencyStats;
  responseParsingLatency: LatencyStats;  // milliseconds

  // Phase 3: TTS Generation (seconds)
  ttsQueueLatency: LatencyStats;
  ttsGenerationLatency: LatencyStats;

  // Phase 4: Audio Playback (seconds)
  audioPlaybackLatency: LatencyStats;
  ffmpegProcessingLatency: LatencyStats;  // milliseconds

  // End-to-End (seconds)
  totalPipelineLatency: LatencyStats;
  timeToFirstAudio: LatencyStats;

  // Counters
  transcriptCount: number;
  errorRate: number;
  uptime: number;
}

export interface RuntimeConfig {
  SILENCE_THRESHOLD_MS?: number;
  MAX_SPEAKING_TIME_MS?: number;
  USE_STREAMING?: boolean;
}

// VoxBridge 2.0: Agent Management
export interface Agent {
  id: string;
  name: string;
  system_prompt: string;
  temperature: number;
  llm_provider: string;
  llm_model: string;
  use_n8n: boolean; // Phase 3: Use n8n webhook instead of direct LLM
  n8n_webhook_url: string | null; // Phase 3: Per-agent n8n webhook URL
  is_default: boolean; // Phase 5: Mark as default agent
  tts_voice: string | null;
  tts_rate: number;
  tts_pitch: number;
  max_utterance_time_ms?: number; // Voice configuration: max duration per speaking turn
  plugins?: {
    discord?: {
      enabled: boolean;
      bot_token: string;
      auto_join: boolean;
      command_prefix: string;
      channels: string[];
    };
  };
  created_at: string;
  updated_at: string;
}

export interface AgentCreateRequest {
  name: string;
  system_prompt: string;
  temperature?: number;
  llm_provider?: string;
  llm_model?: string;
  use_n8n?: boolean; // Phase 3: Use n8n webhook instead of direct LLM
  n8n_webhook_url?: string | null; // Phase 3: Per-agent n8n webhook URL
  is_default?: boolean; // Phase 5: Mark as default agent
  tts_voice?: string | null;
  tts_rate?: number;
  tts_pitch?: number;
  max_utterance_time_ms?: number; // Voice configuration: max duration per speaking turn
  plugins?: {
    discord?: {
      enabled: boolean;
      bot_token: string;
      auto_join: boolean;
      command_prefix: string;
      channels: string[];
    };
  };
}

export interface AgentUpdateRequest {
  name?: string;
  system_prompt?: string;
  temperature?: number;
  llm_provider?: string;
  llm_model?: string;
  use_n8n?: boolean; // Phase 3: Use n8n webhook instead of direct LLM
  n8n_webhook_url?: string | null; // Phase 3: Per-agent n8n webhook URL
  is_default?: boolean; // Phase 5: Mark as default agent
  tts_voice?: string | null;
  tts_rate?: number;
  tts_pitch?: number;
  max_utterance_time_ms?: number; // Voice configuration: max duration per speaking turn
  plugins?: {
    discord?: {
      enabled: boolean;
      bot_token: string;
      auto_join: boolean;
      command_prefix: string;
      channels: string[];
    };
  };
}

// VoxBridge 2.0 Phase 4: Session Management
export interface Session {
  id: string;
  user_id: string;
  user_name: string | null;
  title: string | null;
  agent_id: string;
  active: boolean;
  started_at: string;
  ended_at: string | null;
  session_type: string;
  session_metadata: string | null;
  message_count: number;
}

export interface SessionCreateRequest {
  user_id: string;
  agent_id: string;
  user_name?: string | null;
  title?: string | null;
  session_type?: string;
  session_metadata?: string | null;
}

export interface SessionUpdateRequest {
  title?: string;
  active?: boolean;
}

export interface Message {
  id: number;
  session_id: string;
  role: string;
  content: string;
  timestamp: string;
  audio_duration_ms: number | null;
  tts_duration_ms: number | null;
  llm_latency_ms: number | null;
  total_latency_ms: number | null;
}

export interface MessageRequest {
  role: string;
  content: string;
  audio_duration_ms?: number | null;
  tts_duration_ms?: number | null;
  llm_latency_ms?: number | null;
  total_latency_ms?: number | null;
}

// VoxBridge 2.0 Phase 6.5: LLM Provider Management
export interface LLMProvider {
  id: string;
  name: string;
  base_url: string;
  has_api_key: boolean;  // API key never exposed
  provider_type: string | null;
  models: string[];
  default_model: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LLMProviderCreate {
  name: string;
  base_url: string;
  api_key?: string | null;
  provider_type?: string | null;
  default_model?: string | null;
  is_active?: boolean;
}

export interface LLMProviderUpdate {
  name?: string;
  base_url?: string;
  api_key?: string | null;
  provider_type?: string | null;
  default_model?: string | null;
  is_active?: boolean;
}

export interface TTSOptions {
  // Streaming settings
  chunkSize?: number;
  streamingStrategy?: 'sentence' | 'paragraph' | 'fixed' | 'word';
  streamingQuality?: 'fast' | 'balanced' | 'high';
  streamingBufferSize?: number;

  // Voice generation (required when sending from dashboard)
  temperature: number;
  exaggeration: number;
  cfgWeight: number;

  // Output settings
  speedFactor?: number;
  outputFormat?: 'wav' | 'mp3';

  // Voice settings
  voiceMode?: 'default' | 'clone';
  voiceId?: string;
  referenceAudioFilename?: string;
}

export interface StreamingConfig {
  enabled: boolean;
  chunking_strategy: 'sentence' | 'paragraph' | 'word' | 'fixed';
  min_chunk_length: number;
  max_concurrent_tts: number;
  error_strategy: 'skip' | 'retry' | 'fallback';
  interruption_strategy: 'immediate' | 'graceful' | 'drain';
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`API Error: ${response.status} - ${error}`);
    }

    // 204 No Content returns empty body - don't try to parse JSON
    if (response.status === 204 || response.headers.get('content-length') === '0') {
      return undefined as T;
    }

    return response.json();
  }

  // Health & Status
  async getHealth(): Promise<HealthStatus> {
    return this.request<HealthStatus>('/health');
  }

  async getStatus(): Promise<DetailedStatus> {
    return this.request<DetailedStatus>('/status');
  }

  // Voice Controls (Plugin-based endpoints)
  async joinChannel(agentId: string, channelId: string, guildId: string, sessionId?: string | null): Promise<{ success: boolean; message: string }> {
    // Custom JSON serialization to preserve large integers as numeric literals
    // Discord IDs exceed JavaScript's safe integer limit, so we build JSON manually
    // Phase 6.X: Added optional sessionId for unified conversation threading
    const sessionIdField = sessionId ? `,"session_id":"${sessionId}"` : '';
    const body = `{"agent_id":"${agentId}","channel_id":${channelId},"guild_id":${guildId}${sessionIdField}}`;

    return this.request('/api/plugins/discord/voice/join', {
      method: 'POST',
      body: body,
    });
  }

  async leaveChannel(agentId: string, guildId: string): Promise<{ success: boolean; message: string }> {
    // Custom JSON serialization to preserve large integers as numeric literals
    const body = `{"agent_id":"${agentId}","guild_id":${guildId}}`;

    return this.request('/api/plugins/discord/voice/leave', {
      method: 'POST',
      body: body,
    });
  }

  async speak(text: string, options: any = {}): Promise<{ success: boolean; message: string }> {
    return this.request('/voice/speak', {
      method: 'POST',
      body: JSON.stringify({
        output: { content: text },
        options,
      }),
    });
  }

  // Channels
  async getChannels(): Promise<{ guilds: Guild[] }> {
    return this.request<{ guilds: Guild[] }>('/api/channels');
  }

  // Transcripts
  async getTranscripts(limit: number = 10): Promise<{ transcripts: Transcript[] }> {
    return this.request<{ transcripts: Transcript[] }>(`/api/transcripts?limit=${limit}`);
  }

  // Metrics
  async getMetrics(): Promise<Metrics> {
    return this.request<Metrics>('/api/metrics');
  }

  // Configuration
  async updateConfig(config: RuntimeConfig): Promise<{ success: boolean }> {
    return this.request<{ success: boolean }>('/api/config', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async getStreamingConfig(): Promise<StreamingConfig> {
    return this.request<StreamingConfig>('/api/streaming-config');
  }

  async updateStreamingConfig(config: Partial<StreamingConfig>): Promise<StreamingConfig> {
    return this.request<StreamingConfig>('/api/streaming-config', {
      method: 'PUT',
      body: JSON.stringify(config),
    });
  }

  async resetStreamingConfig(): Promise<StreamingConfig> {
    return this.request<StreamingConfig>('/api/streaming-config/reset', {
      method: 'POST',
    });
  }

  // Speaker Management
  async unlockSpeaker(): Promise<{ success: boolean; previousSpeaker: string | null }> {
    return this.request<{ success: boolean; previousSpeaker: string | null }>('/api/speaker/unlock', {
      method: 'POST',
    });
  }

  // TTS Options
  async setTTSOptions(enabled: boolean, options: TTSOptions): Promise<{ success: boolean; message: string }> {
    return this.request<{ success: boolean; message: string }>('/api/tts/config', {
      method: 'POST',
      body: JSON.stringify({ enabled, options }),
    });
  }

  // VoxBridge 2.0: Agent Management
  async getAgents(): Promise<Agent[]> {
    return this.request<Agent[]>('/api/agents');
  }

  async getAgent(agentId: string): Promise<Agent> {
    return this.request<Agent>(`/api/agents/${agentId}`);
  }

  async createAgent(agent: AgentCreateRequest): Promise<Agent> {
    return this.request<Agent>('/api/agents', {
      method: 'POST',
      body: JSON.stringify(agent),
    });
  }

  async updateAgent(agentId: string, updates: AgentUpdateRequest): Promise<Agent> {
    return this.request<Agent>(`/api/agents/${agentId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  }

  async deleteAgent(agentId: string): Promise<void> {
    await this.request<void>(`/api/agents/${agentId}`, {
      method: 'DELETE',
    });
  }

  async setDefaultAgent(agentId: string): Promise<Agent> {
    return this.request<Agent>(`/api/agents/${agentId}/set-default`, {
      method: 'PUT',
    });
  }

  // VoxBridge 2.0 Phase 4: Session Management
  async getSessions(userId?: string | null, activeOnly: boolean = false, limit: number = 50): Promise<Session[]> {
    // If userId is provided, filter by user; otherwise return all sessions
    const userIdParam = userId ? `user_id=${userId}&` : '';
    return this.request<Session[]>(`/api/sessions?${userIdParam}active_only=${activeOnly}&limit=${limit}`);
  }

  async getSession(sessionId: string): Promise<Session> {
    return this.request<Session>(`/api/sessions/${sessionId}`);
  }

  async createSession(request: SessionCreateRequest): Promise<Session> {
    return this.request<Session>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async updateSession(sessionId: string, updates: SessionUpdateRequest): Promise<Session> {
    return this.request<Session>(`/api/sessions/${sessionId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    });
  }

  async deleteSession(sessionId: string): Promise<void> {
    await this.request<void>(`/api/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  }

  async getSessionMessages(sessionId: string, limit?: number): Promise<Message[]> {
    const url = limit
      ? `/api/sessions/${sessionId}/messages?limit=${limit}`
      : `/api/sessions/${sessionId}/messages`;
    return this.request<Message[]>(url);
  }

  async addMessage(sessionId: string, message: MessageRequest): Promise<Message> {
    return this.request<Message>(`/api/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify(message),
    });
  }

  // VoxBridge 2.0: Per-Agent Discord Plugin Control
  // Note: These currently use global endpoints as placeholders
  // Will be updated to per-agent endpoints in Phase 4

  async getAgentDiscordStatus(agentId: string): Promise<any> {
    // Now using per-agent plugin endpoint
    return this.request(`/api/plugins/discord/voice/status/${agentId}`);
  }

  async agentJoinVoice(agentId: string, channelId: string, guildId: string): Promise<{ success: boolean; message: string }> {
    // Now using plugin-based endpoints
    return this.joinChannel(agentId, channelId, guildId);
  }

  async agentLeaveVoice(agentId: string, guildId: string): Promise<{ success: boolean; message: string }> {
    // Now using plugin-based endpoints
    return this.leaveChannel(agentId, guildId);
  }

  async agentUnlockSpeaker(_agentId: string): Promise<{ success: boolean; previousSpeaker: string | null }> {
    // TODO: Replace with per-agent endpoint when backend is ready
    // return this.request(`/api/agents/${_agentId}/plugins/discord/speaker/unlock`, {
    //   method: 'POST',
    // });
    return this.unlockSpeaker();
  }

  async agentTestTTS(_agentId: string, text: string, options?: any): Promise<{ success: boolean; message: string }> {
    // TODO: Replace with per-agent endpoint when backend is ready
    // return this.request(`/api/agents/${_agentId}/plugins/discord/tts/speak`, {
    //   method: 'POST',
    //   body: JSON.stringify({ text, options }),
    // });
    return this.speak(text, options);
  }

  // VoxBridge 2.0 Phase 6.5: LLM Provider Management
  async getLLMProviders(): Promise<LLMProvider[]> {
    return this.request<LLMProvider[]>('/api/settings/llm-providers');
  }

  async getLLMProvider(providerId: string): Promise<LLMProvider> {
    return this.request<LLMProvider>(`/api/settings/llm-providers/${providerId}`);
  }

  async createLLMProvider(provider: LLMProviderCreate): Promise<LLMProvider> {
    return this.request<LLMProvider>('/api/settings/llm-providers', {
      method: 'POST',
      body: JSON.stringify(provider),
    });
  }

  async updateLLMProvider(providerId: string, updates: LLMProviderUpdate): Promise<LLMProvider> {
    return this.request<LLMProvider>(`/api/settings/llm-providers/${providerId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  }

  async deleteLLMProvider(providerId: string): Promise<void> {
    await this.request<void>(`/api/settings/llm-providers/${providerId}`, {
      method: 'DELETE',
    });
  }

  async testLLMProviderConnection(providerId: string): Promise<{ success: boolean; models_count?: number; response_time_ms?: number; error?: string }> {
    return this.request(`/api/settings/llm-providers/${providerId}/test`, {
      method: 'POST',
    });
  }

  async fetchLLMProviderModels(providerId: string): Promise<{ success: boolean; models_count: number; models: string[] }> {
    return this.request(`/api/settings/llm-providers/${providerId}/fetch-models`, {
      method: 'POST',
    });
  }
}

export const api = new ApiClient();
