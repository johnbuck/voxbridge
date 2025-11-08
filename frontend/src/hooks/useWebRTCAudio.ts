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
import { createLogger } from '@/utils/logger';

// Initialize logger for WebRTC module
const logger = createLogger('useWebRTCAudio');

// WebSocket URL configuration
// IMPORTANT: Always connect directly to backend port 4900, not nginx port 4903
// Nginx cannot reliably proxy WebSocket connections, so we bypass it for WebRTC audio
const getWebSocketUrl = () => {
  logger.debug('🔧 Environment check:');
  logger.debug('  - VITE_WS_URL:', import.meta.env.VITE_WS_URL || 'undefined');
  logger.debug('  - VITE_API_URL:', import.meta.env.VITE_API_URL || 'undefined');
  logger.debug('  - import.meta.env.PROD:', import.meta.env.PROD);
  logger.debug('  - window.location.hostname:', window.location.hostname);
  logger.debug('  - window.location.protocol:', window.location.protocol);

  // Always use VITE_WS_URL if defined (for both dev and prod)
  if (import.meta.env.VITE_WS_URL) {
    logger.debug('✅ Using VITE_WS_URL from env:', import.meta.env.VITE_WS_URL);
    return import.meta.env.VITE_WS_URL;
  }

  // For local development (Docker setup), always use backend port 4900
  // Nginx on 4903 does not proxy WebSocket connections properly
  if (import.meta.env.PROD) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Extract hostname but force port 4900 (backend)
    const hostname = window.location.hostname;
    const url = `${protocol}//${hostname}:4900`;
    logger.debug('🏭 Production mode - constructed URL:', url);
    return url;
  }

  // Development fallback
  logger.debug('💻 Development mode - using fallback URL: ws://localhost:4900');
  return 'ws://localhost:4900';
};

