/** Health ring with a legend (the demo's frRing): one arc per non-empty segment, a centre figure and a sub-line. */
import { fmtNumber } from '../../api/format';

export interface RingSegment { v: number; c: string; l: string }

export function Ring({ segs, center, sub, label }: { segs: RingSegment[]; center: string; sub?: string; label?: string }) {
  const r = 46, c = 2 * Math.PI * r, n = segs.reduce((a, s) => a + s.v, 0) || 1;
  let off = 0;
  const arcs = segs.map((s, i) => {
    const l = (s.v / n) * c;
    const e = s.v ? (
      <circle key={i} cx="60" cy="60" r={r} fill="none" stroke={s.c} strokeWidth="12" strokeDasharray={`${l} ${c - l}`} strokeDashoffset={-off} transform="rotate(-90 60 60)" />
    ) : null;
    off += l;
    return e;
  });
  return (
    <div className="frring">
      <svg viewBox="0 0 120 120" width="128" height="128" role="img" aria-label={label || center + ' ' + (sub || '')}>
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--panel3)" strokeWidth="12" />
        {arcs}
        <text x="60" y="60" textAnchor="middle" fontSize="19" fontWeight="800" fill="var(--ink)" fontFamily="var(--f-display)">{center}</text>
        <text x="60" y="77" textAnchor="middle" fontSize="10" fill="var(--ink2)">{sub || ''}</text>
      </svg>
      <ul className="frleg">
        {segs.map((s, i) => (
          <li key={i}>
            <i style={{ background: s.c }} />
            <b className="num">{fmtNumber(s.v)}</b>
            {s.l}
          </li>
        ))}
      </ul>
    </div>
  );
}
