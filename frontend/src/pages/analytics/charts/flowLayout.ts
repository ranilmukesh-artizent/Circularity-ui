/** The flow chart's geometry: the layout comes from @visx/sankey (d3-sankey), the marks are ours. Pure, so it is tested without a browser. */
import { sankey, sankeyLinkHorizontal } from '@visx/sankey';
import type { FlowGraph, FlowNode } from './chartData';

export interface PlacedNode extends FlowNode { x0: number; x1: number; y0: number; y1: number }
export interface PlacedLink { key: string; source: PlacedNode; target: PlacedNode; n: number; width: number; path: string }
export interface FlowLayout { nodes: PlacedNode[]; links: PlacedLink[]; width: number; height: number }

export const NODE_W = 14;

/** Lay the graph out in `width` x `height` with room for labels left (`left`) and right (`right`). */
export function layoutFlow(g: FlowGraph, width: number, height: number, left: number, right: number, pad = 10): FlowLayout {
  if (!g.nodes.length || !g.links.length) return { nodes: [], links: [], width, height };
  const gen = sankey<FlowNode, { n: number }>()
    .nodeId((d) => d.id)
    .nodeWidth(NODE_W)
    .nodePadding(pad)
    .nodeAlign((d) => d.col)
    .nodeSort((a, b) => a.order - b.order)
    .extent([[left, 6], [width - right, height - 6]]);
  const graph = gen({ nodes: g.nodes.map((n) => ({ ...n })), links: g.links.map((k) => ({ source: k.source, target: k.target, value: k.n, n: k.n })) });
  const path = sankeyLinkHorizontal();
  const nodes = graph.nodes as unknown as PlacedNode[];
  const links: PlacedLink[] = graph.links.map((k) => ({
    key: (k.source as unknown as PlacedNode).id + '>' + (k.target as unknown as PlacedNode).id,
    source: k.source as unknown as PlacedNode, target: k.target as unknown as PlacedNode, n: k.n, width: k.width ?? 1, path: path(k) ?? '',
  }));
  return { nodes, links, width, height };
}
