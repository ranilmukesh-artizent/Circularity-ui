import { useRef, type PointerEvent as ReactPointerEvent } from 'react';
import type { FlowGraph, FlowNode, ModelerScreen } from '../../api/types';
import { edgePath, extent, NODE_W } from './flowEdit';

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
  onMoved: () => void;
}

/**
 * The flow canvas (the prototype's canvasHtml): absolute-positioned nodes at x, y over SVG edges; drag a node to move
 * it, click to select. Locked nodes show a lock. The fixed band labels the core prediction and agents.
 */
export function FlowCanvas({ s, graph, selected, bad, proposed, editable, onSelect, onMove, onMoved }: Props) {
  const drag = useRef<{ id: string; dx: number; dy: number; moved: boolean } | null>(null);
  const { w, h } = extent(graph);
  const by = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
  const ret = s.flow.returned;

  const down = (e: ReactPointerEvent<HTMLDivElement>, n: FlowNode) => {
    onSelect(n.id);
    if (!editable) return;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    drag.current = { id: n.id, dx: e.clientX - n.x, dy: e.clientY - n.y, moved: false };
  };
  const move = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;
    d.moved = true;
    onMove(d.id, e.clientX - d.dx, e.clientY - d.dy);
  };
  const up = () => {
    if (drag.current?.moved) onMoved();
    drag.current = null;
  };

  return (
    <div className="mdl-canvas" role="group" aria-label="Decision flow canvas">
      <div className="mdl-fc" style={{ width: w, height: h }} onPointerMove={move} onPointerUp={up}>
        <svg className="mdl-edges" width={w} height={h} aria-hidden="true">
          <defs>
            <marker id="mdl-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0L10 5L0 10z" fill="var(--muted)" />
            </marker>
          </defs>
          {s.band && (
            <g className="mdl-band">
              <rect x={s.band[0]} y={s.band[1]} width={s.band[2]} height={s.band[3]} rx="12" />
              <text x={s.band[0] + 10} y={s.band[1] + s.band[3] + 16}>{s.band[4]}</text>
            </g>
          )}
          {graph.edges.map((e) => {
            const a = by[e.a], b = by[e.b];
            if (!a || !b) return null;
            const pe = proposed && (e.a === proposed || e.b === proposed);
            return <path key={e.id} className={'mdl-ed' + (pe ? ' pe' : '')} d={edgePath(a, b)} markerEnd="url(#mdl-arr)" />;
          })}
        </svg>
        {graph.nodes.map((n) => {
          const cls = ['mdl-node', 't-' + n.t, n.id === selected && 'sel', bad.has(n.id) && 'bad', n.id === proposed && 'prop'];
          const p = n.t === 'path' ? s.template.paths.find((x) => x.id === n.path) : undefined;
          return (
            <div
              key={n.id}
              className={cls.filter(Boolean).join(' ')}
              data-node={n.id}
              title={ret && n.id === ret.node_id ? 'Returned: ' + ret.reason : undefined}
              style={{ left: n.x, top: n.y, height: n.h, width: NODE_W }}
              role="button"
              tabIndex={0}
              aria-pressed={n.id === selected}
              onPointerDown={(e) => down(e, n)}
              onKeyDown={(e) => e.key === 'Enter' && onSelect(n.id)}
            >
              <span className="hd">
                <span className="tg">{TTAG[n.t]}</span>
                {n.lock && <LockIcon />}
              </span>
              <b>{nodeTitle(n, s)}</b>
              <span className="s">{n.t === 'rule' ? n.owner ?? '' : n.sub}</span>
              {p && <span className="ow">{p.owner}</span>}
              {ret && n.id === ret.node_id && (
                <span
                  className="pill"
                  data-returned={n.id}
                  title={ret.reason}
                  aria-label={'Returned: ' + ret.reason}
                  style={{ alignSelf: 'flex-start', color: 'var(--bad)', background: 'var(--bad-soft)' }}
                >
                  Returned
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
