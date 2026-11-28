/**
 * Where returned assets go: asset class, then route, then outcome. Bands are sized by decisions (the count and the net
 * recovered are in each label); hovering or focusing a part lights its path; Enter or a click opens View data for it.
 * The layout is @visx/sankey's; the marks, colours and labels are drawn here with the app's tokens.
 */
import { useMemo, useState, type KeyboardEvent } from 'react';
import { kfmt, type ClosedRow } from '../../../api/analytics';
import { facet, fmtInt, type Labels, type ViewSpec } from '../data/dataView';
import { flowGraph, flowSummary, litPath, spreadLabels, type FlowNode } from './chartData';
import { layoutFlow, NODE_W, type PlacedLink, type PlacedNode } from './flowLayout';
import { flowSpec } from './specs';
import { useRoving } from './roving';
import { useWidth } from './useWidth';
import './charts.css';

const LEFT = 168, RIGHT = 196;

const nodeColor = (n: FlowNode): string =>
  n.kind === 'route' ? `var(--rt-${n.ref}, var(--chart4))` : n.kind === 'cls' ? 'var(--chart4)' : n.ref === 'reconciled' ? 'var(--ok)' : n.ref === 'pending' ? 'var(--warn)' : 'var(--muted)';

const detail = (n: FlowNode): string => (n.net ? `${fmtInt(n.n)} · ${kfmt(n.net)}` : fmtInt(n.n));

export function Flow({ rows, labels, onViewData }: { rows: ClosedRow[]; labels: Labels; onViewData: (s: ViewSpec) => void }) {
  const g = useMemo(() => flowGraph(rows, labels), [rows, labels]);
  const { ref, width } = useWidth(700);
  const maxCol = Math.max(1, ...[0, 1, 2].map((c) => g.nodes.filter((n) => n.col === c).length));
  const height = Math.max(300, maxCol * 44 + 16);
  const lay = useMemo(() => layoutFlow(g, width, height, LEFT, RIGHT), [g, width, height]);
  const [active, setActive] = useState<{ kind: 'node' | 'link'; id: string } | null>(null);
  const lit = litPath(g, active);
  const { ref: keys, mark } = useRoving();
  const summary = flowSummary(g);

  if (!g.total) return <p className="note">No decisions in this selection.</p>;

  const openNode = (n: PlacedNode) => {
    const f = n.kind === 'cls' ? facet.cls(n.ref, labels) : n.kind === 'route' ? facet.route(n.ref, labels) : facet.status(n.ref as never);
    onViewData(flowSpec([f]));
  };
  const openLink = (k: PlacedLink) => {
    const [a, b] = [k.source, k.target];
    const cls = a.kind === 'cls' ? a : null, route = a.kind === 'route' ? a : b, out = b.kind === 'out' ? b : null;
    onViewData(flowSpec([cls ? facet.cls(cls.ref, labels) : facet.route(route.ref, labels), cls ? facet.route(b.ref, labels) : facet.status(out!.ref as never)]));
  };
  const act = (e: KeyboardEvent, f: () => void) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); f(); } };
  const cols = [0, 1, 2].map((c) => lay.nodes.filter((n) => n.col === c));
  const ly = cols.map((c) => spreadLabels(c.map((n) => (n.y0 + n.y1) / 2 - 8), 36, 4, height - 36));
  let i = 0;

  return (
    <figure className="ch-fig">
      <p className="ch-sum" id="flow-sum">{summary}</p>
      <div className="ch-scroll" ref={ref}>
        <svg className="fl" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="group" aria-label="Flow of decisions from asset class to route to outcome" aria-describedby="flow-sum" ref={keys}>
          <g>
            {lay.nodes.map((n) => {
              const dim = lit && !lit.nodes.has(n.id);
              const label = `${n.label}: ${fmtInt(n.n)} decisions${n.net ? `, ${kfmt(n.net)} net recovered` : ''}. Opens the rows.`;
              const idx = i++;
              return (
                <rect
                  key={n.id} className="fl-node" role="button" aria-label={label} x={n.x0} y={n.y0} width={NODE_W} height={Math.max(2, n.y1 - n.y0)} rx="2" fill={nodeColor(n)} opacity={dim ? 0.3 : 1}
                  {...mark(idx)} onClick={() => openNode(n)} onKeyDown={(e) => act(e, () => openNode(n))}
                  onMouseEnter={() => setActive({ kind: 'node', id: n.id })} onMouseLeave={() => setActive(null)}
                  onFocus={() => { mark(idx).onFocus(); setActive({ kind: 'node', id: n.id }); }} onBlur={() => setActive(null)}
                />
              );
            })}
          </g>
          <g fill="none">
            {lay.links.map((k) => {
              const rt = k.source.kind === 'route' ? k.source : k.target;
              const on = lit?.links.has(k.key), dim = lit && !on;
              const label = `${k.source.label} to ${k.target.label}: ${fmtInt(k.n)} decisions. Opens the rows.`;
              const idx = i++;
              return (
                <path
                  key={k.key} className="fl-link" role="button" aria-label={label} d={k.path} stroke={nodeColor(rt)} strokeWidth={Math.max(3, k.width)} strokeOpacity={on ? 0.8 : dim ? 0.08 : 0.42}
                  {...mark(idx)} onClick={() => openLink(k)} onKeyDown={(e) => act(e, () => openLink(k))}
                  onMouseEnter={() => setActive({ kind: 'link', id: k.key })} onMouseLeave={() => setActive(null)}
                  onFocus={() => { mark(idx).onFocus(); setActive({ kind: 'link', id: k.key }); }} onBlur={() => setActive(null)}
                />
              );
            })}
          </g>
          <g aria-hidden="true">
            {cols.map((c, ci) => c.map((n, k) => {
              const left = n.col === 0, x = left ? n.x0 - 8 : n.x1 + 8, y = ly[ci][k] + 12;
              const dim = lit && !lit.nodes.has(n.id);
              const mid = n.col === 1, tx = mid ? x + 6 : x;
              const pw = Math.ceil(Math.max(n.label.length * 7.9, detail(n).length * 6.8)) + 14;
              return (
                <g key={n.id} opacity={dim ? 0.4 : 1}>
                  {mid && <rect className="fl-plate" x={x - 2} y={y - 14} width={pw} height={36} rx="4" />}
                  <text className="fl-lbl" x={tx} y={y} textAnchor={left ? 'end' : 'start'}>
                    <tspan className="fl-name">{n.label}</tspan>
                    <tspan className="fl-sub" x={tx} dy="1.25em">{detail(n)}</tspan>
                  </text>
                </g>
              );
            }))}
          </g>
        </svg>
      </div>
      <p className="note ch-hint">Band width is the number of decisions. Select a band or a block to open the rows behind it.</p>
    </figure>
  );
}
