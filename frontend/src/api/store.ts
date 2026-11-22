/**
 * Change notification for React: one version number that goes up whenever backend data may have changed (an action,
 * a sync, a sign-in, a stream event, a finished fetch). useBackend() (useBackend.ts) subscribes to it.
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

/**
 * Session change hooks: client.ts calls sessionChanged() on every sign-in and sign-out, and sessionScoped() (view.ts)
 * registers here so state kept between pages (filters, open drafts, what-if assumptions) does not pass to the next user.
 */
const sessionHooks = new Set<() => void>();
export function onSessionChange(f: () => void) {
  sessionHooks.add(f);
}
export function sessionChanged() {
  sessionHooks.forEach((f) => f());
}
