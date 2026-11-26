import { describe, expect, it } from 'vitest';
import type { HomeProposal } from '../../api/home';
import type { RuleSuggestions } from '../../api/modeler';
import type { Check, ModelerScreen } from '../../api/types';
import { flowBrief, heldForFlow, watchingRows } from './flowBrief';

const node = (id: string, t: string, over: Record<string, unknown> = {}) => ({ id, t, x: 0, y: 0, label: id, sub: '', h: 60, lock: t !== 'rule', ...over });
const baseNodes = () => [node('g1', 'guard'), node('r-IR-01', 'rule', { rid: 'IR-01' }), node('p1', 'path'), node('p2', 'path')];
const screen = (over: Record<string, unknown> = {}, flow: Record<string, unknown> = {}) => ({
  org: 'workspace',
  flow: {
    id: 4, name: 'Industrial returns', org_unit_id: 'workspace', status: 'pub', ver: 1, dver: null, returned: null, maker: null,
    graph: { nodes: baseNodes(), edges: [] },
    published: { nodes: baseNodes(), edges: [] },
    ...flow,
  },
  template: { guardrails: [1, 2, 3, 4, 5] },
  shadow: null,
  ...over,
}) as unknown as ModelerScreen; // prettier-ignore
const fail: Check = { level: 'fail', msg: 'IR-01 has no path: it blocks submit.', node_id: 'r-IR-01' };

describe('flowBrief: "What I see" (plan 10 section 3.3)', () => {
  it('counts guardrails, rules and outcomes from the read, tagged Rules', () => {
    const b = flowBrief(screen(), []);
    expect(b[0]).toMatchObject({ text: '5 locked guardrails, 1 business rule, 2 outcomes.', tag: 'Rules', link: null });
  });

  it('writes a blocking check as its own sentence linked to its node', () => {
    const b = flowBrief(screen(), [fail, { level: 'ok', msg: 'fine', node_id: null }]);
    const s = b.find((x) => x.text.startsWith('IR-01 has no path'));
    expect(s).toMatchObject({ icon: 'alert', link: { kind: 'node', id: 'r-IR-01' } });
    expect(s?.text).toBe('IR-01 has no path: it blocks submit.');
  });

  it('a blocking check with no node links to the Checks tab; many collapse into a count', () => {
    const many: Check[] = [1, 2, 3, 4, 5].map((i) => ({ level: 'fail', msg: `Check ${i} fails.`, node_id: null }));
    const b = flowBrief(screen(), many);
    expect(b.length).toBeLessThanOrEqual(5);
    expect(b.some((x) => x.text === '3 more blocking checks.' && x.link?.kind === 'checks')).toBe(true);
  });

  it('says how the draft differs from the published version', () => {
    const s = screen({}, { status: 'draft', ver: 1, dver: 2 });
    const nodes = [...baseNodes(), node('r-IR-02', 'rule', { rid: 'IR-02' })];
    nodes[1] = node('r-IR-01', 'rule', { rid: 'IR-01', action: 'exclude' });
    s.flow.graph = { nodes: nodes as never, edges: [] };
    const d = flowBrief(s, []).find((x) => x.text.startsWith('Draft v2'));
    expect(d?.text).toBe('Draft v2 differs from v1: 1 step added, 1 changed.');
    expect(d?.link).toEqual({ kind: 'node', id: 'r-IR-02' });
  });

  it('says there is no draft when the flow is published', () => {
    expect(flowBrief(screen(), []).map((x) => x.text)).toContain('Published v1. No draft.');
  });

  it('says so when the draft matches the published flow', () => {
    const d = flowBrief(screen({}, { status: 'draft', ver: 1, dver: 2 }), []).find((x) => x.text.startsWith('Draft v2'));
    expect(d?.text).toBe('Draft v2 matches v1.');
  });

  it('says whose flow it is when the org inherits it, and what was returned', () => {
    const s = screen({ org: 'Customer A' }, { returned: { reason: 'Scope it to grade D.', node_id: 'r-IR-01', by: 'approver', at: '' } });
    const t = flowBrief(s, []).map((x) => x.text);
    expect(t).toContain('Customer A uses the flow of workspace.');
    expect(t).toContain('Returned by approver: Scope it to grade D.');
  });

  it('never more than five sentences', () => {
    const s = screen({ org: 'Customer A' }, { status: 'draft', dver: 2, returned: { reason: 'x', node_id: null, by: 'a', at: '' } });
    expect(flowBrief(s, [fail, { ...fail, msg: 'Two.' }]).length).toBeLessThanOrEqual(5);
  });
});

const held = (over: Partial<HomeProposal>): HomeProposal => ({ id: 1, agent: 'cfg', agentName: 'Configuration agent', action: 'overlay.save', title: 'Tighten GR-01', why: '', input: {}, case_id: null, run_id: null, at: '', ...over });
const sugg = (n: number): RuleSuggestions => ({ flow_id: 4, decisions: 10, groups: [], suggestions: Array.from({ length: n }, (_, i) => ({ dim: 'd', value: String(i) }) as never) });

describe('watchingRows (plan 10 section 3.3)', () => {
  it('is empty when nothing exists', () => {
    expect(watchingRows(screen(), { suggestions: null, held: [] })).toEqual([]);
  });

  it('shadow run: n, agree, differ, tagged Simulated', () => {
    const r = watchingRows(screen({ shadow: { n: 120, agree: 114, disagree: 6, dv: -300 } }), { suggestions: null, held: [] });
    expect(r[0]).toMatchObject({ id: 'shadow', text: 'Shadow run: 120 decisions, 114 agree, 6 differ.', tag: 'Simulated' });
  });

  it('suggestions from overrides: a count, tagged Retrieved, opens the first', () => {
    const r = watchingRows(screen(), { suggestions: sugg(3), held: [] });
    expect(r[0]).toMatchObject({ id: 'suggestions', text: '3 rules suggested by approver overrides.', tag: 'Retrieved', action: 'suggestions' });
    expect(watchingRows(screen(), { suggestions: sugg(1), held: [] })[0].text).toBe('1 rule suggested by approver overrides.');
    expect(watchingRows(screen(), { suggestions: sugg(0), held: [] })).toEqual([]);
  });

  it('held proposals, tagged Prepared by agent', () => {
    const r = watchingRows(screen(), { suggestions: null, held: [held({}), held({ id: 2 })] });
    expect(r[0]).toMatchObject({ id: 'held', text: '2 proposals held for a person: Tighten GR-01.', tag: 'Prepared by agent' });
  });

  it('a draft waiting for approval is a row', () => {
    const r = watchingRows(screen({}, { status: 'review', dver: 2, maker: 'planner.a' }), { suggestions: null, held: [] });
    expect(r[0].text).toBe('Draft v2 waits for approval by someone other than planner.a.');
  });
});

describe('heldForFlow', () => {
  it('keeps flow, overlay and compose actions, and drops another flow', () => {
    const all = [
      held({ id: 1, action: 'flow.saveDraft', input: { flow_id: 4 } }),
      held({ id: 2, action: 'flow.saveDraft', input: { flow_id: 9 } }),
      held({ id: 3, action: 'overlay.save' }),
      held({ id: 4, action: 'compose.submit' }),
      held({ id: 5, action: 'decision.approve' }),
    ];
    expect(heldForFlow(all, 4).map((p) => p.id)).toEqual([1, 3, 4]);
  });
});
