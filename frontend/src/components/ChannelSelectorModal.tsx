/**
 * Channel Selector Modal Component
 * Modal dialog for selecting Discord guild and voice channel
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Loader2, Users, Radio } from 'lucide-react';
import { api, type Guild, type VoiceChannel } from '@/services/api';
import { cn } from '@/lib/utils';

interface ChannelSelectorModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (guildId: string, channelId: string) => void;
  currentGuildId?: string;
  currentChannelId?: string;
}

export function ChannelSelectorModal({
  open,
  onOpenChange,
  onSelect,
  currentGuildId,
  currentChannelId,
}: ChannelSelectorModalProps) {
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [selectedGuildId, setSelectedGuildId] = useState<string | null>(currentGuildId || null);
  const [selectedChannelId, setSelectedChannelId] = useState<string | null>(currentChannelId || null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch guilds and channels when modal opens
  useEffect(() => {
    if (open) {
      fetchChannels();
    }
  }, [open]);

  // Pre-select current guild/channel when provided
  useEffect(() => {
    if (currentGuildId) {
      setSelectedGuildId(currentGuildId);
    }
    if (currentChannelId) {
      setSelectedChannelId(currentChannelId);
    }
  }, [currentGuildId, currentChannelId]);

  const fetchChannels = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.getChannels();
      setGuilds(response.guilds);

      // Auto-select first guild if none selected
      if (!selectedGuildId && response.guilds.length > 0) {
        setSelectedGuildId(response.guilds[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch channels:', err);
      setError(err instanceof Error ? err.message : 'Failed to load channels');
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirm = () => {
    if (selectedGuildId && selectedChannelId) {
      onSelect(selectedGuildId, selectedChannelId);
    }
  };

  const handleGuildSelect = (guildId: string) => {
    setSelectedGuildId(guildId);
    // Clear channel selection when guild changes
    setSelectedChannelId(null);
  };

  const handleChannelSelect = (channelId: string) => {
    setSelectedChannelId(channelId);
  };

  // Get currently selected guild
  const selectedGuild = guilds.find((g) => g.id === selectedGuildId);

  // Check if selection is complete
  const isSelectionComplete = selectedGuildId && selectedChannelId;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] sm:max-h-[85vh]">
        <DialogHeader>
          <DialogTitle>Select Voice Channel</DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">Loading channels...</span>
          </div>
        ) : error ? (
          <div className="py-8 text-center">
            <p className="text-destructive mb-4">{error}</p>
            <Button onClick={fetchChannels} variant="outline">
              Retry
            </Button>
          </div>
        ) : guilds.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground">
            <p>No Discord servers found.</p>
            <p className="text-sm mt-2">
              Make sure the bot is added to at least one Discord server.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Guild Selection */}
            <div className="space-y-2">
              <Label>Server</Label>
              <ScrollArea className="h-[200px] sm:h-[300px] rounded-md border">
                <div className="p-2 space-y-1">
                  {guilds.map((guild) => (
                    <button
                      key={guild.id}
                      onClick={() => handleGuildSelect(guild.id)}
                      className={cn(
                        'w-full text-left px-3 py-2 rounded-md text-sm transition-colors',
                        'hover:bg-muted',
                        selectedGuildId === guild.id
                          ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                          : 'bg-background'
                      )}
                    >
                      <div className="font-medium truncate">{guild.name}</div>
                      <div className="text-xs opacity-70 mt-0.5">
                        {guild.channels.length} voice channel{guild.channels.length !== 1 ? 's' : ''}
                      </div>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            </div>

            {/* Channel Selection */}
            <div className="space-y-2">
              <Label>Voice Channel</Label>
              <ScrollArea className="h-[200px] sm:h-[300px] rounded-md border">
                {selectedGuild ? (
                  selectedGuild.channels.length > 0 ? (
                    <div className="p-2 space-y-1">
                      {selectedGuild.channels.map((channel: VoiceChannel) => (
                        <button
                          key={channel.id}
                          onClick={() => handleChannelSelect(channel.id)}
                          className={cn(
                            'w-full text-left px-3 py-2 rounded-md text-sm transition-colors',
                            'hover:bg-muted',
                            selectedChannelId === channel.id
                              ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                              : 'bg-background'
                          )}
                        >
                          <div className="flex items-center gap-2">
                            <Radio className="h-4 w-4 flex-shrink-0" />
                            <span className="font-medium truncate flex-1">{channel.name}</span>
                            <div className="flex items-center gap-1 text-xs opacity-70 flex-shrink-0">
                              <Users className="h-3 w-3" />
                              <span>{channel.userCount}</span>
                            </div>
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="flex items-center justify-center h-full text-sm text-muted-foreground p-4 text-center">
                      No voice channels in this server
                    </div>
                  )
                ) : (
                  <div className="flex items-center justify-center h-full text-sm text-muted-foreground p-4 text-center">
                    Select a server to view channels
                  </div>
                )}
              </ScrollArea>
            </div>
          </div>
        )}

        <DialogFooter className="flex-col-reverse sm:flex-row gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            className="w-full sm:w-auto"
          >
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!isSelectionComplete || isLoading}
            className="w-full sm:w-auto"
          >
            Join Channel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
