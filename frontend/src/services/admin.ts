/**
 * Admin API Service
 *
 * Handles admin-only API calls for user management.
 */

import { getAccessToken } from './auth';

// Use relative URLs in production, localhost in development
const API_BASE_URL = import.meta.env.PROD
  ? ''
  : (import.meta.env.VITE_API_URL || 'http://localhost:4900');

const API_BASE = `${API_BASE_URL}/api/admin`;

export interface AdminUser {
  id: string;
  email: string | null;
  username: string | null;
  display_name: string | null;
  role: 'admin' | 'user';
  is_active: boolean;
  memory_extraction_enabled: boolean;
  created_at: string;
  last_login_at: string | null;
  facts_count: number;
}

export interface UserStats {
  total_users: number;
  active_users: number;
  admin_count: number;
  users_with_facts: number;
}

export interface UpdateUserRequest {
  role?: 'admin' | 'user';
  is_active?: boolean;
  display_name?: string;
}

// API helpers
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || 'An error occurred');
  }
  return response.json();
}

function getAuthHeaders(): HeadersInit {
  const token = getAccessToken();
  if (!token) {
    throw new Error('Not authenticated');
  }
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}

// Admin API calls
export async function listUsers(): Promise<AdminUser[]> {
  const response = await fetch(`${API_BASE}/users`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<AdminUser[]>(response);
}

export async function getUserStats(): Promise<UserStats> {
  const response = await fetch(`${API_BASE}/users/stats`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<UserStats>(response);
}

export async function getUser(userId: string): Promise<AdminUser> {
  const response = await fetch(`${API_BASE}/users/${userId}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<AdminUser>(response);
}

export async function updateUser(userId: string, request: UpdateUserRequest): Promise<AdminUser> {
  const response = await fetch(`${API_BASE}/users/${userId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify(request),
  });
  return handleResponse<AdminUser>(response);
}

export async function deleteUser(userId: string): Promise<{ message: string }> {
  const response = await fetch(`${API_BASE}/users/${userId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  return handleResponse<{ message: string }>(response);
}

export async function resetUserPassword(userId: string, newPassword: string): Promise<{ message: string }> {
  const response = await fetch(`${API_BASE}/users/${userId}/reset-password`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ new_password: newPassword }),
  });
  return handleResponse<{ message: string }>(response);
}
