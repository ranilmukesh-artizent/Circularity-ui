import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { case_id: 'RT-1', status: 'released' }, key: null, action: 'x' })),
}));
vi.mock('./actions', () => ({ invoke: m.invoke }));

import type { CaseRec } from './case';
import { fraudLine, fraudOf, isFraudItem, rejectFraud, releaseFraud, simulateFraud, type FraudRecord } from './fraud';
import type { WorkItem } from './mywork';

const last = () => m.invoke.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];
const record: FraudRecord = { status: 'held', score: 0.8, threshold: 0.6, signals: [], rule_version: 'v1', held_at: '2026-11-25T10:00:00+00:00', by: 'stage-intake' };
const item = (o: Partial<WorkItem>): WorkItem => ({
  id: 'w:1', kind: 'exception', case_id: 'RT-1', title: 'x', cause: null, action: null, owner: 'Approver', due: null, overdue: false, priority: 100, go: null, ...o,
}); // prettier-ignore

beforeEach(() => m.invoke.mockClear());

describe('the fraud facade (plan 9, P9-2.11, X-15)', () => {
  it('x-15: releaseFraud and rejectFraud invoke their actions with the case and the reason', async () => {
    await releaseFraud('RT-1', 'The serial is genuine.');
    expect(last()).toEqual(['fraud.release', { case_id: 'RT-1', reason: 'The serial is genuine.' }]);
    await rejectFraud('RT-1', 'The serial is blacklisted.');
    expect(last()).toEqual(['fraud.reject', { case_id: 'RT-1', reason: 'The serial is blacklisted.' }]);
  });

  it('x-15: simulateFraud sends the threshold and rules only when given', async () => {
    await simulateFraud('device', 'Customer A');
    expect(last()).toEqual(['fraud.simulate', { pack: 'device', org_unit_id: 'Customer A' }]);
    await simulateFraud('device', 'Customer A', { threshold: 0.9 });
    expect(last()).toEqual(['fraud.simulate', { pack: 'device', org_unit_id: 'Customer A', threshold: 0.9 }]);
  });

  it('x-15: the hold line names the score, the threshold and the rule set', () => {
    expect(fraudLine(record)).toBe('Held for fraud review: score 0.8 ≥ 0.6 · rule set v1');
    expect(fraudLine({ ...record, threshold: null })).toBe('Held for fraud review: score 0.8 · rule set v1');
  });

  it('x-15: the case record is read off the case, null when it was never held', () => {
    expect(fraudOf({ id: 'RT-1', fraud: record } as unknown as CaseRec)).toEqual(record);
    expect(fraudOf({ id: 'RT-1' } as unknown as CaseRec)).toBeNull();
  });

  it('x-15: My work tells the fraud holds from other exceptions', () => {
    expect(isFraudItem(item({ title: 'Fraud and compliance: held for fraud review' }))).toBe(true);
    expect(isFraudItem(item({ title: 'Missing evidence' }))).toBe(false);
    expect(isFraudItem(item({ kind: 'task', title: 'Fraud and compliance: held for fraud review' }))).toBe(false);
  });
});
