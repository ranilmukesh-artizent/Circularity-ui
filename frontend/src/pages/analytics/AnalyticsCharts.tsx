/** The Analytics charts (the demo's waterfall, mixChart, funnel, scatter, heat, poolChart, overrides, sustain, modelTable) as JSX SVG. */
import type { CSSProperties, KeyboardEvent } from 'react';
import {
  components, equipmentModels, kfmt, modelStats, modelVersions, months, pct, routeById, routes, sum, telemetryUnavailable,
  type ClosedRow, type Metrics,
} from '../../api/analytics';
import { money } from '../../api/format';
import { onActivateKey } from '../../utils/keys';
import './analytics.css';

export interface Drill { title: string; fn: (r: ClosedRow) => boolean }
type OnDrill = (d: Drill) => void;

const fix = (n: number) => +n.toFixed(2);
/** A route's chart colour: a theme token (analytics.css) with 3:1 against the card in both themes, whatever colour the server sent. */
const routeColor = (id: string, fallback: string) => `var(--rt-${id}, ${fallback})`;

/** A category label on two lines (the chart's text is large, so a long name wraps instead of colliding with its neighbour). */
function Cat({ x, y, text }: { x: number; y: number; text: string }) {
  const i = text.indexOf(' ');
  const [a, b] = i < 0 ? [text, ''] : [text.slice(0, i), text.slice(i + 1)];
  return <text x={x} y={y} textAnchor="middle"><tspan x={x}>{a}</tspan>{b && <tspan x={x} dy="1.15em">{b}</tspan>}</text>;
}
const allReconciled: Drill = { title: 'All reconciled decisions', fn: (r) => r.status === 'reconciled' };
export const drills = {
  all: allReconciled,
  avoid: { title: 'Confirmed avoided spend', fn: (r: ClosedRow) => r.avoided > 0 },
  pend: { title: 'Pending outcomes', fn: (r: ClosedRow) => r.status === 'pending' },
};

function keyAct(f: () => void) {
  return { onClick: f, onKeyDown: (e: KeyboardEvent) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), f()) };
}

export function Waterfall({ m, onDrill }: { m: Metrics; onDrill: OnDrill }) {
  const rc = m.rc;
  const steps = routes().map((rt) => ({ id: rt.id, l: rt.short, v: sum(rc.filter((r) => r.route === rt.id).map((r) => (r.actual ?? 0) - r.baseline)) }));
  const W = 720, H = 360, L = 64, B = 52, T = 22, n = steps.length + 2, bw = (W - L - 10) / n;
  const max = m.act * 1.04 || 1, sc = (v: number) => T + (H - T - B) * (1 - v / max);
  let run = m.base;
  return (
    <svg className="ch big" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Recovery waterfall from baseline to Circularity, by route">
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <g key={f}>
          <line className="gl" x1={L} x2={W} y1={fix(sc((max * f) / 1.04))} y2={fix(sc((max * f) / 1.04))} />
          <text x={L - 6} y={fix(sc((max * f) / 1.04) + 4)} textAnchor="end">{kfmt((max * f) / 1.04)}</text>
        </g>
      ))}
      <g className="clk" data-tip={`Baseline: ${money(m.base)}. What current practice would have recovered`} onClick={() => onDrill(allReconciled)}>
        <title>{`Baseline: ${money(m.base)}. What current practice would have recovered`}</title>
        <rect x={L + 4} y={fix(sc(m.base))} width={bw - 10} height={Math.max(0, fix(H - B - sc(m.base)))} fill="var(--chart5)" />
      </g>
      <text x={fix(L + bw / 2)} y={fix(sc(m.base) - 6)} textAnchor="middle" className="lbl">{kfmt(m.base)}</text>
      <Cat x={fix(L + bw / 2)} y={H - B + 18} text="Baseline" />
      {steps.map((s, i) => {
        const x = L + (i + 1) * bw, y0 = sc(run), y1 = sc(run + s.v);
        run += s.v;
        const tip = `${routeById(s.id).name}: ${money(s.v)} vs baseline`;
        return (
          <g key={s.id}>
            <g className="clk" data-tip={tip} onClick={() => onDrill({ title: routeById(s.id).name + ' · reconciled', fn: (r) => r.route === s.id && r.status === 'reconciled' })}>
              <title>{tip}</title>
              <rect x={fix(x + 4)} y={fix(Math.min(y0, y1))} width={fix(bw - 10)} height={fix(Math.max(2, Math.abs(y0 - y1)))} fill={s.v >= 0 ? 'var(--yellow)' : 'var(--bad)'} stroke="rgba(0,0,0,.3)" />
            </g>
            <text x={fix(x + bw / 2)} y={fix(Math.min(y0, y1) - 6)} textAnchor="middle" className="lbl">{(s.v >= 0 ? '+' : '') + kfmt(s.v)}</text>
            <Cat x={fix(x + bw / 2)} y={H - B + 18} text={s.l} />
          </g>
        );
      })}
      {(() => {
        const x = L + (steps.length + 1) * bw;
        return (
          <>
            <g className="clk" onClick={() => onDrill(allReconciled)}>
              <rect x={fix(x + 4)} y={fix(sc(m.act))} width={fix(bw - 10)} height={Math.max(0, fix(H - B - sc(m.act)))} fill="var(--chart1)" />
            </g>
            <text x={fix(x + bw / 2)} y={fix(sc(m.act) - 6)} textAnchor="middle" className="lbl">{kfmt(m.act)}</text>
            <Cat x={fix(x + bw / 2)} y={H - B + 18} text="With Circularity" />
          </>
        );
      })()}
    </svg>
  );
}

