/** The Command Center's charts, drawn as JSX SVG with the demo's geometry and class names (ccSpark, ccDonut, ccBars, ccCombo …). */
import { comboData, kfmt, monthLabel, varReasons, type CcRows, type CcScope, type HealthDetail, type RouteBar, type Slice } from '../../api/command';
import { fmtNumber } from '../../api/format';

const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);

export function Spark({ s }: { s: number[] }) {
  const mx = Math.max(...s), mn = Math.min(...s), d = mx - mn || 1;
  const pts = s.map((v, i) => [(i / (s.length - 1)) * 76 + 2, 22 - ((v - mn) / d) * 18]), last = pts[pts.length - 1];
  return (
    <svg className="spk" viewBox="0 0 80 24" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts.map((p) => p.join(',')).join(' ')} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <circle cx={last[0]} cy={last[1]} r="2.4" fill="currentColor" />
    </svg>
  );
}

/** Ring chart with a clickable legend; selecting a segment toggles that filter. */
export function Donut({ items, cur, top, bottom, label, onPick }: {
  items: Slice[]; cur: string; top: string; bottom: string; label: string; onPick: (k: string) => void;
}) {
  const tot = sum(items.map((i) => i.v)) || 1, r = 52, c = 2 * Math.PI * r, pos = items.filter((i) => i.v > 0);
  let off = 0;
  const segs = pos.map((i) => {
    const l = (i.v / tot) * c, gap = pos.length > 1 ? 2.5 : 0, d = Math.max(0, l - gap), o = off;
    off += l;
    const tip = i.label + ' · ' + fmtNumber(i.v) + ' (' + Math.round((i.v / tot) * 100) + '%)';
    return (
      <circle key={i.k} className={'dseg ' + (cur === i.k ? 'on' : '')} cx="70" cy="70" r={r} fill="none" stroke={i.color} strokeWidth="18"
        strokeDasharray={`${d} ${c - d}`} strokeDashoffset={-o} transform="rotate(-90 70 70)" data-tip={tip} onClick={() => onPick(i.k)}>
        <title>{tip}</title>
      </circle>
    );
  });
  return (
    <div className="ccdn">
      <svg viewBox="0 0 140 140" role="img" aria-label={label + ': ' + items.map((i) => i.label + ' ' + i.v).join(', ')}>
        <circle cx="70" cy="70" r={r} fill="none" stroke="var(--panel3)" strokeWidth="18" />
        {segs}
        <text x="70" y="68" textAnchor="middle" fontSize="20" fontWeight="800" fill="var(--ink)" style={{ fontFamily: 'var(--f-display)' }}>{top}</text>
        <text x="70" y="86" textAnchor="middle" fontSize="11" fill="var(--ink2)">{bottom}</text>
      </svg>
      <div className="ccleg">
        {items.map((i) => (
          <button key={i.k} className={'ccli ' + (cur === i.k ? 'on' : '')} onClick={() => onPick(i.k)}>
            <i style={{ background: i.color }} />
            <span>{i.label}</span>
            <b className="num">{fmtNumber(i.v)}</b>
            <em className="num">{Math.round((i.v / tot) * 100)}%</em>
          </button>
        ))}
      </div>
    </div>
  );
}

export function RouteBars({ items, cur, label, onPick }: { items: RouteBar[]; cur: string; label: string; onPick: (k: string) => void }) {
  const mx = Math.max(1, ...items.map((i) => i.v)), tot = sum(items.map((i) => i.v)) || 1;
  return (
    <div className="ccbars" role="img" aria-label={label + ': ' + items.map((i) => i.label + ' ' + i.v).join(', ')}>
      {items.map((i) => (
        <button key={i.id} className={'ccbar ' + (cur === i.id ? 'on' : '')} onClick={() => onPick('route:' + i.id)}
          data-tip={i.label + ' · ' + fmtNumber(i.v) + ' units (' + Math.round((i.v / tot) * 100) + '%) · ' + kfmt(i.net) + ' predicted net'}>
          <span className="ccbv num">{fmtNumber(i.v)}</span>
          <span className="ccbc"><i style={{ height: Math.max(3, (i.v / mx) * 100) + '%', background: i.color }} /></span>
          <span className="ccbl">{i.label}</span>
          <span className="ccbp num">{Math.round((i.v / tot) * 100)}%</span>
        </button>
      ))}
    </div>
  );
}

export function VarList({ sc, cur, onPick }: { sc: CcScope; cur: string; onPick: (k: string) => void }) {
  return (
    <>
      {varReasons(sc).map((r) => (
        <button key={r.reason} className={'ccvr ' + (cur === r.reason ? 'on' : '')} data-tip={r.tip} onClick={() => onPick('reason:' + r.reason)}>
          <span className="ccvl">{r.reason}</span>
          <span className="ccvb"><i style={{ width: r.w + '%', background: r.color }} /></span>
          <b className="num">{r.pct}%</b>
          <span className="note num">{kfmt(r.v)}</span>
        </button>
      ))}
    </>
  );
}

