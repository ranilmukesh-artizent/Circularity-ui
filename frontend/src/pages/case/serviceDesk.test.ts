import { describe, expect, it } from 'vitest';
import type { TicketOption } from '../../api/serviceDesk';
import { approvalLine, estimateLine, estimateStatus, expectedLine, flipLine, gateLine, keyUsed, lineProblem, lineSummary, money, optionOrder, optionSummary, peakLine, ticketLine } from './serviceDesk';

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

const opt = (k: TicketOption['k'], over: Partial<TicketOption> = {}): TicketOption => ({
  k, name: k, eligible: true, why: 'because', customer_price: 580.5, margin: 126.5, expected_margin: 126.5, days: 5, take_up: null,
  credit: null, cost: 430, lines: [], ...over,
});

describe('P9-4.6 options (SD-04)', () => {
  it('puts the recommended option first and keeps the rest in order', () => {
    const all = [opt('fix'), opt('swap'), opt('upgrade')];
    expect(optionOrder(all, 'upgrade').map((o) => o.k)).toEqual(['upgrade', 'fix', 'swap']);
    expect(optionOrder(all, null).map((o) => o.k)).toEqual(['fix', 'swap', 'upgrade']);
  });
  it('says the price, margin and days, or why an option is not offered', () => {
    expect(optionSummary(opt('fix'), 'USD')).toBe('Customer pays $580.50 · margin $126.50 · 5 days out of use');
    expect(optionSummary(opt('swap', { customer_price: 0, margin: 90, days: 1 }), 'USD')).toBe('Customer pays nothing · margin $90 · 1 day out of use');
    expect(optionSummary(opt('swap', { eligible: false, why: 'No refurbished Combihammer in stock' }), 'USD')).toBe('Not offered: No refurbished Combihammer in stock');
    expect(optionSummary(opt('fix', { days: null }), 'USD')).toContain('days out of use not known');
  });
  it('names the expected take-up of an upgrade', () => {
    expect(expectedLine(opt('upgrade', { take_up: 0.62, expected_margin: 97.1 }), 'USD')).toBe('62% expected take-up · expected margin $97.10');
    expect(expectedLine(opt('fix'), 'USD')).toBe('expected margin $126.50');
  });
  it('names the approval owner with the holds', () => {
    expect(approvalLine({ owner: 'Standing policy P1 v2', holds: [] })).toBe('Approval: Standing policy P1 v2');
    expect(approvalLine({ owner: 'Fleet manager', holds: [{ id: 'GR-14', reason: 'The repair costs over $600', owner: 'Fleet manager' }] })).toBe(
      'Approval: Fleet manager (GR-14). The repair costs over $600',
    );
  });
});
describe('P9-4.10 flipLine (SD-09)', () => {
  it('says which option wins above which credit', () => {
    expect(flipLine({ from: 'upgrade', crossing: { from: 'upgrade', to: 'fix', credit_pct: 0.28 } })).toBe('Fix and return beats Upgrade with credit above 28% credit');
  });
  it('says the best stays best when nothing flips, and when nothing can be offered', () => {
    expect(flipLine({ from: 'upgrade', crossing: null })).toBe('Upgrade stays best at every credit up to 40%');
    expect(flipLine({ from: null, crossing: null })).toBe('No option can be offered yet');
  });
  it('names where the expected margin peaks', () => {
    expect(peakLine({ peak: { credit_pct: 0.2, upgrade: 97.1 }, currency: 'USD' })).toBe('Expected margin of the upgrade peaks at 20% credit: $97.10');
  });
});