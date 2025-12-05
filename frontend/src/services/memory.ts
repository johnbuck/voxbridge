/**
 * Memory API Client
 * Handles all memory-related API calls
 */

const API_BASE = 'http://localhost:4900/api/memory';

export type MemoryBank = 'Personal' | 'Work' | 'General' | 'Relationships' | 'Health' | 'Interests' | 'Events';

export interface UserFact {
  id: string;
  user_id: string;
  agent_id: string | null;
  fact_key: string;
  fact_value: string;
  fact_text: string | null;
  importance: number;
  memory_bank: MemoryBank;
  vector_id: string | null;
  embedding_provider: string | null;
  embedding_model: string | null;
  validity_start: string;
  validity_end: string | null;
  created_at: string;
  updated_at: string;
  is_valid: boolean;
  // Phase 2: Pruning
  last_accessed_at: string | null;
  is_protected: boolean;
  // Phase 3: Summarization
  is_summarized: boolean;
  summarized_from: string[] | null;  // Array of original fact IDs
}

export interface MemorySettings {
  user_id: string;
  display_name: string | null;
  embedding_provider: string | null;
  memory_extraction_enabled: boolean;
  allow_agent_specific_memory: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
  total_facts: number;
  global_facts: number;
  agent_specific_facts: number;
}

export interface CreateFactRequest {
  agent_id: string;  // Always required - agent to use for embedding config
  scope: 'global' | 'agent';  // 'global' = agent_id NULL in DB, 'agent' = agent_id UUID in DB
  fact_key: string;
  fact_value: string;
  fact_text?: string;
  importance?: number;
  memory_bank?: MemoryBank;  // Personal, Work, General
}

export interface UpdateFactRequest {
  fact_value?: string;
  fact_text?: string;
  importance?: number;
  memory_bank?: MemoryBank;  // Personal, Work, General
  validity_end?: string;
}

export interface UpdateSettingsRequest {
  display_name?: string;
  memory_extraction_enabled?: boolean;
  allow_agent_specific_memory?: boolean;
}

export interface CreateFactResponse {
  task_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  message: string;
}

export interface PendingFact {
  id: string; // task_id as temporary ID
  isPending: true;
  status: 'queued' | 'processing' | 'failed';
  fact_key: string;
  fact_value: string;
  fact_text?: string;
  importance: number;
  agent_id?: string;
  error?: string;
  attempts?: number;
  created_at: string; // ISO timestamp
}

export type FactOrPlaceholder = UserFact | PendingFact;

export interface GDPRExport {
  user_id: string;
  display_name: string | null;
  exported_at: string;
  total_facts: number;
  facts: UserFact[];
}

/**
 * List all facts for a user
 */
