// Plan 9 UI audit gap 7 (used_cars): the used-car case panel's wording, over the facts the case screen already carries.
import { describe, expect, it } from 'vitest';
import type { CaseRec, Route } from '../../../api/case';
import { QUESTIONS_HREF, channelRows, odometerLine, recallLine, titleLine, usedCarView, vehicleGates } from './carView';

const route = (id: string, plan: string, net: number, over: Partial<Route> = {}): Route =>
  ({ id, plan, net, p10: net - 100, p90: net + 100, terms: [], gates: [], ...over });
const car = (over: Record<string, unknown> = {}): CaseRec =>
  ({ id: 'RT-9', template: 'used_cars', routes: [], recommendation: null, evidence: [], ...over }) as unknown as CaseRec;

describe('title and lien line (UC-06)', () => {
  it('says a clear title with no lien', () => expect(titleLine({ status: 'clear', lien_open: false })).toBe('Title clear · no open lien'));
  it('names an open lien and a branded title', () => {
    expect(titleLine({ status: 'salvage', lien_open: true, lien_release_ref: null })).toBe('Title salvage · lien open, no release on file');
    expect(titleLine({ status: 'clear', lien_open: true, lien_release_ref: 'LR-7' })).toBe('Title clear · lien open, release LR-7');
  });
  it('says when no search is on file', () => expect(titleLine(undefined)).toBe('Title and lien search not on file'));
});

describe('odometer line (UC-07)', () => {
  it('shows the photo against the lease record and the gap', () =>
    expect(odometerLine({ photo_reading: 41230, lease_record: 41100 })).toBe('Photo 41,230 mi · lease record 41,100 mi · 130 mi apart'));
  it('says a statement is on file and a reading that is not the actual mileage', () => {
    expect(odometerLine({ statement_ref: 'OS-1', not_actual: true })).toBe('Lessee statement OS-1 · reading is not the actual mileage');
  });
  it('says nothing is read yet', () => expect(odometerLine(undefined)).toBe('No odometer reading on file'));
});

describe('recall line (UC-08)', () => {
  it('names open campaigns and what is remedied', () =>
    expect(recallLine({ checked_at: '2026-10-01T08:00:00+00:00', open: true, campaigns: ['C-1', 'C-2'], remedied: ['C-1'] }))
      .toBe('Open recall: C-2 · checked 2026-10-01 08:00 UTC'));
  it('says no open recall', () => expect(recallLine({ checked_at: '2026-10-01T08:00:00+00:00', open: false })).toBe('No open recall · checked 2026-10-01 08:00 UTC'));
  it('asks for the check when there is none', () => expect(recallLine(undefined)).toBe('Recall check not on file'));
});

describe('channels (UC-10)', () => {
  it('lists each channel with its net, marks the best and gives a blocked one its reason', () => {
    const rows = channelRows(car({
      routes: [route('retail:L1', 'Retail · Lot 1', 2500, { excluded: true, failReason: 'Open recall: no retail until remedied' }), route('auction', 'Auction', 1900)],
      recommendation: route('auction', 'Auction', 1900),
    }));
    expect(rows.map((r) => [r.id, r.name, r.net, r.best, r.note])).toEqual([
      ['auction', 'Auction', 1900, true, ''],
      ['retail:L1', 'Retail · Lot 1', 2500, false, 'Open recall: no retail until remedied'],
    ]);
  });
});

describe('vehicle gates and the view', () => {
  it('keeps only the vehicle gates', () => {
    const gates = [{ id: 'G-VEH-TITLE' }, { id: 'G-OTHER' }, { id: 'G-VEH-ODO' }] as never;
    expect(vehicleGates(gates).map((g) => g.id)).toEqual(['G-VEH-TITLE', 'G-VEH-ODO']);
  });
  it('is null for a case of another pack', () => {
    expect(usedCarView(car({ template: 'device' }))).toBeNull();
    expect(usedCarView(car())?.vin).toBeNull();
  });
  it('links the worked questions to the Packs tab', () => expect(QUESTIONS_HREF).toBe('#/analytics/packs'));
});
