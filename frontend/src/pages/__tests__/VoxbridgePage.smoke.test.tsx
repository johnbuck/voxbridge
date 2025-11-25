/**
 * Smoke tests for VoxbridgePage
 * These tests verify basic rendering and infrastructure setup
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { VoxbridgePage } from '../VoxbridgePage';
import { ToastProvider } from '../../components/ui/toast';
import type { Agent, Session } from '../../services/api';

// Mock the API module
vi.mock('../../services/api', () => ({
  api: {
    getSessionMessages: vi.fn(),
    getSessions: vi.fn(),
    getAgents: vi.fn(),
    createSession: vi.fn(),
  },
}));

// Mock the logger module
vi.mock('../../utils/logger', () => ({
  createLogger: vi.fn(() => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    trace: vi.fn(),
  })),
  LogLevel: {
    TRACE: 0,
    DEBUG: 1,
    INFO: 2,
    WARN: 3,
    ERROR: 4,
  },
}));

// Mock the useWebRTCAudio hook
vi.mock('../../hooks/useWebRTCAudio', () => ({
  useWebRTCAudio: vi.fn(() => ({
    isConnected: false,
    isRecording: false,
    isSpeaking: false,
    isProcessing: false,
    error: null,
    connect: vi.fn(),
    disconnect: vi.fn(),
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    startSession: vi.fn(),
    endSession: vi.fn(),
  })),
}));

// Import mocked api after mocking
import { api } from '../../services/api';

describe('VoxbridgePage Smoke Tests', () => {
  let queryClient: QueryClient;

  const mockAgent: Agent = {
    id: 'agent-123',
    name: 'Test Agent',
    system_prompt: 'You are a helpful assistant',
    temperature: 0.7,
    llm_provider: 'openrouter',
    llm_model: 'mistralai/mistral-7b-instruct',
    use_n8n: false,
    n8n_webhook_url: null,
    is_default: true,
    memory_scope: 'global',
    tts_voice: 'default',
    tts_exaggeration: 1.0,
    tts_cfg_weight: 0.7,
    tts_temperature: 0.3,
    tts_language: 'en',
    filter_actions_for_tts: false,
    created_at: '2025-11-20T00:00:00Z',
    updated_at: '2025-11-20T00:00:00Z',
  };

  const mockSession: Session = {
    id: 'session-456',
    user_id: 'user-789',
    user_name: 'Test User',
    title: 'Test Session',
    agent_id: 'agent-123',
    active: true,
    started_at: '2025-11-20T00:00:00Z',
    ended_at: null,
    session_type: 'webrtc',
    session_metadata: null,
    message_count: 0,
  };

  beforeEach(() => {
    // Create a new QueryClient for each test
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
      },
    });

    // Setup default API mocks
    vi.mocked(api.getAgents).mockResolvedValue([mockAgent]);
    vi.mocked(api.getSessions).mockResolvedValue([mockSession]);
    vi.mocked(api.getSessionMessages).mockResolvedValue([]);
    vi.mocked(api.createSession).mockResolvedValue(mockSession);

    // Mock WebSocket
    global.WebSocket = vi.fn().mockImplementation(() => ({
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      close: vi.fn(),
      send: vi.fn(),
      readyState: 1, // OPEN
    })) as any;
  });

  it('should render without crashing', () => {
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <VoxbridgePage />
        </ToastProvider>
      </QueryClientProvider>
    );

    expect(container).toBeTruthy();
  });

  it('should fetch agents on mount', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <VoxbridgePage />
        </ToastProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(api.getAgents).toHaveBeenCalled();
    });
  });

  it('should fetch sessions on mount', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <VoxbridgePage />
        </ToastProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(api.getSessions).toHaveBeenCalled();
    });
  });

  it('should have accessible heading', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <VoxbridgePage />
        </ToastProvider>
      </QueryClientProvider>
    );

    // Wait for component to render
    await waitFor(() => {
      expect(api.getAgents).toHaveBeenCalled();
    });

    // Check that some key elements are present
    // Note: Exact text may vary, so we use flexible queries
    const headings = screen.queryAllByRole('heading');
    expect(headings.length).toBeGreaterThan(0);
  });
});
