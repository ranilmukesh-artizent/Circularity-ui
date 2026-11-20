/**
 * Every change goes through one call, invoke(actionId, input): the action registry, which checks permission,
 * tenant and warehouse scope, state guards and idempotency, journals the change and notifies listeners.
 * With VITE_BACKEND=api it is POST /api/actions/{id} on di-api; with the engine, the demo's own registry.
 * invoke() is asynchronous in both modes, so pages work the same either way.
 */
import { engine } from '../engine/engine';
import { API } from './backend';
import { apiInvoke, cached, cachedAction, type ActionOptions } from './client';
import type { ActionResult } from './types';

function engineInvoke<T>(id: string, input: Record<string, unknown>): ActionResult<T> {
  return engine()<(id: string, i: Record<string, unknown>) => ActionResult<T>>('invoke')(id, input);
}

export function invoke<T = Record<string, unknown>>(id: string, input: Record<string, unknown> = {}, opts: ActionOptions = {}): Promise<ActionResult<T>> {
  if (API) return apiInvoke<T>(id, input, opts);
  return Promise.resolve(engineInvoke<T>(id, input));
}

/**
 * Read actions return their answer directly; throws on a refusal so callers can show the message.
 * Synchronous: with the API the answer is cached per input (the first call suspends the page until it arrives).
 */
export function read<T>(id: string, input: Record<string, unknown> = {}): T {
  if (API) return cachedAction<T>(id, input);
  const r = engineInvoke<T>(id, input);
  if (!r.ok) throw new Error(r.error.message);
  return r.output;
}

export interface ActionMeta {
  id: string;
  title: string;
  desc: string;
  risk: 'read' | 'draft' | 'act' | 'commit' | 'system';
  perm: string | null;
}

export const actionCatalog = (): ActionMeta[] =>
  (API ? cached<ActionMeta[]>('/api/actions') : Object.values(engine()<Record<string, ActionMeta>>('ACTIONS'))).map(
    ({ id, title, desc, risk, perm }) => ({ id, title, desc, risk, perm }),
  );
