/**
 * Audio Controls Component
 * Microphone mute/unmute with connection status
 * VoxBridge 2.0 Phase 4: Web Voice Interface
 */

import { Mic, MicOff, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ConnectionState } from '@/hooks/useWebRTCAudio';

export interface AudioControlsProps {
  isMuted: boolean;
  onToggleMute: () => void;
  connectionState: ConnectionState;
  permissionError: string | null;
  isRecording: boolean;
}

export function AudioControls({
  isMuted,
  onToggleMute,
  connectionState,
  permissionError,
  isRecording,
}: AudioControlsProps) {
  // Connection status badge
  const getConnectionBadge = () => {
    switch (connectionState) {
      case 'connected':
        return (
          <Badge variant="outline" className="border-green-500/50 bg-green-500/10 text-green-500">
            <div className="w-2 h-2 rounded-full bg-green-500 mr-1 animate-pulse" />
            Connected
          </Badge>
        );
      case 'connecting':
        return (
          <Badge variant="outline" className="border-yellow-500/50 bg-yellow-500/10 text-yellow-500">
            <div className="w-2 h-2 rounded-full bg-yellow-500 mr-1 animate-pulse" />
            Connecting...
          </Badge>
        );
      case 'disconnected':
        return (
          <Badge variant="outline" className="border-gray-500/50 bg-gray-500/10 text-gray-500">
            <div className="w-2 h-2 rounded-full bg-gray-500 mr-1" />
            Disconnected
          </Badge>
        );
      case 'error':
        return (
          <Badge variant="outline" className="border-red-500/50 bg-red-500/10 text-red-500">
            <AlertCircle className="w-3 h-3 mr-1" />
            Error
          </Badge>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex items-center gap-3">
      {/* Connection Status */}
      {getConnectionBadge()}

      {/* Microphone Button */}
      <div className="relative">
        <Button
          variant={isMuted ? 'outline' : 'default'}
          size="icon"
          onClick={onToggleMute}
          title={isMuted ? 'Unmute microphone' : 'Mute microphone'}
          className={cn(
            'transition-all duration-200',
            !isMuted && 'bg-red-500 hover:bg-red-600 border-red-500',
            isRecording && !isMuted && 'animate-pulse'
          )}
          disabled={connectionState === 'connecting'}
        >
          {isMuted ? (
            <MicOff className="h-4 w-4" />
          ) : (
            <Mic className="h-4 w-4" />
          )}
        </Button>

        {/* Recording indicator pulse */}
        {isRecording && !isMuted && (
          <div className="absolute -inset-1 rounded-lg bg-red-500/30 animate-ping pointer-events-none" />
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
