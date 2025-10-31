/**
 * LLM Provider Card Component
 * Displays an LLM provider in card format with test/edit/delete actions
 */

import { useState } from 'react';
import type { LLMProvider } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Edit2, Trash2, Server, CheckCircle, XCircle, HelpCircle, Loader2, RefreshCw } from 'lucide-react';

interface LLMProviderCardProps {
  provider: LLMProvider;
  onEdit: (provider: LLMProvider) => void;
  onDelete: (provider: LLMProvider) => void;
  onTest: (provider: LLMProvider) => Promise<void>;
  onFetchModels: (provider: LLMProvider) => Promise<void>;
  testingProviderId?: string;
  fetchingProviderId?: string;
}

export function LLMProviderCard({
  provider,
  onEdit,
  onDelete,
  onTest,
  onFetchModels,
  testingProviderId,
  fetchingProviderId
}: LLMProviderCardProps) {
  const [connectionStatus, setConnectionStatus] = useState<'unknown' | 'connected' | 'error'>('unknown');

  const isTesting = testingProviderId === provider.id;
  const isFetching = fetchingProviderId === provider.id;

  const providerTypeColors = {
    openrouter: 'bg-purple-500/20 text-purple-400 border-purple-500/50',
    openai: 'bg-green-500/20 text-green-400 border-green-500/50',
    ollama: 'bg-blue-500/20 text-blue-400 border-blue-500/50',
    vllm: 'bg-orange-500/20 text-orange-400 border-orange-500/50',
    custom: 'bg-gray-500/20 text-gray-400 border-gray-500/50',
  };

  const providerTypeColor = provider.provider_type
    ? providerTypeColors[provider.provider_type as keyof typeof providerTypeColors] || providerTypeColors.custom
    : providerTypeColors.custom;

  const handleTest = async () => {
    try {
      await onTest(provider);
      setConnectionStatus('connected');
    } catch (error) {
      setConnectionStatus('error');
    }
  };

  const handleFetchModels = async () => {
    try {
      await onFetchModels(provider);
    } catch (error) {
      // Error handling in parent component
    }
  };

  const getConnectionStatusBadge = () => {
    if (isTesting) {
      return (
        <Badge variant="outline" className="bg-blue-500/20 text-blue-400 border-blue-500/50">
          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
          Testing...
        </Badge>
      );
    }

    switch (connectionStatus) {
      case 'connected':
        return (
          <Badge variant="outline" className="bg-green-500/20 text-green-400 border-green-500/50">
            <CheckCircle className="h-3 w-3 mr-1" />
            Connected
          </Badge>
        );
      case 'error':
        return (
          <Badge variant="outline" className="bg-red-500/20 text-red-400 border-red-500/50">
            <XCircle className="h-3 w-3 mr-1" />
            Error
          </Badge>
        );
      default:
        return (
          <Badge variant="outline" className="bg-gray-500/20 text-gray-400 border-gray-500/50">
            <HelpCircle className="h-3 w-3 mr-1" />
            Not Tested
          </Badge>
        );
    }
  };

  return (
    <Card className="relative hover:border-primary/50 transition-colors">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <CardTitle className="text-lg flex items-center gap-2 mb-2">
              <Server className="h-5 w-5 text-primary" />
              <span className="truncate">{provider.name}</span>
            </CardTitle>
            <div className="flex flex-wrap gap-2">
              {provider.provider_type && (
                <Badge variant="outline" className={providerTypeColor}>
                  {provider.provider_type}
                </Badge>
              )}
              {getConnectionStatusBadge()}
              {!provider.is_active && (
                <Badge variant="outline" className="bg-yellow-500/20 text-yellow-400 border-yellow-500/50">
                  Inactive
                </Badge>
              )}
            </div>
          </div>
          <div className="flex gap-1 ml-2">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onEdit(provider)}
              title="Edit provider"
            >
              <Edit2 className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive hover:text-destructive"
              onClick={() => onDelete(provider)}
              title="Delete provider"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-0">
        {/* Base URL */}
        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">Base URL</div>
          <div className="text-sm font-mono bg-muted px-2 py-1 rounded truncate">
            {provider.base_url}
          </div>
        </div>

        {/* API Key Status */}
        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">API Key</div>
          <div className="text-sm">
            {provider.has_api_key ? (
              <Badge variant="outline" className="bg-green-500/20 text-green-400 border-green-500/50">
                <CheckCircle className="h-3 w-3 mr-1" />
                Configured
              </Badge>
            ) : (
              <Badge variant="outline" className="bg-gray-500/20 text-gray-400 border-gray-500/50">
                Not Configured
              </Badge>
            )}
          </div>
        </div>

        {/* Models */}
        <div className="space-y-1">
          <div className="text-xs text-muted-foreground flex items-center justify-between">
            <span>Available Models</span>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs"
              onClick={handleFetchModels}
              disabled={isFetching}
              title="Fetch models from provider"
            >
              {isFetching ? (
                <>
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  Fetching...
                </>
              ) : (
                <>
                  <RefreshCw className="h-3 w-3 mr-1" />
                  Refresh
                </>
              )}
            </Button>
          </div>
          <div className="text-sm">
            {provider.models.length > 0 ? (
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="bg-primary/20 text-primary border-primary/50">
                  {provider.models.length} models
                </Badge>
                {provider.default_model && (
                  <span className="text-xs text-muted-foreground truncate">
                    Default: {provider.default_model}
                  </span>
                )}
              </div>
            ) : (
              <span className="text-xs text-muted-foreground">No models fetched yet</span>
            )}
          </div>
        </div>

        {/* Test Connection Button */}
        <div className="pt-2">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={handleTest}
            disabled={isTesting}
          >
            {isTesting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Testing Connection...
              </>
            ) : (
              <>
                <Server className="mr-2 h-4 w-4" />
                Test Connection
              </>
            )}
          </Button>
        </div>

        {/* Metadata */}
        <div className="text-xs text-muted-foreground pt-2 border-t">
          Created {new Date(provider.created_at).toLocaleDateString()}
        </div>
      </CardContent>
    </Card>
  );
}
