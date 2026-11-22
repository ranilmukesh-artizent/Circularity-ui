// @vitest-environment jsdom
// The read cache on TanStack Query (refactor step E6, docs/agents/plans/e6-tanstack-design.md): retry, eviction,
// dedup, scoped invalidation and sign-out. The facade's own behaviour (suspend, stale-while-revalidate, refusals,
// retryFailed) is covered by client.test.ts.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, cached, invalidate, logout, peek, queryClient, sweep } from './client';

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

/** Read the way a component does: catch the thrown promise and wait for it. */
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

describe('read cache (TanStack Query)', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    queryClient.clear();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('retries a 503 and then answers', async () => {
    let n = 0;
    const calls = fakeFetch({ 'GET /api/r1': () => (++n < 2 ? { status: 503, body: { detail: 'busy' } } : { body: { ok: n } }) });
    expect(await suspendRead(() => cached<{ ok: number }>('/api/r1'))).toEqual({ ok: 2 });
    expect(calls).toEqual(['GET /api/r1', 'GET /api/r1']);
  });

  it('does not retry a refusal', async () => {
    const calls = fakeFetch({ 'GET /api/r2': () => ({ status: 403, body: { error: { code: 'tenant_boundary', message: 'Not yours.' } } }) });
    const err = await suspendRead(() => cached('/api/r2')).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe('tenant_boundary');
    expect(calls).toEqual(['GET /api/r2']);
  });

  it('makes one request for reads of the same key during one fetch', async () => {
    const calls = fakeFetch({ 'GET /api/d': () => ({ body: 1 }) });
    const a = suspendRead(() => cached('/api/d'));
    const b = suspendRead(() => cached('/api/d'));
    expect(await a).toBe(1);
    expect(await b).toBe(1);
    expect(calls).toEqual(['GET /api/d']);
  });

  it('evicts an answer nobody read for 15 minutes, keeps one read since', async () => {
    fakeFetch({ 'GET /api/old': () => ({ body: 'o' }), 'GET /api/new': () => ({ body: 'n' }) });
    await suspendRead(() => cached('/api/old'));
    await suspendRead(() => cached('/api/new'));
    const t = Date.now();
    vi.useFakeTimers({ now: t + 16 * 60_000, toFake: ['Date'] });
    cached('/api/new'); // on screen: read again by the re-render
    sweep(Date.now());
    expect(peek('/api/old')).toBeUndefined();
    expect(peek('/api/new')).toBe('n');
  });

  it('invalidates only what a scoped invalidate selects', async () => {
    let a = 0, b = 0;
    const calls = fakeFetch({ 'GET /api/sa': () => ({ body: ++a }), 'GET /api/sb': () => ({ body: ++b }) });
    await suspendRead(() => cached('/api/sa'));
    await suspendRead(() => cached('/api/sb'));
    invalidate((k) => k[1] === '/api/sa');
    cached('/api/sa');
    cached('/api/sb');
    await new Promise((r) => setTimeout(r, 0));
    expect(calls.filter((c) => c === 'GET /api/sa')).toHaveLength(2);
    expect(calls.filter((c) => c === 'GET /api/sb')).toHaveLength(1);
  });

  it('drops a late answer from the previous session', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    vi.stubGlobal('fetch', vi.fn(async () => {
      await gate;
      return new Response(JSON.stringify('old'), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    expect(() => cached('/api/late')).toThrow();
    logout();
    release();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(peek('/api/late')).toBeUndefined();
  });
});
