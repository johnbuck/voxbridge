/**
 * Embeddings Settings Page
 * Configure global embedding provider for memory system
 *
 * NOTE: This page will be moved to admin-only access in a future phase.
 * Current implementation is accessible to all users.
 */

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Database, Settings, AlertTriangle, Zap, Cloud, Cpu, CheckCircle, Download, Trash2 } from 'lucide-react';
import { useToastHelpers } from '@/components/ui/toast';
import { api, type EmbeddingConfig, type EmbeddingConfigResponse, type EmbeddingModelStatus } from '@/services/api';

export function EmbeddingsSettingsPage() {
  const [config, setConfig] = useState<EmbeddingConfigResponse | null>(null);
  const [modelStatus, setModelStatus] = useState<EmbeddingModelStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Edited config for the dialog
  const [editedProvider, setEditedProvider] = useState<'azure' | 'local'>('local');
  const [azureApiKey, setAzureApiKey] = useState('');
  const [azureEndpoint, setAzureEndpoint] = useState('');
  const [azureDeployment, setAzureDeployment] = useState('text-embedding-3-large');
  const [localModel, setLocalModel] = useState('sentence-transformers/all-mpnet-base-v2');

  // Cleanup dialog state
  const [cleanupDialogOpen, setCleanupDialogOpen] = useState(false);
  const [isCleaningUp, setIsCleaningUp] = useState(false);

  const toast = useToastHelpers();

  // Fetch current config and model status on mount
  useEffect(() => {
    fetchConfig();
    fetchModelStatus();
  }, []);

  const fetchConfig = async () => {
    setIsLoading(true);
    try {
      const response = await api.getEmbeddingConfig();
      setConfig(response);

      // Initialize edit form with current values
      const provider = response.config.provider as 'azure' | 'local';
      setEditedProvider(provider);

      if (provider === 'azure') {
        // Note: API key is never returned for security reasons
        setAzureApiKey(''); // User must re-enter API key to update
        setAzureEndpoint(response.config.azure_endpoint || '');
        setAzureDeployment(response.config.azure_deployment || 'text-embedding-3-large');
      } else {
        setLocalModel(response.config.model || 'sentence-transformers/all-mpnet-base-v2');
      }
    } catch (error) {
      console.error('[EmbeddingsSettings] Failed to fetch config:', error);
      toast.error('Failed to load embeddings config', 'Using defaults');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchModelStatus = async () => {
    try {
      const status = await api.getEmbeddingModelStatus();
      setModelStatus(status);
    } catch (error) {
      console.error('[EmbeddingsSettings] Failed to fetch model status:', error);
      // Non-critical error, don't show toast
    }
  };

  const handleModelChange = async (newModel: string) => {
    // Update the selected model
    setLocalModel(newModel);

    // Immediately fetch cache status for the new model
    try {
      const status = await api.getEmbeddingModelStatus(newModel);
      setModelStatus(status);
    } catch (error) {
      console.error('[EmbeddingsSettings] Failed to fetch model status:', error);
      // Non-critical error, don't show toast
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const updateRequest: EmbeddingConfig = {
        provider: editedProvider,
      };

      if (editedProvider === 'azure') {
        if (!azureApiKey || !azureEndpoint) {
          toast.error('Azure credentials required', 'Please provide API key and endpoint');
          return;
        }
        updateRequest.azure_api_key = azureApiKey;
        updateRequest.azure_endpoint = azureEndpoint;
        updateRequest.azure_deployment = azureDeployment;
      } else {
        updateRequest.local_model = localModel;
        // Set dimensions based on model
        let dims = 768; // default
        if (localModel.includes('bge-large') || localModel.includes('e5-large')) {
          dims = 1024;
        } else if (localModel.includes('bge-small') || localModel.includes('MiniLM')) {
          dims = 384;
        } else if (localModel.includes('bge-base') || localModel.includes('mpnet') || localModel.includes('jina-embeddings')) {
          dims = 768;
        }
        updateRequest.local_dims = dims;
      }

      const response = await api.updateEmbeddingConfig(updateRequest);
      setConfig({
        source: 'database',
        config: response.config,
      });
      setEditDialogOpen(false);

      toast.success('Embeddings config saved!', 'Changes will take effect on next MemoryService initialization');

      // Auto-download model for local provider
      if (editedProvider === 'local') {
        // Check if model is already cached before showing download toast
        const preDownloadStatus = await api.getEmbeddingModelStatus(localModel);
        const isAlreadyCached = preDownloadStatus.status.is_cached;

        // Only show downloading toast if model needs to be downloaded
        if (!isAlreadyCached) {
          toast.info('Downloading model...', 'This may take several minutes for large models');
        }

        try {
          const downloadResult = await api.downloadEmbeddingModel();

          if (downloadResult.status === 'downloaded') {
            toast.success('Model downloaded!', `${downloadResult.model} is now cached`);
          } else if (downloadResult.status === 'already_cached') {
            toast.success('Model ready!', downloadResult.message);
          }

          // Refresh status after download completes
          await fetchModelStatus();
        } catch (error: any) {
          console.error('[EmbeddingsSettings] Model download failed:', error);
          toast.error('Model download failed', 'Model will download on first use');
          // Non-critical - model will download on first use
        }
      } else {
        // For Azure, just refresh status
        await fetchModelStatus();
      }
    } catch (error: any) {
      console.error('[EmbeddingsSettings] Failed to save config:', error);
      toast.error('Failed to save config', error?.message || 'Unknown error');
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = async () => {
    setIsSaving(true);
    try {
      const response = await api.resetEmbeddingConfig();
      setConfig({
        source: 'environment',
        config: response.config,
      });

      // Update form with reset values
      const provider = response.config.provider as 'azure' | 'local';
      setEditedProvider(provider);
      if (provider === 'local') {
        setLocalModel(response.config.model || 'sentence-transformers/all-mpnet-base-v2');
      }

      toast.success('Config reset to environment defaults!', 'Using .env configuration');
    } catch (error: any) {
      console.error('[EmbeddingsSettings] Failed to reset config:', error);
      toast.error('Failed to reset config', error?.message || 'Unknown error');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCleanup = async () => {
    setIsCleaningUp(true);
    try {
      const result = await api.cleanupEmbeddingModels();

      if (result.status === 'cleaned') {
        toast.success(
          `Cleaned up ${result.models_deleted.length} model(s)!`,
          `Reclaimed ${result.space_reclaimed_mb.toFixed(2)} MB. Kept: ${result.current_model}`
        );

        // Refresh model status after cleanup
        await fetchModelStatus();
      } else if (result.status === 'skipped') {
        toast.info('No cleanup needed', 'Azure provider does not cache models locally');
      }

      setCleanupDialogOpen(false);
    } catch (error: any) {
      console.error('[EmbeddingsSettings] Failed to cleanup models:', error);
      toast.error('Failed to cleanup models', error?.message || 'Unknown error');
    } finally {
      setIsCleaningUp(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading embeddings configuration...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Embeddings Configuration</h1>
        <p className="text-muted-foreground mt-2">
          Configure how VoxBridge generates embeddings for memory retrieval
        </p>
      </div>

      {/* Admin Warning */}
      <Card className="border-yellow-600/50 bg-yellow-600/10">
        <CardHeader>
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-yellow-600" />
            <CardTitle className="text-yellow-600">Admin Settings</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            This page will require admin access in a future update. Currently accessible to all users.
          </p>
        </CardContent>
      </Card>

      {/* Current Configuration */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5" />
              <CardTitle>Current Configuration</CardTitle>
            </div>
            <Badge variant={config?.source === 'database' ? 'default' : 'secondary'}>
              {config?.source === 'database' ? (
                <>
                  <Database className="h-3 w-3 mr-1" />
                  Database
                </>
              ) : (
                <>
                  <Settings className="h-3 w-3 mr-1" />
                  Environment
                </>
              )}
            </Badge>
          </div>
          <CardDescription>
            {config?.source === 'database'
              ? 'Configuration stored in database (persists across container restarts)'
              : 'Using environment variable defaults from .env file'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Provider */}
          <div className="flex items-center justify-between py-2 border-b">
            <span className="text-sm font-medium">Provider</span>
            <Badge variant="outline" className="flex items-center gap-1">
              {config?.config.provider === 'azure' ? (
                <>
                  <Cloud className="h-3 w-3" />
                  Azure OpenAI
                </>
              ) : (
                <>
                  <Cpu className="h-3 w-3" />
                  Local (HuggingFace)
                </>
              )}
            </Badge>
          </div>

          {/* Provider-specific details */}
          {config?.config.provider === 'azure' ? (
            <>
              <div className="flex items-center justify-between py-2 border-b">
                <span className="text-sm font-medium">Model</span>
                <span className="text-sm text-muted-foreground">text-embedding-3-large</span>
              </div>
              <div className="flex items-center justify-between py-2 border-b">
                <span className="text-sm font-medium">Dimensions</span>
                <span className="text-sm text-muted-foreground">3072</span>
              </div>
              <div className="flex items-center justify-between py-2 border-b">
                <span className="text-sm font-medium">Endpoint</span>
                <span className="text-sm text-muted-foreground font-mono text-xs">
                  {config?.config.azure_endpoint}
                </span>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between py-2 border-b">
                <span className="text-sm font-medium">Model</span>
                <span className="text-sm text-muted-foreground font-mono text-xs">
                  {config?.config.model}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 border-b">
                <span className="text-sm font-medium">Dimensions</span>
                <span className="text-sm text-muted-foreground">{config?.config.dims}</span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-sm font-medium">Cost</span>
                <Badge variant="secondary" className="flex items-center gap-1">
                  <Zap className="h-3 w-3" />
                  Free (Self-hosted)
                </Badge>
              </div>
            </>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-4">
            <Button onClick={() => setEditDialogOpen(true)} variant="default">
              <Settings className="h-4 w-4 mr-2" />
              Edit Configuration
            </Button>
            <Button onClick={handleReset} variant="outline" disabled={isSaving}>
              Reset to Defaults
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Model Cache Status */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5" />
              <CardTitle>Model Cache Status</CardTitle>
            </div>
            {modelStatus && modelStatus.provider === 'local' && (
              <Badge variant={modelStatus.status.is_cached ? 'default' : 'secondary'}>
                {modelStatus.status.is_cached ? (
                  <>
                    <CheckCircle className="h-3 w-3 mr-1" />
                    Downloaded
                  </>
                ) : (
                  <>
                    <Download className="h-3 w-3 mr-1" />
                    Not Cached
                  </>
                )}
              </Badge>
            )}
          </div>
          <CardDescription>
            Local embedding models are cached on disk for faster initialization
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {modelStatus && config?.config.provider === 'local' ? (
            <>
              <div className="flex items-center justify-between py-2 border-b">
                <span className="text-sm font-medium">Cache Status</span>
                <span className="text-sm text-muted-foreground">
                  {modelStatus.status.is_cached ? 'Downloaded' : 'Not Downloaded'}
                </span>
              </div>
              {modelStatus.status.is_cached && (
                <>
                  <div className="flex items-center justify-between py-2 border-b">
                    <span className="text-sm font-medium">Cache Size</span>
                    <span className="text-sm text-muted-foreground">
                      {modelStatus.status.cache_size_mb?.toFixed(2)} MB
                    </span>
                  </div>
                  <div className="flex items-center justify-between py-2 border-b">
                    <span className="text-sm font-medium">Files</span>
                    <span className="text-sm text-muted-foreground">
                      {modelStatus.status.files_count} files
                    </span>
                  </div>
                  <div className="flex items-center justify-between py-2">
                    <span className="text-sm font-medium">Last Updated</span>
                    <span className="text-sm text-muted-foreground">
                      {modelStatus.status.last_modified ? new Date(modelStatus.status.last_modified).toLocaleDateString() : 'Unknown'}
                    </span>
                  </div>
                </>
              )}
              {!modelStatus.status.is_cached && (
                <p className="text-sm text-muted-foreground">
                  Model will be downloaded automatically on first use (~{
                    modelStatus.model.includes('MiniLM') ? '80' :
                    modelStatus.model.includes('bge-small') ? '130' :
                    modelStatus.model.includes('mpnet') ? '420' :
                    modelStatus.model.includes('bge-base') ? '420' :
                    modelStatus.model.includes('jina-embeddings') ? '500' :
                    modelStatus.model.includes('bge-large') ? '1340' :
                    modelStatus.model.includes('e5-large') ? '1340' :
                    '500' // default fallback
                  }MB)
                </p>
              )}

              {/* Cleanup Button - Only show if model is cached */}
              {modelStatus.status.is_cached && (
                <div className="pt-4 border-t">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => setCleanupDialogOpen(true)}
                    disabled={isCleaningUp}
                    className="w-full"
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Clear Unused Models
                  </Button>
                  <p className="text-xs text-muted-foreground mt-2">
                    Deletes all cached models except the currently selected one
                  </p>
                </div>
              )}
            </>
          ) : modelStatus && config?.config.provider === 'azure' ? (
            <p className="text-sm text-muted-foreground">
              {modelStatus.status.message || 'Azure embeddings are API-based and do not require local caching'}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Loading model status...
            </p>
          )}
        </CardContent>
      </Card>

      {/* Priority Information */}
      <Card>
        <CardHeader>
          <CardTitle>Configuration Priority</CardTitle>
          <CardDescription>
            Embedding provider is configured using a 3-tier priority system
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="list-decimal list-inside space-y-2 text-sm">
            <li className="font-medium">
              Database (this page) - Highest priority, persists across restarts
            </li>
            <li className="text-muted-foreground">
              Environment variables (.env) - Fallback if database not configured
            </li>
            <li className="text-muted-foreground">
              Hardcoded defaults - Local embeddings (sentence-transformers)
            </li>
          </ol>
        </CardContent>
      </Card>

      {/* Edit Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Edit Embeddings Configuration</DialogTitle>
            <DialogDescription>
              Choose your embedding provider and configure the settings
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Provider Selection */}
            <div className="space-y-2">
              <Label htmlFor="provider">Provider</Label>
              <Select
                value={editedProvider}
                onValueChange={(value: 'azure' | 'local') => setEditedProvider(value)}
              >
                <SelectTrigger id="provider">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="local">
                    <div className="flex items-center gap-2">
                      <Cpu className="h-4 w-4" />
                      <span>Local (sentence-transformers)</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="azure">
                    <div className="flex items-center gap-2">
                      <Cloud className="h-4 w-4" />
                      <span>Azure OpenAI</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Azure Settings */}
            {editedProvider === 'azure' && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="azure-api-key">API Key</Label>
                  <Input
                    id="azure-api-key"
                    type="password"
                    placeholder="Your Azure OpenAI API key"
                    value={azureApiKey}
                    onChange={(e) => setAzureApiKey(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="azure-endpoint">Endpoint</Label>
                  <Input
                    id="azure-endpoint"
                    placeholder="https://your-resource.openai.azure.com"
                    value={azureEndpoint}
                    onChange={(e) => setAzureEndpoint(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="azure-deployment">Deployment Name</Label>
                  <Input
                    id="azure-deployment"
                    placeholder="text-embedding-3-large"
                    value={azureDeployment}
                    onChange={(e) => setAzureDeployment(e.target.value)}
                  />
                </div>
                <p className="text-xs text-yellow-600 flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  API key will be stored unencrypted. Encryption will be added in a future update.
                </p>
              </>
            )}

            {/* Local Settings */}
            {editedProvider === 'local' && (
              <div className="space-y-2">
                <Label htmlFor="local-model">Model</Label>
                <Select value={localModel} onValueChange={handleModelChange}>
                  <SelectTrigger id="local-model">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {/* 384 dims - Fast models */}
                    <SelectItem value="sentence-transformers/all-MiniLM-L6-v2">
                      all-MiniLM-L6-v2 (384 dims, 80MB, fast)
                    </SelectItem>
                    <SelectItem value="BAAI/bge-small-en-v1.5">
                      bge-small-en-v1.5 (384 dims, 130MB, better quality)
                    </SelectItem>

                    {/* 768 dims - Balanced models */}
                    <SelectItem value="sentence-transformers/all-mpnet-base-v2">
                      all-mpnet-base-v2 (768 dims, 420MB)
                    </SelectItem>
                    <SelectItem value="BAAI/bge-base-en-v1.5">
                      bge-base-en-v1.5 (768 dims, 420MB, recommended)
                    </SelectItem>
                    <SelectItem value="jinaai/jina-embeddings-v2-base-en">
                      jina-v2-base (768 dims, 500MB, 8K context)
                    </SelectItem>

                    {/* 1024 dims - High quality models */}
                    <SelectItem value="BAAI/bge-large-en-v1.5">
                      bge-large-en-v1.5 (1024 dims, 1.34GB, best quality)
                    </SelectItem>
                    <SelectItem value="intfloat/e5-large-v2">
                      e5-large-v2 (1024 dims, 1.34GB, high quality)
                    </SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Free, self-hosted embeddings using sentence-transformers
                </p>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? 'Saving...' : 'Save Configuration'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cleanup Confirmation Dialog */}
      <AlertDialog open={cleanupDialogOpen} onOpenChange={setCleanupDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Clear Unused Embedding Models?</AlertDialogTitle>
            <AlertDialogDescription>
              This will delete all cached embedding models except the currently selected one ({config?.config.model || 'unknown'}).
              <br /><br />
              This action cannot be undone. Deleted models can be re-downloaded later if needed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isCleaningUp}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleCleanup} disabled={isCleaningUp}>
              {isCleaningUp ? 'Cleaning up...' : 'Clear Unused Models'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
