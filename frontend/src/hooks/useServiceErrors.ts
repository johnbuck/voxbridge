/**
 * Service Error Handling Hook
 * VoxBridge 2.0 - Frontend Error Handling
 *
 * Centralizes error handling for backend services (WhisperX, Chatterbox, LLM providers).
 * Displays toast notifications and logs technical details.
 */

import { useCallback } from 'react';
import { useToastHelpers } from '@/components/ui/toast';
import type { ServiceErrorEvent, ServiceErrorType, ServiceName } from '@/types/errors';
import {
  STT_CONNECTION_FAILED,
  STT_TRANSCRIPTION_FAILED,
  STT_SERVICE_UNAVAILABLE,
  TTS_SYNTHESIS_FAILED,
  TTS_SERVICE_UNAVAILABLE,
  TTS_VOICE_NOT_FOUND,
  LLM_PROVIDER_FAILED,
  LLM_RATE_LIMITED,
  LLM_INVALID_RESPONSE,
  LLM_TIMEOUT,
  LLM_CONTEXT_LENGTH_EXCEEDED,
} from '@/types/errors';
import { errorMessages } from '@/lib/errorMessages';

export interface UseServiceErrorsOptions {
  onError?: (error: ServiceErrorEvent) => void;
  showToast?: boolean;
  logToConsole?: boolean;
}

export interface UseServiceErrorsReturn {
  handleServiceError: (error: ServiceErrorEvent) => void;
}

export function useServiceErrors(options: UseServiceErrorsOptions = {}): UseServiceErrorsReturn {
  const toast = useToastHelpers();
  const { onError, showToast = true, logToConsole = true } = options;

  const handleServiceError = useCallback(
    (error: ServiceErrorEvent) => {
      // Call custom error handler if provided
      if (onError) {
        onError(error);
      }

      // Log technical details to console for debugging
      if (logToConsole) {
        console.error(
          `[${error.service_name.toUpperCase()}] ${error.error_type}:`,
          {
            userMessage: error.user_message,
            technicalDetails: error.technical_details,
            sessionId: error.session_id,
            severity: error.severity,
            retrySuggested: error.retry_suggested,
            timestamp: error.timestamp || new Date().toISOString(),
          }
        );
      }

      // Show toast notification
      if (showToast) {
        const title = getErrorTitle(error.service_name, error.error_type);
        const description = error.user_message || errorMessages[error.error_type];

        // Toast type based on severity (duration is handled by toast helper)
        if (error.severity === "critical" || error.severity === "error") {
          toast.error(title, description);
        } else {
          toast.warning(title, description);
        }
      }
    },
    [onError, showToast, logToConsole, toast]
  );

  return { handleServiceError };
}

// Helper function for error titles
function getErrorTitle(serviceName: ServiceName, errorType: ServiceErrorType): string {
  const serviceNames: Record<ServiceName, string> = {
    whisperx: "Speech Recognition",
    chatterbox: "Voice Synthesis",
    llm_provider: "AI Response",
  };

  const errorActions: Record<ServiceErrorType, string> = {
    [STT_CONNECTION_FAILED]: "Connection Failed",
    [STT_TRANSCRIPTION_FAILED]: "Transcription Failed",
    [STT_SERVICE_UNAVAILABLE]: "Service Unavailable",
    [TTS_SYNTHESIS_FAILED]: "Synthesis Failed",
    [TTS_SERVICE_UNAVAILABLE]: "Service Unavailable",
    [TTS_VOICE_NOT_FOUND]: "Voice Not Found",
    [LLM_PROVIDER_FAILED]: "Provider Failed",
    [LLM_RATE_LIMITED]: "Rate Limited",
    [LLM_INVALID_RESPONSE]: "Invalid Response",
    [LLM_TIMEOUT]: "Request Timeout",
    [LLM_CONTEXT_LENGTH_EXCEEDED]: "Context Too Long",
  };

  return `${serviceNames[serviceName]} - ${errorActions[errorType]}`;
}
