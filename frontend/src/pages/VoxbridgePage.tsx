/**
 * VoxBridge Main Dashboard Page
 * Analytics at TOP, Unified Conversation Interface at BOTTOM
 * VoxBridge 2.0 - Proper conversation management integration
 */

import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type Message } from '@/services/api';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { MetricsPanel } from '@/components/MetricsPanel';
import { StatusSummary } from '@/components/StatusSummary';
import { RuntimeSettings } from '@/components/RuntimeSettings';
import { ConversationList } from '@/components/ConversationList';
import { NewConversationDialog } from '@/components/NewConversationDialog';
import { AudioControls } from '@/components/AudioControls';
import { AIGeneratingIndicator } from '@/components/AIGeneratingIndicator';
import { BouncingDots } from '@/components/BouncingDots';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { useToastHelpers } from '@/components/ui/toast';
import { useWebRTCAudio } from '@/hooks/useWebRTCAudio';
import { useAudioPlayback } from '@/hooks/useAudioPlayback';
import { useServiceErrors } from '@/hooks/useServiceErrors';
import type { WebRTCAudioMessage } from '@/types/webrtc';
import type { ServiceErrorEvent } from '@/types/errors';
import {
  STT_CONNECTION_FAILED,
  LLM_PROVIDER_FAILED,
  LLM_TIMEOUT,
  TTS_SYNTHESIS_FAILED,
  TTS_SERVICE_UNAVAILABLE,
} from '@/types/errors';
import { Copy, CircleCheckBig, Activity, XCircle, AlertCircle, Volume2, VolumeX, Menu, MessageSquare, Brain, Lock, Unlock, Loader2, LogIn, LogOut, Server, Link } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { ChannelSelectorModal } from '@/components/ChannelSelectorModal';
import { createLogger } from '@/utils/logger';

// Initialize logger for VoxbridgePage
const logger = createLogger('VoxbridgePage');
// BUG FIX #5: Debug logs removed for performance. To re-enable for troubleshooting:
// Set VITE_LOG_LEVEL_UI=DEBUG in frontend/.env and rebuild frontend container

// Use for creating new web sessions (can be changed when auth is added)
const WEB_USER_ID = 'web_user_default';

