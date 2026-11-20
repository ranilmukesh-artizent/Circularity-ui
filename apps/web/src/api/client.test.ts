// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiInvoke, cached, cachedAction, http, invalidate, login, logout, onStream, retryFailed, withQuery } from './client';
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

describe('API client cache', () => {
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

  it('reads the error envelope, and the older shapes, from a failed request', async () => {
    const reply = (status: number, body: string, type = 'application/json') => async () => new Response(body, { status, headers: { 'Content-Type': type } });
    const cases: [() => Promise<Response>, { status: number; code: string; message: string }][] = [
      // di-api's envelope: a refusal, a validation error (422) and an unhandled failure (500)
      [reply(403, JSON.stringify({ ok: false, error: { code: 'tenant_boundary', message: 'RT-1048 belongs to Customer A.' } })), { status: 403, code: 'tenant_boundary', message: 'RT-1048 belongs to Customer A.' }],
      [reply(422, JSON.stringify({ ok: false, error: { code: 'validation_error', message: 'username: Field required' } })), { status: 422, code: 'validation_error', message: 'username: Field required' }],
      [reply(500, JSON.stringify({ ok: false, error: { code: 'internal_error', message: 'Something went wrong on the server.' } })), { status: 500, code: 'internal_error', message: 'Something went wrong on the server.' }],
      // FastAPI's own 422 (a list of field errors): the first one; a plain-text 500 from a proxy: the status
      [reply(422, JSON.stringify({ detail: [{ loc: ['body', 'username'], msg: 'Field required', type: 'missing' }] })), { status: 422, code: 'validation_error', message: 'username: Field required' }],
      [reply(500, 'Internal Server Error', 'text/plain'), { status: 500, code: 'error', message: '500 ' }],
      // the older {detail: {code, message}} shape still reads
      [reply(401, JSON.stringify({ detail: { code: 'unauthenticated', message: 'Sign in first.' } })), { status: 401, code: 'unauthenticated', message: 'Sign in first.' }],
    ];
    for (const [answer, want] of cases) {
      vi.stubGlobal('fetch', vi.fn(answer));
      const e = await http('/api/fail').catch((x: unknown) => x);
      expect(e).toBeInstanceOf(ApiError);
      expect(e).toMatchObject({ status: want.status, code: want.code });
      if (want.message.endsWith(' ')) expect((e as ApiError).message.startsWith(want.message)).toBe(true);
      else expect((e as ApiError).message).toBe(want.message);
    }
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

/** A fake EventSource: records each opened URL and lets the test fire events and errors. */
class FakeEventSource {
  static opened: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  closed = false;
  private listeners = new Map<string, (ev: MessageEvent) => void>();
  constructor(readonly url: string) {
    FakeEventSource.opened.push(this);
  }
  addEventListener(kind: string, l: (ev: MessageEvent) => void) {
    this.listeners.set(kind, l);
  }
  close() {
    this.closed = true;
  }
  emit(kind: string, data: unknown, id: string) {
    this.listeners.get(kind)?.({ data: JSON.stringify(data), lastEventId: id } as MessageEvent);
  }
}

describe('live stream (F3: a stream ticket, never the access token, in the URL)', () => {
  beforeEach(() => {
    FakeEventSource.opened = [];
    vi.stubGlobal('EventSource', FakeEventSource);
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  });
  afterEach(() => {
    logout();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('fetches a ticket with the bearer token, opens ?ticket=, and reconnects with a fresh ticket after an error', async () => {
    let n = 0;
    const calls = fakeFetch({
      'GET /api/screens/reference': () => ({ body: {} }),
      'POST /api/auth/login': () => ({ body: { account: { id: 'admin' }, access_token: 'ACCESS-TOKEN' } }),
      'POST /api/auth/stream-ticket': () => ({ body: { ticket: 'T' + ++n, expires_in: 60 } }),
    });
    await login('admin', 'x');
    await vi.waitFor(() => expect(FakeEventSource.opened).toHaveLength(1));
    const first = FakeEventSource.opened[0];
    expect(first.url).toBe('/api/stream?ticket=T1');
    expect(first.url).not.toContain('ACCESS-TOKEN');
    expect(first.url).not.toContain('access_token');
    const ticketCall = vi.mocked(fetch).mock.calls.find(([p]) => p === '/api/auth/stream-ticket');
    expect((ticketCall?.[1]?.headers as Record<string, string>).Authorization).toBe('Bearer ACCESS-TOKEN');

    // an event marks the cached reads stale (once, after a short wait for its companions)
    const seen: unknown[] = [];
    const off = onStream((kind, data) => seen.push([kind, data]));
    first.onopen?.();
    const v = getVersion();
    first.emit('journal', { id: 41 }, '41');
    expect(seen).toEqual([['journal', { id: 41 }]]);
    await vi.advanceTimersByTimeAsync(200);
    expect(getVersion()).toBeGreaterThan(v);
    off();

    // the connection drops: closed, then reopened after a delay with a new ticket, resuming after event 41
    first.onerror?.();
    expect(first.closed).toBe(true);
    expect(FakeEventSource.opened).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1000);
    await vi.waitFor(() => expect(FakeEventSource.opened).toHaveLength(2));
    expect(FakeEventSource.opened[1].url).toBe('/api/stream?ticket=T2&last_event_id=41');
    expect(calls.filter((c) => c === 'POST /api/auth/stream-ticket')).toHaveLength(2);

    // signing out ends it: no reconnect
    logout();
    FakeEventSource.opened[1].onerror?.();
    await vi.advanceTimersByTimeAsync(60000);
    expect(FakeEventSource.opened).toHaveLength(2);
    expect(FakeEventSource.opened[1].closed).toBe(true);
  });
});
