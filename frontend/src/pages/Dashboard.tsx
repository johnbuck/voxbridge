/**
 * VoxBridge Dashboard
 * Main monitoring and control interface
 */

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ChannelSelector } from '@/components/ChannelSelector';
import { TTSTest } from '@/components/TTSTest';
import { MetricsPanel } from '@/components/MetricsPanel';

export function Dashboard() {
  const [activeSpeaker, setActiveSpeaker] = useState<string | null>(null);
  const [partialTranscript, setPartialTranscript] = useState<string>('');
  const [finalTranscript, setFinalTranscript] = useState<string>('');

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

  // WebSocket for real-time updates
  const { isConnected: wsConnected, lastMessage } = useWebSocket('/ws/events');

  // Handle WebSocket messages
  useEffect(() => {
    if (!lastMessage) return;

    switch (lastMessage.event) {
      case 'speaker_started':
        setActiveSpeaker(lastMessage.data.userId);
        break;
      case 'speaker_stopped':
        setActiveSpeaker(null);
        setPartialTranscript('');
        break;
      case 'partial_transcript':
        setPartialTranscript(lastMessage.data.text);
        break;
      case 'final_transcript':
        setFinalTranscript(lastMessage.data.text);
        setPartialTranscript('');
        break;
      case 'status_update':
        // Status update from WebSocket (supplements polling)
        break;
    }
  }, [lastMessage]);

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
                <p className="text-sm font-medium mb-2">Speaker Status</p>
                {health?.speakerLocked ? (
                  <div className="space-y-2">
                    <Badge>🔒 Locked</Badge>
                    <p className="text-xs text-muted-foreground">
                      Active: {health.activeSpeaker}
                    </p>
                    <Button
                      onClick={() => api.unlockSpeaker()}
                      variant="outline"
                      size="sm"
                      className="w-full"
                    >
                      Force Unlock
                    </Button>
                  </div>
                ) : (
                  <div>
                    <Badge variant="outline">🔓 Unlocked</Badge>
                    <p className="text-xs text-muted-foreground mt-1">
                      No active speaker
                    </p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

            {/* TTS Test */}
            <TTSTest inVoiceChannel={health?.inVoiceChannel ?? false} />
          </div>

          {/* Center Panel: Live Transcription */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Live Transcription</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {activeSpeaker ? (
                <div>
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
              ) : (
                <div className="text-center py-12 text-muted-foreground">
                  <p className="text-sm">Waiting for audio...</p>
                  <p className="text-xs mt-1">
                    Speak in the Discord voice channel to see transcriptions
                  </p>
                </div>
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
