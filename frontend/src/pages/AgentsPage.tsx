/**
 * Agents Management Page
 * VoxBridge 2.0 Phase 2: Agent Management UI
 *
 * Provides a dedicated interface for managing AI agents with full CRUD operations.
 */

import { useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { api, type Agent, type AgentCreateRequest, type AgentUpdateRequest } from '@/services/api';
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
import { AgentCard } from '@/components/AgentCard';
import { AgentForm } from '@/components/AgentForm';
import { useToastHelpers } from '@/components/ui/toast';
import { Brain, Plus, Loader2, AlertCircle } from 'lucide-react';

export function AgentsPage() {
  const [formOpen, setFormOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [agentToDelete, setAgentToDelete] = useState<Agent | null>(null);

  const queryClient = useQueryClient();
  const toast = useToastHelpers();

  // Fetch agents
  const { data: agents = [], isLoading, error } = useQuery({
    queryKey: ['agents'],
    queryFn: () => api.getAgents(),
    refetchInterval: 10000, // Poll every 10 seconds for real-time updates
  });

  // Create agent mutation
  const createAgentMutation = useMutation({
    mutationFn: (agent: AgentCreateRequest) => api.createAgent(agent),
    onSuccess: (newAgent) => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
      toast.success(`Agent "${newAgent.name}" created successfully!`);
    },
    onError: (error: any) => {
      toast.error(`Failed to create agent: ${error.message || 'Unknown error'}`);
    },
  });

  // Update agent mutation
  const updateAgentMutation = useMutation({
    mutationFn: ({ agentId, updates }: { agentId: string; updates: AgentUpdateRequest }) =>
      api.updateAgent(agentId, updates),
    onSuccess: (updatedAgent) => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
      toast.success(`Agent "${updatedAgent.name}" updated successfully!`);
    },
    onError: (error: any) => {
      toast.error(`Failed to update agent: ${error.message || 'Unknown error'}`);
    },
  });

  // Delete agent mutation
  const deleteAgentMutation = useMutation({
    mutationFn: (agentId: string) => api.deleteAgent(agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
      toast.success(`Agent deleted successfully!`);
    },
    onError: (error: any) => {
      toast.error(`Failed to delete agent: ${error.message || 'Unknown error'}`);
    },
  });

  // Handlers
  const handleCreateAgent = () => {
    setSelectedAgent(null);
    setFormOpen(true);
  };

  const handleEditAgent = (agent: Agent) => {
    setSelectedAgent(agent);
    setFormOpen(true);
  };

  const handleDeleteAgent = (agent: Agent) => {
    setAgentToDelete(agent);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = async () => {
    if (!agentToDelete) return;

    try {
      await deleteAgentMutation.mutateAsync(agentToDelete.id);
      setDeleteDialogOpen(false);
      setAgentToDelete(null);
    } catch (error) {
      // Error handled by mutation
    }
  };

  const handleFormSubmit = async (agentData: AgentCreateRequest) => {
    if (selectedAgent) {
      // Update existing agent
      await updateAgentMutation.mutateAsync({
        agentId: selectedAgent.id,
        updates: agentData as AgentUpdateRequest,
      });
    } else {
      // Create new agent
      await createAgentMutation.mutateAsync(agentData);
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <span className="ml-2 text-muted-foreground">Loading agents...</span>
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
              Error Loading Agents
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">
              Failed to load agents. Please check the backend server and try again.
            </p>
            <Button
              onClick={() => queryClient.invalidateQueries({ queryKey: ['agents'] })}
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
    <div className="container mx-auto px-4 py-8">
      {/* Page Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Brain className="h-8 w-8 text-primary" />
            AI Agents
          </h1>
          <p className="text-muted-foreground mt-1">
            Manage your AI agent configurations and personalities
          </p>
        </div>
        <Button onClick={handleCreateAgent} size="lg">
          <Plus className="mr-2 h-5 w-5" />
          Create Agent
        </Button>
      </div>

      {/* Agent Count */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Brain className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Total Agents:</span>
              <span className="text-2xl font-bold">{agents.length}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Agent Grid */}
      {agents.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center py-12">
            <Brain className="h-12 w-12 text-muted-foreground mx-auto mb-4 opacity-50" />
            <h3 className="text-lg font-semibold mb-2">No Agents Yet</h3>
            <p className="text-muted-foreground mb-4">
              Create your first AI agent to get started with VoxBridge 2.0
            </p>
            <Button onClick={handleCreateAgent}>
              <Plus className="mr-2 h-4 w-4" />
              Create Your First Agent
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onEdit={handleEditAgent}
              onDelete={handleDeleteAgent}
            />
          ))}
        </div>
      )}

      {/* Agent Form Dialog */}
      <AgentForm
        open={formOpen}
        onOpenChange={setFormOpen}
        agent={selectedAgent}
        onSubmit={handleFormSubmit}
      />

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Agent</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{agentToDelete?.name}"? This action cannot be
              undone. All sessions and conversations associated with this agent will also be deleted.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDeleteDialogOpen(false);
                setAgentToDelete(null);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={deleteAgentMutation.isPending}
            >
              {deleteAgentMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete Agent'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
