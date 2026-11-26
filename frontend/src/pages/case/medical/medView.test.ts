// Plan 9 UI audit gap 7 (medical_rental): the rental-device case panels' wording, over the facts the case screen already carries.
import { describe, expect, it } from 'vitest';
import type { CaseRec, GateRow } from '../../../api/case';
import {
  QUESTIONS_HREF, certRows, deconLine, followRows, medicalView, repairHold, serviceLines, turnaroundLines, writeOffLine,
} from './medView';

const med = (over: Record<string, unknown> = {}): CaseRec =>
  ({ id: 'RT-9', template: 'medical_rental', routes: [], recommendation: null, evidence: [], gates: [], ...over }) as unknown as CaseRec;
const gate = (over: Record<string, unknown>): GateRow => ({ id: 'G-MED-DECON', name: 'Decontamination', passed: true, evidence: [], reason: '', ...over }) as unknown as GateRow;

describe('decontamination record (MR-04, MR-05)', () => {
  it('shows the cycle end after check-in, the record and an enhanced cycle', () => {
    const g = gate({ evidence: [{ type: 'decontamination', at: '2026-10-01T09:00:00+00:00', source: 'mr_decon',
      value: { decon_ended_at: '2026-10-01T09:00:00+00:00', checked_in_at: '2026-10-01T06:30:00+00:00', decon_record_ref: 'DR-77', decon_enhanced: true } }] });
    expect(deconLine(g)).toBe('Cycle ended 2026-10-01 09:00 UTC · after check-in 2026-10-01 06:30 UTC · record DR-77 · enhanced cycle');
  });
  it('says the case is held while there is no valid record', () =>
    expect(deconLine(gate({ passed: false, reason: 'Decontamination record required' }))).toBe('Held: Decontamination record required'));
  it('says when the gate is not on the case', () => expect(deconLine(undefined)).toBe('No decontamination gate result on the case'));
});

describe('certification window against the rental (MR-06)', () => {
  const c = med({
    rentalRequests: [{ req_id: 'REQ-1', hospital: 'Mercy', start_date: '2026-12-01', days: 30, ends: '2026-12-31' }],
    serviceRead: { certificationExpiry: '2026-12-15', pmDue: '2027-03-01' },
    serviceCheck: { requests: [{ req_id: 'REQ-1', ends: '2026-12-31', ok: false, reason: 'Certification ends 2026-12-15, before the rental ends 2026-12-31', recommendation: 'Send a different unit: PU-2' }], proposed: null },
  });
  it('gives each request its dates, whether the unit is in date and the other unit to send', () => {
    expect(certRows(c)).toEqual([{
      id: 'REQ-1', rental: 'Mercy · 30 days from 2026-12-01 · ends 2026-12-31', ok: false,
      text: 'Certification ends 2026-12-15, before the rental ends 2026-12-31', advice: 'Send a different unit: PU-2',
    }]);
  });
  it('says in date when the check passes', () => {
    const ok = med({ rentalRequests: [{ req_id: 'R', start_date: '2026-12-01', days: 5 }], serviceCheck: { requests: [{ req_id: 'R', ends: '2026-12-06', ok: true, reason: null, recommendation: null }], proposed: null } });
    expect(certRows(ok)[0]).toMatchObject({ ok: true, text: 'In date for the whole rental', advice: null });
  });
  it('has no rows without requests', () => expect(certRows(med())).toEqual([]));
});

