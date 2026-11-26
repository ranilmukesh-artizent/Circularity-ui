/**
 * The shared graph canvas (plan 9, P9-8.13): one wrapper over @xyflow/react 12 for every node-and-edge screen (Workflow
 * Studio now, the Modeler in P9-8.14). It owns pan, zoom, fit on open, minimap, controls, drag to move, drag from a
 * node's right handle to connect, click to select, and the Delete and arrow keys. It never owns the graph: nodes and
 * edges come in as props, every change goes out as a callback, and the caller decides what is allowed (fixed steps,
 * `canLink`, the draft). It knows nothing about workflows, drafts, toasts or the action pipeline.
 */
import '@xyflow/react/dist/base.css';
import './graph.css';
import { useEffect, useRef, useState, type MutableRefObject } from 'react';
import {
  Background, BackgroundVariant, ControlButton, Controls, MiniMap, ReactFlow, ReactFlowProvider, useReactFlow,
  type NodeChange, type NodePositionChange, type NodeTypes,
} from '@xyflow/react';
import { toRfEdges, toRfNodes, type GEdge, type GNode } from './rfModel';

export type { GNode, GEdge };
export type GSel = { t: 'n' | 'e'; id: string } | null;

/** What the owner can ask of the canvas (a drop from a palette, "centre on this step", "fit"). */
export interface GraphApi {
  screenToFlow: (p: { x: number; y: number }) => { x: number; y: number };
  center: (x: number, y: number) => void;
  fit: () => void;
  bounds: () => DOMRect | null;
}

export interface GraphViewProps {
  nodes: GNode[];
  edges: GEdge[];
  nodeTypes: NodeTypes;
  onMove: (id: string, x: number, y: number) => void;
  onConnect: (a: string, b: string) => void;
  onSelect: (sel: GSel) => void;
  /** Delete or Backspace with something selected. */
  onDelete: (sel: NonNullable<GSel>) => void;
  /** An arrow key with a node selected (8 px, 40 with Shift). */
  onNudge?: (id: string, dx: number, dy: number) => void;
  onBlocked?: (id: string) => void;
  readOnly?: boolean;
  minimap?: boolean;
  /** The minimap's size in px (default 200 x 150). */
  minimapSize?: [number, number];
  /** Dot grid spacing in px (default 20; the Modeler uses 24). */
  gap?: number;
  /**
   * The lowest zoom the first view may open at (default: none, the whole graph is fitted). When the whole graph would
   * need less, it opens at this zoom from the top left instead, so labels stay legible; the fit control still shows all.
   */
  openZoom?: number;
  nodeColor?: (id: string) => string;
  apiRef?: MutableRefObject<GraphApi | null>;
  label: string;
}

const ARROWS: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };

