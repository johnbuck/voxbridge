/**
 * Memory Settings Page
 * Configure memory extraction, view statistics, and manage user data (GDPR)
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
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
import { Brain, Download, Trash2, Database, AlertTriangle, Settings } from 'lucide-react';
import { Link } from 'wouter';
import { useToastHelpers } from '@/components/ui/toast';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as memoryApi from '@/services/memory';

const USER_ID = 'web_user_default'; // Unified user ID for all users until auth is implemented

export function MemorySettingsPage() {
  const [deleteAllDialogOpen, setDeleteAllDialogOpen] = useState(false);
  const [agentMemoryDialogOpen, setAgentMemoryDialogOpen] = useState(false);
  const toast = useToastHelpers();
  const queryClient = useQueryClient();

  // Fetch memory settings
  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ['memorySettings', USER_ID],
    queryFn: () => memoryApi.getMemorySettings(USER_ID),
  });

  // Fetch admin memory policy
  const { data: adminPolicy } = useQuery({
    queryKey: ['adminMemoryPolicy'],
    queryFn: () => memoryApi.getAdminMemoryPolicy(),
  });

  // Update memory settings
  const updateSettingsMutation = useMutation({
    mutationFn: (updates: { memory_extraction_enabled?: boolean; allow_agent_specific_memory?: boolean }) =>
      memoryApi.updateMemorySettings(USER_ID, updates),
    onSuccess: (data) => {
      queryClient.setQueryData(['memorySettings', USER_ID], data);

      // Show appropriate success message
      if ('memory_extraction_enabled' in data) {
        toast.success(
          data.memory_extraction_enabled ? 'Memory extraction enabled' : 'Memory extraction disabled',
          data.memory_extraction_enabled
            ? 'New conversations will be analyzed for facts'
            : 'Facts will no longer be extracted from conversations'
        );
      }
      if ('allow_agent_specific_memory' in data) {
        toast.success(
          data.allow_agent_specific_memory ? 'Agent-specific memory enabled' : 'Agent-specific memory disabled',
          data.allow_agent_specific_memory
            ? 'Agents can now store private memories'
            : 'All new memories will be global'
        );
      }
    },
    onError: (error: any) => {
      console.error('[MemorySettings] Failed to update settings:', error);
      toast.error('Failed to update settings', error?.message || 'Unknown error');
    },
  });

  // Export user data
  const handleExport = async () => {
    try {
      const data = await memoryApi.exportUserData(USER_ID);
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `voxbridge-memory-export-${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast.success('Data exported', `Downloaded ${data.total_facts} facts`);
    } catch (error: any) {
      console.error('[MemorySettings] Failed to export data:', error);
      toast.error('Failed to export data', error?.message || 'Unknown error');
    }
  };

  // Delete all user data
  const deleteAllMutation = useMutation({
    mutationFn: () => memoryApi.deleteAllUserData(USER_ID),
    onSuccess: (data) => {
      toast.success(
        'All data deleted',
        `Deleted ${data.facts_deleted} facts. ${data.note}`
      );
      queryClient.invalidateQueries({ queryKey: ['memorySettings', USER_ID] });
      queryClient.invalidateQueries({ queryKey: ['userFacts', USER_ID] });
      setDeleteAllDialogOpen(false);
    },
    onError: (error: any) => {
      console.error('[MemorySettings] Failed to delete data:', error);
      toast.error('Failed to delete data', error?.message || 'Unknown error');
    },
  });

  const handleDeleteAll = () => {
    setDeleteAllDialogOpen(true);
  };

  if (settingsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading memory settings...</p>
      </div>
    );
  }

  const adminAllowsAgentMemory = adminPolicy?.policy?.allow_agent_specific_memory_globally ?? true;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Memory Settings</h1>
        <p className="text-muted-foreground mt-2">
          Configure how VoxBridge remembers information from your conversations
        </p>
      </div>

      {/* Admin Policy Warning Banner */}
      {!adminAllowsAgentMemory && (
        <Card className="border-yellow-500/50 bg-yellow-500/10">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
              <div className="space-y-2">
                <p className="text-sm font-medium text-yellow-600">
                  Admin Policy: Agent-Specific Memory Disabled Globally
                </p>
                <p className="text-xs text-yellow-600/90">
                  The administrator has disabled agent-specific memory system-wide. All new
                  memories will be forced to global scope regardless of your preference. You cannot
                  enable agent-specific memory until the admin policy is changed in the{' '}
                  <a href="/admin/memory-policy" className="underline hover:text-yellow-700">
                    Admin Panel
                  </a>.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Memory Extraction Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5" />
            <CardTitle>Automatic Memory Extraction</CardTitle>
          </div>
          <CardDescription>
            Automatically extract and store facts from your conversations
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="extraction">Enable Memory Extraction</Label>
              <p className="text-sm text-muted-foreground">
                Extract facts from conversations automatically
              </p>
            </div>
            <Switch
              id="extraction"
              checked={settings?.memory_extraction_enabled ?? false}
              onCheckedChange={(checked) => updateSettingsMutation.mutate({ memory_extraction_enabled: checked })}
              disabled={updateSettingsMutation.isPending}
            />
          </div>

          <div className="pt-2 border-t">
            <p className="text-xs text-muted-foreground">
              When enabled, VoxBridge will analyze conversations and automatically store important
              facts like your name, preferences, and context for better personalization.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Per-Agent Memory Management Link (Phase 7: Per-Agent Memory Preferences) */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5" />
            <CardTitle>Agent-Specific Memory</CardTitle>
          </div>
          <CardDescription>
            Manage memory preferences per agent
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Memory preferences are now managed per-agent instead of globally.
            Configure whether each agent stores private memories or uses shared
            knowledge in the Agents page.
          </p>

          <Link to="/agents">
            <Button variant="outline" className="w-full gap-2">
              <Settings className="h-4 w-4" />
              Manage Per-Agent Memory Settings
            </Button>
          </Link>

          <div className="pt-2 border-t">
            <p className="text-xs text-muted-foreground">
              <strong>How it works:</strong>
              <br />
              • Each agent has a default memory scope (global or agent-specific)
              <br />
              • You can override this default for your own conversations
              <br />
              • Private memories are specific to you + that agent
              <br />
              • Global memories are shared across all users
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Memory Statistics Card */}
      {settings && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5" />
              <CardTitle>Memory Statistics</CardTitle>
            </div>
            <CardDescription>Overview of stored memories</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between py-2 border-b">
              <span className="text-sm font-medium">Total Facts</span>
              <span className="text-sm text-muted-foreground">{settings.total_facts}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b">
              <span className="text-sm font-medium">Global Facts</span>
              <span className="text-sm text-muted-foreground">
                {settings.global_facts} (shared across agents)
              </span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-sm font-medium">Agent-Specific Facts</span>
              <span className="text-sm text-muted-foreground">
                {settings.agent_specific_facts} (private per agent)
              </span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Data Management Card (GDPR) */}
      <Card>
        <CardHeader>
          <CardTitle>Data Management</CardTitle>
          <CardDescription>Export or delete all your data (GDPR compliance)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Button variant="outline" onClick={handleExport} className="w-full gap-2">
              <Download className="h-4 w-4" />
              Export All Data (GDPR)
            </Button>
            <p className="text-xs text-muted-foreground">
              Download all your data in JSON format
            </p>
          </div>

          <div className="space-y-2 pt-2 border-t">
            <Button
              variant="destructive"
              onClick={handleDeleteAll}
              className="w-full gap-2"
              disabled={deleteAllMutation.isPending}
            >
              <Trash2 className="h-4 w-4" />
              Delete All Data
            </Button>
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-yellow-600 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-yellow-600">
                This will permanently delete all your facts and cannot be undone (GDPR right to
                erasure)
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Delete All Confirmation Dialog */}
      <AlertDialog open={deleteAllDialogOpen} onOpenChange={setDeleteAllDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete All Your Data?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete all {settings?.total_facts || 0} facts stored for your
              account, including both global and agent-specific memories.
              <br />
              <br />
              This action cannot be undone. Are you sure you want to proceed?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteAllMutation.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteAllMutation.mutate()}
              disabled={deleteAllMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteAllMutation.isPending ? 'Deleting...' : 'Delete All Data'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Agent Memory Confirmation Dialog */}
      <AlertDialog open={agentMemoryDialogOpen} onOpenChange={setAgentMemoryDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Disable Agent-Specific Memory?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete ALL {settings?.agent_specific_facts || 0} agent-specific memories.
              <br />
              <br />
              <strong>When disabled:</strong>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>All existing agent-specific memories will be permanently deleted</li>
                <li>New memories will be global (shared across all agents)</li>
                <li>This action cannot be undone</li>
              </ul>
              <br />
              Are you sure you want to continue?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={updateSettingsMutation.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                updateSettingsMutation.mutate({ allow_agent_specific_memory: false });
                setAgentMemoryDialogOpen(false);
              }}
              disabled={updateSettingsMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {updateSettingsMutation.isPending ? 'Disabling...' : 'Disable & Delete Memories'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
