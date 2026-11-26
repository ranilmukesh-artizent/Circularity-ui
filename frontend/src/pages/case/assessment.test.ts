import { describe, expect, it } from 'vitest';
import type { CaseRec } from '../../api/case';
import { assessable, OUTCOMES, recordedAssessment, recordedLine, saveBlock } from './assessment';

const rec = (extra: Partial<CaseRec>) => ({ id: 'MC-1', ...extra }) as CaseRec;

describe('the assessment form logic (ns-med-01)', () => {
  it('ns-med-01: the outcomes are the values the action accepts', () => {
    expect(OUTCOMES.map((o) => o.value)).toEqual(['servicing', 'remanufacturing', 'full_refurbishment']);
    expect(OUTCOMES[0].label).toBe('Servicing');
  });
  it('ns-med-01: only a medical capital case can be assessed', () => {
    expect(assessable(rec({ template: 'medical_capital' }))).toBe(true);
    expect(assessable(rec({ template: 'medical_rental' }))).toBe(false);
    expect(assessable(rec({}))).toBe(false);
  });
  it('ns-med-01: save is blocked with a reason until both fields are filled', () => {
    expect(saveBlock('', '')).toMatch(/planned work and give the reason/);
    expect(saveBlock('Seal replacement', '  ')).toBe('Give the reason to save.');
    expect(saveBlock(' ', 'No change to intended use')).toBe('Describe the planned work to save.');
    expect(saveBlock('Seal replacement', 'No change to intended use')).toBeNull();
  });
  it('ns-med-01: the recorded assessment shows the outcome, who and when', () => {
    const c = rec({
      evidenceRecords: [{ type: 'servicing_assessment', at: '2026-11-26T14:20:00+00:00', value: { assessment: 'servicing', planned_work: 'Seals', rationale: 'Same use', by: 'engineer' } }],
    });
    const a = recordedAssessment(c)!;
    expect(a.outcome).toBe('servicing');
    expect(recordedLine(a)).toBe('Servicing, recorded by engineer on 26 Nov 14:20');
    expect(recordedAssessment(rec({ evidenceRecords: [] }))).toBeNull();
    expect(recordedAssessment(rec({}))).toBeNull();
  });
});
