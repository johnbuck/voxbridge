/**
 * Metrics Panel Component
 * Displays latency metrics and performance stats with Recharts visualization
 */

import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Activity, Clock, AlertCircle, Timer } from 'lucide-react';

interface MetricsDataPoint {
  timestamp: string;
  avg: number;
  p50: number;
  p95: number;
  p99: number;
}

export function MetricsPanel() {
  const [metricsHistory, setMetricsHistory] = useState<MetricsDataPoint[]>([]);
  const maxDataPoints = 20; // Keep last 20 data points

  // Poll metrics every 5 seconds
  const { data: metrics } = useQuery({
    queryKey: ['metrics'],
    queryFn: () => api.getMetrics(),
    refetchInterval: 5000,
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
        const newData = [
          ...prev,
          {
            timestamp,
            avg: metrics.latency.avg,
            p50: metrics.latency.p50,
            p95: metrics.latency.p95,
            p99: metrics.latency.p99,
          },
        ];

        // Keep only the last N data points
        return newData.slice(-maxDataPoints);
      });
    }
  }, [metrics]);

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

  return (
    <div className="space-y-4">
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Clock className="size-4 text-muted-foreground" />
              Avg Latency
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics?.latency.avg || 0}ms</div>
            <p className="text-xs text-muted-foreground mt-1">Mean response time</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Activity className="size-4 text-muted-foreground" />
              P95 Latency
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics?.latency.p95 || 0}ms</div>
            <p className="text-xs text-muted-foreground mt-1">95th percentile</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <AlertCircle className="size-4 text-muted-foreground" />
              Error Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metrics ? (metrics.errorRate * 100).toFixed(1) : 0}%
            </div>
            <p className="text-xs text-muted-foreground mt-1">Failed requests</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Timer className="size-4 text-muted-foreground" />
              Uptime
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metrics ? formatUptime(metrics.uptime) : '0s'}
            </div>
            <p className="text-xs text-muted-foreground mt-1">System uptime</p>
          </CardContent>
        </Card>
      </div>

      {/* Latency Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Latency Over Time</CardTitle>
        </CardHeader>
        <CardContent>
          {metricsHistory.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={metricsHistory}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="timestamp"
                  tick={{ fontSize: 12 }}
                  className="text-muted-foreground"
                />
                <YAxis
                  label={{ value: 'Latency (ms)', angle: -90, position: 'insideLeft' }}
                  tick={{ fontSize: 12 }}
                  className="text-muted-foreground"
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'hsl(var(--popover))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '6px',
                  }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="avg"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2}
                  dot={false}
                  name="Average"
                />
                <Line
                  type="monotone"
                  dataKey="p50"
                  stroke="hsl(var(--chart-2))"
                  strokeWidth={2}
                  dot={false}
                  name="P50"
                />
                <Line
                  type="monotone"
                  dataKey="p95"
                  stroke="hsl(var(--chart-3))"
                  strokeWidth={2}
                  dot={false}
                  name="P95"
                />
                <Line
                  type="monotone"
                  dataKey="p99"
                  stroke="hsl(var(--chart-4))"
                  strokeWidth={2}
                  dot={false}
                  name="P99"
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[300px] flex items-center justify-center text-muted-foreground">
              <p className="text-sm">Waiting for metrics data...</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
