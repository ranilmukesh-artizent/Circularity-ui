import { describe, expect, it } from 'vitest';
import type { DeviceView, PayoutView } from '../../api/device';
import type { QuoteCheck, RegistryView, WipeView } from '../../api/device';
import { deviceLine, gradeLine, lotLines, mismatchLine, payoutLine, payoutState, quoteCheckLine, refLine, registryLine, registryState, wipeLine, wipeState } from './device';

const cert = { id: 'WC-1', method: 'Purge', toolVersion: '4.2', verification: 'pass', operator: 'OP-17', at: '2026-10-06T08:00:00Z' };

describe('P9-6.7 wipeLine and wipeState (DV-04)', () => {
  it('names the method, tool, verification, operator and day', () => {
    expect(wipeLine(cert)).toBe('Purge · tool 4.2 · verified · operator OP-17 · 6 Oct 2026');
    expect(wipeLine({ ...cert, verification: 'fail' })).toBe('Purge · tool 4.2 · verification failed · operator OP-17 · 6 Oct 2026');
  });
  it('says what a missing or failed certificate waits for, with the batch count', () => {
    const w: WipeView = { state: 'none', certificate: null, missing: ['method'], batch: { ref: 'BATCH-0007', total: 40, waiting: 12 } };
    expect(wipeState(w)).toBe('Waiting for the wipe certificate (batch BATCH-0007: 12 of 40 waiting)');
    expect(wipeState({ ...w, batch: null })).toBe('Waiting for the wipe certificate');
    expect(wipeState({ ...w, state: 'failed', certificate: { ...cert, verification: 'fail' } })).toBe('Wipe verification failed: re-run the wipe or destroy the storage');
    expect(wipeState({ ...w, state: 'ok', certificate: cert })).toBe('Purge · tool 4.2 · verified · operator OP-17 · 6 Oct 2026');
  });
});

const hit: RegistryView = {
  state: 'hit', status: 'reported stolen', checkedAt: '2026-10-06', source: 'Device registry (synthetic)', ageDays: 2,
  recheckDays: 7, owner: 'Compliance', item: 'open', allowedRoutes: [],
};

describe('P9-6.6 registryLine (DV-03)', () => {
  it('names the status, the check day and the source', () => {
    expect(registryLine(hit)).toBe('Registry: reported stolen · checked 6 Oct 2026 · Device registry (synthetic)');
    expect(registryLine({ ...hit, status: 'clear' })).toBe('Registry: clear · checked 6 Oct 2026 · Device registry (synthetic)');
    expect(registryLine({ ...hit, status: 'clear', checkedAt: null })).toBe('Registry: no check on file');
  });
  it('says who a hit waits for and where the device may still go', () => {
    expect(registryState(hit)).toBe('Waiting for Compliance');
    expect(registryState({ ...hit, item: 'done' })).toBe('Released by Compliance');
    expect(registryState({ ...hit, allowedRoutes: ['parts', 'recycle'] })).toBe('Waiting for Compliance · may still go to parts, recycle');
    expect(registryState({ ...hit, state: 'stale' })).toBe('Check older than 7 days: the case waits for a new one');
    expect(registryState({ ...hit, state: 'none' })).toBe('No registry check yet: the case waits for one');
    expect(registryState({ ...hit, state: 'clear' })).toBe('Clear');
  });
});

describe('P9-6.5 mismatchLine (DV-02)', () => {
  it('names the quoted and the read value', () => {
    expect(mismatchLine({ field: 'storage', quoted: 256, read: 128 })).toBe('Storage quoted 256 GB, read 128 GB');
    expect(mismatchLine({ field: 'model', quoted: 'iPhone 14', read: 'iPhone 13' })).toBe('Model quoted iPhone 14, read iPhone 13');
    expect(mismatchLine({ field: 'imei', quoted: '359990000000428', read: '359990000000429' })).toBe(
      'IMEI quoted 359990000000428, read 359990000000429',
    );
  });
  const rows: QuoteCheck['rows'] = [
    { field: 'imei', quoted: '1', read: '1', mismatch: false },
    { field: 'storage', quoted: 256, read: 128, mismatch: true },
  ];
  it('says the state, the owner and where the exception stands', () => {
    expect(quoteCheckLine({ state: 'waiting', rows: [], owner: 'Customer care', item: null })).toBe("Waiting for the lab's diagnostics");
    expect(quoteCheckLine({ state: 'match', rows, owner: 'Customer care', item: null })).toBe('Quote matches the device read');
    const item = { id: 7, state: 'open' as const, outcome: null, by: null };
    expect(quoteCheckLine({ state: 'mismatch', rows, owner: 'Customer care', item })).toBe(
      'Storage quoted 256 GB, read 128 GB. Customer care, open',
    );
    expect(quoteCheckLine({ state: 'mismatch', rows, owner: 'Customer care', item: { ...item, state: 'done', outcome: 'Re-quote accepted' } })).toBe(
      'Storage quoted 256 GB, read 128 GB. Customer care, resolved: Re-quote accepted',
    );
  });
});

