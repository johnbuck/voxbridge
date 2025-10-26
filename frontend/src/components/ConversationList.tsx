/**
 * ConversationList Component
 * ChatGPT-style sidebar showing past conversations
 * VoxBridge 2.0 Phase 4: Web Voice Interface
 */

import { useState } from 'react';
import type { Session } from '@/services/api';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { Plus, MessageSquare, Trash2, Calendar, Hash } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ConversationListProps {
  sessions: Session[];
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onCreateSession: () => void;
  onDeleteSession: (sessionId: string) => void;
  isLoading?: boolean;
}

export function ConversationList({
  sessions,
  activeSessionId,
  onSelectSession,
  onCreateSession,
  onDeleteSession,
  isLoading = false,
}: ConversationListProps) {
  const [hoveredSessionId, setHoveredSessionId] = useState<string | null>(null);

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

  return (
    <div className="flex flex-col h-full bg-card border-r border-border">
      {/* Header with New Conversation Button */}
      <div className="p-4 border-b border-border">
        <Button
          onClick={onCreateSession}
          className="w-full gap-2"
          size="sm"
        >
          <Plus className="h-4 w-4" />
          New Conversation
        </Button>
      </div>

      {/* Conversation List */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
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
                className="relative"
                onMouseEnter={() => setHoveredSessionId(session.id)}
                onMouseLeave={() => setHoveredSessionId(null)}
              >
                <button
                  onClick={() => onSelectSession(session.id)}
                  className={cn(
                    'w-full text-left p-3 rounded-lg transition-all duration-200',
                    'hover:bg-accent/50',
                    activeSessionId === session.id
                      ? 'bg-primary/10 border border-primary/30'
                      : 'bg-transparent border border-transparent'
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      {/* Title */}
                      <h3
                        className={cn(
                          'text-sm font-medium truncate mb-1',
                          activeSessionId === session.id
                            ? 'text-primary'
                            : 'text-foreground'
                        )}
                      >
                        {getSessionTitle(session)}
                      </h3>

                      {/* Metadata */}
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <Hash className="h-3 w-3" />
                          <span>{session.message_count}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          <span>{formatDate(session.started_at)}</span>
                        </div>
                      </div>

                      {/* Active Badge */}
                      {session.active && (
                        <div className="mt-1">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-green-500/10 text-green-400 border border-green-500/20">
                            <div className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
                            Active
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Delete Button (on hover) */}
                    {hoveredSessionId === session.id && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteSession(session.id);
                        }}
                        title="Delete conversation"
                      >
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </Button>
                    )}
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
