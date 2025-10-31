/**
 * Chatterbox TTS Settings Page
 * Text-to-speech service configuration
 */

import { useState } from 'react';
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
import { Volume2, Settings, Server, Activity, Zap } from 'lucide-react';
import { useToastHelpers } from '@/components/ui/toast';

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

  const toast = useToastHelpers();

  const handleSaveSettings = () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(currentSettings));
    setSettingsDialogOpen(false);
    toast.success('Settings saved!', 'TTS configuration updated');
  };

  const handleResetSettings = () => {
    setCurrentSettings(DEFAULT_CONFIG);
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
    </div>
  );
}
