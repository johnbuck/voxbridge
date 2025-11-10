/**
 * Service Error Types
 * VoxBridge 2.0 - Frontend Error Handling
 *
 * Defines error event types for backend service failures.
 */

// Speech-to-Text (WhisperX) Errors
export const STT_CONNECTION_FAILED = "stt_connection_failed" as const;
export const STT_TRANSCRIPTION_FAILED = "stt_transcription_failed" as const;
export const STT_SERVICE_UNAVAILABLE = "stt_service_unavailable" as const;

// Text-to-Speech (Chatterbox) Errors
export const TTS_SYNTHESIS_FAILED = "tts_synthesis_failed" as const;
export const TTS_SERVICE_UNAVAILABLE = "tts_service_unavailable" as const;
export const TTS_VOICE_NOT_FOUND = "tts_voice_not_found" as const;

// LLM Provider Errors
export const LLM_PROVIDER_FAILED = "llm_provider_failed" as const;
export const LLM_RATE_LIMITED = "llm_rate_limited" as const;
export const LLM_INVALID_RESPONSE = "llm_invalid_response" as const;
export const LLM_TIMEOUT = "llm_timeout" as const;
export const LLM_CONTEXT_LENGTH_EXCEEDED = "llm_context_length_exceeded" as const;

export type ServiceErrorType =
  | typeof STT_CONNECTION_FAILED
  | typeof STT_TRANSCRIPTION_FAILED
  | typeof STT_SERVICE_UNAVAILABLE
  | typeof TTS_SYNTHESIS_FAILED
  | typeof TTS_SERVICE_UNAVAILABLE
  | typeof TTS_VOICE_NOT_FOUND
  | typeof LLM_PROVIDER_FAILED
  | typeof LLM_RATE_LIMITED
  | typeof LLM_INVALID_RESPONSE
  | typeof LLM_TIMEOUT
  | typeof LLM_CONTEXT_LENGTH_EXCEEDED;

export type ServiceName = "whisperx" | "chatterbox" | "llm_provider";
export type ErrorSeverity = "warning" | "error" | "critical";

export interface ServiceErrorEvent {
  event_type: "service_error";
  service_name: ServiceName;
  error_type: ServiceErrorType;
  user_message: string;
  technical_details: string;
  session_id?: string;
  severity: ErrorSeverity;
  retry_suggested: boolean;
  timestamp?: string;
}

export interface ServiceErrorState {
  lastError: string | null;
  lastErrorTime: Date | null;
  errorCount: number;
  status: "healthy" | "warning" | "error";
}
