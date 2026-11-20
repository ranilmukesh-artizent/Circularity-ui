/* Connection Fabric component kit: the demo's frIt, frSt, frKpi, frSeg, vlogo, status chips, the row menu and an action toast. */
import { createContext, useContext, useEffect, useReducer, useRef, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from 'react';
import { fmtNumber } from '../../api/format';
import { hashId, journeyStep, recordTest, sources, vendorInitials, vHue, type Source } from '../../api/integration';
import { can } from '../../api/session';
import { Icon } from '../../ui/Icon';

export const canMgr = () => can('manageIntegrations');
export const NOMGR = 'Only the Developer or Admin changes integrations.';
export const fmtN = (n: number) => fmtNumber(n);
export const when = (ts: number | string | Date) =>
  new Date(ts).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
export const plural = (n: number, w: string, p = w + 's') => n + ' ' + (n === 1 ? w : p);
export const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);

/** The vendor's logo tile (the demo's vlogo). */
export const Vlogo = ({ vendor }: { vendor: string }) => (
  <span className="vlogo" style={{ '--h': vHue(vendor) } as CSSProperties} aria-hidden="true">{vendorInitials(vendor)}</span>
);
/** A journey step chip (the demo's stp). */
export function Stp({ n }: { n: number }) {
  const j = journeyStep(n);
  return (
    <span className={'stp ' + (j.kind === 'built' ? '' : j.kind)} title={'Journey step ' + j.n + ': ' + j.label + ' — ' + j.desc}>
      <b>{j.n}</b>
      {j.label}
    </span>
  );
}

/** Highlighted JSON (the demo's jsonHtml): keys, string and number values. */
export function Json({ value }: { value: unknown }) {
  const text = JSON.stringify(value, null, 2) ?? '';
  const out: ReactNode[] = [];
  const re = /"([^"]+?)":|(?<=: )"(.*?)"|(?<=: )(-?\d+(?:\.\d+)?)/g;
  let at = 0, m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    out.push(text.slice(at, m.index));
    if (m[1] !== undefined) out.push(<span key={m.index} className="k">"{m[1]}"</span>, ':');
    else if (m[2] !== undefined) out.push(<span key={m.index} className="s">"{m[2]}"</span>);
    else out.push(<span key={m.index} className="n">{m[3]}</span>);
    at = m.index + m[0].length;
  }
  out.push(text.slice(at));
  return <>{out}</>;
}

export function FrIt({ ic, h, cls }: { ic: string; h?: string; cls?: string }) {
  return (
    <span className={'frit ' + (cls ?? '')} style={{ '--c': `var(--h-${h || 'neutral'})` } as CSSProperties}>
      <Icon name={ic} />
    </span>
  );
}

const FR_ST: Record<string, [string, string]> = {
  completed: ['Completed', 'ok'], success: ['Success', 'ok'], published: ['Published', 'ok'], connected: ['Connected', 'ok'], live: ['Live', 'ok'], healthy: ['Healthy', 'ok'],
  progress: ['In progress', 'info'], running: ['Running', 'info'], syncing: ['Syncing', 'info'], investigating: ['Investigating', 'warn'], action: ['Action required', 'warn'],
  attention: ['Needs attention', 'warn'], stale: ['Stale', 'warn'], paused: ['Paused', 'warn'], warning: ['Warning', 'warn'], expiring: ['Expiring', 'warn'],
  failed: ['Failed', 'bad'], failing: ['Failing', 'bad'], unavailable: ['Not connected', 'bad'], escalated: ['Escalated', 'bad'], draft: ['Draft', 'line'],
  available: ['Available', 'line'], disconnected: ['Disconnected', 'line'], manual: ['Manual import', 'line'], ack: ['Acknowledged', 'line'], open: ['Open', 'warn'],
};
export function FrSt({ k, t }: { k: string; t?: string | null }) {
  const s = FR_ST[k] ?? [k, 'line'];
  return (
    <span className={'frst ' + s[1]}>
      <i />
      {t || s[0]}
    </span>
  );
}

/** The older status chip (stChip). */
export function StChip({ s }: { s: string }) {
  const m: Record<string, [string, string]> = { live: ['ok', 'Live'], manual: ['dk', 'Manual import'], unavailable: ['bad', 'Unavailable'], stale: ['warn', 'Stale'] };
  const c = m[s];
  return c ? <span className={'chip ' + c[0]}>{c[1]}</span> : null;
}

