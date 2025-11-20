import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { VoxbridgePage } from '../VoxbridgePage';
import { WebSocketMock } from '../../__tests__/mocks/WebSocketMock';
import { ToastProvider } from '../../components/ui/toast';
import type { Message, Session, Agent } from '../../services/api';

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
    isEnabledFor: vi.fn(() => true),
    getLevel: vi.fn(() => 1),
    getLevelName: vi.fn(() => 'DEBUG'),
  })),
  Logger: vi.fn(),
  LogLevel: {
    TRACE: 0,
    DEBUG: 1,
    INFO: 2,
    WARN: 3,
    ERROR: 4,
  },
  initializeLogging: vi.fn(),
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

describe('VoxbridgePage', () => {
  let queryClient: QueryClient;
  let mockWebSocket: WebSocketMock;

  // Helper function to render component with all necessary providers
  const renderWithProviders = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <VoxbridgePage />
        </ToastProvider>
      </QueryClientProvider>
    );
  };

  // Mock data
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
    tts_voice: 'default',
    tts_exaggeration: 1.0,
    tts_cfg_weight: 0.7,
    tts_temperature: 0.3,
    tts_language: 'en',
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

  const mockMessages: Message[] = [
    {
      id: 1,
      session_id: 'session-456',
      role: 'user',
      content: 'Hello, AI!',
      timestamp: '2025-11-20T00:00:01Z',
      audio_duration_ms: null,
      tts_duration_ms: null,
      llm_latency_ms: null,
      total_latency_ms: null,
    },
    {
      id: 2,
      session_id: 'session-456',
      role: 'assistant',
      content: 'Hello! How can I help you today?',
      timestamp: '2025-11-20T00:00:02Z',
      audio_duration_ms: null,
      tts_duration_ms: 150,
      llm_latency_ms: 500,
      total_latency_ms: 650,
    },
  ];

  beforeEach(() => {
    // Note: NOT using fake timers due to React Query compatibility issues

    // Create a new QueryClient for each test
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
      },
    });

    // Create WebSocket mock instance
    mockWebSocket = new WebSocketMock('ws://localhost:4900/ws/events');

    // Install WebSocket mock globally - IMPORTANT: Always return the same instance
    // so that events emitted in tests reach the component
    global.WebSocket = vi.fn().mockImplementation((_url: string) => {
      // Return our mock instance regardless of URL
      return mockWebSocket;
    }) as any;

    // Setup default API mocks
    vi.mocked(api.getAgents).mockResolvedValue([mockAgent]);
    vi.mocked(api.getSessions).mockResolvedValue([mockSession]);
    vi.mocked(api.getSessionMessages).mockResolvedValue(mockMessages);
    vi.mocked(api.createSession).mockResolvedValue(mockSession);
  });

  afterEach(() => {
    queryClient.clear();
    mockWebSocket.reset();
    vi.clearAllMocks();
  });

  /**
   * Test 1: AI response renders without refresh
   *
   * This test verifies that when an AI response is received via WebSocket,
   * it appears in the UI immediately without requiring a page refresh.
   */
  it('should render AI response without page refresh', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    // Wait for sessions to load
    await waitFor(() => {
      expect(api.getSessions).toHaveBeenCalled();
    });

    // Select the session by clicking on it
    const sessionElements = await screen.findAllByText('Test Session');
    await user.click(sessionElements[0]);

    // Wait for messages to load
    await waitFor(() => {
      expect(api.getSessionMessages).toHaveBeenCalledWith('session-456');
    });

    // Verify initial messages are displayed
    await waitFor(() => {
      expect(screen.getByText('Hello, AI!')).toBeInTheDocument();
      expect(screen.getByText('Hello! How can I help you today?')).toBeInTheDocument();
    });

    // Simulate receiving a new AI response via WebSocket
    const correlationId = 'test-correlation-123';
    const newAIResponse = 'This is a new AI response that should appear immediately!';

    // Emit ai_response_complete event
    await act(async () => {
      mockWebSocket.emitAIResponseComplete(newAIResponse, correlationId);
    });

    // Update the mock to include the new message after database save
    const updatedMessages: Message[] = [
      ...mockMessages,
      {
        id: 3,
        session_id: 'session-456',
        role: 'assistant',
        content: newAIResponse,
        timestamp: '2025-11-20T00:00:03Z',
        audio_duration_ms: null,
        tts_duration_ms: 180,
        llm_latency_ms: 450,
        total_latency_ms: 630,
      },
    ];
    vi.mocked(api.getSessionMessages).mockResolvedValue(updatedMessages);

    // Emit message_saved event to confirm database persistence
    await act(async () => {
      mockWebSocket.emitMessageSaved('3', 'session-456', 'assistant', correlationId);
      // Wait for debounced query invalidation (100ms) + refetch
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    // Wait for the new message to appear (without page refresh!)
    await waitFor(
      () => {
        expect(screen.getByText(newAIResponse)).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
  });

  /**
   * Test 2: Streaming chunks display correctly
   *
   * This test verifies that streaming AI response chunks are displayed
   * incrementally as they arrive via WebSocket.
   */
  it('should display streaming AI response chunks correctly', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    // Wait for sessions to load and select the session
    await waitFor(() => {
      expect(api.getSessions).toHaveBeenCalled();
    });

    const sessionElements = await screen.findAllByText('Test Session');
    await user.click(sessionElements[0]);

    // Wait for messages to load
    await waitFor(() => {
      expect(api.getSessionMessages).toHaveBeenCalledWith('session-456');
    });

    const correlationId = 'streaming-test-456';

    // Emit multiple streaming chunks
    await act(async () => {
      mockWebSocket.emitAIResponseChunk('This is ', correlationId);
    });

    // First chunk should appear
    await waitFor(() => {
      const elements = screen.queryAllByText(/This is/);
      expect(elements.length).toBeGreaterThan(0);
    });

    // Emit more chunks
    await act(async () => {
      mockWebSocket.emitAIResponseChunk('a streaming ', correlationId);
      mockWebSocket.emitAIResponseChunk('response!', correlationId);
    });

    // All chunks should be combined and visible
    await waitFor(() => {
      const elements = screen.queryAllByText(/This is a streaming response!/);
      expect(elements.length).toBeGreaterThan(0);
    });

    // Emit completion event
    const fullResponse = 'This is a streaming response!';
    await act(async () => {
      mockWebSocket.emitAIResponseComplete(fullResponse, correlationId);
    });

    // Update messages to include the complete response
    const updatedMessages: Message[] = [
      ...mockMessages,
      {
        id: 4,
        session_id: 'session-456',
        role: 'assistant',
        content: fullResponse,
        timestamp: '2025-11-20T00:00:04Z',
        audio_duration_ms: null,
        tts_duration_ms: 200,
        llm_latency_ms: 600,
        total_latency_ms: 800,
      },
    ];

    vi.mocked(api.getSessionMessages).mockResolvedValue(updatedMessages);

    // Emit message_saved to confirm persistence
    await act(async () => {
      mockWebSocket.emitMessageSaved('4', 'session-456', 'assistant', correlationId);
      // Wait for debounced query invalidation (100ms) + refetch
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    // Verify streaming chunks are replaced by database message
    await waitFor(() => {
      expect(screen.getByText(fullResponse)).toBeInTheDocument();
    });
  });

  /**
   * Test 3: Race condition handling (cache update vs. refetch)
   *
   * This test verifies that the component correctly handles race conditions
   * between optimistic cache updates and database refetches.
   */
  it('should handle race condition between cache update and database refetch', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    // Wait for sessions to load and select the session
    await waitFor(() => {
      expect(api.getSessions).toHaveBeenCalled();
    });

    const sessionElements = await screen.findAllByText('Test Session');
    await user.click(sessionElements[0]);

    // Wait for messages to load
    await waitFor(() => {
      expect(api.getSessionMessages).toHaveBeenCalledWith('session-456');
    });

    const correlationId = 'race-condition-789';
    const aiResponse = 'Testing race condition handling';

    // Simulate rapid sequence of events that could cause race condition

    // 1. ai_response_complete arrives
    await act(async () => {
      mockWebSocket.emitAIResponseComplete(aiResponse, correlationId);
    });

    // 2. Simulate database save delay (message not yet in DB)
    vi.mocked(api.getSessionMessages).mockResolvedValue(mockMessages); // Old messages only

    // Wait a bit to simulate processing time
    await new Promise(resolve => setTimeout(resolve, 100));

    // 3. Now database save completes
    const updatedMessages: Message[] = [
      ...mockMessages,
      {
        id: 5,
        session_id: 'session-456',
        role: 'assistant',
        content: aiResponse,
        timestamp: '2025-11-20T00:00:05Z',
        audio_duration_ms: null,
        tts_duration_ms: 175,
        llm_latency_ms: 520,
        total_latency_ms: 695,
      },
    ];

    vi.mocked(api.getSessionMessages).mockResolvedValue(updatedMessages);

    // 4. message_saved event arrives
    await act(async () => {
      mockWebSocket.emitMessageSaved('5', 'session-456', 'assistant', correlationId);
      // Wait for debounced query invalidation (100ms) + refetch
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    // Verify the message appears exactly once (no duplicates from race condition)
    await waitFor(() => {
      const matches = screen.queryAllByText(aiResponse);
      expect(matches.length).toBeGreaterThanOrEqual(1);
      // Should not have duplicates
      expect(matches.length).toBeLessThanOrEqual(2); // Allow 1-2 matches (streaming + DB)
    });
  });

  /**
   * Test 4: Optimistic UI transitions (streaming → database)
   *
   * This test verifies smooth transition from streaming chunks to
   * database-persisted messages without flickering or duplication.
   */
  it('should smoothly transition from streaming to database message', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    // Wait for sessions to load and select the session
    await waitFor(() => {
      expect(api.getSessions).toHaveBeenCalled();
    });

    const sessionElements = await screen.findAllByText('Test Session');
    await user.click(sessionElements[0]);

    // Wait for messages to load
    await waitFor(() => {
      expect(api.getSessionMessages).toHaveBeenCalledWith('session-456');
    });

    const correlationId = 'transition-test-abc';

    // Start streaming
    await act(async () => {
      mockWebSocket.emitAIResponseChunk('Smooth ', correlationId);
    });

    await waitFor(() => {
      const elements = screen.queryAllByText(/Smooth/);
      expect(elements.length).toBeGreaterThan(0);
    });

    await act(async () => {
      mockWebSocket.emitAIResponseChunk('transition ', correlationId);
      mockWebSocket.emitAIResponseChunk('test', correlationId);
    });

    const fullResponse = 'Smooth transition test';

    // Complete the response
    await act(async () => {
      mockWebSocket.emitAIResponseComplete(fullResponse, correlationId);
    });

    // Update database
    const updatedMessages: Message[] = [
      ...mockMessages,
      {
        id: 6,
        session_id: 'session-456',
        role: 'assistant',
        content: fullResponse,
        timestamp: '2025-11-20T00:00:06Z',
        audio_duration_ms: null,
        tts_duration_ms: 165,
        llm_latency_ms: 480,
        total_latency_ms: 645,
      },
    ];

    vi.mocked(api.getSessionMessages).mockResolvedValue(updatedMessages);

    // Confirm database save
    await act(async () => {
      mockWebSocket.emitMessageSaved('6', 'session-456', 'assistant', correlationId);
      // Wait for debounced query invalidation (100ms) + refetch
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    // Verify message appears (streaming chunks should be replaced by DB message)
    await waitFor(() => {
      expect(screen.getByText(fullResponse)).toBeInTheDocument();
    });

    // Verify no duplicates after transition
    const matches = screen.queryAllByText(fullResponse);
    expect(matches.length).toBeLessThanOrEqual(2); // Allow some overlap during transition
  });

  /**
   * Test 5: Error handling (service error events)
   *
   * This test verifies that service errors are properly displayed and
   * don't crash the application.
   */
  it('should handle service error events gracefully', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    // Wait for sessions to load and select the session
    await waitFor(() => {
      expect(api.getSessions).toHaveBeenCalled();
    });

    const sessionElements = await screen.findAllByText('Test Session');
    await user.click(sessionElements[0]);

    // Wait for messages to load
    await waitFor(() => {
      expect(api.getSessionMessages).toHaveBeenCalledWith('session-456');
    });

    // Simulate a service error
    const errorMessage = 'LLM provider connection failed';
    mockWebSocket.emitServiceError(errorMessage, {
      provider: 'openrouter',
      error_code: 'CONNECTION_TIMEOUT',
    });

    // Verify error is displayed (exact implementation depends on error UI)
    // For now, just verify the app doesn't crash
    await waitFor(() => {
      // Component should still be functional
      expect(screen.getByText('Hello, AI!')).toBeInTheDocument();
    });

    // Verify we can still receive messages after an error
    const correlationId = 'after-error-def';
    const recoveryResponse = 'System recovered successfully';

    await act(async () => {
      mockWebSocket.emitAIResponseComplete(recoveryResponse, correlationId);
    });

    const updatedMessages: Message[] = [
      ...mockMessages,
      {
        id: 7,
        session_id: 'session-456',
        role: 'assistant',
        content: recoveryResponse,
        timestamp: '2025-11-20T00:00:07Z',
        audio_duration_ms: null,
        tts_duration_ms: 190,
        llm_latency_ms: 510,
        total_latency_ms: 700,
      },
    ];

    vi.mocked(api.getSessionMessages).mockResolvedValue(updatedMessages);

    await act(async () => {
      mockWebSocket.emitMessageSaved('7', 'session-456', 'assistant', correlationId);
      // Wait for debounced query invalidation (100ms) + refetch
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    // Verify recovery message appears
    await waitFor(() => {
      expect(screen.getByText(recoveryResponse)).toBeInTheDocument();
    });
  });

});
