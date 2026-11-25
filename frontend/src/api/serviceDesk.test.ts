import { describe, expect, it } from 'vitest';
import type { CaseRec } from './case';
import { serviceDeskView, type ServiceDeskView } from './serviceDesk';

const base = { id: 'RT-1048', owner: 'Customer A', location: 'Warehouse 1', assetId: 'MTR-2041', stage: 'none' } as unknown as CaseRec;
const view: ServiceDeskView = {
  ticket: 'CS0010042', account: 'ACC-US-0042', market: 'US', site: 'Austin', batch: false, batchId: null, loanerPromised: false, requesterRole: 'Site manager',
  lines: [{
    n: 1, serial: 'CRH-46042', model_class: 'CRH', family: 'Cordless rotary hammer, 22 V', age_months: 18, fault_code: 'MOT', fault_text: 'Runs hot',
    cover_type: 'fleet', cover_until: '2027-06-30', life_used_pct: 50, gates: [],
  }],
};

describe('P9-4.3 serviceDeskView (SD-01)', () => {
  it('is the serviceDesk block of a case opened from a ticket', () => {
    expect(serviceDeskView({ ...base, serviceDesk: view })).toBe(view);
  });
  it('is null for an industrial case', () => {
    expect(serviceDeskView(base)).toBeNull();
    expect(serviceDeskView({ ...base, serviceDesk: undefined })).toBeNull();
  });
});