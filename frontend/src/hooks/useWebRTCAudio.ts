/**
 * WebRTC Audio Capture Hook
 * Handles microphone access, Opus encoding, and WebSocket streaming
 * VoxBridge 2.0 Phase 4: Web Voice Interface
 * Phase 2: Error Handling Integration
 * Phase 4.6: MediaRecorder API with WebM/Opus (simpler, native, maintainable)
 * ENHANCED LOGGING: Timestamps and detailed diagnostics
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type { WebRTCAudioMessage, ConnectionState } from '@/types/webrtc';
import type { ServiceErrorEvent } from '@/types/errors';

// Debug logging flag - set to true to enable verbose logging
const DEBUG_WEBRTC_HOOK = false;

// Logging utility with timestamps and debug flag support
const log = (...args: any[]) => {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] [WebRTC]`, ...args);
};

const logDebug = (...args: any[]) => {
  if (!DEBUG_WEBRTC_HOOK) return;
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] [WebRTC]`, ...args);
};

const logWarn = (...args: any[]) => {
  const timestamp = new Date().toISOString();
  console.warn(`[${timestamp}] [WebRTC]`, ...args);
};

const logError = (...args: any[]) => {
  const timestamp = new Date().toISOString();
  console.error(`[${timestamp}] [WebRTC]`, ...args);
};

// WebSocket URL configuration
// IMPORTANT: Always connect directly to backend port 4900, not nginx port 4903
// Nginx cannot reliably proxy WebSocket connections, so we bypass it for WebRTC audio
const getWebSocketUrl = () => {
  logDebug('🔧 Environment check:');
  logDebug('  - VITE_WS_URL:', import.meta.env.VITE_WS_URL || 'undefined');
  logDebug('  - VITE_API_URL:', import.meta.env.VITE_API_URL || 'undefined');
  logDebug('  - import.meta.env.PROD:', import.meta.env.PROD);
  logDebug('  - window.location.hostname:', window.location.hostname);
  logDebug('  - window.location.protocol:', window.location.protocol);

  // Always use VITE_WS_URL if defined (for both dev and prod)
  if (import.meta.env.VITE_WS_URL) {
    logDebug('✅ Using VITE_WS_URL from env:', import.meta.env.VITE_WS_URL);
    return import.meta.env.VITE_WS_URL;
  }

  // For local development (Docker setup), always use backend port 4900
  // Nginx on 4903 does not proxy WebSocket connections properly
  if (import.meta.env.PROD) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Extract hostname but force port 4900 (backend)
    const hostname = window.location.hostname;
    const url = `${protocol}//${hostname}:4900`;
    logDebug('🏭 Production mode - constructed URL:', url);
    return url;
  }

  // Development fallback
  logDebug('💻 Development mode - using fallback URL: ws://localhost:4900');
  return 'ws://localhost:4900';
};

const WS_URL = getWebSocketUrl();
logDebug('🌐 Final WebSocket URL configured:', WS_URL);

// Default user ID for web clients
const WEB_USER_ID = 'web_user_default';

export interface UseWebRTCAudioOptions {
  sessionId: string | null;
  onMessage?: (message: WebRTCAudioMessage) => void;
  onBinaryMessage?: (data: Uint8Array) => void;  // NEW: Binary audio chunks
  onError?: (error: string) => void;
  onServiceError?: (error: ServiceErrorEvent) => void; // NEW: Service error events
  onRecordingStop?: () => void; // NEW: Callback when recording stops (for cleanup)
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
    onServiceError,
    onRecordingStop,
    autoStart = false,
    timeslice = 100, // 100ms chunks for low latency
  } = options;

  logDebug('🎤 Hook initialized with options:', {
    sessionId: sessionId || 'null',
    autoStart,
    timeslice,
    hasOnMessage: !!onMessage,
    hasOnBinaryMessage: !!onBinaryMessage,
    hasOnError: !!onError,
    hasOnServiceError: !!onServiceError,
  });

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
    logDebug('🔌 connectWebSocket() called');

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      logDebug('⚠️  Already connected, skipping');
      return; // Already connected
    }

    // Validate sessionId is present
    if (!sessionId) {
      const errorMsg = 'Cannot connect: No session ID available';
      logError('❌', errorMsg);
      setConnectionState('error');
      if (onError) {
        onError(errorMsg);
      }
      return;
    }

    log('📡 Attempting WebSocket connection with session:', sessionId);
    setConnectionState('connecting');

    try {
      // Build WebSocket URL with required query parameters
      const wsUrl = `${WS_URL}/ws/voice?session_id=${encodeURIComponent(sessionId)}&user_id=${encodeURIComponent(WEB_USER_ID)}`;
      logDebug('🔗 Full WebSocket URL:', wsUrl);

      const ws = new WebSocket(wsUrl);
      logDebug('🌐 WebSocket object created, readyState:', ws.readyState);

      ws.onopen = () => {
        log('✅ WebSocket CONNECTED successfully');
        setConnectionState('connected');
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          // Check if message is binary (audio) or text (JSON)
          if (event.data instanceof ArrayBuffer) {
            // Binary audio chunk from TTS
            const audioData = new Uint8Array(event.data);
            logDebug(`🔊 Received binary audio chunk: ${audioData.length} bytes`);

            if (onBinaryMessage) {
              onBinaryMessage(audioData);
            }
          } else if (event.data instanceof Blob) {
            // Blob data (convert to ArrayBuffer)
            event.data.arrayBuffer().then((buffer) => {
              const audioData = new Uint8Array(buffer);
              logDebug(`🔊 Received blob audio chunk: ${audioData.length} bytes`);

              if (onBinaryMessage) {
                onBinaryMessage(audioData);
              }
            });
          } else {
            // Text message (JSON)
            const message: WebRTCAudioMessage = JSON.parse(event.data);
            logDebug('📨 Received message:', message.event, 'text:', message.data.text?.substring(0, 50));

            // Handle error messages from backend
            if (message.event === 'error') {
              const errorText = message.data.message || message.data.text || 'Unknown error';
              logError('❌ Backend error:', errorText);
              setConnectionState('error');
              if (onError) {
                onError(errorText);
              }
              return;
            }

            // Handle service error events (Phase 2)
            if (message.event === 'service_error' && onServiceError) {
              logWarn('⚠️  Service error event:', message.data);
              onServiceError(message.data as any as ServiceErrorEvent);
              return;
            }

            // Handle stop_listening event (silence detection)
            // MULTI-TURN MODE: Keep MediaRecorder running continuously (like Discord's AudioReceiver)
            if (message.event === 'stop_listening') {
              const reason = message.data.reason || 'unknown';
              const metadata = message.data.silence_duration_ms
                ? `(silence: ${message.data.silence_duration_ms}ms)`
                : message.data.elapsed_ms
                ? `(elapsed: ${message.data.elapsed_ms}ms)`
                : '';

              logDebug(`🤫 Silence detected: ${reason} ${metadata} - finalizing utterance but KEEPING mic active for next turn`);

              // ✅ DO NOT STOP MediaRecorder - keep it running for multi-turn conversations!
              // ✅ DO NOT STOP media stream - keep it active like Discord's continuous audio
              // ✅ DO NOT set isMuted=true - mic stays active automatically

              // Backend auto-restart detection (lines 643-658 in webrtc_handler.py) will
              // automatically detect new audio and start a new conversation turn.

              logDebug('✅ Utterance finalized, microphone STAYS ACTIVE - ready for next question');
              return;
            }

            // Handle TTS complete - MULTI-TURN MODE: Keep connection open!
            // After TTS completes, we wait for user to speak again (auto-restart detection on backend)
            // Only disconnect when user explicitly stops or closes page
            if (message.event === 'tts_complete') {
              logDebug(`✅ TTS complete - ready for next conversation turn (keeping WebSocket open)`);
              // Notify parent so it can trigger audio playback
              if (onMessage) {
                onMessage(message);
              }
              // ✅ DON'T disconnect - keep connection alive for next turn!
              return;
            }

            if (onMessage) {
              onMessage(message);
            }
          }
        } catch (err) {
          logError('❌ Failed to parse WebSocket message:', err);
        }
      };

      ws.onerror = (event) => {
        logError('❌ WebSocket ERROR event:', event);
        logError('   - readyState:', ws.readyState);
        logError('   - URL:', wsUrl);
        setConnectionState('error');
        const errorMsg = 'WebSocket connection error';
        if (onError) {
          onError(errorMsg);
        }
      };

      ws.onclose = (event) => {
        log('🔌 WebSocket CLOSED');
        logDebug('   - code:', event.code);
        logDebug('   - reason:', event.reason || 'none');
        logDebug('   - wasClean:', event.wasClean);
        setConnectionState('disconnected');

        // Discard buffered audio on disconnect
        audioChunksBufferRef.current = [];

        // Auto-reconnect logic
        if (
          reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS &&
          !isMuted // Only reconnect if we're still unmuted
        ) {
          reconnectAttemptsRef.current += 1;
          log(
            `🔄 Reconnecting... (${reconnectAttemptsRef.current}/${MAX_RECONNECT_ATTEMPTS})`
          );

          reconnectTimeoutRef.current = window.setTimeout(() => {
            connectWebSocket();
          }, RECONNECT_INTERVAL);
        }
      };

      wsRef.current = ws;
      logDebug('✅ WebSocket object stored in ref');
    } catch (err) {
      logError('❌ WebSocket connection FAILED:', err);
      setConnectionState('error');
      if (onError) {
        onError('Failed to connect to voice server');
      }
    }
  }, [sessionId, isMuted, onMessage, onBinaryMessage, onServiceError, onError]);

  // Disconnect WebSocket
  const disconnectWebSocket = useCallback(() => {
    logDebug('🔌 disconnectWebSocket() called');

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
      logDebug('   - Cleared reconnect timeout');
    }

    if (wsRef.current) {
      logDebug('   - Closing WebSocket (current state:', wsRef.current.readyState, ')');
      wsRef.current.close();
      wsRef.current = null;
    }

    setConnectionState('disconnected');
    audioChunksBufferRef.current = [];
  }, []);

  // Start audio capture
  const start = useCallback(async () => {
    log('🎙️ start() called - initiating audio capture');
    logDebug('   - Current sessionId:', sessionId);
    logDebug('   - Current isMuted:', isMuted);
    logDebug('   - Current connectionState:', connectionState);

    try {
      setPermissionError(null);

      logDebug('🎤 Requesting microphone access...');
      // Request microphone access (48kHz stereo to match Discord)
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 2, // Stereo (matching Discord)
          sampleRate: 48000, // 48kHz (matching Discord)
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      log('✅ Microphone access GRANTED');
      logDebug('   - Audio tracks:', stream.getAudioTracks().length);

      mediaStreamRef.current = stream;

      logDebug('🎬 Creating MediaRecorder (OGG/Opus preferred, 100ms chunks)');

      // Try OGG/Opus first (better streaming), fallback to WebM
      const mimeTypes = [
        'audio/ogg;codecs=opus',     // OGG/Opus - best for streaming
        'audio/webm;codecs=opus',    // WebM fallback
      ];

      let selectedMimeType = '';
      for (const mimeType of mimeTypes) {
        if (MediaRecorder.isTypeSupported(mimeType)) {
          selectedMimeType = mimeType;
          logDebug('✅ Using MIME type:', mimeType);
          break;
        }
      }

      if (!selectedMimeType) {
        throw new Error('No supported audio codec found (OGG/Opus or WebM/Opus required)');
      }

      // Create MediaRecorder
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: selectedMimeType,
        audioBitsPerSecond: 64000, // 64kbps for voice
      });

      // Handle audio data chunks
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          // Send WebM chunk via WebSocket if connected
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            // Send as Blob (will be sent as binary data)
            event.data.arrayBuffer().then((buffer) => {
              wsRef.current?.send(buffer);
              logDebug(`📤 Sent WebM chunk: ${buffer.byteLength} bytes`);
            });
          } else {
            // Buffer chunks while disconnected (will be discarded on reconnect)
            audioChunksBufferRef.current.push(event.data);
            logDebug('⚠️  Audio chunk buffered (WebSocket not connected, state:', wsRef.current?.readyState, ')');
          }
        }
      };

      mediaRecorder.onstart = () => {
        log('✅ MediaRecorder STARTED');
        setIsRecording(true);
      };

      mediaRecorder.onstop = () => {
        log('🛑 MediaRecorder STOPPED');
        setIsRecording(false);
        audioChunksBufferRef.current = [];
      };

      mediaRecorder.onerror = (event) => {
        logError('❌ MediaRecorder ERROR:', event);
        const errorMsg = 'Audio recording error';
        setPermissionError(errorMsg);
        if (onError) {
          onError(errorMsg);
        }
      };

      mediaRecorderRef.current = mediaRecorder;

      // Start recording with 100ms timeslice (good balance of latency vs overhead)
      logDebug('🎬 Starting MediaRecorder with timeslice:', timeslice, 'ms');
      mediaRecorder.start(timeslice || 100);

      // Connect WebSocket
      logDebug('🔌 Calling connectWebSocket()...');
      connectWebSocket();

      // Unmute
      logDebug('🔓 Setting isMuted to false');
      setIsMuted(false);

      logDebug('✅ start() completed successfully');
    } catch (err) {
      logError('❌ Failed to start audio capture:', err);

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

      logError('   - Error message:', errorMsg);
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
  }, [connectWebSocket, timeslice, onError, sessionId, isMuted, connectionState]);

  // Stop audio capture
  const stop = useCallback(() => {
    log('🛑 stop() called - stopping audio capture');

    // Stop MediaRecorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      logDebug('   - Stopping MediaRecorder (current state:', mediaRecorderRef.current.state, ')');
      mediaRecorderRef.current.stop();
    }
    mediaRecorderRef.current = null;

    // Stop media stream tracks
    if (mediaStreamRef.current) {
      logDebug('   - Stopping', mediaStreamRef.current.getTracks().length, 'media tracks');
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }

    // Disconnect WebSocket
    disconnectWebSocket();

    setIsMuted(true);
    setIsRecording(false);
    audioChunksBufferRef.current = [];

    // Notify parent component to clear UI state (Fix #2: Listening indicator cleanup)
    if (onRecordingStop) {
      logDebug('   - Calling onRecordingStop callback');
      onRecordingStop();
    }

    logDebug('✅ stop() completed');
  }, [disconnectWebSocket, onRecordingStop]);

  // Toggle mute (stop/start recording but keep WebSocket connection)
  const toggleMute = useCallback(() => {
    logDebug('🔄 toggleMute() called (current isMuted:', isMuted, ')');

    if (isMuted) {
      logDebug('   - Currently muted, calling start()...');
      start();
    } else {
      logDebug('   - Currently unmuted, calling stop()...');
      stop();
    }
  }, [isMuted, start, stop]);

  // Auto-start if enabled
  useEffect(() => {
    logDebug('🔄 useEffect[autoStart, sessionId] triggered');
    logDebug('   - autoStart:', autoStart);
    logDebug('   - sessionId:', sessionId);

    if (autoStart && sessionId) {
      logDebug('   - Calling start() due to autoStart');
      start();
    }

    // Cleanup on unmount
    return () => {
      logDebug('🧹 useEffect cleanup - calling stop()');
      stop();
    };
  }, [autoStart, sessionId]); // Only run when autoStart or sessionId changes

  // Update WebSocket session when sessionId changes
  useEffect(() => {
    logDebug('🔄 useEffect[sessionId] triggered - session ID changed to:', sessionId);

    if (wsRef.current?.readyState === WebSocket.OPEN && sessionId) {
      logDebug('   - Sending session_init message to WebSocket');
      wsRef.current.send(JSON.stringify({ event: 'session_init', session_id: sessionId }));
    }
  }, [sessionId]);

  logDebug('🔄 Hook rendering with state:', {
    isMuted,
    connectionState,
    isRecording,
    hasPermissionError: !!permissionError,
  });

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
