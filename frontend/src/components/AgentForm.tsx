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
import { Loader2 } from 'lucide-react';

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
  const [ttsVoice, setTtsVoice] = useState('');
  const [ttsRate, setTtsRate] = useState(1.0);
  const [ttsPitch, setTtsPitch] = useState(1.0);
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
      setTtsVoice(agent.tts_voice || '');
      setTtsRate(agent.tts_rate);
      setTtsPitch(agent.tts_pitch);
    } else {
      // Reset to defaults when creating
      setName('');
      setSystemPrompt('');
      setTemperature(0.7);
      setLlmProvider('openrouter');
      setLlmModel('anthropic/claude-3.5-sonnet');
      setUseN8n(false);
      setTtsVoice('');
      setTtsRate(1.0);
      setTtsPitch(1.0);
    }
  }, [agent, open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      await onSubmit({
        name,
        system_prompt: systemPrompt,
        temperature,
        llm_provider: llmProvider,
        llm_model: llmModel,
        use_n8n: useN8n,
        tts_voice: ttsVoice || null,
        tts_rate: ttsRate,
        tts_pitch: ttsPitch,
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
