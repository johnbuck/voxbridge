/**
 * Memory API Client
 * Handles all memory-related API calls
 */

const API_BASE = 'http://localhost:4900/api/memory';

export interface UserFact {
  id: string;
  user_id: string;
  agent_id: string | null;
  fact_key: string;
  fact_value: string;
  fact_text: string | null;
  importance: number;
  vector_id: string | null;
  embedding_provider: string | null;
  embedding_model: string | null;
  validity_start: string;
  validity_end: string | null;
  created_at: string;
  updated_at: string;
  is_valid: boolean;
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
}

export interface UpdateFactRequest {
  fact_value?: string;
  fact_text?: string;
  importance?: number;
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
  params?: { scope?: string; agent_id?: string; include_invalid?: boolean }
): Promise<UserFact[]> {
  const queryParams = new URLSearchParams();
  if (params?.scope) queryParams.append('scope', params.scope);
  if (params?.agent_id) queryParams.append('agent_id', params.agent_id);
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
