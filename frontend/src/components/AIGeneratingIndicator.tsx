/**
 * AI Generating Indicator Component
 * Shows thinking animation and duration counter during AI response generation
 * VoxBridge 2.0 Phase 6.5.2: UX Behavior Unification
 */

import { useEffect, useState } from 'react';
import { Loader2, Brain } from 'lucide-react';

export interface AIGeneratingIndicatorProps {
  /** Whether AI is currently generating a response */
  isGenerating: boolean;
  /** Generation duration in milliseconds */
  duration: number;
}

export function AIGeneratingIndicator({
  isGenerating,
  duration,
}: AIGeneratingIndicatorProps) {
  const [dots, setDots] = useState('');

  // Animated dots for "Thinking..." text
  useEffect(() => {
    if (!isGenerating) return;

    const interval = setInterval(() => {
      setDots((prev) => {
        if (prev.length >= 3) return '';
        return prev + '.';
      });
    }, 500);

    return () => clearInterval(interval);
  }, [isGenerating]);

  // Format duration as seconds with decimal
  const formatDuration = (ms: number) => {
    const seconds = (ms / 1000).toFixed(1);
    return `${seconds}s`;
  };

  if (!isGenerating) return null;

  return (
    <div className="flex items-center gap-4 px-4 py-3 bg-purple-500/10 border-t border-purple-500/20 animate-in slide-in-from-bottom duration-300">
      {/* Brain Icon with Rotating Loader */}
      <div className="relative">
        <div className="absolute inset-0 rounded-full bg-purple-500/30 animate-pulse" />
        <div className="relative flex items-center justify-center w-10 h-10 rounded-full bg-purple-500/20">
          <Brain className="w-5 h-5 text-purple-400" />
          <Loader2 className="absolute w-8 h-8 text-purple-400/50 animate-spin" />
        </div>
      </div>

      {/* Text Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3">
          <p className="text-sm font-medium text-purple-400">
            Thinking{dots}
          </p>
          <span className="text-xs text-muted-foreground tabular-nums">
            {formatDuration(duration)}
          </span>
        </div>

        <p className="text-xs text-muted-foreground/60 mt-1">
          AI is generating a response...
        </p>
      </div>
    </div>
  );
}
