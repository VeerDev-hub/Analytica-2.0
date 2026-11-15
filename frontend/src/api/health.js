import { useQuery } from '@tanstack/react-query';
import { apiFetch } from './client.js';

/**
 * @typedef {{ status: 'ok' | 'down', latency_ms: number, error?: string | null }} DependencyStatus
 * @typedef {{ status: 'ok' | 'degraded', version: string, environment: string,
 *             dependencies: Record<string, DependencyStatus> }} HealthResponse
 */

/** @returns {Promise<HealthResponse>} */
export function fetchHealth() {
  // 503 still carries a useful body (which dependency is down).
  return apiFetch('/health', { allowStatus: [503] });
}

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: fetchHealth, refetchInterval: 10_000 });
}