export function MixChart({ rows, onDrill }: { rows: ClosedRow[]; onDrill: OnDrill }) {
  const M = months(), R = routes();
  const W = 900, H = 260, L = 44, B = 30, T = 10, bw = (W - L) / 12;
  const by = M.map((_, i) => rows.filter((r) => r.mi === i && (r.status === 'reconciled' || r.status === 'pending')));
  const raw = Math.max(1, ...by.map((a) => a.length)), mx = Math.ceil(raw / 40) * 40, sc = (v: number) => T + (H - T - B) * (1 - v / mx);
  return (
    <>
      <svg className="ch" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Route mix by month: decisions carried out">
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line className="gl" x1={L} x2={W} y1={fix(sc(mx * f))} y2={fix(sc(mx * f))} />
            <text x={L - 6} y={fix(sc(mx * f) + 4)} textAnchor="end">{Math.round(mx * f)}</text>
          </g>
        ))}
        {by.map((a, i) => {
          let acc = 0;
          return (
            <g key={i}>
              {R.map((rt) => {
                const n = a.filter((r) => r.route === rt.id).length, y0 = sc(acc), y1 = sc(acc + n);
                acc += n;
                if (!n) return null;
                const tip = `${M[i]} · ${rt.name}: ${n} (${Math.round((n / a.length) * 100)}%)`;
                return (
                  <rect key={rt.id} className="clk" x={fix(L + i * bw + 6)} y={fix(y1)} width={fix(bw - 12)} height={fix(y0 - y1)} fill={routeColor(rt.id, rt.color)} stroke="var(--panel)" strokeWidth=".8" data-tip={tip}
                    onClick={() => onDrill({ title: rt.name + ' · ' + M[i], fn: (r) => r.route === rt.id && r.mi === i && (r.status === 'reconciled' || r.status === 'pending') })}>
                    <title>{tip}</title>
                  </rect>
                );
              })}
              <text x={fix(L + i * bw + bw / 2)} y={H - 10} textAnchor="middle">{M[i].slice(0, 3)}</text>
            </g>
          );
        })}
      </svg>
      <div className="legend">{R.map((r) => <span key={r.id}><i style={{ background: routeColor(r.id, r.color) }} />{r.short}</span>)}</div>
    </>
  );
}

