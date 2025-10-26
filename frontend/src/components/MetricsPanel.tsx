/**
 * Metrics Panel Component
 * Displays latency metrics and performance stats with Recharts visualization
 * Chatterbox-style single card with sectioned content
 */

import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { BarChart3, Zap, Mic, Brain, Volume2, Play, Timer } from 'lucide-react';

interface MetricsDataPoint {
  timestamp: string;
  timeToFirstAudio: number;
  totalResponseTime: number;
  aiGeneration: number;
  ttsGeneration: number;
}

// Helper function to determine color based on performance thresholds
const getLatencyColor = (value: number, metricType: 'critical' | 'fast' | 'moderate' | 'slow'): string => {
  if (!value || value === 0) return 'text-muted-foreground';

  // Thresholds based on metric type (relaxed for complex AI pipeline)
  const thresholds = {
    critical: { good: 2, moderate: 4 }, // Time to First Audio: <2s green, 2-4s yellow, >4s red
    fast: { good: 1, moderate: 2 },     // Fast metrics (first partial, silence detection)
    moderate: { good: 3, moderate: 5 }, // Moderate metrics (transcription, TTS queue)
    slow: { good: 5, moderate: 8 }      // Slow metrics (Total Pipeline, AI generation)
  };

  const t = thresholds[metricType];

  if (value < t.good) {
    return 'text-green-600 dark:text-green-400';
  } else if (value < t.moderate) {
    return 'text-yellow-600 dark:text-yellow-500';
  } else {
    return 'text-red-600 dark:text-red-400';
  }
};

// Format latency values consistently
const formatLatency = (seconds: number, isMilliseconds: boolean = false): string => {
  if (isMilliseconds) {
    return `${seconds.toFixed(0)}ms`;
  }
  return `${seconds.toFixed(3)}s`;
};

