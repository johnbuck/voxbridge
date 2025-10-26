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
  tts_voice: string | null;
  tts_rate: number;
  tts_pitch: number;
  created_at: string;
  updated_at: string;
}

export interface AgentCreateRequest {
  name: string;
  system_prompt: string;
  temperature?: number;
  llm_provider?: string;
  llm_model?: string;
  tts_voice?: string | null;
  tts_rate?: number;
  tts_pitch?: number;
}

export interface AgentUpdateRequest {
  name?: string;
  system_prompt?: string;
  temperature?: number;
  llm_provider?: string;
  llm_model?: string;
  tts_voice?: string | null;
  tts_rate?: number;
  tts_pitch?: number;
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

    return response.json();
  }

  // Health & Status
  async getHealth(): Promise<HealthStatus> {
    return this.request<HealthStatus>('/health');
  }

  async getStatus(): Promise<DetailedStatus> {
    return this.request<DetailedStatus>('/status');
  }

  // Voice Controls
  async joinChannel(channelId: string, guildId: string): Promise<{ success: boolean; message: string }> {
    return this.request('/voice/join', {
      method: 'POST',
      body: JSON.stringify({ channelId, guildId }),
    });
  }

  async leaveChannel(): Promise<{ success: boolean; message: string }> {
    return this.request('/voice/leave', {
      method: 'POST',
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
}

export const api = new ApiClient();