function Inner(p: GraphViewProps) {
  const rf = useReactFlow();
  const box = useRef<HTMLDivElement>(null);
  const [live, setLive] = useState<Record<string, { x: number; y: number }>>({}); // positions while a drag is in progress
  const blocked = useRef(false);
  const [mapOpen, setMapOpen] = useState(true);
  const latest = useRef(p);
  latest.current = p;

  useEffect(() => {
    if (!p.apiRef) return;
    const ref = p.apiRef;
    ref.current = {
      screenToFlow: (pt) => rf.screenToFlowPosition(pt),
      center: (x, y) => { void rf.setCenter(x, y, { zoom: rf.getZoom(), duration: 300 }); },
      fit: () => { void rf.fitView({ padding: 0.15, maxZoom: 1, duration: 250 }); },
      bounds: () => box.current?.getBoundingClientRect() ?? null,
    };
    return () => { ref.current = null; };
  }, [rf, p.apiRef]);

  // Delete and arrows, from anywhere on the page except a text field (the demo's document-level keys)
  useEffect(() => {
    function key(e: KeyboardEvent) {
      const q = latest.current;
      if (q.readOnly || (e.target as Element).closest?.('input,select,textarea')) return;
      const sn = q.nodes.find((n) => n.selected), se = q.edges.find((x) => x.selected);
      const sel: GSel = sn ? { t: 'n', id: sn.id } : se ? { t: 'e', id: se.id } : null;
      if (!sel) return;
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); q.onDelete(sel); return; }
      const m = ARROWS[e.key];
      if (m && sel.t === 'n' && q.onNudge) { e.preventDefault(); const s = e.shiftKey ? 40 : 8; q.onNudge(sel.id, m[0] * s, m[1] * s); }
    }
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, []);

  // Enter or Space on a focused node selects it (the node's own div is the tab stop; a click does the same)
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    function nodeKey(e: KeyboardEvent) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const t = e.target as Element;
      if (t.getAttribute('role') !== 'button') return;
      const id = t.closest('.react-flow__node')?.getAttribute('data-id');
      if (!id) return;
      e.preventDefault();
      latest.current.onSelect({ t: 'n', id });
    }
    el.addEventListener('keydown', nodeKey);
    return () => el.removeEventListener('keydown', nodeKey);
  }, []);

  /** Open at `openZoom` at least: fit when the graph fits there, else anchor its top left (padding 24) at that zoom. */
  function openView() {
    const z = p.openZoom;
    const list = rf.getNodes();
    if (!z || !list.length) return;
    const b = rf.getNodesBounds(list);
    const el = box.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    const fit = Math.min((width - 48) / b.width, (height - 48) / b.height);
    if (fit >= z) { void rf.fitView({ padding: 0.08, maxZoom: 1 }); return; }
    void rf.setViewport({ x: 24 - b.x * z, y: 24 - b.y * z, zoom: z });
  }

  const nodes = toRfNodes(p.nodes, live, !!p.readOnly);
  const edges = toRfEdges(p.edges);
  const by = new Map(p.nodes.map((n) => [n.id, n]));

  function changes(cs: NodeChange[]) {
    const moved = cs.filter((c): c is NodePositionChange => c.type === 'position' && !!c.position && !by.get(c.id)?.locked);
    if (moved.length) setLive((l) => { const next = { ...l }; moved.forEach((c) => { next[c.id] = c.position!; }); return next; });
  }

  return (
    <div className="graphbox" ref={box}>
      <ReactFlow
        nodes={nodes} edges={edges} nodeTypes={p.nodeTypes} onNodesChange={changes}
        onNodeClick={(_, n) => p.onSelect({ t: 'n', id: n.id })} onEdgeClick={(_, e) => p.onSelect({ t: 'e', id: e.id })} onPaneClick={() => p.onSelect(null)}
        onNodeDragStart={(_, n) => { blocked.current = false; p.onSelect({ t: 'n', id: n.id }); if (by.get(n.id)?.locked) { blocked.current = true; p.onBlocked?.(n.id); } }}
        onNodeDragStop={(_, n) => { setLive({}); if (!blocked.current && !by.get(n.id)?.locked) p.onMove(n.id, n.position.x, n.position.y); blocked.current = false; }}
        onConnect={(c) => { if (c.source && c.target) p.onConnect(c.source, c.target); }}
        nodesDraggable={!p.readOnly} nodesConnectable={!p.readOnly} nodesFocusable={false} edgesFocusable={false}
        deleteKeyCode={null} disableKeyboardA11y selectionKeyCode={null}
        fitView={!p.openZoom} onInit={p.openZoom ? openView : undefined} fitViewOptions={{ padding: p.openZoom ? 0.08 : 0.15, maxZoom: 1 }} minZoom={0.2} maxZoom={1.6} zoomOnDoubleClick={false}
        aria-label={p.label}
      >
        <Background variant={BackgroundVariant.Dots} gap={p.gap ?? 20} size={1} color="var(--line)" />
        <Controls showInteractive={false} position="bottom-left">
          {p.minimap && p.minimapSize && (
            <ControlButton onClick={() => setMapOpen((o) => !o)} aria-label={mapOpen ? 'Hide the minimap' : 'Show the minimap'} aria-pressed={mapOpen} title={mapOpen ? 'Hide the minimap' : 'Show the minimap'}>
              <svg viewBox="0 0 24 24" style={{ fill: 'none' }} stroke="currentColor" strokeWidth="2" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><rect x="12" y="12" width="6" height="6" /></svg>
            </ControlButton>
          )}
        </Controls>
        {p.minimap && mapOpen && <MiniMap pannable zoomable nodeBorderRadius={4} style={p.minimapSize ? { width: p.minimapSize[0], height: p.minimapSize[1] } : undefined} nodeColor={(n) => p.nodeColor?.(n.id) ?? 'var(--mv-line)'} />}
      </ReactFlow>
    </div>
  );
}

export function GraphView(p: GraphViewProps) {
  return <ReactFlowProvider><Inner {...p} /></ReactFlowProvider>;
}
