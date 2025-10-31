/**
 * STT Waiting Indicator Component
 * Shows microphone pulse animation, partial transcript, and recording duration
 * VoxBridge 2.0 Phase 6.5.2: UX Behavior Unification
 */

import { useEffect, useState } from 'react';
import { Mic } from 'lucide-react';

export interface STTWaitingIndicatorProps {
  /** Whether currently listening/recording */
  isListening: boolean;
  /** Recording duration in milliseconds */
  duration: number;
  /** Partial transcript text (live transcription) */
  partialTranscript?: string;
}

export function STTWaitingIndicator({
  isListening,
  duration,
  partialTranscript,
}: STTWaitingIndicatorProps) {
  const [dots, setDots] = useState('');

  // Animated dots for "Listening..." text
  useEffect(() => {
    if (!isListening) return;

    const interval = setInterval(() => {
      setDots((prev) => {
        if (prev.length >= 3) return '';
        return prev + '.';
      });
    }, 500);

    return () => clearInterval(interval);
  }, [isListening]);

  // Format duration as MM:SS
  const formatDuration = (ms: number) => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  if (!isListening) return null;

  return (
    <div className="flex items-center gap-4 px-4 py-3 bg-primary/10 border-t border-primary/20 animate-in slide-in-from-bottom duration-300">
      {/* Microphone Icon with Pulse Animation */}
      <div className="relative">
        <div className="absolute inset-0 rounded-full bg-primary/30 animate-ping" />
        <div className="relative flex items-center justify-center w-10 h-10 rounded-full bg-primary/20 animate-pulse">
          <Mic className="w-5 h-5 text-primary" />
        </div>
      </div>

      {/* Text Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3 mb-1">
          <p className="text-sm font-medium text-primary">
            Listening{dots}
          </p>
          <span className="text-xs text-muted-foreground tabular-nums">
            {formatDuration(duration)}
          </span>
        </div>

        {/* Partial Transcript (Live Transcription) */}
        {partialTranscript && (
          <p className="text-sm text-muted-foreground italic animate-in fade-in duration-200">
            {partialTranscript}
          </p>
        )}

        {!partialTranscript && (
          <p className="text-xs text-muted-foreground/60">
            Start speaking...
          </p>
        )}
      </div>
    </div>
  );
}
