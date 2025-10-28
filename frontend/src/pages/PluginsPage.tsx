/**
 * Plugins Management Page
 * VoxBridge 2.0 Phase 6.4.1 - Plugin Management UI
 */

import { useQuery } from '@tanstack/react-query';
import { pluginApi, type Plugin } from '@/services/plugins';
import { PluginStatusCard } from '@/components/PluginStatusCard';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useToastHelpers } from '@/components/ui/toast';
import { Loader2, AlertCircle, Plug, Activity, XCircle, Cpu, MemoryStick } from 'lucide-react';

export function PluginsPage() {
  const toast = useToastHelpers();

  // Fetch plugins with polling
  const { data: plugins = [], isLoading: isLoadingPlugins, error: pluginsError, refetch: refetchPlugins } = useQuery({
    queryKey: ['plugins'],
    queryFn: () => pluginApi.getPlugins(),
    refetchInterval: 5000, // Poll every 5 seconds
  });

  // Fetch plugin stats with polling
  const { data: stats, isLoading: isLoadingStats, error: statsError } = useQuery({
    queryKey: ['plugin-stats'],
    queryFn: () => pluginApi.getPluginStats(),
    refetchInterval: 5000, // Poll every 5 seconds
  });

  const loading = isLoadingPlugins || isLoadingStats;
  const error = pluginsError || statsError;

  // Plugin control handlers
  const handleStart = async (plugin: Plugin) => {
    try {
      await pluginApi.startPlugin(plugin.agent_id, plugin.plugin_type);
      toast.success('Plugin Started', `${plugin.plugin_type} for ${plugin.agent_name} is starting`);
      await refetchPlugins();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      toast.error('Failed to start plugin', message);
    }
  };

  const handleStop = async (plugin: Plugin) => {
    try {
      await pluginApi.stopPlugin(plugin.agent_id, plugin.plugin_type);
      toast.success('Plugin Stopped', `${plugin.plugin_type} for ${plugin.agent_name} is stopping`);
      await refetchPlugins();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      toast.error('Failed to stop plugin', message);
    }
  };

  const handleRestart = async (plugin: Plugin) => {
    try {
      await pluginApi.restartPlugin(plugin.agent_id, plugin.plugin_type);
      toast.success('Plugin Restarting', `${plugin.plugin_type} for ${plugin.agent_name} is restarting`);
      await refetchPlugins();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      toast.error('Failed to restart plugin', message);
    }
  };

  return (
    <div className="min-h-screen bg-page-background p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-4xl font-bold flex items-center justify-center gap-3">
            <Plug className="h-10 w-10 text-primary" />
            Plugin Management
          </h1>
          <p className="text-muted-foreground mt-2">
            Monitor and control VoxBridge plugins in real-time
          </p>
        </div>

        {/* Error Message */}
        {error && (
          <Card className="border-red-500/20 bg-red-500/5">
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-red-500 mb-1">Failed to load plugin data</p>
                  <p className="text-xs text-muted-foreground">
                    {error instanceof Error ? error.message : 'Unknown error occurred'}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Stats Overview */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">Total Plugins</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3">
                  <Plug className="h-8 w-8 text-primary" />
                  <p className="text-3xl font-bold">{stats.total_plugins}</p>
                </div>
              </CardContent>
            </Card>

            <Card className="border-green-500/20 bg-green-500/5">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">Active</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3">
                  <Activity className="h-8 w-8 text-green-500" />
                  <p className="text-3xl font-bold text-green-500">{stats.active_plugins}</p>
                </div>
              </CardContent>
            </Card>

            <Card className="border-red-500/20 bg-red-500/5">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">Failed</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3">
                  <XCircle className="h-8 w-8 text-red-500" />
                  <p className="text-3xl font-bold text-red-500">{stats.failed_plugins}</p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">Resource Usage</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground flex items-center gap-1">
                    <Cpu className="h-3 w-3" />
                    CPU:
                  </span>
                  <span className="font-semibold">{stats.resource_usage.total_cpu_percent.toFixed(1)}%</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground flex items-center gap-1">
                    <MemoryStick className="h-3 w-3" />
                    RAM:
                  </span>
                  <span className="font-semibold">{stats.resource_usage.total_memory_mb.toFixed(0)} MB</span>
                </div>
                {stats.resource_usage.total_gpu_memory_mb !== undefined && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">GPU:</span>
                    <span className="font-semibold">{stats.resource_usage.total_gpu_memory_mb.toFixed(0)} MB</span>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* Loading State */}
        {loading && !stats && (
          <Card>
            <CardContent className="p-12">
              <div className="text-center space-y-3">
                <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
                <p className="text-sm text-muted-foreground">Loading plugins...</p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Empty State */}
        {!loading && plugins.length === 0 && !error && (
          <Card>
            <CardContent className="p-12">
              <div className="text-center space-y-3">
                <Plug className="h-16 w-16 mx-auto text-muted-foreground opacity-50" />
                <div>
                  <h3 className="text-lg font-semibold mb-1">No Plugins Found</h3>
                  <p className="text-sm text-muted-foreground">
                    Create an agent with plugins to get started
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Plugin Cards */}
        {!loading && plugins.length > 0 && (
          <div>
            <h2 className="text-xl font-semibold mb-4">Active Plugins ({plugins.length})</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {plugins.map((plugin, idx) => (
                <PluginStatusCard
                  key={`${plugin.agent_id}-${plugin.plugin_type}-${idx}`}
                  plugin={plugin}
                  onStart={() => handleStart(plugin)}
                  onStop={() => handleStop(plugin)}
                  onRestart={() => handleRestart(plugin)}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
