/**
 * LLM Provider Dialog Component
 * Dialog/modal for adding or editing LLM providers
 */

import { useState, useEffect } from 'react';
import type { LLMProvider, LLMProviderCreate } from '@/services/api';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, Eye, EyeOff, Server } from 'lucide-react';

interface LLMProviderDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  provider: LLMProvider | null;
  onSubmit: (data: LLMProviderCreate) => Promise<void>;
  isSubmitting?: boolean;
}

export function LLMProviderDialog({
  open,
  onOpenChange,
  provider,
  onSubmit,
  isSubmitting = false,
}: LLMProviderDialogProps) {
  const [formData, setFormData] = useState<LLMProviderCreate>({
    name: '',
    base_url: '',
    api_key: null,
    provider_type: null,
    default_model: null,
    is_active: true,
  });

  const [showApiKey, setShowApiKey] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [modelFilter, setModelFilter] = useState('');

  // Pre-populate form when editing
  useEffect(() => {
    if (provider) {
      setFormData({
        name: provider.name,
        base_url: provider.base_url,
        api_key: null, // Never populate API key for security
        provider_type: provider.provider_type,
        default_model: provider.default_model,
        is_active: provider.is_active,
      });
    } else {
      // Reset form for new provider
      setFormData({
        name: '',
        base_url: '',
        api_key: null,
        provider_type: null,
        default_model: null,
        is_active: true,
      });
    }
    setErrors({});
    setModelFilter(''); // Reset model filter when dialog opens/closes
  }, [provider, open]);

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.name.trim()) {
      newErrors.name = 'Provider name is required';
    }

    if (!formData.base_url.trim()) {
      newErrors.base_url = 'Base URL is required';
    } else {
      try {
        new URL(formData.base_url);
      } catch {
        newErrors.base_url = 'Invalid URL format';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    try {
      await onSubmit(formData);
      onOpenChange(false);
    } catch (error) {
      // Error handled by parent component
    }
  };

  const handleProviderTypeChange = (value: string) => {
    setFormData({ ...formData, provider_type: value === 'custom' ? null : value });

    // Set default base URLs for known providers
    const defaultUrls: Record<string, string> = {
      openrouter: 'https://openrouter.ai/api/v1',
      openai: 'https://api.openai.com/v1',
      ollama: 'http://localhost:11434/v1',
      vllm: 'http://localhost:8000/v1',
    };

    if (value in defaultUrls && !formData.base_url) {
      setFormData(prev => ({ ...prev, base_url: defaultUrls[value] }));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Server className="h-5 w-5" />
            {provider ? 'Edit LLM Provider' : 'Add LLM Provider'}
          </DialogTitle>
          <DialogDescription>
            {provider
              ? 'Update the configuration for this LLM provider.'
              : 'Configure a new OpenAI-compatible LLM provider.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Provider Name */}
          <div className="space-y-2">
            <Label htmlFor="name">
              Provider Name <span className="text-destructive">*</span>
            </Label>
            <Input
              id="name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="e.g., OpenRouter, Local Ollama, OpenAI"
              aria-invalid={!!errors.name}
            />
            {errors.name && (
              <p className="text-sm text-destructive">{errors.name}</p>
            )}
          </div>

          {/* Provider Type */}
          <div className="space-y-2">
            <Label htmlFor="provider_type">Provider Type</Label>
            <Select
              value={formData.provider_type || 'custom'}
              onValueChange={handleProviderTypeChange}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select provider type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="openrouter">OpenRouter</SelectItem>
                <SelectItem value="openai">OpenAI</SelectItem>
                <SelectItem value="ollama">Ollama</SelectItem>
                <SelectItem value="vllm">vLLM</SelectItem>
                <SelectItem value="custom">Custom</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Base URL */}
          <div className="space-y-2">
            <Label htmlFor="base_url">
              Base URL <span className="text-destructive">*</span>
            </Label>
            <Input
              id="base_url"
              type="url"
              value={formData.base_url}
              onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
              placeholder="https://api.openai.com/v1"
              aria-invalid={!!errors.base_url}
            />
            {errors.base_url && (
              <p className="text-sm text-destructive">{errors.base_url}</p>
            )}
            <p className="text-xs text-muted-foreground">
              Must be an OpenAI-compatible API endpoint (ending with /v1)
            </p>
          </div>

          {/* API Key */}
          <div className="space-y-2">
            <Label htmlFor="api_key">
              API Key
              {provider && (
                <span className="text-xs text-muted-foreground ml-2">
                  (leave blank to keep existing)
                </span>
              )}
            </Label>
            <div className="relative">
              <Input
                id="api_key"
                type={showApiKey ? 'text' : 'password'}
                value={formData.api_key || ''}
                onChange={(e) => setFormData({ ...formData, api_key: e.target.value || null })}
                placeholder={provider?.has_api_key ? '••••••••' : 'Optional for local providers'}
              />
              {/* Only show eye icon when user has entered a new key */}
              {formData.api_key && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-0 top-0 h-9 w-9"
                  onClick={() => setShowApiKey(!showApiKey)}
                >
                  {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {provider?.has_api_key
                ? 'For security, existing API key cannot be displayed. Enter a new key to replace it, or leave blank to keep the existing key.'
                : 'Optional for local providers like Ollama. Required for hosted services.'
              }
            </p>
          </div>

          {/* Default Model (if editing and models exist) */}
          {provider && provider.models.length > 0 && (
            <div className="space-y-2">
              <Label htmlFor="default_model">Default Model</Label>

              {/* Model filter input for providers with many models */}
              {provider.models.length > 20 && (
                <Input
                  placeholder="Filter models..."
                  value={modelFilter}
                  onChange={(e) => setModelFilter(e.target.value)}
                  className="mb-2"
                />
              )}

              <Select
                value={formData.default_model || undefined}
                onValueChange={(value) => setFormData({ ...formData, default_model: value || null })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select default model (or type below)" />
                </SelectTrigger>
                <SelectContent className="max-h-[300px]">
                  {(() => {
                    // Filter models based on search
                    const filteredModels = modelFilter
                      ? provider.models.filter(model =>
                          model.toLowerCase().includes(modelFilter.toLowerCase())
                        )
                      : provider.models;

                    // Limit to 100 models for performance
                    const displayModels = filteredModels.slice(0, 100);

                    return (
                      <>
                        {displayModels.map((model) => (
                          <SelectItem key={model} value={model}>
                            {model}
                          </SelectItem>
                        ))}
                        {filteredModels.length > 100 && (
                          <div className="px-2 py-1 text-xs text-muted-foreground">
                            ... and {filteredModels.length - 100} more. Use filter to narrow results.
                          </div>
                        )}
                      </>
                    );
                  })()}
                </SelectContent>
              </Select>

              {/* Direct input option for typing model name */}
              <div className="flex items-start gap-2 mt-2">
                <Input
                  placeholder="Or type model name directly"
                  value={formData.default_model || ''}
                  onChange={(e) => setFormData({ ...formData, default_model: e.target.value || null })}
                  className="flex-1"
                />
              </div>

              <p className="text-xs text-muted-foreground">
                {provider.models.length > 100
                  ? `Provider has ${provider.models.length} models. Use filter or type model name directly.`
                  : 'The default model to use with this provider'
                }
              </p>
            </div>
          )}

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
              {isSubmitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {provider ? 'Updating...' : 'Creating...'}
                </>
              ) : (
                <>{provider ? 'Update Provider' : 'Create Provider'}</>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