export function Funnel({ rows, m, onDrill }: { rows: ClosedRow[]; m: Metrics; onDrill: OnDrill }) {
  const k = rows.length / 1400, opened = rows.length + Math.round(111 * k), ex = rows.length - m.canc - m.exp;
  const st: [string, number, string, Drill | null][] = [
    ['Cases opened', opened, 'Return signals that created a case', null],
    ['Decision approved', rows.length, 'A person approved a route', { title: 'Approved decisions', fn: () => true }],
    ['Carried out by enterprise systems', ex, 'Reported done by ERP, EAM or WMS', { title: 'Decisions carried out', fn: (r) => r.status === 'reconciled' || r.status === 'pending' }],
    ['Reconciled', m.rc.length, 'Actuals linked to the decision', { title: 'Reconciled decisions', fn: (r) => r.status === 'reconciled' }],
  ];
  return (
    <div className="an-funnel">
      {st.map((s, i) => (
        <div key={s[0]} style={{ marginBottom: 12 }}>
          <div className="row between">
            <b>{s[0]}</b>
            <span className="num"><b>{s[1].toLocaleString()}</b> {i ? <span className="note">{pct(s[1] / st[i - 1][1], 0)} of previous</span> : null}</span>
          </div>
          {s[3] ? (
            <div className="bar" style={{ height: 14, margin: '4px 0', cursor: 'pointer' }} role="button" tabIndex={0} aria-label={s[0]}
              onClick={() => onDrill(s[3]!)} onKeyDown={onActivateKey(() => onDrill(s[3]!))}>
              <i style={{ width: (s[1] / (opened || 1)) * 100 + '%' }} />
            </div>
          ) : (
            <div className="bar" style={{ height: 14, margin: '4px 0' }}>
              <i style={{ width: (s[1] / (opened || 1)) * 100 + '%' }} />
            </div>
          )}
          <div className="note">{s[2]}</div>
        </div>
      ))}
      <div className="callout info">
        <b>Not failures:</b> {m.pend} decisions are still pending, {m.canc} lost demand and {m.exp} offers expired. Pending cases stay pending until their evidence is complete.
      </div>
    </div>
  );
}

const MODEL_COL: Record<string, string> = { 'v1.0': '#9C8F84', 'v1.1': '#8A6D00', 'v1.2': '#C9B24A', 'v1.3': 'var(--chart1)' };

export function Scatter({ rows }: { rows: ClosedRow[] }) {
  const pts = rows.filter((r) => r.status === 'reconciled' && r.route !== 'exit' && r.p50 > 0 && (r.actual ?? 0) > 0 && !r.override);
  const W = 520, H = 420, L = 48, B = 40, T = 10, lo = Math.log10(15);
  const hi = Math.log10(Math.max(60000, ...pts.map((p) => Math.max(p.p50, p.actual ?? 0))));
  const x = (v: number) => L + ((Math.log10(v) - lo) / (hi - lo)) * (W - L - 10);
  const y = (v: number) => T + (H - T - B) * (1 - (Math.log10(Math.max(v, 15)) - lo) / (hi - lo));
  const f = Math.exp(1.2816 * 0.15), top = Math.pow(10, hi), ticks = [20, 100, 500, 2500, 12000, 60000].filter((t) => Math.log10(t) <= hi);
  return (
    <>
      <svg className="ch" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Predicted versus actual net value, log scale, with calibration band">
        {ticks.map((t) => (
          <g key={t}>
            <line className="gl" x1={fix(x(t))} x2={fix(x(t))} y1={T} y2={H - B} />
            <line className="gl" x1={L} x2={W - 10} y1={fix(y(t))} y2={fix(y(t))} />
            <text x={fix(x(t))} y={H - B + 14} textAnchor="middle">{kfmt(t)}</text>
            <text x={L - 6} y={fix(y(t) + 4)} textAnchor="end">{kfmt(t)}</text>
          </g>
        ))}
        <polygon points={`${x(15)},${y(15 * f)} ${x(top)},${y(top * f)} ${x(top)},${y(top / f)} ${x(15)},${y(15 / f)}`} fill="var(--yellow)" opacity=".25" />
        <line x1={x(15)} y1={y(15)} x2={x(top)} y2={y(top)} stroke="var(--ink)" strokeDasharray="4 3" />
        {pts.map((p) => <circle key={p.id} cx={x(p.p50).toFixed(1)} cy={y(p.actual ?? 0).toFixed(1)} r="2.3" fill={MODEL_COL[p.model]} opacity=".62" />)}
        <text x={(W + L) / 2} y={H - 4} textAnchor="middle">Predicted P50 (log scale)</text>
        <text transform={`translate(12 ${H / 2}) rotate(-90)`} textAnchor="middle">Actual (log scale)</text>
      </svg>
      <div className="legend">
        {modelVersions().map((m) => <span key={m.v}><i style={{ background: MODEL_COL[m.v] }} />{m.v}</span>)}
        <span><i style={{ background: 'var(--yellow)', opacity: 0.5 }} />Typical P10–P90 band</span>
      </div>
    </>
  );
}

