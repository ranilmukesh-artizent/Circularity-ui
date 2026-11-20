// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiInvoke, cached, cachedAction, http, invalidate, retryFailed, withQuery } from './client';
import { getVersion } from './store';

/** A fake di-api: answers by path, counting calls. */
function fakeFetch(answers: Record<string, () => { status?: number; body: unknown }>) {
  const calls: string[] = [];
  const fn = vi.fn(async (path: string, init?: RequestInit) => {
    const key = (init?.method ?? 'GET') + ' ' + path;
    calls.push(key);
    const a = answers[key];
    if (!a) return new Response(JSON.stringify({ detail: 'nope' }), { status: 404 });
    const { status = 200, body } = a();
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fn);
  return calls;
}

/** Read through the cache the way a component does: catch the thrown promise and wait for it. */
async function suspendRead<T>(f: () => T): Promise<T> {
  for (let i = 0; i < 5; i++) {
    try {
      return f();
    } catch (p) {
      if (p instanceof Promise) await p;
      else throw p;
    }
  }
  throw new Error('never resolved');
}

describe('API client cache (VITE_BACKEND=api)', () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => vi.unstubAllGlobals());

  it('suspends on the first read, then answers synchronously from the cache', async () => {
    let n = 0;
    const calls = fakeFetch({ 'GET /api/x': () => ({ body: { n: ++n } }) });
    expect(() => cached('/api/x')).toThrow(); // a pending promise: React Suspense waits for it
    expect(await suspendRead(() => cached<{ n: number }>('/api/x'))).toEqual({ n: 1 });
    expect(cached<{ n: number }>('/api/x')).toEqual({ n: 1 });
    expect(calls).toEqual(['GET /api/x']);
  });

  it('keeps the old answer on screen while a stale one refetches', async () => {
    let n = 10;
    fakeFetch({ 'GET /api/y': () => ({ body: { n: ++n } }) });
    await suspendRead(() => cached('/api/y'));
    const v = getVersion();
    invalidate();
    expect(getVersion()).toBeGreaterThan(v);
    expect(cached<{ n: number }>('/api/y')).toEqual({ n: 11 }); // stale answer, refetch started
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(cached<{ n: number }>('/api/y')).toEqual({ n: 12 });
  });

  it('throws the server refusal for a failed read', async () => {
    fakeFetch({ 'GET /api/z': () => ({ status: 403, body: { detail: { code: 'tenant_boundary', message: 'RT-1048 belongs to Customer A.' } } }) });
    await expect(suspendRead(() => cached('/api/z'))).rejects.toThrow('RT-1048 belongs to Customer A.');
  });

  it('caches read actions per input and refuses with the action error', async () => {
    fakeFetch({
      'POST /api/actions/case.get': () => ({ body: { ok: true, output: { id: 'RT-1048' }, key: null, action: 'case.get' } }),
      'POST /api/actions/case.evidence': () => ({ status: 403, body: { ok: false, error: { code: 'tenant_boundary', message: 'No.' } } }),
    });
    expect(await suspendRead(() => cachedAction('case.get', { case_id: 'RT-1048' }))).toEqual({ id: 'RT-1048' });
    await expect(suspendRead(() => cachedAction('case.evidence', { case_id: 'RT-1048' }))).rejects.toThrow('No.');
  });

  it('marks reads stale after a successful action, not after a refusal', async () => {
    fakeFetch({
      'POST /api/actions/decision.submit': () => ({ body: { ok: true, output: {}, key: 'k', action: 'decision.submit' } }),
      'POST /api/actions/decision.approve': () => ({ status: 403, body: { ok: false, error: { code: 'out_of_scope', message: 'No.' } } }),
    });
    let v = getVersion();
    expect((await apiInvoke('decision.submit', { case_id: 'RT-1048' })).ok).toBe(true);
    expect(getVersion()).toBeGreaterThan(v);
    v = getVersion();
    const r = await apiInvoke('decision.approve', { case_id: 'RT-1048' });
    expect(r.ok).toBe(false);
    expect(getVersion()).toBe(v);
  });

  it('retries a failed read after retryFailed()', async () => {
    let fail = true;
    const calls = fakeFetch({
      'GET /api/retry': () => (fail ? { status: 500, body: { detail: { code: 'error', message: 'Boom.' } } } : { body: { ok: 1 } }),
    });
    await expect(suspendRead(() => cached('/api/retry'))).rejects.toThrow('Boom.');
    expect(() => cached('/api/retry')).toThrow('Boom.'); // the failed entry keeps its error
    fail = false;
    const v = getVersion();
    retryFailed();
    expect(getVersion()).toBeGreaterThan(v);
    expect(await suspendRead(() => cached('/api/retry'))).toEqual({ ok: 1 });
    expect(calls).toEqual(['GET /api/retry', 'GET /api/retry']);
  });

  it('turns an unreachable server into a network error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    const r = await apiInvoke('decision.submit', { case_id: 'RT-1048' });
    expect(r).toEqual({ ok: false, error: { code: 'network', message: 'Could not reach the server. Check your connection and try again.' } });
    await expect(http('/api/anything')).rejects.toMatchObject({ code: 'network', message: 'Could not reach the server. Check your connection and try again.' });
    await expect(http('/api/anything')).rejects.toBeInstanceOf(ApiError);
  });

  it('builds query strings without empty values', () => {
    expect(withQuery('/api/screens/nav', { cc_mode: 'senior', last_asset: null, tenant_filter: '' })).toBe('/api/screens/nav?cc_mode=senior');
    expect(withQuery('/a?x=1', { y: 2 })).toBe('/a?x=1&y=2');
  });
});
