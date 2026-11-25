import { describe, expect, it } from 'vitest';
import { estimateLine, estimateStatus, gateLine, keyUsed, lineProblem, lineSummary, money, ticketLine } from './serviceDesk';

describe('P9-4.4 estimateLine (SD-02)', () => {
  const e = { point: 430, p10: 395, p90: 470, confidence: 0.92, n: 186, currency: 'USD' };
  it('says the point, the range, the confidence and the match count', () => {
    expect(estimateLine(e)).toBe('$430 (range $395–$470) · 92% confidence · 186 similar repairs');
  });
  it('keeps cents when there are some and names other currencies', () => {
    expect(money(222.5, 'USD')).toBe('$222.50');
    expect(money(1234, 'EUR')).toBe('€1,234');
    expect(money(5, 'CHF')).toBe('CHF 5');
  });
  it('says whether a technician checks, with the reason', () => {
    expect(estimateStatus({ auto: true, reason: '186 similar repairs' })).toBe('Priced without a technician. 186 similar repairs');
    expect(estimateStatus({ auto: false, reason: '37 similar repairs (under 50)' })).toBe('Draft: a technician checks. 37 similar repairs (under 50)');
    expect(keyUsed('class_fault')).toBe('same class and fault, any age');
  });
});

const line = { model_class: 'CRH', family: 'Cordless rotary hammer, 22 V', age_months: 18, fault_code: 'MOT', cover_type: 'fleet' };

describe('P9-4.3 lineSummary (SD-01)', () => {
  it('names the class, family, age, fault and cover', () => {
    expect(lineSummary(line)).toBe('CRH · Cordless rotary hammer, 22 V · 18 months · MOT · fleet cover');
  });
  it('says unclear for an empty fault and no cover for none', () => {
    expect(lineSummary({ ...line, fault_code: '', cover_type: 'none' })).toBe('CRH · Cordless rotary hammer, 22 V · 18 months · unclear · no cover');
    expect(lineSummary({ ...line, fault_code: null, cover_type: null })).toContain('unclear · no cover');
  });
});

describe('P9-4.3 gateLine, lineProblem and ticketLine (SD-01)', () => {
  const ok = { name: 'Contract right', passed: true, reason: 'Active contract line FL-1' };
  const bad = { name: 'Safety recall', passed: false, reason: 'Safety recall RC-1 (repair): quarantined until Quality releases it' };
  it('says each result with its reason', () => {
    expect(gateLine(ok)).toBe('Contract right: passed. Active contract line FL-1');
    expect(gateLine(bad)).toBe('Safety recall: failed. Safety recall RC-1 (repair): quarantined until Quality releases it');
  });
  it('names the reasons that need a person, or null', () => {
    expect(lineProblem({ gates: [ok as never] })).toBeNull();
    expect(lineProblem({ gates: [ok as never, bad as never] })).toBe(bad.reason);
  });
  it('counts the tools of a ticket', () => {
    expect(ticketLine({ ticket: 'CS0010050', batch: true, batchId: 'BATCH-0050', lines: new Array(22) })).toBe('Ticket CS0010050 · batch BATCH-0050 · 22 tools');
    expect(ticketLine({ ticket: 'CS0010042', batch: false, batchId: null, lines: [1] })).toBe('Ticket CS0010042 · 1 tool');
  });
});