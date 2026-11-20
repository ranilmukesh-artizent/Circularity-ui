// @vitest-environment jsdom
import { beforeAll, describe, expect, it } from 'vitest';
import { invoke, read } from './actions';
import { accountById, can, canPage, canRoute, currentAccount, homeRoute, resolveSignIn, signIn, signInWith, signOut } from './session';

beforeAll(() => localStorage.clear());

describe('mock backend (engine) through the API facade', () => {
  it('resolves the demo sign-in IDs', () => {
    expect(resolveSignIn('exec')?.id).toBe('executive');
    expect(resolveSignIn('planner.b@northfield.example')?.id).toBe('planner-b');
    expect(resolveSignIn('someone@elsewhere.com')).toBeNull();
  });

  it('starts signed out and refuses actions', async () => {
    signOut();
    expect(currentAccount()).toBeNull();
    const r = await invoke('cases.list', {});
    expect(r.ok).toBe(false);
  });

  it('signs in through the form helper with the demo messages', async () => {
    expect(await signInWith('', 'x')).toEqual({ ok: false, message: 'Enter your work email or user ID.', field: 'id' });
    expect((await signInWith('nobody', 'x')).ok).toBe(false);
    expect(await signInWith('exec', '')).toEqual({ ok: false, message: 'Enter your password.', field: 'pw' });
    const r = await signInWith('planner.b@northfield.example', 'pw');
    expect(r.ok && r.account.id).toBe('planner-b');
  });

  it('applies the tenant lock for a Planner', () => {
    signIn(accountById('planner-b')!);
    const out = read<{ rows: { owner: string }[]; total: number }>('cases.list', { limit: 500 });
    expect(out.rows.length).toBeGreaterThan(0);
    expect(new Set(out.rows.map((c) => c.owner))).toEqual(new Set(['Customer B']));
    expect(canRoute({ page: 'product', a: 'RT-1048', b: null })).toBe('tenant'); // RT-1048 belongs to Customer A
    expect(can('approve.decisions')).toBe(false);
    expect(canPage('integration')).toBe(false);
  });

  it('lets the Approver see every tenant and approve', () => {
    signIn(accountById('approver')!);
    expect(can('approve.decisions')).toBe(true);
    expect(read<{ total: number }>('cases.list', { limit: 500 }).total).toBe(128);
    expect(homeRoute()).toBe('home');
  });

  it('returns the hero case with its recommendation', () => {
    const c = read<{ id: string; recommendation?: { route: string } | null }>('case.get', { case_id: 'RT-1048' });
    expect(c.id).toBe('RT-1048');
  });
});
