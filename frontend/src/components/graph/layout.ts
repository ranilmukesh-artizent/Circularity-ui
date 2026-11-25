/**
 * Automatic layout for node-and-edge graphs (plan 9, P9-8.13). Owns one thing: turning sizes and links into
 * positions with dagre. Never touches React, the draft or the canvas; the Studio canvas and (P9-8.14) the Modeler
 * canvas both call it. Deterministic: the same input in the same order gives the same output.
 */
import dagre from '@dagrejs/dagre';

export interface LayoutNode { id: string; w: number; h: number }
export interface LayoutEdge { a: string; b: string }
export type LayoutDir = 'LR' | 'TB';
export type Positions = Record<string, { x: number; y: number }>;

const MARGIN = 24;

/** Top-left positions (whole pixels) for every node: no two overlap, links run left to right (`LR`) or top down (`TB`). */
export function autoLayout(nodes: LayoutNode[], edges: LayoutEdge[], dir: LayoutDir = 'LR'): Positions {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: dir, nodesep: 40, ranksep: 72, marginx: MARGIN, marginy: MARGIN });
  g.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((n) => g.setNode(n.id, { width: n.w, height: n.h }));
  edges.forEach((e) => { if (g.hasNode(e.a) && g.hasNode(e.b) && e.a !== e.b) g.setEdge(e.a, e.b); });
  dagre.layout(g);
  const out: Positions = {};
  nodes.forEach((n) => {
    const p = g.node(n.id); // dagre gives the centre; the canvas wants the top-left corner
    out[n.id] = { x: Math.round(p.x - n.w / 2), y: Math.round(p.y - n.h / 2) };
  });
  return out;
}

/** True when the node has stored coordinates (a generated or imported graph may carry none). */
export const isPlaced = (n: { x?: number; y?: number }): boolean => Number.isFinite(n.x) && Number.isFinite(n.y);

/** Positions for the nodes that have none; nodes with stored positions are left out, so they are kept as they are. */
export function placeMissing(nodes: (LayoutNode & { x?: number; y?: number })[], edges: LayoutEdge[], dir: LayoutDir = 'LR'): Positions {
  if (nodes.every(isPlaced)) return {};
  const all = autoLayout(nodes, edges, dir);
  return Object.fromEntries(nodes.filter((n) => !isPlaced(n)).map((n) => [n.id, all[n.id]]));
}
