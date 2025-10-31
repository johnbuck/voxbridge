/**
 * WhisperX STT Settings Page
 * Speech-to-text service configuration
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
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
import { Slider } from '@/components/ui/slider';
import { Mic, Settings, Loader2, AlertCircle, CheckCircle, Server, Activity } from 'lucide-react';

// WhisperX configuration stored in localStorage
interface WhisperXConfig {
  model: string;
  language: string;
  batchSize: number;
  device: string;
  computeType: string;
}

const DEFAULT_CONFIG: WhisperXConfig = {
  model: 'small',
  language: 'en',
  batchSize: 16,
  device: 'auto',
  computeType: 'float16',
};

export function WhisperXSettingsPage() {
  const [settingsDialogOpen, setSettingsDialogOpen] = useState(false);
  const [currentSettings, setCurrentSettings] = useState<WhisperXConfig>(() => {
    const saved = localStorage.getItem('whisperx-config');
    return saved ? JSON.parse(saved) : DEFAULT_CONFIG;
  });

  // Fetch status for WhisperX info
  const { data: status, isLoading, error } = useQuery({
    queryKey: ['status'],
    queryFn: () => api.getStatus(),
    refetchInterval: 5000, // Poll every 5 seconds
  });

  const handleSaveSettings = () => {
    localStorage.setItem('whisperx-config', JSON.stringify(currentSettings));
    setSettingsDialogOpen(false);
  };

  const handleResetSettings = () => {
    setCurrentSettings(DEFAULT_CONFIG);
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Mic className="h-7 w-7 text-primary" />
            WhisperX STT
          </h2>
          <p className="text-muted-foreground mt-1">
            Speech-to-text service configuration
          </p>
        </div>
        <Card>
          <CardContent className="p-12">
            <div className="text-center space-y-3">
              <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
              <p className="text-sm text-muted-foreground">Loading WhisperX status...</p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Mic className="h-7 w-7 text-primary" />
            WhisperX STT
          </h2>
          <p className="text-muted-foreground mt-1">
            Speech-to-text service configuration
          </p>
        </div>
        <Card className="border-red-500/20 bg-red-500/5">
          <CardContent className="p-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-red-500 mb-1">Failed to load WhisperX status</p>
                <p className="text-xs text-muted-foreground">
                  {error instanceof Error ? error.message : 'Unknown error occurred'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const whisperxStatus = status?.whisperx;
  const deviceInfo = status?.devices?.whisperx;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Mic className="h-8 w-8 text-primary" />
            WhisperX STT
          </h1>
          <p className="text-muted-foreground mt-1">
            Speech-to-text service configuration
          </p>
        </div>
        <Button onClick={() => setSettingsDialogOpen(true)} size="lg">
          <Settings className="h-5 w-5 mr-2" />
          Configure
        </Button>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className={whisperxStatus?.serverConfigured ? 'border-green-500/20 bg-green-500/5' : 'border-red-500/20 bg-red-500/5'}>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">Status</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              {whisperxStatus?.serverConfigured ? (
                <>
                  <CheckCircle className="h-8 w-8 text-green-500" />
                  <div>
                    <p className="text-lg font-bold text-green-500">Connected</p>
                    <p className="text-xs text-muted-foreground">Server active</p>
                  </div>
                </>
              ) : (
                <>
                  <AlertCircle className="h-8 w-8 text-red-500" />
                  <div>
                    <p className="text-lg font-bold text-red-500">Disconnected</p>
                    <p className="text-xs text-muted-foreground">Server offline</p>
                  </div>
                </>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">Model Loaded</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <Activity className="h-8 w-8 text-primary" />
              <div>
                <p className="text-lg font-bold">{currentSettings.model}</p>
                <p className="text-xs text-muted-foreground">Current model</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">Device</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <Server className="h-8 w-8 text-blue-500" />
              <div>
                <p className="text-lg font-bold">{deviceInfo || currentSettings.device}</p>
                <p className="text-xs text-muted-foreground">Compute device</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Server URL Info */}
      {whisperxStatus?.serverUrl && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Server Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label className="text-xs text-muted-foreground">Server URL</Label>
              <div className="mt-1 font-mono text-sm bg-muted px-3 py-2 rounded-md">
                {whisperxStatus.serverUrl}
              </div>
            </div>
            <div className="flex gap-2">
              <Badge variant="outline" className="bg-blue-500/20 text-blue-400 border-blue-500/50">
                Language: {currentSettings.language}
              </Badge>
              <Badge variant="outline" className="bg-purple-500/20 text-purple-400 border-purple-500/50">
                Batch Size: {currentSettings.batchSize}
              </Badge>
              <Badge variant="outline" className="bg-green-500/20 text-green-400 border-green-500/50">
                {currentSettings.computeType}
              </Badge>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Configuration Section */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Model Configuration</CardTitle>
              <p className="text-sm text-muted-foreground mt-1">
                Configure WhisperX transcription settings
              </p>
            </div>
            <Button onClick={() => setSettingsDialogOpen(true)} size="sm">
              <Settings className="h-4 w-4 mr-2" />
              Configure
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <Label className="text-xs text-muted-foreground">Model</Label>
              <p className="font-semibold mt-1">{currentSettings.model}</p>
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Language</Label>
              <p className="font-semibold mt-1">{currentSettings.language}</p>
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Batch Size</Label>
              <p className="font-semibold mt-1">{currentSettings.batchSize}</p>
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Compute Type</Label>
              <p className="font-semibold mt-1">{currentSettings.computeType}</p>
            </div>
          </div>

          <div className="pt-3 border-t text-xs text-muted-foreground">
            <p>Note: Changes to these settings require restarting the WhisperX container to take effect.</p>
          </div>
        </CardContent>
      </Card>

      {/* Configuration Dialog */}
      <Dialog open={settingsDialogOpen} onOpenChange={setSettingsDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              Configure WhisperX
            </DialogTitle>
            <DialogDescription>
              Adjust WhisperX transcription settings. Changes are saved locally and require container restart.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Model Selection */}
            <div className="space-y-2">
              <Label htmlFor="model">Model</Label>
              <Select
                value={currentSettings.model}
                onValueChange={(value) => setCurrentSettings({ ...currentSettings, model: value })}
              >
                <SelectTrigger id="model">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="tiny">Tiny (fastest, lowest accuracy)</SelectItem>
                  <SelectItem value="base">Base</SelectItem>
                  <SelectItem value="small">Small (balanced)</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="large-v2">Large-v2 (slowest, highest accuracy)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Language */}
            <div className="space-y-2">
              <Label htmlFor="language">Language Code</Label>
              <Input
                id="language"
                value={currentSettings.language}
                onChange={(e) => setCurrentSettings({ ...currentSettings, language: e.target.value })}
                placeholder="en"
              />
              <p className="text-xs text-muted-foreground">
                Use ISO language codes (e.g., en, es, fr, de)
              </p>
            </div>

            {/* Batch Size */}
            <div className="space-y-2">
              <Label htmlFor="batch-size">Batch Size: {currentSettings.batchSize}</Label>
              <Slider
                id="batch-size"
                min={1}
                max={32}
                step={1}
                value={[currentSettings.batchSize]}
                onValueChange={([value]) => setCurrentSettings({ ...currentSettings, batchSize: value })}
              />
              <p className="text-xs text-muted-foreground">
                Higher values use more GPU memory but can be faster
              </p>
            </div>

            {/* Device */}
            <div className="space-y-2">
              <Label htmlFor="device">Device</Label>
              <Select
                value={currentSettings.device}
                onValueChange={(value) => setCurrentSettings({ ...currentSettings, device: value })}
              >
                <SelectTrigger id="device">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto (recommended)</SelectItem>
                  <SelectItem value="cuda">CUDA (GPU)</SelectItem>
                  <SelectItem value="cpu">CPU</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Compute Type */}
            <div className="space-y-2">
              <Label htmlFor="compute-type">Compute Type</Label>
              <Select
                value={currentSettings.computeType}
                onValueChange={(value) => setCurrentSettings({ ...currentSettings, computeType: value })}
              >
                <SelectTrigger id="compute-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="float16">Float16 (GPU recommended)</SelectItem>
                  <SelectItem value="int8">Int8 (CPU friendly)</SelectItem>
                  <SelectItem value="float32">Float32 (highest precision)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={handleResetSettings}>
              Reset to Defaults
            </Button>
            <Button onClick={handleSaveSettings}>
              Save Settings
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
