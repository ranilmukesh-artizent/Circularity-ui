import { describe, expect, it } from 'vitest';
import type { Proposal } from '../../api/modeler';
import type { ModelerScreen } from '../../api/types';
import { looksLikeChange, looksLikeQuestion, openingLine, previewOf, proposalChecks, undoAvailable, undoNote } from './proposal';

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

// ---- plan 10 T2: the preview card model, Undo and the question hint
const node = (id: string, over: Record<string, unknown> = {}) => ({ id, t: 'rule', x: 0, y: 0, label: id, sub: '', h: 60, lock: false, ...over });
const screen = (over: Record<string, unknown> = {}) => ({
  flow: { id: 4, name: 'Industrial returns', org_unit_id: 'workspace', status: 'draft', ver: 1, dver: 2, graph: { nodes: [node('r-IR-01', { rid: 'IR-01', action: 'prefer', path: 'resale' })], edges: [] }, published: { nodes: [], edges: [] }, returned: null },
  template: { key: 'industrial', paths: [{ id: 'resale', name: 'Resale' }, { id: 'recycle', name: 'Recycle' }], guardrails: [1, 2, 3, 4, 5], dims: [{ key: 'grade', label: 'Grade', kind: 'set', values: ['A', 'D'] }] },
  can: { edit: true, approve: false, fork: false }, ...over,
}) as unknown as ModelerScreen; // prettier-ignore
const ruleP: Proposal = {
  ...base, rid: 'IR-02', node_id: 'r-IR-02', label: 'IR-02: grade D: never resale', text: 'Never send grade D motors to resale',
  graph: { nodes: [node('r-IR-01', { rid: 'IR-01', action: 'prefer', path: 'resale' }), node('r-IR-02', { rid: 'IR-02', action: 'exclude', path: 'resale', scope: { grade: ['D'] } })], edges: [] } as never,
  sim: { kind: 'equip', n: 41, flips: [{ case_id: 'a', from: 'x', to: 'y', dv: -400 }, { case_id: 'b', from: 'x', to: 'y', dv: -840 }, { case_id: 'c', from: 'x', to: 'y', dv: 0 }], dv: -1240, extra: {} },
}; // prettier-ignore

describe('previewOf: the preview card of plan 10 section 2.3', () => {
  it('a rule: title, + diff line, the checks, the impact from the simulation, limits and the basis', () => {
    const m = previewOf(ruleP, screen());
    expect(m.blocked).toBe(false);
    expect(m.title).toBe('Proposed: IR-02: grade D: never resale');
    expect(m.tag).toBe('IR-02');
    expect(m.basis).toBe('Read by the rules');
    expect(m.diff).toEqual([{ sign: '+', text: 'IR-02 · never resale when Grade is D' }]);
    expect(m.checks.map((c) => c.text)).toContain('Passes all 5 locked guardrails');
    expect(m.impact?.heading).toBe('Impact on the 41 open decisions');
    expect(m.impact?.lines[0]).toBe('3 of 41 open decisions change · −$1,240 queue net');
    expect(m.impact?.lines[1]).toMatch(/^Trade-off: .* gives up \$1,240\./);
    expect(previewOf({ ...ruleP, sim: { ...ruleP.sim!, dv: 900 } }, screen()).impact?.lines).toHaveLength(1);
    expect(m.limits).toBe('Saved to draft v2 only. Not published. A different person approves it after you submit.');
    expect(m.canApply).toBe(true);
  });

  it('marks a changed rule with ~ and a removed one with -', () => {
    const g = { nodes: [node('r-IR-01', { rid: 'IR-01', action: 'exclude', path: 'recycle' })], edges: [] } as never;
    expect(previewOf({ ...ruleP, graph: g }, screen()).diff).toEqual([{ sign: '~', text: 'IR-01 · never recycle' }]);
    expect(previewOf({ ...ruleP, graph: { nodes: [], edges: [] } }, screen()).diff).toEqual([{ sign: '-', text: 'IR-01 · prefer resale' }]);
  });

  it('a person without edit rights sees no Apply and the reason', () => {
    const m = previewOf(ruleP, screen({ can: { edit: false, approve: false, fork: false } }));
    expect(m.canApply).toBe(false);
    expect(m.limits).toBe('Only a person with Modeler edit rights applies this.');
  });

  it('says rules plus model when a model read it, and the draft is the next version when there is none', () => {
    const s = screen();
    (s.flow as { dver: number | null }).dver = null;
    const m = previewOf({ ...ruleP, read_by: 'rules+model' }, s);
    expect(m.basis).toBe('Read by a language model, checked by the rules');
    expect(m.limits).toMatch(/^Saved to draft v2 only\./);
  });

  it('blocked: the guardrail names the title, the message is the text, nothing to apply', () => {
    const m = previewOf({ ...ruleP, kind: 'blocked', guard: 'GR-I2', msg: 'GR-I2 is locked: a rule cannot skip it.' }, screen());
    expect(m.blocked).toBe(true);
    expect(m.title).toBe('Blocked by GR-I2');
    expect(m.diff).toEqual([]);
    expect(m.checks).toEqual([{ level: 'warn', text: 'GR-I2 is locked: a rule cannot skip it.' }]);
    expect(m.canApply).toBe(false);
  });
});

describe('Undo (plan 10 section 2.7)', () => {
  it('its journal note names the change', () => expect(undoNote('Never recycle lasers')).toBe("Undid the assistant's change: Never recycle lasers"));
  it('is available only while the draft still equals what was applied', () => {
    expect(undoAvailable('{"a":1}', '{"a":1}')).toBe(true);
    expect(undoAvailable('{"a":1}', '{"a":2}')).toBe(false);
  });
});

describe('the question hint (plan 10 section 2.1)', () => {
  it('reads a question by its mark or its first word', () => {
    for (const t of ['What does GR-I2 do?', 'why is IR-01 blocking', 'is this allowed', 'Can we ship it', 'Which grades sell fastest?']) expect(looksLikeQuestion(t)).toBe(true);
    for (const t of ['Never send grade D motors to resale', 'Whatever, prefer resale for A']) expect(looksLikeQuestion(t)).toBe(false);
  });
  it('reads a change by its first word', () => {
    for (const t of ['Never send it', 'only resale for A', 'Route lasers to repair', 'Exclude recycle']) expect(looksLikeChange(t)).toBe(true);
    for (const t of ['What changed?', 'hello']) expect(looksLikeChange(t)).toBe(false);
  });
});
