import { create } from 'zustand';

/**
 * @typedef {{ id: string, email: string, display_name: string, role: string }} User
 * The access token lives only in memory; the refresh token is an HttpOnly cookie the
 * browser sends to /api/v1/auth/refresh. A page reload restores the session via refresh.
 */
export const useAuthStore = create((set) => ({
  /** @type {User | null} */ user: null,
  /** @type {string | null} */ accessToken: null,
  /** 'unknown' until the first refresh attempt finishes */
  status: /** @type {'unknown' | 'authenticated' | 'anonymous'} */ ('unknown'),
  setSession: (/** @type {{access_token: string, user: User}} */ s) =>
    set({ user: s.user, accessToken: s.access_token, status: 'authenticated' }),
  clear: () => set({ user: null, accessToken: null, status: 'anonymous' }),
}));
