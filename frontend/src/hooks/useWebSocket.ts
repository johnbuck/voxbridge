/**
 * WebSocket Hook for Real-Time Updates
 * Connects to VoxBridge backend for live transcription and status updates
 */

import { useEffect, useRef, useState, useCallback } from 'react';

// In production, use relative WebSocket URL (wss:// or ws:// based on current protocol)
// In development, use VITE_WS_URL or fallback to localhost
const getWebSocketUrl = () => {
  if (import.meta.env.PROD) {
    // Use current protocol (wss:// for https://, ws:// for http://)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}`;
  }
  return import.meta.env.VITE_WS_URL || 'ws://localhost:4900';
};

const WS_URL = getWebSocketUrl();

export interface WebSocketMessage {
  event: string;
  data: any;
  timestamp: string;
}

export interface WebSocketOptions {
  reconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onMessage?: (message: WebSocketMessage) => void;
}

export function useWebSocket(
  endpoint: string,
  options: WebSocketOptions = {}
) {
  const {
    reconnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | null>(null);

  // FIX: Store callback in ref to prevent stale closures
  // When activeSessionId changes in parent, this ref gets the latest callback
  // without requiring WebSocket reconnection
  const onMessageRef = useRef(options.onMessage);

  // Update ref when callback changes (prevents stale closure bug)
  useEffect(() => {
    onMessageRef.current = options.onMessage;
  }, [options.onMessage]);

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(`${WS_URL}${endpoint}`);

      ws.onopen = () => {
        console.log(`[WebSocket] Connected to ${endpoint}`);
        setIsConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          setLastMessage(message);
          // FIX: Use ref to get latest callback (prevents stale closure)
          // This ensures we always call the current callback with current activeSessionId
          if (onMessageRef.current) {
            onMessageRef.current(message);
          }
        } catch (err) {
          console.error('[WebSocket] Failed to parse message:', err);
        }
      };

      ws.onerror = (event) => {
        console.error('[WebSocket] Error:', event);
        setError(new Error('WebSocket connection error'));
      };

      ws.onclose = () => {
        console.log('[WebSocket] Disconnected');
        setIsConnected(false);

        // Attempt reconnection
        if (
          reconnect &&
          reconnectAttemptsRef.current < maxReconnectAttempts
        ) {
          reconnectAttemptsRef.current += 1;
          console.log(
            `[WebSocket] Reconnecting... (${reconnectAttemptsRef.current}/${maxReconnectAttempts})`
          );

          reconnectTimeoutRef.current = window.setTimeout(() => {
            connect();
          }, reconnectInterval);
        }
      };

      wsRef.current = ws;
    } catch (err) {
      console.error('[WebSocket] Connection failed:', err);
      setError(err as Error);
    }
  }, [endpoint, reconnect, reconnectInterval, maxReconnectAttempts]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      window.clearTimeout(reconnectTimeoutRef.current);
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setIsConnected(false);
  }, []);

  const sendMessage = useCallback((data: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    } else {
      console.warn('[WebSocket] Cannot send message - not connected');
    }
  }, []);

  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    isConnected,
    lastMessage,
    error,
    sendMessage,
    reconnect: connect,
    disconnect,
  };
}
