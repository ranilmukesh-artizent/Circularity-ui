// @vitest-environment jsdom
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { can, canPage, canRoute, currentAccount, homeRoute, signInWith, signOut } from './session';

/** A fake di-api with the answers sign-in and the access checks need (shapes as di/routes/auth.py and di/services/screens). */
const REFERENCE = {
  ROLE_POLICY: { Planner: { landing: 'home', perms: [], pages: {}, asTabs: [], desc: 'Plans returns.' } },
  RB_AV: { Planner: 'PL' },
  TENANTS: ['Customer A', 'Customer B', 'Customer C'],
  PERM_ALIAS: { approve: 'approve.decisions' },
  PAGES: { home: {}, product: {}, access: {}, mcp: {} },
  RB_SECS: { product: ['received', 'expected', 'asset', 'case'] },
};
const ME_B = {
  account: { id: 'planner-b', role: 'Planner', label: 'Planner · Customer B', tenant: 'Customer B', email: 'planner.b@northfield.example' },
  description: 'Plans returns.', home: 'home', permissions: ['submit.decisions'],
  pages: { home: [], product: ['received', 'expected', 'asset', 'case'] }, tenants: ['Customer B'], tenant_scoped: true, warehouse: null,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

beforeAll(() => {
  vi.stubGlobal('fetch', async (path: string, init?: RequestInit) => {
    if (path === '/api/screens/reference') return json(REFERENCE);
    if (path === '/api/auth/login') {
      const { username } = JSON.parse(String(init?.body));
      if (username === 'nobody') return json({ detail: { code: 'unknown_account', message: 'nope' } }, 401);
      return json({ ...ME_B, access_token: 't' });
    }
    if (path === '/api/screens/nav/scope') return json({ 'RT-1048': ['Customer A', 'Warehouse 1'], 'RT-1101': ['Customer B', 'Warehouse 2'] });
    return json({ detail: 'not in the fake' }, 404);
  });
  vi.stubGlobal('EventSource', undefined); // no live stream in unit tests
});
afterAll(() => vi.unstubAllGlobals());

/** Read through the cache as a component does: wait for a pending fetch, then read again. */
async function settle<T>(f: () => T): Promise<T> {
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

describe('session against di-api', () => {
  it('refuses an empty or unknown account with the demo messages', async () => {
    expect(await signInWith('', 'x')).toEqual({ ok: false, message: 'Enter your work email or user ID.', field: 'id' });
    expect(await signInWith('nobody', 'x')).toEqual({ ok: false, message: 'We could not find that account. Check the email or user ID.', field: 'id' });
  });

  it('signs in and evaluates access from /api/auth/me', async () => {
    const r = await signInWith('planner.b@northfield.example', 'pw');
    expect(r.ok && r.account.id).toBe('planner-b');
    expect(currentAccount()?.id).toBe('planner-b');
    expect(homeRoute()).toBe('home');
    expect(can('approve')).toBe(false);
    expect(can('submit.decisions')).toBe(true);
    expect(canPage('product', 'case')).toBe(true);
    expect(canPage('access')).toBe(false);
  });

  it('applies the tenant boundary to record links', async () => {
    expect(await settle(() => canRoute({ page: 'product', a: 'RT-1048', b: null }))).toBe('tenant');
    expect(canRoute({ page: 'product', a: 'RT-1101', b: null })).toBe(true);
    expect(canRoute({ page: 'access', a: null, b: null })).toBe(false);
  });

  it('signs out', () => {
    signOut();
    expect(currentAccount()).toBeNull();
    expect(can('submit.decisions')).toBe(false);
  });
});
