/**
 * Discord Bot Controls Page
 * Voice controls, TTS testing, and runtime settings
 */

import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ChannelSelector } from '@/components/ChannelSelector';
import { TTSTest } from '@/components/TTSTest';
import { RuntimeSettings } from '@/components/RuntimeSettings';

export function DiscordBotPage() {
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

  return (
    <div className="min-h-screen bg-page-background p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-4xl font-bold">Discord Bot Controls</h1>
          <p className="text-muted-foreground mt-1">
            Voice channel controls, TTS testing, and runtime configuration
          </p>
        </div>

        {/* Voice Controls */}
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
      </div>
    </div>
  );
}
