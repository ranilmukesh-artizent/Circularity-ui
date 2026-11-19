/**
 * Every change goes through one call, invoke(actionId, input): the demo's action registry, which checks permission,
 * tenant and warehouse scope, state guards and idempotency, journals the change and notifies listeners.
 * The same ids become POST /api/actions/{id} on di-api later.
 */
import { engine } from '../engine/engine';
import type { ActionResult } from './types';

export function invoke<T = Record<string, unknown>>(id: string, input: Record<string, unknown> = {}): ActionResult<T> {
  return engine()<(id: string, i: Record<string, unknown>) => ActionResult<T>>('invoke')(id, input);
}

/** Read actions return their answer directly; throws on a refusal so callers can show the message. */
export function read<T>(id: string, input: Record<string, unknown> = {}): T {
  const r = invoke<T>(id, input);
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
  Object.values(engine()<Record<string, ActionMeta>>('ACTIONS')).map(({ id, title, desc, risk, perm }) => ({ id, title, desc, risk, perm }));
