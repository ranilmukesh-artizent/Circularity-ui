import { describe, expect, it } from 'vitest';
import type { ReplayReport } from '../../api/replay';
import { finished, headline, signed, upliftLine, versionLabel } from './replayReport';

const uplift = { primary: 4.2, band80: [-1, 7.44] as [number, number], band95: [-3, 9] as [number, number], secondary: 3.2, bias: 0.9, conservative: 3.2, basis: 'modelled' as const };

describe('replay report wording (plan 9, P9-7.2, X-06)', () => {
  it('x-06: an uplift line leads with the conservative figure and says modelled', () => {
    expect(upliftLine(uplift)).toBe('+3.2 % (80 % band -1.0 % to +7.4 %), modelled');
    expect(signed(-0.04)).toBe('-0.0 %');
  });
  it('x-06: the headline lists straight-through, approvals and exceptions', () => {
    const r = { straight_through_pct: 70, approvals_per_day: 2, exceptions_per_day: 1 } as ReplayReport;
    expect(headline(r).map((h) => h.value)).toEqual(['70.0 %', '2.0', '1.0']);
  });
  it('x-06: a run is finished when done or failed; versions read draft or vN', () => {
    expect(['queued', 'running', 'done', 'failed'].map((s) => finished(s as 'done'))).toEqual([false, false, true, true]);
    expect([versionLabel('draft'), versionLabel('3')]).toEqual(['draft', 'v3']);
  });
});
