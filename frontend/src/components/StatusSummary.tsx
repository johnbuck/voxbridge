/**
 * StatusSummary Component
 * Displays summary statistics like Chatterbox TTS
 * Shows GPU device, transcript count, success rate, and average latencies
 */

import { Wifi, WifiOff } from 'lucide-react';

interface Metrics {
  transcriptCount: number;
  errorRate: number;
  uptime: number;
  timeToFirstAudio: {
    avg: number;
  };
  totalPipelineLatency: {
    avg: number;
  };
}

interface StatusSummaryProps {
  metrics: Metrics | undefined;
  isLoadingMetrics?: boolean;
  wsConnected: boolean;
}

export function StatusSummary({ metrics, isLoadingMetrics, wsConnected }: StatusSummaryProps) {
  // Don't render anything if no data yet
  if (!metrics || isLoadingMetrics) {
    return null;
  }

  const formatUptime = (seconds: number): string => {
    if (seconds === 0) return '–';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  };

  // Format individual metrics with en dash (–) for zero values
  const transcripts = metrics.transcriptCount > 0
    ? `${metrics.transcriptCount} transcripts`
    : '– transcripts';

  const errorRate = metrics.errorRate * 100;
  const errors = errorRate > 0
    ? `${errorRate.toFixed(1)}% errors`
    : '–% errors';

  const firstAudio = metrics.timeToFirstAudio?.avg > 0
    ? `${metrics.timeToFirstAudio.avg.toFixed(1)}s first audio`
    : '–s first audio';

  const total = metrics.totalPipelineLatency?.avg > 0
    ? `${metrics.totalPipelineLatency.avg.toFixed(1)}s total`
    : '–s total';

  const uptime = `${formatUptime(metrics.uptime)} uptime`;

  const statusColor = wsConnected ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400';
  const StatusIcon = wsConnected ? Wifi : WifiOff;
  const statusText = wsConnected ? 'Ready' : 'Not Ready';

  return (
    <div className="text-center">
      {/* Line 1: Icon + Ready + first 3 metrics */}
      <div className={`inline-flex items-center gap-2 text-sm ${statusColor}`}>
        <StatusIcon className="w-4 h-4" />
        <span className="font-medium">{statusText}</span>
        <span>•</span>
        <span className="text-muted-foreground">
          {transcripts} • {errors} • {firstAudio}
        </span>
      </div>

      {/* Line 2: Last 2 metrics */}
      <div className="text-sm text-muted-foreground mt-1">
        {total} • {uptime}
      </div>
    </div>
  );
}
