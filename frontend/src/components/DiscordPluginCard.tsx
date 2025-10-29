/**
 * Discord Plugin Card Component
 * Shows Discord bot status and controls for an agent with Discord plugin enabled
 */

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  MessageSquare,
  ChevronDown,
  ChevronUp,
  Volume2,
  Lock,
  Unlock,
  TestTube,
  LogIn,
  LogOut,
  Loader2
} from 'lucide-react';
import { api, type Agent } from '@/services/api';
import { TTSTestModal } from '@/components/TTSTestModal';
import { ChannelSelectorModal } from '@/components/ChannelSelectorModal';

interface DiscordPluginCardProps {
  agent: Agent;
}

interface DiscordStatus {
  connected: boolean;
  inVoice: boolean;
  guildId: string | null;
  guildName: string | null;
  channelName: string | null;
  speakerLocked: boolean;
  activeSpeaker: string | null;
}

export function DiscordPluginCard({ agent }: DiscordPluginCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [status, setStatus] = useState<DiscordStatus>({
    connected: false,
    inVoice: false,
    guildId: null,
    guildName: null,
    channelName: null,
    speakerLocked: false,
    activeSpeaker: null
  });
  const [isLoading, setIsLoading] = useState(false);
  const [showTTSTest, setShowTTSTest] = useState(false);
  const [showChannelSelector, setShowChannelSelector] = useState(false);

  // Get stored guild ID from localStorage (persists across page reloads)
  const getStoredGuildId = () => {
    try {
      return localStorage.getItem(`discord_guild_${agent.id}`);
    } catch {
      return null;
    }
  };

  const [lastJoinedGuildId, setLastJoinedGuildId] = useState<string | null>(getStoredGuildId());

  // Fetch Discord plugin status for this agent
  useEffect(() => {
    if (agent.plugins?.discord?.enabled) {
      // Fetch status immediately on mount or when agent changes
      fetchStatus();

      // Poll status every 3 seconds while expanded
      if (isExpanded) {
        const interval = setInterval(fetchStatus, 3000);
        return () => clearInterval(interval);
      }
    }
  }, [isExpanded, agent.id]);

  const fetchStatus = async () => {
    try {
      // Use per-agent status endpoint
      const data = await api.getAgentDiscordStatus(agent.id);

      // Check if agent has any active voice connections
      const connection = data.connections && data.connections.length > 0 ? data.connections[0] : null;

      setStatus({
        connected: true, // If we got a response, plugin is connected
        inVoice: connection?.connected || false,
        guildId: connection?.guild_id?.toString() || null,
        guildName: connection?.guild_name || null,
        channelName: connection?.channel_name || null,
        speakerLocked: false, // TODO: Get from per-agent endpoint when available
        activeSpeaker: null // TODO: Get from per-agent endpoint when available
      });
    } catch (error) {
      console.error('Failed to fetch Discord status:', error);
      // Fallback: assume disconnected
      setStatus({
        connected: false,
        inVoice: false,
        guildId: null,
        guildName: null,
        channelName: null,
        speakerLocked: false,
        activeSpeaker: null
      });
    }
  };

  const handleJoinVoice = async () => {
    // Just open the modal - selection is handled by handleChannelSelected
    setShowChannelSelector(true);
  };

  const handleChannelSelected = async (guildId: string, channelId: string) => {
    setIsLoading(true);
    try {
      await api.joinChannel(agent.id, channelId, guildId);
      // Store guild ID locally to avoid precision loss from status endpoint
      setLastJoinedGuildId(guildId);
      localStorage.setItem(`discord_guild_${agent.id}`, guildId);
      await fetchStatus();
      setShowChannelSelector(false);
      // Optional: Add success toast notification
    } catch (error: any) {
      console.error('Failed to join voice:', error);

      // If already connected, try to force leave first then retry
      if (error?.message?.includes('Already connected')) {
        try {
          console.log('Already connected detected, forcing leave and retry...');
          await api.leaveChannel(agent.id, guildId);
          // Retry join after leaving
          await api.joinChannel(agent.id, channelId, guildId);
          setLastJoinedGuildId(guildId);
          localStorage.setItem(`discord_guild_${agent.id}`, guildId);
          await fetchStatus();
          setShowChannelSelector(false);
          return; // Success on retry
        } catch (retryError) {
          console.error('Failed to reconnect:', retryError);
          alert(`Failed to reconnect: ${retryError instanceof Error ? retryError.message : 'Unknown error'}`);
        }
      } else {
        // Show error to user for non-reconnect issues
        alert(`Failed to join voice channel: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleLeaveVoice = async () => {
    // Use locally stored guild ID to avoid precision loss from status endpoint
    const guildIdToUse = lastJoinedGuildId || status.guildId;

    if (!guildIdToUse) {
      console.error('Cannot leave voice: no guild ID available');
      alert('Cannot leave voice: guild ID not found');
      return;
    }

    console.log(`Leaving voice with guild ID: ${guildIdToUse}`);

    setIsLoading(true);
    try {
      await api.leaveChannel(agent.id, guildIdToUse);
      // Clear stored guild ID after leaving
      setLastJoinedGuildId(null);
      localStorage.removeItem(`discord_guild_${agent.id}`);
      await fetchStatus();
    } catch (error) {
      console.error('Failed to leave voice:', error);
      alert(`Failed to leave voice channel: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleUnlockSpeaker = async () => {
    setIsLoading(true);
    try {
      await api.unlockSpeaker();
      await fetchStatus();
    } catch (error) {
      console.error('Failed to unlock speaker:', error);
    } finally {
      setIsLoading(false);
    }
  };

  if (!agent.plugins?.discord?.enabled) {
    return null;
  }

  return (
    <>
      <div className="space-y-3">
        {/* Plugin Header */}
        <div className="space-y-2">
          {/* Row 1: Title and Status */}
          <div
            className="flex items-center justify-between cursor-pointer hover:bg-muted/50 transition-colors p-2 -mx-2 rounded"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <MessageSquare className="h-4 w-4 text-purple-400 flex-shrink-0" />
              <span className="text-sm font-medium">Discord Bot Plugin</span>
              <Badge
                variant="outline"
                className={status.connected
                  ? 'bg-green-500/20 text-green-400 border-green-500/50'
                  : 'bg-red-500/20 text-red-400 border-red-500/50'
                }
              >
                {status.connected ? '● Connected' : '○ Disconnected'}
              </Badge>
            </div>
            <Button variant="ghost" size="icon" className="h-6 w-6 flex-shrink-0">
              {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
          </div>

          {/* Row 2: Connection Details (only when in voice) */}
          {status.inVoice && (
            <div className="flex items-center gap-2 px-2 pb-2 flex-wrap">
              {status.guildName && (
                <Badge variant="outline" className="bg-purple-500/20 text-purple-400 border-purple-500/50">
                  {status.guildName}
                </Badge>
              )}
              {status.channelName && (
                <Badge variant="outline" className="bg-blue-500/20 text-blue-400 border-blue-500/50">
                  <Volume2 className="h-3 w-3 mr-1" />
                  {status.channelName}
                </Badge>
              )}
            </div>
          )}
        </div>

        {/* Expanded Content */}
        {isExpanded && (
          <div className="space-y-3">
            {/* Voice Channel Controls */}
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">Voice Controls</div>
              <div className="flex gap-2">
                {!status.inVoice ? (
                  <Button
                    onClick={handleJoinVoice}
                    disabled={isLoading || !status.connected}
                    size="sm"
                    className="flex-1"
                  >
                    {isLoading ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <LogIn className="h-4 w-4 mr-2" />
                    )}
                    Join Voice
                  </Button>
                ) : (
                  <Button
                    onClick={handleLeaveVoice}
                    disabled={isLoading}
                    variant="destructive"
                    size="sm"
                    className="flex-1"
                  >
                    {isLoading ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <LogOut className="h-4 w-4 mr-2" />
                    )}
                    Leave Voice
                  </Button>
                )}
              </div>
            </div>

            {/* Speaker Lock Status */}
            {status.inVoice && (
              <div className="space-y-2">
                <div className="text-xs text-muted-foreground">Speaker Lock</div>
                <div className="flex items-center justify-between gap-2 p-2 rounded bg-muted">
                  <div className="flex items-center gap-2 text-sm">
                    {status.speakerLocked ? (
                      <>
                        <Lock className="h-4 w-4 text-yellow-400" />
                        <span>Locked: {status.activeSpeaker || 'Unknown'}</span>
                      </>
                    ) : (
                      <>
                        <Unlock className="h-4 w-4 text-green-400" />
                        <span>Unlocked</span>
                      </>
                    )}
                  </div>
                  {status.speakerLocked && (
                    <Button
                      onClick={handleUnlockSpeaker}
                      disabled={isLoading}
                      size="sm"
                      variant="outline"
                    >
                      {isLoading ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <Unlock className="h-4 w-4 mr-2" />
                      )}
                      Force Unlock
                    </Button>
                  )}
                </div>
              </div>
            )}

            {/* TTS Test */}
            <div className="space-y-2 pt-2 border-t">
              <Button
                onClick={() => setShowTTSTest(true)}
                disabled={!status.connected}
                size="sm"
                variant="outline"
                className="w-full"
              >
                <TestTube className="h-4 w-4 mr-2" />
                Test TTS
              </Button>
            </div>

            {/* Plugin Configuration */}
            <div className="space-y-1 pt-2 border-t">
              <div className="text-xs text-muted-foreground">Configuration</div>
              <div className="text-xs space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Auto-join:</span>
                  <span>{agent.plugins.discord.auto_join ? 'Enabled' : 'Disabled'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Command Prefix:</span>
                  <span className="font-mono">{agent.plugins.discord.command_prefix}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* TTS Test Modal */}
      <TTSTestModal
        open={showTTSTest}
        onOpenChange={setShowTTSTest}
        agent={agent}
      />

      {/* Channel Selector Modal */}
      <ChannelSelectorModal
        open={showChannelSelector}
        onOpenChange={setShowChannelSelector}
        onSelect={handleChannelSelected}
        currentGuildId={undefined} // Backend doesn't expose guildId yet
        currentChannelId={undefined} // Not pre-selecting for now
      />
    </>
  );
}
