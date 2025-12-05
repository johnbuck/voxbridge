/**
 * MemoryPage Component
 * Full CRUD interface for user memory/facts management
 */

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Link } from 'wouter';
import { Plus, Brain, RefreshCw, Filter, Settings, Users, Briefcase, Folder, Heart, Activity, Star, CalendarDays } from 'lucide-react';
import { FactCard } from '@/components/FactCard';
import { PendingFactCard } from '@/components/PendingFactCard';
import {
  listUserFacts,
  createUserFact,
  updateUserFact,
  deleteUserFact,
  getMemorySettings,
} from '@/services/memory';
import type {
  UserFact,
  CreateFactRequest,
  UpdateFactRequest,
  PendingFact,
  FactOrPlaceholder,
  MemoryBank,
} from '@/services/memory';
import { api } from '@/services/api';
import { useToastHelpers } from '@/components/ui/toast';
import { useMemoryExtractionStatus } from '@/hooks/useMemoryExtractionStatus';

const DEFAULT_USER_ID = 'web_user_default'; // Unified user ID for all users until auth is implemented

interface EditingFact {
  fact: UserFact;
  updates: UpdateFactRequest;
}

export function MemoryPage() {
  const queryClient = useQueryClient();
  const toast = useToastHelpers();

  // State
  const [userId] = useState(DEFAULT_USER_ID);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editingFact, setEditingFact] = useState<EditingFact | null>(null);
  const [filterAgentId, setFilterAgentId] = useState<string>('all');
  const [filterMemoryBank, setFilterMemoryBank] = useState<string>('all');
  const [includeInvalid, setIncludeInvalid] = useState(false);
  const [pendingFacts, setPendingFacts] = useState<Map<string, PendingFact>>(new Map());

  // WebSocket monitoring for memory extraction tasks
  useMemoryExtractionStatus({
    onProcessing: (task) => {
      // Update pending fact status to processing
      setPendingFacts((prev) => {
        const updated = new Map(prev);
        const pending = updated.get(task.task_id);
        if (pending) {
          updated.set(task.task_id, { ...pending, status: 'processing', attempts: task.attempts });
        }
        return updated;
      });
    },
    onCompleted: (task) => {
      // Remove pending fact
      setPendingFacts((prev) => {
        const updated = new Map(prev);
        updated.delete(task.task_id);
        return updated;
      });

      toast.success(
        'Memory Extraction Complete',
        `Extracted ${task.facts_count || 0} facts from conversation`
      );
      // Refresh facts list
      queryClient.invalidateQueries({ queryKey: ['facts', userId] });
    },
    onFailed: (task) => {
      if (task.status === 'retrying') {
        setPendingFacts((prev) => {
          const updated = new Map(prev);
          const pending = updated.get(task.task_id);
          if (pending) {
            updated.set(task.task_id, { ...pending, status: 'processing', attempts: task.attempts });
          }
          return updated;
        });
        toast.warning(
          'Memory Extraction Retry',
          `Attempt ${task.attempts} failed, retrying... (${task.error || 'Unknown error'})`
        );
      } else {
        setPendingFacts((prev) => {
          const updated = new Map(prev);
          const pending = updated.get(task.task_id);
          if (pending) {
            updated.set(task.task_id, { ...pending, status: 'failed', error: task.error });
          }
          return updated;
        });
        toast.error(
          'Memory Extraction Failed',
          task.error || 'Failed to extract facts from conversation'
        );
      }
    },
  });

  // Create form state
  const [factScope, setFactScope] = useState<'global' | string>('global');  // 'global' or agent ID

  const [newFact, setNewFact] = useState<Omit<CreateFactRequest, 'agent_id' | 'scope'>>({
    fact_key: '',
    fact_value: '',
    fact_text: '',
    importance: 0.8,
    memory_bank: 'General',
  });

  // Queries
  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => api.getAgents(),
  });

  const {
    data: facts,
    isLoading: isLoadingFacts,
    error: factsError,
  } = useQuery({
    queryKey: ['facts', userId, filterAgentId, filterMemoryBank, includeInvalid],
    queryFn: () => {
      // Determine scope and agent_id parameters
      let scope: string | undefined;
      let agent_id: string | undefined;

      if (filterAgentId === 'all') {
        // Show all facts (no filtering)
        scope = undefined;
        agent_id = undefined;
      } else if (filterAgentId === 'global') {
        // Show only global facts (agent_id = NULL)
        scope = 'global';
        agent_id = undefined;
      } else {
        // Show specific agent's facts
        scope = undefined;
        agent_id = filterAgentId;
      }

      return listUserFacts(userId, {
        scope,
        agent_id,
        memory_bank: filterMemoryBank === 'all' ? undefined : filterMemoryBank,
        include_invalid: includeInvalid,
      });
    },
  });

  const { data: settings } = useQuery({
    queryKey: ['memory-settings', userId],
    queryFn: () => getMemorySettings(userId),
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: (request: CreateFactRequest) => createUserFact(userId, request),
    onSuccess: (response, variables) => {
      setIsCreateModalOpen(false);

      // Add optimistic pending fact
      const pendingFact: PendingFact = {
        id: response.task_id,
        isPending: true,
        status: 'queued',
        fact_key: variables.fact_key,
        fact_value: variables.fact_value,
        fact_text: variables.fact_text,
        importance: variables.importance || 0.8,
        agent_id: variables.agent_id,
        created_at: new Date().toISOString(),
      };

      setPendingFacts((prev) => new Map(prev).set(response.task_id, pendingFact));

      resetCreateForm();
      toast.info(
        'Fact Queued for Processing',
        'Processing in background...'
      );
    },
    onError: (error: Error) => {
      toast.error('Error', error.message);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ factId, updates }: { factId: string; updates: UpdateFactRequest }) =>
      updateUserFact(userId, factId, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['facts', userId] });
      setIsEditModalOpen(false);
      setEditingFact(null);
      toast.success('Success', 'Fact updated successfully');
    },
    onError: (error: Error) => {
      toast.error('Error', error.message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (factId: string) => deleteUserFact(userId, factId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['facts', userId] });
      queryClient.invalidateQueries({ queryKey: ['memory-settings', userId] });
      toast.success('Success', 'Fact deleted successfully');
    },
    onError: (error: Error) => {
      toast.error('Error', error.message);
    },
  });

  // Merge pending facts with real facts for rendering
  const allFacts: FactOrPlaceholder[] = useMemo(() => {
    const realFacts = facts || [];
    const pending = Array.from(pendingFacts.values());

    // Merge and sort by created_at (newest first)
    return [...pending, ...realFacts].sort((a, b) => {
      const aTime = new Date(a.created_at).getTime();
      const bTime = new Date(b.created_at).getTime();
      return bTime - aTime; // Descending order (newest first)
    });
  }, [facts, pendingFacts]);

  // Handlers
  const resetCreateForm = () => {
    setFactScope('global');
    setNewFact({
      fact_key: '',
      fact_value: '',
      fact_text: '',
      importance: 0.8,
      memory_bank: 'General',
    });
  };

  const handleCreate = () => {
    if (!newFact.fact_key || !newFact.fact_value) {
      toast.error('Validation Error', 'Fact key and value are required');
      return;
    }

    // Determine agent_id and scope based on selection
    const isGlobal = factScope === 'global';
    const agent_id = isGlobal ? (agents && agents[0]?.id) : factScope;

    if (!agent_id) {
      toast.error('Configuration Error', 'No agents available. Please create an agent first.');
      return;
    }

    const request: CreateFactRequest = {
      ...newFact,
      agent_id,
      scope: isGlobal ? 'global' : 'agent',
    };

    createMutation.mutate(request);
  };

  const handleEdit = (fact: UserFact) => {
    setEditingFact({
      fact,
      updates: {
        fact_value: fact.fact_value,
        fact_text: fact.fact_text || '',
        importance: fact.importance,
        memory_bank: fact.memory_bank,
      },
    });
    setIsEditModalOpen(true);
  };

  const handleUpdate = () => {
    if (!editingFact) return;

    updateMutation.mutate({
      factId: editingFact.fact.id,
      updates: editingFact.updates,
    });
  };

  const handleDelete = async (factId: string) => {
    deleteMutation.mutate(factId);
  };

  return (
    <div className="container mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Memory Management</h1>
          <p className="text-muted-foreground mt-1">
            View and manage your conversational memory
          </p>
        </div>
        <Button onClick={() => setIsCreateModalOpen(true)} className="gap-2">
          <Plus className="h-4 w-4" />
          Add Fact
        </Button>
      </div>

      {/* Stats Cards */}
      {settings && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Total Facts</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{settings.total_facts}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Global Facts</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{settings.global_facts}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Agent-Specific</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{settings.agent_specific_facts}</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Link to Settings */}
      <Card>
        <CardContent className="pt-6">
          <Link href="/settings/memory">
            <Button variant="outline" className="w-full gap-2">
              <Settings className="h-4 w-4" />
              Configure Memory Settings
            </Button>
          </Link>
          <p className="text-xs text-muted-foreground text-center mt-2">
            Manage memory extraction, export data, and privacy settings
          </p>
        </CardContent>
      </Card>

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-5 w-5" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Memory Bank Filter Tabs */}
          <div>
            <Label className="mb-2 block">Memory Bank</Label>
            <div className="flex flex-wrap gap-2">
              <Button
                variant={filterMemoryBank === 'all' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterMemoryBank('all')}
              >
                All Banks
              </Button>
              <Button
                variant={filterMemoryBank === 'Personal' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterMemoryBank('Personal')}
                className="gap-1"
              >
                <Users className="h-4 w-4" />
                Personal
              </Button>
              <Button
                variant={filterMemoryBank === 'Work' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterMemoryBank('Work')}
                className="gap-1"
              >
                <Briefcase className="h-4 w-4" />
                Work
              </Button>
              <Button
                variant={filterMemoryBank === 'General' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterMemoryBank('General')}
                className="gap-1"
              >
                <Folder className="h-4 w-4" />
                General
              </Button>
              <Button
                variant={filterMemoryBank === 'Relationships' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterMemoryBank('Relationships')}
                className="gap-1"
              >
                <Heart className="h-4 w-4" />
                Relationships
              </Button>
              <Button
                variant={filterMemoryBank === 'Health' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterMemoryBank('Health')}
                className="gap-1"
              >
                <Activity className="h-4 w-4" />
                Health
              </Button>
              <Button
                variant={filterMemoryBank === 'Interests' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterMemoryBank('Interests')}
                className="gap-1"
              >
                <Star className="h-4 w-4" />
                Interests
              </Button>
              <Button
                variant={filterMemoryBank === 'Events' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterMemoryBank('Events')}
                className="gap-1"
              >
                <CalendarDays className="h-4 w-4" />
                Events
              </Button>
            </div>
          </div>

          {/* Scope and Include Expired Filters */}
          <div className="flex flex-wrap gap-4">
            <div className="flex-1 min-w-[200px]">
              <Label htmlFor="agent-filter">Memory Scope</Label>
              <Select value={filterAgentId} onValueChange={setFilterAgentId}>
                <SelectTrigger id="agent-filter">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Memories</SelectItem>
                  <SelectItem value="global">Global</SelectItem>
                  {agents?.map((agent) => (
                    <SelectItem key={agent.id} value={agent.id}>
                      {agent.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end gap-4">
              <div className="flex items-center gap-2">
                <Switch
                  id="include-invalid"
                  checked={includeInvalid}
                  onCheckedChange={setIncludeInvalid}
                />
                <Label htmlFor="include-invalid">Include Expired</Label>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Facts List */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">Your Facts</h2>
          {facts && <Badge variant="secondary">{facts.length} facts</Badge>}
        </div>

        {isLoadingFacts && (
          <div className="text-center py-12">
            <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4" />
            <p className="text-muted-foreground">Loading facts...</p>
          </div>
        )}

        {factsError && (
          <Card className="bg-destructive/10 border-destructive">
            <CardContent className="pt-6">
              <p className="text-destructive">Error: {(factsError as Error).message}</p>
            </CardContent>
          </Card>
        )}

        {allFacts && allFacts.length === 0 && (
          <Card>
            <CardContent className="text-center py-12">
              <Brain className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
              <p className="text-muted-foreground">No facts yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                Start a conversation or add facts manually
              </p>
            </CardContent>
          </Card>
        )}

        {allFacts && allFacts.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {allFacts.map((item) =>
              'isPending' in item ? (
                <PendingFactCard
                  key={item.id}
                  pending={item}
                  onRetry={() => {
                    // Retry by creating a new fact with the same data
                    // Infer scope from whether agent_id is present
                    const isGlobal = !item.agent_id;
                    const agent_id = isGlobal ? (agents && agents[0]?.id) : item.agent_id;

                    if (!agent_id) return; // No agents available

                    createMutation.mutate({
                      fact_key: item.fact_key,
                      fact_value: item.fact_value,
                      fact_text: item.fact_text,
                      importance: item.importance,
                      agent_id,
                      scope: isGlobal ? 'global' : 'agent',
                    });
                  }}
                  onCancel={() => {
                    // Remove pending fact from state
                    setPendingFacts((prev) => {
                      const updated = new Map(prev);
                      updated.delete(item.id);
                      return updated;
                    });
                  }}
                />
              ) : (
                <FactCard key={item.id} fact={item} onEdit={handleEdit} onDelete={handleDelete} agents={agents} />
              )
            )}
          </div>
        )}
      </div>

      {/* Create Fact Modal */}
      <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New Fact</DialogTitle>
            <DialogDescription>Add a new fact to your memory</DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="fact-key">Fact Key *</Label>
              <Input
                id="fact-key"
                placeholder="e.g., favorite_color"
                value={newFact.fact_key}
                onChange={(e) => setNewFact({ ...newFact, fact_key: e.target.value })}
              />
            </div>

            <div>
              <Label htmlFor="fact-value">Fact Value *</Label>
              <Input
                id="fact-value"
                placeholder="e.g., blue"
                value={newFact.fact_value}
                onChange={(e) => setNewFact({ ...newFact, fact_value: e.target.value })}
              />
            </div>

            <div>
              <Label htmlFor="fact-text">Natural Language (Optional)</Label>
              <Textarea
                id="fact-text"
                placeholder="e.g., User's favorite color is blue"
                value={newFact.fact_text || ''}
                onChange={(e) => setNewFact({ ...newFact, fact_text: e.target.value })}
              />
            </div>

            <div>
              <Label htmlFor="fact-scope">Memory Scope</Label>
              <Select value={factScope} onValueChange={setFactScope}>
                <SelectTrigger id="fact-scope">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="global">Global (Shared across all agents)</SelectItem>
                  {agents?.map((agent) => (
                    <SelectItem key={agent.id} value={agent.id}>
                      {agent.name} (Agent-specific)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="memory-bank">Memory Bank</Label>
              <Select
                value={newFact.memory_bank || 'General'}
                onValueChange={(value: MemoryBank) => setNewFact({ ...newFact, memory_bank: value })}
              >
                <SelectTrigger id="memory-bank">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Personal">
                    <span className="flex items-center gap-2">
                      <Users className="h-4 w-4" />
                      Personal
                    </span>
                  </SelectItem>
                  <SelectItem value="Work">
                    <span className="flex items-center gap-2">
                      <Briefcase className="h-4 w-4" />
                      Work
                    </span>
                  </SelectItem>
                  <SelectItem value="General">
                    <span className="flex items-center gap-2">
                      <Folder className="h-4 w-4" />
                      General
                    </span>
                  </SelectItem>
                  <SelectItem value="Relationships">
                    <span className="flex items-center gap-2">
                      <Heart className="h-4 w-4" />
                      Relationships
                    </span>
                  </SelectItem>
                  <SelectItem value="Health">
                    <span className="flex items-center gap-2">
                      <Activity className="h-4 w-4" />
                      Health
                    </span>
                  </SelectItem>
                  <SelectItem value="Interests">
                    <span className="flex items-center gap-2">
                      <Star className="h-4 w-4" />
                      Interests
                    </span>
                  </SelectItem>
                  <SelectItem value="Events">
                    <span className="flex items-center gap-2">
                      <CalendarDays className="h-4 w-4" />
                      Events
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="importance">
                Importance: {((newFact.importance || 0.8) * 100).toFixed(0)}%
              </Label>
              <Slider
                id="importance"
                min={0}
                max={100}
                step={5}
                value={[(newFact.importance || 0.8) * 100]}
                onValueChange={([value]) => setNewFact({ ...newFact, importance: value / 100 })}
                className="mt-2"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Fact'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Fact Modal */}
      <Dialog open={isEditModalOpen} onOpenChange={setIsEditModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Fact</DialogTitle>
            <DialogDescription>Update fact details</DialogDescription>
          </DialogHeader>

          {editingFact && (
            <div className="space-y-4 py-4">
              <div>
                <Label>Fact Key (read-only)</Label>
                <Input value={editingFact.fact.fact_key} disabled />
              </div>

              <div>
                <Label htmlFor="edit-fact-value">Fact Value</Label>
                <Input
                  id="edit-fact-value"
                  value={editingFact.updates.fact_value || ''}
                  onChange={(e) =>
                    setEditingFact({
                      ...editingFact,
                      updates: { ...editingFact.updates, fact_value: e.target.value },
                    })
                  }
                />
              </div>

              <div>
                <Label htmlFor="edit-fact-text">Natural Language</Label>
                <Textarea
                  id="edit-fact-text"
                  value={editingFact.updates.fact_text || ''}
                  onChange={(e) =>
                    setEditingFact({
                      ...editingFact,
                      updates: { ...editingFact.updates, fact_text: e.target.value },
                    })
                  }
                />
              </div>

              <div>
                <Label htmlFor="edit-memory-bank">Memory Bank</Label>
                <Select
                  value={editingFact.updates.memory_bank || 'General'}
                  onValueChange={(value: MemoryBank) =>
                    setEditingFact({
                      ...editingFact,
                      updates: { ...editingFact.updates, memory_bank: value },
                    })
                  }
                >
                  <SelectTrigger id="edit-memory-bank">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Personal">
                      <span className="flex items-center gap-2">
                        <Users className="h-4 w-4" />
                        Personal
                      </span>
                    </SelectItem>
                    <SelectItem value="Work">
                      <span className="flex items-center gap-2">
                        <Briefcase className="h-4 w-4" />
                        Work
                      </span>
                    </SelectItem>
                    <SelectItem value="General">
                      <span className="flex items-center gap-2">
                        <Folder className="h-4 w-4" />
                        General
                      </span>
                    </SelectItem>
                    <SelectItem value="Relationships">
                      <span className="flex items-center gap-2">
                        <Heart className="h-4 w-4" />
                        Relationships
                      </span>
                    </SelectItem>
                    <SelectItem value="Health">
                      <span className="flex items-center gap-2">
                        <Activity className="h-4 w-4" />
                        Health
                      </span>
                    </SelectItem>
                    <SelectItem value="Interests">
                      <span className="flex items-center gap-2">
                        <Star className="h-4 w-4" />
                        Interests
                      </span>
                    </SelectItem>
                    <SelectItem value="Events">
                      <span className="flex items-center gap-2">
                        <CalendarDays className="h-4 w-4" />
                        Events
                      </span>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label htmlFor="edit-importance">
                  Importance: {((editingFact.updates.importance || 0.8) * 100).toFixed(0)}%
                </Label>
                <Slider
                  id="edit-importance"
                  min={0}
                  max={100}
                  step={5}
                  value={[(editingFact.updates.importance || 0.8) * 100]}
                  onValueChange={([value]) =>
                    setEditingFact({
                      ...editingFact,
                      updates: { ...editingFact.updates, importance: value / 100 },
                    })
                  }
                  className="mt-2"
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleUpdate} disabled={updateMutation.isPending}>
              {updateMutation.isPending ? 'Updating...' : 'Update Fact'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
