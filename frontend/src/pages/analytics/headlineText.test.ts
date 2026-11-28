import { describe, expect, it } from 'vitest';
import { headlineMeta, headlineParts } from './headlineText';
import { row } from './charts/testRows';

const m = (o: Partial<Parameters<typeof headlineParts>[0]> = {}) => ({ uplift: 2310000, rc: [row(), row()], days: 14, baseDays: 22, ...o });

describe('headline sentence', () => {
  it('says the gain, the count and the pace from the same numbers as the figures', () => {
    const h = headlineParts(m());
    expect(h.amount).toBe('$2.31M');
    expect(h.before + h.amount + h.after).toBe('Circularity recovered $2.31M more than the baseline across 2 reconciled decisions; cases close in a median 14 days, 36% faster than today.');
  });
  it('says less when the gain is negative and slower when the days grew', () => {
    const h = headlineParts(m({ uplift: -5000, days: 30, baseDays: 20 }));
    expect(h.tone).toBe('neg');
    expect(h.after).toContain('less than the baseline');
    expect(h.after).toContain('50% slower than today');
  });
  it('does not invent a pace without a baseline, and says so when nothing reconciled', () => {
    expect(headlineParts(m({ baseDays: 0 })).after).toContain('about as fast as today');
    const e = headlineParts(m({ rc: [] }));
    expect(e.empty).toBe(true);
    expect(e.before).toContain('No reconciled decisions');
  });
  it('gives its count, period and tenants', () => {
    expect(headlineMeta(1277, 1400, 'Jan to Dec', ['Customer A', 'Customer B'])).toBe('1,277 reconciled of 1,400 decisions · Jan to Dec · Customer A, Customer B');
  });
});
