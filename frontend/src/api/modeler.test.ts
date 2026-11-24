import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { id: 7 }, key: null, action: 'x' })),
  cached: vi.fn(),
}));
vi.mock('./actions', () => ({ invoke: m.invoke }));
vi.mock('./client', async (orig) => ({ ...(await orig<typeof import('./client')>()), cached: m.cached }));

import { actionScope, matcher } from './invalidation';
import {
  applySuggestion, approveFlow, discardFlow, forkFlow, publishFlow, rejectFlow, rollbackFlow, ruleSuggestions, saveDraft, simulateFlow,
  submitFlow, useModeler, type RuleSuggestion,
} from './modeler'; // prettier-ignore
import type { FlowGraph } from './types';

const graph: FlowGraph = { nodes: [], edges: [] };
const last = () => m.invoke.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];

beforeEach(() => {
  m.invoke.mockClear();
  m.cached.mockReset();
});

describe('the Modeler facade (plan 8 MVP-4.3)', () => {
  it('reads the screen for a template and an org', () => {
    m.cached.mockReturnValue({ flow: { id: 1 } });
    useModeler('tool_fleet', 'Customer A');
    expect(m.cached).toHaveBeenCalledWith('/api/screens/modeler?template=tool_fleet&org=Customer+A');
    useModeler('', '');
    expect(m.cached).toHaveBeenLastCalledWith('/api/screens/modeler');
  });

  it('each write invokes its action with its body', async () => {
    const cases: [() => Promise<unknown>, string, Record<string, unknown>][] = [
      [() => saveDraft(3, graph), 'flow.saveDraft', { flow_id: 3, graph }],
      [() => forkFlow('industrial', 'Customer A'), 'flow.fork', { template_key: 'industrial', org_unit_id: 'Customer A' }],
      [() => submitFlow(3), 'flow.submit', { flow_id: 3 }],
      [() => approveFlow(3), 'flow.approve', { flow_id: 3 }],
      [() => rejectFlow(3, 'Scope this to grade D as well.'), 'flow.reject', { flow_id: 3, reason: 'Scope this to grade D as well.' }],
      [() => publishFlow(3), 'flow.publish', { flow_id: 3 }],
      [() => discardFlow(3), 'flow.discard', { flow_id: 3 }],
      [() => rollbackFlow(3), 'flow.rollback', { flow_id: 3 }],
    ];
    for (const [run, id, body] of cases) {
      await run();
      expect(last()).toEqual([id, body]);
    }
  });

  it('P9-0.12 rejectFlow sends node_id only when given', async () => {
    await rejectFlow(3, 'Scope this to grade D as well.', 'p-resale');
    expect(last()).toEqual(['flow.reject', { flow_id: 3, reason: 'Scope this to grade D as well.', node_id: 'p-resale' }]);
    await rejectFlow(3, 'Scope this to grade D as well.');
    expect(last()).toEqual(['flow.reject', { flow_id: 3, reason: 'Scope this to grade D as well.' }]);
  });

  it('simulates the draft or a graph, and throws the refusal', async () => {
    const sim = { kind: 'equip', n: 2, flips: [], dv: 0, extra: {} };
    m.invoke.mockResolvedValueOnce({ ok: true, output: sim, key: null, action: 'flow.simulate' });
    expect(await simulateFlow(3)).toEqual(sim);
    expect(last()).toEqual(['flow.simulate', { flow_id: 3 }]);
    m.invoke.mockResolvedValueOnce({ ok: false, error: { code: 'tenant_boundary', message: 'No.' } });
    await expect(simulateFlow(3, graph)).rejects.toThrow('No.');
    expect(last()).toEqual(['flow.simulate', { flow_id: 3, graph }]);
  });

  it('a write invalidates the Modeler and the case reads; a simulation nothing', () => {
    for (const id of ['flow.saveDraft', 'flow.fork', 'flow.submit', 'flow.approve', 'flow.reject', 'flow.publish', 'flow.discard', 'flow.rollback']) {
      const match = matcher(actionScope(id));
      expect(match).toBeTypeOf('function');
      expect(match!(['GET', '/api/screens/modeler?template=industrial'])).toBe(true);
      expect(match!(['ACT', 'case.get', { case_id: 'RT-1048' }])).toBe(true);
      expect(match!(['GET', '/api/screens/home'])).toBe(false);
    }
    expect(matcher(actionScope('flow.simulate'))).toBeNull();
  });

  it('reads the rule suggestions of a flow, and throws the refusal', async () => {
    const out = { flow_id: 3, decisions: 4, groups: [], suggestions: [] };
    m.invoke.mockResolvedValueOnce({ ok: true, output: out, key: null, action: 'flow.suggestions' });
    expect(await ruleSuggestions(3)).toEqual(out);
    expect(last()).toEqual(['flow.suggestions', { flow_id: 3 }]);
    m.invoke.mockResolvedValueOnce({ ok: false, error: { code: 'out_of_scope', message: 'The Finance view cannot read rule suggestions.' } });
    await expect(ruleSuggestions(3)).rejects.toThrow('The Finance view cannot read rule suggestions.');
  });

  it('applies a suggestion as a draft save by the person, never a publish', async () => {
    const s = {
      dim: 'cls', value: 'motor', path: 'resale', overrides: 3, decisions: 4, share: 0.75, text: 'industrial motors: prefer whole-asset resale',
      rule: { action: 'prefer', path: 'resale', scope: { cls: ['motor'] } },
      proposal: { kind: 'rule', text: 'industrial motors: prefer whole-asset resale', graph, node_id: 'r-IR-01', rid: 'IR-01', label: 'IR-01: x', guard: null, checks: [], sim: null, msg: '' },
    } as RuleSuggestion; // prettier-ignore
    await applySuggestion(3, s);
    expect(last()).toEqual([
      'flow.saveDraft',
      { flow_id: 3, graph, source: 'assistant', note: 'Suggested from overrides: industrial motors: prefer whole-asset resale' },
    ]);
  });

  it('reading suggestions changes nothing', () => {
    expect(matcher(actionScope('flow.suggestions'))).toBeNull();
  });
});
