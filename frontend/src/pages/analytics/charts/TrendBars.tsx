/**
 * Net recovered each month (bars) and the gain over the baseline so far (the line, labelled at its end), on one dollar axis.
 * Each month is a button that opens its rows. Counted from the same reconciled rows as every other figure on the page.
 */
import { useMemo } from 'react';
import { kfmt, type ClosedRow } from '../../../api/analytics';
import { money } from '../../../api/format';
import { facet, fmtInt, type Labels, type ViewSpec } from '../data/dataView';
import { niceTicks, trendData, trendSummary } from './chartData';
import { trendSpec } from './specs';
import { useRoving } from './roving';
import { useWidth } from './useWidth';
import './charts.css';

const H = 310, L = 58, R = 18, T = 34, B = 50;
const signed = (v: number) => (v > 0 ? '+' : '') + kfmt(v);

export function TrendBars({ rows, labels, onViewData }: { rows: ClosedRow[]; labels: Labels; onViewData: (s: ViewSpec) => void }) {
  const t = useMemo(() => trendData(rows, labels), [rows, labels]);
  const { ref, width } = useWidth(480, 620);
  const { ref: keys, mark } = useRoving();
  if (!t.length) return <p className="note">No reconciled decisions in this selection.</p>;

  const lo = Math.min(0, ...t.map((m) => m.cumulative), ...t.map((m) => m.net)), hi = Math.max(1, ...t.map((m) => m.net), ...t.map((m) => m.cumulative)) * 1.1;
  const y = (v: number) => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  const band = (width - L - R) / t.length, cx = (i: number) => L + band * i + band / 2;
  const ticks = niceTicks(lo, hi, 4);
  const last = t[t.length - 1];
  const pts = t.map((m, i) => `${cx(i).toFixed(1)},${y(m.cumulative).toFixed(1)}`).join(' ');
  const open = (mi: number) => onViewData(trendSpec([facet.month(mi, labels)]));

  return (
    <figure className="ch-fig">
      <p className="ch-sum" id="trend-sum">{trendSummary(t, kfmt)}</p>
      <p className="ch-key" aria-hidden="true"><span><i className="k-bar" />Net recovered each month</span><span><i className="k-line" />Gain over the baseline so far</span></p>
      <div className="ch-scroll" ref={ref}>
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="group" aria-label="Net recovered per month with the gain over the baseline so far" aria-describedby="trend-sum" ref={keys}>
          {ticks.map((v) => (
            <g key={v} aria-hidden="true">
              <line className="gl" x1={L} x2={width - R} y1={y(v)} y2={y(v)} />
              <text className="ax" x={L - 8} y={y(v) + 4} textAnchor="end">{kfmt(v)}</text>
            </g>
          ))}
          {t.map((m, i) => {
            const w = Math.min(46, band * 0.62), top = Math.min(y(m.net), y(0)), h = Math.max(1, Math.abs(y(0) - y(m.net)));
            const label = `${m.label}: ${money(m.net)} net recovered, ${signed(m.uplift)} against the baseline, ${fmtInt(m.n)} cases. Opens the rows.`;
            return (
              <g key={m.mi} className="tr-m" role="button" aria-label={label} {...mark(i)} onClick={() => open(m.mi)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(m.mi); } }}>
                <rect className="tr-hit" x={cx(i) - band / 2} y={T} width={band} height={H - T - B} fill="transparent" />
                <rect className="tr-bar" x={cx(i) - w / 2} y={top} width={w} height={h} rx="2" fill="var(--chart5)" />
                <text className="ax" x={cx(i)} y={H - 28} textAnchor="middle" aria-hidden="true">{m.label}</text>
                <text className="val" x={cx(i)} y={H - 11} textAnchor="middle" aria-hidden="true">{kfmt(m.net).replace('$', '')}</text>
              </g>
            );
          })}
          <g aria-hidden="true" pointerEvents="none">
            <polyline points={pts} fill="none" stroke="var(--chart1)" strokeWidth="2.5" strokeLinejoin="round" />
            {t.map((m, i) => <circle key={m.mi} cx={cx(i)} cy={y(m.cumulative)} r="3.5" fill="var(--panel)" stroke="var(--chart1)" strokeWidth="2" />)}
            <text className="end" x={cx(t.length - 1) - 8} y={y(last.cumulative) - 12} textAnchor="end">{signed(last.cumulative)} over the baseline</text>
          </g>
        </svg>
      </div>
    </figure>
  );
}
