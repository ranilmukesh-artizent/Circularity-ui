import { describe, expect, it, vi } from 'vitest';
const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { case_id: 'RT-1', evidence_type: 'recall_check', checked_at: '2026-10-07T09:00:00+00:00' }, key: null, action: 'x' })),
}));
vi.mock('./actions', () => ({ invoke: m.invoke }));
import { refreshEvidence } from './case';
import { staleType } from '../pages/case/CaseBlocks';

describe('P9-9.9 refreshEvidence (UC-08)', () => {
  it('invokes evidence.refresh with the case and the evidence type', async () => {
    const r = await refreshEvidence('RT-1', 'recall_check');
    expect(m.invoke.mock.calls.at(-1)).toEqual(['evidence.refresh', { case_id: 'RT-1', evidence_type: 'recall_check' }]);
    expect(r).toMatchObject({ ok: true });
  });

  it('offers a re-check only for a failed gate whose missing evidence can be re-run at its source', () => {
    expect(staleType({ passed: false, missingTypes: ['recall_check'] })).toBe('recall_check');
    expect(staleType({ passed: false, missingTypes: ['odometer_statement'] })).toBeNull();
    expect(staleType({ passed: false })).toBeNull();
    expect(staleType({ passed: true, missingTypes: ['recall_check'] })).toBeNull();
  });
});
