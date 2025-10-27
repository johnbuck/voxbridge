/**
 * VoxBridge Main Dashboard Page
 * Status cards, conversation, system info, and metrics
 */

import { useState, useRef, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { MetricsPanel } from '@/components/MetricsPanel';
import { StatusSummary } from '@/components/StatusSummary';
import { RuntimeSettings } from '@/components/RuntimeSettings';
import { useToastHelpers } from '@/components/ui/toast';
import { Copy, CircleCheckBig, Activity, XCircle, AlertCircle, Mic } from 'lucide-react';

interface TranscriptItem {
  id: string;
  type: 'user' | 'ai';
  userId?: string;
  username?: string;
  text: string;
  timestamp: string;
  isFinal?: boolean;
}

export function VoxbridgePage() {
  const [activeSpeaker, setActiveSpeaker] = useState<string | null>(null);
  const [activeSpeakerUsername, setActiveSpeakerUsername] = useState<string | null>(null);
  const [partialTranscript, setPartialTranscript] = useState<string>('');
  const [isAIGenerating, setIsAIGenerating] = useState<boolean>(false);
  const [transcriptHistory, setTranscriptHistory] = useState<TranscriptItem[]>([]);
  const [showStatistics, setShowStatistics] = useState(false);
  const seenMessageIdsRef = useRef(new Set<string>());
  const queryClient = useQueryClient();
  const toast = useToastHelpers();

  // Poll health status
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => api.getHealth(),
    refetchInterval: 2000,
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

  // Handle WebSocket messages
  const handleMessage = useCallback((message: any) => {
    // VoxBridge 2.0: Handle agent CRUD events (real-time updates)
    if (message.event === 'agent_created' || message.event === 'agent_updated' || message.event === 'agent_deleted') {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
      return;
    }

    switch (message.event) {
      case 'speaker_started':
        setActiveSpeaker(message.data.userId);
        setActiveSpeakerUsername(message.data.username);
        break;
      case 'speaker_stopped':
        setActiveSpeaker(null);
        setActiveSpeakerUsername(null);
        setPartialTranscript('');
        break;
      case 'partial_transcript':
        setPartialTranscript(message.data.text);
        break;
      case 'final_transcript':
        // Clear active speaker section immediately
        setActiveSpeaker(null);
        setActiveSpeakerUsername(null);
        setPartialTranscript('');

        // Start AI generation indicator
        setIsAIGenerating(true);

        const userMessageId = `user-${message.data.userId}-${message.data.timestamp}-${message.data.text.substring(0, 50)}`;

        if (seenMessageIdsRef.current.has(userMessageId)) {
          console.log('[Final Transcript] Duplicate message, skipping:', userMessageId);
          break;
        }

        console.log('[Final Transcript] Adding new message:', userMessageId);
        seenMessageIdsRef.current.add(userMessageId);

        setTranscriptHistory((prev) => {
          const newItem: TranscriptItem = {
            id: userMessageId,
            type: 'user',
            userId: message.data.userId,
            username: message.data.username,
            text: message.data.text,
            timestamp: message.data.timestamp,
          };
          return [newItem, ...prev].slice(0, 100);
        });
        break;
      case 'ai_response':
        // Clear AI generation indicator
        setIsAIGenerating(false);

        const messageId = message.data.id;
        console.log('[AI Response] Received:', { id: messageId, text: message.data.text });

        if (seenMessageIdsRef.current.has(messageId)) {
          console.log('[AI Response] Duplicate message, skipping:', messageId);
          break;
        }

        console.log('[AI Response] Adding new message:', messageId);
        seenMessageIdsRef.current.add(messageId);

        setTranscriptHistory((prev) => {
          const newItem: TranscriptItem = {
            id: messageId,
            type: 'ai',
            text: message.data.text,
            timestamp: message.data.timestamp,
            isFinal: message.data.isFinal,
          };
          return [newItem, ...prev].slice(0, 100);
        });

        if (message.data.isFinal) {
          console.log('[Metrics] Refetching metrics after AI response completion');
          queryClient.invalidateQueries({ queryKey: ['metrics'] });
        }
        break;
      case 'status_update':
        break;
    }
  }, [queryClient]);

  // WebSocket for real-time updates
  const { isConnected: wsConnected } = useWebSocket('/ws/events', {
    onMessage: handleMessage
  });

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

  // Status helper functions for dynamic service status displays
  const getDiscordStatus = () => {
    if (!health?.botReady) {
      return {
        color: 'text-red-600 dark:text-red-400',
        icon: <XCircle className="w-4 h-4" />,
        text: 'Offline',
        info: 'Not Ready'
      };
    }
    if (activeSpeaker) {
      return {
        color: 'text-purple-600 dark:text-purple-400',
        icon: <Mic className="w-4 h-4" />,
        text: 'Active',
        info: status?.voice.channelName || 'Processing audio'
      };
    }
    if (status?.voice.connected) {
      return {
        color: 'text-green-600 dark:text-green-400',
        icon: <CircleCheckBig className="w-4 h-4" />,
        text: 'Ready',
        info: status.voice.channelName || 'Connected'
      };
    }
    return {
      color: 'text-yellow-600 dark:text-yellow-400',
      icon: <AlertCircle className="w-4 h-4" />,
      text: 'Ready',
      info: 'Not in voice channel'
    };
  };

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
    // Check if there's a recent non-final AI response (indicates generating)
    const isGenerating = transcriptHistory.length > 0 &&
      transcriptHistory[0].type === 'ai' &&
      !transcriptHistory[0].isFinal;

    if (isGenerating) {
      return {
        color: 'text-blue-600 dark:text-blue-400',
        icon: <Activity className="w-4 h-4 animate-pulse" />,
        text: 'Generating',
        info: 'Creating audio'
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
        <StatusSummary metrics={metrics} isLoadingMetrics={isLoadingMetrics} wsConnected={wsConnected} />

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

        {/* Connection Status Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Discord Bot</CardTitle>
            </CardHeader>
            <CardContent>
              {(() => {
                const statusInfo = getDiscordStatus();
                return (
                  <>
                    <div className={`flex items-center gap-2 text-sm font-semibold ${statusInfo.color}`}>
                      {statusInfo.icon}
                      <span>{statusInfo.text}</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {statusInfo.info}
                    </p>
                    {status?.bot.id && (
                      <div className="flex items-center gap-1 mt-1">
                        <p className="text-xs text-muted-foreground font-mono flex-1" title={status.bot.id}>
                          {status.bot.id}
                        </p>
                        <button
                          onClick={() => copyToClipboard(status.bot.id)}
                          className="p-1 hover:bg-muted rounded"
                          title="Copy Bot ID"
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

        {/* Conversation Card */}
        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle>Conversation</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col flex-1 min-h-0 space-y-4">
            {/* Active Speaker Section */}
            {activeSpeaker && (
              <div className="pb-4 shrink-0">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                  <span className="font-medium">{activeSpeakerUsername || activeSpeaker}</span>
                </div>

                {/* Animated Ellipsis Bubble */}
                <div className="flex justify-start">
                  <div className="max-w-[80%] p-3 rounded-lg bg-primary/10 border border-primary/20">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                      <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                      <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* AI Generation Indicator */}
            {isAIGenerating && (
              <div className="pb-4 shrink-0">
                <div className="flex justify-end">
                  <div className="max-w-[80%] p-3 rounded-lg bg-purple-500/10 border border-purple-500/20">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Conversation History */}
            {transcriptHistory.length > 0 ? (
              <div className="flex-1 overflow-y-auto space-y-3 min-h-0">
                {transcriptHistory.map((item) => (
                  <div
                    key={item.id}
                    className={`flex ${item.type === 'ai' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[80%] p-3 rounded-lg ${
                        item.type === 'user'
                          ? 'bg-primary/10 border border-primary/20'
                          : 'bg-purple-500/10 border border-purple-500/20'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1 gap-2">
                        <span className={`text-xs font-medium ${
                          item.type === 'user' ? 'text-primary' : 'text-purple-400'
                        }`}>
                          {item.type === 'user' ? item.username : (status?.bot.username || 'AI Assistant')}
                        </span>
                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                          {new Date(item.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-sm">{item.text}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              !activeSpeaker && (
                <div className="text-center py-12 text-muted-foreground flex-1">
                  <p className="text-sm">Waiting for audio...</p>
                  <p className="text-xs mt-1">
                    Speak in the Discord voice channel to see transcriptions
                  </p>
                </div>
              )
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
