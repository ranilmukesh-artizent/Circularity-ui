import { describe, expect, it } from 'vitest';
import type { CaseRec } from './case';
import { deviceView, type DeviceView } from './device';

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
