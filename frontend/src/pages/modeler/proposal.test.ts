import { describe, expect, it } from 'vitest';
import type { Proposal } from '../../api/modeler';
import { openingLine, proposalChecks } from './proposal';

const base: Proposal = {
  kind: 'rule', text: 'Never recycle construction lasers', graph: null, node_id: 'r-BR-03', rid: 'BR-03',
  label: 'BR-03: construction lasers: never recycle', guard: null, checks: [], sim: null, msg: '', note: '', read_by: 'rules',
}; // prettier-ignore

describe('the assistant proposal (the prototype propHtml)', () => {
  it('lists the four checks with no conflict', () => {
    const p = { ...base, checks: [{ level: 'ok' as const, msg: 'BR-03 active: construction lasers: never recycle.', node_id: 'r-BR-03' }] };
    expect(proposalChecks(p, 6).map((c) => c.text)).toEqual([
      'Fits the process: placed between the guardrail gate and the decision',
      'Passes all 6 locked guardrails',
      'No conflict with existing rules',
      'Prediction models and agents unchanged',
    ]);
  });

  it('lists each conflict as a warning instead', () => {
    const msg = 'Conflict: BR-01 and BR-03 pull Recycle in opposite directions for overlapping returns.';
    const p = { ...base, checks: [{ level: 'warn' as const, msg, node_id: 'r-BR-03' }] };
    const out = proposalChecks(p, 6);
    expect(out[2]).toEqual({ level: 'warn', text: msg });
    expect(out).toHaveLength(4);
  });

  it('opens with the template line', () => {
    expect(openingLine('tool_fleet')).toMatch(/^I watch this flow/);
    expect(openingLine('device')).toMatch(/^This is the device recommerce template/);
  });
});
