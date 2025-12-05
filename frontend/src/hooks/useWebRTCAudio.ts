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

// WebSocket URL configuration - uses nginx proxy for LAN/mobile compatibility
const getWebSocketUrl = () => {
  logger.debug('🔧 Environment check:');
  logger.debug('  - VITE_WS_URL:', import.meta.env.VITE_WS_URL || 'undefined');
  logger.debug('  - import.meta.env.PROD:', import.meta.env.PROD);
  logger.debug('  - window.location.host:', window.location.host);

  // Allow explicit override via env var (for special deployments)
  if (import.meta.env.VITE_WS_URL) {
    logger.debug('✅ Using VITE_WS_URL from env:', import.meta.env.VITE_WS_URL);
    return import.meta.env.VITE_WS_URL;
  }

  // Production: use same host/port as page (nginx proxy handles routing)
  // This enables mobile/LAN access without requiring port 4900 to be exposed
  if (import.meta.env.PROD) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}`;
    logger.debug('🏭 Production mode - using nginx proxy:', url);
    return url;
  }

  // Development fallback (local machine, localhost works)
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
  isPendingTTS: boolean;  // Whether TTS audio is pending (AI is generating/streaming response)

  // Phase 3 Refactor: Separate mic control from session lifecycle
  startMicrophone: () => Promise<void>;  // Start mic only (assumes WebSocket connected)
  stopMicrophone: () => void;            // Stop mic only (leaves WebSocket connected)
  startSession: () => Promise<void>;     // Start full session (mic + WebSocket)
  endSession: () => void;                // End full session (stop mic + disconnect WebSocket)

  // Backward compatibility (deprecated)
  /** @deprecated Use startSession() instead */
  start: () => Promise<void>;
  /** @deprecated Use stopMicrophone() instead */
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
    timeslice = 250, // 250ms chunks for complete WebM Clusters (web best practice)
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

  // TTS playback state tracking (for UI indicators only - multi-turn conversation mode)
  const [isPendingTTS, setIsPendingTTS] = useState(false);  // True when AI is generating/streaming TTS

  const wsRef = useRef<WebSocket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const audioChunksBufferRef = useRef<Blob[]>([]);
  const lastChunkTimeRef = useRef<number | null>(null); // Track last ondataavailable timestamp
  // emptyChunkCountRef removed - was only used in old start() function

  // Option E: Audio ducking refs (Web Audio API for gain control during TTS)
  const audioContextRef = useRef<AudioContext | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const destinationStreamRef = useRef<MediaStream | null>(null);

  // Increased from 5 to 999 to allow backend auto-reconnect time to succeed
  // Backend STT service now handles reconnection, so frontend should be resilient
  const MAX_RECONNECT_ATTEMPTS = 999;
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

            // Option E: Handle bot speaking state changes for audio ducking
            if (message.event === 'bot_speaking_state_changed') {
              const isSpeaking = message.data.is_speaking;

              if (gainNodeRef.current && audioContextRef.current) {
                if (isSpeaking) {
                  // Duck to 20% during TTS
                  logger.info('🔉 Ducking microphone gain to 20% (TTS playing)');
                  gainNodeRef.current.gain.setTargetAtTime(
                    0.2,
                    audioContextRef.current.currentTime,
                    0.1  // 100ms smooth transition
                  );
                } else {
                  // Restore full gain after TTS
                  logger.info('🔊 Restoring microphone gain to 100% (TTS complete)');
                  gainNodeRef.current.gain.setTargetAtTime(
                    1.0,
                    audioContextRef.current.currentTime,
                    0.1
                  );
                }
              }

              // Pass event to parent
              if (onMessage) {
                onMessage(message);
              }
              return;
            }

            // Handle AI response start - track TTS pending state
            if (message.event === 'ai_response_start') {
              logger.info('🤖 AI response started - TTS pending');
              setIsPendingTTS(true);
              // Notify parent component
              if (onMessage) {
                onMessage(message);
              }
              return;
            }

            // Handle TTS complete - MULTI-TURN MODE: Keep connection open!
            // After TTS completes, we wait for user to speak again (auto-restart detection on backend)
            // Only disconnect when user explicitly stops or closes page
            if (message.event === 'tts_complete') {
              logger.info('✅ TTS complete - ready for next conversation turn');
              setIsPendingTTS(false);

              // Notify parent so it can trigger audio playback
              if (onMessage) {
                onMessage(message);
              }
              // ✅ MULTI-TURN: Keep WebSocket alive - user can speak again immediately
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
        // ✅ ARCHITECTURE FIX: Always reconnect WebSocket regardless of mic mute state
        // Mic mute should ONLY affect audio capture, not WebSocket connectivity
        // This allows AI responses and TTS to work even when mic is muted
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
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
  }, [sessionId, onMessage, onBinaryMessage, onServiceError, onError]);

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

  // ============================================================================
  // OLD start() FUNCTION REMOVED - Replaced by Phase 3 Refactor
  // See new architecture below: startMicrophone, stopMicrophone, startSession, endSession
  // ============================================================================

  // ============================================================================
  // PHASE 3 REFACTOR: Separate Microphone Control from Session/WebSocket Lifecycle
  // ============================================================================
  //
  // Architecture: Discord-Style Persistent Connection (Option 1)
  // - WebSocket stays connected across all conversation switches
  // - Mic mute/unmute only affects audio capture (not WebSocket)
  // - Switching conversations sends session_init message (no reconnect)
  // - Only disconnect WebSocket on tab close or explicit "Leave Voice"
  //
  // Functions:
  // - startMicrophone() / stopMicrophone() = Mic control only
  // - startSession() / endSession() = Full lifecycle (mic + WebSocket)
  // - toggleMute() = Uses startMicrophone/stopMicrophone (no WebSocket interaction)
  // ============================================================================

  /**
   * Start microphone capture only (assumes WebSocket already connected)
   * Used by: toggleMute() when unmuting
   */
  const startMicrophone = useCallback(async () => {
    logger.info('🎙️ startMicrophone() called - enabling microphone input only');

    try {
      setPermissionError(null);

      // If we don't have a media stream yet, request microphone access
      if (!mediaStreamRef.current) {
        logger.debug('🎤 No existing stream, requesting microphone access...');
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 2, // Stereo (matching Discord)
            sampleRate: 48000, // 48kHz (matching Discord)
            echoCancellation: { ideal: true },  // Force enable
            noiseSuppression: { ideal: true },
            autoGainControl: { ideal: true },
          },
        });
        logger.info('✅ Microphone access GRANTED');

        // Verify echo cancellation is active (Option A: Enhanced WebRTC AEC)
        const audioTrack = stream.getAudioTracks()[0];
        const settings = audioTrack.getSettings();
        logger.info('🎧 Audio constraints applied:', {
          echoCancellation: settings.echoCancellation,
          noiseSuppression: settings.noiseSuppression,
          autoGainControl: settings.autoGainControl,
          sampleRate: settings.sampleRate,
          channelCount: settings.channelCount,
        });

        if (!settings.echoCancellation) {
          logger.warn('⚠️ Echo cancellation not supported by browser!');
        }

        mediaStreamRef.current = stream;

        // Option E: Create Web Audio API pipeline for audio ducking
        // This allows us to reduce microphone gain during TTS playback
        try {
          const audioContext = new AudioContext();
          const source = audioContext.createMediaStreamSource(stream);
          const gainNode = audioContext.createGain();
          const destination = audioContext.createMediaStreamDestination();

          gainNode.gain.value = 1.0;  // Normal gain initially

          source.connect(gainNode);
          gainNode.connect(destination);

          // Store refs
          audioContextRef.current = audioContext;
          gainNodeRef.current = gainNode;
          sourceNodeRef.current = source;
          destinationStreamRef.current = destination.stream;

          logger.info('🎚️ Audio ducking pipeline created (gain: 100%)');
        } catch (error) {
          logger.error('❌ Failed to create Web Audio API pipeline:', error);
          // Continue without ducking (graceful degradation)
        }

        // Create MediaRecorder if it doesn't exist
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

        // Use destination stream (with gain control) if available, otherwise use original stream
        const recordingStream = destinationStreamRef.current || stream;
        logger.debug('🎙️ MediaRecorder using:', destinationStreamRef.current ? 'ducked stream' : 'original stream');

        const mediaRecorder = new MediaRecorder(recordingStream, {
          mimeType: selectedMimeType,
        });

        // Set up MediaRecorder event handlers (same as start())
        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            lastChunkTimeRef.current = Date.now();
            audioChunksBufferRef.current.push(event.data);

            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(event.data);
            }
          }
        };

        mediaRecorder.onstop = () => {
          logger.debug('🛑 MediaRecorder stopped');
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
      }

      // Enable audio tracks
      mediaStreamRef.current.getAudioTracks().forEach(track => {
        track.enabled = true;
        logger.debug('✅ Enabled audio track');
      });

      // Start MediaRecorder if not already recording
      if (mediaRecorderRef.current?.state === 'inactive') {
        logger.debug('🎬 Starting MediaRecorder with timeslice:', timeslice, 'ms');
        mediaRecorderRef.current.start(timeslice || 100);
      }

      // Update state
      setIsMuted(false);
      setIsRecording(true);

      logger.debug('✅ startMicrophone() completed successfully');
    } catch (err) {
      logger.error('❌ Failed to start microphone:', err);

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
    }
  }, [timeslice, onError]);

  /**
   * Stop microphone capture only (leaves WebSocket connected)
   * Used by: toggleMute() when muting
   */
  const stopMicrophone = useCallback(() => {
    logger.info('🛑 stopMicrophone() called - disabling microphone input only');

    // Stop MediaRecorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
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

    // Update state
    setIsMuted(true);
    setIsRecording(false);
    audioChunksBufferRef.current = [];

    // Notify parent component to clear UI state
    if (onRecordingStop) {
      logger.debug('   - Calling onRecordingStop callback');
      onRecordingStop();
    }

    // ✅ DISCORD-STYLE PERSISTENT CONNECTION: WebSocket stays alive
    // Philosophy: Mic OFF = "stop listening to me", NOT "end conversation"
    // - WebSocket remains connected for TTS audio and conversation switching
    // - User can unmute and speak again immediately (no reconnection delay)
    // - Connection only closes when user leaves page (endSession) or explicit disconnect
    logger.info('✅ Microphone stopped - WebSocket stays open for persistent connection');

    logger.debug('✅ stopMicrophone() completed');
  }, [onRecordingStop]);

  /**
   * Start full session (microphone + WebSocket connection)
   * Used by: Auto-start effect, initial page load
   */
  const startSession = useCallback(async () => {
    logger.info('🚀 startSession() called - starting full voice session');

    // Connect WebSocket first
    connectWebSocket();

    // Then start microphone
    await startMicrophone();

    logger.debug('✅ startSession() completed');
  }, [connectWebSocket, startMicrophone]);

  /**
   * End full session (stop microphone + disconnect WebSocket)
   * Used by: Component unmount, explicit "Leave Voice" action
   */
  const endSession = useCallback(() => {
    logger.info('🛑 endSession() called - ending full voice session');

    // Stop microphone
    stopMicrophone();

    // Disconnect WebSocket
    disconnectWebSocket();

    logger.debug('✅ endSession() completed');
  }, [stopMicrophone, disconnectWebSocket]);

  // ============================================================================
  // BACKWARD COMPATIBILITY: Keep old function names as aliases
  // ============================================================================

  /**
   * @deprecated Use startSession() instead
   * Kept for backward compatibility
   */
  const start = startSession;

  /**
   * @deprecated Use stopMicrophone() instead
   * Kept for backward compatibility
   */
  const stop = stopMicrophone;

  /**
   * Toggle microphone mute state
   * If WebSocket is disconnected (e.g., after "Leave Voice"), reconnect everything
   * Otherwise, only toggle mic (Discord-style: WebSocket stays connected)
   */
  const toggleMute = useCallback(() => {
    logger.debug('🔄 toggleMute() called (current isMuted:', isMuted, ')');

    if (isMuted) {
      // Unmuting - check if WebSocket is disconnected
      const wsState = wsRef.current?.readyState;
      logger.debug('   - Currently muted, checking WebSocket state:', wsState);

      if (wsState !== WebSocket.OPEN && wsState !== WebSocket.CONNECTING) {
        // WebSocket is disconnected (e.g., after "Leave Voice") - start full session
        logger.info('   - WebSocket disconnected, starting full session (WebSocket + mic)');
        startSession();
      } else {
        // WebSocket is connected - just unmute mic
        logger.debug('   - WebSocket connected, just starting microphone');
        startMicrophone();
      }
    } else {
      logger.debug('   - Currently unmuted, calling stopMicrophone()...');
      stopMicrophone();   // ✅ Only affects mic, WebSocket stays connected
    }
  }, [isMuted, startMicrophone, stopMicrophone, startSession]);

  // Component mount/unmount lifecycle
  useEffect(() => {
    logger.debug('🔄 useEffect[mount] - Component mounted');

    // Auto-start if enabled
    if (autoStart && sessionId) {
      logger.debug('   - Calling startSession() due to autoStart (mic + WebSocket)');
      startSession();
    }

    // Cleanup on unmount ONLY - not on sessionId changes
    return () => {
      logger.debug('🧹 useEffect[mount] cleanup - Component unmounting, calling endSession()');

      // Option E: Cleanup Web Audio API resources
      if (audioContextRef.current) {
        logger.debug('   - Closing AudioContext');
        audioContextRef.current.close();
        audioContextRef.current = null;
      }

      endSession();  // ✅ Proper cleanup when component unmounts (user leaving page)
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run once on mount, cleanup once on unmount

  // Session switching - handle sessionId changes after mount
  useEffect(() => {
    logger.debug('🔄 useEffect[sessionId] triggered - session ID changed to:', sessionId);

    if (!sessionId) {
      logger.debug('   - No session ID, skipping');
      return;
    }

    // If WebSocket is already connected, just send session_init
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      logger.debug('   - WebSocket already open, sending session_init message');
      wsRef.current.send(JSON.stringify({ event: 'session_init', session_id: sessionId }));
      return;
    }

    // If WebSocket is disconnected, auto-connect (Discord-style persistent connection)
    if (wsRef.current?.readyState !== WebSocket.CONNECTING) {
      logger.info('🚀 Session selected - auto-connecting WebSocket (Discord-style)');
      connectWebSocket();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]); // Only depend on sessionId, not connectWebSocket (stable via useCallback)

  // Watchdog: Detect if MediaRecorder stops sending chunks (silent failure)
  useEffect(() => {
    if (!isRecording) return;

    const watchdog = setInterval(() => {
      if (lastChunkTimeRef.current) {
        const timeSinceLastChunk = Date.now() - lastChunkTimeRef.current;
        if (timeSinceLastChunk > 5000) { // 5 seconds without chunks = problem
          logger.error(`🚨 [WATCHDOG] MediaRecorder ondataavailable stopped firing!`);
          logger.error(`   - Last chunk: ${timeSinceLastChunk}ms ago`);
          logger.error(`   - MediaRecorder state: ${mediaRecorderRef.current?.state}`);
          logger.error(`   - WebSocket state: ${wsRef.current?.readyState}`);
          logger.error(`   - isRecording: ${isRecording}, isMuted: ${isMuted}`);
          logger.error(`   - Chunk count: ${audioChunksBufferRef.current.length}`);
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
    isPendingTTS,  // Export for UI indicators

    // Phase 3 Refactor: New lifecycle functions
    startMicrophone,   // Start mic only (assumes WebSocket connected)
    stopMicrophone,    // Stop mic only (leaves WebSocket connected)
    startSession,      // Start full session (mic + WebSocket)
    endSession,        // End full session (stop mic + disconnect WebSocket)

    // Backward compatibility (deprecated)
    start,  // @deprecated Use startSession() instead
    stop,   // @deprecated Use stopMicrophone() instead
  };
}
