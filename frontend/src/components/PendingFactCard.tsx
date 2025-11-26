/**
 * PendingFactCard Component
 *
 * Displays a pending fact placeholder while fact extraction is in progress.
 * Shows real-time status updates (queued → processing → completed/failed).
 */

import { RefreshCw, XIcon, Clock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { PendingFact } from '@/services/memory';

interface PendingFactCardProps {
  pending: PendingFact;
  onRetry?: () => void;
  onCancel?: () => void;
}

export function PendingFactCard({ pending, onRetry, onCancel }: PendingFactCardProps) {
  return (
    <Card className="opacity-75 border-dashed border-primary/50 bg-muted/30">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="space-y-1 flex-1">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              {pending.fact_key}
              {pending.status === 'processing' && (
                <RefreshCw className="h-4 w-4 animate-spin text-blue-400" />
              )}
              {pending.status === 'queued' && (
                <Clock className="h-4 w-4 text-yellow-400" />
              )}
            </CardTitle>
            <p className="text-sm text-muted-foreground">{pending.fact_value}</p>
          </div>
          {pending.status === 'failed' && onRetry && onCancel && (
            <div className="flex gap-2 ml-4">
              <Button
                variant="ghost"
                size="icon"
                onClick={onRetry}
                title="Retry extraction"
                className="h-8 w-8"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={onCancel}
                title="Cancel and remove"
                className="h-8 w-8"
              >
                <XIcon className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex flex-wrap gap-2 text-xs">
          {/* Status Badge */}
          <Badge
            variant="outline"
            className={
              pending.status === 'queued'
                ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
                : pending.status === 'processing'
                ? 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                : 'bg-red-500/20 text-red-400 border-red-500/30'
            }
          >
            {pending.status === 'queued' && 'Queued for Processing'}
            {pending.status === 'processing' &&
              `Processing${pending.attempts ? ` (attempt ${pending.attempts})` : ''}`}
            {pending.status === 'failed' && 'Extraction Failed'}
          </Badge>

          {/* Importance Badge */}
          <Badge variant="outline" className="bg-primary/10">
            Importance: {(pending.importance * 100).toFixed(0)}%
          </Badge>

          {/* Scope Badge */}
          {pending.agent_id ? (
            <Badge variant="outline" className="bg-purple-500/10 text-purple-400">
              Agent-Specific
            </Badge>
          ) : (
            <Badge variant="outline" className="bg-green-500/10 text-green-400">
              Global
            </Badge>
          )}
        </div>

        {/* Error Message */}
        {pending.error && pending.status === 'failed' && (
          <div className="mt-3 p-2 rounded-md bg-destructive/10 border border-destructive/20">
            <p className="text-xs text-destructive font-medium">Error:</p>
            <p className="text-xs text-destructive/80 mt-1">{pending.error}</p>
          </div>
        )}

        {/* Fact Text Preview */}
        {pending.fact_text && (
          <p className="text-xs text-muted-foreground mt-3 italic border-l-2 border-primary/30 pl-2">
            {pending.fact_text}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