const WS_URL = getWebSocketUrl();
logger.debug('🌐 Final WebSocket URL configured:', WS_URL);

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

  // ✅ DISABLED: Too verbose - only enable when debugging hook initialization
  // logger.debug('🎤 Hook initialized with options:', {
  //   sessionId: sessionId || 'null',
  //   autoStart,
  //   timeslice,
  //   hasOnMessage: !!onMessage,
  //   hasOnBinaryMessage: !!onBinaryMessage,
  //   hasOnError: !!onError,
  //   hasOnServiceError: !!onServiceError,
  // });

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
  const lastChunkTimeRef = useRef<number | null>(null); // Track last ondataavailable timestamp
  const emptyChunkCountRef = useRef(0); // Batch 3.1: Track consecutive empty chunks

  const MAX_RECONNECT_ATTEMPTS = 5;
  const RECONNECT_INTERVAL = 3000;

  // Connect to WebSocket
  const connectWebSocket = useCallback(() => {
    logger.debug('🔌 connectWebSocket() called');

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      logger.debug('⚠️  Already connected, skipping');
      return; // Already connected
    }

    // Validate sessionId is present
    if (!sessionId) {
      const errorMsg = 'Cannot connect: No session ID available';
      logger.error('❌', errorMsg);
      setConnectionState('error');
      if (onError) {
        onError(errorMsg);
      }
      return;
    }

    logger.info('📡 Attempting WebSocket connection with session:', sessionId);
    setConnectionState('connecting');

    try {
      // Build WebSocket URL with required query parameters
      const wsUrl = `${WS_URL}/ws/voice?session_id=${encodeURIComponent(sessionId)}&user_id=${encodeURIComponent(WEB_USER_ID)}`;
      logger.debug('🔗 Full WebSocket URL:', wsUrl);

      const ws = new WebSocket(wsUrl);
      logger.debug('🌐 WebSocket object created, readyState:', ws.readyState);

      ws.onopen = () => {
        logger.info('✅ WebSocket CONNECTED successfully');
        setConnectionState('connected');
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          // Check if message is binary (audio) or text (JSON)
          if (event.data instanceof ArrayBuffer) {
            // Binary audio chunk from TTS
            const audioData = new Uint8Array(event.data);
            logger.debug(`🔊 Received binary audio chunk: ${audioData.length} bytes`);

            if (onBinaryMessage) {
              onBinaryMessage(audioData);
            }
          } else if (event.data instanceof Blob) {
            // Blob data (convert to ArrayBuffer)
            event.data.arrayBuffer().then((buffer) => {
              const audioData = new Uint8Array(buffer);
              logger.debug(`🔊 Received blob audio chunk: ${audioData.length} bytes`);

              if (onBinaryMessage) {
                onBinaryMessage(audioData);
              }
            });
          } else {
            // Text message (JSON)
            const message: WebRTCAudioMessage = JSON.parse(event.data);
            logger.debug('📨 Received message:', message.event, 'text:', message.data.text?.substring(0, 50));

            // Handle error messages from backend
            if (message.event === 'error') {
              const errorText = message.data.message || message.data.text || 'Unknown error';
              logger.error('❌ Backend error:', errorText);
              setConnectionState('error');
              if (onError) {
                onError(errorText);
              }
              return;
            }

            // Handle service error events (Phase 2)
            if (message.event === 'service_error' && onServiceError) {
              logger.warn('⚠️  Service error event:', message.data);
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

              logger.debug(`🤫 Silence detected: ${reason} ${metadata} - finalizing utterance but KEEPING mic active for next turn`);

              // ✅ DO NOT STOP MediaRecorder - keep it running for multi-turn conversations!
              // ✅ DO NOT STOP media stream - keep it active like Discord's continuous audio
              // ✅ DO NOT set isMuted=true - mic stays active automatically

              // Backend auto-restart detection (lines 643-658 in webrtc_handler.py) will
              // automatically detect new audio and start a new conversation turn.

              logger.debug('✅ Utterance finalized, microphone STAYS ACTIVE - ready for next question');
              return;
            }

            // Handle TTS complete - MULTI-TURN MODE: Keep connection open!
            // After TTS completes, we wait for user to speak again (auto-restart detection on backend)
            // Only disconnect when user explicitly stops or closes page
            if (message.event === 'tts_complete') {
              logger.debug(`✅ TTS complete - ready for next conversation turn (keeping WebSocket open)`);
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
          logger.error('❌ Failed to parse WebSocket message:', err);
        }
      };

      ws.onerror = (event) => {
        logger.error('❌ WebSocket ERROR event:', event);
        logger.error('   - readyState:', ws.readyState);
        logger.error('   - URL:', wsUrl);
        setConnectionState('error');
        const errorMsg = 'WebSocket connection error';
        if (onError) {
          onError(errorMsg);
        }
      };

      ws.onclose = (event) => {
        logger.info('🔌 WebSocket CLOSED');
        logger.debug('   - code:', event.code);
        logger.debug('   - reason:', event.reason || 'none');
        logger.debug('   - wasClean:', event.wasClean);
        setConnectionState('disconnected');

        // Discard buffered audio on disconnect
        audioChunksBufferRef.current = [];

        // Auto-reconnect logic
        if (
          reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS &&
          !isMuted // Only reconnect if we're still unmuted
        ) {
          reconnectAttemptsRef.current += 1;
          logger.info(
            `🔄 Reconnecting... (${reconnectAttemptsRef.current}/${MAX_RECONNECT_ATTEMPTS})`
          );

          reconnectTimeoutRef.current = window.setTimeout(() => {
            connectWebSocket();
          }, RECONNECT_INTERVAL);
        }
      };

      wsRef.current = ws;
      logger.debug('✅ WebSocket object stored in ref');
    } catch (err) {
      logger.error('❌ WebSocket connection FAILED:', err);
      setConnectionState('error');
      if (onError) {
        onError('Failed to connect to voice server');
      }
    }
  }, [sessionId, isMuted, onMessage, onBinaryMessage, onServiceError, onError]);

  // Disconnect WebSocket
  const disconnectWebSocket = useCallback(() => {
    logger.debug('🔌 disconnectWebSocket() called');

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
      logger.debug('   - Cleared reconnect timeout');
    }

    if (wsRef.current) {
      logger.debug('   - Closing WebSocket (current state:', wsRef.current.readyState, ')');
      wsRef.current.close();
      wsRef.current = null;
    }

    setConnectionState('disconnected');
    audioChunksBufferRef.current = [];
  }, []);

  // Start audio capture
  const start = useCallback(async () => {
    logger.info('🎙️ start() called - initiating audio capture');
    logger.debug('   - Current sessionId:', sessionId);
    logger.debug('   - Current isMuted:', isMuted);
    logger.debug('   - Current connectionState:', connectionState);

    try {
      setPermissionError(null);

      logger.debug('🎤 Requesting microphone access...');
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

      logger.info('✅ Microphone access GRANTED');
      logger.debug('   - Audio tracks:', stream.getAudioTracks().length);

      mediaStreamRef.current = stream;

      logger.debug('🎬 Creating MediaRecorder (OGG/Opus preferred, 100ms chunks)');

      // Try OGG/Opus first (better streaming), fallback to WebM
      const mimeTypes = [
        'audio/ogg;codecs=opus',     // OGG/Opus - best for streaming
        'audio/webm;codecs=opus',    // WebM fallback
      ];

      let selectedMimeType = '';
      for (const mimeType of mimeTypes) {
        if (MediaRecorder.isTypeSupported(mimeType)) {
          selectedMimeType = mimeType;
          logger.debug('✅ Using MIME type:', mimeType);
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
        const timestamp = new Date().toISOString();
        lastChunkTimeRef.current = Date.now(); // Track last chunk time for watchdog

        if (event.data.size > 0) {
          // Batch 3.1: Reset empty chunk counter on non-empty chunk
          emptyChunkCountRef.current = 0;

          // ✅ CHECKPOINT 1: Frontend Audio Chunk Available
          logger.info(`[${timestamp}] [MediaRecorder] 📤 Audio chunk available: ${event.data.size} bytes, connected=${wsRef.current?.readyState === WebSocket.OPEN}`);

          // Send WebM chunk via WebSocket if connected
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            // Send as Blob (will be sent as binary data)
            event.data.arrayBuffer().then((buffer) => {
              wsRef.current?.send(buffer);
              // ✅ CHECKPOINT 1: Confirm Send
              logger.info(`[${timestamp}] [MediaRecorder] ✅ Sent ${buffer.byteLength} bytes to WebSocket`);
            });
          } else {
            // Buffer chunks while disconnected (will be discarded on reconnect)
            audioChunksBufferRef.current.push(event.data);
            logger.warn(`[${timestamp}] [MediaRecorder] ⚠️  Audio chunk BUFFERED (WebSocket not connected, state: ${wsRef.current?.readyState}), buffer size: ${audioChunksBufferRef.current.length}`);
          }
        } else {
          // Batch 3.1: Track consecutive empty chunks
          emptyChunkCountRef.current++;
          logger.warn(`[${timestamp}] [MediaRecorder] ⚠️  Empty audio chunk received (size=0), consecutive count: ${emptyChunkCountRef.current}`);

          // Batch 3.1: Error after >10 consecutive empty chunks
          if (emptyChunkCountRef.current > 10) {
            logger.error(`🚨 [MediaRecorder] CRITICAL: ${emptyChunkCountRef.current} consecutive empty chunks - MediaRecorder may be broken!`);
            logger.error(`   - MediaRecorder state: ${mediaRecorderRef.current?.state}`);
            logger.error(`   - Stream active: ${mediaStreamRef.current?.active}`);
            logger.error(`   - Audio tracks: ${mediaStreamRef.current?.getAudioTracks().length}`);
          }
        }
      };

      mediaRecorder.onstart = () => {
        logger.info('✅ MediaRecorder STARTED');
        setIsRecording(true);
      };

      mediaRecorder.onstop = () => {
        logger.info('🛑 MediaRecorder STOPPED');
        setIsRecording(false);
        audioChunksBufferRef.current = [];
      };

      mediaRecorder.onerror = (event) => {
        logger.error('❌ MediaRecorder ERROR:', event);
        const errorMsg = 'Audio recording error';
        setPermissionError(errorMsg);
        if (onError) {
          onError(errorMsg);
        }
      };

      mediaRecorderRef.current = mediaRecorder;

      // Start recording with 100ms timeslice (good balance of latency vs overhead)
      logger.debug('🎬 Starting MediaRecorder with timeslice:', timeslice, 'ms');
      mediaRecorder.start(timeslice || 100);

      // Connect WebSocket
      logger.debug('🔌 Calling connectWebSocket()...');
      connectWebSocket();

      // Unmute
      logger.debug('🔓 Setting isMuted to false');
      setIsMuted(false);

      logger.debug('✅ start() completed successfully');
    } catch (err) {
      logger.error('❌ Failed to start audio capture:', err);

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

      logger.error('   - Error message:', errorMsg);
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
    logger.info('🛑 stop() called - stopping audio capture');

    // Stop MediaRecorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      // Batch 3.1: Log MediaRecorder state before stop()
      const state = mediaRecorderRef.current.state;
      const hasStream = !!mediaStreamRef.current;
      const streamActive = mediaStreamRef.current?.active || false;
      logger.info(`🛑 [MediaRecorder] Stopping (state: ${state}, hasStream: ${hasStream}, streamActive: ${streamActive})`);
      mediaRecorderRef.current.stop();
    }
    mediaRecorderRef.current = null;

    // Stop media stream tracks
    if (mediaStreamRef.current) {
      logger.debug('   - Stopping', mediaStreamRef.current.getTracks().length, 'media tracks');
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
      logger.debug('   - Calling onRecordingStop callback');
      onRecordingStop();
    }

    logger.debug('✅ stop() completed');
  }, [disconnectWebSocket, onRecordingStop]);

  // Toggle mute (stop/start recording but keep WebSocket connection)
  const toggleMute = useCallback(() => {
    logger.debug('🔄 toggleMute() called (current isMuted:', isMuted, ')');

    // ✅ DEBUG: Print stack trace to see who called toggleMute
    console.trace('🔍 toggleMute() stack trace:');

    if (isMuted) {
      logger.debug('   - Currently muted, calling start()...');
      start();
    } else {
      logger.debug('   - Currently unmuted, calling stop()...');
      stop();
    }
  }, [isMuted, start, stop]);

  // Auto-start if enabled
  useEffect(() => {
    logger.debug('🔄 useEffect[autoStart, sessionId] triggered');
    logger.debug('   - autoStart:', autoStart);
    logger.debug('   - sessionId:', sessionId);

    if (autoStart && sessionId) {
      logger.debug('   - Calling start() due to autoStart');
      start();
    }

    // Cleanup on unmount
    return () => {
      logger.debug('🧹 useEffect cleanup - calling stop()');
      stop();
    };
  }, [autoStart, sessionId]); // Only run when autoStart or sessionId changes

  // Update WebSocket session when sessionId changes
  useEffect(() => {
    logger.debug('🔄 useEffect[sessionId] triggered - session ID changed to:', sessionId);

    if (wsRef.current?.readyState === WebSocket.OPEN && sessionId) {
      logger.debug('   - Sending session_init message to WebSocket');
      wsRef.current.send(JSON.stringify({ event: 'session_init', session_id: sessionId }));
    }
  }, [sessionId]);

  // Watchdog: Detect if MediaRecorder stops sending chunks (silent failure)
  useEffect(() => {
    if (!isRecording) return;

    const watchdog = setInterval(() => {
      if (lastChunkTimeRef.current) {
        const timeSinceLastChunk = Date.now() - lastChunkTimeRef.current;
        if (timeSinceLastChunk > 5000) { // 5 seconds without chunks = problem
          logger.error(`🚨 [WATCHDOG] MediaRecorder ondataavailable stopped firing! Last chunk: ${timeSinceLastChunk}ms ago`);
          logger.error(`   - MediaRecorder state: ${mediaRecorderRef.current?.state}`);
          logger.error(`   - WebSocket state: ${wsRef.current?.readyState}`);
          logger.error(`   - isRecording: ${isRecording}`);
          logger.error(`   - isMuted: ${isMuted}`);
        }
      }
    }, 2000); // Check every 2 seconds

    return () => clearInterval(watchdog);
  }, [isRecording, isMuted]);

  // ✅ DISABLED: Too verbose - only enable when debugging hook lifecycle
  // logger.debug('🔄 Hook rendering with state:', {
  //   isMuted,
  //   connectionState,
  //   isRecording,
  //   hasPermissionError: !!permissionError,
  // });

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
