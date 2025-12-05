/**
 * NewConversationDialog Component
 * Dialog for creating a new conversation with agent selection
 * VoxBridge 2.0 Phase 4: Web Voice Interface
 */

import { useState, useEffect } from 'react';
import type { Agent } from '@/services/api';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
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
import { ScrollArea } from '@/components/ui/scroll-area';
import { Brain, Loader2 } from 'lucide-react';

interface NewConversationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: Agent[];
  isLoadingAgents: boolean;
  onCreateConversation: (agentId: string, title?: string) => Promise<void>;
}

export function NewConversationDialog({
  open,
  onOpenChange,
  agents,
  isLoadingAgents,
  onCreateConversation,
}: NewConversationDialogProps) {
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [title, setTitle] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Auto-select default agent (or first agent) when dialog opens
  useEffect(() => {
    if (open && agents.length > 0 && !selectedAgentId) {
      // Select default agent if available, otherwise select first agent
      const defaultAgent = agents.find(a => a.is_default) || agents[0];
      setSelectedAgentId(defaultAgent.id);
    }
  }, [open, agents, selectedAgentId]);

  // Reset form when dialog closes
  useEffect(() => {
    if (!open) {
      setTitle('');
      setSelectedAgentId('');
    }
  }, [open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgentId) return;

    setIsSubmitting(true);
    try {
      await onCreateConversation(selectedAgentId, title || undefined);
      onOpenChange(false);
    } catch (error) {
      console.error('Failed to create conversation:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedAgent = agents.find((a) => a.id === selectedAgentId);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-2xl mx-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            Start New Conversation
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Title (Optional) */}
          <div className="space-y-2">
            <Label htmlFor="title">Conversation Title (Optional)</Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Project Planning Discussion"
              maxLength={200}
            />
            <p className="text-xs text-muted-foreground">
              Leave empty to auto-generate from timestamp
            </p>
          </div>

          {/* Agent Selection */}
          <div className="space-y-2">
            <Label htmlFor="agent">Select AI Agent *</Label>
            {isLoadingAgents ? (
              <div className="text-center py-8 text-muted-foreground">
                <Loader2 className="h-6 w-6 mx-auto mb-2 animate-spin" />
                <p className="text-sm">Loading agents...</p>
              </div>
            ) : agents.length === 0 ? (
              <div className="text-center py-8 px-4 text-muted-foreground border border-dashed rounded-lg">
                <Brain className="h-12 w-12 mx-auto mb-3 opacity-50" />
                <p className="text-sm">No agents available</p>
                <p className="text-xs mt-1">Create an agent first in the VoxBridge dashboard</p>
              </div>
            ) : (
              <>
                <Select value={selectedAgentId} onValueChange={setSelectedAgentId}>
                  <SelectTrigger id="agent">
                    <SelectValue placeholder="Choose an agent" />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((agent) => (
                      <SelectItem key={agent.id} value={agent.id}>
                        {agent.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {/* Agent Preview */}
                {selectedAgent && (
                  <div className="mt-3 p-4 border border-border rounded-lg bg-muted/30 space-y-3">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h4 className="text-sm font-medium flex items-center gap-2 mb-1">
                          <Brain className="h-4 w-4 text-primary" />
                          {selectedAgent.name}
                        </h4>
                        <div className="text-xs text-muted-foreground space-y-0.5">
                          <div>Provider: <span className="font-mono">{selectedAgent.llm_provider}</span></div>
                          <div>Model: <span className="font-mono">{selectedAgent.llm_model}</span></div>
                          <div>Temperature: <span className="font-mono">{selectedAgent.temperature}</span></div>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-1">
                      <div className="text-xs font-medium text-muted-foreground">System Prompt</div>
                      <ScrollArea className="h-24 w-full rounded border bg-background/50 p-2">
                        <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">
                          {selectedAgent.system_prompt}
                        </p>
                      </ScrollArea>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          <DialogFooter className="flex-col-reverse sm:flex-row gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
              className="w-full sm:w-auto"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!selectedAgentId || isSubmitting || agents.length === 0}
              className="w-full sm:w-auto"
            >
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Start Conversation
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
