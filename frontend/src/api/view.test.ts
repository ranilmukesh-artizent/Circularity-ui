// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const KEY = 'circ-view-v1';
const DEFAULTS = { tenant: 'All', theme: 'light', ccMode: 'operational', lastAsset: null, rg: { lang: 'en', tz: 'UTC', cur: 'INR' }, acks: {} };

/** view.ts reads local storage once, when it loads; load a fresh copy (and its store) for each case. */
async function load() {
  vi.resetModules();
  const v = await import('./view');
  const store = await import('./store');
  return { ...v, store };
}

beforeEach(() => localStorage.clear());

describe('view settings', () => {
  it('start from the defaults when nothing is stored', async () => {
    const { view } = await load();
    expect(view()).toEqual(DEFAULTS);
  });

  it('read stored settings over the defaults', async () => {
    localStorage.setItem(KEY, JSON.stringify({ tenant: 'Customer B', theme: 'dark' }));
    const { view } = await load();
    expect(view()).toEqual({ ...DEFAULTS, tenant: 'Customer B', theme: 'dark' });
  });

  it('fall back to the defaults when the stored value is not JSON', async () => {
    localStorage.setItem(KEY, '{not json');
    const { view } = await load();
    expect(view()).toEqual(DEFAULTS);
  });

  it('setView changes the settings, stores them and tells React', async () => {
    const { view, setView, store } = await load();
    const before = store.getVersion();
    setView({ ccMode: 'senior', lastAsset: 'RT-1048' });
    expect(view()).toMatchObject({ ccMode: 'senior', lastAsset: 'RT-1048', tenant: 'All' });
    expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual({ ...DEFAULTS, ccMode: 'senior', lastAsset: 'RT-1048' });
    expect(store.getVersion()).toBe(before + 1);
  });

  it('survive a reload', async () => {
    (await load()).setView({ tenant: 'Customer C', acks: { 'FR-1': true } });
    const { view } = await load();
    expect(view()).toMatchObject({ tenant: 'Customer C', acks: { 'FR-1': true } });
  });
});

describe('sessionScoped', () => {
  afterEach(() => vi.unstubAllGlobals());

  /** view.ts and client.ts from one fresh module graph, so they share one store (and one reset registry). */
  async function loadWithClient() {
    const v = await load();
    const client = await import('./client');
    return { ...v, client };
  }

  it('starts from init() and keeps changes while the session lasts', async () => {
    const { sessionScoped } = await load();
    const s = sessionScoped(() => ({ q: '', n: 0 }));
    expect(s.current).toEqual({ q: '', n: 0 });
    s.current = { ...s.current, q: 'RT-1048' };
    s.current.n = 2;
    expect(s.current).toEqual({ q: 'RT-1048', n: 2 });
  });

  it('goes back to a fresh init() value on sign-out', async () => {
    const { sessionScoped, client } = await loadWithClient();
    const init = vi.fn(() => ({ open: {} as Record<string, boolean> }));
    const s = sessionScoped(init);
    const first = s.current;
    s.current.open['RT-1048'] = true;
    client.logout();
    expect(s.current).toEqual({ open: {} });
    expect(s.current).not.toBe(first); // a new object, not the one the last user changed
    expect(init).toHaveBeenCalledTimes(2);
  });

  it('goes back to init() on sign-in too (a session that expired without a sign-out)', async () => {
    const { sessionScoped, client } = await loadWithClient();
    const me = { account: { id: 'admin', label: 'Admin', role: 'Admin', email: 'admin@northfield.example' }, description: '', home: 'home',
      permissions: [], pages: {}, tenants: [], tenant_scoped: false, warehouse: null };
    vi.stubGlobal('fetch', vi.fn(async (path: string) => new Response(JSON.stringify(
      path === '/api/auth/login' ? { ...me, access_token: 't' } : {},
    ), { status: 200, headers: { 'Content-Type': 'application/json' } })));
    const s = sessionScoped(() => 'details');
    s.current = 'canvas';
    await client.login('admin', 'pw');
    expect(s.current).toBe('details');
  });
});

describe('view settings without usable local storage', () => {
  const desc = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  afterEach(() => {
    if (desc) Object.defineProperty(globalThis, 'localStorage', desc);
    vi.restoreAllMocks();
  });

  it('work for this tab when reading local storage throws (blocked site data)', async () => {
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      get() { throw new DOMException('The operation is insecure.', 'SecurityError'); },
    });
    const { view, setView, store } = await load();
    expect(view()).toEqual(DEFAULTS);
    const before = store.getVersion();
    expect(() => setView({ theme: 'dark' })).not.toThrow();
    expect(view().theme).toBe('dark');
    expect(store.getVersion()).toBe(before + 1);
  });

  it('keep the change when saving throws (storage full)', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError'); });
    const { view, setView } = await load();
    expect(() => setView({ tenant: 'Customer A' })).not.toThrow();
    expect(view().tenant).toBe('Customer A');
  });
});
