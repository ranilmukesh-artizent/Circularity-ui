/**
 * Pure mapping from the graph canvas's nodes and edges to xyflow's. Owns one rule: a node handed to xyflow carries
 * `measured` (its fixed size). Without it xyflow resets the node's handle bounds each time the node object is rebuilt
 * (every drag step), the edges of that node lose their anchors and disappear until the node is measured again,
 * which never happens for a node of fixed size.
 */
import { MarkerType, type Edge, type Node } from '@xyflow/react';

export interface GNode {
  id: string; x: number; y: number; w: number; h: number;
  /** A key of `nodeTypes`. */
  type: string;
  data: Record<string, unknown>;
  selected?: boolean;
  /** A locked node cannot be moved: a drag calls `onBlocked` and the node stays. */
  locked?: boolean;
}
export interface GEdge { id: string; a: string; b: string; selected?: boolean; className?: string; label?: string }

export type LivePositions = Record<string, { x: number; y: number }>;

export function toRfNodes(nodes: GNode[], live: LivePositions, readOnly: boolean): Node[] {
  return nodes.map((n) => ({
    id: n.id, type: n.type, data: n.data, position: live[n.id] ?? { x: n.x, y: n.y }, width: n.w, height: n.h,
    measured: { width: n.w, height: n.h }, selected: !!n.selected, draggable: !readOnly,
  }));
}

export function toRfEdges(edges: GEdge[]): Edge[] {
  return edges.map((e) => ({
    id: e.id, source: e.a, target: e.b, type: 'smoothstep', className: e.className, label: e.label, selected: !!e.selected,
    markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 }, interactionWidth: 24,
  }));
}
