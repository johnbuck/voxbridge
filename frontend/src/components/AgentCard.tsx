/**
 * Agent Card Component
 * Displays an AI agent in card format with edit/delete actions
 */

import type { Agent } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Edit2, Trash2, Brain, Mic, ThermometerIcon, Star, Globe, Lock, AlertTriangle, RotateCcw } from 'lucide-react';
import { DiscordPluginCard } from '@/components/DiscordPluginCard';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAgentMemoryConfig, setUserAgentMemorySetting, resetUserAgentMemorySetting } from '@/services/memory';
import { useToastHelpers } from '@/components/ui/toast';

// TODO: Replace with actual user ID from auth
const USER_ID = 'discord:123456789';

interface AgentCardProps {
  agent: Agent;
  onEdit: (agent: Agent) => void;
  onDelete: (agent: Agent) => void;
  onSetDefault: (agent: Agent) => void;
}

export function AgentCard({ agent, onEdit, onDelete, onSetDefault }: AgentCardProps) {
  const queryClient = useQueryClient();
  const toast = useToastHelpers();

  // Fetch effective memory configuration
  const { data: memoryConfig, isLoading: memoryLoading } = useQuery({
    queryKey: ['agentMemoryConfig', agent.id, USER_ID],
    queryFn: () => getAgentMemoryConfig(agent.id, USER_ID, agent.memory_scope),
  });

  // Mutation to update memory preference
  const updateMemoryPrefMutation = useMutation({
    mutationFn: (allowAgentSpecific: boolean) =>
      setUserAgentMemorySetting(agent.id, USER_ID, allowAgentSpecific),
    onSuccess: (data) => {
      queryClient.setQueryData(['agentMemoryConfig', agent.id, USER_ID], data);
      toast.success(
        'Memory preference updated',
        data.effective_scope === 'agent' ? 'Private memories enabled for this agent' : 'Global memories enabled for this agent'
      );
    },
    onError: (error: any) => {
      console.error('[AgentCard] Failed to update memory preference:', error);
      toast.error('Failed to update preference', error?.message || 'Unknown error');
    },
  });

  // Mutation to reset memory preference
  const resetMemoryPrefMutation = useMutation({
    mutationFn: () => resetUserAgentMemorySetting(agent.id, USER_ID, agent.memory_scope),
    onSuccess: (data) => {
      queryClient.setQueryData(['agentMemoryConfig', agent.id, USER_ID], data);
      toast.success('Preference reset', `Reverted to agent default (${data.effective_scope})`);
    },
    onError: (error: any) => {
      console.error('[AgentCard] Failed to reset memory preference:', error);
      toast.error('Failed to reset preference', error?.message || 'Unknown error');
    },
  });

  const providerColors = {
    openrouter: 'bg-purple-500/20 text-purple-400 border-purple-500/50',
    local: 'bg-blue-500/20 text-blue-400 border-blue-500/50',
  };

  const providerColor = providerColors[agent.llm_provider as keyof typeof providerColors] || 'bg-gray-500/20 text-gray-400';

  // Use effective scope from memory config if available, otherwise fall back to agent default
  const effectiveScope = memoryConfig?.effective_scope || agent.memory_scope;

  return (
    <Card className="relative hover:border-primary/50 transition-colors">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between">
            <div className="flex-1 min-w-0">
              <CardTitle className="text-lg flex items-center gap-2 mb-2">
                <Brain className="h-5 w-5 text-primary" />
                <span className="truncate">{agent.name}</span>
              </CardTitle>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline" className={providerColor}>
                  {agent.llm_provider}
                </Badge>
                <Badge variant="outline" className="bg-muted">
                  <ThermometerIcon className="h-3 w-3 mr-1" />
                  {agent.temperature}
                </Badge>
                {agent.is_default && (
                  <Badge variant="outline" className="bg-yellow-500/20 text-yellow-400 border-yellow-500/50">
                    <Star className="h-3 w-3 mr-1 fill-yellow-400" />
                    Default
                  </Badge>
                )}
                {/* Memory Scope Badge (Phase 6: Per-Agent Memory Preferences) */}
                <Badge
                  variant="outline"
                  className={effectiveScope === 'agent'
                    ? 'bg-green-500/20 text-green-400 border-green-500/50'
                    : 'bg-blue-500/20 text-blue-400 border-blue-500/50'
                  }
                  title={`Memory: ${effectiveScope === 'agent' ? 'Private (user + agent)' : 'Shared (global)'} - Source: ${memoryConfig?.source || 'loading'}`}
                >
                  {effectiveScope === 'agent' ? (
                    <>
                      <Lock className="h-3 w-3 mr-1" />
                      Private
                    </>
                  ) : (
                    <>
                      <Globe className="h-3 w-3 mr-1" />
                      Global
                    </>
                  )}
                </Badge>
              </div>
            </div>
            <div className="flex gap-1 ml-2">
              {!agent.is_default && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-yellow-400 hover:text-yellow-300"
                  onClick={() => onSetDefault(agent)}
                  title="Set as default agent"
                >
                  <Star className="h-4 w-4" />
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => onEdit(agent)}
                title="Edit agent"
              >
                <Edit2 className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-destructive hover:text-destructive"
                onClick={() => onDelete(agent)}
                title="Delete agent"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 pt-0">
          {/* Model Info */}
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground">Model</div>
            <div className="text-sm font-mono bg-muted px-2 py-1 rounded truncate">
              {agent.llm_model}
            </div>
          </div>

          {/* System Prompt Preview */}
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground">System Prompt</div>
            <div className="text-sm text-muted-foreground line-clamp-2 leading-relaxed">
              {agent.system_prompt}
            </div>
          </div>

          {/* TTS Settings - Chatterbox Aligned */}
          {agent.tts_voice && (
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground flex items-center gap-1">
                <Mic className="h-3 w-3" />
                TTS Voice
              </div>
              <div className="text-sm font-mono bg-muted px-2 py-1 rounded truncate">
                {agent.tts_voice}
              </div>
              <div className="flex gap-3 text-xs text-muted-foreground mt-1 flex-wrap">
                <span>Emotion: {agent.tts_exaggeration.toFixed(2)}</span>
                <span>Pace: {agent.tts_cfg_weight.toFixed(2)}</span>
                <span>Sampling: {agent.tts_temperature.toFixed(2)}</span>
                <span>Lang: {agent.tts_language}</span>
              </div>
            </div>
          )}

          {/* Memory Preferences Section (Phase 6: Interactive Controls) */}
          <div className="space-y-2 pt-3 border-t">
            <div className="text-xs text-muted-foreground flex items-center gap-1">
              {effectiveScope === 'agent' ? <Lock className="h-3 w-3" /> : <Globe className="h-3 w-3" />}
              Memory Preferences
            </div>

            {!memoryLoading && memoryConfig && (
              <>
                {/* Admin Policy Warning */}
                {!memoryConfig.admin_allows && (
                  <div className="flex items-start gap-2 p-2 bg-yellow-500/10 border border-yellow-500/50 rounded text-xs">
                    <AlertTriangle className="h-3 w-3 text-yellow-600 flex-shrink-0 mt-0.5" />
                    <div className="text-yellow-600">
                      <strong>Admin Policy Active:</strong> Agent-specific memory disabled globally. All memories forced to global scope.
                    </div>
                  </div>
                )}

                {/* Memory Preference Controls */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-xs">
                      {memoryConfig.user_preference ? (
                        <span className="text-blue-400">Your preference: {memoryConfig.effective_scope}</span>
                      ) : (
                        <span className="text-muted-foreground">Agent default: {memoryConfig.agent_default}</span>
                      )}
                    </div>
                    {memoryConfig.admin_allows && (
                      <Switch
                        checked={memoryConfig.effective_scope === 'agent'}
                        onCheckedChange={(checked) => updateMemoryPrefMutation.mutate(checked)}
                        disabled={updateMemoryPrefMutation.isPending || resetMemoryPrefMutation.isPending}
                      />
                    )}
                  </div>

                  {/* Reset Button (shown when user has override) */}
                  {memoryConfig.user_preference && memoryConfig.admin_allows && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => resetMemoryPrefMutation.mutate()}
                      disabled={resetMemoryPrefMutation.isPending || updateMemoryPrefMutation.isPending}
                      className="w-full text-xs h-7"
                    >
                      <RotateCcw className="h-3 w-3 mr-1" />
                      Reset to Agent Default ({memoryConfig.agent_default})
                    </Button>
                  )}

                  {/* Source Explanation */}
                  <div className="text-xs text-muted-foreground">
                    {memoryConfig.source === 'admin' && 'Enforced by admin policy'}
                    {memoryConfig.source === 'user' && 'Your custom preference'}
                    {memoryConfig.source === 'agent' && 'Using agent default'}
                  </div>
                </div>
              </>
            )}

            {memoryLoading && (
              <div className="text-xs text-muted-foreground">Loading preference...</div>
            )}
          </div>

          {/* Active Plugins Section */}
          {agent.plugins?.discord?.enabled && (
            <div className="pt-3 border-t">
              <DiscordPluginCard agent={agent} />
            </div>
          )}

          {/* Metadata */}
          <div className="text-xs text-muted-foreground pt-2 border-t">
            Created {new Date(agent.created_at).toLocaleDateString()}
          </div>
        </CardContent>
    </Card>
  );
}