export function ModelTable({ filtered, onFilter }: { filtered: string; onFilter: (v: string) => void }) {
  const ms = modelVersions().map((m) => ({ m, s: modelStats(m.v) }));
  return (
    <>
      <div className="tw">
        <table className="t static">
          <thead><tr><th>Version</th><th className="r">Closed</th><th className="r">Error</th><th className="r">Bias</th><th className="r">Coverage</th><th /></tr></thead>
          <tbody>
            {ms.map(({ m, s }) => (
              <tr key={m.v} style={{ cursor: 'pointer' }} tabIndex={0} {...keyAct(() => onFilter(m.v))}>
                <td><b>{m.v}</b>{filtered === m.v && <> <span className="chip y">filtered</span></>}</td>
                <td className="r num">{s?.n ?? 0}</td>
                <td className="r num">{s ? pct(s.mape, 1) : '—'}</td>
                <td className={'r num' + (s && s.bias < 0 ? ' neg' : '')}>{s ? (s.bias * 100).toFixed(1) + '%' : '—'}</td>
                <td className="r num">{s ? pct(s.cov) : '—'}</td>
                <td style={{ width: 90 }}><div className="bar"><i style={{ width: Math.min(100, (s?.cov ?? 0) * 100) + '%' }} /></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="note" style={{ marginTop: 6 }}>Target coverage for P10–P90 is 80%. Early versions were optimistic (negative bias) and too narrow.</div>
    </>
  );
}

export function Heat({ rows, onDrill }: { rows: ClosedRow[]; onDrill: OnDrill }) {
  const COMPS = components(), eq = equipmentModels();
  const cells: Record<string, { n: number; ero: number }> = {};
  rows.forEach((r) => {
    const k = r.equip + '|' + r.comp;
    (cells[k] = cells[k] || { n: 0, ero: 0 }).n++;
    cells[k].ero += r.ero;
  });
  const mx = Math.max(1, ...Object.values(cells).map((c) => (c.n >= 8 ? c.ero / c.n : 0)));
  return (
    <div className="tw">
      <div className="heat" style={{ gridTemplateColumns: `150px repeat(${COMPS.length},minmax(70px,1fr))` }}>
        <div />
        {COMPS.map((c) => <div key={c} className="hh">{c}</div>)}
        {eq.map((e) => [
          <div key={e} className="hr">{e}</div>,
          ...COMPS.map((c) => {
            const d = cells[e + '|' + c];
            if (!d || d.n < 8) return <div key={e + c} className="hc" style={{ background: 'var(--panel2)', color: 'var(--muted)' }}>n&lt;8</div>;
            const v = d.ero / d.n, a = v / mx, tip = `${e} · ${c}: ${money(v)} lost per case across ${d.n} cases`;
            return (
              <div key={e + c} className="hc clk" tabIndex={0} role="button" title={tip} data-tip={tip}
                style={{ background: `color-mix(in srgb,var(--yellow) ${Math.round(a * 100)}%,var(--panel2))`, color: '#141414', cursor: 'pointer', border: a > 0.5 ? '1.5px solid #141414' : '0' }}
                {...keyAct(() => onDrill({ title: e + ' · ' + c + ' (value erosion)', fn: (r) => r.equip === e && r.comp === c && r.ero > 0 }))}>
                <b>{money(v)}</b><span style={{ fontSize: 10.5, opacity: 0.75 }}>n={d.n}</span>
              </div>
            );
          }),
        ])}
      </div>
    </div>
  );
}

export function PoolChart({ rows }: { rows: ClosedRow[] }) {
  const M = months();
  const pr = rows.filter((r) => r.pool && r.status === 'reconciled');
  const W = 500, H = 230, L = 48, B = 30, T = 8, bw = (W - L) / 12;
  const by = M.map((_, i) => ({ g: sum(pr.filter((r) => r.mi === i).map((r) => r.pool!.g)), o: sum(pr.filter((r) => r.mi === i).map((r) => r.pool!.o)) }));
  const mx = Math.max(1, ...by.map((b) => b.o)), sc = (v: number) => T + (H - T - B) * (1 - v / mx);
  const tg = sum(pr.map((r) => r.pool!.g)), to = sum(pr.map((r) => r.pool!.o));
  return (
    <>
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="chip ok">+{kfmt(to - tg)} ({tg ? ((to / tg - 1) * 100).toFixed(1) : 0}%)</span>
        <span className="note">{pr.length} pooled decisions: per-asset greedy {kfmt(tg)} vs pool-optimized {kfmt(to)}</span>
      </div>
      <svg className="ch pool" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Pool efficiency by month">
        {[0, 0.5, 1].map((f) => (
          <g key={f}><line className="gl" x1={L} x2={W} y1={fix(sc(mx * f))} y2={fix(sc(mx * f))} /><text x={L - 6} y={fix(sc(mx * f) + 4)} textAnchor="end">{kfmt(mx * f)}</text></g>
        ))}
        {by.map((b, i) => (
          <g key={i}>
            <rect x={fix(L + i * bw + 8)} y={fix(sc(b.g))} width={fix((bw - 16) / 2)} height={fix(H - B - sc(b.g))} fill="var(--chart5)"><title>{`${M[i]} greedy ${money(b.g)}`}</title></rect>
            <rect x={fix(L + i * bw + 8 + (bw - 16) / 2)} y={fix(sc(b.o))} width={fix((bw - 16) / 2)} height={fix(H - B - sc(b.o))} fill="var(--chart1)"><title>{`${M[i]} pooled ${money(b.o)}`}</title></rect>
            <text x={fix(L + i * bw + bw / 2)} y={H - 8} textAnchor="middle">{M[i].slice(0, 3)}</text>
          </g>
        ))}
      </svg>
      <div className="legend"><span><i style={{ background: 'var(--chart5)' }} />Per-asset greedy</span><span><i style={{ background: 'var(--chart1)' }} />Pool-optimized</span></div>
    </>
  );
}

const big = (size: number): CSSProperties => ({ font: `800 ${size}px var(--f-display)` });

export function Overrides({ rows, onDrill }: { rows: ClosedRow[]; onDrill: OnDrill }) {
  const rc = rows.filter((r) => r.status === 'reconciled'), ov = rc.filter((r) => r.override);
  const by: Record<string, { n: number; d: number }> = {};
  ov.forEach((r) => {
    const k = r.override!.reason;
    (by[k] = by[k] || { n: 0, d: 0 }).n++;
    by[k].d += r.override!.delta;
  });
  const list = Object.entries(by).sort((a, b) => b[1].n - a[1].n), gained = ov.filter((r) => r.override!.delta > 0).length;
  const byM = months().map((_, i) => {
    const a = rc.filter((r) => r.mi === i);
    return a.length ? a.filter((r) => r.override).length / a.length : 0;
  });
  const W = 300, H = 70, pts = byM.map((v, i) => `${fix(i * (W / 11))},${fix(H - (v / 0.25) * H)}`).join(' ');
  return (
    <>
      <div className="row" style={{ marginBottom: 10 }}>
        <div><div className="num" style={big(30)}>{pct(ov.length / Math.max(1, rc.length), 1)}</div><div className="note">overridden ({ov.length} of {rc.length})</div></div>
        <div style={{ marginLeft: 14 }}><div className="num" style={big(30)}>{kfmt(sum(ov.map((r) => r.override!.delta)))}</div><div className="note">net effect vs recommended route (estimated)</div></div>
        <svg viewBox={`0 0 ${W} ${H + 4}`} style={{ width: 150, marginLeft: 'auto' }} aria-label="Override rate by month"><polyline points={pts} fill="none" stroke="var(--ink)" strokeWidth="2" /></svg>
      </div>
      <div className="tw">
        <table className="t static">
          <thead><tr><th>Reason</th><th className="r">Cases</th><th className="r">Net effect</th></tr></thead>
          <tbody>
            {list.length ? list.map(([k, v]) => (
              <tr key={k} className="clk" style={{ cursor: 'pointer' }} tabIndex={0} {...keyAct(() => onDrill({ title: 'Overrides · ' + k, fn: (r) => !!r.override && r.override.reason === k }))}>
                <td>{k}</td><td className="r num">{v.n}</td><td className={'r num ' + (v.d < 0 ? 'neg' : 'pos')}>{money(v.d)}</td>
              </tr>
            )) : <tr><td colSpan={3}><div className="empty">No overrides in this selection.</div></td></tr>}
          </tbody>
        </table>
      </div>
      <div className="note" style={{ marginTop: 8 }}>{gained} of {ov.length} overrides beat the recommendation. The counterfactual is the model's estimate, not an observed result.</div>
    </>
  );
}

export function Sustain({ rows }: { rows: ClosedRow[] }) {
  const rc = rows.filter((r) => r.status === 'reconciled'), me = rc.filter((r) => r.co2m != null);
  const est = sum(rc.map((r) => r.co2e)), mEst = sum(me.map((r) => r.co2e)), mMeas = sum(me.map((r) => r.co2m ?? 0));
  const per = routes().filter((x) => x.id !== 'exit').map((rt) => {
    const a = me.filter((r) => r.route === rt.id);
    return { l: rt.short, e: sum(a.map((r) => r.co2e)), m: sum(a.map((r) => r.co2m ?? 0)), n: a.length };
  });
  const mx = Math.max(1, ...per.map((p) => Math.max(p.e, p.m)));
  return (
    <>
      <div className="grid g3" style={{ marginBottom: 14 }}>
        <div><div className="num" style={big(28)}>{(est / 1000).toFixed(0)} t</div><div className="note">CO₂e avoided, <b>estimated</b>, all reconciled cases</div></div>
        <div><div className="num" style={big(28)}>{(mMeas / 1000).toFixed(0)} t</div><div className="note"><b>Measured</b> on {me.length} cases ({pct(me.length / Math.max(1, rc.length))} of reconciled)</div></div>
        <div><div className="num" style={big(28)}>{mEst ? ((mMeas / mEst - 1) * 100).toFixed(1) : 0}%</div><div className="note">Measured vs estimated on the same cases</div></div>
      </div>
      {per.map((p) => (
        <div key={p.l} className="sl" style={{ gridTemplateColumns: '110px 1fr 120px' }}>
          <span>{p.l}</span>
          <div>
            <div className="bar" style={{ marginBottom: 3 }}><i style={{ width: (p.e / mx) * 100 + '%', background: 'var(--chart5)' }} /></div>
            <div className="bar"><i style={{ width: (p.m / mx) * 100 + '%' }} /></div>
          </div>
          <span className="note num">{(p.e / 1000).toFixed(1)} → {(p.m / 1000).toFixed(1)} t</span>
        </div>
      ))}
      <div className="legend"><span><i style={{ background: 'var(--chart5)' }} />Estimated</span><span><i style={{ background: 'var(--ink)' }} />Measured</span></div>
      <div className="callout info" style={{ marginTop: 10 }}>
        <b>Baseline:</b> sell-or-scrap by separate teams, then buy new. <b>Method:</b> embodied-carbon factor by asset class × share avoided by route; measured values
        come from partner certificates and ERP movements. Estimates and measurements are never mixed in one total.{' '}
        {telemetryUnavailable() ? 'ESG telemetry is not connected, so duty-based figures are not inferred.' : ''}
      </div>
    </>
  );
}
