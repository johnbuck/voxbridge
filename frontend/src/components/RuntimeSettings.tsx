/**
 * Runtime Settings Panel
 * Allows users to configure runtime parameters like silence threshold and max speaking time
 * Chatterbox-style icon button with dropdown
 */

import { useState, useEffect } from 'react';
import { Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { useToastHelpers } from '@/components/ui/toast';
import { api } from '@/services/api';

const STORAGE_KEY = 'voxbridge_runtime_settings';

interface RuntimeSettings {
  enabled: boolean;
  config: {
    SILENCE_THRESHOLD_MS: number;
    MAX_SPEAKING_TIME_MS: number;
    USE_STREAMING: boolean;
  };
}

const DEFAULT_SETTINGS: RuntimeSettings = {
  enabled: false,
  config: {
    SILENCE_THRESHOLD_MS: 800,
    MAX_SPEAKING_TIME_MS: 45000,
    USE_STREAMING: true,
  },
};

export function RuntimeSettings() {
  const [settings, setSettings] = useState<RuntimeSettings>(DEFAULT_SETTINGS);
  const [showSettings, setShowSettings] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const toast = useToastHelpers();

  // Load settings from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        setSettings(parsed);
        console.log('[Runtime Settings] Loaded from localStorage:', parsed);
      } catch (e) {
        console.error('Failed to parse stored runtime settings:', e);
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

      // Send to backend only if enabled
      if (settings.enabled) {
        await api.updateConfig(settings.config);
      }

      console.log('[Runtime Settings] Saved:', settings);

      // Show success toast
      toast.success(
        'Runtime settings saved!',
        settings.enabled
          ? 'Custom runtime configuration is now active'
          : 'Using default runtime configuration'
      );
    } catch (error) {
      console.error('[Runtime Settings] Failed to save:', error);
      toast.error(
        'Failed to save settings',
        error instanceof Error ? error.message : 'Unknown error'
      );
    } finally {
      setIsSaving(false);
    }
  };

  const updateConfig = <K extends keyof RuntimeSettings['config']>(
    key: K,
    value: RuntimeSettings['config'][K]
  ) => {
    setSettings((prev) => ({
      ...prev,
      config: {
        ...prev.config,
        [key]: value,
      },
    }));
  };

  const toggleEnabled = (enabled: boolean) => {
    setSettings((prev) => ({ ...prev, enabled }));
  };

  const closeSettings = () => {
    setShowSettings(false);
  };

  return (
    <div className="relative">
      {/* Settings Icon Button (Chatterbox-style) */}
      <button
        className="relative p-2 rounded-lg hover:bg-accent border border-border bg-card duration-300 dark:shadow-sm dark:hover:shadow-md cursor-pointer"
        title="Runtime Settings"
        onClick={() => setShowSettings(!showSettings)}
      >
        <Settings className="w-5 h-5 text-foreground" />
        <span className="sr-only">Runtime Settings</span>
      </button>

      {/* Dropdown (appears below button when open) */}
      {showSettings && (
        <>
          <div className="absolute top-full right-0 mt-2 bg-card border border-border rounded-lg shadow-lg p-4 w-[300px] sm:w-[500px] max-w-[70vw] z-10">
            <h3 className="text-sm font-medium text-foreground mb-3">Runtime Settings</h3>

            <div className="space-y-4">
              {/* Enable/Disable Toggle */}
              <div>
                <h4 className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide text-left">
                  Configuration
                </h4>
                <label className="flex items-center gap-3 cursor-pointer">
                  <Switch
                    checked={settings.enabled}
                    onCheckedChange={toggleEnabled}
                  />
                  <div className="text-left">
                    <div className="text-sm font-medium text-foreground">
                      Enable Custom Settings
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Override default runtime configuration
                    </div>
                  </div>
                </label>
              </div>

              {settings.enabled && (
                <>
                  {/* Timing Settings */}
                  <div>
                    <h4 className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide text-left">
                      Timing
                    </h4>
                    <div className="space-y-3">
                      <div>
                        <Label htmlFor="silenceThreshold" className="text-xs text-left block mb-1">
                          Silence Threshold (ms)
                        </Label>
                        <Input
                          id="silenceThreshold"
                          type="number"
                          min="100"
                          max="5000"
                          step="100"
                          value={settings.config.SILENCE_THRESHOLD_MS}
                          onChange={(e) =>
                            updateConfig('SILENCE_THRESHOLD_MS', parseInt(e.target.value))
                          }
                          className="h-8"
                        />
                        <p className="text-xs text-muted-foreground mt-1 text-left">
                          Silence duration before finalizing transcript (default: 800ms)
                        </p>
                      </div>

                      <div>
                        <Label htmlFor="maxSpeakingTime" className="text-xs text-left block mb-1">
                          Max Speaking Time (ms)
                        </Label>
                        <Input
                          id="maxSpeakingTime"
                          type="number"
                          min="5000"
                          max="120000"
                          step="1000"
                          value={settings.config.MAX_SPEAKING_TIME_MS}
                          onChange={(e) =>
                            updateConfig('MAX_SPEAKING_TIME_MS', parseInt(e.target.value))
                          }
                          className="h-8"
                        />
                        <p className="text-xs text-muted-foreground mt-1 text-left">
                          Maximum continuous speaking duration (default: 45000ms)
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Processing Options */}
                  <div>
                    <h4 className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide text-left">
                      Processing
                    </h4>
                    <label className="flex items-center gap-3 cursor-pointer">
                      <Switch
                        checked={settings.config.USE_STREAMING}
                        onCheckedChange={(checked) =>
                          updateConfig('USE_STREAMING', checked)
                        }
                      />
                      <div className="text-left">
                        <div className="text-sm font-medium text-foreground">
                          Enable Streaming
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Stream responses as they're generated
                        </div>
                      </div>
                    </label>
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
                </>
              )}
            </div>

            {/* Close Button */}
            <div className="mt-4 pt-3 border-t border-border">
              <button
                onClick={closeSettings}
                className="text-xs text-primary hover:text-primary/80 transition-colors duration-200 w-full text-center"
              >
                Close
              </button>
            </div>
          </div>

          {/* Backdrop (click to close) */}
          <div
            className="fixed inset-0 z-0"
            onClick={closeSettings}
          />
        </>
      )}
    </div>
  );
}
