// @vitest-environment jsdom
import { beforeAll, describe, expect, it } from 'vitest';
import { invoke, read } from './actions';
import { accountById, can, canPage, canRoute, currentAccount, homeRoute, resolveSignIn, signIn, signOut } from './session';

beforeAll(() => localStorage.clear());

describe('mock backend (engine) through the API facade', () => {
  it('resolves the demo sign-in IDs', () => {
    expect(resolveSignIn('exec')?.id).toBe('executive');
    expect(resolveSignIn('planner.b@northfield.example')?.id).toBe('planner-b');
    expect(resolveSignIn('someone@elsewhere.com')).toBeNull();
  });

  it('starts signed out and refuses actions', () => {
    signOut();
    expect(currentAccount()).toBeNull();
    const r = invoke('cases.list', {});
    expect(r.ok).toBe(false);
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
