/**
 * Pure edits of a decision flow graph (plan 8, MVP-4.4; Domain spec D1 and D10). Every function returns a new graph
 * and leaves its argument alone; an edit that is not allowed (removing a locked step, a duplicate connection) returns
 * the graph unchanged. The server checks and compiles whatever is saved (flow.saveDraft).
 */
import type { FlowEdge, FlowGraph, FlowNode } from '../../api/types';

/** The prototype's NW: every node is this wide. */
export const NODE_W = 168;

const edge = (a: string, b: string, l = ''): FlowEdge => ({ id: a + '>' + b, a, b, l });

const decisionOf = (g: FlowGraph): FlowNode | undefined => g.nodes.find((n) => n.t === 'decision');
const gateOf = (g: FlowGraph): FlowNode | undefined => g.nodes.find((n) => n.t === 'gate');

/** The next rule id: the highest number among the existing rules plus one, two digits (`BR-03` after BR-01, BR-02). */
export function nextRid(g: FlowGraph, pre: string): string {
  const nums = g.nodes.filter((n) => n.rid).map((n) => Number((n.rid ?? '').split('-').pop()) || 0);
  return pre + '-' + String(Math.max(0, ...nums) + 1).padStart(2, '0');
}

/** A node id not used yet in the graph, from a base. */
function freeId(g: FlowGraph, base: string): string {
  const used = new Set(g.nodes.map((n) => n.id));
  let id = base;
  for (let k = 2; used.has(id); k++) id = base + '-' + k;
  return id;
}

/**
 * A new rule node (no path yet, action exclude) between the node feeding the decision and the decision, as the
 * prototype's buildProposal places a proposed rule: under the gate, below the lowest rule.
 */
export function addRule(g: FlowGraph, rid: string, owner: string, extra: Partial<FlowNode> = {}): FlowGraph {
  const dec = decisionOf(g), gate = gateOf(g);
  if (!dec || !gate) return g;
  const into = g.edges.find((e) => e.b === dec.id);
  const last = into ? into.a : gate.id;
  const rules = g.nodes.filter((n) => n.t === 'rule');
  const y = (rules.length ? Math.max(...rules.map((n) => n.y)) : 50) + 140;
  const id = freeId(g, 'r-' + rid);
  const node: FlowNode = {
    id, t: 'rule', x: gate.x, y, label: '', sub: '', h: 112, lock: false, rid, action: 'exclude', path: null, scope: {}, owner, ...extra,
  }; // prettier-ignore
  const edges = g.edges.filter((e) => e !== into);
  return { nodes: [...g.nodes, node], edges: [...edges, edge(last, id), edge(id, dec.id)] };
}

/** Remove a step and its connections; a locked step stays. */
export function removeNode(g: FlowGraph, id: string): FlowGraph {
  const n = g.nodes.find((x) => x.id === id);
  if (!n || n.lock) return g;
  return { nodes: g.nodes.filter((x) => x.id !== id), edges: g.edges.filter((e) => e.a !== id && e.b !== id) };
}

/** Connect a to b (not to itself, not twice). */
export function connect(g: FlowGraph, a: string, b: string): FlowGraph {
  const ids = new Set(g.nodes.map((n) => n.id));
  if (a === b || !ids.has(a) || !ids.has(b) || g.edges.some((e) => e.a === a && e.b === b)) return g;
  return { nodes: g.nodes, edges: [...g.edges, edge(a, b)] };
}

/** Remove a connection; one between two locked steps (the core chain) stays. */
export function disconnect(g: FlowGraph, edgeId: string): FlowGraph {
  const e = g.edges.find((x) => x.id === edgeId);
  if (!e) return g;
  const lock = (id: string) => g.nodes.find((n) => n.id === id)?.lock ?? false;
  if (lock(e.a) && lock(e.b)) return g;
  return { nodes: g.nodes, edges: g.edges.filter((x) => x !== e) };
}

/** Move a step (locked steps may move too), kept on the canvas. */
export function moveNode(g: FlowGraph, id: string, x: number, y: number): FlowGraph {
  const at = (v: number) => Math.max(0, Math.round(v));
  return { nodes: g.nodes.map((n) => (n.id === id ? { ...n, x: at(x), y: at(y) } : n)), edges: g.edges };
}

/** Change a rule's action, path, scope or owner. */
export function updateRule(g: FlowGraph, id: string, patch: Pick<Partial<FlowNode>, 'action' | 'path' | 'scope' | 'owner'>): FlowGraph {
  return { nodes: g.nodes.map((n) => (n.id === id && n.t === 'rule' ? { ...n, ...patch } : n)), edges: g.edges };
}

/** The canvas size that holds every node, with a margin. */
export function extent(g: FlowGraph): { w: number; h: number } {
  const w = Math.max(600, ...g.nodes.map((n) => n.x + NODE_W)) + 60;
  const h = Math.max(300, ...g.nodes.map((n) => n.y + n.h)) + 60;
  return { w, h };
}

/** The prototype's edgePath: a curve from a's right side to b's left side (or round the right when b is behind). */
export function edgePath(a: FlowNode, b: FlowNode): string {
  const x1 = a.x + NODE_W, y1 = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2, dx = Math.max(40, Math.abs(x2 - x1) / 2);
  if (x2 >= x1 - 10) return `M${x1} ${y1} C${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2 - 2} ${y2}`;
  if (Math.abs(a.x - b.x) < 20) {
    const xr = a.x + NODE_W + 26;
    return `M${x1} ${y1} C${xr} ${y1} ${xr} ${y2} ${b.x + NODE_W} ${y2}`;
  }
  return `M${x1} ${y1} C${x1 + 80} ${y1} ${x2 - 80} ${y2} ${x2 - 2} ${y2}`;
}
