/** The demo's component kit (5.12) as used by Workflow Studio: same class names, so legacy.gen.css styles them. */
import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { fmtNumber } from '../../api/format';
import { statusPill } from '../../api/workflows';
import { Icon } from '../../ui/Icon';

/** Trusted markup from the demo's own icon and logo helpers (vlogo, frIt, frNodeIcon). */
export function Raw({ html }: { html: string }) {
  return <span style={{ display: 'contents' }} dangerouslySetInnerHTML={{ __html: html }} />;
}

/** Tinted icon tile (frIt). */
export function It({ ic, h = 'neutral', cls = '' }: { ic: string; h?: string; cls?: string }) {
  return (
    <span className={'frit ' + cls} style={{ '--c': `var(--h-${h})` } as CSSProperties}>
      <Icon name={ic} />
    </span>
  );
}

/** Status pill (frSt). */
export function St({ k, t }: { k: string; t?: string }) {
  const [label, cls] = statusPill(k);
  return <span className={'frst ' + cls}><i />{t ?? label}</span>;
}

/** KPI tile (frKpi). */
export function Kpi({ ic, h, v, l, sub, k }: { ic: string; h: string; v: number; l: string; sub?: string; k?: string }) {
  return (
    <div className="frkpi" data-k={k ?? ''} data-n={v}>
      <It ic={ic} h={h} />
      <span className="frkv"><b className="num">{v}</b><span className="frkl">{l}</span>{sub && <span className="note">{sub}</span>}</span>
    </div>
  );
}

/** Panel with a title (frPanel). */
export function Panel({ title, sub, right, id, cls = '', children }: { title: ReactNode; sub?: string; right?: ReactNode; id?: string; cls?: string; children: ReactNode }) {
  return (
    <section className={'panel frp ' + cls} id={id}>
      <div className="ph"><div><h3>{title}</h3>{sub && <span className="note">{sub}</span>}</div>{right}</div>
      <div className="pb">{children}</div>
    </section>
  );
}

/** Pill tabs (frSeg). */
export function Seg<T extends string>({ name, items, cur, onPick, label }: { name: string; items: [T, string][]; cur: T; onPick: (k: T) => void; label: string }) {
  // ← and → move to the previous or next tab and focus it (roving tabindex)
  const arrows = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const i = items.findIndex((x) => x[0] === cur), n = items[(i + (e.key === 'ArrowRight' ? 1 : items.length - 1)) % items.length];
    e.preventDefault();
    const box = e.currentTarget.parentElement!;
    onPick(n[0]);
    window.setTimeout(() => (box.querySelector('[aria-selected="true"]') as HTMLElement | null)?.focus(), 0);
  };
  return (
    <div className="frseg" role="tablist" aria-label={label} data-seg={name}>
      {items.map(([k, t]) => (
        <button key={k} role="tab" aria-selected={k === cur} tabIndex={k === cur ? 0 : -1} onClick={() => onPick(k)} onKeyDown={arrows}>{t}</button>
      ))}
    </div>
  );
}

/** Health ring with a legend (frRing). */
export function Ring({ segs, center, sub }: { segs: { v: number; c: string; l: string }[]; center: string; sub: string }) {
  const r = 46, c = 2 * Math.PI * r, n = segs.reduce((a, s) => a + s.v, 0) || 1;
  let off = 0;
  return (
    <div className="frring">
      <svg viewBox="0 0 120 120" width="128" height="128" role="img" aria-label={center + ' ' + sub}>
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--panel3)" strokeWidth="12" />
        {segs.map((s, i) => {
          const l = (s.v / n) * c, o = off;
          off += l;
          return s.v ? <circle key={i} cx="60" cy="60" r={r} fill="none" stroke={s.c} strokeWidth="12" strokeDasharray={`${l} ${c - l}`} strokeDashoffset={-o} transform="rotate(-90 60 60)" /> : null;
        })}
        <text x="60" y="60" textAnchor="middle" fontSize="19" fontWeight="800" fill="var(--ink)" fontFamily="var(--f-display)">{center}</text>
        <text x="60" y="77" textAnchor="middle" fontSize="10" fill="var(--ink2)">{sub}</text>
      </svg>
      <ul className="frleg">{segs.map((s, i) => <li key={i}><i style={{ background: s.c }} /><b className="num">{fmtNumber(s.v)}</b>{s.l}</li>)}</ul>
    </div>
  );
}

/** Timeline rows (frTl). */
export function Timeline({ rows, empty }: { rows: { key: string; ic: string; h: string; t: ReactNode; s?: ReactNode; x?: ReactNode; ago?: string; st?: ReactNode }[]; empty: string }) {
  if (!rows.length) return <p className="note">{empty}</p>;
  return (
    <ol className="frtl">
      {rows.map((r) => (
        <li key={r.key}>
          <It ic={r.ic} h={r.h} cls="sm" />
          <div className="frtlb"><b>{r.t}</b>{r.s && <span className="note">{r.s}</span>}{r.x && <span className="frtlx">{r.x}</span>}</div>
          <span className="frtlr">{r.ago && <span className="note num">{r.ago}</span>}{r.st}</span>
        </li>
      ))}
    </ol>
  );
}

/** Quick actions (frQa). */
export function QuickActions({ rows }: { rows: { l: string; ic: string; on: () => void }[] }) {
  return (
    <div className="frqa">
      {rows.map((r) => <button key={r.l} className="frqr" onClick={r.on}><Icon name={r.ic} /><span>{r.l}</span><Icon name="chevR" /></button>)}
    </div>
  );
}

/** ⋯ menu that closes after a choice (the demo's details.frmenu). */
export function Menu({ summary, summaryCls, label, children }: { summary: ReactNode; summaryCls: string; label?: string; children: ReactNode }) {
  return (
    // closes after a choice: a click on a menu item, which Enter and Space on that item's button also send
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions -- delegated from the items
    <details className="frmenu" onClick={(e) => {
      if ((e.target as HTMLElement).closest('[role=menuitem]')) (e.currentTarget as HTMLDetailsElement).open = false;
    }}>
      <summary className={summaryCls} aria-label={label}>{summary}</summary>
      <div className="frdd" role="menu">{children}</div>
    </details>
  );
}

/** Re-render every `ms` (live ages and runs that finish in the backend). */
export function useTick(ms = 1000): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setN((x) => x + 1), ms);
    return () => window.clearInterval(t);
  }, [ms]);
  return n;
}

/** Save a file to the viewer's computer. */
export function download(file: string, text: string, type = 'application/json') {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = file;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export const LOCK_SVG = (
  <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" />
  </svg>
);
export const GRIP_SVG = (
  <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor" aria-hidden="true">
    <circle cx="9" cy="6" r="1.7" /><circle cx="15" cy="6" r="1.7" /><circle cx="9" cy="12" r="1.7" /><circle cx="15" cy="12" r="1.7" /><circle cx="9" cy="18" r="1.7" /><circle cx="15" cy="18" r="1.7" />
  </svg>
);
