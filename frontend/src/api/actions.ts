/**
 * Every change goes through one call, invoke(actionId, input): POST /api/actions/{id} on di-api, whose action
 * registry checks permission, tenant and warehouse scope, state guards and idempotency, journals the change and
 * notifies the live stream.
 */
import { apiInvoke, cached, cachedAction, type ActionOptions } from './client';
import type { ActionResult } from './types';

export function invoke<T = Record<string, unknown>>(id: string, input: Record<string, unknown> = {}, opts: ActionOptions = {}): Promise<ActionResult<T>> {
  return apiInvoke<T>(id, input, opts);
}

/**
 * Read actions return their answer directly; throws on a refusal so callers can show the message.
 * Synchronous: the answer is cached per input (the first call suspends the page until it arrives).
 */
export function read<T>(id: string, input: Record<string, unknown> = {}): T {
  return cachedAction<T>(id, input);
}

export interface ActionMeta {
  id: string;
  title: string;
  desc: string;
  risk: 'read' | 'draft' | 'act' | 'commit' | 'system';
  perm: string | null;
}

export const actionCatalog = (): ActionMeta[] =>
  cached<ActionMeta[]>('/api/actions').map(({ id, title, desc, risk, perm }) => ({ id, title, desc, risk, perm }));
