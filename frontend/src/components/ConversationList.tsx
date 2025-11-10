/**
 * ConversationList Component
 * ChatGPT-style sidebar showing past conversations
 * VoxBridge 2.0: Discord-style persistent connection with "Leave Voice" button
 */

import type { Session } from '@/services/api';
import type { ConnectionState } from '@/types/webrtc';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Plus, MessageSquare, Trash2, Calendar, Hash, Globe, MessageCircle, LogOut } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ConversationListProps {
  sessions: Session[];
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onCreateSession: () => void;
  onDeleteSession: (sessionId: string) => void;
  isLoading?: boolean;
  // Discord-style: Connection state and Leave Voice button
  connectionState: ConnectionState;
  onLeaveVoice: () => void;
}

export function ConversationList({
  sessions,
  activeSessionId,
  onSelectSession,
  onCreateSession,
  onDeleteSession,
  isLoading = false,
  connectionState,
  onLeaveVoice,
}: ConversationListProps) {
  // Hover state removed - delete button now always visible for debugging

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const getSessionTitle = (session: Session) => {
    if (session.title) return session.title;
    return `Conversation ${new Date(session.started_at).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })}`;
  };

  const getSessionSourceInfo = (session: Session) => {
    // Determine if this is a web or Discord session
    const isWebSession = session.user_id === 'web_user_default' || session.session_type === 'web';
    const isDiscordSession = session.session_type === 'discord' || (!isWebSession && session.user_id !== 'web_user_default');

    if (isWebSession) {
      return {
        icon: Globe,
        label: 'Web',
        className: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
      };
    } else if (isDiscordSession) {
      return {
        icon: MessageCircle,
        label: 'Discord',
        className: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
        userId: session.user_id, // Show Discord user ID
      };
    }

    // Fallback for unknown session types
    return {
      icon: MessageSquare,
      label: session.session_type || 'Unknown',
      className: 'bg-muted text-muted-foreground border-border',
    };
  };

  return (
    <div className="flex flex-col h-full w-full bg-card border-r border-border">
      {/* Header with New Conversation + Leave Voice Buttons */}
      <div className="p-4 border-b border-border w-full flex gap-2">
        <Button
          onClick={onCreateSession}
          className="flex-1 gap-2"
          size="sm"
        >
          <Plus className="h-4 w-4" />
          New Conversation
        </Button>

        {/* Discord-style: Leave Voice button (icon-only, right side) */}
        {connectionState === 'connected' && (
          <Button
            onClick={onLeaveVoice}
            variant="destructive"
            className="shrink-0"
            size="sm"
            title="Leave Voice - End voice session and disconnect"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Conversation List */}
      <ScrollArea className="flex-1 w-full">
        <div className="p-2 space-y-1 w-full">
          {isLoading ? (
            <div className="text-center py-8 text-muted-foreground">
              <p className="text-sm">Loading conversations...</p>
            </div>
          ) : sessions.length === 0 ? (
            <div className="text-center py-8 px-4 text-muted-foreground">
              <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <p className="text-sm">No conversations yet</p>
              <p className="text-xs mt-1">Click &quot;New Conversation&quot; to start</p>
            </div>
          ) : (
            sessions.map((session) => (
              <div
                key={session.id}
                className="relative w-full"
              >
                <button
                  onClick={() => onSelectSession(session.id)}
                  className={cn(
                    'w-full text-left p-2 rounded-lg transition-all duration-200',
                    'hover:bg-accent/50',
                    activeSessionId === session.id
                      ? 'bg-primary/10 border border-primary/30'
                      : 'bg-transparent border border-transparent'
                  )}
                >
                  {/* Compact 2-row layout to fit in 320px */}
                  <div className="flex flex-col gap-1">
                    {/* Row 1: Title + Badge + Delete Button */}
                    <div className="flex items-center gap-2">
                      <h3
                        className={cn(
                          'text-sm font-medium truncate max-w-[140px]',
                          activeSessionId === session.id
                            ? 'text-primary'
                            : 'text-foreground'
                        )}
                        title={getSessionTitle(session)}
                      >
                        {getSessionTitle(session)}
                      </h3>
                      {(() => {
                        const sourceInfo = getSessionSourceInfo(session);
                        const SourceIcon = sourceInfo.icon;
                        return (
                          <Badge
                            variant="outline"
                            className={cn('text-xs h-4 px-1 shrink-0', sourceInfo.className)}
                            title={sourceInfo.label}
                          >
                            <SourceIcon className="h-3 w-3" />
                          </Badge>
                        );
                      })()}
                      <div className="flex-1" />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteSession(session.id);
                        }}
                        title="Delete conversation"
                      >
                        <Trash2 className="h-3 w-3 text-destructive" />
                      </Button>
                    </div>

                    {/* Row 2: Metadata + Voice Active Badge */}
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <Hash className="h-3 w-3" />
                        <span>{session.message_count}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        <span>{formatDate(session.started_at)}</span>
                      </div>
                      {/* Discord-style: Voice Active only when this session is selected AND voice is connected */}
                      {activeSessionId === session.id && connectionState === 'connected' && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs bg-green-500/10 text-green-400 border border-green-500/20">
                          <div className="w-1 h-1 bg-green-500 rounded-full animate-pulse" />
                          Voice Active
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