describe('turnaround and service planning (MR-17, MR-18, MR-22)', () => {
  it('shows the close measures', () =>
    expect(turnaroundLines(med({ close: { turnaround_hours: 30.5, rerented_within_48h: true, utilisation: 0.8123 } })))
      .toEqual(['Check-in to dispatch 30.5 h · within 48 hours', 'Utilisation 81.2 % of the cycle']));
  it('says over 48 hours', () => expect(turnaroundLines(med({ close: { turnaround_hours: 60, rerented_within_48h: false } }))[0]).toBe('Check-in to dispatch 60 h · over 48 hours'));
  it('is empty before a close', () => expect(turnaroundLines(med())).toEqual([]));
  it('lists the proposed booking and the orders already booked', () => {
    const c = med({
      serviceCheck: { requests: [], proposed: { action: 'service.book', input: { case_id: 'RT-9', asset_tag: 'PU-1', kind: 'certification', due_by: '2026-12-15' } } },
      serviceOrders: [{ asset_tag: 'PU-1', kind: 'pm', due_by: '2026-11-20', sent: true, order_id: 'SO-5' }, { asset_tag: 'PU-1', kind: 'repair', due_by: '2026-11-22', sent: false }],
    });
    expect(serviceLines(c)).toEqual([
      'Proposed for a person to book: certification for PU-1 by 2026-12-15',
      'Booked: pm for PU-1 by 2026-11-20 · sent to the service system (SO-5)',
      'Booked: repair for PU-1 by 2026-11-22 · recorded on the case',
    ]);
  });
});

describe('repair approval (MR-10)', () => {
  const hold = { id: 'AP-MR-REPAIR', owner: 'fleet_manager', reason: 'The repair estimate of $4,200.00 is over the $2,500 limit: the fleet manager approves (AP-MR-REPAIR)', repairEstimate: 4200, limit: 2500, income: 6000, incomeBasis: '30 days at 50% utilisation at 400 a day', alternative: { route: 'retire', net: 1800 } };
  it('names the estimate, the limit, the income and the alternative', () =>
    expect(repairHold(med({ approvalHolds: [{ id: 'X' }, hold] }))).toEqual({
      reason: hold.reason, lines: ['Repair estimate $4,200 against a $2,500 limit', 'Rental income over the next period $6,000 (30 days at 50% utilisation at 400 a day)', 'Instead, retire: net $1,800'],
    }));
  it('is null with no such hold', () => expect(repairHold(med({ approvalHolds: [{ id: 'AP-OTHER' }] }))).toBeNull());
});

describe('follow-through and write-off (MR-19, MR-23)', () => {
  it('lists the steps of the plan with their state, else those of the chosen route', () => {
    const exec = med({ exec: { steps: [{ k: 'dispatch', label: 'Dispatch', sys: 'Rental', state: 'done' }, { k: 'service_order', label: 'Service order', sys: 'Svc', state: 'active' }] } });
    expect(followRows(exec).map((r) => [r.label, r.state])).toEqual([['Dispatch', 'done'], ['Service order', 'active']]);
    const planned = med({ chosen: { id: 'retire', steps: ['data_sanitisation', 'disposal_collection'] } });
    expect(followRows(planned).map((r) => [r.label, r.state])).toEqual([['Data sanitisation', 'planned'], ['Disposal collection', 'planned']]);
  });
  it('holds the write-off of a retired device for a person', () =>
    expect(writeOffLine(med({ chosen: { id: 'retire' }, valuer: { book_value: 1234.5 }, close: { certificate_ref: 'DC-1' } })))
      .toBe('Write-off of $1,235 is prepared for Finance and held until a person accepts it · disposal certificate DC-1'));
  it('says when it is posted', () =>
    expect(writeOffLine(med({ chosen: { id: 'retire' }, valuer: { book_value: 900 }, close: { posted: { write_off: { amount: 900, at: '2026-11-02T10:00:00+00:00' } } } })))
      .toBe('Write-off of $900 posted 2026-11-02 10:00 UTC'));
  it('is null for a route that is not retire', () => expect(writeOffLine(med({ chosen: { id: 'rerent:REQ-1' }, valuer: { book_value: 900 } }))).toBeNull());
});

describe('the view', () => {
  it('is null for another pack and links the worked questions', () => {
    expect(medicalView(med({ template: 'device' }))).toBeNull();
    expect(medicalView(med())).not.toBeNull();
    expect(QUESTIONS_HREF).toBe('#/analytics/packs');
  });
});
