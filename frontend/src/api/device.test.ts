import { describe, expect, it, vi } from 'vitest';
import type { CaseRec } from './case';
const m = vi.hoisted(() => ({ invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { status: 'decided' }, key: null, action: 'x' })) }));
vi.mock('./actions', () => ({ invoke: m.invoke }));
import { approveLot, buildLots, decidePayout, deviceView, proposeLot, rejectLot, type DeviceView } from './device';

const base = { id: 'RT-1', owner: 'Customer A', location: 'Warehouse 1', assetId: 'IMEI:359990000000428', stage: 'none' } as unknown as CaseRec;
const view: DeviceView = {
  imei: '359990000000428', sku: 'iPhone 14|128', brand: 'Apple', model: 'iPhone 14', storageGb: 128, declaredGrade: 'B', grade: 'B',
  graded: false, quote: { amount: 410, currency: 'USD' }, partner: 'P01', batch: null, received: '2026-09-20T10:00:00+00:00',
  ref: 330, refSource: 'feed', bulk: false, lines: [],
};

describe('P9-6.4 deviceView (DV-01)', () => {
  it('is the device block of a received device', () => {
    expect(deviceView({ ...base, device: view })).toBe(view);
  });
  it('is null for a case that is not a received device', () => {
    expect(deviceView(base)).toBeNull();
    expect(deviceView({ ...base, device: undefined })).toBeNull();
  });
});

describe('P9-6.8 decidePayout (DV-05)', () => {
  it('invokes payout.decide with the case, the amount and the reason', async () => {
    await decidePayout('RT-1', 300, 'Photos show a cracked back glass');
    expect(m.invoke.mock.calls.at(-1)).toEqual(['payout.decide', { case_id: 'RT-1', payout: 300, reason: 'Photos show a cracked back glass' }]);
  });
});

describe('P9-6.11 lot actions (DV-07)', () => {
  it('invokes the four lot actions with their inputs', async () => {
    await buildLots('Customer A');
    expect(m.invoke.mock.calls.at(-1)).toEqual(['lot.build', { org_unit_id: 'Customer A' }]);
    await proposeLot('L-1');
    expect(m.invoke.mock.calls.at(-1)).toEqual(['lot.propose', { lot_id: 'L-1' }]);
    await approveLot('L-1');
    expect(m.invoke.mock.calls.at(-1)).toEqual(['lot.approve', { lot_id: 'L-1' }]);
    await rejectLot('L-1', 'Buyer pool too thin this week');
    expect(m.invoke.mock.calls.at(-1)).toEqual(['lot.reject', { lot_id: 'L-1', reason: 'Buyer pool too thin this week' }]);
  });
});