export function FrSpark({ v, col }: { v: number[]; col: string }) {
  if (!v || v.length < 2) return null;
  const mn = Math.min(...v), mx = Math.max(...v), w = 72, h = 26, r = mx - mn || 1;
  const pts = v.map((x, i) => ((i / (v.length - 1)) * w).toFixed(1) + ',' + (h - 3 - ((x - mn) / r) * (h - 6)).toFixed(1)).join(' ');
  return (
    <svg className="frsp" viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <polyline points={pts} fill="none" stroke={col} strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function FrDelta({ cur, prev, goodUp }: { cur: number; prev: number; goodUp: boolean | null }) {
  if (prev == null || !isFinite(prev) || prev === 0 || cur == null) return null;
  const p = ((cur - prev) / Math.abs(prev)) * 100;
  if (!isFinite(p)) return null;
  const up = p >= 0, good = goodUp == null ? '' : up === goodUp ? 'good' : 'bad';
  return (
    <span className={'frd ' + good} data-tip="Against the same measure 30 days earlier">
      {up ? '▲' : '▼'} {Math.abs(p) < 10 ? Math.abs(p).toFixed(1) : Math.abs(p).toFixed(0)}%
    </span>
  );
}

export function FrKpi({ ic, h, v, l, sub, d, sp, k }: { ic: string; h: string; v: ReactNode; l: string; sub?: string; d?: ReactNode; sp?: number[]; k?: string }) {
  return (
    <div className="frkpi" data-k={k ?? ''}>
      <FrIt ic={ic} h={h} />
      <span className="frkv">
        <b className="num">{v}</b>
        <span className="frkl">{l}</span>
        {sub && <span className="note">{sub}</span>}
      </span>
      {(d || sp) && (
        <span className="frkd">
          {d}
          {sp && <FrSpark v={sp} col={`var(--h-${h})`} />}
        </span>
      )}
    </div>
  );
}

export function FrSeg<T extends string>({ items, cur, onPick, label }: { items: [T, string, string?][]; cur: T; onPick: (v: T) => void; label: string }) {
  return (
    <div className="frseg" role="tablist" aria-label={label}>
      {items.map(([k, l, ic]) => (
        <button key={k} role="tab" aria-selected={k === cur} tabIndex={k === cur ? 0 : -1} onClick={() => onPick(k)}>
          {ic && <Icon name={ic} />}
          {l}
        </button>
      ))}
    </div>
  );
}

export function FrPanel({ title, sub, right, cls, children }: { title: ReactNode; sub?: string; right?: ReactNode; cls?: string; children: ReactNode }) {
  return (
    <section className={'panel frp ' + (cls ?? '')}>
      <div className="ph">
        <div>
          <h3>{title}</h3>
          {sub && <span className="note">{sub}</span>}
        </div>
        {right}
      </div>
      <div className="pb">{children}</div>
    </section>
  );
}

/** Re-render on a timer while the page is open: ages tick and syncs progress inside the engine. */
export function useTick(ms: number) {
  const [, force] = useReducer((x: number) => x + 1, 0);
  useEffect(() => {
    const t = window.setInterval(force, ms);
    return () => window.clearInterval(t);
  }, [ms]);
}

/* ---- connection test (5.10): DNS, TLS, auth, permissions, sample read ---- */
export interface TestState { i: number; res: { ok: boolean; msg: string }[]; done: boolean; ok?: boolean; at: number }
let tests: Record<string, TestState> = {};
const tSubs = new Set<() => void>();
const tEmit = () => { tests = { ...tests }; tSubs.forEach((f) => f()); };
export const useTests = () => useSyncExternalStore((f) => (tSubs.add(f), () => tSubs.delete(f)), () => tests);
const FR_TEST: [string, string][] = [['DNS', 'Resolve host'], ['TLS', 'Handshake and certificate'], ['Auth', 'Authenticate'], ['Permissions', 'Check read scopes'], ['Sample read', 'Read a sample record']];
const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export function runTest(s: Pick<Source, 'id' | 'vendor' | 'status' | 'auth' | 'read'> & { url?: string }, done?: (ok: boolean) => void) {
  const h = (k: string) => parseInt(hashId(k), 16);
  const host = (s.url || '').replace(/^[a-z]+:\/\//, '').split('/')[0] || s.vendor, res: TestState['res'] = [];
  const t: TestState = { i: 0, res, done: false, at: Date.now() };
  tests[s.id] = t;
  const msg = [
    () => host + ' → 10.' + (h(s.id) % 200) + '.' + (h(s.id + 'b') % 250) + '.' + (h(s.id + 'c') % 250),
    () => 'TLS 1.3 · certificate valid',
    () => (s.status === 'stale' ? 'Token rejected: expired' : s.auth),
    () => plural((s.read || []).length, 'read scope') + ' granted',
    () => '1 record in ' + (120 + (h(s.id + 't') % 300)) + ' ms',
  ];
  const step = () => {
    const i = t.i, fail = (s.status === 'unavailable' && i === 0) || (s.status === 'stale' && i === 2);
    res.push({ ok: !fail, msg: fail && i === 0 ? 'No route to host: the system is not provisioned' : msg[i]() });
    t.i++;
    if (fail || t.i >= FR_TEST.length) {
      t.done = true; t.ok = !fail; t.at = Date.now();
      tEmit();
      recordTest(s, !!t.ok, FR_TEST[i][0]);
      done?.(!!t.ok);
      return;
    }
    tEmit();
    window.setTimeout(step, reduced() ? 0 : 260);
  };
  tEmit();
  window.setTimeout(step, reduced() ? 0 : 200);
}

export function TestSteps({ id }: { id: string }) {
  const t = useTests()[id];
  if (!t) return null;
  return (
    <>
      <ol className="frtest">
        {FR_TEST.map((x, i) => {
          const r = t.res[i];
          return (
            <li key={x[0]} className={r ? (r.ok ? 'ok' : 'bad') : i === t.i ? 'run' : ''}>
              <span className="frtd">{r ? (r.ok ? '✓' : '✕') : i === t.i ? '…' : ''}</span>
              <b>{x[0]}</b>
              <span className="note">{r ? r.msg : x[1]}</span>
            </li>
          );
        })}
      </ol>
      {t.done && (
        <p className="note">
          {t.ok ? 'Connection test passed' : 'Connection test failed'} · {new Date(t.at).toTimeString().slice(0, 8)}
        </p>
      )}
    </>
  );
}

/* ---- toast with an action button (the demo's toastAct) ---- */
type ActT = { id: number; msg: string; label: string; fn: () => void };
let acts: ActT[] = [];
let aSeq = 0;
const aSubs = new Set<() => void>();
const aEmit = () => aSubs.forEach((f) => f());
export function toastAct(msg: string, label: string, fn: () => void, ms = 8000) {
  const t = { id: ++aSeq, msg, label, fn };
  acts = [...acts, t];
  aEmit();
  window.setTimeout(() => { acts = acts.filter((x) => x !== t); aEmit(); }, ms);
}
export function ActToasts() {
  const list = useSyncExternalStore((f) => (aSubs.add(f), () => aSubs.delete(f)), () => acts);
  if (!list.length) return null;
  return (
    <div className="toasts" aria-live="polite" style={{ bottom: 70 }}>
      {list.map((t) => (
        <div key={t.id} className="toast act" role="status">
          <span>{t.msg} </span>
          <button className="toastbtn" onClick={() => { acts = acts.filter((x) => x !== t); aEmit(); t.fn(); }}>
            {t.label}
          </button>
        </div>
      ))}
    </div>
  );
}

/* ---- page-wide controls (drawers and dialogs live in the page dispatcher) ---- */
export interface IntUI {
  openSource: (id: string, tab?: string) => void;
  addSource: (cat: string) => void;
  sync: (id: string) => void;
  pause: (id: string) => void;
  disconnect: (id: string) => void;
  reconnect: (id: string) => void;
  remove: (id: string) => void;
  rotate: (id: string) => void;
  connect: (catId: string) => void;
  reauth: (id: string) => void;
  newIntegration: () => void;
  test: (id: string) => void;
  openEvent: (id: string) => void;
  go: (path: string) => void;
}
export const IntCtx = createContext<IntUI | null>(null);
export const useInt = () => useContext(IntCtx)!;

/** The ⋯ menu of a source row (frSrcMenu); read-only roles see a View button. */
export function SrcMenu({ s }: { s: Source }) {
  const ui = useInt();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!open) return;
    const f = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('click', f);
    return () => document.removeEventListener('click', f);
  }, [open]);
  if (!canMgr()) return <button className="btn sm" onClick={() => ui.openSource(s.id, 'ov')}>View</button>;
  const item = (ic: string, l: string, f: () => void, dis?: boolean) => (
    <button role="menuitem" disabled={dis} onClick={() => { setOpen(false); f(); }}>
      <Icon name={ic} />
      <span>{l}</span>
    </button>
  );
  return (
    <details ref={ref} className="frmenu" open={open}>
      <summary className="iconbtn sm" aria-label={'Actions for ' + s.vendor} onClick={(e) => { e.preventDefault(); setOpen((o) => !o); }}>
        <Icon name="more" />
      </summary>
      <div className="frdd" role="menu">
        {item('eye', 'Open', () => ui.openSource(s.id, 'ov'))}
        {s.status === 'unavailable' ? (
          item('unplug', s.disconnected ? 'Reconnect' : 'Connect', () => ui.reconnect(s.id))
        ) : (
          <>
            {item('sync', 'Sync now', () => ui.sync(s.id), !!(s.syncing || s.paused || s.status === 'manual'))}
            {item(s.paused ? 'play' : 'pause', s.paused ? 'Resume' : 'Pause', () => ui.pause(s.id))}
            {item('unplug', 'Disconnect', () => ui.disconnect(s.id))}
          </>
        )}
      </div>
    </details>
  );
}

export const anySyncing = () => sources().some((s) => s.syncing);