export function VoxbridgePage() {
  // Analytics state (Discord conversation monitoring) - kept for future Discord transcript integration
  const [activeSpeaker, setActiveSpeaker] = useState<string | null>(null);
  const [partialTranscript, setPartialTranscript] = useState<string>('');
  const [showStatistics, setShowStatistics] = useState(false);

  // Conversation Management state
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [newConversationDialogOpen, setNewConversationDialogOpen] = useState(false);
  const [speakerLocked, setSpeakerLocked] = useState(false);
  const [isUnlocking, setIsUnlocking] = useState(false);

  // Discord voice connection state
  const [showChannelSelector, setShowChannelSelector] = useState(false);
  const [discordBotReady, setDiscordBotReady] = useState(false);
  const [discordInVoice, setDiscordInVoice] = useState(false);
  const [discordChannelName, setDiscordChannelName] = useState<string | null>(null);
  const [discordGuildName, setDiscordGuildName] = useState<string | null>(null);
  const [discordGuildId, setDiscordGuildId] = useState<string | null>(null);
  const [isJoiningLeaving, setIsJoiningLeaving] = useState(false);

  // Unified conversation state (adapts for Discord/WebRTC)
  const [isListening, setIsListening] = useState(false);
  const [isVoiceAIGenerating, setIsVoiceAIGenerating] = useState(false);
  const [aiGeneratingDuration, setAiGeneratingDuration] = useState(0);
  const [streamingChunks, setStreamingChunks] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isSpeakerMuted, setIsSpeakerMuted] = useState(false);
  const [voicePartialTranscript, setVoicePartialTranscript] = useState<string>('');
  const [isBotSpeaking, setIsBotSpeaking] = useState(false);  // Bot speaking state (blocks input during TTS)
  const [activeTTSContent, setActiveTTSContent] = useState<string | null>(null);  // Track message content being synthesized for ellipsis animation (survives DB refetch)
  const [pendingUserTranscript, setPendingUserTranscript] = useState<{ text: string; isFinalizing: boolean; isStreaming: boolean } | null>(null);

  const queryClient = useQueryClient();
  const toast = useToastHelpers();
  const listeningStartTimeRef = useRef<number | null>(null);
  const aiStartTimeRef = useRef<number | null>(null);
  const isHandlingMessageRef = useRef(false); // Batch 3.3: Re-entrance detection
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // Service error handling
  const { handleServiceError } = useServiceErrors({
    onError: (error) => {
      // Custom error handling logic
      if (error.error_type === STT_CONNECTION_FAILED) {
        // Stop recording if STT connection fails
        setIsListening(false);
        setVoicePartialTranscript('');
      } else if (error.error_type === LLM_PROVIDER_FAILED || error.error_type === LLM_TIMEOUT) {
        // Stop AI generating indicator if LLM fails
        setIsVoiceAIGenerating(false);
        setIsStreaming(false);
        setStreamingChunks([]);
      } else if (error.error_type === TTS_SYNTHESIS_FAILED || error.error_type === TTS_SERVICE_UNAVAILABLE) {
        // Clear TTS audio buffer if synthesis fails
        audioPlayback.stop();
      }
    }
  });

  // Poll detailed status
  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: () => api.getStatus(),
    refetchInterval: 5000,
  });

  // Fetch metrics
  const { data: metrics, isLoading: isLoadingMetrics } = useQuery({
    queryKey: ['metrics'],
    queryFn: () => api.getMetrics(),
    // Metrics are refetched when AI responses complete (via invalidation)
  });

  // Fetch ALL sessions (both web and Discord) for conversation management
  const { data: sessions = [], isLoading: isLoadingSessions, refetch: refetchSessions } = useQuery({
    queryKey: ['sessions'], // Remove USER_ID from key - fetch all sessions
    queryFn: () => api.getSessions(undefined, false, 50), // undefined = all users
    refetchInterval: 5000, // Poll every 5 seconds
  });

  // Fetch agents for new conversation dialog
  const { data: agents = [], isLoading: isLoadingAgents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => api.getAgents(),
  });

  // Fetch messages for active session
  const { data: messages = [], isLoading: isLoadingMessages, dataUpdatedAt } = useQuery<Message[]>({
    queryKey: ['messages', activeSessionId],
    queryFn: async () => {
      if (!activeSessionId) return [];

      const fetchStart = Date.now();
      logger.debug('🔄 [QUERY_START] Fetching messages', {
        sessionId: activeSessionId,
        timestamp: fetchStart,
      });

      const result = await api.getSessionMessages(activeSessionId);

      const fetchEnd = Date.now();
      const fetchDuration = fetchEnd - fetchStart;

      logger.debug('✅ [QUERY_COMPLETE] Fetched messages', {
        count: result.length,
        userCount: result.filter(m => m.role === 'user').length,
        assistantCount: result.filter(m => m.role === 'assistant').length,
        duration: fetchDuration,
        timestamp: fetchEnd,
      });

      return result;
    },
    enabled: !!activeSessionId,
    staleTime: Infinity, // ✅ Optimistic UI: Never auto-refetch, only invalidate on explicit events
    refetchOnWindowFocus: false, // ✅ Don't refetch on window focus
    // refetchInterval removed - WebSocket provides real-time updates, explicit invalidation on completion

    // Lifecycle callbacks for logging
    onSuccess: (data) => {
      logger.debug('📦 [QUERY_SUCCESS] Cache updated', {
        messagesCount: data.length,
        timestamp: Date.now(),
      });
    },
    onError: (error) => {
      logger.error('❌ [QUERY_ERROR] Failed to fetch messages', {
        error: String(error),
        timestamp: Date.now(),
      });
    },
  });

  // ✅ Optimistic UI: Merge database messages + streaming chunks for seamless display
  const displayMessages = useMemo(() => {
    // BUG FIX #3: Removed debug logging spam (was causing 150+ logs per 3-second utterance)
    const dbMessages = [...messages];

    // Add pending user transcript placeholder (shows immediately before DB fetch)
    // Only show if the message isn't already in the database (prevents duplicates)
    if (pendingUserTranscript && activeSessionId) {
      const hasPendingInDB = dbMessages.some(
        m => m.role === 'user' && m.content === pendingUserTranscript.text
      );

      if (!hasPendingInDB) {
        // Add optimistic user message to display
        dbMessages.push({
          id: 'pending-user-message', // Stable string ID (BUG FIX: was Date.now() - 1)
          session_id: activeSessionId,
          role: 'user',
          content: pendingUserTranscript.text,
          timestamp: new Date().toISOString(),
          audio_duration_ms: null,
          tts_duration_ms: null,
          llm_latency_ms: null,
          total_latency_ms: null,
          isPending: !pendingUserTranscript.isFinalizing,
          isFinalizing: pendingUserTranscript.isFinalizing,
          isStreaming: pendingUserTranscript.isStreaming,
        } as unknown as Message);
      }
      // else: Pending message already in DB, skip placeholder

    }

    // If streaming, append optimistic message (not yet in database)
    if (streamingChunks.length > 0 && activeSessionId) {
      const streamingContent = streamingChunks.join('');
      // Add optimistic AI streaming message to display
      dbMessages.push({
        id: 'streaming-ai-message', // Stable string ID (BUG FIX: was Date.now())
        session_id: activeSessionId,
        role: 'assistant',
        content: streamingContent,
        timestamp: new Date().toISOString(),
        audio_duration_ms: null,
        tts_duration_ms: null,
        llm_latency_ms: null,
        total_latency_ms: null,
        isStreaming: true,
      } as unknown as Message);
    }

    return dbMessages;
  }, [
    messages,
    streamingChunks,
    activeSessionId,
    // BUG FIX #4: Destructure to prevent re-renders on object reference changes
    pendingUserTranscript?.text,
    pendingUserTranscript?.isFinalizing,
    pendingUserTranscript?.isStreaming
  ]);

  // Monitor React Query cache updates via dataUpdatedAt
  useEffect(() => {
    if (dataUpdatedAt && Array.isArray(messages) && messages.length > 0) {
      logger.debug('📦 [CACHE_UPDATED] Cache reflected new data', {
        messagesCount: messages.length,
        userCount: messages.filter((m: Message) => m.role === 'user').length,
        assistantCount: messages.filter((m: Message) => m.role === 'assistant').length,
        dataUpdatedAt,
        timestamp: Date.now(),
      });
    }
  }, [dataUpdatedAt, messages]);

  // State conflict detection: Detect invalid state combinations
  useEffect(() => {
    // Detect invalid state combinations
    if (isListening && isBotSpeaking) {
      logger.error('🚨 [STATE_CONFLICT] Invalid: isListening && isBotSpeaking both true!');
    }
    if (isListening && isVoiceAIGenerating) {
      logger.warn('⚠️ [STATE_CONFLICT] Unusual: isListening && isVoiceAIGenerating both true');
    }
    if (isStreaming && !isVoiceAIGenerating) {
      logger.warn('⚠️ [STATE_CONFLICT] Unusual: isStreaming true but isVoiceAIGenerating false');
    }
    // Note: connectionState check removed as variable no longer exists
  }, [isListening, isBotSpeaking, isVoiceAIGenerating, isStreaming]);

  // Batch 2.4: Frontend LLM timeout safety (120s)
  useEffect(() => {
    if (!isVoiceAIGenerating || !aiStartTimeRef.current) return;

    const checkTimeout = setInterval(() => {
      if (aiStartTimeRef.current) {
        const elapsed = Date.now() - aiStartTimeRef.current;
        if (elapsed > 120000) { // 120 seconds
          logger.error(`🚨 [LLM_TIMEOUT] Frontend safety timeout triggered - AI generating for ${elapsed}ms (>120s)`);
          logger.error('   - This may indicate backend timeout or stuck LLM request');
          logger.error('   - Consider refreshing the page or reconnecting');
        }
      }
    }, 5000); // Check every 5 seconds

    return () => clearInterval(checkTimeout);
  }, [isVoiceAIGenerating]);

  // Defensive auto-clear: If DB message loaded while placeholder still visible, clear it immediately
  // This ensures seamless transition from optimistic → database message
  useEffect(() => {
    if (pendingUserTranscript && activeSessionId && Array.isArray(messages) && messages.length > 0) {
      const hasPendingInDB = messages.some(
        (m: Message) => m.role === 'user' && m.content === pendingUserTranscript.text
      );

      // Clear immediately when DB message exists (no duplicate bubbles)
      if (hasPendingInDB) {
        logger.debug('🧹 [AUTO_CLEAR] DB message loaded - clearing pendingUserTranscript', {
          pendingText: pendingUserTranscript.text.substring(0, 50),
          messagesCount: messages.length,
          timestamp: Date.now(),
        });
        setPendingUserTranscript(null);
      } else {
        logger.debug('⏳ [AUTO_CLEAR] Pending message not in DB yet, keeping placeholder', {
          pendingText: pendingUserTranscript.text.substring(0, 30),
          dbUserMessagesCount: messages.filter((m: Message) => m.role === 'user').length,
          timestamp: Date.now(),
        });
      }
    }
  }, [messages, pendingUserTranscript, activeSessionId]);

  // BUG FIX: Clear streaming chunks AFTER cache update reflects in messages query
  // This prevents AI responses from disappearing due to race condition
  useEffect(() => {
    if (streamingChunks.length > 0 && activeSessionId && Array.isArray(messages) && messages.length > 0) {
      // Check if the streaming content has been added to the messages array
      const streamingContent = streamingChunks.join('');
      const hasStreamingInDB = messages.some(
        (m: Message) => m.role === 'assistant' && m.content === streamingContent
      );

      if (hasStreamingInDB) {
        logger.debug('🧹 [AUTO_CLEAR_AI] Cache update reflected - clearing streamingChunks', {
          streamingContent: streamingContent.substring(0, 50),
          chunksCount: streamingChunks.length,
          messagesCount: messages.length,
          timestamp: Date.now(),
        });
        setStreamingChunks([]);
      } else {
        logger.debug('⏳ [AUTO_CLEAR_AI] Streaming message not in cache yet, keeping chunks', {
          streamingContent: streamingContent.substring(0, 30),
          chunksCount: streamingChunks.length,
          dbAIMessagesCount: messages.filter((m: Message) => m.role === 'assistant').length,
          timestamp: Date.now(),
        });
      }
    }
  }, [messages, streamingChunks, activeSessionId]);

  // Get active session details
  const activeSession = sessions.find((s) => s.id === activeSessionId);

  // Get agent for active session
  const activeAgent = agents.find((a) => a.id === activeSession?.agent_id);

  // Audio playback hook for TTS (web voice chat)
  const audioPlayback = useAudioPlayback({
    autoPlay: true,
    onPlaybackStart: () => logger.debug('🔊 Playing TTS audio'),
    onPlaybackEnd: () => logger.debug('✅ TTS playback complete'),
    onError: (error) => toast.error('Audio playback failed', error),
  });

  // Handle WebRTC audio messages (web voice chat with database persistence)
  const handleWebRTCAudioMessage = useCallback(
    async (message: WebRTCAudioMessage) => {
      // Batch 3.3: Re-entrance detection
      if (isHandlingMessageRef.current) {
        logger.warn(`⚠️ [REENTRANCE] WebSocket message handler re-entered while still processing (event: ${message.event})`);
      }
      isHandlingMessageRef.current = true;
      const handlerStartTime = performance.now();

      try {
        // Log all WebRTC events for debugging (debug only)
        logger.debug('📡', 'WS EVENT (WebRTC)', message.event, {
          event: message.event,
          sessionId: message.data?.session_id,
          textLength: message.data?.text?.length,
        }, true);

        switch (message.event) {
        case 'partial_transcript':
          // Show speech bubble immediately when user starts speaking
          // React will re-render when text content changes naturally

          if (!listeningStartTimeRef.current) {
            logger.debug('🎤', 'LISTENING (WebRTC)', `Started (partial: "${message.data.text?.substring(0, 30) || '(empty)'}...")`, undefined, true);
            listeningStartTimeRef.current = Date.now();
          }

          // Update voice chat partial transcript
          setVoicePartialTranscript(message.data.text || '');
          setIsListening(true);

          // Create optimistic user message placeholder (shows immediately in conversation)
          // Bubble will show "Listening..." if text is empty, or streaming text if available
          const transcriptText = message.data.text || '';
          logger.debug(`📝 [PENDING_USER] Setting pendingUserTranscript (partial)`, {
            text: transcriptText.substring(0, 50),
            length: transcriptText.length,
            isStreaming: true,
            isFinalizing: false,
            timestamp: Date.now(),
          });
          setPendingUserTranscript({
            text: transcriptText,
            isFinalizing: false,
            isStreaming: true
          });
          break;

        case 'final_transcript':
          logger.debug('🎤', 'LISTENING (WebRTC)', `Stopped (final: "${message.data.text?.substring(0, 50)}...")`, undefined, true);

          // Clear voice chat partial transcript
          setVoicePartialTranscript('');
          setIsListening(false);
          listeningStartTimeRef.current = null;

          // Update pending transcript to show finalizing state (bouncing dots)
          if (message.data.text) {
            logger.debug(`📝 [PENDING_USER] Setting pendingUserTranscript (final)`, {
              text: message.data.text.substring(0, 50),
              length: message.data.text.length,
              isStreaming: false,
              isFinalizing: true,
              timestamp: Date.now(),
            });
            setPendingUserTranscript({
              text: message.data.text,
              isFinalizing: true,
              isStreaming: false
            });
          }

          // Backend already saved user message - frontend only updates UI
          // (Removed duplicate save - backend is single source of truth)

          // Refresh message list to show backend-saved message
          // Note: Placeholder will be cleared in ai_response_complete, NOT here
          // This ensures user message stays visible during AI generation
          if (activeSessionId) {
            logger.debug('🔄', 'QUERY (WebRTC)', `Invalidating messages query (session: ${activeSessionId})`, undefined, true);
            queryClient.invalidateQueries({ queryKey: ['messages', activeSessionId] });
            logger.debug('✅ [PENDING_USER] Keeping placeholder visible - will clear after AI completes');
          }

          // Start AI generation indicator for voice chat
          logger.debug('💭', 'THINKING (WebRTC)', `Started (session: ${activeSessionId})`, undefined, true);
          setIsVoiceAIGenerating(true);
          aiStartTimeRef.current = Date.now();
          break;

        case 'ai_response_chunk':
          // Stream AI response chunks for voice chat
          // Use StreamingMessageDisplay component for real-time display
          // No optimistic updates needed - backend saves to database
          logger.debug(`🌊 [STREAMING_AI] Adding chunk to streamingChunks`, {
            chunkText: message.data.text?.substring(0, 50),
            chunkLength: message.data.text?.length,
            currentChunksCount: streamingChunks.length,
            timestamp: Date.now(),
          });
          setStreamingChunks((prev) => {
            const newChunks = [...prev, message.data.text || ''];
            logger.debug(`🌊 [STREAMING_AI] Updated streamingChunks`, {
              totalChunks: newChunks.length,
              totalLength: newChunks.join('').length,
              contentPreview: newChunks.join('').substring(0, 50),
            });
            return newChunks;
          });
          setIsStreaming(true);
          break;

        case 'ai_response_complete':
          const aiDuration = aiStartTimeRef.current ? Date.now() - aiStartTimeRef.current : 0;
          logger.debug('💭', 'THINKING (WebRTC)', `Complete (duration: ${aiDuration}ms)`, undefined, true);

          logger.debug(`🏁 [AI_COMPLETE] Starting ai_response_complete handler`, {
            activeSessionId,
            messageText: message.data.text?.substring(0, 50),
            currentStreamingChunksCount: streamingChunks.length,
            currentMessagesCount: messages.length,
            timestamp: Date.now(),
          });

          // Stop AI generating animation
          setIsVoiceAIGenerating(false);
          aiStartTimeRef.current = null;
          setAiGeneratingDuration(0);

          // Stop streaming animation
          setIsStreaming(false);

          // Don't clear pending here - let auto-clear effect handle it when DB query returns
          // This prevents the user message from disappearing during the refetch delay
          // logger.debug('[PENDING] Clearing user placeholder - AI response complete');
          // setPendingUserTranscript(null); // ❌ REMOVED: Causes 500ms gap

          // ✅ Optimistic UI: Directly update cache with completed message
          if (activeSessionId && message.data.text) {
            logger.debug('💾 [CACHE_UPDATE] Updating React Query cache with completed AI message', {
              sessionId: activeSessionId,
              textLength: message.data.text.length,
              textPreview: message.data.text.substring(0, 50),
              timestamp: Date.now(),
            });

            // Store temporary message ID for TTS tracking (ellipsis animation)
            const tempMessageId = Date.now();

            logger.debug('💾 [CACHE_SET] Updating cache with optimistic AI message', {
              sessionId: activeSessionId,
              textLength: message.data.text.length,
              tempMessageId,
              timestamp: Date.now(),
            });

            // Update cache immediately with new message
            queryClient.setQueryData<Message[]>(['messages', activeSessionId], (oldMessages = []) => {
              logger.debug('💾 [CACHE_SET] setQueryData callback executing', {
                oldMessagesCount: oldMessages.length,
                timestamp: Date.now(),
              });

              const newMessages = [
                ...oldMessages,
                {
                  id: tempMessageId, // Temporary ID until background refetch gets real DB ID
                  session_id: activeSessionId,
                  role: 'assistant',
                  content: message.data.text,
                  timestamp: new Date().toISOString(),
                  audio_duration_ms: null,
                  tts_duration_ms: null,
                  llm_latency_ms: null,
                  total_latency_ms: null,
                } as Message
              ];
              logger.debug('💾 [CACHE_SET] Cache update complete', {
                oldMessagesCount: oldMessages.length,
                newMessagesCount: newMessages.length,
                addedMessage: true,
                timestamp: Date.now(),
              });
              return newMessages;
            });

            // ✅ BUG FIX: Don't clear streamingChunks here - let useEffect handle it
            // The useEffect will clear chunks AFTER the cache update reflects in the messages query
            // This prevents AI responses from disappearing due to race condition
            logger.debug(`✅ [STREAMING_AI] Cache updated - waiting for useEffect to clear chunks`, {
              chunksCount: streamingChunks.length,
              timestamp: Date.now(),
            });

            // Track this message for TTS animation (ellipsis continues until TTS complete)
            // Using content (not ID) because DB refetch will change ID but content persists
            setActiveTTSContent(message.data.text);
            logger.debug('🎯 [TTS_TRACKING] Set activeTTSContent', {
              contentPreview: message.data.text.substring(0, 50),
              fullLength: message.data.text.length
            }, true);

            // Background refetch to get real DB IDs (immediate, React Query handles smooth transition)
            logger.debug('🔄 [QUERY_INVALIDATE] Invalidating messages query for background refetch', {
              sessionId: activeSessionId,
              timestamp: Date.now(),
            });
            queryClient.invalidateQueries({ queryKey: ['messages', activeSessionId] });
          }

          // AI response text is complete, now waiting for TTS audio
          logger.debug('✅ [AI_COMPLETE] Handler complete - waiting for TTS audio...');
          break;

        case 'tts_start':
          logger.debug('🔊 TTS generation started');
          break;

        case 'bot_speaking_state_changed':
          logger.debug(`🤖 Bot speaking state changed: ${message.data.is_speaking ? 'SPEAKING' : 'LISTENING'}`);
          setIsBotSpeaking(message.data.is_speaking ?? false);

          // Clear TTS animation when speaking stops (TTS playback complete)
          if (!message.data.is_speaking) {
            logger.debug('🎯 [TTS_TRACKING] Cleared activeTTSContent', {
              wasContent: activeTTSContent?.substring(0, 50)
            }, true);
            setActiveTTSContent(null);
          }
          break;

        case 'tts_complete':
          logger.debug(`✅ TTS complete (${message.data.duration_s?.toFixed(2)}s)`);
          logger.debug(`🔍 DEBUG: isSpeakerMuted=${isSpeakerMuted}, audioPlayback=${!!audioPlayback}`);
          logger.debug(`🔍 DEBUG: audioPlayback.completeAudio=${!!audioPlayback?.completeAudio}`);

          // Play buffered TTS audio if not muted
          if (!isSpeakerMuted) {
            logger.debug('🔍 DEBUG: Calling audioPlayback.completeAudio()...');
            try {
              await audioPlayback.completeAudio();
              logger.debug('🔍 DEBUG: completeAudio() returned successfully');
            } catch (error) {
              logger.error('🔍 DEBUG: completeAudio() threw error:', error);
            }
          } else {
            logger.debug('🔇 Speaker muted, discarding TTS audio');
            audioPlayback.stop();
          }
          break;

        case 'error':
          logger.error('[VoiceChat] Backend error:', message.data.message);
          toast.error('Voice Chat Error', message.data.message || 'Unknown error');
          break;

        default:
          logger.warn('[VoiceChat] Unknown message event:', message.event);
      }
      } finally {
        // Batch 3.3: Handler duration tracking and re-entrance cleanup
        isHandlingMessageRef.current = false;
        const handlerDuration = performance.now() - handlerStartTime;
        if (handlerDuration > 100) {
          logger.warn(`⚠️ [HANDLER_SLOW] WebSocket message handler took ${handlerDuration.toFixed(1)}ms (>100ms, event: ${message.event})`);
        }
      }
    },
    [activeSessionId, audioPlayback, isSpeakerMuted, queryClient, toast, setIsBotSpeaking]
  );

  // Handle binary audio chunks from TTS (web voice chat)
  const handleBinaryMessage = useCallback(
    (audioData: Uint8Array) => {
      if (!isSpeakerMuted) {
        logger.debug(`🎵 Buffering audio chunk: ${audioData.length} bytes`);
        audioPlayback.addAudioChunk(audioData);
      } else {
        logger.debug('🔇 Speaker muted, discarding audio chunk');
      }
    },
    [audioPlayback, isSpeakerMuted]
  );

  // Handle WebRTC errors (web voice chat)
  const handleAudioError = useCallback(
    (error: string) => {
      toast.error('Audio Error', error);
    },
    [toast]
  );

  // WebRTC Audio Hook (web voice chat - uses active session)
  const {
    isMuted,
    toggleMute,
    connectionState,
    permissionError,
    isRecording,
    // isPendingTTS removed - no longer used (ellipsis now controlled by activeTTSMessageId)
    endSession,    // Discord-style: Explicit "Leave Voice" button to end session
  } = useWebRTCAudio({
    sessionId: activeSessionId, // Use active session ID from conversation management
    onMessage: handleWebRTCAudioMessage,
    onBinaryMessage: handleBinaryMessage,
    onError: handleAudioError,
    onServiceError: handleServiceError, // Phase 2: Service error handling
    onRecordingStop: () => {
      // Fix #2: Clear listening state when recording stops
      setIsListening(false);
      setVoicePartialTranscript('');
      listeningStartTimeRef.current = null;
    },
    autoStart: false,
    timeslice: 100,
  });

  // Fix #2 (Enhancement): Clear listening state when WebRTC connection drops
  // Discord-style: Show toast notifications for errors only (no connection badges)
  useEffect(() => {
    if (connectionState === 'disconnected' || connectionState === 'error') {
      // Connection lost - clear any stale listening state
      setIsListening(false);
      setVoicePartialTranscript('');
      listeningStartTimeRef.current = null;

      // Show toast notification for connection errors (Discord-style: toast only, no persistent badge)
      if (connectionState === 'error') {
        toast.error('Voice connection error', 'Failed to connect to voice server. Retrying...');
      }
    }
  }, [connectionState, toast]);

  // REMOVED: 60-second timeout safety net
  // This timeout was causing issues in multi-turn conversations where users might
  // pause for more than 60 seconds between exchanges. The listening state is already
  // properly cleared by:
  // 1. final_transcript events (lines 233, 462)
  // 2. onRecordingStop callback (line 361)
  // 3. Connection state changes (lines 373-376)
  // So this timeout was redundant and harmful.

  // Handle WebSocket messages (Discord conversation monitoring - for metrics updates)
  const handleMessage = useCallback((message: any) => {
    // Log all WebSocket events for debugging (debug only)
    logger.debug('📡', 'WS EVENT', message.event, {
      event: message.event,
      sessionId: message.data?.session_id,
      textLength: message.data?.text?.length,
      userId: message.data?.userId,
    }, true);

    // VoxBridge 2.0: Handle service error events
    if (message.event === 'service_error') {
      handleServiceError(message.data as ServiceErrorEvent);
      return;
    }

    // VoxBridge 2.0: Handle agent CRUD events (real-time updates)
    if (message.event === 'agent_created' || message.event === 'agent_updated' || message.event === 'agent_deleted') {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
      return;
    }

    // Real-time metrics updates (after every conversation turn)
    if (message.event === 'metrics_updated') {
      // Invalidate metrics query to trigger refetch with new data
      queryClient.setQueryData(['metrics'], message.data);
      return;
    }

    // LLM retry notification
    if (message.event === 'llm_retry') {
      toast.info("Retrying AI Response", message.data.message);
      return;
    }

    // LLM fallback notification
    if (message.event === 'llm_fallback') {
      toast.warning("AI Response Fallback", message.data.message);
      return;
    }

    // Track speaker activity for status cards
    if (message.event === 'speaker_started') {
      setActiveSpeaker(message.data.userId);
    } else if (message.event === 'speaker_stopped') {
      setActiveSpeaker(null);
    } else if (message.event === 'partial_transcript') {
      // Update analytics partial transcript (for status cards)
      setPartialTranscript(message.data.text);

      // Start listening animation indicator (unified experience)
      if (!isListening && message.data.text) {
        logger.debug('🎤', 'LISTENING', `Started (partial: "${message.data.text?.substring(0, 30)}...")`, undefined, true);
        setIsListening(true);
        listeningStartTimeRef.current = Date.now();
      }
      setVoicePartialTranscript(message.data.text);
    } else if (message.event === 'final_transcript') {
      logger.debug('🎤', 'LISTENING', `Stopped (final: "${message.data.text?.substring(0, 50)}...")`, undefined, true);

      // Clear analytics state
      setActiveSpeaker(null);
      setPartialTranscript('');

      // Stop listening, start AI generating animation (unified experience)
      setIsListening(false);
      listeningStartTimeRef.current = null;
      setVoicePartialTranscript('');

      logger.debug('💭', 'THINKING', `Started (session: ${activeSessionId})`, undefined, true);
      setIsVoiceAIGenerating(true);
      aiStartTimeRef.current = Date.now();

      // Backend already saved Discord user message - frontend only updates UI
      // (Removed duplicate save - backend is single source of truth)

      // Refresh message list to show backend-saved message
      if (activeSessionId) {
        logger.debug('🔄', 'QUERY', `Invalidating messages query (session: ${activeSessionId})`, undefined, true);
        queryClient.invalidateQueries({ queryKey: ['messages', activeSessionId] });
      }
    } else if (message.event === 'ai_response_chunk') {
      // Discord AI response chunks - no action needed
      // Backend saves chunks to database, frontend just waits for ai_response_complete
    } else if (message.event === 'ai_response_complete') {
      const aiDuration = aiStartTimeRef.current ? Date.now() - aiStartTimeRef.current : 0;
      logger.debug('💭', 'THINKING', `Complete (duration: ${aiDuration}ms)`, undefined, true);

      // Stop AI generating animation (unified experience)
      setIsVoiceAIGenerating(false);
      aiStartTimeRef.current = null;
      setAiGeneratingDuration(0);

      // Check for errors
      if (message.data.error) {
        logger.error('[Discord] LLM error:', message.data.error);
        // Show error toast to user
        toast.error("AI Response Error", message.data.error);
      }

      // Refresh message list to show backend-saved message
      // No optimistic updates to remove - just fetch from database
      if (activeSessionId) {
        logger.debug('🔄', 'QUERY', `Invalidating messages query (session: ${activeSessionId})`, undefined, true);
        queryClient.invalidateQueries({ queryKey: ['messages', activeSessionId] });
      }

      // Refetch metrics after AI response completes
      queryClient.invalidateQueries({ queryKey: ['metrics'] });
    } else if (message.event === 'ai_response' && message.data.isFinal) {
      // Legacy event handler - refetch metrics after AI response completes
      queryClient.invalidateQueries({ queryKey: ['metrics'] });
    }
  }, [queryClient, handleServiceError, activeSessionId]);

  // WebSocket for real-time updates (Discord conversation monitoring)
  const { isConnected: wsConnected } = useWebSocket('/ws/events', {
    onMessage: handleMessage
  });

  // Component lifecycle logging
  useEffect(() => {
    logger.debug('🚀', 'COMPONENT', 'VoxbridgePage mounted');
    return () => {
      logger.debug('💥', 'COMPONENT', 'VoxbridgePage unmounting');
    };
  }, []);

  // Auto-select first session on INITIAL load only (not on every sessions update)
  // ✅ FIX: Only run when activeSessionId is null AND we have sessions
  //         Don't re-run when sessions array updates during active conversation
  //         (which was causing WebSocket disconnects mid-conversation)
  useEffect(() => {
    // Only auto-select if we have no active session yet
    if (sessions.length > 0 && activeSessionId === null) {
      logger.debug('📋 Auto-selecting first session:', sessions[0].id);
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions.length, activeSessionId]); // Only trigger when length changes or activeSessionId becomes null

  // Fetch speaker lock status when agent has Discord plugin
  useEffect(() => {
    if (!activeAgent?.plugins?.discord?.enabled) {
      // Reset speaker lock state if no Discord plugin
      setSpeakerLocked(false);
      return;
    }

    // Fetch status immediately
    const fetchSpeakerStatus = async () => {
      try {
        const statusData = await api.getStatus();
        setSpeakerLocked(statusData.speaker?.locked || false);
      } catch (error) {
        logger.error('[VoxBridge] Failed to fetch speaker status:', error);
      }
    };

    fetchSpeakerStatus();

    // Poll every 3 seconds while agent has Discord plugin
    const interval = setInterval(fetchSpeakerStatus, 3000);
    return () => clearInterval(interval);
  }, [activeAgent]);

  // Fetch Discord voice connection status when agent has Discord plugin
  useEffect(() => {
    if (!activeAgent?.plugins?.discord?.enabled) {
      // Reset Discord voice state if no Discord plugin
      setDiscordBotReady(false);
      setDiscordInVoice(false);
      setDiscordChannelName(null);
      setDiscordGuildName(null);
      setDiscordGuildId(null);
      return;
    }

    // Initialize guild ID from localStorage (persists across reloads)
    const storedGuildId = localStorage.getItem(`discord_guild_${activeAgent.id}`);
    if (storedGuildId) {
      setDiscordGuildId(storedGuildId);
    }

    const fetchDiscordStatus = async () => {
      try {
        const status = await api.getAgentDiscordStatus(activeAgent.id);
        const connection = status.connections && status.connections.length > 0 ? status.connections[0] : null;

        logger.debug('[VoxbridgePage] Discord status update:', {
          bot_ready: status.bot?.ready,
          connections_count: status.connections?.length,
          connection_connected: connection?.connected,
          channel_name: connection?.channel_name,
          guild_name: connection?.guild_name,
          full_status: status,
        });

        const botReady = status.bot?.ready || false;
        const inVoice = connection?.connected || false;
        const channelName = connection?.channel_name || null;
        const guildName = connection?.guild_name || null;

        logger.debug('[VoxbridgePage] Setting state:', { botReady, inVoice, channelName, guildName });

        setDiscordBotReady(botReady);
        setDiscordInVoice(inVoice);
        setDiscordChannelName(channelName);
        setDiscordGuildName(guildName);

        // Backend now returns guild_id as string to preserve precision
        // Store it to localStorage if we don't have one yet
        const storedId = localStorage.getItem(`discord_guild_${activeAgent.id}`);
        if (!storedId && connection?.guild_id) {
          const guildIdStr = String(connection.guild_id);
          setDiscordGuildId(guildIdStr);
          localStorage.setItem(`discord_guild_${activeAgent.id}`, guildIdStr);
        } else if (storedId) {
          setDiscordGuildId(storedId);
        }
      } catch (error) {
        logger.error('[VoxbridgePage] Failed to fetch Discord status:', error);
        setDiscordBotReady(false);
        setDiscordInVoice(false);
      }
    };

    fetchDiscordStatus();

    // Poll every 3 seconds while agent has Discord plugin
    const interval = setInterval(fetchDiscordStatus, 3000);
    return () => clearInterval(interval);
  }, [activeAgent]);

  // Update AI generating duration (web voice chat)
  useEffect(() => {
    if (isVoiceAIGenerating && aiStartTimeRef.current) {
      const interval = setInterval(() => {
        setAiGeneratingDuration(Date.now() - aiStartTimeRef.current!);
      }, 100);
      return () => clearInterval(interval);
    }
  }, [isVoiceAIGenerating]);

  // Clear pending user transcript when switching sessions
  useEffect(() => {
    setPendingUserTranscript(null);
  }, [activeSessionId]);

  // Batch 3.3: 10s timeout for pending transcript placeholder (safety net)
  useEffect(() => {
    if (!pendingUserTranscript) return;

    const timeoutId = setTimeout(() => {
      logger.warn(`⚠️ [PENDING_TIMEOUT] Pending user transcript not cleared after 10s - forcing clear`);
      logger.warn(`   - Text: "${pendingUserTranscript.text.substring(0, 50)}..."`);
      logger.warn(`   - isFinalizing: ${pendingUserTranscript.isFinalizing}`);
      setPendingUserTranscript(null);
    }, 10000); // 10 seconds

    return () => clearTimeout(timeoutId);
  }, [pendingUserTranscript]);

  // ✅ Cleanup useEffect removed - optimistic UI pattern handles transition directly in ai_response_complete

  // Conversation Management Handlers

  // Handle create conversation
  const handleCreateConversation = useCallback(
    async (agentId: string, title?: string) => {
      try {
        // Step 1: Deactivate all current sessions (Discord-style: only one active at a time)
        if (sessions.length > 0) {
          logger.debug(`🔄 Deactivating ${sessions.length} existing sessions`);
          await Promise.all(
            sessions.map((session) =>
              api.updateSession(session.id, { active: false }).catch((err) => {
                logger.warn(`⚠️  Failed to deactivate session ${session.id}:`, err);
              })
            )
          );
        }

        // Step 2: Create new session (will be active=true by default)
        const newSession = await api.createSession({
          user_id: WEB_USER_ID,
          agent_id: agentId,
          title: title || null,
          session_type: 'web',
        });

        logger.info(`✅ Created new session ${newSession.id}, deactivated ${sessions.length} old sessions`);

        // Step 3: Refetch sessions and select new one
        await refetchSessions();
        setActiveSessionId(newSession.id);

        // Step 4: WebSocket auto-connects via useEffect[sessionId] in useWebRTCAudio (Discord-style)
        // No manual startSession() needed - React will trigger connection when activeSessionId updates

        toast.success('Conversation created', `Started new conversation with agent`);
      } catch (error) {
        toast.error('Failed to create conversation', error instanceof Error ? error.message : 'Unknown error');
        throw error;
      }
    },
    [sessions, refetchSessions, toast]
  );

  // Handle delete conversation
  const handleDeleteSession = useCallback(
    async (sessionId: string) => {
      if (!confirm('Delete this conversation? This cannot be undone.')) {
        return;
      }

      try {
        await api.deleteSession(sessionId);

        // If we deleted the active session, select another
        if (sessionId === activeSessionId) {
          const remainingSessions = sessions.filter((s) => s.id !== sessionId);
          setActiveSessionId(remainingSessions.length > 0 ? remainingSessions[0].id : null);
        }

        await refetchSessions();
        toast.success('Conversation deleted');
      } catch (error) {
        toast.error('Failed to delete conversation', error instanceof Error ? error.message : 'Unknown error');
      }
    },
    [activeSessionId, sessions, refetchSessions, toast]
  );

  // Handle select session (Discord-style: voice follows selected conversation)
  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      try {
        // Step 1: Deactivate currently active session (if any)
        const currentlyActive = sessions.find((s) => s.active);
        if (currentlyActive && currentlyActive.id !== sessionId) {
          logger.debug(`🔄 Deactivating previous session ${currentlyActive.id}`);
          await api.updateSession(currentlyActive.id, { active: false }).catch((err) => {
            logger.warn(`⚠️  Failed to deactivate session ${currentlyActive.id}:`, err);
          });
        }

        // Step 2: Activate the newly selected session
        logger.debug(`✅ Activating selected session ${sessionId}`);
        await api.updateSession(sessionId, { active: true }).catch((err) => {
          logger.warn(`⚠️  Failed to activate session ${sessionId}:`, err);
        });

        // Step 3: Update UI state (triggers useEffect[sessionId] which auto-connects WebSocket)
        setActiveSessionId(sessionId);

        // Step 4: WebSocket auto-connects or switches via useEffect[sessionId] in useWebRTCAudio
        // Discord-style: Voice follows selected conversation automatically
        logger.info(`🔄 Switched to conversation ${sessionId} (voice follows selected conversation)`);

        // Step 5: Refetch sessions to update UI badges
        await refetchSessions();
      } catch (error) {
        logger.error('❌ Failed to switch conversation:', error);
        toast.error('Failed to switch conversation', error instanceof Error ? error.message : 'Unknown error');
      }
    },
    [sessions, refetchSessions, toast]
  );

  // Handle unlock speaker
  const handleUnlockSpeaker = useCallback(async () => {
    setIsUnlocking(true);
    try {
      const result = await api.unlockSpeaker();
      setSpeakerLocked(false);
      toast.success('Speaker unlocked', result.previousSpeaker ? `Unlocked ${result.previousSpeaker}` : undefined);
    } catch (error) {
      toast.error('Failed to unlock speaker', error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setIsUnlocking(false);
    }
  }, [toast]);

  // Helper to get stored guild ID (avoids precision loss from status endpoint)
  const getStoredGuildId = useCallback(() => {
    if (!activeAgent) return null;
    try {
      return localStorage.getItem(`discord_guild_${activeAgent.id}`);
    } catch {
      return null;
    }
  }, [activeAgent]);

  // Handle join Discord voice channel
  const handleJoinVoice = useCallback(() => {
    setShowChannelSelector(true);
  }, []);

  // Handle channel selected
  const handleChannelSelected = useCallback(async (guildId: string, channelId: string) => {
    if (!activeAgent) return;

    setIsJoiningLeaving(true);
    try {
      // Phase 6.X: Pass activeSessionId for unified conversation threading
      // If user has active conversation, Discord voice will link to it
      await api.joinChannel(activeAgent.id, channelId, guildId, activeSessionId);
      // Store guild ID locally to avoid precision loss from status endpoint
      setDiscordGuildId(guildId);
      localStorage.setItem(`discord_guild_${activeAgent.id}`, guildId);

      // Show appropriate toast message
      if (activeSessionId) {
        toast.success('Joined voice channel (linked to active conversation)');
      } else {
        toast.success('Joined voice channel');
      }
      setShowChannelSelector(false);
    } catch (error: any) {
      logger.error('[VoxbridgePage] Failed to join voice:', error);

      // If already connected, try to force leave first then retry
      if (error?.message?.includes('Already connected')) {
        try {
          logger.debug('Already connected detected, forcing leave and retry...');
          await api.leaveChannel(activeAgent.id, guildId);
          await api.joinChannel(activeAgent.id, channelId, guildId, activeSessionId);
          setDiscordGuildId(guildId);
          localStorage.setItem(`discord_guild_${activeAgent.id}`, guildId);
          toast.success('Reconnected to voice channel');
          setShowChannelSelector(false);
          return;
        } catch (retryError) {
          toast.error('Failed to reconnect', retryError instanceof Error ? retryError.message : 'Unknown error');
        }
      } else {
        toast.error('Failed to join voice channel', error instanceof Error ? error.message : 'Unknown error');
      }
    } finally {
      setIsJoiningLeaving(false);
    }
  }, [activeAgent, activeSessionId, toast]);

  // Handle leave Discord voice channel
  const handleLeaveVoice = useCallback(async () => {
    if (!activeAgent) {
      toast.error('Cannot leave voice', 'No active agent');
      return;
    }

    // Use locally stored guild ID to avoid precision loss from status endpoint
    const guildIdToUse = getStoredGuildId() || discordGuildId;

    if (!guildIdToUse) {
      toast.error('Cannot leave voice', 'No guild ID available');
      return;
    }

    logger.debug(`[VoxbridgePage] Leaving voice with guild ID: ${guildIdToUse}`);

    setIsJoiningLeaving(true);
    try {
      await api.leaveChannel(activeAgent.id, guildIdToUse);
      // Clear stored guild ID after leaving
      setDiscordGuildId(null);
      localStorage.removeItem(`discord_guild_${activeAgent.id}`);
      toast.success('Left voice channel');
    } catch (error) {
      toast.error('Failed to leave voice channel', error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setIsJoiningLeaving(false);
    }
  }, [activeAgent, discordGuildId, getStoredGuildId, toast]);

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success('Copied!', 'Text copied to clipboard');
    } catch (err) {
      logger.error('Failed to copy:', err);
      toast.error('Copy failed', err instanceof Error ? err.message : 'Unknown error');
    }
  };

  const shortenUrl = (url: string, maxLength: number = 35) => {
    if (url.length <= maxLength) return url;
    const start = url.substring(0, maxLength - 3);
    return `${start}...`;
  };

  // Format timestamp for messages
  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  // Status helper functions for dynamic service status displays
  const getWhisperXStatus = () => {
    if (!status?.whisperx.serverConfigured) {
      return {
        color: 'text-red-600 dark:text-red-400',
        icon: <XCircle className="w-4 h-4" />,
        text: 'Not Configured',
        info: 'No server URL set'
      };
    }
    if (activeSpeaker && partialTranscript) {
      return {
        color: 'text-blue-600 dark:text-blue-400',
        icon: <Activity className="w-4 h-4 animate-pulse" />,
        text: 'Processing',
        info: 'Transcribing speech'
      };
    }
    return {
      color: 'text-green-600 dark:text-green-400',
      icon: <CircleCheckBig className="w-4 h-4" />,
      text: 'Ready',
      info: status?.devices?.whisperx || 'STT available'
    };
  };

  const getChatterboxStatus = () => {
    if (!status?.services.chatterbox) {
      return {
        color: 'text-red-600 dark:text-red-400',
        icon: <XCircle className="w-4 h-4" />,
        text: 'Offline',
        info: 'Service not responding'
      };
    }
    return {
      color: 'text-green-600 dark:text-green-400',
      icon: <CircleCheckBig className="w-4 h-4" />,
      text: 'Ready',
      info: status?.devices?.chatterbox || 'TTS available'
    };
  };

  const getN8nStatus = () => {
    if (!status?.services.n8nWebhook) {
      return {
        color: 'text-red-600 dark:text-red-400',
        icon: <XCircle className="w-4 h-4" />,
        text: 'Not Set',
        info: 'No webhook configured'
      };
    }
    return {
      color: 'text-green-600 dark:text-green-400',
      icon: <CircleCheckBig className="w-4 h-4" />,
      text: 'Configured',
      info: 'Webhook ready'
    };
  };

  return (
    <div className="min-h-screen bg-page-background p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* ============================================ */}
        {/* ANALYTICS SECTION (TOP) */}
        {/* ============================================ */}

        {/* Header */}
        <div className="text-center relative">
          <h1 className="text-4xl font-bold">VoxBridge Dashboard</h1>
          <p className="text-muted-foreground mt-1">
            Real-time voice bridge monitoring and control
          </p>

          {/* Absolutely positioned settings button */}
          <div className="absolute right-0 sm:right-4 top-12">
            <RuntimeSettings />
          </div>
        </div>

        {/* Summary Statistics */}
        <StatusSummary
          metrics={metrics}
          isLoadingMetrics={isLoadingMetrics}
          wsConnected={wsConnected}
        />

        {/* Show/Hide Stats Button */}
        <div className="flex justify-center">
          <button
            onClick={() => setShowStatistics(!showStatistics)}
            className="px-3 py-1 text-xs bg-primary/10 hover:bg-primary/20 text-primary rounded-full transition-colors duration-300"
          >
            {showStatistics ? 'Hide Stats' : 'Show Stats'}
          </button>
        </div>

        {/* Metrics Panel (Conditional) */}
        {showStatistics && <MetricsPanel />}

        {/* Service Status Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">WhisperX</CardTitle>
            </CardHeader>
            <CardContent>
              {(() => {
                const statusInfo = getWhisperXStatus();
                return (
                  <>
                    <div className={`flex items-center gap-2 text-sm font-semibold ${statusInfo.color}`}>
                      {statusInfo.icon}
                      <span>{statusInfo.text}</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {statusInfo.info}
                    </p>
                    {status?.whisperx.serverUrl && (
                      <div className="flex items-center gap-1 mt-1">
                        <p className="text-xs text-muted-foreground truncate flex-1" title={status.whisperx.serverUrl}>
                          {shortenUrl(status.whisperx.serverUrl)}
                        </p>
                        <button
                          onClick={() => copyToClipboard(status.whisperx.serverUrl)}
                          className="p-1 hover:bg-muted rounded"
                          title="Copy URL"
                        >
                          <Copy className="w-3 h-3" />
                        </button>
                      </div>
                    )}
                  </>
                );
              })()}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Chatterbox TTS</CardTitle>
            </CardHeader>
            <CardContent>
              {(() => {
                const statusInfo = getChatterboxStatus();
                return (
                  <>
                    <div className={`flex items-center gap-2 text-sm font-semibold ${statusInfo.color}`}>
                      {statusInfo.icon}
                      <span>{statusInfo.text}</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {statusInfo.info}
                    </p>
                    {status?.services.chatterboxUrl && (
                      <div className="flex items-center gap-1 mt-1">
                        <p className="text-xs text-muted-foreground truncate flex-1" title={status.services.chatterboxUrl}>
                          {shortenUrl(status.services.chatterboxUrl)}
                        </p>
                        <button
                          onClick={() => copyToClipboard(status.services.chatterboxUrl)}
                          className="p-1 hover:bg-muted rounded"
                          title="Copy URL"
                        >
                          <Copy className="w-3 h-3" />
                        </button>
                      </div>
                    )}
                  </>
                );
              })()}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">n8n Webhook</CardTitle>
            </CardHeader>
            <CardContent>
              {(() => {
                const statusInfo = getN8nStatus();
                return (
                  <>
                    <div className={`flex items-center gap-2 text-sm font-semibold ${statusInfo.color}`}>
                      {statusInfo.icon}
                      <span>{statusInfo.text}</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {statusInfo.info}
                    </p>
                    {status?.services.n8nWebhookUrl && (
                      <div className="flex items-center gap-1 mt-1">
                        <p className="text-xs text-muted-foreground truncate flex-1" title={status.services.n8nWebhookUrl}>
                          {shortenUrl(status.services.n8nWebhookUrl)}
                        </p>
                        <button
                          onClick={() => copyToClipboard(status.services.n8nWebhookUrl)}
                          className="p-1 hover:bg-muted rounded"
                          title="Copy URL"
                        >
                          <Copy className="w-3 h-3" />
                        </button>
                      </div>
                    )}
                  </>
                );
              })()}
            </CardContent>
          </Card>
        </div>

        {/* ============================================ */}
        {/* UNIFIED CONVERSATION INTERFACE (BOTTOM) */}
        {/* ============================================ */}

        <Card className="flex flex-col h-[600px]">
          <CardContent className="flex flex-1 min-h-0 p-0">
            {/* Sidebar - Conversation List */}
            <div
              className={cn(
                'transition-all duration-300 border-r border-border overflow-hidden',
                sidebarOpen ? 'w-80' : 'w-0'
              )}
            >
              {sidebarOpen && (
                <ConversationList
                  sessions={sessions}
                  activeSessionId={activeSessionId}
                  onSelectSession={handleSelectSession}
                  onCreateSession={() => setNewConversationDialogOpen(true)}
                  onDeleteSession={handleDeleteSession}
                  isLoading={isLoadingSessions}
                  connectionState={connectionState}
                  onLeaveVoice={endSession}
                />
              )}
            </div>

            {/* Main Conversation View */}
            <div className="flex-1 flex flex-col min-w-0">
              {/* Conversation Header */}
              <div className="h-16 border-b border-border flex items-center justify-between px-6 shrink-0">
                <div className="flex items-center gap-4">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setSidebarOpen(!sidebarOpen)}
                    title={sidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
                  >
                    <Menu className="h-5 w-5" />
                  </Button>

                  {activeSession && activeAgent ? (
                    <div className="flex items-center gap-3">
                      <Brain className="h-5 w-5 text-primary" />
                      <div>
                        <h2 className="text-sm font-semibold">
                          {activeSession.title || `Conversation ${new Date(activeSession.started_at).toLocaleDateString()}`}
                        </h2>
                        <p className="text-xs text-muted-foreground">
                          {activeAgent.name} • {activeAgent.llm_model}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center gap-3">
                      <MessageSquare className="h-5 w-5 text-muted-foreground" />
                      <div>
                        <h2 className="text-sm font-semibold">No Conversation Selected</h2>
                        <p className="text-xs text-muted-foreground">Create or select a conversation</p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Audio Controls (WebRTC) */}
                <div className="flex items-center gap-4">
                  {activeSessionId && (
                    <div className="flex items-center gap-2">
                      {/* Debug logging for mic button investigation */}
                      {(() => {
                        logger.debug('[AudioControls Debug]', {
                          isMuted,
                          connectionState,
                          permissionError,
                          isRecording,
                        });
                        return null;
                      })()}
                      <AudioControls
                        isMuted={isMuted}
                        onToggleMute={toggleMute}
                        permissionError={permissionError}
                        isRecording={isRecording}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setIsSpeakerMuted(!isSpeakerMuted)}
                        title={isSpeakerMuted ? 'Unmute speaker' : 'Mute speaker'}
                      >
                        {isSpeakerMuted ? (
                          <VolumeX className="h-5 w-5 text-muted-foreground" />
                        ) : (
                          <Volume2 className="h-5 w-5" />
                        )}
                      </Button>
                      {/* REMOVED: Bot speaking indicators now shown as ellipsis in message bubble */}
                    </div>
                  )}
                </div>
              </div>

              {/* Discord Status Bar (Plugin Only) - Two-Row Layout */}
              {activeAgent?.plugins?.discord?.enabled && (
                <div className="border-b border-border bg-muted/30 px-6 py-3 shrink-0">
                  <div className="flex flex-col gap-3">
                    {/* Row 1: Bot Status */}
                    <div className="flex items-center justify-between">
                      {/* Left: Title + Icon */}
                      <div className="flex items-center gap-2">
                        <MessageSquare className="h-4 w-4 text-purple-400" />
                        <span className="text-sm font-medium">Discord Bot Plugin</span>
                      </div>

                      {/* Right: Connection Status Badge */}
                      {discordBotReady ? (
                        <Badge variant="outline" className="text-xs bg-green-500/20 text-green-400 border-green-500/50">
                          <span className="inline-block h-2 w-2 rounded-full bg-green-500 mr-1.5" />
                          Connected
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs bg-red-500/20 text-red-400 border-red-500/50">
                          <span className="inline-block h-2 w-2 rounded-full border-2 border-red-500 mr-1.5" />
                          Not Ready
                        </Badge>
                      )}
                    </div>

                    {/* Row 2: Location & Session Status + Actions */}
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      {/* Left: Location & Session Badges */}
                      {discordInVoice ? (
                        <div className="flex items-center gap-2 flex-wrap">
                          {/* Guild/Server Badge with text */}
                          <Badge variant="outline" className="text-xs bg-purple-500/20 text-purple-400 border-purple-500/50">
                            <Server className="h-3 w-3 mr-1" />
                            {discordGuildName}
                          </Badge>

                          {/* Voice Channel Badge with text */}
                          <Badge variant="outline" className="text-xs bg-blue-500/20 text-blue-400 border-blue-500/50">
                            <Volume2 className="h-3 w-3 mr-1" />
                            {discordChannelName}
                          </Badge>

                          {/* Linked Status Badge with text (conditional) */}
                          {activeSessionId && (
                            <Badge variant="outline" className="text-xs bg-green-500/20 text-green-400 border-green-500/50">
                              <Link className="h-3 w-3 mr-1" />
                              Linked
                            </Badge>
                          )}
                        </div>
                      ) : (
                        <Badge variant="outline" className="text-xs bg-muted text-muted-foreground">
                          Not in voice
                        </Badge>
                      )}

                      {/* Right: Action Buttons */}
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* Join/Leave Voice Channel */}
                        {!discordInVoice ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleJoinVoice}
                            disabled={isJoiningLeaving}
                          >
                            {isJoiningLeaving ? (
                              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                              <LogIn className="h-4 w-4 mr-2" />
                            )}
                            Join Voice
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={handleLeaveVoice}
                            disabled={isJoiningLeaving}
                          >
                            {isJoiningLeaving ? (
                              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                              <LogOut className="h-4 w-4 mr-2" />
                            )}
                            Leave Voice
                          </Button>
                        )}

                        {/* Speaker Lock */}
                        {speakerLocked && (
                          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-background border border-border">
                            <Lock className="h-4 w-4 text-yellow-400" />
                            <span className="text-xs font-medium">Locked:</span>
                            <Badge variant="outline" className="text-xs bg-yellow-500/20 text-yellow-400 border-yellow-500/50">
                              {activeSpeaker || 'Unknown'}
                            </Badge>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={handleUnlockSpeaker}
                              disabled={isUnlocking}
                              className="h-6 px-2 text-xs"
                            >
                              {isUnlocking ? (
                                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                              ) : (
                                <Unlock className="h-3 w-3 mr-1" />
                              )}
                              Unlock
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Messages Area */}
              <div className="flex-1 overflow-hidden">
                {!activeSessionId ? (
                  <div className="h-full flex items-center justify-center text-center text-muted-foreground p-8">
                    <div>
                      <MessageSquare className="h-16 w-16 mx-auto mb-4 opacity-50" />
                      <h3 className="text-lg font-semibold mb-2">No conversation selected</h3>
                      <p className="text-sm mb-4">Start a new conversation to begin</p>
                      <Button onClick={() => setNewConversationDialogOpen(true)}>
                        New Conversation
                      </Button>
                    </div>
                  </div>
                ) : (
                  <ScrollArea className="h-full" ref={scrollAreaRef}>
                    <div className="max-w-4xl mx-auto p-6 space-y-4">
                      {/* Permission Error */}
                      {permissionError && (
                        <div className="flex items-start gap-3 p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
                          <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-red-500 mb-1">Microphone Permission Required</p>
                            <p className="text-xs text-muted-foreground">{permissionError}</p>
                          </div>
                        </div>
                      )}

                      {/* AI Generating Indicator */}
                      {isVoiceAIGenerating && (
                        <AIGeneratingIndicator
                          isGenerating={isVoiceAIGenerating}
                          duration={aiGeneratingDuration}
                        />
                      )}

                      {/* Discord-style: No "ready" indicator - system is always ready for next input */}

                      {/* Messages (Database + Optimistic Streaming) */}
                      {isLoadingMessages ? (
                        <div className="text-center py-12 text-muted-foreground">
                          <p className="text-sm">Loading messages...</p>
                        </div>
                      ) : displayMessages.length === 0 && !voicePartialTranscript && !isListening ? (
                        <div className="text-center py-12 text-muted-foreground">
                          <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-50" />
                          <p className="text-sm">No messages yet</p>
                          <p className="text-xs mt-1">Start speaking to begin the conversation</p>
                        </div>
                      ) : (
                        <>
                          {displayMessages.slice().reverse().map((message) => {
                            // Calculate React key for this message
                            // BUG FIX #1: Stable keys across state transitions (prevents remounting/disappearing)
                            const reactKey = message.role === 'user'
                              ? `user-${(message as any).isPending || (message as any).isFinalizing
                                  ? 'pending'
                                  : message.id}`
                              : `assistant-${(message as any).isStreaming
                                  ? 'streaming'
                                  : message.id}`;

                            // BUG FIX #3: Removed render debug logs (was causing 10+ logs per frame)

                            return (
                            <div
                              key={reactKey}
                              className={cn(
                                'flex',
                                message.role === 'user' ? 'justify-start' : 'justify-end'
                              )}
                            >
                              <div
                                className={cn(
                                  'max-w-[80%] p-4 rounded-lg',
                                  message.role === 'user'
                                    ? 'bg-primary/10 border border-primary/20'
                                    : 'bg-purple-500/10 border border-purple-500/20'
                                )}
                              >
                                <div className="flex items-center justify-between mb-2 gap-3">
                                  <span
                                    className={cn(
                                      'text-xs font-medium',
                                      message.role === 'user' ? 'text-primary' : 'text-purple-400'
                                    )}
                                  >
                                    {message.role === 'user' ? 'You' : activeAgent?.name || 'AI Assistant'}
                                  </span>
                                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                                    {formatTimestamp(message.timestamp)}
                                  </span>
                                </div>
                                {/* User message: Show streaming/finalizing state (dots + text) */}
                                {/* BUG FIX #4: Merge streaming and finalizing - seamless visual transition */}
                                {message.role === 'user' && ((message as any).isStreaming || (message as any).isFinalizing) && (
                                  <div className="flex items-center gap-2">
                                    <BouncingDots size="sm" className="text-primary/60" />
                                    <p className="text-sm whitespace-pre-line leading-relaxed opacity-75">
                                      {message.content || 'Listening...'}
                                    </p>
                                  </div>
                                )}

                                {/* User message: Show final content (normal state) */}
                                {message.role === 'user' && !(message as any).isStreaming && !(message as any).isFinalizing && (
                                  <p className="text-sm whitespace-pre-line leading-relaxed">
                                    {message.content}
                                  </p>
                                )}

                                {/* Assistant message: Show streaming state with dots (BUG FIX #2) */}
                                {message.role === 'assistant' && (message as any).isStreaming && (
                                  <div className="flex items-center gap-2">
                                    <BouncingDots size="sm" className="text-purple-400/60" />
                                    <p className="text-sm whitespace-pre-line leading-relaxed opacity-75">
                                      {message.content || 'Generating...'}
                                    </p>
                                  </div>
                                )}

                                {/* Assistant message: Show final content */}
                                {message.role === 'assistant' && !(message as any).isStreaming && (
                                  <p className="text-sm whitespace-pre-line leading-relaxed">
                                    {message.content}
                                  </p>
                                )}

                                {/* AI Speaking Indicator - Show bouncing dots while TTS is active */}
                                {message.role === 'assistant' && message.content === activeTTSContent && (
                                  <div className="mt-2">
                                    <BouncingDots size="sm" className="text-purple-400/60" />
                                  </div>
                                )}

                                {/* Latency info (if available) */}
                                {(message.llm_latency_ms || message.tts_duration_ms || message.total_latency_ms) && (
                                  <div className="mt-2 pt-2 border-t border-border/50 flex flex-wrap gap-3 text-xs text-muted-foreground">
                                    {message.llm_latency_ms && (
                                      <span>LLM: {message.llm_latency_ms}ms</span>
                                    )}
                                    {message.tts_duration_ms && (
                                      <span>TTS: {message.tts_duration_ms}ms</span>
                                    )}
                                    {message.total_latency_ms && (
                                      <span>Total: {message.total_latency_ms}ms</span>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                            );
                          })}
                        </>
                      )}
                    </div>
                  </ScrollArea>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* New Conversation Dialog */}
        <NewConversationDialog
          open={newConversationDialogOpen}
          onOpenChange={setNewConversationDialogOpen}
          agents={agents}
          isLoadingAgents={isLoadingAgents}
          onCreateConversation={handleCreateConversation}
        />

        {/* Channel Selector Modal */}
        <ChannelSelectorModal
          open={showChannelSelector}
          onOpenChange={setShowChannelSelector}
          onSelect={handleChannelSelected}
          currentGuildId={undefined}
          currentChannelId={undefined}
        />
      </div>
    </div>
  );
}
