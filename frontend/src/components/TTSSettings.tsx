/**
 * TTS Settings Panel
 * Allows users to override default TTS parameters for experimentation
 */

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToastHelpers } from '@/components/ui/toast';
import { api } from '@/services/api';

const STORAGE_KEY = 'voxbridge_tts_settings';

interface TTSSettings {
  enabled: boolean;
  options: {
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

    // Voice settings
    voiceMode?: 'default' | 'clone';
    voiceId?: string;
    referenceAudioFilename?: string;
  };
}

const DEFAULT_SETTINGS: TTSSettings = {
  enabled: false,
  options: {
    chunkSize: 200,
    streamingStrategy: 'sentence',
    streamingQuality: 'fast',
    streamingBufferSize: 3,
    temperature: 0.8,
    exaggeration: 0.6,
    cfgWeight: 0.4,
    speedFactor: 1.0,
    outputFormat: 'wav',
  },
};

export function TTSSettings() {
  const [settings, setSettings] = useState<TTSSettings>(DEFAULT_SETTINGS);
  const [isSaving, setIsSaving] = useState(false);
  const toast = useToastHelpers();

  // Load settings from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        setSettings(parsed);
        console.log('[TTS Settings] Loaded from localStorage:', parsed);
      } catch (e) {
        console.error('Failed to parse stored TTS settings:', e);
        toast.error('Failed to load saved settings', 'Using default values');
      }
    }
  }, [toast]);

  // Save settings to localStorage and backend
  const saveSettings = async () => {
    setIsSaving(true);
    try {
      // Save to localStorage
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));

      // Send to backend
      await api.setTTSOptions(settings.enabled, settings.options);

      console.log('[TTS Settings] Saved:', settings);

      // Show success toast
      toast.success(
        'Settings saved!',
        settings.enabled
          ? 'Custom TTS options are now active'
          : 'Using default TTS options'
      );
    } catch (error) {
      console.error('[TTS Settings] Failed to save:', error);
      toast.error(
        'Failed to save settings',
        error instanceof Error ? error.message : 'Unknown error'
      );
    } finally {
      setIsSaving(false);
    }
  };

  const updateOption = <K extends keyof TTSSettings['options']>(
    key: K,
    value: TTSSettings['options'][K]
  ) => {
    setSettings((prev) => ({
      ...prev,
      options: {
        ...prev.options,
        [key]: value,
      },
    }));
  };

  const toggleEnabled = (enabled: boolean) => {
    setSettings((prev) => ({ ...prev, enabled }));
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>TTS Settings</span>
          <Switch
            checked={settings.enabled}
            onCheckedChange={toggleEnabled}
          />
        </CardTitle>
        <p className="text-xs text-muted-foreground mt-1">
          Override default TTS parameters (experimental)
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {settings.enabled ? (
          <>
            {/* Streaming Settings */}
            <div className="space-y-3 border-b border-border pb-4">
              <h4 className="text-sm font-semibold">Streaming</h4>

              <div className="space-y-2">
                <Label htmlFor="chunkSize" className="text-xs">
                  Chunk Size
                </Label>
                <Input
                  id="chunkSize"
                  type="number"
                  min="10"
                  max="500"
                  value={settings.options.chunkSize}
                  onChange={(e) =>
                    updateOption('chunkSize', parseInt(e.target.value))
                  }
                  className="h-8"
                />
                <p className="text-xs text-muted-foreground">
                  Characters per chunk (default: 200)
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="streamingStrategy" className="text-xs">
                  Strategy
                </Label>
                <Select
                  value={settings.options.streamingStrategy}
                  onValueChange={(value) =>
                    updateOption(
                      'streamingStrategy',
                      value as 'sentence' | 'paragraph' | 'fixed' | 'word'
                    )
                  }
                >
                  <SelectTrigger id="streamingStrategy" className="h-8">
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
                <Label htmlFor="streamingBufferSize" className="text-xs">
                  Buffer Size
                </Label>
                <Input
                  id="streamingBufferSize"
                  type="number"
                  min="1"
                  max="10"
                  value={settings.options.streamingBufferSize}
                  onChange={(e) =>
                    updateOption('streamingBufferSize', parseInt(e.target.value))
                  }
                  className="h-8"
                />
                <p className="text-xs text-muted-foreground">
                  Streaming buffer size (default: 3)
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="streamingQuality" className="text-xs">
                  Quality
                </Label>
                <Select
                  value={settings.options.streamingQuality}
                  onValueChange={(value) =>
                    updateOption(
                      'streamingQuality',
                      value as 'fast' | 'balanced' | 'high'
                    )
                  }
                >
                  <SelectTrigger id="streamingQuality" className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fast">Fast</SelectItem>
                    <SelectItem value="balanced">Balanced</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Voice Generation */}
            <div className="space-y-3 border-b border-border pb-4">
              <h4 className="text-sm font-semibold">Voice Generation</h4>

              <div className="space-y-2">
                <Label htmlFor="temperature" className="text-xs">
                  Temperature
                </Label>
                <Input
                  id="temperature"
                  type="number"
                  min="0"
                  max="1"
                  step="0.1"
                  value={settings.options.temperature}
                  onChange={(e) =>
                    updateOption('temperature', parseFloat(e.target.value))
                  }
                  className="h-8"
                />
                <p className="text-xs text-muted-foreground">
                  Default: 0.8
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="exaggeration" className="text-xs">
                  Exaggeration
                </Label>
                <Input
                  id="exaggeration"
                  type="number"
                  min="0"
                  max="1"
                  step="0.1"
                  value={settings.options.exaggeration}
                  onChange={(e) =>
                    updateOption('exaggeration', parseFloat(e.target.value))
                  }
                  className="h-8"
                />
                <p className="text-xs text-muted-foreground">
                  Default: 0.6
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="cfgWeight" className="text-xs">
                  CFG Weight
                </Label>
                <Input
                  id="cfgWeight"
                  type="number"
                  min="0"
                  max="1"
                  step="0.1"
                  value={settings.options.cfgWeight}
                  onChange={(e) =>
                    updateOption('cfgWeight', parseFloat(e.target.value))
                  }
                  className="h-8"
                />
                <p className="text-xs text-muted-foreground">
                  Default: 0.4
                </p>
              </div>
            </div>

            {/* Output Settings */}
            <div className="space-y-3">
              <h4 className="text-sm font-semibold">Output</h4>

              <div className="space-y-2">
                <Label htmlFor="speedFactor" className="text-xs">
                  Speed Factor
                </Label>
                <Input
                  id="speedFactor"
                  type="number"
                  min="0.5"
                  max="2.0"
                  step="0.1"
                  value={settings.options.speedFactor}
                  onChange={(e) =>
                    updateOption('speedFactor', parseFloat(e.target.value))
                  }
                  className="h-8"
                />
                <p className="text-xs text-muted-foreground">
                  0.5 = half speed, 2.0 = double speed
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="outputFormat" className="text-xs">
                  Format
                </Label>
                <Select
                  value={settings.options.outputFormat}
                  onValueChange={(value) =>
                    updateOption('outputFormat', value as 'wav' | 'mp3')
                  }
                >
                  <SelectTrigger id="outputFormat" className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="wav">WAV</SelectItem>
                    <SelectItem value="mp3">MP3</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Save Button */}
            <Button
              onClick={saveSettings}
              disabled={isSaving}
              className="w-full"
              size="sm"
            >
              {isSaving ? 'Saving...' : 'Save Settings'}
            </Button>

            <p className="text-xs text-muted-foreground">
              Priority: n8n headers → Dashboard settings → Defaults
            </p>
          </>
        ) : (
          <div className="text-center py-6 text-muted-foreground">
            <p className="text-sm">
              Enable to override default TTS parameters
            </p>
            <p className="text-xs mt-2">
              Useful for experimenting with streaming strategies and fixing awkward pauses
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
