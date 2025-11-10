/**
 * Agent Streaming Settings Component
 *
 * Configures sentence-level streaming for latency optimization.
 * Reduces time-to-first-audio from ~6.8s to ~2-3s (68% improvement).
 */

import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Info } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export interface StreamingConfig {
  streaming_enabled: boolean;
  streaming_min_sentence_length: number;
  streaming_max_concurrent_tts: number;
  streaming_error_strategy: 'skip' | 'retry' | 'fallback';
  streaming_interruption_strategy: 'immediate' | 'graceful' | 'drain';
}

interface AgentStreamingSettingsProps {
  config: StreamingConfig;
  onChange: (config: StreamingConfig) => void;
}

export function AgentStreamingSettings({ config, onChange }: AgentStreamingSettingsProps) {
  const updateConfig = (updates: Partial<StreamingConfig>) => {
    onChange({ ...config, ...updates });
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Sentence-Level Streaming</CardTitle>
            <CardDescription>
              Optimize latency by processing responses sentence-by-sentence
            </CardDescription>
          </div>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-5 w-5 text-muted-foreground cursor-help" />
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                <p>
                  Reduces time-to-first-audio from ~6.8s to ~2-3s (68% faster).
                  Works alongside Chatterbox TTS's native streaming capabilities.
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Enable Streaming Toggle */}
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="streaming-enabled">Enable Streaming</Label>
            <p className="text-sm text-muted-foreground">
              Process LLM responses sentence-by-sentence
            </p>
          </div>
          <Switch
            id="streaming-enabled"
            checked={config.streaming_enabled}
            onCheckedChange={(checked) =>
              updateConfig({ streaming_enabled: checked })
            }
          />
        </div>

        {/* Settings only visible when streaming is enabled */}
        {config.streaming_enabled && (
          <>
            {/* Minimum Sentence Length Slider */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="min-sentence-length">
                  Minimum Sentence Length
                </Label>
                <span className="text-sm text-muted-foreground">
                  {config.streaming_min_sentence_length} characters
                </span>
              </div>
              <Slider
                id="min-sentence-length"
                min={5}
                max={50}
                step={5}
                value={[config.streaming_min_sentence_length]}
                onValueChange={(values) =>
                  updateConfig({ streaming_min_sentence_length: values[0] })
                }
              />
              <p className="text-xs text-muted-foreground">
                Shorter sentences are buffered to avoid synthesizing very short phrases
              </p>
            </div>

            {/* Max Concurrent TTS Slider */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="max-concurrent-tts">
                  Max Concurrent TTS Requests
                </Label>
                <span className="text-sm text-muted-foreground">
                  {config.streaming_max_concurrent_tts} parallel
                </span>
              </div>
              <Slider
                id="max-concurrent-tts"
                min={1}
                max={8}
                step={1}
                value={[config.streaming_max_concurrent_tts]}
                onValueChange={(values) =>
                  updateConfig({ streaming_max_concurrent_tts: values[0] })
                }
              />
              <p className="text-xs text-muted-foreground">
                Higher values = faster but more GPU memory usage. Recommended: 3-4
              </p>
            </div>

            {/* Error Strategy Dropdown */}
            <div className="space-y-2">
              <Label htmlFor="error-strategy">TTS Error Strategy</Label>
              <Select
                value={config.streaming_error_strategy}
                onValueChange={(value: StreamingConfig['streaming_error_strategy']) =>
                  updateConfig({ streaming_error_strategy: value })
                }
              >
                <SelectTrigger id="error-strategy">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="skip">
                    <div>
                      <div className="font-medium">Skip</div>
                      <div className="text-xs text-muted-foreground">
                        Continue with next sentence (fastest, partial audio)
                      </div>
                    </div>
                  </SelectItem>
                  <SelectItem value="retry">
                    <div>
                      <div className="font-medium">Retry</div>
                      <div className="text-xs text-muted-foreground">
                        Retry up to 2 times (most reliable)
                      </div>
                    </div>
                  </SelectItem>
                  <SelectItem value="fallback">
                    <div>
                      <div className="font-medium">Fallback</div>
                      <div className="text-xs text-muted-foreground">
                        Synthesize remaining text as single chunk (safe)
                      </div>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                How to handle when individual sentence TTS synthesis fails
              </p>
            </div>

            {/* Interruption Strategy Dropdown */}
            <div className="space-y-2">
              <Label htmlFor="interruption-strategy">User Interruption Strategy</Label>
              <Select
                value={config.streaming_interruption_strategy}
                onValueChange={(value: StreamingConfig['streaming_interruption_strategy']) =>
                  updateConfig({ streaming_interruption_strategy: value })
                }
              >
                <SelectTrigger id="interruption-strategy">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="immediate">
                    <div>
                      <div className="font-medium">Immediate</div>
                      <div className="text-xs text-muted-foreground">
                        Cancel all queued TTS and stop playback (most responsive)
                      </div>
                    </div>
                  </SelectItem>
                  <SelectItem value="graceful">
                    <div>
                      <div className="font-medium">Graceful</div>
                      <div className="text-xs text-muted-foreground">
                        Finish current sentence, cancel queue (better UX)
                      </div>
                    </div>
                  </SelectItem>
                  <SelectItem value="drain">
                    <div>
                      <div className="font-medium">Drain</div>
                      <div className="text-xs text-muted-foreground">
                        Process 1-2 more sentences, then stop (completes thought)
                      </div>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                How to handle when user starts speaking while AI is responding
              </p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
