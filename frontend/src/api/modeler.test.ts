import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { id: 7 }, key: null, action: 'x' })),
  cached: vi.fn(),
}));
vi.mock('./actions', () => ({ invoke: m.invoke }));
vi.mock('./client', async (orig) => ({ ...(await orig<typeof import('./client')>()), cached: m.cached }));

import { actionScope, matcher } from './invalidation';
import {
  approveFlow, discardFlow, forkFlow, publishFlow, rejectFlow, rollbackFlow, saveDraft, simulateFlow, submitFlow, useModeler,
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
});
