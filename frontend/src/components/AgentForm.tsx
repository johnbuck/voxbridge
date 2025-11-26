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

  // Debug logging
  console.log('[AgentForm] Rendering:', { open, isEditMode, agentId: agent?.id });

  // Form state
  const [name, setName] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [temperature, setTemperature] = useState(0.7);
  const [llmProvider, setLlmProvider] = useState<'openrouter' | 'local'>('openrouter');
  const [llmModel, setLlmModel] = useState('anthropic/claude-3.5-sonnet');
  const [useN8n, setUseN8n] = useState(false);
  const [n8nWebhookUrl, setN8nWebhookUrl] = useState('');
  const [ttsVoice, setTtsVoice] = useState('');
  const [ttsExaggeration, setTtsExaggeration] = useState(1.0);
  const [ttsCfgWeight, setTtsCfgWeight] = useState(0.7);
  const [ttsTemperature, setTtsTemperature] = useState(0.3);
  const [ttsLanguage, setTtsLanguage] = useState('en');
  const [filterActionsForTts, setFilterActionsForTts] = useState(false);

  // Memory Scope (Phase 5: Per-Agent Memory Preferences)
  const [memoryScope, setMemoryScope] = useState<'global' | 'agent'>('global');

  // Voice Configuration
  const [maxUtteranceTimeMs, setMaxUtteranceTimeMs] = useState<number>(120000); // 2 minutes default

  // Discord Plugin state
  const [discordEnabled, setDiscordEnabled] = useState(false);
  const [discordBotToken, setDiscordBotToken] = useState('');
  const [discordAutoJoin, setDiscordAutoJoin] = useState(false);
  const [discordCommandPrefix, setDiscordCommandPrefix] = useState('!');

  const [isSubmitting, setIsSubmitting] = useState(false);

  // Available voices from Chatterbox
  const [availableVoices, setAvailableVoices] = useState<string[]>([]);
  const [voicesLoading, setVoicesLoading] = useState(false);

  // Fetch available voices from Chatterbox via VoxBridge API on mount
  useEffect(() => {
    const fetchVoices = async () => {
      setVoicesLoading(true);
      try {
        // Fetch from VoxBridge API (proxies to Chatterbox TTS)
        const response = await fetch('/api/voices');

        if (!response.ok) {
          throw new Error(`Failed to fetch voices: ${response.status} ${response.statusText}`);
        }

        const data = await response.json();

        if (data.voices && Array.isArray(data.voices)) {
          const voiceNames = data.voices.map((v: any) => v.name).filter(Boolean);
          setAvailableVoices(voiceNames);
          console.log(`✅ Loaded ${voiceNames.length} voices:`, voiceNames);
        } else {
          console.warn('⚠️ Invalid voices response format:', data);
          setAvailableVoices([]);
        }
      } catch (error) {
        console.error('❌ Failed to fetch voices:', error);
        setAvailableVoices([]); // Fallback to empty if fetch fails
      } finally {
        setVoicesLoading(false);
      }
    };

    // Only fetch if dialog is open
    if (open) {
      fetchVoices();
    }
  }, [open]);

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
      setTtsExaggeration(agent.tts_exaggeration);
      setTtsCfgWeight(agent.tts_cfg_weight);
      setTtsTemperature(agent.tts_temperature);
      setTtsLanguage(agent.tts_language);
      setFilterActionsForTts(agent.filter_actions_for_tts || false);
      setMaxUtteranceTimeMs(agent.max_utterance_time_ms ?? 120000);
      setMemoryScope(agent.memory_scope);

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
      setTtsExaggeration(1.0);
      setTtsCfgWeight(0.7);
      setTtsTemperature(0.3);
      setTtsLanguage('en');
      setFilterActionsForTts(false);
      setMaxUtteranceTimeMs(120000);
      setMemoryScope('global');
      setDiscordEnabled(false);
      setDiscordBotToken('');
      setDiscordAutoJoin(false);
      setDiscordCommandPrefix('!');
    }
  }, [agent]);

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
        memory_scope: memoryScope,
        tts_voice: ttsVoice || null,
        tts_exaggeration: ttsExaggeration,
        tts_cfg_weight: ttsCfgWeight,
        tts_temperature: ttsTemperature,
        tts_language: ttsLanguage,
        filter_actions_for_tts: filterActionsForTts,
        max_utterance_time_ms: maxUtteranceTimeMs,
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

          {/* Memory Scope Configuration (Phase 5: Per-Agent Memory Preferences) */}
          <div className="flex items-center justify-between space-x-2 py-2">
            <div className="space-y-0.5">
              <Label htmlFor="memoryScope">Agent-Specific Memory</Label>
              <p className="text-xs text-muted-foreground">
                Enable private memories per user (off = shared global memories)
              </p>
            </div>
            <Switch
              id="memoryScope"
              checked={memoryScope === 'agent'}
              onCheckedChange={(checked) => setMemoryScope(checked ? 'agent' : 'global')}
            />
          </div>

          {/* TTS Configuration - Aligned with Chatterbox TTS API */}
          <div className="space-y-4 pt-4 border-t">
            <h4 className="text-sm font-medium">Text-to-Speech Configuration (Optional)</h4>

            <div className="space-y-2">
              <Label htmlFor="ttsVoice">TTS Voice</Label>
              <Select
                value={ttsVoice || undefined}
                onValueChange={(value) => setTtsVoice(value === '_default' ? '' : value)}
                disabled={voicesLoading}
              >
                <SelectTrigger id="ttsVoice">
                  <SelectValue placeholder={voicesLoading ? "Loading voices..." : "Default (no voice)"} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="_default">Default (no voice)</SelectItem>
                  {Array.isArray(availableVoices) && availableVoices.length > 0 ? (
                    availableVoices.map((voice) => (
                      <SelectItem key={voice} value={voice}>
                        {voice.charAt(0).toUpperCase() + voice.slice(1)}
                      </SelectItem>
                    ))
                  ) : null}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {voicesLoading
                  ? "Loading available voices from Chatterbox TTS..."
                  : availableVoices.length > 0
                  ? `${availableVoices.length} voices available from Chatterbox TTS library`
                  : "Select a voice or leave as default"}
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="ttsExaggeration">
                Emotion Intensity: {ttsExaggeration.toFixed(2)}
              </Label>
              <Slider
                id="ttsExaggeration"
                value={[ttsExaggeration]}
                onValueChange={(vals) => setTtsExaggeration(vals[0])}
                min={0.25}
                max={2.0}
                step={0.05}
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">
                Controls emotional expressiveness (0.25 = subtle, 1.0 = normal, 2.0 = exaggerated)
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="ttsCfgWeight">
                Speech Pace: {ttsCfgWeight.toFixed(2)}
              </Label>
              <Slider
                id="ttsCfgWeight"
                value={[ttsCfgWeight]}
                onValueChange={(vals) => setTtsCfgWeight(vals[0])}
                min={0.0}
                max={1.0}
                step={0.05}
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">
                Controls speech pace (0.0 = faster, 1.0 = slower)
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="ttsTemperature">
                Voice Sampling: {ttsTemperature.toFixed(2)}
              </Label>
              <Slider
                id="ttsTemperature"
                value={[ttsTemperature]}
                onValueChange={(vals) => setTtsTemperature(vals[0])}
                min={0.05}
                max={5.0}
                step={0.05}
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">
                Controls voice variation (0.05 = consistent, 0.3 = default, 5.0 = highly variable)
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="ttsLanguage">Language</Label>
              <Select value={ttsLanguage} onValueChange={setTtsLanguage}>
                <SelectTrigger id="ttsLanguage">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">English</SelectItem>
                  <SelectItem value="es">Spanish</SelectItem>
                  <SelectItem value="fr">French</SelectItem>
                  <SelectItem value="de">German</SelectItem>
                  <SelectItem value="it">Italian</SelectItem>
                  <SelectItem value="pt">Portuguese</SelectItem>
                  <SelectItem value="zh">Chinese</SelectItem>
                  <SelectItem value="ja">Japanese</SelectItem>
                  <SelectItem value="ko">Korean</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* TTS Action Filtering */}
            <div className="flex items-center justify-between space-x-2 py-2">
              <div className="space-y-0.5">
                <Label htmlFor="filterActionsForTts">Filter Action Text</Label>
                <p className="text-xs text-muted-foreground">
                  Remove roleplay actions (*text*) before TTS synthesis
                </p>
              </div>
              <Switch
                id="filterActionsForTts"
                checked={filterActionsForTts}
                onCheckedChange={setFilterActionsForTts}
              />
            </div>
            <p className="text-xs text-muted-foreground pl-1">
              When enabled, asterisk-wrapped actions like *nods* or *pauses thoughtfully* will be filtered from TTS output while preserving them in conversation history. Math expressions like 2*3*4 are preserved.
            </p>
          </div>

          {/* Voice Configuration */}
          <div className="space-y-4 pt-4 border-t">
            <h4 className="text-sm font-medium">Voice Configuration</h4>

            <div className="space-y-2">
              <Label htmlFor="maxUtteranceTimeMs">
                Max Utterance Time (ms)
              </Label>
              <Input
                id="maxUtteranceTimeMs"
                type="number"
                value={maxUtteranceTimeMs}
                onChange={(e) => setMaxUtteranceTimeMs(parseInt(e.target.value) || 120000)}
                placeholder="120000"
                min={0}
                step={1000}
              />
              <p className="text-xs text-muted-foreground">
                Maximum duration for a single speaking turn in milliseconds. Force-finalize if user speaks continuously beyond this limit. Default: 120000 (2 minutes). Set to 0 for unlimited.
              </p>
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
