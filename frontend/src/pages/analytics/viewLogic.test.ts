// P9-9.19 (UC-20): the helpers of the Saved views panel.
import { describe, expect, it } from 'vitest';
import type { SavedView } from '../../api/analytics';
import { alertText, audienceText, measureLabel, parseThreshold, toggleRole, viewsOfPack } from './viewLogic';

const v = (o: Partial<SavedView>): SavedView => ({
  id: 1, org_unit_id: 'Customer A', owner: 'planner-a', pack: 'used_cars', question_id: 'wq_uc_1', question: 'Q', name: 'N', params: {},
  shared_with_roles: [], alert: null, alert_active: false, mine: true, measures: ['days_in_stock'], ...o,
});

describe('P9-9.19 saved views', () => {
  it('words the alert on days_in_stock', () => {
    expect(measureLabel('days_in_stock')).toBe('days in stock');
    expect(alertText({ measure: 'days_in_stock', op: '>', threshold: 45 })).toBe('Alert when days in stock is above 45');
    expect(alertText(null)).toBe('No alert');
  });
  it('parses a threshold only when it is a finite number', () => {
    expect(parseThreshold(' 45 ')).toBe(45);
    expect(parseThreshold('0')).toBe(0);
    expect(parseThreshold('')).toBeNull();
    expect(parseThreshold('abc')).toBeNull();
    expect(parseThreshold('1e999')).toBeNull();
  });
  it('lists the pack views, the own ones first', () => {
    const list = viewsOfPack([v({ id: 1, name: 'B', mine: false, owner: 'x' }), v({ id: 2, name: 'Z' }), v({ id: 3, pack: 'device' }), v({ id: 4, name: 'A' })], 'used_cars');
    expect(list.map((x) => x.id)).toEqual([4, 2, 1]);
  });
  it('says who a view is for', () => {
    expect(audienceText(v({}))).toBe('Yours, not shared');
    expect(audienceText(v({ shared_with_roles: ['Approver'] }))).toBe('Yours, shared with Approver');
    expect(audienceText(v({ mine: false, owner: 'planner-a' }))).toBe('Shared by planner-a');
  });
  it('toggles a role and keeps the role order', () => {
    const all = ['Admin', 'Planner', 'Approver'];
    expect(toggleRole(['Admin'], 'Approver', true, all)).toEqual(['Admin', 'Approver']);
    expect(toggleRole(['Admin', 'Approver'], 'Admin', false, all)).toEqual(['Approver']);
  });
});
