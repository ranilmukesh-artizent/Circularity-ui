import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * The route to a case id that the case list read at sign-in does not hold (a case opened since by a scan, an agent or another
 * person): the list is read again once, not taken as "no such case". The client is faked: `cached` answers the list, `invalidate`
 * records what is made stale.
 */
const scope: Record<string, [string, string]> = { 'RT-1048': ['Customer A', 'Warehouse 1'] };
const invalidate = vi.fn();
vi.mock('./client', () => ({
  cached: () => scope,
  classLabelOf: (c: string) => c,
  invalidate: (...a: unknown[]) => invalidate(...a),
  ref: () => ({}),
  session: () => null,
  withQuery: (p: string) => p,
}));

import { reloadScopeFor, shouldReloadScope } from './product';

beforeEach(() => invalidate.mockClear());

describe('shouldReloadScope', () => {
  it('reloads for an unknown case id', () => expect(shouldReloadScope('RT-1148', false)).toBe(true));
  it('does not for a case the list holds', () => expect(shouldReloadScope('RT-1048', true)).toBe(false));
  it('does not for something that is not a case id', () => {
    expect(shouldReloadScope('expected', false)).toBe(false);
    expect(shouldReloadScope(undefined, false)).toBe(false);
  });
  it('waits a few seconds before reading the list again for the same id', () => {
    expect(shouldReloadScope('RT-1148', false, 1000, 2000)).toBe(false);
    expect(shouldReloadScope('RT-1148', false, 1000, 6000)).toBe(true);
  });
});

describe('reloadScopeFor', () => {
  it('makes only the case list stale, once, for an unknown case id', () => {
    expect(reloadScopeFor('RT-1200')).toBe(true);
    expect(reloadScopeFor('RT-1200')).toBe(false);
    expect(invalidate).toHaveBeenCalledTimes(1);
    const match = invalidate.mock.calls[0][0] as (k: readonly unknown[]) => boolean;
    expect(match(['GET', '/api/screens/nav/scope'])).toBe(true);
    expect(match(['GET', '/api/screens/product/returned'])).toBe(false);
  });
  it('does nothing for a case the list holds', () => {
    expect(reloadScopeFor('RT-1048')).toBe(false);
    expect(invalidate).not.toHaveBeenCalled();
  });
});
