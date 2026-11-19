/** The demo's component kit (5.12) as React: same markup and class names, so legacy.gen.css styles them unchanged. */
import { useRef, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react';
import type { Delta, Kpi, RingSeg, Status } from '../../api/home';
import { fmtNumber } from '../../api/format';
import { Icon } from '../../ui/Icon';
import { toast } from '../../ui/toast';

/** Everything that opens Ask Circularity (the agent panel) is ported separately. */
export const askSoon = () => toast('Ask Circularity arrives soon.');

const hue = (h?: string) => ({ '--c': `var(--h-${h || 'neutral'})` }) as CSSProperties;

/** Tinted icon tile (frIt). */
export const FrIt = ({ ic, h, cls }: { ic: string; h?: string; cls?: string }) => (
  <span className={'frit ' + (cls || '')} style={hue(h)}>
    <Icon name={ic} />
  </span>
);

export function FrSpark({ v, col }: { v?: number[]; col?: string }) {
  if (!v || v.length < 2) return null;
  const mn = Math.min(...v), mx = Math.max(...v), w = 72, h = 26, r = mx - mn || 1;
  const pts = v.map((x, i) => ((i / (v.length - 1)) * w).toFixed(1) + ',' + (h - 3 - ((x - mn) / r) * (h - 6)).toFixed(1)).join(' ');
  return (
    <svg className="frsp" viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <polyline points={pts} fill="none" stroke={col || 'currentColor'} strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export const FrDelta = ({ d }: { d?: Delta }) => (d ? <span className={'frd ' + d.cls} data-tip={d.tip}>{d.text}</span> : null);

/** KPI tile (frKpi): a link when it opens a list. */
export function FrKpi({ o }: { o: Kpi }) {
  const body = (
    <>
      <FrIt ic={o.ic} h={o.h} />
      <span className="frkv">
        <b className="num">{o.v}</b>
        <span className="frkl">{o.l}</span>
        {o.sub && <span className="note">{o.sub}</span>}
      </span>
      {(o.delta || o.sp) && (
        <span className="frkd">
          <FrDelta d={o.delta} />
          {o.sp && <FrSpark v={o.sp} col={`var(--h-${o.h})`} />}
        </span>
      )}
    </>
  );
  const attrs = { 'data-k': o.k || '', 'data-n': o.n == null ? '' : String(o.n) };
  return o.go ? (
    <a className="frkpi" href={'#/' + o.go} {...attrs}>{body}</a>
  ) : (
    <div className="frkpi" {...attrs}>{body}</div>
  );
}

export const FrSt = ({ s }: { s?: Status }) =>
  s ? (
    <span className={'frst ' + s.tone}>
      <i />
      {s.label}
    </span>
  ) : null;

/** Pill tabs (frSeg) with arrow-key movement. items: [id, label, icon?] */
export function FrSeg({ name, items, cur, onPick, label }: { name: string; items: [string, string, string?][]; cur: string; onPick: (id: string) => void; label?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const key = (e: KeyboardEvent, i: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const n = (i + (e.key === 'ArrowRight' ? 1 : items.length - 1)) % items.length;
    (ref.current?.querySelectorAll('[role=tab]')[n] as HTMLElement | undefined)?.focus();
    onPick(items[n][0]);
  };
  return (
    <div ref={ref} className="frseg" role="tablist" aria-label={label || name} data-seg={name}>
      {items.map((x, i) => (
        <button key={x[0]} role="tab" aria-selected={x[0] === cur} tabIndex={x[0] === cur ? 0 : -1} onClick={() => onPick(x[0])} onKeyDown={(e) => key(e, i)}>
          {x[2] && <Icon name={x[2]} />}
          {x[1]}
        </button>
      ))}
    </div>
  );
}

/** Panel (frPanel). */
export const FrPanel = ({ title, sub, right, id, cls, children }: { title: ReactNode; sub?: ReactNode; right?: ReactNode; id?: string; cls?: string; children: ReactNode }) => (
  <section className={'panel frp ' + (cls || '')} id={id}>
    <div className="ph">
      <div>
        <h3>{title}</h3>
        {sub != null && <span className="note">{sub}</span>}
      </div>
      {right}
    </div>
    <div className="pb">{children}</div>
  </section>
);

/** Page header (frHead). */
export const FrHead = ({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) => (
  <div className="phead frph">
    <div>
      <h1>{title}</h1>
      {sub && <p>{sub}</p>}
    </div>
    {right && <div className="row">{right}</div>}
  </div>
);

/** Attention card (frAttn). */
export const FrAttn = ({ head, line, btn, onClick }: { head: string; line: string; btn?: string; onClick?: () => void }) => (
  <div className="frattn" role="status">
    <Icon name="alert" />
    <div>
      <b>{head}</b>
      <p>{line}</p>
      {btn && (
        <button className="btn sm" onClick={onClick}>
          {btn} →
        </button>
      )}
    </div>
  </div>
);

/** Health ring with legend (frRing). */
export function FrRing({ segs, center, sub, label }: { segs: RingSeg[]; center: string; sub?: string; label?: string }) {
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

/** Timeline (frTl). */
export interface TlRow { key: string; ic: string; h: string; t: ReactNode; s?: ReactNode; x?: ReactNode; ago?: string; st?: ReactNode; cls?: string }
export function FrTl({ rows, empty, cls }: { rows: TlRow[]; empty?: string; cls?: string }) {
  if (!rows.length) return <p className="note">{empty || 'Nothing yet.'}</p>;
  return (
    <ol className={'frtl' + (cls ? ' ' + cls : '')}>
      {rows.map((r) => (
        <li key={r.key} className={r.cls}>
          <FrIt ic={r.ic} h={r.h} cls="sm" />
          <div className="frtlb">
            <b>{r.t}</b>
            {r.s && <span className="note">{r.s}</span>}
            {r.x && <span className="frtlx">{r.x}</span>}
          </div>
          <span className="frtlr">
            {r.ago && <span className="note num">{r.ago}</span>}
            {r.st}
          </span>
        </li>
      ))}
    </ol>
  );
}
