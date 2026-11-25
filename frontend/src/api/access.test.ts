import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { id: 11, status: 'draft' }, key: null, action: 'x' })),
  read: vi.fn((): unknown => ({ email: 'planner.b@example.com', found: true })),
  cached: vi.fn((): unknown => ({ identity: { group_map: [{ id: 1, group_id: 'circ-approvers', status: 'approved' }] } })),
}));
vi.mock('./actions', () => ({ invoke: m.invoke, read: m.read }));
vi.mock('./client', () => ({ cached: m.cached, ref: vi.fn(), refreshMe: vi.fn() }));
vi.mock('./session', () => ({ can: vi.fn(() => true), currentAccount: vi.fn() }));

import { approveGroupMap, groupMap, saveGroupMap, syncDirectory, syncLine, testUser } from './access';

const lastInvoke = () => m.invoke.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];
const lastRead = () => m.read.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];

beforeEach(() => {
  m.invoke.mockClear();
  m.read.mockClear();
});

describe('the directory group map facade (plan 9, P9-8.10, X-10)', () => {
  it('x-10: groupMap lists the rows the identity section carries', () => {
    expect(groupMap().map((r) => r.group_id)).toEqual(['circ-approvers']);
  });

  it('x-10: saveGroupMap and approveGroupMap invoke the access actions', async () => {
    await saveGroupMap({ group_id: 'circ-planners-customer-c', role: 'Planner', org_unit_id: 'Customer C', site: 'Warehouse 2' });
    expect(lastInvoke()).toEqual(['access.saveGroupMap', { group_id: 'circ-planners-customer-c', role: 'Planner', org_unit_id: 'Customer C', site: 'Warehouse 2' }]);
    await approveGroupMap(11);
    expect(lastInvoke()).toEqual(['access.approveGroupMap', { id: 11 }]);
  });

  it('x-10: testUser reads access.testUser by email, with groups only when given', () => {
    testUser('planner.b@example.com');
    expect(lastRead()).toEqual(['access.testUser', { email: 'planner.b@example.com' }]);
    testUser('new@example.com', ['circ-approvers']);
    expect(lastRead()).toEqual(['access.testUser', { email: 'new@example.com', groups: ['circ-approvers'] }]);
  });
});

describe('the directory sync facade (plan 9, P9-8.11, X-10)', () => {
  it('x-10: syncDirectory invokes access.syncDirectory with no input', async () => {
    await syncDirectory();
    expect(lastInvoke()).toEqual(['access.syncDirectory', {}]);
  });

  it('x-10: the sync line names the joiners and leavers, singular and plural', () => {
    expect(syncLine({ users: 13, joiners: ['a@example.com', 'b@example.com'], leavers: ['c@example.com'], mappings: 10 })).toBe('2 joiners, 1 leaver');
    expect(syncLine({ users: 13, joiners: [], leavers: [] })).toBe('0 joiners, 0 leavers');
  });

  it('x-10: without a directory source the answer has no lists and no line (parity)', () => {
    expect(syncLine({ users: 13 })).toBe('');
  });
});
