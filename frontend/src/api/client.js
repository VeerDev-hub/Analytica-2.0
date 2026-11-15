import { useAuthStore } from '../store/auth.js';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export class ApiError extends Error {
  /** @param {number} status @param {any} body */
  constructor(status, body) {
    super(body?.error?.message ?? `Request failed (${status})`);
    this.status = status;
    this.code = body?.error?.code ?? 'HTTP_ERROR';
    this.details = body?.error?.details ?? null;
    this.body = body;
  }
}

/** @type {Promise<boolean> | null} */
let refreshing = null;

/** Exchange the refresh cookie for a new access token. Concurrent callers share one call. */
export function refreshSession() {
  if (!refreshing) {
    refreshing = fetch(`${BASE_URL}/auth/refresh`, { method: 'POST', credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) {
          useAuthStore.getState().clear();
          return false;
        }
        useAuthStore.getState().setSession(await res.json());
        return true;
      })
      .catch(() => {
        useAuthStore.getState().clear();
        return false;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

/**
 * @param {string} path
 * @param {RequestInit & { json?: unknown, allowStatus?: number[], raw?: boolean,
 *   retry?: boolean }} [options]
 */
export async function apiFetch(path, options = {}) {
  const { json, allowStatus = [], raw = false, retry = true, ...init } = options;
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  const token = useAuthStore.getState().accessToken;
  if (token) headers.set('Authorization', `Bearer ${token}`);
  let body = init.body;
  if (json !== undefined) {
    headers.set('Content-Type', 'application/json');
    body = JSON.stringify(json);
  }
  const res = await fetch(`${BASE_URL}${path}`, { credentials: 'include', ...init, headers, body });

  if (res.status === 401 && retry && !path.startsWith('/auth/')) {
    if (await refreshSession()) return apiFetch(path, { ...options, retry: false });
  }
  if (raw) return res;
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok && !allowStatus.includes(res.status)) throw new ApiError(res.status, data);
  return data;
}

export const api = {
  get: (/** @type {string} */ p, /** @type {any} */ o) => apiFetch(p, o),
  post: (/** @type {string} */ p, /** @type {unknown} */ json, /** @type {any} */ o) =>
    apiFetch(p, { method: 'POST', json, ...o }),
  patch: (/** @type {string} */ p, /** @type {unknown} */ json) =>
    apiFetch(p, { method: 'PATCH', json }),
  put: (/** @type {string} */ p, /** @type {unknown} */ json) =>
    apiFetch(p, { method: 'PUT', json }),
  del: (/** @type {string} */ p, /** @type {unknown} */ json) => apiFetch(p, { method: 'DELETE', json }),
};
