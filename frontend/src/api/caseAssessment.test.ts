import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { case_id: 'MC-1', result: 'servicing' }, key: null, action: 'assessment.record' })),
}));
vi.mock('./actions', () => ({ invoke: m.invoke }));

import { recordAssessment } from './case';

const last = () => m.invoke.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];

beforeEach(() => m.invoke.mockClear());

describe('the regulatory assessment facade (plan 9, P9-12.9, NS-MED-01)', () => {
  it('ns-med-01: recordAssessment invokes assessment.record with the case, the planned work, the result and the rationale', async () => {
    await recordAssessment('MC-1', 'Battery and seal replacement', 'servicing', 'No change to intended use.');
    expect(last()).toEqual([
      'assessment.record',
      { case_id: 'MC-1', planned_work: 'Battery and seal replacement', result: 'servicing', rationale: 'No change to intended use.' },
    ]);
  });
});
