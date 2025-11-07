/**
 * VoxBridge Main Dashboard Page
 * Analytics at TOP, Unified Conversation Interface at BOTTOM
 * VoxBridge 2.0 - Proper conversation management integration
 */

import { useState, useRef, useCallback, useEffect } from 'react';
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
import { STTWaitingIndicator } from '@/components/STTWaitingIndicator';
import { AIGeneratingIndicator } from '@/components/AIGeneratingIndicator';
import { StreamingMessageDisplay } from '@/components/StreamingMessageDisplay';
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

// Use for creating new web sessions (can be changed when auth is added)
const WEB_USER_ID = 'web_user_default';

// ============================================================
// LOGGING UTILITIES FOR UI/UX DEBUGGING
// ============================================================
const DEBUG_LOGGING = false; // Set to true to enable verbose logging

const logTimestamp = () => new Date().toISOString();

const logUIEvent = (emoji: string, category: string, message: string, data?: any, isDebug = false) => {
  // Skip debug logs unless explicitly enabled
  if (isDebug && !DEBUG_LOGGING) return;

  const timestamp = logTimestamp();
  if (data) {
    console.log(`[${timestamp}] ${emoji} ${category}: ${message}`, data);
  } else {
    console.log(`[${timestamp}] ${emoji} ${category}: ${message}`);
  }
};

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
  const [listeningDuration, setListeningDuration] = useState(0);
  const [isVoiceAIGenerating, setIsVoiceAIGenerating] = useState(false);
  const [aiGeneratingDuration, setAiGeneratingDuration] = useState(0);
  const [streamingChunks, setStreamingChunks] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isSpeakerMuted, setIsSpeakerMuted] = useState(false);
  const [voicePartialTranscript, setVoicePartialTranscript] = useState<string>('');
  const [isBotSpeaking, setIsBotSpeaking] = useState(false);  // Bot speaking state (blocks input during TTS)

  const queryClient = useQueryClient();
  const toast = useToastHelpers();
  const listeningStartTimeRef = useRef<number | null>(null);
  const aiStartTimeRef = useRef<number | null>(null);
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
  const { data: messages = [], isLoading: isLoadingMessages } = useQuery<Message[]>({
    queryKey: ['messages', activeSessionId],
    queryFn: async () => {
      if (!activeSessionId) return [];

      // DIAGNOSTIC: Log fetch start
      const fetchStart = Date.now();
      console.log(`[QUERY] Starting message fetch at ${fetchStart} for session ${activeSessionId}`);

      const result = await api.getSessionMessages(activeSessionId);

      // DIAGNOSTIC: Log fetch complete
      const fetchEnd = Date.now();
      const fetchDuration = fetchEnd - fetchStart;
      console.log(`[QUERY] Fetch complete in ${fetchDuration}ms, received ${result.length} messages`);

      // Log database fetch results (debug only)
      logUIEvent('📥', 'QUERY', `Fetched ${result.length} messages from database (session: ${activeSessionId})`, undefined, true);
      result.forEach((m, i) => {
        if (m.role === 'assistant') {
          logUIEvent('  ', '  ', `- DB message[${i}]: id=${m.id}, role=${m.role}, length=${m.content.length} chars`, undefined, true);
        }
      });

      // DIAGNOSTIC: Check for duplicates
      const assistantMessages = result.filter(m => m.role === 'assistant');
      if (assistantMessages.length > 1) {
        console.warn(`[QUERY] ⚠️ Received ${assistantMessages.length} assistant messages from database!`);
        assistantMessages.forEach((m, i) => {
          console.warn(`  - Assistant[${i}]: id=${m.id}, length=${m.content.length} chars, timestamp=${m.timestamp}`);
        });
      }

      return result;
    },
    enabled: !!activeSessionId,
    refetchInterval: 30000, // Poll every 30 seconds to catch any drift (WebSocket provides real-time updates)
  });

  // Get active session details
  const activeSession = sessions.find((s) => s.id === activeSessionId);

  // Get agent for active session
  const activeAgent = agents.find((a) => a.id === activeSession?.agent_id);

  // Audio playback hook for TTS (web voice chat)
  const audioPlayback = useAudioPlayback({
    autoPlay: true,
    onPlaybackStart: () => console.log('🔊 Playing TTS audio'),
    onPlaybackEnd: () => console.log('✅ TTS playback complete'),
    onError: (error) => toast.error('Audio playback failed', error),
  });

  // Handle WebRTC audio messages (web voice chat with database persistence)
  const handleWebRTCAudioMessage = useCallback(
    async (message: WebRTCAudioMessage) => {
      // Log all WebRTC events for debugging (debug only)
      logUIEvent('📡', 'WS EVENT (WebRTC)', message.event, {
        event: message.event,
        sessionId: message.data?.session_id,
        textLength: message.data?.text?.length,
      }, true);

      switch (message.event) {
        case 'partial_transcript':
          if (!listeningStartTimeRef.current) {
            logUIEvent('🎤', 'LISTENING (WebRTC)', `Started (partial: "${message.data.text?.substring(0, 30)}...")`, undefined, true);
          }

          // Update voice chat partial transcript
          setVoicePartialTranscript(message.data.text || '');
          setIsListening(true);
          if (!listeningStartTimeRef.current) {
            listeningStartTimeRef.current = Date.now();
          }
          break;

        case 'final_transcript':
          logUIEvent('🎤', 'LISTENING (WebRTC)', `Stopped (final: "${message.data.text?.substring(0, 50)}...")`, undefined, true);

          // Clear voice chat partial transcript
          setVoicePartialTranscript('');
          setIsListening(false);
          listeningStartTimeRef.current = null;
          setListeningDuration(0);

          // Backend already saved user message - frontend only updates UI
          // (Removed duplicate save - backend is single source of truth)

          // Refresh message list to show backend-saved message
          if (activeSessionId) {
            logUIEvent('🔄', 'QUERY (WebRTC)', `Invalidating messages query (session: ${activeSessionId})`, undefined, true);
            queryClient.invalidateQueries({ queryKey: ['messages', activeSessionId] });
          }

          // Start AI generation indicator for voice chat
          logUIEvent('💭', 'THINKING (WebRTC)', `Started (session: ${activeSessionId})`, undefined, true);
          setIsVoiceAIGenerating(true);
          aiStartTimeRef.current = Date.now();
          break;

        case 'ai_response_chunk':
          // Stream AI response chunks for voice chat
          // Use StreamingMessageDisplay component for real-time display
          // No optimistic updates needed - backend saves to database
          setStreamingChunks((prev) => [...prev, message.data.text || '']);
          setIsStreaming(true);
          break;

        case 'ai_response_complete':
          const aiDuration = aiStartTimeRef.current ? Date.now() - aiStartTimeRef.current : 0;
          logUIEvent('💭', 'THINKING (WebRTC)', `Complete (duration: ${aiDuration}ms)`, undefined, true);

          // Stop AI generating animation
          setIsVoiceAIGenerating(false);
          aiStartTimeRef.current = null;
          setAiGeneratingDuration(0);

          // Stop streaming animation but KEEP chunks visible
          // (Chunks will be cleared by useEffect when database has assistant message)
          setIsStreaming(false);
          // DON'T clear streamingChunks here

          // Trigger database fetch
          if (activeSessionId) {
            logUIEvent('🔄', 'QUERY (WebRTC)', `Invalidating messages query (session: ${activeSessionId})`, undefined, true);
            queryClient.invalidateQueries({ queryKey: ['messages', activeSessionId] });
          }

          // AI response text is complete, now waiting for TTS audio
          console.log('✅ AI response complete - waiting for TTS audio...');
          break;

        case 'tts_start':
          console.log('🔊 TTS generation started');
          break;

        case 'bot_speaking_state_changed':
          console.log(`🤖 Bot speaking state changed: ${message.data.is_speaking ? 'SPEAKING' : 'LISTENING'}`);
          setIsBotSpeaking(message.data.is_speaking ?? false);
          break;

        case 'tts_complete':
          console.log(`✅ TTS complete (${message.data.duration_s?.toFixed(2)}s)`);
          console.log(`🔍 DEBUG: isSpeakerMuted=${isSpeakerMuted}, audioPlayback=${!!audioPlayback}`);
          console.log(`🔍 DEBUG: audioPlayback.completeAudio=${!!audioPlayback?.completeAudio}`);

          // Play buffered TTS audio if not muted
          if (!isSpeakerMuted) {
            console.log('🔍 DEBUG: Calling audioPlayback.completeAudio()...');
            try {
              await audioPlayback.completeAudio();
              console.log('🔍 DEBUG: completeAudio() returned successfully');
            } catch (error) {
              console.error('🔍 DEBUG: completeAudio() threw error:', error);
            }
          } else {
            console.log('🔇 Speaker muted, discarding TTS audio');
            audioPlayback.stop();
          }
          break;

        case 'error':
          console.error('[VoiceChat] Backend error:', message.data.message);
          toast.error('Voice Chat Error', message.data.message || 'Unknown error');
          break;

        default:
          console.warn('[VoiceChat] Unknown message event:', message.event);
      }
    },
    [activeSessionId, audioPlayback, isSpeakerMuted, queryClient, toast, setIsBotSpeaking]
  );

  // Handle binary audio chunks from TTS (web voice chat)
  const handleBinaryMessage = useCallback(
    (audioData: Uint8Array) => {
      if (!isSpeakerMuted) {
        console.log(`🎵 Buffering audio chunk: ${audioData.length} bytes`);
        audioPlayback.addAudioChunk(audioData);
      } else {
        console.log('🔇 Speaker muted, discarding audio chunk');
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
  } = useWebRTCAudio({
    sessionId: activeSessionId, // Use active session ID from conversation management
    onMessage: handleWebRTCAudioMessage,
    onBinaryMessage: handleBinaryMessage,
    onError: handleAudioError,
    onServiceError: handleServiceError, // Phase 2: Service error handling
    autoStart: false,
    timeslice: 100,
  });


  // Handle WebSocket messages (Discord conversation monitoring - for metrics updates)
  const handleMessage = useCallback((message: any) => {
    // Log all WebSocket events for debugging (debug only)
    logUIEvent('📡', 'WS EVENT', message.event, {
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
        logUIEvent('🎤', 'LISTENING', `Started (partial: "${message.data.text?.substring(0, 30)}...")`, undefined, true);
        setIsListening(true);
        listeningStartTimeRef.current = Date.now();
      }
      setVoicePartialTranscript(message.data.text);
    } else if (message.event === 'final_transcript') {
      logUIEvent('🎤', 'LISTENING', `Stopped (final: "${message.data.text?.substring(0, 50)}...")`, undefined, true);

      // Clear analytics state
      setActiveSpeaker(null);
      setPartialTranscript('');

      // Stop listening, start AI generating animation (unified experience)
      setIsListening(false);
      listeningStartTimeRef.current = null;
      setListeningDuration(0);
      setVoicePartialTranscript('');

      logUIEvent('💭', 'THINKING', `Started (session: ${activeSessionId})`, undefined, true);
      setIsVoiceAIGenerating(true);
      aiStartTimeRef.current = Date.now();

      // Backend already saved Discord user message - frontend only updates UI
      // (Removed duplicate save - backend is single source of truth)

      // Refresh message list to show backend-saved message
      if (activeSessionId) {
        logUIEvent('🔄', 'QUERY', `Invalidating messages query (session: ${activeSessionId})`, undefined, true);
        queryClient.invalidateQueries({ queryKey: ['messages', activeSessionId] });
      }
    } else if (message.event === 'ai_response_chunk') {
      // Discord AI response chunks - no action needed
      // Backend saves chunks to database, frontend just waits for ai_response_complete
    } else if (message.event === 'ai_response_complete') {
      const aiDuration = aiStartTimeRef.current ? Date.now() - aiStartTimeRef.current : 0;
      logUIEvent('💭', 'THINKING', `Complete (duration: ${aiDuration}ms)`, undefined, true);

      // Stop AI generating animation (unified experience)
      setIsVoiceAIGenerating(false);
      aiStartTimeRef.current = null;
      setAiGeneratingDuration(0);

      // Check for errors
      if (message.data.error) {
        console.error('[Discord] LLM error:', message.data.error);
        // Show error toast to user
        toast.error("AI Response Error", message.data.error);
      }

      // Refresh message list to show backend-saved message
      // No optimistic updates to remove - just fetch from database
      if (activeSessionId) {
        logUIEvent('🔄', 'QUERY', `Invalidating messages query (session: ${activeSessionId})`, undefined, true);
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
    logUIEvent('🚀', 'COMPONENT', 'VoxbridgePage mounted');
    return () => {
      logUIEvent('💥', 'COMPONENT', 'VoxbridgePage unmounting');
    };
  }, []);

  // Auto-select first session on load
  useEffect(() => {
    if (sessions.length > 0 && !activeSessionId) {
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions, activeSessionId]);

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
        console.error('[VoxBridge] Failed to fetch speaker status:', error);
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

        console.log('[VoxbridgePage] Discord status update:', {
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

        console.log('[VoxbridgePage] Setting state:', { botReady, inVoice, channelName, guildName });

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
        console.error('[VoxbridgePage] Failed to fetch Discord status:', error);
        setDiscordBotReady(false);
        setDiscordInVoice(false);
      }
    };

    fetchDiscordStatus();

    // Poll every 3 seconds while agent has Discord plugin
    const interval = setInterval(fetchDiscordStatus, 3000);
    return () => clearInterval(interval);
  }, [activeAgent]);

  // Update listening duration (web voice chat)
  useEffect(() => {
    if (isListening && listeningStartTimeRef.current) {
      const interval = setInterval(() => {
        setListeningDuration(Date.now() - listeningStartTimeRef.current!);
      }, 100);
      return () => clearInterval(interval);
    }
  }, [isListening]);

  // Update AI generating duration (web voice chat)
  useEffect(() => {
    if (isVoiceAIGenerating && aiStartTimeRef.current) {
      const interval = setInterval(() => {
        setAiGeneratingDuration(Date.now() - aiStartTimeRef.current!);
      }, 100);
      return () => clearInterval(interval);
    }
  }, [isVoiceAIGenerating]);

  // Clear streaming chunks when database has assistant message
  useEffect(() => {
    if (!isStreaming && streamingChunks.length > 0 && activeSessionId) {
      // Check if database has an assistant message
      const latestAssistantMsg = messages
        .filter(m => m.role === 'assistant')
        .slice(-1)[0];

      if (latestAssistantMsg) {
        // Database has caught up - clear streaming display
        console.log(`[STREAMING] Database ready, clearing ${streamingChunks.length} chunks`);
        setStreamingChunks([]);
      }
    }
  }, [messages, isStreaming, streamingChunks.length, activeSessionId]);

  // Conversation Management Handlers

  // Handle create conversation
  const handleCreateConversation = useCallback(
    async (agentId: string, title?: string) => {
      try {
        const newSession = await api.createSession({
          user_id: WEB_USER_ID,
          agent_id: agentId,
          title: title || null,
          session_type: 'web',
        });

        // Refetch sessions and select new one
        await refetchSessions();
        setActiveSessionId(newSession.id);
        toast.success('Conversation created', `Started new conversation with agent`);
      } catch (error) {
        toast.error('Failed to create conversation', error instanceof Error ? error.message : 'Unknown error');
        throw error;
      }
    },
    [refetchSessions, toast]
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

  // Handle select session
  const handleSelectSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
  }, []);

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
      console.error('[VoxbridgePage] Failed to join voice:', error);

      // If already connected, try to force leave first then retry
      if (error?.message?.includes('Already connected')) {
        try {
          console.log('Already connected detected, forcing leave and retry...');
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

    console.log(`[VoxbridgePage] Leaving voice with guild ID: ${guildIdToUse}`);

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
      console.error('Failed to copy:', err);
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
                      <AudioControls
                        isMuted={isMuted}
                        onToggleMute={toggleMute}
                        connectionState={connectionState}
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
                      {/* Bot Speaking Indicator */}
                      {isBotSpeaking && (
                        <Badge variant="secondary" className="animate-pulse">
                          <Volume2 className="h-3 w-3 mr-1" />
                          AI Speaking...
                        </Badge>
                      )}
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

                      {/* STT Waiting Indicator */}
                      {(isListening || voicePartialTranscript) && (
                        <STTWaitingIndicator
                          isListening={isListening}
                          duration={listeningDuration}
                          partialTranscript={voicePartialTranscript}
                        />
                      )}

                      {/* AI Generating Indicator */}
                      {isVoiceAIGenerating && (
                        <AIGeneratingIndicator
                          isGenerating={isVoiceAIGenerating}
                          duration={aiGeneratingDuration}
                        />
                      )}

                      {/* Streaming Message Display - shows during streaming and while waiting for database */}
                      {streamingChunks.length > 0 && (
                        <StreamingMessageDisplay
                          chunks={streamingChunks}
                          isStreaming={isStreaming}
                          agentName={activeAgent?.name || 'AI Assistant'}
                        />
                      )}

                      {/* Ready for Next Question Indicator (Multi-Turn Mode) */}
                      {activeSessionId && connectionState === 'connected' && !isListening && !isVoiceAIGenerating && !isBotSpeaking && !isStreaming && (
                        <div className="flex items-center justify-center py-4">
                          <Badge variant="outline" className="text-sm bg-green-500/10 text-green-400 border-green-500/30">
                            <CircleCheckBig className="h-4 w-4 mr-2" />
                            Ready for next question
                          </Badge>
                        </div>
                      )}

                      {/* Messages from Database */}
                      {isLoadingMessages ? (
                        <div className="text-center py-12 text-muted-foreground">
                          <p className="text-sm">Loading messages...</p>
                        </div>
                      ) : messages.length === 0 && !voicePartialTranscript && !isListening ? (
                        <div className="text-center py-12 text-muted-foreground">
                          <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-50" />
                          <p className="text-sm">No messages yet</p>
                          <p className="text-xs mt-1">Start speaking to begin the conversation</p>
                        </div>
                      ) : (
                        <>
                          {messages.slice().reverse().map((message) => (
                            <div
                              key={message.id}
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
                                <p className="text-sm whitespace-pre-wrap leading-relaxed">
                                  {message.content}
                                </p>

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
                          ))}
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
