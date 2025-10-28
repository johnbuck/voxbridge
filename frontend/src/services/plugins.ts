/**
 * Plugin API Client
 * Handles plugin management API calls
 */

// In production (served by nginx), use relative URLs
// In development, use VITE_API_URL or fallback to localhost
const API_BASE_URL = import.meta.env.PROD
  ? '' // Relative URLs in production (proxied by nginx)
  : (import.meta.env.VITE_API_URL || 'http://localhost:4900');

export interface Plugin {
  plugin_type: string;
  agent_id: string;
  agent_name: string;
  status: 'running' | 'stopped' | 'error';
  enabled: boolean;
  resource_usage?: {
    cpu_percent: number;
    memory_mb: number;
    gpu_memory_mb?: number;
  };
  uptime_seconds?: number;
  last_error?: string;
}

export interface PluginStats {
  total_plugins: number;
  active_plugins: number;
  failed_plugins: number;
  plugins_by_type: Record<string, number>;
  resource_usage: {
    total_cpu_percent: number;
    total_memory_mb: number;
    total_gpu_memory_mb?: number;
  };
}

class PluginApiClient {
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

  // Get all plugins
  async getPlugins(): Promise<Plugin[]> {
    const response = await this.request<{ plugins: Plugin[] }>('/api/plugins');
    return response.plugins || [];
  }

  // Get plugin statistics
  async getPluginStats(): Promise<PluginStats> {
    return this.request<PluginStats>('/api/plugins/stats');
  }

  // Start a plugin (future endpoint)
  async startPlugin(agentId: string, pluginType: string): Promise<void> {
    await this.request(`/api/plugins/${pluginType}/start`, {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId }),
    });
  }

  // Stop a plugin (future endpoint)
  async stopPlugin(agentId: string, pluginType: string): Promise<void> {
    await this.request(`/api/plugins/${pluginType}/stop`, {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId }),
    });
  }

  // Restart a plugin (future endpoint)
  async restartPlugin(agentId: string, pluginType: string): Promise<void> {
    await this.request(`/api/plugins/${pluginType}/restart`, {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId }),
    });
  }
}

export const pluginApi = new PluginApiClient();
