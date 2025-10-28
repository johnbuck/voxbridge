/**
 * WebRTC Audio Capture Hook
 * Handles microphone access, Opus encoding, and WebSocket streaming
 * VoxBridge 2.0 Phase 4: Web Voice Interface
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type { WebRTCAudioMessage, ConnectionState } from '@/types/webrtc';

// WebSocket URL configuration (same as useWebSocket)
const getWebSocketUrl = () => {
  if (import.meta.env.PROD) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}`;
  }
  return import.meta.env.VITE_WS_URL || 'ws://localhost:4900';
};

const WS_URL = getWebSocketUrl();

export interface UseWebRTCAudioOptions {
  sessionId: string | null;
  onMessage?: (message: WebRTCAudioMessage) => void;
  onBinaryMessage?: (data: Uint8Array) => void;  // NEW: Binary audio chunks
  onError?: (error: string) => void;
  autoStart?: boolean;
  timeslice?: number; // milliseconds between audio chunks
}

export interface UseWebRTCAudioReturn {
  isMuted: boolean;
  toggleMute: () => void;
  connectionState: ConnectionState;
  permissionError: string | null;
  isRecording: boolean;
  start: () => Promise<void>;
  stop: () => void;
}

export function useWebRTCAudio(options: UseWebRTCAudioOptions): UseWebRTCAudioReturn {
  const {
    sessionId,
    onMessage,
    onBinaryMessage,
    onError,
    autoStart = false,
    timeslice = 100, // 100ms chunks for low latency
  } = options;

  const [isMuted, setIsMuted] = useState(true);
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const audioChunksBufferRef = useRef<Blob[]>([]);

  const MAX_RECONNECT_ATTEMPTS = 5;
  const RECONNECT_INTERVAL = 3000;

  // Connect to WebSocket
  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    setConnectionState('connecting');

    try {
      const ws = new WebSocket(`${WS_URL}/ws/voice`);

      ws.onopen = () => {
        console.log('[WebRTC] WebSocket connected');
        setConnectionState('connected');
        reconnectAttemptsRef.current = 0;

        // Send session ID if available
        if (sessionId) {
          ws.send(JSON.stringify({ event: 'session_init', session_id: sessionId }));
        }
      };

      ws.onmessage = (event) => {
        try {
          // Check if message is binary (audio) or text (JSON)
          if (event.data instanceof ArrayBuffer) {
            // Binary audio chunk from TTS
            const audioData = new Uint8Array(event.data);
            console.log(`[WebRTC] Received binary audio chunk: ${audioData.length} bytes`);

            if (onBinaryMessage) {
              onBinaryMessage(audioData);
            }
          } else if (event.data instanceof Blob) {
            // Blob data (convert to ArrayBuffer)
            event.data.arrayBuffer().then((buffer) => {
              const audioData = new Uint8Array(buffer);
              console.log(`[WebRTC] Received blob audio chunk: ${audioData.length} bytes`);

              if (onBinaryMessage) {
                onBinaryMessage(audioData);
              }
            });
          } else {
            // Text message (JSON)
            const message: WebRTCAudioMessage = JSON.parse(event.data);
            console.log('[WebRTC] Received message:', message.event, message.data.text?.substring(0, 50));

            if (onMessage) {
              onMessage(message);
            }
          }
        } catch (err) {
          console.error('[WebRTC] Failed to parse WebSocket message:', err);
        }
      };

      ws.onerror = (event) => {
        console.error('[WebRTC] WebSocket error:', event);
        setConnectionState('error');
        const errorMsg = 'WebSocket connection error';
        if (onError) {
          onError(errorMsg);
        }
      };

      ws.onclose = () => {
        console.log('[WebRTC] WebSocket disconnected');
        setConnectionState('disconnected');

        // Discard buffered audio on disconnect
        audioChunksBufferRef.current = [];

        // Auto-reconnect logic
        if (
          reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS &&
          !isMuted // Only reconnect if we're still unmuted
        ) {
          reconnectAttemptsRef.current += 1;
          console.log(
            `[WebRTC] Reconnecting... (${reconnectAttemptsRef.current}/${MAX_RECONNECT_ATTEMPTS})`
          );

          reconnectTimeoutRef.current = window.setTimeout(() => {
            connectWebSocket();
          }, RECONNECT_INTERVAL);
        }
      };

      wsRef.current = ws;
    } catch (err) {
      console.error('[WebRTC] WebSocket connection failed:', err);
      setConnectionState('error');
      if (onError) {
        onError('Failed to connect to voice server');
      }
    }
  }, [sessionId, isMuted, onMessage, onError]);

  // Disconnect WebSocket
  const disconnectWebSocket = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setConnectionState('disconnected');
    audioChunksBufferRef.current = [];
  }, []);

  // Start audio capture
  const start = useCallback(async () => {
    try {
      setPermissionError(null);

      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1, // Mono
          sampleRate: 16000, // 16kHz (WhisperX compatible)
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      mediaStreamRef.current = stream;

      // Try Opus codec first, fallback to WebM/Opus
      const mimeTypes = [
        'audio/webm;codecs=opus',
        'audio/ogg;codecs=opus',
        'audio/webm',
      ];

      let selectedMimeType = '';
      for (const mimeType of mimeTypes) {
        if (MediaRecorder.isTypeSupported(mimeType)) {
          selectedMimeType = mimeType;
          console.log('[WebRTC] Using MIME type:', mimeType);
          break;
        }
      }

      if (!selectedMimeType) {
        throw new Error('No supported audio codec found (Opus required)');
      }

      // Create MediaRecorder
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: selectedMimeType,
      });

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          // Send audio chunk via WebSocket if connected
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            // Send as binary data (ArrayBuffer)
            event.data.arrayBuffer().then((buffer) => {
              wsRef.current?.send(buffer);
            });
          } else {
            // Buffer chunks while disconnected (will be discarded on reconnect)
            audioChunksBufferRef.current.push(event.data);
            console.warn('[WebRTC] Audio chunk buffered (not connected)');
          }
        }
      };

      mediaRecorder.onstart = () => {
        console.log('[WebRTC] Recording started');
        setIsRecording(true);
      };

      mediaRecorder.onstop = () => {
        console.log('[WebRTC] Recording stopped');
        setIsRecording(false);
        audioChunksBufferRef.current = [];
      };

      mediaRecorder.onerror = (event) => {
        console.error('[WebRTC] MediaRecorder error:', event);
        const errorMsg = 'Audio recording error';
        setPermissionError(errorMsg);
        if (onError) {
          onError(errorMsg);
        }
      };

      mediaRecorderRef.current = mediaRecorder;

      // Start recording with timeslice
      mediaRecorder.start(timeslice);

      // Connect WebSocket
      connectWebSocket();

      // Unmute
      setIsMuted(false);
    } catch (err) {
      console.error('[WebRTC] Failed to start audio capture:', err);

      let errorMsg = 'Failed to access microphone';
      if (err instanceof Error) {
        if (err.name === 'NotAllowedError') {
          errorMsg = 'Microphone access denied. Please allow microphone permissions in your browser settings and reload the page.';
        } else if (err.name === 'NotFoundError') {
          errorMsg = 'No microphone found. Please check your device settings and ensure a microphone is connected.';
        } else {
          errorMsg = err.message;
        }
      }

      setPermissionError(errorMsg);
      if (onError) {
        onError(errorMsg);
      }

      // Clean up
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
      }
    }
  }, [connectWebSocket, timeslice, onError]);

  // Stop audio capture
  const stop = useCallback(() => {
    console.log('[WebRTC] Stopping audio capture');

    // Stop MediaRecorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    mediaRecorderRef.current = null;

    // Stop media stream tracks
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }

    // Disconnect WebSocket
    disconnectWebSocket();

    setIsMuted(true);
    setIsRecording(false);
    audioChunksBufferRef.current = [];
  }, [disconnectWebSocket]);

  // Toggle mute (stop/start recording but keep WebSocket connection)
  const toggleMute = useCallback(() => {
    if (isMuted) {
      start();
    } else {
      stop();
    }
  }, [isMuted, start, stop]);

  // Auto-start if enabled
  useEffect(() => {
    if (autoStart && sessionId) {
      start();
    }

    // Cleanup on unmount
    return () => {
      stop();
    };
  }, [autoStart, sessionId]); // Only run when autoStart or sessionId changes

  // Update WebSocket session when sessionId changes
  useEffect(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN && sessionId) {
      wsRef.current.send(JSON.stringify({ event: 'session_init', session_id: sessionId }));
    }
  }, [sessionId]);

  return {
    isMuted,
    toggleMute,
    connectionState,
    permissionError,
    isRecording,
    start,
    stop,
  };
}
