/**
 * Admin Memory Settings Page
 * System-wide control over agent-specific memory policy
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
import { Shield, RotateCcw, Info, Database, Settings } from 'lucide-react';
import { useToastHelpers } from '@/components/ui/toast';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as memoryApi from '@/services/memory';

export function AdminMemorySettingsPage() {
  const [disableDialogOpen, setDisableDialogOpen] = useState(false);
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const toast = useToastHelpers();
  const queryClient = useQueryClient();

  // Fetch admin memory policy
  const { data: policyData, isLoading: policyLoading } = useQuery({
    queryKey: ['adminMemoryPolicy'],
    queryFn: () => memoryApi.getAdminMemoryPolicy(),
  });

  // Update admin memory policy
  const updatePolicyMutation = useMutation({
    mutationFn: (allow: boolean) =>
      memoryApi.updateAdminMemoryPolicy({ allow_agent_specific_memory_globally: allow }),
    onSuccess: (data) => {
      queryClient.setQueryData(['adminMemoryPolicy'], {
        source: 'database',
        policy: data.policy,
      });

      toast.success(
        data.policy.allow_agent_specific_memory_globally
          ? 'Agent-specific memory enabled globally'
          : 'Agent-specific memory disabled globally',
        data.policy.allow_agent_specific_memory_globally
          ? 'Agents can now store private memories'
          : 'All new memories will be forced to global scope'
      );

      setDisableDialogOpen(false);
    },
    onError: (error: any) => {
      console.error('[AdminMemorySettings] Failed to update policy:', error);
      toast.error('Failed to update admin policy', error?.message || 'Unknown error');
    },
  });

  // Reset admin memory policy
  const resetPolicyMutation = useMutation({
    mutationFn: () => memoryApi.resetAdminMemoryPolicy(),
    onSuccess: (data) => {
      queryClient.setQueryData(['adminMemoryPolicy'], {
        source: 'environment',
        policy: data.policy,
      });

      toast.success('Policy reset to defaults', 'Admin policy restored to environment variables');
      setResetDialogOpen(false);
    },
    onError: (error: any) => {
      console.error('[AdminMemorySettings] Failed to reset policy:', error);
      toast.error('Failed to reset policy', error?.message || 'Unknown error');
    },
  });

  const handleTogglePolicy = (checked: boolean) => {
    if (!checked) {
      // Show warning dialog before disabling
      setDisableDialogOpen(true);
    } else {
      // Enable directly (no warning needed)
      updatePolicyMutation.mutate(true);
    }
  };

  const handleReset = () => {
    setResetDialogOpen(true);
  };

  if (policyLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading admin settings...</p>
      </div>
    );
  }

  const policy = policyData?.policy;
  const source = policyData?.source;
  const isEnabled = policy?.allow_agent_specific_memory_globally ?? true;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Admin Memory Policy</h1>
        <p className="text-muted-foreground mt-2">
          System-wide control over agent-specific memory capabilities
        </p>
      </div>

      {/* Admin Policy Toggle Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            <CardTitle>Global Memory Policy</CardTitle>
          </div>
          <CardDescription>
            Control whether agent-specific memories are allowed system-wide
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Policy Source Badge */}
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Policy Source:</span>
            <span
              className={`px-2 py-0.5 rounded-md text-xs font-medium ${
                source === 'database'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-gray-100 text-gray-700'
              }`}
            >
              {source === 'database' ? 'Database Override' : 'Environment Default'}
            </span>
          </div>

          {/* Toggle Switch */}
          <div className="flex items-center justify-between pt-2">
            <div className="space-y-0.5">
              <Label htmlFor="admin-policy">Allow Agent-Specific Memory Globally</Label>
              <p className="text-sm text-muted-foreground">
                When enabled: Agents can store private memories (subject to user preferences)
                <br />
                When disabled: All memories are forced to global scope system-wide
              </p>
            </div>
            <Switch
              id="admin-policy"
              checked={isEnabled}
              onCheckedChange={handleTogglePolicy}
              disabled={updatePolicyMutation.isPending}
            />
          </div>

          {/* Current Status */}
          <div className="pt-2 border-t">
            <p className="text-xs text-muted-foreground">
              <strong>Current Status:</strong> Agent-specific memory is{' '}
              <span className={isEnabled ? 'text-green-600' : 'text-red-600'}>
                {isEnabled ? 'ALLOWED' : 'DISABLED'}
              </span>{' '}
              globally.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Two-Tier Hierarchy Explanation (Phase 8: Per-Agent Memory Preferences) */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Info className="h-5 w-5" />
            <CardTitle>Two-Tier Memory Hierarchy</CardTitle>
          </div>
          <CardDescription>
            How admin policy and user preferences interact
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-3">
            {/* Tier 1: Admin Global Policy */}
            <div className="flex items-start gap-3">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-red-100 text-red-700 text-xs font-bold flex-shrink-0">
                1
              </div>
              <div>
                <p className="text-sm font-medium">Admin Global Policy (Highest Priority)</p>
                <p className="text-xs text-muted-foreground">
                  System-wide on/off switch. When disabled, ALL memories forced to global
                  regardless of user or agent preferences.
                </p>
              </div>
            </div>

            {/* Tier 2: Per-Agent User Preference */}
            <div className="flex items-start gap-3">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex-shrink-0">
                2
              </div>
              <div>
                <p className="text-sm font-medium">Per-Agent User Preference</p>
                <p className="text-xs text-muted-foreground">
                  Users configure memory scope for each agent individually. Falls back to
                  agent's default memory_scope if no preference set.
                </p>
              </div>
            </div>
          </div>

          <div className="pt-2 border-t">
            <p className="text-xs text-muted-foreground">
              <strong>Key Changes:</strong> Removed global user toggle. Memory preferences now
              managed per-agent in the Agents page, providing fine-grained control while
              respecting admin policy.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Policy Management Actions */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            <CardTitle>Policy Management</CardTitle>
          </div>
          <CardDescription>Reset policy to environment defaults</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Button
              variant="outline"
              onClick={handleReset}
              className="w-full gap-2"
              disabled={resetPolicyMutation.isPending || source === 'environment'}
            >
              <RotateCcw className="h-4 w-4" />
              Reset to Environment Defaults
            </Button>
            <p className="text-xs text-muted-foreground">
              {source === 'environment'
                ? 'Policy is already using environment defaults'
                : 'Delete database override and restore environment variable defaults'}
            </p>
          </div>

          <div className="pt-2 border-t">
            <div className="flex items-start gap-2">
              <Database className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
              <p className="text-xs text-muted-foreground">
                <strong>Environment Variable:</strong> ADMIN_ALLOW_AGENT_SPECIFIC_MEMORY (default: true)
                <br />
                Database overrides take precedence over environment variables. Reset to use
                environment defaults.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Disable Policy Confirmation Dialog */}
      <AlertDialog open={disableDialogOpen} onOpenChange={setDisableDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Disable Agent-Specific Memory Globally?</AlertDialogTitle>
            <AlertDialogDescription>
              This will enforce global memory scope for ALL users and agents system-wide.
              <br />
              <br />
              <strong>Impact:</strong>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>All NEW memories will be forced to global scope (agent_id = NULL)</li>
                <li>Existing agent-specific memories will remain but won't be accessible</li>
                <li>Users CANNOT override this policy (admin has ultimate control)</li>
                <li>Per-agent memory_scope settings will be ignored</li>
              </ul>
              <br />
              Are you sure you want to disable agent-specific memory globally?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={updatePolicyMutation.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => updatePolicyMutation.mutate(false)}
              disabled={updatePolicyMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {updatePolicyMutation.isPending ? 'Disabling...' : 'Disable Globally'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reset Policy Confirmation Dialog */}
      <AlertDialog open={resetDialogOpen} onOpenChange={setResetDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset to Environment Defaults?</AlertDialogTitle>
            <AlertDialogDescription>
              This will delete the database override and restore the policy from environment
              variables.
              <br />
              <br />
              <strong>Current environment default:</strong> ADMIN_ALLOW_AGENT_SPECIFIC_MEMORY = true
              (maintains current behavior)
              <br />
              <br />
              Are you sure you want to reset to environment defaults?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={resetPolicyMutation.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => resetPolicyMutation.mutate()}
              disabled={resetPolicyMutation.isPending}
            >
              {resetPolicyMutation.isPending ? 'Resetting...' : 'Reset to Defaults'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
