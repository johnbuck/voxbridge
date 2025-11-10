/**
 * LLM Providers Management Page
 * VoxBridge 2.0 Phase 6.5: LLM Provider Management UI
 *
 * Provides a dedicated interface for managing OpenAI-compatible LLM providers.
 */

import { useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { api, type LLMProvider, type LLMProviderCreate, type LLMProviderUpdate } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { LLMProviderCard } from '@/components/LLMProviderCard';
import { LLMProviderDialog } from '@/components/LLMProviderDialog';
import { useToastHelpers } from '@/components/ui/toast';
import { Server, Plus, Loader2, AlertCircle } from 'lucide-react';

export function LLMProvidersPage() {
  const [formOpen, setFormOpen] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<LLMProvider | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [providerToDelete, setProviderToDelete] = useState<LLMProvider | null>(null);
  const [testingProviderId, setTestingProviderId] = useState<string | undefined>();
  const [fetchingProviderId, setFetchingProviderId] = useState<string | undefined>();

  const queryClient = useQueryClient();
  const toast = useToastHelpers();

  // Fetch providers
  const { data: providers = [], isLoading, error } = useQuery({
    queryKey: ['llm-providers'],
    queryFn: () => api.getLLMProviders(),
    refetchInterval: 30000, // Poll every 30 seconds
  });

  // Create provider mutation
  const createProviderMutation = useMutation({
    mutationFn: (provider: LLMProviderCreate) => api.createLLMProvider(provider),
    onSuccess: (newProvider) => {
      queryClient.invalidateQueries({ queryKey: ['llm-providers'] });
      toast.success(`Provider "${newProvider.name}" created successfully!`);
    },
    onError: (error: any) => {
      toast.error(`Failed to create provider: ${error.message || 'Unknown error'}`);
    },
  });

  // Update provider mutation
  const updateProviderMutation = useMutation({
    mutationFn: ({ providerId, updates }: { providerId: string; updates: LLMProviderUpdate }) =>
      api.updateLLMProvider(providerId, updates),
    onSuccess: (updatedProvider) => {
      queryClient.invalidateQueries({ queryKey: ['llm-providers'] });
      toast.success(`Provider "${updatedProvider.name}" updated successfully!`);
    },
    onError: (error: any) => {
      toast.error(`Failed to update provider: ${error.message || 'Unknown error'}`);
    },
  });

  // Delete provider mutation
  const deleteProviderMutation = useMutation({
    mutationFn: (providerId: string) => api.deleteLLMProvider(providerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['llm-providers'] });
      toast.success('Provider deleted successfully!');
    },
    onError: (error: any) => {
      toast.error(`Failed to delete provider: ${error.message || 'Unknown error'}`);
    },
  });

  // Test connection mutation
  const testConnectionMutation = useMutation({
    mutationFn: (providerId: string) => api.testLLMProviderConnection(providerId),
    onSuccess: (result) => {
      if (result.success) {
        toast.success(
          `Connection successful! Found ${result.models_count} models (${result.response_time_ms}ms)`
        );
      } else {
        toast.error(`Connection failed: ${result.error || 'Unknown error'}`);
      }
    },
    onError: (error: any) => {
      toast.error(`Connection test failed: ${error.message || 'Unknown error'}`);
    },
    onSettled: () => {
      setTestingProviderId(undefined);
    },
  });

  // Fetch models mutation
  const fetchModelsMutation = useMutation({
    mutationFn: (providerId: string) => api.fetchLLMProviderModels(providerId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['llm-providers'] });
      if (result.success) {
        toast.success(`Fetched ${result.models_count} models successfully!`);
      }
    },
    onError: (error: any) => {
      toast.error(`Failed to fetch models: ${error.message || 'Unknown error'}`);
    },
    onSettled: () => {
      setFetchingProviderId(undefined);
    },
  });

  // Handlers
  const handleCreateProvider = () => {
    setSelectedProvider(null);
    setFormOpen(true);
  };

  const handleEditProvider = (provider: LLMProvider) => {
    setSelectedProvider(provider);
    setFormOpen(true);
  };

  const handleDeleteProvider = (provider: LLMProvider) => {
    setProviderToDelete(provider);
    setDeleteDialogOpen(true);
  };

  const handleTestConnection = async (provider: LLMProvider) => {
    setTestingProviderId(provider.id);
    try {
      await testConnectionMutation.mutateAsync(provider.id);
    } catch (error) {
      // Error handled by mutation
    }
  };

  const handleFetchModels = async (provider: LLMProvider) => {
    setFetchingProviderId(provider.id);
    try {
      await fetchModelsMutation.mutateAsync(provider.id);
    } catch (error) {
      // Error handled by mutation
    }
  };

  const confirmDelete = async () => {
    if (!providerToDelete) return;

    try {
      await deleteProviderMutation.mutateAsync(providerToDelete.id);
      setDeleteDialogOpen(false);
      setProviderToDelete(null);
    } catch (error) {
      // Error handled by mutation
    }
  };

  const handleFormSubmit = async (providerData: LLMProviderCreate) => {
    if (selectedProvider) {
      // Update existing provider
      await updateProviderMutation.mutateAsync({
        providerId: selectedProvider.id,
        updates: providerData as LLMProviderUpdate,
      });
    } else {
      // Create new provider
      await createProviderMutation.mutateAsync(providerData);
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <span className="ml-2 text-muted-foreground">Loading LLM providers...</span>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="container mx-auto px-4 py-8">
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              Error Loading LLM Providers
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">
              Failed to load LLM providers. Please check the backend server and try again.
            </p>
            <Button
              onClick={() => queryClient.invalidateQueries({ queryKey: ['llm-providers'] })}
              variant="outline"
              className="mt-4"
            >
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Server className="h-8 w-8 text-primary" />
            LLM Providers
          </h1>
          <p className="text-muted-foreground mt-1">
            Manage OpenAI-compatible LLM providers for your AI agents
          </p>
        </div>
        <Button onClick={handleCreateProvider} size="lg">
          <Plus className="mr-2 h-5 w-5" />
          Add Provider
        </Button>
      </div>

      {/* Quick Start Guide */}
      <Card className="bg-primary/5 border-primary/20">
        <CardContent className="pt-6">
          <h3 className="font-semibold mb-2">Quick Start Examples</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div>
              <p className="font-mono text-primary">OpenRouter</p>
              <p className="text-xs text-muted-foreground">https://openrouter.ai/api/v1</p>
            </div>
            <div>
              <p className="font-mono text-primary">Local Ollama</p>
              <p className="text-xs text-muted-foreground">http://localhost:11434/v1</p>
            </div>
            <div>
              <p className="font-mono text-primary">OpenAI</p>
              <p className="text-xs text-muted-foreground">https://api.openai.com/v1</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Provider Stats */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Server className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Total Providers:</span>
              <span className="text-2xl font-bold">{providers.length}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Active:</span>
              <span className="text-xl font-bold text-green-400">
                {providers.filter((p) => p.is_active).length}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Total Models:</span>
              <span className="text-xl font-bold text-blue-400">
                {providers.reduce((sum, p) => sum + p.models.length, 0)}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Provider Grid */}
      {providers.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center py-12">
            <Server className="h-12 w-12 text-muted-foreground mx-auto mb-4 opacity-50" />
            <h3 className="text-lg font-semibold mb-2">No LLM Providers Yet</h3>
            <p className="text-muted-foreground mb-4">
              Add your first LLM provider to enable AI capabilities in VoxBridge
            </p>
            <Button onClick={handleCreateProvider}>
              <Plus className="mr-2 h-4 w-4" />
              Add Your First Provider
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {providers.map((provider) => (
            <LLMProviderCard
              key={provider.id}
              provider={provider}
              onEdit={handleEditProvider}
              onDelete={handleDeleteProvider}
              onTest={handleTestConnection}
              onFetchModels={handleFetchModels}
              testingProviderId={testingProviderId}
              fetchingProviderId={fetchingProviderId}
            />
          ))}
        </div>
      )}

      {/* Provider Form Dialog */}
      <LLMProviderDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        provider={selectedProvider}
        onSubmit={handleFormSubmit}
        isSubmitting={createProviderMutation.isPending || updateProviderMutation.isPending}
      />

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete LLM Provider</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{providerToDelete?.name}"? This action cannot be
              undone. Agents using this provider will need to be reconfigured.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDeleteDialogOpen(false);
                setProviderToDelete(null);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={deleteProviderMutation.isPending}
            >
              {deleteProviderMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete Provider'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
