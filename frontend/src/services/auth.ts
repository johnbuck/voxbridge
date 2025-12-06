/**
 * Authentication API Service
 *
 * Handles all auth-related API calls and token management.
 */

// Use relative URLs in production, localhost in development
const API_BASE_URL = import.meta.env.PROD
  ? ''
  : (import.meta.env.VITE_API_URL || 'http://localhost:4900');

const API_BASE = `${API_BASE_URL}/api/auth`;

// Token storage keys
const ACCESS_TOKEN_KEY = 'voxbridge_access_token';
const REFRESH_TOKEN_KEY = 'voxbridge_refresh_token';

export interface User {
  id: string;
  email: string | null;
  username: string | null;
  display_name: string | null;
  role: 'admin' | 'user';
  is_active: boolean;
  memory_extraction_enabled: boolean;
  timezone: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
  display_name?: string;
  timezone?: string;
}

export interface LoginRequest {
  username: string;  // Can be username or email
  password: string;
}

// Token management
export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(tokens: TokenResponse): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
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
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// Auth API calls
export async function register(request: RegisterRequest): Promise<TokenResponse> {
  const response = await fetch(`${API_BASE}/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  const tokens = await handleResponse<TokenResponse>(response);
  setTokens(tokens);
  return tokens;
}

export async function login(request: LoginRequest): Promise<TokenResponse> {
  const response = await fetch(`${API_BASE}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  const tokens = await handleResponse<TokenResponse>(response);
  setTokens(tokens);
  return tokens;
}

export async function refreshToken(): Promise<TokenResponse | null> {
  const token = getRefreshToken();
  if (!token) return null;

  try {
    const response = await fetch(`${API_BASE}/refresh`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    const tokens = await handleResponse<TokenResponse>(response);
    setTokens(tokens);
    return tokens;
  } catch {
    clearTokens();
    return null;
  }
}

export async function getCurrentUser(): Promise<User | null> {
  const token = getAccessToken();
  if (!token) return null;

  try {
    const response = await fetch(`${API_BASE}/me`, {
      headers: getAuthHeaders(),
    });
    return await handleResponse<User>(response);
  } catch {
    // Try to refresh token
    const refreshed = await refreshToken();
    if (!refreshed) return null;

    // Retry with new token
    const response = await fetch(`${API_BASE}/me`, {
      headers: getAuthHeaders(),
    });
    return await handleResponse<User>(response);
  }
}

export async function logout(): Promise<void> {
  const token = getAccessToken();
  if (token) {
    try {
      await fetch(`${API_BASE}/logout`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
    } catch {
      // Ignore logout errors
    }
  }
  clearTokens();
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const response = await fetch(`${API_BASE}/change-password`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    } as ChangePasswordRequest),
  });
  await handleResponse<{ message: string }>(response);
}

export interface UpdatePreferencesRequest {
  timezone?: string;
  display_name?: string;
}

export async function updatePreferences(request: UpdatePreferencesRequest): Promise<User> {
  const response = await fetch(`${API_BASE}/me/preferences`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(request),
  });
  return handleResponse<User>(response);
}
