/**
 * Chatterbox TTS Settings Page
 * Text-to-speech service configuration
 */

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Volume2, Settings, Server, Activity, Zap, Layers } from 'lucide-react';
import { useToastHelpers } from '@/components/ui/toast';
import { api, type StreamingConfig } from '@/services/api';

// Chatterbox TTS configuration stored in localStorage
interface ChatterboxConfig {
  // Streaming settings
  chunkSize: number;
  streamingStrategy: 'sentence' | 'paragraph' | 'fixed' | 'word';
  streamingQuality: 'fast' | 'balanced' | 'high';
  streamingBufferSize: number;

  // Voice generation
  temperature: number;
  exaggeration: number;
  cfgWeight: number;

  // Output settings
  speedFactor: number;
  outputFormat: 'wav' | 'mp3';
}

const DEFAULT_CONFIG: ChatterboxConfig = {
  chunkSize: 200,
  streamingStrategy: 'sentence',
  streamingQuality: 'fast',
  streamingBufferSize: 3,
  temperature: 0.8,
  exaggeration: 0.6,
  cfgWeight: 0.4,
  speedFactor: 1.0,
  outputFormat: 'wav',
};

const STORAGE_KEY = 'voxbridge_tts_settings';

export function ChatterboxSettingsPage() {
  const [settingsDialogOpen, setSettingsDialogOpen] = useState(false);
  const [currentSettings, setCurrentSettings] = useState<ChatterboxConfig>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        // Extract options from old format if needed
        return parsed.options || parsed;
      } catch {
        return DEFAULT_CONFIG;
      }
    }
    return DEFAULT_CONFIG;
  });

  // Sentence-level streaming config (global, from environment variables)
  const [streamingConfig, setStreamingConfig] = useState<StreamingConfig | null>(null);
  const [streamingDialogOpen, setStreamingDialogOpen] = useState(false);
  const [editedStreamingConfig, setEditedStreamingConfig] = useState<StreamingConfig | null>(null);
  const [isSavingStreaming, setIsSavingStreaming] = useState(false);

  const toast = useToastHelpers();

  // Fetch global streaming config on mount
  useEffect(() => {
    const fetchStreamingConfig = async () => {
      try {
        const config = await api.getStreamingConfig();
        setStreamingConfig(config);
      } catch (error) {
        console.error('[ChatterboxSettings] Failed to fetch streaming config:', error);
        toast.error('Failed to load streaming config', 'Using defaults');
      }
    };
    fetchStreamingConfig();
  }, [toast]);

  const handleSaveSettings = () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(currentSettings));
    setSettingsDialogOpen(false);
    toast.success('Settings saved!', 'TTS configuration updated');
  };

  const handleResetSettings = () => {
    setCurrentSettings(DEFAULT_CONFIG);
  };

  const handleOpenStreamingDialog = () => {
    if (streamingConfig) {
      setEditedStreamingConfig({ ...streamingConfig });
      setStreamingDialogOpen(true);
    }
  };

  const handleSaveStreamingConfig = async () => {
    if (!editedStreamingConfig) return;

    setIsSavingStreaming(true);
    try {
      const updated = await api.updateStreamingConfig(editedStreamingConfig);
      setStreamingConfig(updated);
      setStreamingDialogOpen(false);
      toast.success('Streaming config saved!', 'Changes take effect immediately');
    } catch (error) {
      console.error('[ChatterboxSettings] Failed to save streaming config:', error);
      toast.error('Failed to save streaming config', error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setIsSavingStreaming(false);
    }
  };

  const handleResetStreamingConfig = async () => {
    setIsSavingStreaming(true);
    try {
      const reset = await api.resetStreamingConfig();
      setStreamingConfig(reset);
      setEditedStreamingConfig(reset);
      toast.success('Streaming config reset!', 'Restored environment defaults');
    } catch (error) {
      console.error('[ChatterboxSettings] Failed to reset streaming config:', error);
      toast.error('Failed to reset streaming config', error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setIsSavingStreaming(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Volume2 className="h-8 w-8 text-primary" />
            Chatterbox TTS
          </h1>
          <p className="text-muted-foreground mt-1">
            Text-to-speech service configuration
          </p>
        </div>
        <Button onClick={() => setSettingsDialogOpen(true)} size="lg">
          <Settings className="h-5 w-5 mr-2" />
          Configure
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Streaming Strategy */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Zap className="h-4 w-4 text-primary" />
              Streaming
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Strategy</span>
                <Badge variant="outline" className="bg-primary/20 text-primary border-primary/50">
                  {currentSettings.streamingStrategy}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Quality</span>
                <Badge variant="outline" className="bg-blue-500/20 text-blue-400 border-blue-500/50">
                  {currentSettings.streamingQuality}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Buffer</span>
                <span className="text-sm font-medium">{currentSettings.streamingBufferSize}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Voice Generation */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              Voice Generation
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Temperature</span>
                <span className="text-sm font-medium">{currentSettings.temperature.toFixed(1)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Exaggeration</span>
                <span className="text-sm font-medium">{currentSettings.exaggeration.toFixed(1)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">CFG Weight</span>
                <span className="text-sm font-medium">{currentSettings.cfgWeight.toFixed(1)}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Output Settings */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Server className="h-4 w-4 text-primary" />
              Output
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Format</span>
                <Badge variant="outline" className="bg-green-500/20 text-green-400 border-green-500/50">
                  {currentSettings.outputFormat.toUpperCase()}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Speed</span>
                <span className="text-sm font-medium">{currentSettings.speedFactor.toFixed(1)}x</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Chunk Size</span>
                <span className="text-sm font-medium">{currentSettings.chunkSize}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Streaming Configuration (Global) */}
      {streamingConfig && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg font-semibold flex items-center gap-2">
                  <Layers className="h-5 w-5 text-primary" />
                  Streaming Configuration
                </CardTitle>
                <p className="text-xs text-muted-foreground mt-1">
                  Control how LLM responses are chunked and sent to TTS (similar to Chatterbox streaming)
                </p>
              </div>
              <Button onClick={handleOpenStreamingDialog} size="sm">
                <Settings className="h-4 w-4 mr-2" />
                Configure
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Enabled</span>
                  <Badge variant="outline" className={streamingConfig.enabled ? "bg-green-500/20 text-green-400 border-green-500/50" : "bg-red-500/20 text-red-400 border-red-500/50"}>
                    {streamingConfig.enabled ? 'Yes' : 'No'}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Chunking Strategy</span>
                  <Badge variant="outline" className="bg-primary/20 text-primary border-primary/50">
                    {streamingConfig.chunking_strategy}
                  </Badge>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Min Chunk Length</span>
                  <span className="text-sm font-medium">{streamingConfig.min_chunk_length} chars</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Max Concurrent TTS</span>
                  <span className="text-sm font-medium">{streamingConfig.max_concurrent_tts}</span>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Error Strategy</span>
                  <Badge variant="outline" className="bg-blue-500/20 text-blue-400 border-blue-500/50">
                    {streamingConfig.error_strategy}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Interruption</span>
                  <Badge variant="outline" className="bg-purple-500/20 text-purple-400 border-purple-500/50">
                    {streamingConfig.interruption_strategy}
                  </Badge>
                </div>
              </div>
            </div>
            <div className="text-xs text-muted-foreground mt-4">
              <span className="font-semibold">Note:</span> Runtime changes reset on container restart (environment defaults restored)
            </div>
          </CardContent>
        </Card>
      )}

      {/* Configuration Dialog */}
      <Dialog open={settingsDialogOpen} onOpenChange={setSettingsDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Chatterbox TTS Configuration</DialogTitle>
            <DialogDescription>
              Configure text-to-speech voice settings and streaming options
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-6">
            {/* Streaming Settings */}
            <div className="space-y-4">
              <h4 className="text-sm font-semibold flex items-center gap-2">
                <Zap className="h-4 w-4" />
                Streaming
              </h4>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="chunkSize">Chunk Size</Label>
                  <Input
                    id="chunkSize"
                    type="number"
                    min="10"
                    max="500"
                    value={currentSettings.chunkSize}
                    onChange={(e) =>
                      setCurrentSettings({
                        ...currentSettings,
                        chunkSize: parseInt(e.target.value),
                      })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Characters per chunk (10-500)
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="streamingStrategy">Strategy</Label>
                  <Select
                    value={currentSettings.streamingStrategy}
                    onValueChange={(value) =>
                      setCurrentSettings({
                        ...currentSettings,
                        streamingStrategy: value as ChatterboxConfig['streamingStrategy'],
                      })
                    }
                  >
                    <SelectTrigger id="streamingStrategy">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="sentence">Sentence</SelectItem>
                      <SelectItem value="paragraph">Paragraph</SelectItem>
                      <SelectItem value="fixed">Fixed</SelectItem>
                      <SelectItem value="word">Word</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="streamingQuality">Quality</Label>
                  <Select
                    value={currentSettings.streamingQuality}
                    onValueChange={(value) =>
                      setCurrentSettings({
                        ...currentSettings,
                        streamingQuality: value as ChatterboxConfig['streamingQuality'],
                      })
                    }
                  >
                    <SelectTrigger id="streamingQuality">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="fast">Fast</SelectItem>
                      <SelectItem value="balanced">Balanced</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="streamingBufferSize">Buffer Size</Label>
                  <Input
                    id="streamingBufferSize"
                    type="number"
                    min="1"
                    max="10"
                    value={currentSettings.streamingBufferSize}
                    onChange={(e) =>
                      setCurrentSettings({
                        ...currentSettings,
                        streamingBufferSize: parseInt(e.target.value),
                      })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Chunks to buffer (1-10)
                  </p>
                </div>
              </div>
            </div>

            {/* Voice Generation */}
            <div className="space-y-4">
              <h4 className="text-sm font-semibold flex items-center gap-2">
                <Activity className="h-4 w-4" />
                Voice Generation
              </h4>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="temperature">Temperature</Label>
                  <Input
                    id="temperature"
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={currentSettings.temperature}
                    onChange={(e) =>
                      setCurrentSettings({
                        ...currentSettings,
                        temperature: parseFloat(e.target.value),
                      })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Voice randomness (0.0-1.0)
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="exaggeration">Exaggeration</Label>
                  <Input
                    id="exaggeration"
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={currentSettings.exaggeration}
                    onChange={(e) =>
                      setCurrentSettings({
                        ...currentSettings,
                        exaggeration: parseFloat(e.target.value),
                      })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Expression intensity (0.0-1.0)
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="cfgWeight">CFG Weight</Label>
                  <Input
                    id="cfgWeight"
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={currentSettings.cfgWeight}
                    onChange={(e) =>
                      setCurrentSettings({
                        ...currentSettings,
                        cfgWeight: parseFloat(e.target.value),
                      })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Guidance strength (0.0-1.0)
                  </p>
                </div>
              </div>
            </div>

            {/* Output Settings */}
            <div className="space-y-4">
              <h4 className="text-sm font-semibold flex items-center gap-2">
                <Server className="h-4 w-4" />
                Output
              </h4>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="speedFactor">Speed Factor</Label>
                  <Input
                    id="speedFactor"
                    type="number"
                    min="0.5"
                    max="2.0"
                    step="0.1"
                    value={currentSettings.speedFactor}
                    onChange={(e) =>
                      setCurrentSettings({
                        ...currentSettings,
                        speedFactor: parseFloat(e.target.value),
                      })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Playback speed (0.5-2.0x)
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="outputFormat">Output Format</Label>
                  <Select
                    value={currentSettings.outputFormat}
                    onValueChange={(value) =>
                      setCurrentSettings({
                        ...currentSettings,
                        outputFormat: value as 'wav' | 'mp3',
                      })
                    }
                  >
                    <SelectTrigger id="outputFormat">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="wav">WAV</SelectItem>
                      <SelectItem value="mp3">MP3</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={handleResetSettings}>
              Reset to Defaults
            </Button>
            <Button onClick={handleSaveSettings}>
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Streaming Configuration Dialog */}
      <Dialog open={streamingDialogOpen} onOpenChange={setStreamingDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Streaming Configuration</DialogTitle>
            <DialogDescription>
              Control how LLM responses are chunked and sent to TTS. Changes take effect immediately and persist until container restart.
            </DialogDescription>
          </DialogHeader>

          {editedStreamingConfig && (
            <div className="space-y-6">
              {/* Enable/Disable */}
              <div className="flex items-center justify-between">
                <div>
                  <Label htmlFor="streaming-enabled">Enable Streaming</Label>
                  <p className="text-xs text-muted-foreground mt-1">
                    Process LLM responses in chunks for lower latency
                  </p>
                </div>
                <input
                  id="streaming-enabled"
                  type="checkbox"
                  checked={editedStreamingConfig.enabled}
                  onChange={(e) =>
                    setEditedStreamingConfig({
                      ...editedStreamingConfig,
                      enabled: e.target.checked,
                    })
                  }
                  className="h-4 w-4"
                />
              </div>

              {/* Settings Grid */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="chunking-strategy">Chunking Strategy</Label>
                  <Select
                    value={editedStreamingConfig.chunking_strategy}
                    onValueChange={(value) =>
                      setEditedStreamingConfig({
                        ...editedStreamingConfig,
                        chunking_strategy: value as 'sentence' | 'paragraph' | 'word' | 'fixed',
                      })
                    }
                  >
                    <SelectTrigger id="chunking-strategy">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="sentence">Sentence</SelectItem>
                      <SelectItem value="paragraph">Paragraph</SelectItem>
                      <SelectItem value="word">Word</SelectItem>
                      <SelectItem value="fixed">Fixed</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    How to split LLM responses
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="min-chunk-length">Min Chunk Length</Label>
                  <Input
                    id="min-chunk-length"
                    type="number"
                    min="5"
                    max="200"
                    value={editedStreamingConfig.min_chunk_length}
                    onChange={(e) =>
                      setEditedStreamingConfig({
                        ...editedStreamingConfig,
                        min_chunk_length: parseInt(e.target.value),
                      })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Characters (5-200). Shorter chunks buffered.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="max-concurrent-tts">Max Concurrent TTS</Label>
                  <Input
                    id="max-concurrent-tts"
                    type="number"
                    min="1"
                    max="8"
                    value={editedStreamingConfig.max_concurrent_tts}
                    onChange={(e) =>
                      setEditedStreamingConfig({
                        ...editedStreamingConfig,
                        max_concurrent_tts: parseInt(e.target.value),
                      })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Parallel TTS requests (1-8)
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="error-strategy">Error Strategy</Label>
                  <Select
                    value={editedStreamingConfig.error_strategy}
                    onValueChange={(value) =>
                      setEditedStreamingConfig({
                        ...editedStreamingConfig,
                        error_strategy: value as 'skip' | 'retry' | 'fallback',
                      })
                    }
                  >
                    <SelectTrigger id="error-strategy">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="skip">Skip</SelectItem>
                      <SelectItem value="retry">Retry</SelectItem>
                      <SelectItem value="fallback">Fallback</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    How to handle TTS synthesis failures
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="interruption-strategy">Interruption Strategy</Label>
                  <Select
                    value={editedStreamingConfig.interruption_strategy}
                    onValueChange={(value) =>
                      setEditedStreamingConfig({
                        ...editedStreamingConfig,
                        interruption_strategy: value as 'immediate' | 'graceful' | 'drain',
                      })
                    }
                  >
                    <SelectTrigger id="interruption-strategy">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="immediate">Immediate</SelectItem>
                      <SelectItem value="graceful">Graceful</SelectItem>
                      <SelectItem value="drain">Drain</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    When user starts speaking mid-response
                  </p>
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={handleResetStreamingConfig}
              disabled={isSavingStreaming}
            >
              Reset to Environment Defaults
            </Button>
            <Button
              onClick={handleSaveStreamingConfig}
              disabled={isSavingStreaming}
            >
              {isSavingStreaming ? 'Saving...' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
