/**
 * Agent Card Component
 * Displays an AI agent in card format with edit/delete actions
 */

import type { Agent } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Edit2, Trash2, Brain, Mic, ThermometerIcon, Star } from 'lucide-react';
import { DiscordPluginCard } from '@/components/DiscordPluginCard';

interface AgentCardProps {
  agent: Agent;
  onEdit: (agent: Agent) => void;
  onDelete: (agent: Agent) => void;
  onSetDefault: (agent: Agent) => void;
}

export function AgentCard({ agent, onEdit, onDelete, onSetDefault }: AgentCardProps) {
  const providerColors = {
    openrouter: 'bg-purple-500/20 text-purple-400 border-purple-500/50',
    local: 'bg-blue-500/20 text-blue-400 border-blue-500/50',
  };

  const providerColor = providerColors[agent.llm_provider as keyof typeof providerColors] || 'bg-gray-500/20 text-gray-400';

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
