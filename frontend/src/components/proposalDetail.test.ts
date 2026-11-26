import { describe, expect, it } from 'vitest';
import { bulkGroups, confidenceText, describeInput, labelOf, valueText } from './proposalDetail';

describe('proposal detail (UI fix 39, E13)', () => {
  it('reads field names as words', () => {
    expect(labelOf('work_order_ref')).toBe('Work order reference');
    expect(labelOf('caseId')).toBe('Case ID');
    expect(labelOf('qty')).toBe('Quantity');
  });
  it('shows values in plain words, never raw JSON', () => {
    expect(valueText(true)).toBe('Yes');
    expect(valueText(['a', 'b'])).toBe('a, b');
    expect(valueText([{ x: 1 }, { x: 2 }])).toBe('2 items');
    expect(valueText({ unit_price: 4, currency: 'USD' })).toBe('unit price 4, currency USD');
    expect(valueText(null)).toBe('');
    expect(valueText({})).toBe('');
  });
  it('lists the input without repeating the why or the case', () => {
    const d = describeInput({ input: { case_id: 'RT-1', reason: 'Stale', lot_size: 4, route: ['A', 'B'], empty: '' }, why: 'Stale', case_id: 'RT-1' });
    expect(d.lines).toEqual([{ label: 'Lot size', value: '4' }, { label: 'Route', value: 'A, B' }]);
    expect(d.more).toBe(0);
    expect(describeInput({ input: { a: 1, b: 2, c: 3 }, why: '', case_id: null }, 2)).toMatchObject({ more: 1 });
  });
  it('shows confidence only when the server sent it', () => {
    expect(confidenceText({})).toBe('');
    expect(confidenceText({ confidence: 0.62, threshold: 0.75 })).toBe('Confidence 62% (threshold 75%)');
    expect(confidenceText({ confidence: 0.9 })).toBe('Confidence 90%');
  });
  it('groups the same action held for the same reasons, never the own or the reasonless', () => {
    const r = (reason: string) => [{ reason: reason as 'risk', detail: '' }];
    const list = [
      { id: 1, action: 'a.x', title: 'X', reasons: r('confidence') },
      { id: 2, action: 'a.x', title: 'X', reasons: r('confidence') },
      { id: 3, action: 'a.x', title: 'X', reasons: r('confidence'), own: true },
      { id: 4, action: 'a.x', title: 'X', reasons: r('value') },
      { id: 5, action: 'a.y', title: 'Y', reasons: [] },
      { id: 6, action: 'a.y', title: 'Y', reasons: [] },
    ];
    const g = bulkGroups(list);
    expect(g).toHaveLength(1);
    expect(g[0].ids).toEqual([1, 2]);
    expect(g[0].label).toBe('X, held for confidence below the threshold');
  });
});
