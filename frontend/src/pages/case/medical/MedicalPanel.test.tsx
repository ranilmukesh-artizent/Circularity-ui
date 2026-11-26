// @vitest-environment jsdom
// Plan 9 UI audit gap 7: the rental-device panel shows decontamination, the certification window, the repair hold, the steps and the questions link; other packs get nothing.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { CaseRec } from '../../../api/case';
import { MedicalPanel } from './MedicalPanel';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));

const MED = {
  id: 'RT-9', template: 'medical_rental', assetId: 'north:PU-1', cls: 'infusion_pump', routes: [], recommendation: null,
  chosen: { id: 'retire', steps: ['data_sanitisation', 'disposal_collection'] }, valuer: { book_value: 900 },
  gates: [{ id: 'G-MED-DECON', name: 'Decontamination', passed: false, kind: 'block', routes: [], routeNames: ['Re-rent'], reason: 'Decontamination record required', evidence: [] }],
  rentalRequests: [{ req_id: 'REQ-1', hospital: 'Mercy', start_date: '2026-12-01', days: 30, ends: '2026-12-31' }],
  serviceCheck: { requests: [{ req_id: 'REQ-1', ends: '2026-12-31', ok: false, reason: 'Certification ends 2026-12-15, before the rental ends 2026-12-31', recommendation: null }], proposed: null },
  approvalHolds: [{ id: 'AP-MR-REPAIR', reason: 'The repair estimate of $4,200.00 is over the $2,500 limit', repairEstimate: 4200, limit: 2500 }],
} as unknown as CaseRec;

describe('MedicalPanel', () => {
  it('shows the checks, the repair hold, the steps, the write-off and the questions link', () => {
    act(() => root.render(<MedicalPanel c={MED} />));
    const t = host.textContent ?? '';
    expect(t).toContain('Held: Decontamination record required');
    expect(t).toContain('Certification ends 2026-12-15, before the rental ends 2026-12-31');
    expect(t).toContain('Repair estimate $4,200 against a $2,500 limit');
    expect(t).toContain('Data sanitisation · planned');
    expect(t).toContain('held until a person accepts it');
    expect(host.querySelector('a[href="#/analytics/packs"]')).not.toBeNull();
  });
  it('renders nothing for another pack', () => {
    act(() => root.render(<MedicalPanel c={{ ...MED, template: 'device' } as CaseRec} />));
    expect(host.textContent).toBe('');
  });
});
