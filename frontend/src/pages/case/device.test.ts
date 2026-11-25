import { describe, expect, it } from 'vitest';
import type { DeviceView } from '../../api/device';
import type { QuoteCheck } from '../../api/device';
import { deviceLine, gradeLine, lotLines, mismatchLine, quoteCheckLine, refLine } from './device';

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
