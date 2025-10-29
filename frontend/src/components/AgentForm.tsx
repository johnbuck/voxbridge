/**
 * Agent Form Component
 * Dialog form for creating and editing AI agents
 */

import { useState, useEffect } from 'react';
import type { Agent, AgentCreateRequest } from '@/services/api';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Loader2, MessageSquare } from 'lucide-react';

interface AgentFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agent?: Agent | null; // If provided, edit mode; otherwise, create mode
  onSubmit: (agent: AgentCreateRequest) => Promise<void>;
}

export function AgentForm({ open, onOpenChange, agent, onSubmit }: AgentFormProps) {
  const isEditMode = !!agent;

  // Form state
  const [name, setName] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [temperature, setTemperature] = useState(0.7);
  const [llmProvider, setLlmProvider] = useState<'openrouter' | 'local'>('openrouter');
  const [llmModel, setLlmModel] = useState('anthropic/claude-3.5-sonnet');
  const [useN8n, setUseN8n] = useState(false);
  const [n8nWebhookUrl, setN8nWebhookUrl] = useState('');
  const [ttsVoice, setTtsVoice] = useState('');
  const [ttsRate, setTtsRate] = useState(1.0);
  const [ttsPitch, setTtsPitch] = useState(1.0);

  // Discord Plugin state
  const [discordEnabled, setDiscordEnabled] = useState(false);
  const [discordBotToken, setDiscordBotToken] = useState('');
  const [discordAutoJoin, setDiscordAutoJoin] = useState(false);
  const [discordCommandPrefix, setDiscordCommandPrefix] = useState('!');

  const [isSubmitting, setIsSubmitting] = useState(false);

  // Populate form when editing
  useEffect(() => {
    if (agent) {
      setName(agent.name);
      setSystemPrompt(agent.system_prompt);
      setTemperature(agent.temperature);
      setLlmProvider(agent.llm_provider as 'openrouter' | 'local');
      setLlmModel(agent.llm_model);
      setUseN8n(agent.use_n8n);
      setN8nWebhookUrl(agent.n8n_webhook_url || '');
      setTtsVoice(agent.tts_voice || '');
      setTtsRate(agent.tts_rate);
      setTtsPitch(agent.tts_pitch);

      // Load Discord plugin config if present
      if (agent.plugins?.discord) {
        setDiscordEnabled(agent.plugins.discord.enabled || false);
        setDiscordBotToken(agent.plugins.discord.bot_token || '');
        setDiscordAutoJoin(agent.plugins.discord.auto_join || false);
        setDiscordCommandPrefix(agent.plugins.discord.command_prefix || '!');
      } else {
        setDiscordEnabled(false);
        setDiscordBotToken('');
        setDiscordAutoJoin(false);
        setDiscordCommandPrefix('!');
      }
    } else {
      // Reset to defaults when creating
      setName('');
      setSystemPrompt('');
      setTemperature(0.7);
      setLlmProvider('openrouter');
      setLlmModel('anthropic/claude-3.5-sonnet');
      setUseN8n(false);
      setN8nWebhookUrl('');
      setTtsVoice('');
      setTtsRate(1.0);
      setTtsPitch(1.0);
      setDiscordEnabled(false);
      setDiscordBotToken('');
      setDiscordAutoJoin(false);
      setDiscordCommandPrefix('!');
    }
  }, [agent, open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      // Build plugins object
      const plugins: Record<string, any> = {};
      if (discordEnabled && discordBotToken) {
        plugins.discord = {
          enabled: true,
          bot_token: discordBotToken,
          auto_join: discordAutoJoin,
          command_prefix: discordCommandPrefix,
          channels: []
        };
      }

      await onSubmit({
        name,
        system_prompt: systemPrompt,
        temperature,
        llm_provider: llmProvider,
        llm_model: llmModel,
        use_n8n: useN8n,
        n8n_webhook_url: n8nWebhookUrl || null,
        tts_voice: ttsVoice || null,
        tts_rate: ttsRate,
        tts_pitch: ttsPitch,
        plugins: Object.keys(plugins).length > 0 ? plugins : undefined,
      });
      onOpenChange(false);
    } catch (error) {
      console.error('Failed to submit agent:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEditMode ? 'Edit Agent' : 'Create New Agent'}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div className="space-y-2">
            <Label htmlFor="name">Agent Name *</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Helpful Assistant"
              required
              maxLength={100}
            />
          </div>

          {/* System Prompt */}
          <div className="space-y-2">
            <Label htmlFor="systemPrompt">System Prompt *</Label>
            <Textarea
              id="systemPrompt"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="Describe the agent's role and behavior..."
              required
              rows={6}
              maxLength={10000}
              className="resize-none"
            />
            <p className="text-xs text-muted-foreground">
              {systemPrompt.length} / 10,000 characters
            </p>
          </div>

          {/* LLM Configuration */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="llmProvider">LLM Provider *</Label>
              <Select value={llmProvider} onValueChange={(val) => setLlmProvider(val as 'openrouter' | 'local')}>
                <SelectTrigger id="llmProvider">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openrouter">OpenRouter</SelectItem>
                  <SelectItem value="local">Local LLM</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="llmModel">Model Identifier *</Label>
              <Input
                id="llmModel"
                value={llmModel}
                onChange={(e) => setLlmModel(e.target.value)}
                placeholder="anthropic/claude-3.5-sonnet"
                required
              />
            </div>
          </div>

          {/* Temperature */}
          <div className="space-y-2">
            <Label htmlFor="temperature">
              Temperature: {temperature.toFixed(2)}
            </Label>
            <Slider
              id="temperature"
              value={[temperature]}
              onValueChange={(vals) => setTemperature(vals[0])}
              min={0}
              max={1}
              step={0.05}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Lower = more focused, Higher = more creative
            </p>
          </div>

          {/* Use n8n Toggle (Phase 3) */}
          <div className="flex items-center justify-between space-x-2 py-2">
            <div className="space-y-0.5">
              <Label htmlFor="useN8n">Use n8n Webhook</Label>
              <p className="text-xs text-muted-foreground">
                Route to n8n webhook instead of direct LLM
              </p>
            </div>
            <Switch
              id="useN8n"
              checked={useN8n}
              onCheckedChange={setUseN8n}
            />
          </div>

          {/* n8n Webhook URL (conditional) */}
          {useN8n && (
            <div className="space-y-2 pl-4 border-l-2 border-muted">
              <Label htmlFor="n8nWebhookUrl">n8n Webhook URL (Optional)</Label>
              <Input
                id="n8nWebhookUrl"
                type="url"
                value={n8nWebhookUrl}
                onChange={(e) => setN8nWebhookUrl(e.target.value)}
                placeholder="https://n8n.example.com/webhook/..."
                maxLength={500}
              />
              <p className="text-xs text-muted-foreground">
                Leave empty to use global webhook URL from environment
              </p>
            </div>
          )}

          {/* TTS Configuration */}
          <div className="space-y-4 pt-4 border-t">
            <h4 className="text-sm font-medium">Text-to-Speech Configuration (Optional)</h4>

            <div className="space-y-2">
              <Label htmlFor="ttsVoice">TTS Voice ID</Label>
              <Input
                id="ttsVoice"
                value={ttsVoice}
                onChange={(e) => setTtsVoice(e.target.value)}
                placeholder="Leave empty to use default"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="ttsRate">
                  Speech Rate: {ttsRate.toFixed(2)}x
                </Label>
                <Slider
                  id="ttsRate"
                  value={[ttsRate]}
                  onValueChange={(vals) => setTtsRate(vals[0])}
                  min={0.5}
                  max={2.0}
                  step={0.1}
                  className="w-full"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="ttsPitch">
                  Pitch: {ttsPitch.toFixed(2)}x
                </Label>
                <Slider
                  id="ttsPitch"
                  value={[ttsPitch]}
                  onValueChange={(vals) => setTtsPitch(vals[0])}
                  min={0.5}
                  max={2.0}
                  step={0.1}
                  className="w-full"
                />
              </div>
            </div>
          </div>

          {/* Plugins Section */}
          <div className="space-y-4 pt-4 border-t">
            <h4 className="text-sm font-medium">Plugins (Optional)</h4>
            <p className="text-xs text-muted-foreground">
              Enable optional plugins to extend agent capabilities
            </p>

            {/* Discord Plugin Card */}
            <Card className="border-2">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <MessageSquare className="h-4 w-4" />
                    <CardTitle className="text-sm">Discord Bot Plugin</CardTitle>
                  </div>
                  <Switch
                    checked={discordEnabled}
                    onCheckedChange={setDiscordEnabled}
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Connect this agent to Discord as a voice bot
                </p>
              </CardHeader>
              {discordEnabled && (
                <CardContent className="space-y-3">
                  <div className="space-y-2">
                    <Label htmlFor="botToken">
                      Bot Token *
                    </Label>
                    <Input
                      id="botToken"
                      type="password"
                      value={discordBotToken}
                      onChange={(e) => setDiscordBotToken(e.target.value)}
                      placeholder="Paste your Discord bot token"
                      required={discordEnabled}
                      maxLength={200}
                    />
                    <p className="text-xs text-muted-foreground">
                      Get your token from{' '}
                      <a
                        href="https://discord.com/developers/applications"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline"
                      >
                        Discord Developer Portal
                      </a>
                    </p>
                  </div>

                  <div className="flex items-center justify-between space-x-2">
                    <div className="space-y-0.5">
                      <Label htmlFor="autoJoin">Auto-join voice channels</Label>
                      <p className="text-xs text-muted-foreground">
                        Automatically join when users enter voice
                      </p>
                    </div>
                    <Switch
                      id="autoJoin"
                      checked={discordAutoJoin}
                      onCheckedChange={setDiscordAutoJoin}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="commandPrefix">Command Prefix</Label>
                    <Input
                      id="commandPrefix"
                      value={discordCommandPrefix}
                      onChange={(e) => setDiscordCommandPrefix(e.target.value)}
                      placeholder="!"
                      maxLength={3}
                    />
                    <p className="text-xs text-muted-foreground">
                      Prefix for bot commands (e.g., !help)
                    </p>
                  </div>
                </CardContent>
              )}
            </Card>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isEditMode ? 'Save Changes' : 'Create Agent'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
