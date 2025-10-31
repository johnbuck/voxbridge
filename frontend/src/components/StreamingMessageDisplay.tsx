/**
 * Streaming Message Display Component
 * Shows AI response chunks in real-time with typewriter effect
 * VoxBridge 2.0 Phase 6.5.2: UX Behavior Unification
 */

import { useEffect, useRef } from 'react';
import { Brain } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface StreamingMessageDisplayProps {
  /** Array of text chunks (appended in real-time) */
  chunks: string[];
  /** Whether more chunks are incoming */
  isStreaming: boolean;
  /** Agent name for display */
  agentName?: string;
  /** Optional CSS class name */
  className?: string;
}

export function StreamingMessageDisplay({
  chunks,
  isStreaming,
  agentName = 'AI Assistant',
  className,
}: StreamingMessageDisplayProps) {
  const messageRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new chunks arrive
  useEffect(() => {
    if (messageRef.current) {
      messageRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [chunks]);

  // Don't render if no chunks
  if (chunks.length === 0) return null;

  const fullText = chunks.join('');

  return (
    <div
      ref={messageRef}
      className={cn(
        'flex justify-end animate-in fade-in slide-in-from-bottom-2 duration-300',
        className
      )}
    >
      <div className="max-w-[80%] p-4 rounded-lg bg-purple-500/10 border border-purple-500/20">
        {/* Header */}
        <div className="flex items-center gap-2 mb-2">
          <Brain className="w-4 h-4 text-purple-400" />
          <span className="text-xs font-medium text-purple-400">
            {agentName}
          </span>
          {isStreaming && (
            <span className="text-xs text-muted-foreground italic animate-pulse">
              (streaming...)
            </span>
          )}
        </div>

        {/* Streaming Text Content with Typewriter Effect */}
        <div className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
          {fullText}
          {isStreaming && (
            <span className="inline-block w-2 h-4 ml-1 bg-purple-400 animate-pulse" />
          )}
        </div>

        {/* Streaming indicator dots */}
        {isStreaming && (
          <div className="mt-2 flex gap-1">
            <div className="w-2 h-2 rounded-full bg-purple-400/60 animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-2 h-2 rounded-full bg-purple-400/60 animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-2 h-2 rounded-full bg-purple-400/60 animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        )}
      </div>
    </div>
  );
}
