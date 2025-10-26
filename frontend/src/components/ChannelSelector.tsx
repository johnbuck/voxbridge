/**
 * Channel Selector Component
 * Dropdown to select and join Discord voice channels
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, type Guild } from '@/services/api';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Users } from 'lucide-react';

interface ChannelSelectorProps {
  onJoinSuccess?: () => void;
  onJoinError?: (error: Error) => void;
}

export function ChannelSelector({ onJoinSuccess, onJoinError }: ChannelSelectorProps) {
  const [selectedChannel, setSelectedChannel] = useState<{ channelId: string; guildId: string } | null>(null);
  const queryClient = useQueryClient();

  // Fetch available channels
  const { data, isLoading, error } = useQuery({
    queryKey: ['channels'],
    queryFn: () => api.getChannels(),
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  // Join channel mutation
  const joinMutation = useMutation({
    mutationFn: ({ channelId, guildId }: { channelId: string; guildId: string }) =>
      api.joinChannel(channelId, guildId),
    onSuccess: () => {
      // Invalidate status queries to reflect new connection state
      queryClient.invalidateQueries({ queryKey: ['health'] });
      queryClient.invalidateQueries({ queryKey: ['status'] });
      setSelectedChannel(null); // Clear selection
      onJoinSuccess?.();
    },
    onError: (err: Error) => {
      onJoinError?.(err);
    },
  });

  const handleJoin = () => {
    if (selectedChannel) {
      joinMutation.mutate(selectedChannel);
    }
  };

  const handleQuickConnect = () => {
    if (!data?.guilds || data.guilds.length === 0) return;

    // Try to find a channel with users first
    for (const guild of data.guilds) {
      const channelWithUsers = guild.channels.find(ch => ch.userCount > 0);
      if (channelWithUsers) {
        joinMutation.mutate({
          channelId: channelWithUsers.id,
          guildId: guild.id
        });
        return;
      }
    }

    // Otherwise, join the first available channel
    const firstGuild = data.guilds[0];
    if (firstGuild.channels.length > 0) {
      joinMutation.mutate({
        channelId: firstGuild.channels[0].id,
        guildId: firstGuild.id
      });
    }
  };

  const handleValueChange = (value: string) => {
    // Value format: "guildId:channelId"
    const [guildId, channelId] = value.split(':');
    setSelectedChannel({ channelId, guildId });
  };

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading channels...</p>;
  }

  if (error) {
    return <p className="text-sm text-destructive">Failed to load channels</p>;
  }

  if (!data?.guilds || data.guilds.length === 0) {
    return <p className="text-sm text-muted-foreground">No guilds available</p>;
  }

  return (
    <div className="space-y-2">
      {/* Quick Connect Button */}
      <Button
        onClick={handleQuickConnect}
        disabled={isLoading || joinMutation.isPending || !data?.guilds || data.guilds.length === 0}
        className="w-full font-semibold"
        size="lg"
      >
        {joinMutation.isPending ? 'Joining...' : 'Quick Connect'}
      </Button>

      {/* Manual Channel Selection */}
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <span className="w-full border-t" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-background px-2 text-muted-foreground">Or select manually</span>
        </div>
      </div>

      <Select onValueChange={handleValueChange}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Select a voice channel" />
        </SelectTrigger>
        <SelectContent>
          {data.guilds.map((guild: Guild) => (
            <SelectGroup key={guild.id}>
              <SelectLabel>{guild.name}</SelectLabel>
              {guild.channels.length > 0 ? (
                guild.channels.map((channel) => (
                  <SelectItem key={channel.id} value={`${guild.id}:${channel.id}`}>
                    <div className="flex items-center gap-2 w-full">
                      <span className="flex-1">{channel.name}</span>
                      {channel.userCount > 0 && (
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Users className="size-3" />
                          {channel.userCount}
                        </span>
                      )}
                    </div>
                  </SelectItem>
                ))
              ) : (
                <SelectItem value={`${guild.id}:empty`} disabled>
                  No voice channels
                </SelectItem>
              )}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>

      <Button
        onClick={handleJoin}
        disabled={!selectedChannel || joinMutation.isPending}
        className="w-full"
        variant="outline"
      >
        {joinMutation.isPending ? 'Joining...' : 'Join Selected Channel'}
      </Button>
    </div>
  );
}
