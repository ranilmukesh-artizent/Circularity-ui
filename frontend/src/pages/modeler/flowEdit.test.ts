import { describe, expect, it } from 'vitest';
import type { FlowGraph, FlowNode } from '../../api/types';
import { addRule, connect, disconnect, moveNode, nextRid, removeNode, updateRule } from './flowEdit';

const n = (id: string, t: FlowNode['t'], x: number, y: number, extra: Partial<FlowNode> = {}): FlowNode => ({
  id, t, x, y, label: id, sub: '', h: t === 'path' ? 104 : 112, lock: !['rule', 'path', 'step'].includes(t), ...extra,
}); // prettier-ignore
const e = (a: string, b: string) => ({ id: a + '>' + b, a, b, l: '' });

/** The tool-fleet shape: trigger, gate, two rules, decision, approval, one path. */
const g: FlowGraph = {
  nodes: [
    n('in', 'trigger', 24, 40), n('gate', 'gate', 1004, 40),
    n('r1', 'rule', 1004, 190, { rid: 'BR-01', action: 'exclude', path: 'exit', scope: {} }),
    n('r2', 'rule', 1004, 330, { rid: 'BR-02', action: 'prefer', path: 'refurb', scope: {} }),
    n('dec', 'decision', 1200, 330), n('apr', 'approval', 1396, 330), n('p-exit', 'path', 1592, 20, { path: 'exit' }),
  ],
  edges: [e('in', 'gate'), e('gate', 'r1'), e('r1', 'r2'), e('r2', 'dec'), e('dec', 'apr'), e('apr', 'p-exit')],
};

describe('flow edits', () => {
  it('nextRid gives BR-03 after BR-01 and BR-02, and 01 with no rules', () => {
    expect(nextRid(g, 'BR')).toBe('BR-03');
    expect(nextRid({ nodes: [], edges: [] }, 'IR')).toBe('IR-01');
  });

  it('addRule places the rule between the gate chain and the decision', () => {
    const out = addRule(g, 'BR-03', 'Fleet desk');
    const r = out.nodes.at(-1)!;
    expect(r).toMatchObject({ t: 'rule', rid: 'BR-03', owner: 'Fleet desk', x: 1004, y: 470, lock: false, path: null });
    expect(out.edges.map((x) => x.id)).toEqual(['in>gate', 'gate>r1', 'r1>r2', 'dec>apr', 'apr>p-exit', 'r2>' + r.id, r.id + '>dec']);
    expect(g.nodes).toHaveLength(7); // the argument is unchanged
  });

  it('addRule with no rule feeding the decision starts from the gate', () => {
    const bare: FlowGraph = { nodes: g.nodes.filter((x) => x.t !== 'rule'), edges: [e('in', 'gate'), e('dec', 'apr')] };
    const out = addRule(bare, 'IR-01', 'Planner');
    expect(out.edges.slice(-2).map((x) => x.id)).toEqual(['gate>r-IR-01', 'r-IR-01>dec']);
  });

  it('removeNode on a locked node is a no-op; on a rule it drops the node and its edges', () => {
    expect(removeNode(g, 'gate')).toBe(g);
    const out = removeNode(g, 'r1');
    expect(out.nodes.some((x) => x.id === 'r1')).toBe(false);
    expect(out.edges.map((x) => x.id)).toEqual(['in>gate', 'r2>dec', 'dec>apr', 'apr>p-exit']);
  });

  it('connect and disconnect: no self or duplicate edges, the core chain stays', () => {
    expect(connect(g, 'r1', 'r1')).toBe(g);
    expect(connect(g, 'gate', 'r1')).toBe(g);
    expect(connect(g, 'gate', 'r2').edges.at(-1)!.id).toBe('gate>r2');
    expect(disconnect(g, 'dec>apr')).toBe(g);
    expect(disconnect(g, 'r1>r2').edges.map((x) => x.id)).not.toContain('r1>r2');
  });

  it('moveNode and updateRule', () => {
    expect(moveNode(g, 'gate', 10.4, -5).nodes[1]).toMatchObject({ x: 10, y: 0 });
    const out = updateRule(g, 'r1', { action: 'require', scope: { grade: ['C'] } });
    expect(out.nodes[2]).toMatchObject({ action: 'require', path: 'exit', scope: { grade: ['C'] } });
    expect(updateRule(g, 'gate', { action: 'require' }).nodes[1].action).toBeUndefined();
  });
});
