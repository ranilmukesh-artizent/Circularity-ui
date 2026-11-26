import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({ invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { kind: 'equip', n: 41, flips: [], dv: 0, extra: {} }, key: null, action: 'flow.simulate' })) }));
vi.mock('./actions', () => ({ invoke: m.invoke }));

import { lastSimOf, saveDraft, simulateFlow } from './modeler';
import type { FlowGraph } from './types';

const graph: FlowGraph = { nodes: [], edges: [] };
beforeEach(() => m.invoke.mockClear());

describe('plan 10 T2: the facade', () => {
  it('saveDraft sends the note only when given', async () => {
    await saveDraft(3, graph);
    expect(m.invoke).toHaveBeenLastCalledWith('flow.saveDraft', { flow_id: 3, graph });
    await saveDraft(3, graph, "Undid the assistant's change: x");
    expect(m.invoke).toHaveBeenLastCalledWith('flow.saveDraft', { flow_id: 3, graph, note: "Undid the assistant's change: x" });
  });

  it('keeps the whole last simulation of a flow with its time and draft version', async () => {
    const t0 = Date.now();
    await simulateFlow(5, undefined, undefined, 2);
    const l = lastSimOf(5);
    expect(l?.sim.n).toBe(41);
    expect(l?.draftVer).toBe(2);
    expect(l!.at).toBeGreaterThanOrEqual(t0);
    expect(lastSimOf(6)).toBeUndefined();
  });
});
