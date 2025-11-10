/**
 * Audio Controls Component
 * Microphone mute/unmute control
 * VoxBridge 2.0: Discord-style persistent connection (no connection status indicators)
 */

import { Mic, MicOff, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface AudioControlsProps {
  isMuted: boolean;
  onToggleMute: () => void;
  permissionError: string | null;
  isRecording: boolean;
  /** Disable mic button (e.g., during AI generation) */
  disabled?: boolean;
}

export function AudioControls({
  isMuted,
  onToggleMute,
  permissionError,
  isRecording,
  disabled = false,
}: AudioControlsProps) {
  return (
    <div className="flex items-center gap-3">
      {/* Microphone Button */}
      <div className="relative">
        <Button
          variant={isMuted ? 'outline' : 'default'}
          size="icon"
          onClick={onToggleMute}
          title={
            disabled
              ? 'Microphone disabled during AI generation'
              : isMuted
              ? 'Unmute microphone'
              : 'Mute microphone'
          }
          className={cn(
            'transition-all duration-200',
            !isMuted && 'bg-red-500 hover:bg-red-600 border-red-500',
            isRecording && !isMuted && 'animate-pulse',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
          disabled={disabled}
        >
          {isMuted ? (
            <MicOff className="h-4 w-4" />
          ) : (
            <Mic className="h-4 w-4" />
          )}
        </Button>

        {/* Recording indicator pulse (enhanced with red glow) */}
        {isRecording && !isMuted && (
          <>
            <div className="absolute -inset-1 rounded-lg bg-red-500/30 animate-ping pointer-events-none" />
            <div className="absolute -inset-2 rounded-lg bg-red-500/20 blur-md animate-pulse pointer-events-none" />
          </>
        )}
      </div>

      {/* Permission Error Indicator */}
      {permissionError && (
        <div className="flex items-center gap-2 text-red-500 text-sm">
          <AlertCircle className="h-4 w-4" />
          <span className="max-w-[200px] truncate" title={permissionError}>
            Permission denied
          </span>
        </div>
      )}
    </div>
  );
}
