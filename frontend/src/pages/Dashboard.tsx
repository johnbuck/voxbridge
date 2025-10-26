/**
 * VoxBridge Dashboard
 * Main monitoring and control interface
 */

import { useState, useRef, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ChannelSelector } from '@/components/ChannelSelector';
import { TTSTest } from '@/components/TTSTest';
import { TTSSettings } from '@/components/TTSSettings';
import { RuntimeSettings } from '@/components/RuntimeSettings';
import { MetricsPanel } from '@/components/MetricsPanel';

interface TranscriptItem {
  id: string; // Unique identifier for the message
  type: 'user' | 'ai';
  userId?: string;
  username?: string;
  text: string;
  timestamp: string;
  isFinal?: boolean;
}

export function Dashboard() {
  const [activeSpeaker, setActiveSpeaker] = useState<string | null>(null);
  const [partialTranscript, setPartialTranscript] = useState<string>('');
  const [finalTranscript, setFinalTranscript] = useState<string>('');
  const [transcriptHistory, setTranscriptHistory] = useState<TranscriptItem[]>([]);
  const seenMessageIdsRef = useRef(new Set<string>());
  const queryClient = useQueryClient();

  // Poll health status
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => api.getHealth(),
    refetchInterval: 2000, // Poll every 2 seconds
  });

  // Poll detailed status
  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: () => api.getStatus(),
    refetchInterval: 5000, // Poll every 5 seconds
  });

  // Handle WebSocket messages via callback (bypasses React batching)
  const handleMessage = useCallback((message: any) => {
    switch (message.event) {
      case 'speaker_started':
        setActiveSpeaker(message.data.userId);
        break;
      case 'speaker_stopped':
        setActiveSpeaker(null);
        setPartialTranscript('');
        break;
      case 'partial_transcript':
        setPartialTranscript(message.data.text);
        break;
      case 'final_transcript':
        setFinalTranscript(message.data.text);
        setPartialTranscript('');
        // Add to history (newest first)
        // Generate deterministic ID based on message content (not random)
        const userMessageId = `user-${message.data.userId}-${message.data.timestamp}-${message.data.text.substring(0, 50)}`;

        // Check if already seen (using ref for synchronous check)
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
          // Keep only last 100 transcripts
          return [newItem, ...prev].slice(0, 100);
        });
        break;
      case 'ai_response':
        // Add AI response sentence to history
        const messageId = message.data.id;
        console.log('[AI Response] Received:', { id: messageId, text: message.data.text });

        // Check if we've already seen this message (using ref for synchronous check)
        if (seenMessageIdsRef.current.has(messageId)) {
          console.log('[AI Response] Duplicate message, skipping:', messageId);
          break;
        }

        console.log('[AI Response] Adding new message:', messageId);
        seenMessageIdsRef.current.add(messageId);

        setTranscriptHistory((prev) => {
          console.log('[AI Response] Current history length:', prev.length);

          const newItem: TranscriptItem = {
            id: messageId,
            type: 'ai',
            text: message.data.text,
            timestamp: message.data.timestamp,
            isFinal: message.data.isFinal,
          };
          const newHistory = [newItem, ...prev].slice(0, 100);
          console.log('[AI Response] New history length:', newHistory.length);
          // Keep only last 100 transcripts
          return newHistory;
        });

        // Trigger metrics refetch when AI response is complete
        if (message.data.isFinal) {
          console.log('[Metrics] Refetching metrics after AI response completion');
          queryClient.invalidateQueries({ queryKey: ['metrics'] });
        }
        break;
      case 'status_update':
        // Status update from WebSocket (supplements polling)
        break;
    }
  }, [queryClient]);

  // WebSocket for real-time updates
  const { isConnected: wsConnected } = useWebSocket('/ws/events', {
    onMessage: handleMessage
  });

  const getStatusBadge = (isReady: boolean) => {
    return isReady ? (
      <Badge className="bg-green-500">✓ Ready</Badge>
    ) : (
      <Badge variant="destructive">✗ Offline</Badge>
    );
  };

  return (
    <div className="min-h-screen bg-page-background p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold">VoxBridge Dashboard</h1>
            <p className="text-muted-foreground mt-1">
              Real-time voice bridge monitoring and control
            </p>
          </div>
          <div className="flex gap-2">
            {getStatusBadge(health?.botReady ?? false)}
            <Badge variant={wsConnected ? 'default' : 'outline'}>
              {wsConnected ? '🔌 WebSocket Connected' : '⏸️ WebSocket Disconnected'}
            </Badge>
          </div>
        </div>

        {/* Connection Status Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Discord Bot</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {health?.botReady ? '✓' : '✗'}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {status?.bot.username || 'Not Ready'}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">WhisperX</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {status?.whisperx.serverConfigured ? '✓' : '✗'}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {status?.whisperx.serverUrl || 'Not Configured'}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Chatterbox TTS</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {status?.services.chatterbox ? '✓' : '✗'}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {status?.services.chatterbox ? 'Available' : 'Offline'}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">n8n Webhook</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {status?.services.n8nWebhook ? '✓' : '✗'}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {status?.services.n8nWebhook ? 'Configured' : 'Not Set'}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Panel: Voice Controls & TTS */}
          <div className="lg:col-span-1 space-y-6">
            <Card>
            <CardHeader>
              <CardTitle>Voice Controls</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-sm font-medium mb-2">Voice Channel</p>
                {status?.voice.connected ? (
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">
                      {status.voice.channelName} ({status.voice.guildName})
                    </p>
                    <Button
                      onClick={() => api.leaveChannel()}
                      variant="destructive"
                      className="w-full"
                    >
                      Leave Channel
                    </Button>
                  </div>
                ) : (
                  <ChannelSelector />
                )}
              </div>

              <div>
                <p className="text-sm font-medium mb-2">Speaker Lock</p>
                {health?.speakerLocked ? (
                  <div className="space-y-2">
                    <Badge>🔒 Locked</Badge>
                    <p className="text-xs text-muted-foreground">
                      Active: {health.activeSpeaker}
                    </p>
                    <p className="text-xs text-muted-foreground mb-2">
                      Speaker lock prevents interruptions during transcription.
                      Use unlock if stuck.
                    </p>
                    <Button
                      onClick={() => api.unlockSpeaker()}
                      variant="outline"
                      size="sm"
                      className="w-full"
                    >
                      Force Unlock Speaker
                    </Button>
                  </div>
                ) : (
                  <div>
                    <Badge variant="outline">🔓 Unlocked</Badge>
                    <p className="text-xs text-muted-foreground mt-1">
                      Ready to accept new speakers
                    </p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

            {/* TTS Test */}
            <TTSTest inVoiceChannel={health?.inVoiceChannel ?? false} />

            {/* Runtime Settings */}
            <RuntimeSettings />

            {/* TTS Settings */}
            <TTSSettings />
          </div>

          {/* Center Panel: Conversation */}
          <Card className="lg:col-span-2 flex flex-col">
            <CardHeader>
              <CardTitle>Conversation</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col flex-1 min-h-0 space-y-4">
              {/* Active Speaker Section */}
              {activeSpeaker && (
                <div className="border-b border-border pb-4 shrink-0">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                    <span className="font-medium">User: {activeSpeaker}</span>
                  </div>

                  {partialTranscript && (
                    <div className="p-3 bg-muted rounded-md mb-2">
                      <p className="text-sm text-muted-foreground italic">
                        {partialTranscript}
                      </p>
                    </div>
                  )}

                  {finalTranscript && (
                    <div className="p-3 bg-primary/10 rounded-md border border-primary/20">
                      <p className="text-sm font-semibold">
                        {finalTranscript}
                      </p>
                    </div>
                  )}
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
                            {item.type === 'user' ? item.username : 'AI Assistant'}
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

        {/* Bottom: System Info */}
        <Card>
          <CardHeader>
            <CardTitle>System Information</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Bot Username</p>
                <p className="font-medium">{status?.bot.username || 'N/A'}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Bot ID</p>
                <p className="font-medium font-mono text-xs">
                  {status?.bot.id || 'N/A'}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Voice Channel</p>
                <p className="font-medium">
                  {status?.voice.channelName || 'Not Connected'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Metrics Panel */}
        <MetricsPanel />
      </div>
    </div>
  );
}