// Format uptime (copied from original)
const formatUptime = (seconds: number): string => {
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

export function MetricsPanel() {
  const [metricsHistory, setMetricsHistory] = useState<MetricsDataPoint[]>([]);
  const maxDataPoints = 20; // Keep last 20 data points

  // Fetch metrics (triggered by Dashboard after AI response completion)
  const { data: metrics } = useQuery({
    queryKey: ['metrics'],
    queryFn: () => api.getMetrics(),
    // No automatic polling - only refetch after user interactions
  });

  // Update metrics history when new data arrives
  useEffect(() => {
    if (metrics) {
      const now = new Date();
      const timestamp = now.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });

      setMetricsHistory((prev) => {
        // Don't add duplicate data points (same timestamp)
        if (prev.length > 0 && prev[prev.length - 1].timestamp === timestamp) {
          return prev;
        }

        const newData = [
          ...prev,
          {
            timestamp,
            timeToFirstAudio: metrics.timeToFirstAudio.avg,
            totalResponseTime: metrics.totalPipelineLatency.avg,
            aiGeneration: metrics.aiGenerationLatency.avg,
            ttsGeneration: metrics.ttsGenerationLatency.avg,
          },
        ];

        console.log('[MetricsPanel] Added data point:', {
          timestamp,
          dataPoints: newData.length,
          timeToFirstAudio: metrics.timeToFirstAudio.avg,
          totalResponseTime: metrics.totalPipelineLatency.avg
        });

        // Keep only the last N data points
        return newData.slice(-maxDataPoints);
      });
    }
  }, [metrics]);

  return (
    <Card className="w-full max-w-6xl">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <BarChart3 className="w-4 h-4" />
          Performance Metrics
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-0">

        {/* SECTION 1: Latency Trend Chart (TOP PRIORITY) */}
        <div className="pb-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs text-muted-foreground font-medium">Response Latency Over Time</span>
          </div>
          {metricsHistory.length > 0 ? (
            <div style={{ width: '100%', height: '250px' }}>
              <ResponsiveContainer>
                <LineChart data={metricsHistory}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" opacity={0.2} />
                  <XAxis
                    dataKey="timestamp"
                    tick={{ fontSize: 12 }}
                    stroke="var(--color-border)"
                  />
                  <YAxis
                    label={{
                      value: 'Latency (s)',
                      angle: -90,
                      position: 'insideLeft'
                    }}
                    tick={{ fontSize: 12 }}
                    stroke="var(--color-border)"
                  />
                  <Tooltip />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="timeToFirstAudio"
                    stroke="var(--color-chart-1)"
                    strokeWidth={3}
                    dot={false}
                    name="Time to First Audio"
                  />
                  <Line
                    type="monotone"
                    dataKey="totalResponseTime"
                    stroke="var(--color-chart-2)"
                    strokeWidth={2}
                    dot={false}
                    name="Total Response Time"
                  />
                  <Line
                    type="monotone"
                    dataKey="aiGeneration"
                    stroke="var(--color-chart-3)"
                    strokeWidth={2}
                    dot={false}
                    name="AI Generation"
                  />
                  <Line
                    type="monotone"
                    dataKey="ttsGeneration"
                    stroke="var(--color-chart-4)"
                    strokeWidth={2}
                    dot={false}
                    name="TTS Generation"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-muted-foreground">
              <p className="text-sm">Waiting for metrics data...</p>
            </div>
          )}
        </div>

        {/* SECTION 2: Critical UX Metrics */}
        <div className="border-t pt-3">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground font-medium">Critical UX Metrics (Perceived Latency)</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Time to First Audio */}
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">Time to First Audio</div>
              <div className={`text-3xl font-bold ${getLatencyColor(metrics?.timeToFirstAudio?.avg || 0, 'critical')}`}>
                {formatLatency(metrics?.timeToFirstAudio?.avg || 0)}
              </div>
              <div className="flex gap-2 text-xs flex-wrap">
                <span className={`px-2 py-0.5 rounded ${getLatencyColor(metrics?.timeToFirstAudio?.p50 || 0, 'critical')} bg-opacity-10`}>
                  P50: {formatLatency(metrics?.timeToFirstAudio?.p50 || 0)}
                </span>
                <span className={`px-2 py-0.5 rounded ${getLatencyColor(metrics?.timeToFirstAudio?.p95 || 0, 'critical')} bg-opacity-10`}>
                  P95: {formatLatency(metrics?.timeToFirstAudio?.p95 || 0)}
                </span>
                <span className={`px-2 py-0.5 rounded ${getLatencyColor(metrics?.timeToFirstAudio?.p99 || 0, 'critical')} bg-opacity-10`}>
                  P99: {formatLatency(metrics?.timeToFirstAudio?.p99 || 0)}
                </span>
              </div>
              <div className="text-xs text-muted-foreground">
                User stops speaking → First audio byte
              </div>
            </div>

            {/* Total Pipeline Latency */}
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">Total Response Time</div>
              <div className={`text-3xl font-bold ${getLatencyColor(metrics?.totalPipelineLatency?.avg || 0, 'slow')}`}>
                {formatLatency(metrics?.totalPipelineLatency?.avg || 0)}
              </div>
              <div className="flex gap-2 text-xs flex-wrap">
                <span className={`px-2 py-0.5 rounded ${getLatencyColor(metrics?.totalPipelineLatency?.p50 || 0, 'slow')} bg-opacity-10`}>
                  P50: {formatLatency(metrics?.totalPipelineLatency?.p50 || 0)}
                </span>
                <span className={`px-2 py-0.5 rounded ${getLatencyColor(metrics?.totalPipelineLatency?.p95 || 0, 'slow')} bg-opacity-10`}>
                  P95: {formatLatency(metrics?.totalPipelineLatency?.p95 || 0)}
                </span>
                <span className={`px-2 py-0.5 rounded ${getLatencyColor(metrics?.totalPipelineLatency?.p99 || 0, 'slow')} bg-opacity-10`}>
                  P99: {formatLatency(metrics?.totalPipelineLatency?.p99 || 0)}
                </span>
              </div>
              <div className="text-xs text-muted-foreground">
                User stops speaking → Response complete
              </div>
            </div>
          </div>
        </div>

        {/* SECTION 3: Phase 1 - Speech Processing */}
        <div className="border-t pt-3">
          <div className="flex items-center gap-2 mb-3">
            <Mic className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground font-medium">Phase 1: Speech Processing</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">WhisperX Connection</div>
              <div className={`text-xl font-semibold ${getLatencyColor(metrics?.whisperConnectionLatency?.avg || 0, 'fast')}`}>
                {formatLatency(metrics?.whisperConnectionLatency?.avg || 0)}
              </div>
              <div className="h-2 w-full bg-muted rounded overflow-hidden">
                <div
                  className={`h-full ${getLatencyColor(metrics?.whisperConnectionLatency?.avg || 0, 'fast').replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min((metrics?.whisperConnectionLatency?.avg || 0) * 50, 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground">P95: {formatLatency(metrics?.whisperConnectionLatency?.p95 || 0)}</div>
            </div>

            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">First Partial Transcript</div>
              <div className={`text-xl font-semibold ${getLatencyColor(metrics?.firstPartialTranscriptLatency?.avg || 0, 'fast')}`}>
                {formatLatency(metrics?.firstPartialTranscriptLatency?.avg || 0)}
              </div>
              <div className="h-2 w-full bg-muted rounded overflow-hidden">
                <div
                  className={`h-full ${getLatencyColor(metrics?.firstPartialTranscriptLatency?.avg || 0, 'fast').replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min((metrics?.firstPartialTranscriptLatency?.avg || 0) * 50, 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground">P95: {formatLatency(metrics?.firstPartialTranscriptLatency?.p95 || 0)}</div>
            </div>

            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">Transcription Duration</div>
              <div className={`text-xl font-semibold ${getLatencyColor(metrics?.transcriptionDuration?.avg || 0, 'moderate')}`}>
                {formatLatency(metrics?.transcriptionDuration?.avg || 0)}
              </div>
              <div className="h-2 w-full bg-muted rounded overflow-hidden">
                <div
                  className={`h-full ${getLatencyColor(metrics?.transcriptionDuration?.avg || 0, 'moderate').replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min((metrics?.transcriptionDuration?.avg || 0) * 20, 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground">P95: {formatLatency(metrics?.transcriptionDuration?.p95 || 0)}</div>
            </div>

            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">Silence Detection</div>
              <div className={`text-xl font-semibold ${getLatencyColor(metrics?.silenceDetectionLatency?.avg || 0, 'fast')}`}>
                {formatLatency(metrics?.silenceDetectionLatency?.avg || 0, true)}
              </div>
              <div className="h-2 w-full bg-muted rounded overflow-hidden">
                <div
                  className={`h-full ${getLatencyColor(metrics?.silenceDetectionLatency?.avg ? metrics.silenceDetectionLatency.avg / 1000 : 0, 'fast').replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min((metrics?.silenceDetectionLatency?.avg || 0) / 10, 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground">P95: {formatLatency(metrics?.silenceDetectionLatency?.p95 || 0, true)}</div>
            </div>
          </div>
        </div>

        {/* SECTION 4: Phase 2 - AI Generation */}
        <div className="border-t pt-3">
          <div className="flex items-center gap-2 mb-3">
            <Brain className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground font-medium">Phase 2: AI Generation</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">AI Generation Time</div>
              <div className={`text-2xl font-bold ${getLatencyColor(metrics?.aiGenerationLatency?.avg || 0, 'slow')}`}>
                {formatLatency(metrics?.aiGenerationLatency?.avg || 0)}
              </div>
              <div className="h-3 w-full bg-muted rounded overflow-hidden">
                <div
                  className={`h-full ${getLatencyColor(metrics?.aiGenerationLatency?.avg || 0, 'slow').replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min((metrics?.aiGenerationLatency?.avg || 0) * 12.5, 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground">
                P50: {formatLatency(metrics?.aiGenerationLatency?.p50 || 0)} |
                P95: {formatLatency(metrics?.aiGenerationLatency?.p95 || 0)}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Webhook sent → Response received
              </div>
            </div>

            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">Response Parsing</div>
              <div className={`text-2xl font-bold ${getLatencyColor(metrics?.responseParsingLatency?.avg ? metrics.responseParsingLatency.avg / 1000 : 0, 'fast')}`}>
                {formatLatency(metrics?.responseParsingLatency?.avg || 0, true)}
              </div>
              <div className="h-3 w-full bg-muted rounded overflow-hidden">
                <div
                  className={`h-full ${getLatencyColor(metrics?.responseParsingLatency?.avg ? metrics.responseParsingLatency.avg / 1000 : 0, 'fast').replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min((metrics?.responseParsingLatency?.avg || 0) / 10, 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground">
                P50: {formatLatency(metrics?.responseParsingLatency?.p50 || 0, true)} |
                P95: {formatLatency(metrics?.responseParsingLatency?.p95 || 0, true)}
              </div>
            </div>
          </div>
        </div>

        {/* SECTION 5: Phase 3 - TTS Generation */}
        <div className="border-t pt-3">
          <div className="flex items-center gap-2 mb-3">
            <Volume2 className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground font-medium">Phase 3: TTS Generation</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">TTS Queue Wait</div>
              <div className={`text-xl font-semibold ${getLatencyColor(metrics?.ttsQueueLatency?.avg || 0, 'moderate')}`}>
                {formatLatency(metrics?.ttsQueueLatency?.avg || 0)}
              </div>
              <div className="h-2 w-full bg-muted rounded overflow-hidden">
                <div
                  className={`h-full ${getLatencyColor(metrics?.ttsQueueLatency?.avg || 0, 'moderate').replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min((metrics?.ttsQueueLatency?.avg || 0) * 20, 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground">P95: {formatLatency(metrics?.ttsQueueLatency?.p95 || 0)}</div>
            </div>

            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">TTS Generation</div>
              <div className={`text-xl font-semibold ${getLatencyColor(metrics?.ttsGenerationLatency?.avg || 0, 'moderate')}`}>
                {formatLatency(metrics?.ttsGenerationLatency?.avg || 0)}
              </div>
              <div className="h-2 w-full bg-muted rounded overflow-hidden">
                <div
                  className={`h-full ${getLatencyColor(metrics?.ttsGenerationLatency?.avg || 0, 'moderate').replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min((metrics?.ttsGenerationLatency?.avg || 0) * 20, 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground">
                P50: {formatLatency(metrics?.ttsGenerationLatency?.p50 || 0)} |
                P95: {formatLatency(metrics?.ttsGenerationLatency?.p95 || 0)}
              </div>
            </div>

            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">First Audio Byte</div>
              <div className={`text-xl font-semibold ${getLatencyColor(metrics?.ttsFirstByteLatency?.avg || 0, 'moderate')}`}>
                {formatLatency(metrics?.ttsFirstByteLatency?.avg || 0)}
              </div>
              <div className="h-2 w-full bg-muted rounded overflow-hidden">
                <div
                  className={`h-full ${getLatencyColor(metrics?.ttsFirstByteLatency?.avg || 0, 'moderate').replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min((metrics?.ttsFirstByteLatency?.avg || 0) * 20, 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground">
                P50: {formatLatency(metrics?.ttsFirstByteLatency?.p50 || 0)} |
                P95: {formatLatency(metrics?.ttsFirstByteLatency?.p95 || 0)}
              </div>
            </div>
          </div>
        </div>

        {/* SECTION 6: Phase 4 - Audio Playback */}
        <div className="border-t pt-3">
          <div className="flex items-center gap-2 mb-3">
            <Play className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground font-medium">Phase 4: Audio Playback</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">Audio Playback Time</div>
              <div className={`text-xl font-semibold ${getLatencyColor(metrics?.audioPlaybackLatency?.avg || 0, 'moderate')}`}>
                {formatLatency(metrics?.audioPlaybackLatency?.avg || 0)}
              </div>
              <div className="h-2 w-full bg-muted rounded overflow-hidden">
                <div
                  className={`h-full ${getLatencyColor(metrics?.audioPlaybackLatency?.avg || 0, 'moderate').replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min((metrics?.audioPlaybackLatency?.avg || 0) * 20, 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground">
                P50: {formatLatency(metrics?.audioPlaybackLatency?.p50 || 0)} |
                P95: {formatLatency(metrics?.audioPlaybackLatency?.p95 || 0)}
              </div>
            </div>

            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">FFmpeg Processing</div>
              <div className={`text-xl font-semibold ${getLatencyColor(metrics?.ffmpegProcessingLatency?.avg ? metrics.ffmpegProcessingLatency.avg / 1000 : 0, 'fast')}`}>
                {formatLatency(metrics?.ffmpegProcessingLatency?.avg || 0, true)}
              </div>
              <div className="h-2 w-full bg-muted rounded overflow-hidden">
                <div
                  className={`h-full ${getLatencyColor(metrics?.ffmpegProcessingLatency?.avg ? metrics.ffmpegProcessingLatency.avg / 1000 : 0, 'fast').replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min((metrics?.ffmpegProcessingLatency?.avg || 0) / 10, 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground">P95: {formatLatency(metrics?.ffmpegProcessingLatency?.p95 || 0, true)}</div>
            </div>
          </div>
        </div>

        {/* SECTION 7: System Status */}
        <div className="border-t pt-3">
          <div className="flex items-center gap-2">
            <Timer className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground font-medium">System Uptime</span>
          </div>
          <div className="mt-2">
            <div className="text-2xl font-bold text-foreground">
              {metrics ? formatUptime(metrics.uptime) : '0s'}
            </div>
            <p className="text-xs text-muted-foreground mt-1">System has been running</p>
          </div>
        </div>

      </CardContent>
    </Card>
  );
}
