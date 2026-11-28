/**
 * Typical gain over the baseline per case (the median, so one large sale does not decide it), by route and asset class.
 * Green above zero, red below, the number in every cell; fewer than five cases shows a dash (the rows are still one click away).
 */
import { useMemo } from 'react';
import type { ClosedRow } from '../../../api/analytics';
import { facet, fmtInt, formatMeasure, type Labels, type ViewSpec } from '../data/dataView';
import { heatData, heatSummary, MIN_CELL, tint, type HeatCell } from './chartData';
import { heatSpec } from './specs';
import { useRoving } from './roving';
import './charts.css';

const signed = (v: number): string => (v > 0 ? '+' : '') + formatMeasure(v, 'usd');
const background = (v: number | null, max: number): string | undefined =>
  v == null || v === 0 ? undefined : `color-mix(in srgb, var(${v > 0 ? '--ok' : '--bad'}) ${Math.round(8 + tint(v, max) * 42)}%, var(--panel))`;

export function HeatGrid({ rows, labels, onViewData }: { rows: ClosedRow[]; labels: Labels; onViewData: (s: ViewSpec) => void }) {
  const h = useMemo(() => heatData(rows, labels), [rows, labels]);
  const { ref: keys, mark } = useRoving();
  if (!h.routes.length) return <p className="note">No reconciled decisions in this selection.</p>;
  const cols = h.classes.length + 1;
  let m = 0;

  const cell = (c: HeatCell, r: number, k: number, name: string, parts: ReturnType<typeof facet.route>[]) => {
    const idx = m++;
    const none = c.n === 0, dash = c.median == null;
    const text = none ? '' : dash ? '–' : signed(c.median!);
    const label = none ? `${name}: no cases` : dash
      ? `${name}: fewer than ${MIN_CELL} cases (${fmtInt(c.n)}), too few for a typical gain. Opens the rows.`
      : `${name}: typical gain ${signed(c.median!)} per case across ${fmtInt(c.n)} cases. Opens the rows.`;
    return (
      <button
        key={`${r}-${k}`} type="button" className={'hg-cell' + (dash ? ' dash' : '') + (r === h.routes.length || k === h.classes.length ? ' tot' : '')} style={{ background: background(c.median, h.maxAbs) }} disabled={none}
        aria-label={label} data-row={r} data-col={k} {...(none ? {} : mark(idx))} onClick={() => onViewData(heatSpec(parts))}
      >
        <b className={c.median != null && c.median < 0 ? 'neg-t' : undefined}>{text}</b>
        {!none && <span>{fmtInt(c.n)} {c.n === 1 ? 'case' : 'cases'}</span>}
      </button>
    );
  };

  return (
    <figure className="ch-fig">
      <p className="ch-sum" id="heat-sum">{heatSummary(h)}</p>
      <div className="ch-scroll">
        <div className="hg" role="group" aria-label="Typical gain per case by route and asset class" aria-describedby="heat-sum" ref={keys} style={{ gridTemplateColumns: `minmax(120px, 1.1fr) repeat(${cols}, minmax(84px, 1fr))` }}>
          <span />
          {h.classes.map((c) => <span key={c.id} className="hg-h">{c.label}</span>)}
          <span className="hg-h hg-all">All classes</span>
          {h.routes.map((rt, r) => [
            <span key={rt.id} className="hg-r"><i style={{ background: `var(--rt-${rt.id}, var(--chart4))` }} aria-hidden="true" />{rt.label}</span>,
            ...h.classes.map((c, k) => cell(h.cells[r * h.classes.length + k], r, k, `${rt.label}, ${c.label}`, [facet.route(rt.id, labels), facet.cls(c.id, labels)])),
            cell(h.byRoute[r], r, h.classes.length, `${rt.label}, all classes`, [facet.route(rt.id, labels)]),
          ])}
          <span className="hg-r hg-all">All routes</span>
          {h.byClass.map((c, k) => cell(c, h.routes.length, k, `${h.classes[k].label}, all routes`, [facet.cls(h.classes[k].id, labels)]))}
          {cell(h.all, h.routes.length, h.classes.length, 'All routes and classes', [])}
        </div>
      </div>
      <p className="note ch-hint">Median gain per reconciled case over the agreed baseline (modelled). Green is above it, red below. A dash means fewer than {MIN_CELL} cases.</p>
    </figure>
  );
}
