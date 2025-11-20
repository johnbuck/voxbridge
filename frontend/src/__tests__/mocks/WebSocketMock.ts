import { vi } from 'vitest';

export type WebSocketEventHandler = (event: MessageEvent) => void;
export type WebSocketErrorHandler = (event: Event) => void;

export class WebSocketMock {
  public url: string;
  public readyState: number;
  public onopen: ((event: Event) => void) | null = null;
  public onclose: ((event: CloseEvent) => void) | null = null;
  public onerror: WebSocketErrorHandler | null = null;
  public onmessage: WebSocketEventHandler | null = null;

  private eventListeners: Map<string, Set<EventListener>> = new Map();
  public sentMessages: any[] = [];

  // Mock constants
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  constructor(url: string, _protocols?: string | string[]) {
    this.url = url;
    this.readyState = WebSocketMock.CONNECTING;

    // Simulate async connection
    setTimeout(() => {
      this.readyState = WebSocketMock.OPEN;
      if (this.onopen) {
        this.onopen(new Event('open'));
      }
      this.dispatchEvent(new Event('open'));
    }, 10);
  }

  send(data: string | ArrayBufferLike | Blob | ArrayBufferView): void {
    if (this.readyState !== WebSocketMock.OPEN) {
      throw new Error('WebSocket is not open');
    }

    // Parse and store sent messages
    try {
      const message = typeof data === 'string' ? JSON.parse(data) : data;
      this.sentMessages.push(message);
    } catch (e) {
      this.sentMessages.push(data);
    }
  }

  close(code?: number, reason?: string): void {
    this.readyState = WebSocketMock.CLOSING;
    setTimeout(() => {
      this.readyState = WebSocketMock.CLOSED;
      const event = new CloseEvent('close', { code: code || 1000, reason: reason || '' });
      if (this.onclose) {
        this.onclose(event);
      }
      this.dispatchEvent(event);
    }, 10);
  }

  addEventListener(type: string, listener: EventListener): void {
    if (!this.eventListeners.has(type)) {
      this.eventListeners.set(type, new Set());
    }
    this.eventListeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: EventListener): void {
    const listeners = this.eventListeners.get(type);
    if (listeners) {
      listeners.delete(listener);
    }
  }

  dispatchEvent(event: Event): boolean {
    const listeners = this.eventListeners.get(event.type);
    if (listeners) {
      listeners.forEach(listener => listener(event));
    }
    return true;
  }

  // Test helper methods

  /**
   * Simulate receiving a WebSocket message from the server
   */
  simulateMessage(data: any): void {
    const messageData = typeof data === 'string' ? data : JSON.stringify(data);
    const event = new MessageEvent('message', { data: messageData });

    if (this.onmessage) {
      this.onmessage(event);
    }
    this.dispatchEvent(event);
  }

  /**
   * Simulate a WebSocket error
   */
  simulateError(_error?: Error): void {
    const event = new Event('error');
    if (this.onerror) {
      this.onerror(event);
    }
    this.dispatchEvent(event);
  }

  /**
   * Emit a VoxBridge partial_transcript event
   */
  emitPartialTranscript(text: string, timestamp?: number): void {
    this.simulateMessage({
      event: 'partial_transcript',
      data: {
        text,
        timestamp: timestamp || Date.now(),
      },
    });
  }

  /**
   * Emit a VoxBridge final_transcript event
   */
  emitFinalTranscript(text: string, timestamp?: number): void {
    this.simulateMessage({
      event: 'final_transcript',
      data: {
        text,
        timestamp: timestamp || Date.now(),
      },
    });
  }

  /**
   * Emit a VoxBridge ai_response_chunk event
   */
  emitAIResponseChunk(text: string, correlation_id?: string): void {
    this.simulateMessage({
      event: 'ai_response_chunk',
      data: {
        text,
        correlation_id: correlation_id || 'test-correlation-id',
        timestamp: Date.now(),
      },
    });
  }

  /**
   * Emit a VoxBridge ai_response_complete event
   */
  emitAIResponseComplete(text: string, correlation_id?: string): void {
    this.simulateMessage({
      event: 'ai_response_complete',
      data: {
        text,
        correlation_id: correlation_id || 'test-correlation-id',
        timestamp: Date.now(),
      },
    });
  }

  /**
   * Emit a VoxBridge message_saved event
   */
  emitMessageSaved(
    messageId: string,
    sessionId: string,
    role: 'user' | 'assistant',
    correlation_id?: string
  ): void {
    this.simulateMessage({
      event: 'message_saved',
      data: {
        message_id: messageId,
        session_id: sessionId,
        role,
        correlation_id: correlation_id || 'test-correlation-id',
        timestamp: new Date().toISOString(),
      },
    });
  }

  /**
   * Emit a VoxBridge service_error event
   */
  emitServiceError(message: string, details?: any): void {
    this.simulateMessage({
      event: 'service_error',
      data: {
        message,
        details,
        timestamp: Date.now(),
      },
    });
  }

  /**
   * Reset the mock (clear sent messages, reset state)
   */
  reset(): void {
    this.sentMessages = [];
    this.eventListeners.clear();
    this.onopen = null;
    this.onclose = null;
    this.onerror = null;
    this.onmessage = null;
  }
}

/**
 * Factory function to create a WebSocket mock
 */
export function createWebSocketMock(): typeof WebSocketMock {
  return WebSocketMock as any;
}

/**
 * Install the WebSocket mock globally
 */
export function installWebSocketMock(): void {
  global.WebSocket = WebSocketMock as any;
}

/**
 * Create a mock instance and install it globally
 */
export function setupWebSocketMock(): WebSocketMock {
  const mockInstance = new WebSocketMock('ws://localhost:4900/ws/events');
  global.WebSocket = vi.fn().mockImplementation(() => mockInstance) as any;
  return mockInstance;
}
