/**
 * Voice Chat Page
 * Web-based voice chat interface with conversation sidebar
 * VoxBridge 2.0 Phase 4: Web Voice Interface
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type Message } from '@/services/api';
import { ConversationList } from '@/components/ConversationList';
import { NewConversationDialog } from '@/components/NewConversationDialog';
import { AudioControls } from '@/components/AudioControls';
import { useToastHelpers } from '@/components/ui/toast';
import { useWebRTCAudio } from '@/hooks/useWebRTCAudio';
import { useAudioPlayback } from '@/hooks/useAudioPlayback';
import type { WebRTCAudioMessage } from '@/types/webrtc';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Menu, Volume2, VolumeX, MessageSquare, Brain, AlertCircle, Lock, Unlock, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

const USER_ID = 'web_user_default'; // Hardcoded until auth is implemented

export function VoiceChatPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [newConversationDialogOpen, setNewConversationDialogOpen] = useState(false);
  const [isSpeakerMuted, setIsSpeakerMuted] = useState(false);
  const [partialTranscript, setPartialTranscript] = useState<string>('');
  const [speakerLocked, setSpeakerLocked] = useState(false);
  const [activeSpeaker, setActiveSpeaker] = useState<string | null>(null);
  const [isUnlocking, setIsUnlocking] = useState(false);

  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // Audio playback hook for TTS
  const audioPlayback = useAudioPlayback({
    autoPlay: true,
    onPlaybackStart: () => console.log('🔊 Playing TTS audio'),
    onPlaybackEnd: () => console.log('✅ TTS playback complete'),
    onError: (error) => toast.error('Audio playback failed', error),
  });

  // Fetch sessions
  const { data: sessions = [], isLoading: isLoadingSessions, refetch: refetchSessions } = useQuery({
    queryKey: ['sessions', USER_ID],
    queryFn: () => api.getSessions(USER_ID, false, 50),
    refetchInterval: 5000, // Poll every 5 seconds
  });

  // Fetch agents for new conversation dialog
  const { data: agents = [], isLoading: isLoadingAgents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => api.getAgents(),
  });

  // Fetch messages for active session
  const { data: messages = [], isLoading: isLoadingMessages } = useQuery({
    queryKey: ['messages', activeSessionId],
    queryFn: () => activeSessionId ? api.getSessionMessages(activeSessionId) : Promise.resolve([]),
    enabled: !!activeSessionId,
    refetchInterval: 2000, // Poll every 2 seconds for real-time updates
  });

  // Get active session details
  const activeSession = sessions.find((s) => s.id === activeSessionId);

  // Get agent for active session
  const activeAgent = agents.find((a) => a.id === activeSession?.agent_id);

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
      setActiveSpeaker(null);
      return;
    }

    // Fetch status immediately
    const fetchSpeakerStatus = async () => {
      try {
        const status = await api.getStatus();
        setSpeakerLocked(status.speaker.locked);
        setActiveSpeaker(status.speaker.activeSpeaker);
      } catch (error) {
        console.error('[VoiceChat] Failed to fetch speaker status:', error);
      }
    };

    fetchSpeakerStatus();

    // Poll every 3 seconds while agent has Discord plugin
    const interval = setInterval(fetchSpeakerStatus, 3000);
    return () => clearInterval(interval);
  }, [activeAgent]);

  // Handle WebRTC audio messages
  const handleAudioMessage = useCallback(
    async (message: WebRTCAudioMessage) => {
      if (!activeSessionId) return;

      switch (message.event) {
        case 'partial_transcript':
          // Update partial transcript (live transcription)
          setPartialTranscript(message.data.text || '');
          break;

        case 'final_transcript':
          // Save user message to database
          try {
            await api.addMessage(activeSessionId, {
              role: 'user',
              content: message.data.text || '',
            });

            // Clear partial transcript
            setPartialTranscript('');

            // Invalidate messages query to refetch
            queryClient.invalidateQueries({ queryKey: ['messages', activeSessionId] });
          } catch (error) {
            console.error('[VoiceChat] Failed to save user message:', error);
            toast.error('Failed to save message', error instanceof Error ? error.message : 'Unknown error');
          }
          break;

        case 'ai_response_chunk':
          // Stream AI response (update last message in real-time)
          queryClient.setQueryData(['messages', activeSessionId], (oldData: Message[] | undefined) => {
            if (!oldData) return oldData;

            const lastMessage = oldData[oldData.length - 1];
            if (lastMessage && lastMessage.role === 'assistant') {
              // Append to existing assistant message
              return [
                ...oldData.slice(0, -1),
                {
                  ...lastMessage,
                  content: lastMessage.content + (message.data.text || ''),
                },
              ];
            } else {
              // Create new assistant message
              return [
                ...oldData,
                {
                  id: Date.now(), // Temporary ID
                  session_id: activeSessionId,
                  role: 'assistant',
                  content: message.data.text || '',
                  timestamp: new Date().toISOString(),
                  audio_duration_ms: null,
                  tts_duration_ms: null,
                  llm_latency_ms: null,
                  total_latency_ms: null,
                },
              ];
            }
          });
          break;

        case 'ai_response_complete':
          // Save final AI message to database
          try {
            await api.addMessage(activeSessionId, {
              role: 'assistant',
              content: message.data.text || '',
            });

            // Invalidate messages query to refetch (get proper ID from backend)
            queryClient.invalidateQueries({ queryKey: ['messages', activeSessionId] });
          } catch (error) {
            console.error('[VoiceChat] Failed to save AI message:', error);
            toast.error('Failed to save AI response', error instanceof Error ? error.message : 'Unknown error');
          }
          break;

        case 'tts_start':
          // TTS generation started
          console.log('🔊 TTS generation started');
          break;

        case 'tts_complete':
          // TTS generation complete - play buffered audio
          console.log(`✅ TTS complete (${message.data.duration_s?.toFixed(2)}s)`);

          // Play all buffered audio chunks
          if (!isSpeakerMuted) {
            await audioPlayback.completeAudio();
          } else {
            console.log('🔇 Speaker muted, discarding TTS audio');
            audioPlayback.stop(); // Clear buffer
          }
          break;

        case 'error':
          // Error from backend
          console.error('[VoiceChat] Backend error:', message.data.message);
          toast.error('Backend Error', message.data.message || 'Unknown error');
          break;

        default:
          console.warn('[VoiceChat] Unknown message event:', message.event);
      }
    },
    [activeSessionId, queryClient, toast, audioPlayback, isSpeakerMuted]
  );

  // Handle binary audio chunks from TTS
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

  // Handle WebRTC errors
  const handleAudioError = useCallback(
    (error: string) => {
      toast.error('Audio Error', error);
    },
    [toast]
  );

  // WebRTC Audio Hook
  const {
    isMuted,
    toggleMute,
    connectionState,
    permissionError,
    isRecording,
  } = useWebRTCAudio({
    sessionId: activeSessionId,
    onMessage: handleAudioMessage,
    onBinaryMessage: handleBinaryMessage,  // NEW: Handle TTS audio chunks
    onError: handleAudioError,
    autoStart: false, // User must click to start
    timeslice: 100, // 100ms chunks
  });

  // Handle create conversation
  const handleCreateConversation = useCallback(
    async (agentId: string, title?: string) => {
      try {
        const newSession = await api.createSession({
          user_id: USER_ID,
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
      setActiveSpeaker(null);
      toast.success('Speaker unlocked', result.previousSpeaker ? `Unlocked ${result.previousSpeaker}` : undefined);
    } catch (error) {
      toast.error('Failed to unlock speaker', error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setIsUnlocking(false);
    }
  }, [toast]);

  // Format timestamp
  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <div
        className={cn(
          'transition-all duration-300 border-r border-border',
          sidebarOpen ? 'w-80' : 'w-0 overflow-hidden'
        )}
      >
        <ConversationList
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onCreateSession={() => setNewConversationDialogOpen(true)}
          onDeleteSession={handleDeleteSession}
          isLoading={isLoadingSessions}
        />
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="h-16 border-b border-border flex items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              title={sidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
            >
              <Menu className="h-5 w-5" />
            </Button>

            {activeSession && (
              <div className="flex items-center gap-3">
                <Brain className="h-5 w-5 text-primary" />
                <div>
                  <h2 className="text-sm font-semibold">
                    {activeSession.title || `Conversation ${new Date(activeSession.started_at).toLocaleDateString()}`}
                  </h2>
                  {activeAgent && (
                    <p className="text-xs text-muted-foreground">
                      {activeAgent.name} • {activeAgent.llm_model}
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Speaker Lock (Discord Plugin Only) */}
          <div className="flex items-center gap-4">
            {activeAgent?.plugins?.discord?.enabled && (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted border border-border">
                {speakerLocked ? (
                  <>
                    <Lock className="h-4 w-4 text-yellow-400" />
                    <div className="flex items-center gap-2">
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
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <>
                            <Unlock className="h-3 w-3 mr-1" />
                            Unlock
                          </>
                        )}
                      </Button>
                    </div>
                  </>
                ) : (
                  <>
                    <Unlock className="h-4 w-4 text-green-400" />
                    <span className="text-xs font-medium text-muted-foreground">Speaker Unlocked</span>
                  </>
                )}
              </div>
            )}

            {/* Voice Controls */}
              <AudioControls
                isMuted={isMuted}
                onToggleMute={toggleMute}
                connectionState={connectionState}
                permissionError={permissionError}
                isRecording={isRecording}
              />
              <Button
                variant={isSpeakerMuted ? 'outline' : 'default'}
                size="icon"
                onClick={() => setIsSpeakerMuted(!isSpeakerMuted)}
                title={isSpeakerMuted ? 'Unmute speaker' : 'Mute speaker'}
              >
                {isSpeakerMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
              </Button>
          </div>
        </div>

        {/* Conversation View */}
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
                {isLoadingMessages ? (
                  <div className="text-center py-12 text-muted-foreground">
                    <p className="text-sm">Loading messages...</p>
                  </div>
                ) : messages.length === 0 && !partialTranscript ? (
                  <div className="text-center py-12 text-muted-foreground">
                    <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-50" />
                    <p className="text-sm">No messages yet</p>
                    <p className="text-xs mt-1">Start speaking to begin the conversation</p>
                  </div>
                ) : (
                  <>
                    {messages.map((message) => (
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

                    {/* Partial Transcript (Live Transcription) */}
                    {partialTranscript && (
                      <div className="flex justify-start">
                        <div className="max-w-[80%] p-4 rounded-lg bg-primary/5 border border-primary/10">
                          <div className="flex items-center mb-2 gap-2">
                            <span className="text-xs font-medium text-primary">You</span>
                            <span className="text-xs text-muted-foreground italic">(speaking...)</span>
                          </div>
                          <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
                            {partialTranscript}
                          </p>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </ScrollArea>
          )}
        </div>

        {/* Voice Input Status */}
        {permissionError && (
          <div className="border-t border-border p-4">
            <Card className="border-red-500/20 bg-red-500/5">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-red-500 mb-1">Microphone Permission Required</p>
                    <p className="text-xs text-muted-foreground">
                      {permissionError}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>

      {/* New Conversation Dialog */}
      <NewConversationDialog
        open={newConversationDialogOpen}
        onOpenChange={setNewConversationDialogOpen}
        agents={agents}
        isLoadingAgents={isLoadingAgents}
        onCreateConversation={handleCreateConversation}
      />
    </div>
  );
}
