/**
 * The Modeler's flow canvas (plan 9, P9-8.14): draws a decision flow on the shared GraphView (xyflow) so it pans, zooms
 * and fits like the Studio. Owns the look of a flow node (title, TTAG label, lock, dashed when proposed, the returned
 * pill) and the fixed band behind the core prediction and agents. Never edits the graph: every move, connection and
 * removal goes out as a callback and the page applies `flowEdit.ts`; a locked step is refused here with a toast.
 */
import { useState } from 'react';
import { Handle, Position, type NodeProps, type NodeTypes } from '@xyflow/react';
import type { FlowGraph, FlowNode, ModelerScreen } from '../../api/types';
import { GraphView, type GEdge, type GNode, type GSel } from '../../components/graph/GraphView';
import { toast } from '../../components/toast';
import { NODE_W } from './flowEdit';

/** The prototype's TTAG: what each node type is. */
export const TTAG: Record<FlowNode['t'], string> = {
  trigger: 'Core · intake', agent: 'Core agent', gate: 'Guardrail gate', guard: 'Guardrail', decision: 'Core decision',
  approval: 'Owner approval', execute: 'Core · execute', learn: 'Core · learning', rule: 'Business rule', path: 'Outcome',
  step: 'Process step',
}; // prettier-ignore

export const LockIcon = () => (
  <svg className="mdl-lock" viewBox="0 0 24 24" aria-label="Locked" role="img">
    <rect x="5" y="11" width="14" height="10" rx="2" />
    <path d="M8 11V8a4 4 0 0 1 8 0v3" />
  </svg>
);

/** A rule node's title: "<rid> · <never|only|prefer path>" (the prototype's nodeLabel), or "set a path". */
export function nodeTitle(n: FlowNode, s: ModelerScreen): string {
  if (n.t !== 'rule') return n.label;
  const p = s.template.paths.find((x) => x.id === n.path);
  const verb = n.action === 'exclude' ? 'never ' : n.action === 'require' ? 'only ' : 'prefer ';
  return (n.rid ?? '') + ' · ' + (p ? verb + p.name.toLowerCase() : 'set a path');
}

const BAND = '__band';
const LOCKED_MSG = 'Locked steps cannot be removed.';

interface FlowData extends Record<string, unknown> {
  n: FlowNode;
  title: string;
  owner?: string;
  returned?: string;
  bad: boolean;
  proposed: boolean;
  pick: (id: string) => void;
}
interface BandData extends Record<string, unknown> { label: string; rectH: number }

function ModelerNode({ data, selected }: NodeProps) {
  const { n, title, owner, returned, bad, proposed, pick } = data as FlowData;
  const cls = ['mdl-node', 't-' + n.t, selected && 'sel', bad && 'bad', proposed && 'prop'];
  return (
    <div className={cls.filter(Boolean).join(' ')} data-node={n.id} title={returned ? 'Returned: ' + returned : undefined}
      role="button" tabIndex={0} aria-pressed={!!selected} onKeyDown={(e) => e.key === 'Enter' && pick(n.id)}>
      {n.t !== 'trigger' && <Handle type="target" position={Position.Left} className="port in mdl-port" />}
      <Handle type="source" position={Position.Right} className="port out mdl-port" />
      <span className="hd"><span className="tg">{TTAG[n.t]}</span>{n.lock && <LockIcon />}</span>
      <b>{title}</b>
      <span className="s">{n.t === 'rule' ? n.owner ?? '' : n.sub}</span>
      {owner && <span className="ow">{owner}</span>}
      {returned && (
        <span className="pill" data-returned={n.id} title={returned} aria-label={'Returned: ' + returned}
          style={{ alignSelf: 'flex-start', color: 'var(--bad)', background: 'var(--bad-soft)' }}>Returned</span>
      )}
    </div>
  );
}

/** The dashed box behind the core steps, with its label under it; it takes no clicks and cannot move. */
function BandNode({ data }: NodeProps) {
  const { label, rectH } = data as BandData;
  return <div className="mdl-band"><div className="mdl-bandbox" style={{ height: rectH }} /><span>{label}</span></div>;
}

const NODE_TYPES: NodeTypes = { flow: ModelerNode, band: BandNode };

interface Props {
  s: ModelerScreen;
  graph: FlowGraph;
  selected: string | null;
  /** node ids with a blocking check */
  bad: Set<string>;
  /** a proposed node (drawn dashed until applied or dismissed) */
  proposed?: string | null;
  editable: boolean;
  onSelect: (id: string | null) => void;
  onMove: (id: string, x: number, y: number) => void;
  /** A move is finished (drag stop or arrow key): the page schedules its autosave. */
  onMoved: () => void;
  onConnect: (a: string, b: string) => void;
  onRemove: (id: string) => void;
  onDisconnect: (edgeId: string) => void;
}

export function FlowCanvas({ s, graph, selected, bad, proposed, editable, onSelect, onMove, onMoved, onConnect, onRemove, onDisconnect }: Props) {
  const [edgeSel, setEdgeSel] = useState<string | null>(null);
  const by = new Map(graph.nodes.map((n) => [n.id, n]));
  const ret = s.flow.returned;

  const gnodes: GNode[] = graph.nodes.map((n) => {
    const p = n.t === 'path' ? s.template.paths.find((x) => x.id === n.path) : undefined;
    const isRet = !!ret && n.id === ret.node_id;
    const data: FlowData = { n, title: nodeTitle(n, s), owner: p?.owner, returned: isRet ? ret.reason : undefined, bad: bad.has(n.id), proposed: n.id === proposed, pick: (id) => onSelect(id) };
    return { id: n.id, x: n.x, y: n.y, w: NODE_W, h: n.h, type: 'flow', data, selected: n.id === selected };
  });
  if (s.band) {
    const [x, y, w, h, label] = s.band;
    const data: BandData = { label, rectH: h };
    gnodes.unshift({ id: BAND, x, y, w, h: h + 24, type: 'band', data, locked: true });
  }
  const gedges: GEdge[] = graph.edges.flatMap((e) => by.has(e.a) && by.has(e.b)
    ? [{ id: e.id, a: e.a, b: e.b, selected: e.id === edgeSel, className: proposed && (e.a === proposed || e.b === proposed) ? 'pe' : undefined }]
    : []);

  const select = (sel: GSel) => {
    if (sel?.id === BAND) return;
    setEdgeSel(sel?.t === 'e' ? sel.id : null);
    onSelect(sel?.t === 'n' ? sel.id : null);
  };
  const remove = (sel: NonNullable<GSel>) => {
    if (sel.t === 'e') { setEdgeSel(null); onDisconnect(sel.id); return; }
    if (by.get(sel.id)?.lock) { toast(LOCKED_MSG); return; }
    onRemove(sel.id);
  };
  const moveTo = (id: string, x: number, y: number) => { onMove(id, x, y); onMoved(); };

  return (
    <div className="mdl-canvas" role="group" aria-label="Decision flow canvas">
      <GraphView nodes={gnodes} edges={gedges} nodeTypes={NODE_TYPES} readOnly={!editable} minimap
        nodeColor={(id) => (by.get(id)?.lock ? 'var(--ink)' : 'var(--mv-line)')}
        label="Decision flow canvas. Select a step, then use arrow keys to move it or Delete to remove it."
        onSelect={select} onDelete={remove} onConnect={onConnect} onMove={moveTo}
        onNudge={(id, dx, dy) => { const n = by.get(id); if (n) moveTo(id, n.x + dx, n.y + dy); }} />
    </div>
  );
}
