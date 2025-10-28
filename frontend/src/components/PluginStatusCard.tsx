/**
 * Plugin Status Card Component
 * Displays individual plugin status with controls
 */

import type { Plugin } from '@/services/plugins';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Play, Square, RotateCw, Activity } from 'lucide-react';

interface PluginStatusCardProps {
  plugin: Plugin;
  onStart?: () => void;
  onStop?: () => void;
  onRestart?: () => void;
}

export function PluginStatusCard({
  plugin,
  onStart,
  onStop,
  onRestart,
}: PluginStatusCardProps) {
  const statusConfig = {
    running: {
      color: 'bg-green-500/20 text-green-400 border-green-500/50',
      icon: '✅',
      text: 'Running'
    },
    stopped: {
      color: 'bg-gray-500/20 text-gray-400 border-gray-500/50',
      icon: '⏸️',
      text: 'Stopped'
    },
    error: {
      color: 'bg-red-500/20 text-red-400 border-red-500/50',
      icon: '❌',
      text: 'Error'
    },
  };

  const config = statusConfig[plugin.status];

  const formatUptime = (seconds: number): string => {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
  };

  return (
    <Card className="hover:border-primary/50 transition-colors">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between mb-2">
          <CardTitle className="text-lg flex items-center gap-2">
            <span className="text-xl">{config.icon}</span>
            <span className="capitalize">{plugin.plugin_type}</span>
          </CardTitle>
          <Badge variant="outline" className={config.color}>
            {config.text}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Agent: <span className="text-foreground font-medium">{plugin.agent_name}</span>
        </p>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Resource Usage */}
        {plugin.resource_usage && (
          <div className="grid grid-cols-2 gap-2 p-3 bg-muted rounded-lg">
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">CPU</p>
              <p className="text-sm font-semibold flex items-center gap-1">
                <Activity className="h-3 w-3" />
                {plugin.resource_usage.cpu_percent.toFixed(1)}%
              </p>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">RAM</p>
              <p className="text-sm font-semibold">
                {plugin.resource_usage.memory_mb.toFixed(0)} MB
              </p>
            </div>
            {plugin.resource_usage.gpu_memory_mb !== undefined && (
              <div className="col-span-2 space-y-1">
                <p className="text-xs text-muted-foreground">GPU Memory</p>
                <p className="text-sm font-semibold">
                  {plugin.resource_usage.gpu_memory_mb.toFixed(0)} MB
                </p>
              </div>
            )}
          </div>
        )}

        {/* Uptime */}
        {plugin.uptime_seconds !== undefined && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Uptime:</span>
            <span className="font-medium">{formatUptime(plugin.uptime_seconds)}</span>
          </div>
        )}

        {/* Error Message */}
        {plugin.last_error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-xs text-red-400 font-mono">{plugin.last_error}</p>
          </div>
        )}

        {/* Control Buttons */}
        <div className="flex gap-2 pt-2">
          {plugin.status === 'stopped' && onStart && (
            <Button
              onClick={onStart}
              className="flex-1 gap-2"
              variant="default"
              size="sm"
            >
              <Play className="h-4 w-4" />
              Start
            </Button>
          )}
          {plugin.status === 'running' && (
            <>
              {onStop && (
                <Button
                  onClick={onStop}
                  className="flex-1 gap-2"
                  variant="destructive"
                  size="sm"
                >
                  <Square className="h-4 w-4" />
                  Stop
                </Button>
              )}
              {onRestart && (
                <Button
                  onClick={onRestart}
                  className="flex-1 gap-2"
                  variant="outline"
                  size="sm"
                >
                  <RotateCw className="h-4 w-4" />
                  Restart
                </Button>
              )}
            </>
          )}
          {plugin.status === 'error' && onRestart && (
            <Button
              onClick={onRestart}
              className="flex-1 gap-2"
              variant="outline"
              size="sm"
            >
              <RotateCw className="h-4 w-4" />
              Retry
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