const one: DeviceView = {
  imei: '359990000000428', sku: 'iPhone 14|128', brand: 'Apple', model: 'iPhone 14', storageGb: 128, declaredGrade: 'B', grade: 'B',
  graded: false, quote: { amount: 410, currency: 'USD' }, partner: 'P01', batch: 'BATCH-0011', received: '2026-09-20T10:00:00+00:00',
  ref: 330, refSource: 'feed', bulk: false, lines: [],
};
const lot: DeviceView = {
  ...one, imei: null, bulk: true, batch: 'BATCH-0020', model: 'iPhone 14',
  lines: [
    { imei: '359990000100', model: 'iPhone 14', storageGb: 128, declaredGrade: 'B', grade: 'B', quote: 410 },
    { imei: '359990000101', model: 'iPhone 13', storageGb: 256, declaredGrade: 'C', grade: 'C', quote: 300 },
  ],
};

describe('P9-6.4 deviceLine (DV-01)', () => {
  it('names the model, storage, declared grade, quote and partner', () => {
    expect(deviceLine(one)).toBe('iPhone 14 · 128 GB · declared B · quote $410 · partner P01');
  });
  it('leaves out what a device does not have', () => {
    expect(deviceLine({ ...one, storageGb: null, quote: null })).toBe('iPhone 14 · declared B · partner P01');
  });
  it('counts the devices of a bulk lot', () => {
    expect(deviceLine(lot)).toBe('2 devices · batch BATCH-0020 · grade B · partner P01');
  });
});

describe('P9-6.4 reference, grade and lines', () => {
  it('says where the reference value came from', () => {
    expect(refLine(one)).toBe('Reference $330 a unit, from the market feed');
    expect(refLine({ ...one, refSource: 'quote' })).toBe('Reference $330 a unit, from the quote');
  });
  it('says whether the grade was read or declared', () => {
    expect(gradeLine(one)).toBe('grade B (declared)');
    expect(gradeLine({ ...one, grade: 'C', graded: true })).toBe('grade C (graded)');
  });
  it('lists the lines of a lot', () => {
    expect(lotLines(lot)).toEqual([
      '359990000100 · iPhone 14 · 128 GB · grade B · quote $410', '359990000101 · iPhone 13 · 256 GB · grade C · quote $300',
    ]);
    expect(lotLines(one)).toEqual([]);
  });
});

describe('P9-6.8 payoutLine (DV-05)', () => {
  const adjusted: PayoutView = {
    status: 'adjusted', quote: 410, adjusted: 385.4, gapPct: -0.06, reason: 'Battery health 80–84%', table: 'US payout rules v1',
    auto: true, limit: 0.1, currency: 'USD', photos: [], item: null, decided: null,
  };
  it('says the quote, the adjusted payout, the gap and the rule', () => {
    expect(payoutLine(adjusted)).toBe('$410 → $385.40 (−6%) · Battery health 80–84%');
    expect(payoutLine({ ...adjusted, adjusted: 410, gapPct: 0, reason: 'As quoted' })).toBe('$410 → $410 (0%) · As quoted');
  });
  it('names who decided a payout that waited', () => {
    const waiting: PayoutView = { ...adjusted, status: 'waiting', adjusted: 287, gapPct: -0.3, reason: 'Graded two or more grades below the quote', auto: false };
    expect(payoutState(waiting)).toBe('Waiting for Customer care: the gap is above 10%');
    expect(payoutState({ ...waiting, status: 'decided', adjusted: 300, decided: { by: 'planner.a', reason: 'Cracked glass', at: '2026-10-07T10:00:00Z' } }))
      .toBe('Decided by planner.a: $300 (Cracked glass)');
    expect(payoutState(adjusted)).toBe('Adjusted by the table: US payout rules v1');
  });
});
