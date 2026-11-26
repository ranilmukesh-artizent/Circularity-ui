import { describe, expect, it } from 'vitest';
import {
  approvalLines, batteryLines, benchLine, closeLine, exportLine, inventoryLine, isTelecom, recyclerLine, sparesLines, wipeLine, type TelecomCase,
} from './telecom';

const gate = (id: string, passed: boolean, value: Record<string, unknown> | null, extra: Record<string, unknown> = {}) => ({
  id, name: id, type: 'Compliance', stage: 'x', stageLabel: 'x', passed, kind: 'block', routes: [], routeNames: [], hold: false, step: null,
  owner: 'Test bench lead', evidence: value ? [{ type: 'e', label: 'e', source: 'tn_inv', at: '2026-11-01T00:00:00Z', value }] : [], missing: [], reason: '',
  locked: false, ...extra,
});
const bid = { id: 'BID-9', unit_price: 4200, qty: 3, country: 'DE', domestic: false, screening: 'clear', ref: 'SCR-77' };
const base = (o: Partial<TelecomCase> = {}): TelecomCase => ({ template: 'telecom_network', routes: [], gates: [], ...o }) as TelecomCase;

describe('isTelecom', () => {
  it('is true only for the telecom_network template', () => {
    expect(isTelecom(base())).toBe(true);
    expect(isTelecom({ template: 'tool_fleet' } as TelecomCase)).toBe(false);
  });
});

describe('exportLine (G-NET-EXP, TN-07)', () => {
  it('names a confirmed class with its source and the bid screening', () => {
    const c = base({ gates: [gate('G-NET-EXP', false, { export_class: '5A002', class_source: 'tn_inv', inferred: '5A992', bid }, { kind: 'require_approval' })] as never });
    expect(exportLine(c)).toBe('Export class 5A002 (tn_inv) · end-user screening clear (ref SCR-77)');
  });
  it('says an inferred class is not confirmed and a missing screening is not on file', () => {
    const c = base({ gates: [gate('G-NET-EXP', false, { export_class: null, inferred: '5A992', bid: { ...bid, screening: null, ref: null } })] as never });
    expect(exportLine(c)).toBe('Export class not confirmed (inferred 5A992 from the part number) · end-user screening not on file');
  });
  it('says nothing is on file without the evidence', () => {
    expect(exportLine(base())).toBe('Export class not on file');
  });
});

describe('approvalLines (AP-TN-EXP, TN-08)', () => {
  const c = base({
    gates: [gate('G-NET-EXP', false, { export_class: '5A002', class_source: 'tn_inv', bid }, { kind: 'require_approval', owner: 'Trade compliance' })] as never,
    routes: [{ id: 'spare', net: 1800, excluded: false }, { id: 'resell', net: 9000, excluded: true }] as never,
  });
  it('shows the bid and the keep-as-spares alternative with its value', () => {
    expect(approvalLines(c)).toEqual({
      bid: 'Bid BID-9: 3 units at $4,200 each, buyer country DE, end-user screening clear (ref SCR-77).',
      alternative: 'Alternative: keep as spares, worth $1,800.',
    });
  });
  it('drops the value when the spare route is not valued', () => {
    expect(approvalLines({ ...c, routes: [] })?.alternative).toBe('Alternative: keep as spares.');
  });
  it('is null when the gate needs no approval', () => {
    expect(approvalLines(base())).toBeNull();
    expect(approvalLines({ ...c, gates: [gate('G-NET-EXP', true, { export_class: null }, { kind: 'require_approval' })] as never })).toBeNull();
  });
});

