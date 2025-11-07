/**
 * WebRTC Audio Capture Type Definitions
 * VoxBridge 2.0 Phase 4: Web Voice Interface
 */

/**
 * WebSocket connection state
 */
export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error';

/**
 * WebSocket message event types
 */
export type WebRTCAudioEventType =
  | 'partial_transcript'
  | 'final_transcript'
  | 'ai_response_chunk'
  | 'ai_response_complete'
  | 'tts_start'
  | 'tts_complete'
  | 'bot_speaking_state_changed'  // Multi-turn: Bot speaking state for input blocking
  | 'service_error'  // Phase 2: Service error events
  | 'stop_listening'  // Silence detection event
  | 'error';

/**
 * WebSocket message structure (Server → Client)
 */
export interface WebRTCAudioMessage {
  event: WebRTCAudioEventType;
  data: {
    text?: string;
    user_id?: string;
    session_id?: string;
    duration_s?: number;  // For tts_complete event
    message?: string;     // For error event
    // Bot speaking state (multi-turn conversations)
    is_speaking?: boolean;  // For bot_speaking_state_changed event
    // Silence detection event fields
    reason?: string;             // stop_listening reason: "silence_detected" | "max_utterance_timeout"
    silence_duration_ms?: number;  // Duration of silence detected
    elapsed_ms?: number;          // Total elapsed time for max_utterance_timeout
    max_ms?: number;              // Max utterance limit for max_utterance_timeout
  };
}

/**
 * Session initialization message (Client → Server)
 */
export interface SessionInitMessage {
  event: 'session_init';
  session_id: string;
}

/**
 * Options for useWebRTCAudio hook
 */
export interface UseWebRTCAudioOptions {
  /** Active session ID (required for message association) */
  sessionId: string | null;

  /** Callback for incoming WebSocket messages */
  onMessage?: (message: WebRTCAudioMessage) => void;

  /** Callback for errors */
  onError?: (error: string) => void;

  /** Auto-start recording on mount (default: false) */
  autoStart?: boolean;

  /** Milliseconds between audio chunks (default: 100) */
  timeslice?: number;
}

/**
 * Return type for useWebRTCAudio hook
 */
export interface UseWebRTCAudioReturn {
  /** Whether microphone is muted */
  isMuted: boolean;

  /** Toggle microphone mute/unmute */
  toggleMute: () => void;

  /** WebSocket connection state */
  connectionState: ConnectionState;

  /** Permission error message (null if no error) */
  permissionError: string | null;

  /** Whether actively recording audio */
  isRecording: boolean;

  /** Manually start recording (requests microphone permission) */
  start: () => Promise<void>;

  /** Manually stop recording and disconnect */
  stop: () => void;
}

/**
 * MediaRecorder MIME types supported for audio encoding
 */
export const SUPPORTED_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/ogg;codecs=opus',
  'audio/webm',
] as const;

/**
 * Default WebSocket reconnection settings
 */
export const WEBSOCKET_CONFIG = {
  MAX_RECONNECT_ATTEMPTS: 5,
  RECONNECT_INTERVAL: 3000, // milliseconds
  DEFAULT_TIMESLICE: 100, // milliseconds
} as const;

/**
 * getUserMedia constraints for audio capture
 */
export const AUDIO_CONSTRAINTS: MediaStreamConstraints = {
  audio: {
    channelCount: 1, // Mono
    sampleRate: 16000, // 16kHz (WhisperX compatible)
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  },
};
