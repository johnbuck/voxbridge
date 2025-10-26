/**
 * Voice Chat Page
 * Web-based voice chat interface with conversation sidebar
 * VoxBridge 2.0 Phase 4: Web Voice Interface
 */

import { useState, useCallback, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import { ConversationList } from '@/components/ConversationList';
import { NewConversationDialog } from '@/components/NewConversationDialog';
import { useToastHelpers } from '@/components/ui/toast';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Menu, Mic, MicOff, Volume2, VolumeX, MessageSquare, Brain } from 'lucide-react';
import { cn } from '@/lib/utils';

const USER_ID = 'web_user_default'; // Hardcoded until auth is implemented

export function VoiceChatPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [newConversationDialogOpen, setNewConversationDialogOpen] = useState(false);
  const [isMicActive, setIsMicActive] = useState(false);
  const [isSpeakerMuted, setIsSpeakerMuted] = useState(false);

  const toast = useToastHelpers();

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

          {/* Voice Controls (Placeholder) */}
          <div className="flex items-center gap-2">
            <Button
              variant={isMicActive ? 'default' : 'outline'}
              size="icon"
              onClick={() => setIsMicActive(!isMicActive)}
              title={isMicActive ? 'Mute microphone' : 'Unmute microphone'}
            >
              {isMicActive ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
            </Button>
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
            <ScrollArea className="h-full">
              <div className="max-w-4xl mx-auto p-6 space-y-4">
                {isLoadingMessages ? (
                  <div className="text-center py-12 text-muted-foreground">
                    <p className="text-sm">Loading messages...</p>
                  </div>
                ) : messages.length === 0 ? (
                  <div className="text-center py-12 text-muted-foreground">
                    <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-50" />
                    <p className="text-sm">No messages yet</p>
                    <p className="text-xs mt-1">Start speaking to begin the conversation</p>
                  </div>
                ) : (
                  messages.map((message) => (
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
                  ))
                )}
              </div>
            </ScrollArea>
          )}
        </div>

        {/* Voice Input Area (Placeholder) */}
        <div className="border-t border-border p-4">
          <Card>
            <CardContent className="p-6">
              <div className="text-center text-muted-foreground">
                <Mic className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm font-medium mb-1">Voice Controls Coming Soon</p>
                <p className="text-xs">
                  WebRTC voice capture and playback will be implemented in Phase 4
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
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