describe('wipeLine and benchLine (G-NET-CFG, TN-06)', () => {
  it('shows a verified wipe with its certificate and scope', () => {
    const c = base({ bench: { summary: '18 of 18 passed', firmware: '9.2', wipe: { status: 'verified', attempts: 1, scope: ['configuration', 'keys'], certificate: 'WC-5', verifiedAt: '2026-11-02T09:00:00Z' } } as never });
    expect(wipeLine(c)).toBe('Wipe verified · certificate WC-5 · configuration, keys · 02 Nov 2026');
    expect(benchLine(c)).toBe('Test bench: 18 of 18 passed · firmware 9.2');
  });
  it('shows a failed wipe with its attempts and none on file', () => {
    expect(wipeLine(base({ bench: { wipe: { status: 'failed', attempts: 2, scope: [] } } as never }))).toBe('Wipe failed after 2 attempts: re-run it or destroy the unit');
    expect(wipeLine(base())).toBe('No wipe certificate on file');
    expect(benchLine(base())).toBeNull();
  });
});

describe('inventoryLine (G-NET-INV, TN-05)', () => {
  it('says the serial matches the inventory, or why not', () => {
    const ok = base({ gates: [gate('G-NET-INV', true, { model: 'RRU-5', site: 'S-1', status: 'active' })] as never });
    expect(inventoryLine(ok)).toBe('Matches the network inventory: RRU-5 at S-1');
    const bad = base({ gates: [gate('G-NET-INV', false, { model: 'RRU-5', site: 'S-2' }, { reason: 'Site differs: inventory S-2, removal S-1' })] as never });
    expect(inventoryLine(bad)).toBe('Does not match the network inventory: Site differs: inventory S-2, removal S-1');
    expect(inventoryLine(base())).toBe('Network inventory not checked yet');
  });
});

describe('sparesLines (TN-18)', () => {
  it('suggests moving an idle unit to the region short of spares before a new purchase', () => {
    const c = base({ valuer: { asset: { region: 'EMEA', idle_days: 90 }, spares: { gap: 3, region_below_target: 'APAC' }, market: { new_price: 5000 } } as never });
    expect(sparesLines(c)).toEqual([
      'New price $5,000: a unit that fills a gap avoids that spend.',
      'APAC is 3 units below its spares target: transfer this unit from EMEA before buying new.',
    ]);
  });
  it('has no transfer line in the region that is short itself, or with no gap', () => {
    const same = base({ valuer: { asset: { region: 'APAC' }, spares: { gap: 3, region_below_target: 'APAC' } } as never });
    expect(sparesLines(same)).toEqual(['APAC is 3 units below its spares target: keep this unit as a spare.']);
    expect(sparesLines(base())).toEqual([]);
  });
});

describe('batteryLines and recyclerLine (TN-23, TN-20)', () => {
  it('shows a damaged lithium unit on the dangerous-goods lane only', () => {
    const c = base({ battery: { chemistry: 'lithium', damaged: true } as never, gates: [gate('G-BAT-4', false, null, { reason: 'Damaged lithium battery: no resale' })] as never });
    expect(batteryLines(c)).toEqual(['Lithium battery, damaged: dangerous-goods lane only', 'Damaged lithium battery: no resale']);
    expect(batteryLines(base())).toEqual([]);
  });
  it('names the recycler, the WEEE category, the weight and the certificate', () => {
    expect(recyclerLine(base({ downstream: { vendor_id: 'REC-2', weee_category: 'IT-4', weight_kg: 12.5, certificate: { ref: 'CERT-8' } } as never })))
      .toBe('Recycler REC-2 · WEEE IT-4 · 12.5 kg · certificate CERT-8');
    expect(recyclerLine(base())).toBeNull();
  });
});

describe('closeLine (TN-21, TN-22)', () => {
  it('shows the new spend avoided and the days to redeploy', () => {
    expect(closeLine(base({ close: { telecom: { reused: true, new_spend_avoided: 5000, days_to_redeploy: 12, route: 'redeploy' } } as never }))).toBe('Reused (redeploy): new spend avoided $5,000 · 12 days to redeploy');
    expect(closeLine(base({ close: { telecom: { reused: false, new_spend_avoided: 0, days_to_redeploy: null, route: 'recycle' } } as never }))).toBe('Not reused (recycle): no new spend avoided');
    expect(closeLine(base())).toBeNull();
  });
});
