import { useSyncExternalStore } from 'react';
import { getVersion, subscribe } from '../engine/engine';

/**
 * Re-render when the backend state changes (any action, sync or sign-in).
 * Usage: `useBackend(); const cases = listCases(...)` at the top of a component.
 * When the real API lands this becomes TanStack Query invalidation; components do not change.
 */
export function useBackend(): number {
  return useSyncExternalStore(subscribe, getVersion, getVersion);
}
