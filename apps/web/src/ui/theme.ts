import { useSyncExternalStore } from 'react';

export type Theme = 'light' | 'dark';
const KEY = 'circ-theme'; // same key as the static demo
const subs = new Set<() => void>();

function read(): Theme {
  try {
    return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

let current: Theme = read();

export function applyTheme(t: Theme = current) {
  current = t;
  document.documentElement.dataset.theme = t;
  try {
    localStorage.setItem(KEY, t);
  } catch {
    /* storage unavailable */
  }
  subs.forEach((s) => s());
}

export const toggleTheme = () => applyTheme(current === 'dark' ? 'light' : 'dark');

export function useTheme(): Theme {
  return useSyncExternalStore((f) => (subs.add(f), () => subs.delete(f)), () => current);
}
