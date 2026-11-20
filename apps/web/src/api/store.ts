/**
 * Change notification for React: one version number that goes up whenever backend data may have changed (an action,
 * a sync, a sign-in, a stream event, a finished fetch). useBackend() (hooks.ts) subscribes to it.
 */
let version = 0;
const listeners = new Set<() => void>();

export function bump() {
  version++;
  listeners.forEach((l) => l());
}
export function subscribe(l: () => void) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}
export const getVersion = () => version;
