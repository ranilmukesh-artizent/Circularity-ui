import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  apiInvoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { id: 7, status: 'draft' }, key: null, action: 'x' })),
  cachedAction: vi.fn(),
}));
vi.mock('./client', () => ({ apiInvoke: m.apiInvoke, cachedAction: m.cachedAction, cached: vi.fn(), http: vi.fn(), peek: vi.fn() }));

import { actionScope } from './invalidation';
import { approveMarketTable, rejectMarketTable, saveMarketTable, submitMarketTable, testMarketTable, useMarketTables } from './marketTables';

const last = () => (m.apiInvoke.mock.calls.at(-1) as unknown as [string, Record<string, unknown>]).slice(0, 2); // [action id, input]

beforeEach(() => {
  m.apiInvoke.mockClear();
  m.cachedAction.mockReset();
});

describe('the market tables facade (plan 9, P9-4.2, SD-03)', () => {
  it('sd-03: each write invokes its action with its input', async () => {
    const draft = { pack: 'tool_fleet', flow: 'service_desk', market: 'FR', name: 'labour', kind: 'rate_card' as const, valid_from: '2026-11-01', body: { values: { per_hour: 48 } } };
    await saveMarketTable(draft);
    expect(last()).toEqual(['marketTable.save', draft]);
    await saveMarketTable({ ...draft, id: 7 });
    expect(last()[1]).toMatchObject({ id: 7 });
    await submitMarketTable(7);
    expect(last()).toEqual(['marketTable.submit', { id: 7 }]);
    await approveMarketTable(7);
    expect(last()).toEqual(['marketTable.approve', { id: 7 }]);
    await rejectMarketTable(7, 'The agreed rate is 47.');
    expect(last()).toEqual(['marketTable.reject', { id: 7, reason: 'The agreed rate is 47.' }]);
    await testMarketTable(7, { market: 'US' });
    expect(last()).toEqual(['marketTable.test', { id: 7, inputs: { market: 'US' } }]);
  });

  it('sd-03: useMarketTables reads marketTable.list through cachedAction, as case.get is read', () => {
    m.cachedAction.mockReturnValue({ tables: [] });
    expect(useMarketTables('tool_fleet', 'service_desk')).toEqual({ tables: [] });
    expect(m.cachedAction).toHaveBeenCalledWith('marketTable.list', { pack: 'tool_fleet', flow: 'service_desk' });
  });

  it('sd-03: a write refreshes the Modeler', () => {
    expect(actionScope('marketTable.approve')).toEqual(['modeler']);
  });
});
