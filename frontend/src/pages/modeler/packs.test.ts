import { describe, expect, it } from 'vitest';
import { impactLine, partsLine, refusalLine } from './packs';

describe('pack version lines (X-01, X-03)', () => {
  it('x-01: the parts line counts the parts that check out', () => {
    expect(partsLine({ parts: { ok: 13, total: 13 } })).toBe('13 of 13 parts');
    expect(partsLine({ parts: { ok: 4, total: 13 } })).toBe('4 of 13 parts');
  });

  it('x-03: the impact line says how many decisions change and what it is worth', () => {
    expect(impactLine({ changed: 3, total: 41, dv: 1240 })).toBe('Would change 3 of 41 decisions (+$1,240)');
    expect(impactLine({ changed: 2, total: 8, dv: -320 })).toBe('Would change 2 of 8 decisions (-$320)');
    expect(impactLine({ changed: 1, total: 8, dv: 0 })).toBe('Would change 1 of 8 decisions ($0)');
    expect(impactLine({ changed: 0, total: 8, dv: 0 })).toBe('Would change none of 8 decisions');
    expect(impactLine({ changed: 0, total: 0, dv: 0 })).toBe('No decisions to compare');
    expect(impactLine(null)).toBe('Impact not calculated');
  });

  it('x-01: a refusal leads with the part that failed', () => {
    expect(refusalLine('Pack device v2.8.0: part 5 (routes): Field required')).toBe('Part 5 (routes): Field required');
    expect(refusalLine('Pack device 2.7.0 is not newer than 2.7.0.')).toBe('Pack device 2.7.0 is not newer than 2.7.0.');
  });
});
