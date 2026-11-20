import { useSyncExternalStore } from 'react';
import { getVersion, subscribe } from './store';

/**
 * Re-render when the backend state may have changed (an action, a sync, a sign-in, a stream event, a finished fetch).
 * Usage: `useBackend(); const cases = listCases(...)` at the top of a component.
 */
export function useBackend(): number {
  return useSyncExternalStore(subscribe, getVersion, getVersion);
}
