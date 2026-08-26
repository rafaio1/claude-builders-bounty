import { useQuery, useMutation } from '@tanstack/react-query';
import type { DashboardStats, User, Session } from '../types';

const API_BASE = '/api/v1';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

export function useDashboardStats() {
  return useQuery<DashboardStats>({
    queryKey: ['dashboard', 'stats'],
    queryFn: () => fetchJson<DashboardStats>('/dashboard/stats'),
    staleTime: 15_000,
  });
}

export function useUserProfile(userId: string) {
  return useQuery<User>({
    queryKey: ['users', userId],
    queryFn: () => fetchJson<User>(`/users/${userId}`),
    enabled: !!userId,
  });
}

export function useSessions() {
  return useQuery<Session[]>({
    queryKey: ['sessions'],
    queryFn: () => fetchJson<Session[]>('/sessions'),
    refetchInterval: 30_000,
  });
}

export function useLogin() {
  return useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      fetchJson<{ token: string }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify(credentials),
      }),
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: () =>
      fetchJson<void>('/auth/logout', { method: 'POST' }),
  });
}
