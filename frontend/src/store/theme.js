import { useEffect, useSyncExternalStore } from 'react';
import { create } from 'zustand';

const KEY = 'analytica-theme';
const readSaved = () => {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' ? v : 'system';
  } catch {
    return 'system';
  }
};

/** Chosen theme: 'light' | 'dark' | 'system' (follow the computer). Saved per browser. */
export const useThemeStore = create((set) => ({
  mode: /** @type {'light' | 'dark' | 'system'} */ (readSaved()),
  setMode: (/** @type {'light' | 'dark' | 'system'} */ mode) => {
    try {
      localStorage.setItem(KEY, mode);
    } catch {
      /* storage blocked: still applies for this session */
    }
    set({ mode });
  },
}));

const mq = () => window.matchMedia('(prefers-color-scheme: dark)');
const subscribe = (/** @type {() => void} */ cb) => {
  const m = mq();
  m.addEventListener('change', cb);
  return () => m.removeEventListener('change', cb);
};

/** The theme actually on screen right now ('light' or 'dark'). */
export function useEffectiveTheme() {
  const mode = useThemeStore((s) => s.mode);
  const systemDark = useSyncExternalStore(subscribe, () => mq().matches, () => false);
  return mode === 'system' ? (systemDark ? 'dark' : 'light') : mode;
}

/** Mount once at the root: writes data-theme on <html>. */
export function ThemeSync() {
  const theme = useEffectiveTheme();
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);
  return null;
}
