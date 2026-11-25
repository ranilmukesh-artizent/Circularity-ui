import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { id: 'SP-1', status: 'active' }, key: null, action: 'x' })),
  read: vi.fn(),
}));
vi.mock('./actions', () => ({ invoke: m.invoke, read: m.read }));

import { actionScope } from './invalidation';
import {
  approveStandingPolicy, listStandingPolicies, retireStandingPolicy, saveStandingPolicy, submitStandingPolicy,
} from './standingPolicy'; // prettier-ignore

const last = () => m.invoke.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];

beforeEach(() => {
  m.invoke.mockClear();
  m.read.mockReset();
});

describe('the standing policy facade (plan 9, P9-2.5, X-05)', () => {
  it('x-05: approveStandingPolicy invokes standingPolicy.approve with the id', async () => {
    await approveStandingPolicy('SP-1');
    expect(last()).toEqual(['standingPolicy.approve', { id: 'SP-1' }]);
  });

  it('x-05: each write invokes its action with its body', async () => {
    const rules = { max_value: 500, min_confidence: 0.75 };
    await saveStandingPolicy({ pack: 'industrial', org: 'Customer A', name: 'Below $500', rules, owner: 'admin' });
    expect(last()).toEqual(['standingPolicy.save', { pack: 'industrial', org_unit_id: 'Customer A', name: 'Below $500', rules, owner: 'admin' }]);
    await saveStandingPolicy({ pack: 'industrial', org: 'Customer A', name: 'Below $500', rules, owner: 'admin', id: 'SP-1' });
    expect(last()[1]).toMatchObject({ id: 'SP-1' });
    await submitStandingPolicy('SP-1');
    expect(last()).toEqual(['standingPolicy.submit', { id: 'SP-1' }]);
    await retireStandingPolicy('SP-1', 'The board withdrew it.');
    expect(last()).toEqual(['standingPolicy.retire', { id: 'SP-1', reason: 'The board withdrew it.' }]);
  });

  it('x-05: the list is a read action for a pack and an org, and a write refreshes every read', () => {
    m.read.mockReturnValue({ policies: [] });
    listStandingPolicies('industrial', 'Customer A');
    expect(m.read).toHaveBeenCalledWith('standingPolicy.list', { pack: 'industrial', org_unit_id: 'Customer A' });
    expect(actionScope('standingPolicy.approve')).toBe('all');
  });
});