/** Predicted (bars) against actual (bars) net recovery by month, with the recovery yield line. */
export function Combo({ rows, months }: { rows: CcRows; months: number }) {
  const d = comboData(rows, months), n = months;
  const P = d.map((x) => x.p), A = d.map((x) => x.a), Y = d.map((x) => x.y);
  const W = 600, H = 230, L = 46, R = 44, T0 = 14, B = 34, pw = (W - L - R) / n, mx = Math.max(1, ...P, ...A) * 1.12;
  const ymx = Math.max(120, Math.ceil(Math.max(...Y) / 20) * 20);
  const yo = (v: number) => H - B - (v / mx) * (H - B - T0), yy = (v: number) => H - B - (v / ymx) * (H - B - T0);
  const line = Y.map((v, i) => `${i ? 'L' : 'M'}${L + i * pw + pw / 2} ${yy(v)}`).join('');
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="cccombo" role="img" aria-label="Predicted versus actual net recovery by month, with recovery yield">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const y = H - B - t * (H - B - T0);
          return (
            <g key={t}>
              <line x1={L} x2={W - R} y1={y} y2={y} stroke="var(--line2)" />
              <text x={L - 6} y={y + 4} textAnchor="end" fontSize="10.5" fill="var(--muted)">{kfmt(mx * t).replace('$', '')}</text>
              <text x={W - R + 6} y={y + 4} fontSize="10.5" fill="var(--muted)">{Math.round(ymx * t)}%</text>
            </g>
          );
        })}
        {d.map((x, i) => {
          const bx = L + i * pw, bw = Math.min(18, pw * 0.32);
          const tip = monthLabel(x.mi) + ' · predicted ' + kfmt(x.p) + ', actual ' + kfmt(x.a) + ', yield ' + x.y.toFixed(0) + '%';
          return (
            <g key={x.mi} data-tip={tip}>
              <title>{tip}</title>
              <rect x={bx + pw / 2 - bw - 1} y={yo(x.p)} width={bw} height={H - B - yo(x.p)} rx="2" fill="var(--chart7)" />
              <rect x={bx + pw / 2 + 1} y={yo(x.a)} width={bw} height={H - B - yo(x.a)} rx="2" fill="var(--chart1)" />
              <text x={bx + pw / 2} y={H - 12} textAnchor="middle" fontSize="11" fill="var(--ink2)">{monthLabel(x.mi)}</text>
            </g>
          );
        })}
        <path d={line} fill="none" stroke="var(--ok)" strokeWidth="2.2" strokeLinejoin="round" />
        {Y.map((v, i) => <circle key={i} cx={L + i * pw + pw / 2} cy={yy(v)} r="3.2" fill="var(--panel)" stroke="var(--ok)" strokeWidth="2" />)}
      </svg>
      <div className="legend">
        <span><i style={{ background: 'var(--chart7)' }} />Predicted</span>
        <span><i style={{ background: 'var(--chart1)' }} />Actual</span>
        <span><i style={{ background: 'var(--ok)', height: 3, verticalAlign: 3 }} />Recovery yield (actual ÷ predicted)</span>
      </div>
    </>
  );
}

/** Integration health ring and hourly bars (the demo's smSideHTML first panel). */
export function HealthRing({ h }: { h: HealthDetail }) {
  const r = 54, c = 2 * Math.PI * r, n = h.ok + h.warn + h.bad || 1;
  let off = 0;
  const seg = (v: number, col: string) => {
    const l = (v / n) * c, o = off;
    off += l;
    return <circle key={col} cx="70" cy="70" r={r} fill="none" stroke={col} strokeWidth="16" strokeDasharray={`${l} ${c - l}`} strokeDashoffset={-o} transform="rotate(-90 70 70)" />;
  };
  const mx = Math.max(1, ...h.hours.map((b) => b.ok + b.warn + b.bad));
  return (
    <>
      <div className="hlth">
        <svg viewBox="0 0 140 140" width="132" height="132" role="img" aria-label={h.pct.toFixed(1) + ' percent healthy'}>
          <circle cx="70" cy="70" r={r} fill="none" stroke="var(--panel3)" strokeWidth="16" />
          {seg(h.ok, 'var(--ok)')}
          {seg(h.warn, '#D4A800')}
          {seg(h.bad, 'var(--bad)')}
          <text x="70" y="68" textAnchor="middle" fontSize="22" fontWeight="800" fill="var(--ink)">{h.pct.toFixed(1)}%</text>
          <text x="70" y="86" textAnchor="middle" fontSize="11" fill="var(--ink2)">Healthy</text>
        </svg>
        <div className="hleg">
          <div><i style={{ background: 'var(--ok)' }} />Successful<b className="num">{fmtNumber(h.ok)}</b></div>
          <div><i style={{ background: '#D4A800' }} />Warnings<b className="num">{fmtNumber(h.warn)}</b></div>
          <div><i style={{ background: 'var(--bad)' }} />Failures<b className="num">{fmtNumber(h.bad)}</b></div>
          <div><i style={{ background: 'var(--ink2)' }} />In progress<b className="num">{h.run}</b></div>
        </div>
      </div>
      <div className="hbars" aria-hidden="true">
        {h.hours.map((b, i) => (
          <span key={i} data-tip={String(i).padStart(2, '0') + ':00 · ' + b.ok + ' successful, ' + b.warn + ' warnings, ' + b.bad + ' failures'}>
            <i style={{ height: (b.bad / mx) * 100 + '%', background: 'var(--bad)' }} />
            <i style={{ height: (b.warn / mx) * 100 + '%', background: '#D4A800' }} />
            <i style={{ height: (b.ok / mx) * 100 + '%', background: 'var(--ok)' }} />
          </span>
        ))}
      </div>
    </>
  );
}
