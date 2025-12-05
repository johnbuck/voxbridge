/**
 * FactCard Component
 * Displays a single fact with edit/delete actions
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Pencil, Trash2, Clock, Database, Bot, Globe, Folder, Briefcase, Users, Heart, Activity, Star, CalendarDays, Layers, Shield, RefreshCw } from 'lucide-react';
import type { UserFact } from '@/services/memory';
import type { Agent } from '@/services/api';

/**
 * Format a date as relative time (e.g., "2 days ago", "3 hours ago")
 */
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  const diffWeeks = Math.floor(diffDays / 7);
  const diffMonths = Math.floor(diffDays / 30);

  if (diffSecs < 60) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffWeeks < 4) return `${diffWeeks}w ago`;
  if (diffMonths < 12) return `${diffMonths}mo ago`;
  return `${Math.floor(diffMonths / 12)}y ago`;
}

/**
 * Format a full date for tooltip display
 */
function formatFullDate(dateString: string): string {
  return new Date(dateString).toLocaleString();
}

interface FactCardProps {
  fact: UserFact;
  onEdit: (fact: UserFact) => void;
  onDelete: (factId: string) => void;
  agents?: Agent[];
}

export function FactCard({ fact, onEdit, onDelete, agents }: FactCardProps) {
  const [isDeleting, setIsDeleting] = useState(false);

  // Look up agent name from agent_id
  const agentName = fact.agent_id
    ? agents?.find((a) => a.id === fact.agent_id)?.name
    : null;

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this fact? This action cannot be undone.')) {
      return;
    }

    setIsDeleting(true);
    try {
      await onDelete(fact.id);
    } finally {
      setIsDeleting(false);
    }
  };

  const importanceColor =
    fact.importance >= 0.8
      ? 'bg-green-500/20 text-green-400 border-green-500/50'
      : fact.importance >= 0.5
      ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50'
      : 'bg-gray-500/20 text-gray-400 border-gray-500/50';

  return (
    <Card className="hover:border-primary/50 transition-colors">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="space-y-1 flex-1">
            <CardTitle className="text-lg font-semibold">{fact.fact_key}</CardTitle>
            <p className="text-sm text-muted-foreground">{fact.fact_value}</p>
          </div>
          <div className="flex gap-2 ml-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onEdit(fact)}
              title="Edit fact"
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleDelete}
              disabled={isDeleting}
              title="Delete fact"
              className="text-destructive hover:text-destructive/80"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex flex-wrap gap-2 text-xs">
          {/* Importance Badge */}
          <Badge variant="outline" className={importanceColor}>
            Importance: {(fact.importance * 100).toFixed(0)}%
          </Badge>

          {/* Scope Badge */}
          {fact.agent_id ? (
            <Badge variant="outline" className="gap-1 bg-purple-500/20 text-purple-400 border-purple-500/50">
              <Bot className="h-3 w-3" />
              {agentName || 'Agent-Specific'}
            </Badge>
          ) : (
            <Badge variant="outline" className="gap-1 bg-blue-500/20 text-blue-400 border-blue-500/50">
              <Globe className="h-3 w-3" />
              Global
            </Badge>
          )}

          {/* Memory Bank Badge */}
          {fact.memory_bank === 'Personal' && (
            <Badge variant="outline" className="gap-1 bg-pink-500/20 text-pink-400 border-pink-500/50">
              <Users className="h-3 w-3" />
              Personal
            </Badge>
          )}
          {fact.memory_bank === 'Work' && (
            <Badge variant="outline" className="gap-1 bg-amber-500/20 text-amber-400 border-amber-500/50">
              <Briefcase className="h-3 w-3" />
              Work
            </Badge>
          )}
          {fact.memory_bank === 'General' && (
            <Badge variant="outline" className="gap-1 bg-slate-500/20 text-slate-400 border-slate-500/50">
              <Folder className="h-3 w-3" />
              General
            </Badge>
          )}
          {fact.memory_bank === 'Relationships' && (
            <Badge variant="outline" className="gap-1 bg-rose-500/20 text-rose-400 border-rose-500/50">
              <Heart className="h-3 w-3" />
              Relationships
            </Badge>
          )}
          {fact.memory_bank === 'Health' && (
            <Badge variant="outline" className="gap-1 bg-emerald-500/20 text-emerald-400 border-emerald-500/50">
              <Activity className="h-3 w-3" />
              Health
            </Badge>
          )}
          {fact.memory_bank === 'Interests' && (
            <Badge variant="outline" className="gap-1 bg-violet-500/20 text-violet-400 border-violet-500/50">
              <Star className="h-3 w-3" />
              Interests
            </Badge>
          )}
          {fact.memory_bank === 'Events' && (
            <Badge variant="outline" className="gap-1 bg-cyan-500/20 text-cyan-400 border-cyan-500/50">
              <CalendarDays className="h-3 w-3" />
              Events
            </Badge>
          )}

          {/* Summarized Badge (Phase 3) */}
          {fact.is_summarized && (
            <Badge variant="outline" className="gap-1 bg-indigo-500/20 text-indigo-400 border-indigo-500/50">
              <Layers className="h-3 w-3" />
              Summarized{fact.summarized_from ? ` (${fact.summarized_from.length})` : ''}
            </Badge>
          )}

          {/* Protected Badge (Phase 2) */}
          {fact.is_protected && (
            <Badge variant="outline" className="gap-1 bg-amber-500/20 text-amber-400 border-amber-500/50">
              <Shield className="h-3 w-3" />
              Protected
            </Badge>
          )}

          {/* Validity Badge */}
          {!fact.is_valid && <Badge variant="destructive">Expired</Badge>}

          {/* Created Date - with relative time and tooltip */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge variant="secondary" className="gap-1 cursor-help">
                  <Clock className="h-3 w-3" />
                  {formatRelativeTime(fact.created_at)}
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                <p>Created: {formatFullDate(fact.created_at)}</p>
                {fact.updated_at && fact.updated_at !== fact.created_at && (
                  <p>Updated: {formatFullDate(fact.updated_at)}</p>
                )}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>

          {/* Updated indicator - show if fact was modified */}
          {fact.updated_at && fact.updated_at !== fact.created_at && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge variant="outline" className="gap-1 cursor-help bg-blue-500/10 text-blue-400 border-blue-500/30">
                    <RefreshCw className="h-3 w-3" />
                    edited
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Last updated: {formatFullDate(fact.updated_at)}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}

          {/* Embedding Provider */}
          {fact.embedding_provider && (
            <Badge variant="secondary" className="gap-1">
              <Database className="h-3 w-3" />
              {fact.embedding_provider}
            </Badge>
          )}
        </div>

        {/* Optional fact text (natural language) */}
        {fact.fact_text && fact.fact_text !== `${fact.fact_key}: ${fact.fact_value}` && (
          <p className="text-xs text-muted-foreground mt-3 italic">{fact.fact_text}</p>
        )}

        {/* Embedding Model */}
        {fact.embedding_model && (
          <p className="text-xs text-muted-foreground mt-2">
            Model: {fact.embedding_model}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
