/**
 * User-Friendly Error Messages
 * VoxBridge 2.0 - Frontend Error Handling
 *
 * Maps backend error types to user-friendly messages with actionable guidance.
 */

import type { ServiceErrorType } from '@/types/errors';
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

export const errorMessages: Record<ServiceErrorType, string> = {
  // Speech-to-Text Errors
  [STT_CONNECTION_FAILED]:
    "Unable to connect to speech recognition service. Please check your connection and try again.",

  [STT_TRANSCRIPTION_FAILED]:
    "Could not transcribe your speech. Please speak more clearly and try again.",

  [STT_SERVICE_UNAVAILABLE]:
    "Speech recognition service is currently unavailable. Please try again in a few moments.",

  // Text-to-Speech Errors
  [TTS_SYNTHESIS_FAILED]:
    "Voice synthesis failed. The response will be shown as text only.",

  [TTS_SERVICE_UNAVAILABLE]:
    "Voice synthesis service is unavailable. Using text-only mode.",

  [TTS_VOICE_NOT_FOUND]:
    "Configured voice not found. Using default voice or text-only mode.",

  // LLM Provider Errors
  [LLM_PROVIDER_FAILED]:
    "AI provider failed to respond. Please try again or switch providers in agent settings.",

  [LLM_RATE_LIMITED]:
    "Rate limit exceeded. Please wait a moment before trying again.",

  [LLM_INVALID_RESPONSE]:
    "Received invalid response from AI. Please try rephrasing your question.",

  [LLM_TIMEOUT]:
    "AI response timed out. Please try again with a shorter or simpler question.",

  [LLM_CONTEXT_LENGTH_EXCEEDED]:
    "Conversation is too long for the AI model. Please start a new conversation.",
};

export const retryMessages: Record<ServiceErrorType, string> = {
  [STT_CONNECTION_FAILED]: "Retry speaking",
  [STT_TRANSCRIPTION_FAILED]: "Speak again",
  [STT_SERVICE_UNAVAILABLE]: "Wait and retry",
  [TTS_SYNTHESIS_FAILED]: "Continue with text",
  [TTS_SERVICE_UNAVAILABLE]: "Continue with text",
  [TTS_VOICE_NOT_FOUND]: "Continue with default",
  [LLM_PROVIDER_FAILED]: "Retry or change agent",
  [LLM_RATE_LIMITED]: "Wait 60 seconds",
  [LLM_INVALID_RESPONSE]: "Rephrase question",
  [LLM_TIMEOUT]: "Simplify question",
  [LLM_CONTEXT_LENGTH_EXCEEDED]: "Start new conversation",
};