export async function listUserFacts(
  userId: string,
  params?: { scope?: string; agent_id?: string; memory_bank?: string; include_invalid?: boolean }
): Promise<UserFact[]> {
  const queryParams = new URLSearchParams();
  if (params?.scope) queryParams.append('scope', params.scope);
  if (params?.agent_id) queryParams.append('agent_id', params.agent_id);
  if (params?.memory_bank) queryParams.append('memory_bank', params.memory_bank);
  if (params?.include_invalid) queryParams.append('include_invalid', 'true');

  const url = `${API_BASE}/users/${userId}/facts${queryParams.toString() ? `?${queryParams}` : ''}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Failed to list facts: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Create a new fact (queues task for background processing)
 */
export async function createUserFact(
  userId: string,
  request: CreateFactRequest
): Promise<CreateFactResponse> {
  const response = await fetch(`${API_BASE}/users/${userId}/facts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to queue fact creation: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Update an existing fact
 */
export async function updateUserFact(
  userId: string,
  factId: string,
  request: UpdateFactRequest
): Promise<UserFact> {
  const response = await fetch(`${API_BASE}/users/${userId}/facts/${factId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to update fact: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Delete a fact
 */
export async function deleteUserFact(
  userId: string,
  factId: string
): Promise<{ status: string; fact_id: string }> {
  const response = await fetch(`${API_BASE}/users/${userId}/facts/${factId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new Error(`Failed to delete fact: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get memory settings
 */
export async function getMemorySettings(userId: string): Promise<MemorySettings> {
  const response = await fetch(`${API_BASE}/users/${userId}/settings`);

  if (!response.ok) {
    throw new Error(`Failed to get settings: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Update memory settings
 */
export async function updateMemorySettings(
  userId: string,
  request: UpdateSettingsRequest
): Promise<MemorySettings> {
  const response = await fetch(`${API_BASE}/users/${userId}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to update settings: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Export user data (GDPR)
 */
export async function exportUserData(userId: string): Promise<GDPRExport> {
  const response = await fetch(`${API_BASE}/users/${userId}/export`);

  if (!response.ok) {
    throw new Error(`Failed to export data: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Delete all user data (GDPR right to erasure)
 */
export async function deleteAllUserData(
  userId: string
): Promise<{ status: string; user_id: string; facts_deleted: number; note: string }> {
  const response = await fetch(`${API_BASE}/users/${userId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new Error(`Failed to delete user data: ${response.statusText}`);
  }

  return response.json();
}

// Admin Memory Policy API (System Settings)
const SYSTEM_SETTINGS_API_BASE = 'http://localhost:4900/api/system-settings';

export interface AdminMemoryPolicy {
  allow_agent_specific_memory_globally: boolean;
}

export interface AdminMemoryPolicyResponse {
  source: 'database' | 'environment';
  policy: AdminMemoryPolicy;
}

export interface AdminMemoryPolicyUpdateRequest {
  allow_agent_specific_memory_globally: boolean;
}

/**
 * Get admin-level memory policy
 */
export async function getAdminMemoryPolicy(): Promise<AdminMemoryPolicyResponse> {
  const response = await fetch(`${SYSTEM_SETTINGS_API_BASE}/admin-memory-policy`);

  if (!response.ok) {
    throw new Error(`Failed to get admin memory policy: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Update admin-level memory policy
 */
export async function updateAdminMemoryPolicy(
  request: AdminMemoryPolicyUpdateRequest
): Promise<{ status: string; policy: AdminMemoryPolicy; updated_at: string }> {
  const response = await fetch(`${SYSTEM_SETTINGS_API_BASE}/admin-memory-policy`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to update admin memory policy: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Reset admin memory policy to environment defaults
 */
export async function resetAdminMemoryPolicy(): Promise<{ status: string; policy: AdminMemoryPolicy }> {
  const response = await fetch(`${SYSTEM_SETTINGS_API_BASE}/admin-memory-policy/reset`, {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error(`Failed to reset admin memory policy: ${response.statusText}`);
  }

  return response.json();
}

// Per-Agent Memory Configuration (Phase 6: Interactive Memory Controls)
const AGENTS_API_BASE = 'http://localhost:4900/api/agents';

export interface AgentMemoryConfig {
  effective_scope: 'global' | 'agent';
  source: 'admin' | 'user' | 'agent';
  admin_allows: boolean;
  user_preference: {
    id: string;
    user_id: string;
    agent_id: string;
    allow_agent_specific_memory: boolean;
    created_at: string;
    updated_at: string;
  } | null;
  agent_default: 'global' | 'agent';
}

/**
 * Get effective memory configuration for an agent
 * Implements two-tier hierarchy: Admin Policy → User Preference → Agent Default
 */
export async function getAgentMemoryConfig(
  agentId: string,
  userId: string,
  agentDefault: 'global' | 'agent'
): Promise<AgentMemoryConfig> {
  // Tier 1: Check admin policy
  const adminPolicyResponse = await getAdminMemoryPolicy();
  const adminAllows = adminPolicyResponse.policy.allow_agent_specific_memory_globally;

  if (!adminAllows) {
    // Admin policy blocks agent-specific memory
    return {
      effective_scope: 'global',
      source: 'admin',
      admin_allows: false,
      user_preference: null,
      agent_default: agentDefault,
    };
  }

  // Tier 2: Check user preference
  try {
    const response = await fetch(
      `${AGENTS_API_BASE}/${agentId}/memory-preference?user_id=${encodeURIComponent(userId)}`
    );

    if (response.ok) {
      const userPref = await response.json();
      return {
        effective_scope: userPref.allow_agent_specific_memory ? 'agent' : 'global',
        source: 'user',
        admin_allows: true,
        user_preference: userPref,
        agent_default: agentDefault,
      };
    }

    // 404 means no user preference set, fall through to agent default
    if (response.status !== 404) {
      throw new Error(`Failed to get user preference: ${response.statusText}`);
    }
  } catch (error) {
    console.error('[getAgentMemoryConfig] Error fetching user preference:', error);
    // Fall through to agent default
  }

  // Tier 3: Use agent default
  return {
    effective_scope: agentDefault,
    source: 'agent',
    admin_allows: true,
    user_preference: null,
    agent_default: agentDefault,
  };
}

/**
 * Set user's memory preference for an agent
 */
export async function setUserAgentMemorySetting(
  agentId: string,
  userId: string,
  allowAgentSpecific: boolean
): Promise<AgentMemoryConfig> {
  const response = await fetch(`${AGENTS_API_BASE}/${agentId}/memory-preference`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      allow_agent_specific_memory: allowAgentSpecific,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to set memory preference: ${response.statusText}`);
  }

  const userPref = await response.json();

  // Re-fetch config to get effective scope with admin policy considered
  const adminPolicyResponse = await getAdminMemoryPolicy();
  const adminAllows = adminPolicyResponse.policy.allow_agent_specific_memory_globally;

  return {
    effective_scope: adminAllows && userPref.allow_agent_specific_memory ? 'agent' : 'global',
    source: 'user',
    admin_allows: adminAllows,
    user_preference: userPref,
    agent_default: userPref.allow_agent_specific_memory ? 'agent' : 'global', // Fallback approximation
  };
}

/**
 * Reset user's memory preference for an agent (delete override, revert to agent default)
 */
export async function resetUserAgentMemorySetting(
  agentId: string,
  userId: string,
  agentDefault: 'global' | 'agent'
): Promise<AgentMemoryConfig> {
  const response = await fetch(
    `${AGENTS_API_BASE}/${agentId}/memory-preference?user_id=${encodeURIComponent(userId)}`,
    { method: 'DELETE' }
  );

  if (!response.ok) {
    throw new Error(`Failed to reset memory preference: ${response.statusText}`);
  }

  // After deleting, effective scope reverts to agent default (if admin allows)
  const adminPolicyResponse = await getAdminMemoryPolicy();
  const adminAllows = adminPolicyResponse.policy.allow_agent_specific_memory_globally;

  return {
    effective_scope: adminAllows && agentDefault === 'agent' ? 'agent' : 'global',
    source: 'agent',
    admin_allows: adminAllows,
    user_preference: null,
    agent_default: agentDefault,
  };
}
