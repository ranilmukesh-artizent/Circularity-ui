/** Audit & provenance (#/audit/log, #/audit/gaps): the demo's renderAudit, its entry drawers, the data trace and comments. */
import { Fragment, useCallback, useEffect, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ackKind, auditEntries, auditGaps, comments, eventJson, isoT, postComment, provenanceOf, type AuditEntry, type Provenance,
} from '../../api/audit';
import { fmtDateYear } from '../../api/format';
import { useBackend } from '../../api/hooks';
import { can, canRoute } from '../../api/session';
import type { PageProps } from '../registry';
import { Drawer, Modal } from '../../ui/Overlay';
import { toast } from '../../ui/toast';
import { anchor } from '../analytics/AnalyticsPage';
import { downloadCsv, q } from './csv';

interface AuFilter { q: string; src: string; type: string; status: string; dir: 1 | -1; limit: number; prep: boolean }
const EMPTY: AuFilter = { q: '', src: '', type: '', status: '', dir: -1, limit: 40, prep: false };
let saved: AuFilter = { ...EMPTY };

const PU = <span className="chip bad" style={{ height: 'auto', padding: '1px 8px' }}>Provenance unavailable</span>;
const fv = (v: unknown): ReactNode => (v == null || v === '' ? PU : String(v));
const stC = (s: AuditEntry['status']) =>
  ({ available: <span className="chip ok">Full</span>, partial: <span className="chip warn">Partial</span>, recorded: <span className="chip line">System event</span> })[s];
export const provChip = (p: Provenance) =>
  p.status === 'available' ? <span className="chip ok">Full provenance</span> : p.status === 'partial' ? <span className="chip warn">Partial provenance</span> : <span className="chip bad">Provenance unavailable</span>;
const canOpen = (id: string) => canRoute({ page: 'product', a: id, b: null }) === true;

function filtered(f: AuFilter): AuditEntry[] {
  let a = auditEntries();
  if (f.q) { const s = f.q.toLowerCase(); a = a.filter((x) => (x.caseId + ' ' + x.asset + ' ' + x.item + ' ' + x.source + ' ' + x.request + ' ' + x.used).toLowerCase().includes(s)); }
  if (f.src) a = a.filter((x) => x.source === f.src);
  if (f.type) a = a.filter((x) => x.kind === f.type);
  if (f.status) a = a.filter((x) => x.status === f.status);
  if (f.prep) a = a.filter((x) => x.prep);
  return a.sort((x, y) => (+x.ts - +y.ts) * f.dir);
}

export function AuditPage({ route, query }: PageProps) {
  useBackend();
  const [f, setF0] = useState<AuFilter>(() => {
    const qq = query.get('q') ?? query.get('case');
    return qq ? (saved = { ...saved, q: qq, limit: 40 }) : saved;
  });
  // `saved` always holds the current filter (every change goes through setF), so effects read it instead of `f`
  const setF = useCallback((x: AuFilter) => { saved = x; setF0(x); }, []);
  const [entry, setEntry] = useState<string | null>(null);
  const [trace, setTrace] = useState<{ id: string; k: string } | null>(null);

  // a ?q= / ?case= in the address (a link from another page) replaces the search, only when the address changes
  const qs = query.toString();
  useEffect(() => {
    const p = new URLSearchParams(qs);
    const qq = p.get('q') ?? p.get('case');
    if (qq && qq !== saved.q) setF({ ...saved, q: qq, limit: 40 });
  }, [qs, setF]);
  useEffect(() => {
    if (!route.a) return;
    const t = window.setTimeout(() => anchor(document.getElementById(route.a === 'gaps' ? 'auGaps' : 'auLog')), 30);
    return () => window.clearTimeout(t);
  }, [route.a]);

  const every = auditEntries(), all = filtered(f), gaps = auditGaps(), shown = all.slice(0, f.limit);
  const src = [...new Set(every.map((x) => x.source))].sort();
  const fetches = all.filter((x) => x.kind === 'fetch').length;
  const exportCsv = () => {
    downloadCsv(
      'timestamp_utc,source,case,item,request,result,used_in,provenance\n' +
        all.map((x) => [x.ts.toISOString(), x.source, x.caseId, x.item, x.request, x.result, x.used, x.status].map(q).join(',')).join('\n'),
      'audit-log.csv',
    );
    toast('Exported ' + all.length + ' entries');
  };
  let lastDay = '';

  return (
    <>
      <div className="phead">
        <div>
          <h1>Audit &amp; provenance</h1>
          <p>A chronological record of what data was fetched, from exactly which source, when, with what request, and where it was used. Select any entry for its full provenance.</p>
        </div>
        <div className="row"><button className="btn" onClick={exportCsv}>Export log (CSV)</button></div>
      </div>
      <div className="grid g4" style={{ marginBottom: 14 }}>
        {([[all.length.toLocaleString(), 'audit entries in view'], [fetches.toLocaleString(), 'data fetches recorded'], [every.filter((x) => x.status === 'partial').length, 'with partial provenance'], [gaps.length, 'evidence gaps with no provenance']] as const).map((x) => (
          <div key={x[1]} className="panel flat" style={{ padding: 12 }}><div className="num" style={{ font: '800 24px var(--f-display)' }}>{x[0]}</div><div className="note">{x[1]}</div></div>
        ))}
      </div>
      <div className="panel" id="auLog">
        <div className="filters">
          <input type="search" placeholder="Search case, asset, source, request or where used" aria-label="Search audit log" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, limit: 40 })} />
          <select className="sel" aria-label="Source" value={f.src} onChange={(e) => setF({ ...f, src: e.target.value })}>
            <option value="">All sources</option>
            {src.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="sel" aria-label="Entry type" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>
            <option value="">All entries</option><option value="fetch">Data fetches</option><option value="event">Instructions and events</option>
          </select>
          <select className="sel" aria-label="Provenance" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
            <option value="">Any provenance</option><option value="available">Full</option><option value="partial">Partial</option><option value="recorded">System events</option>
          </select>
          <button className="btn sm" onClick={() => setF({ ...f, dir: f.dir < 0 ? 1 : -1 })}>{f.dir < 0 ? 'Newest first' : 'Oldest first'}</button>
          <button className="btn ghost sm" onClick={() => setF({ ...EMPTY })}>Clear</button>
          <label className="tog"><input type="checkbox" checked={f.prep} onChange={(e) => setF({ ...f, prep: e.target.checked })} /> Prepared by agent</label>
        </div>
        <div className="tw" style={{ maxHeight: 640, overflow: 'auto' }}>
          <table className="t">
            <thead><tr><th>Fetched / recorded (UTC)</th><th>Source</th><th>Case · item</th><th>Request / query</th><th>Result</th><th>Where it was used</th><th>Provenance</th></tr></thead>
            <tbody>
              {shown.length ? shown.map((x) => {
                const d = x.ts.toISOString().slice(0, 10), sep = d !== lastDay;
                if (sep) lastDay = d;
                const n = comments('au:' + x.id).length;
                return (
                  <Fragment key={x.id}>
                    {sep && <tr style={{ cursor: 'default' }}><td colSpan={7} style={{ background: 'var(--panel2)', fontWeight: 600, padding: '6px 12px' }}>{fmtDateYear(x.ts)}</td></tr>}
                    <tr tabIndex={0} onClick={() => setEntry(x.id)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setEntry(x.id))}>
                      <td className="num nowrap">{x.ts.toISOString().slice(11, 19)}</td>
                      <td>{x.source}</td>
                      <td><b>{x.caseId}</b><div className="note">{x.item}</div></td>
                      <td className="mono" style={{ maxWidth: 260, wordBreak: 'break-all' }}>{x.request}</td>
                      <td>{x.result}</td>
                      <td style={{ maxWidth: 240 }}>{x.used}</td>
                      <td>{stC(x.status)}{n > 0 && <> <span className="chip line">{n} comment{n > 1 ? 's' : ''}</span></>}</td>
                    </tr>
                  </Fragment>
                );
              }) : <tr><td colSpan={7}><div className="empty"><b>No entries match</b>Clear the filters to see the whole log.</div></td></tr>}
            </tbody>
          </table>
        </div>
        <div className="filters" style={{ borderTop: '1px solid var(--line2)', borderBottom: 0, justifyContent: 'space-between' }}>
          <span className="note">Showing {shown.length} of {all.length}. Entries are read-only; retraining never rewrites them.</span>
          {all.length > shown.length && <button className="btn sm" onClick={() => setF({ ...f, limit: f.limit + 40 })}>Show 40 more</button>}
        </div>
      </div>
      <div className="sect" id="auGaps">
        <div className="sh"><h2>Evidence gaps</h2><span className="note">No fetch is recorded for these, so no provenance is shown</span></div>
        <div className="panel">
          <div className="tw">
            <table className="t static">
              <thead><tr><th>Case</th><th>Missing evidence</th><th>Expected source</th><th>Provenance</th></tr></thead>
              <tbody>
                {gaps.length ? gaps.slice(0, 12).map((g) => (
                  <tr key={g.c.id + g.e.k} style={{ cursor: 'pointer' }} tabIndex={0} onClick={() => setTrace({ id: g.c.id, k: g.e.k })}
                    onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setTrace({ id: g.c.id, k: g.e.k }))}>
                    <td><b>{g.c.id}</b></td><td>{g.e.label}</td><td>{g.e.source}</td><td>{PU}</td>
                  </tr>
                )) : <tr><td colSpan={4}><div className="empty">No gaps in this view.</div></td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      {entry && <EntryDrawer id={entry} onClose={() => setEntry(null)} onTrace={(id, k) => setTrace({ id, k })} />}
      {trace && <DataTrace caseId={trace.id} k={trace.k} onClose={() => setTrace(null)} />}
    </>
  );
}

export function ProvTable({ p }: { p: Provenance }) {
  if (p.status === 'unavailable') return <div className="callout bad"><b>Provenance unavailable.</b> {p.reason}</div>;
  const rows: [string, unknown][] = [
    ['Source system', p.sourceName + ' (' + p.vendor + ')'], ['Access', p.auth + ' · ' + p.mode], ['File name / path', p.file], ['Table / sheet', p.table], ['Column', p.column],
    ['Row / record', p.record ? `${p.record} (row ${(p.row ?? 0).toLocaleString()} of ${(p.rowsTotal ?? 0).toLocaleString()})` : null], ['Exact value', p.value],
    ['Exact fetch timestamp', p.fetchedAt && isoT(p.fetchedAt)], ['Observed at source', p.observedAt && isoT(p.observedAt)], ['Request / query', p.request], ['Payload checksum', p.file ? p.checksum : null],
  ];
  return (
    <>
      <table className="t static">
        <tbody>
          {rows.map((r) => (
            <tr key={r[0]}><td style={{ width: 170, color: 'var(--muted)' }}>{r[0]}</td><td className={/path|query|checksum|Column|Table/.test(r[0]) ? 'mono' : undefined}>{fv(r[1])}</td></tr>
          ))}
        </tbody>
      </table>
      {p.partialWhy && <div className="note" style={{ marginTop: 6 }}>{p.partialWhy}</div>}
      {(p.notes ?? []).map((n) => <div key={n} className="callout" style={{ marginTop: 8 }}>{n}</div>)}
    </>
  );
}

/** Comments on an audit entry (the demo's cmHTML): Finance, Developer and Admin post; everyone who sees the entry reads. */
function Comments({ k, label }: { k: string; label: string }) {
  const l = comments(k);
  const [text, setText] = useState('');
  const [err, setErr] = useState('');
  const post = async () => {
    const r = await postComment(k, text.trim());
    if (!r.ok) { setErr(r.error.message); return; }
    setText(''); setErr('');
    toast('Comment posted.');
  };
  return (
    <div className="cmbox">
      <h4 style={{ margin: '18px 0 6px' }}>Comments <span className="note">{l.length}</span></h4>
      {l.length ? l.map((c, i) => (
        <div key={i} className="cmi"><div className="row" style={{ gap: 8 }}><b>{c.by}</b><span className="note num">{isoT(c.at)}</span></div><div className="cmt">{c.text}</div></div>
      )) : <div className="note">No comments yet.</div>}
      {can('comment') ? (
        <>
          <div className="fld" style={{ margin: '10px 0 8px' }}>
            <label htmlFor="cmText">Add a comment</label>
            <textarea id="cmText" maxLength={500} placeholder={`Visible to everyone who can see this ${label}.`} value={text} onChange={(e) => setText(e.target.value)} />
            <div className="hint">Do not enter personal data.</div>
            <div className="err" role="alert" hidden={!err}>{err}</div>
          </div>
          <button className="btn sm pri" onClick={post}>Post comment</button>
        </>
      ) : <div className="note" style={{ marginTop: 8 }}>Finance, Developer and Admin can comment here.</div>}
    </div>
  );
}

function EntryDrawer({ id, onClose, onTrace }: { id: string; onClose: () => void; onTrace: (id: string, k: string) => void }) {
  const nav = useNavigate();
  const x = auditEntries().find((e) => e.id === id);
  useEffect(() => { if (!x) { toast('Entry not found'); onClose(); } }, [x, onClose]);
  if (!x) return null;
  if (x.kind === 'event' && x.ev) {
    const e = x.ev;
    const open = e.caseId && e.caseId !== '—' && canOpen(e.caseId);
    return (
      <Drawer wide title={e.type} sub={e.id} onClose={onClose} foot={open ? <button className="btn" onClick={() => nav('/product/' + e.caseId)}>Open {e.caseId}</button> : undefined}>
        <div className="row" style={{ marginBottom: 10 }}>
          <span className={'chip ' + (e.dir === 'out' ? 'dk' : 'line')}>{e.dir === 'out' ? 'Outbound' : 'Inbound'}</span>
          <span className={'chip ' + ackKind(e.ack)}>{e.ack}</span>
        </div>
        {e.note && <div className="callout" style={{ marginBottom: 12 }}>{e.note}</div>}
        <table className="t static">
          <tbody>
            {([['Recorded at', isoT(e.ts)], ['Recorded by', e.by], ['Destination / source', e.dest], ['Case', e.caseId], ['Decision', e.decisionId], ['Approval reference', e.approval], ['Instruction version', e.ver], ['Idempotency key', e.key]] as [string, unknown][]).map((r) => (
              <tr key={r[0]}><td style={{ width: 170, color: 'var(--muted)' }}>{r[0]}</td><td>{fv(r[1] && r[1] !== '—' ? r[1] : null)}</td></tr>
            ))}
          </tbody>
        </table>
        <h4 style={{ margin: '16px 0 6px' }}>Raw event</h4>
        <pre className="code">{eventJson(e)}</pre>
        <Comments k={'au:' + x.id} label="audit entry" />
      </Drawer>
    );
  }
  const p = x.p!;
  return (
    <Drawer wide title={x.item} sub={`${x.caseId} · ${x.asset} · ${isoT(x.ts)}`} onClose={onClose}
      foot={<>
        <button className="btn pri" onClick={() => onTrace(x.caseId, x.key)}>View Data Trace</button>
        {canOpen(x.caseId) && <button className="btn" onClick={() => nav('/product/' + x.caseId)}>Open {x.caseId}</button>}
      </>}>
      <div className="row" style={{ marginBottom: 12 }}>{provChip(p)}<span className="chip line">{p.id}</span></div>
      <h4 style={{ marginBottom: 6 }}>Provenance</h4>
      <ProvTable p={p} />
      <h4 style={{ margin: '18px 0 6px' }}>Processing</h4>
      <ol style={{ margin: 0, paddingLeft: 18 }}>{(p.processing ?? []).map((s) => <li key={s}>{s}</li>)}</ol>
      <h4 style={{ margin: '18px 0 6px' }}>Where this data was used</h4>
      <ul style={{ margin: 0, paddingLeft: 18 }}>{p.usedIn.map((s) => <li key={s}>{s}</li>)}</ul>
      <Comments k={'au:' + x.id} label="audit entry" />
    </Drawer>
  );
}

/** The demo's data trace dialog: source → file → table → row → data → fetch time → processing → evidence. */
export function DataTrace({ caseId, k, onClose }: { caseId: string; k: string; onClose: () => void }) {
  const r = provenanceOf(caseId, k);
  if (!r) return null;
  const { c, ev: e, p } = r;
  const U = p.status === 'unavailable', noF = U || !p.file;
  const node = (n: number, t: string, body: ReactNode, miss: boolean) => (
    <li key={n} className={'tn ' + (miss ? 'miss' : '')}><span className="tnum">{n}</span><b>{t}</b><div>{body}</div></li>
  );
  const exportRecord = () => {
    const o: Record<string, unknown> = {
      provenance_id: p.id, case: caseId, item: p.label, source: p.sourceName, file: p.file, table: p.table, column: p.column, record: p.record, value: p.value,
      fetched_at: p.fetchedAt ? new Date(p.fetchedAt).toISOString() : null, request: p.request, checksum: p.checksum,
    };
    downloadCsv('field,value\n' + Object.entries(o).map(([a, b]) => `${a},${q(b == null ? 'Provenance unavailable' : b)}`).join('\n'), `provenance-${p.id}.csv`);
    toast('Exported ' + p.id);
  };
  return (
    <Modal wide title={'Data trace · ' + e.label} onClose={onClose}
      foot={<>{!U && <button className="btn" onClick={exportRecord}>Export record</button>}<button className="btn" onClick={onClose}>Close</button></>}>
      <p className="ink2" style={{ marginTop: 0 }}>
        {c.id} · {c.assetId}. Each step is recorded by the Connection Fabric; a step with no record is shown as unavailable and is never inferred. {provChip(p)}
      </p>
      <ol className="trace">
        {node(1, 'Source', U ? fv(null) : <>{p.sourceName}<div className="note">{p.vendor} · {p.mode}</div></>, U)}
        {node(2, 'File', noF ? fv(null) : <><span className="mono">{p.file}</span><div className="note">{p.fileNote}</div></>, noF)}
        {node(3, 'Table / sheet', noF || !p.table ? fv(null) : <><span className="mono">{p.table}</span><div className="note">column <span className="mono">{p.column}</span></div></>, noF || !p.table)}
        {node(4, 'Row', U || !p.record ? fv(null) : <>{p.record}<div className="note">row {(p.row ?? 0).toLocaleString()} of {(p.rowsTotal ?? 0).toLocaleString()}</div></>, U || !p.record)}
        {node(5, 'Data', U ? fv(null) : <b>{p.value}</b>, U)}
        {node(6, 'Fetch time', U ? fv(null) : <><span className="num">{p.fetchedAt && isoT(p.fetchedAt)}</span><div className="note">{p.request}</div></>, U)}
        {node(7, 'Processing', U ? fv(null) : <ol style={{ margin: 0, paddingLeft: 16 }}>{(p.processing ?? []).map((x) => <li key={x}>{x}</li>)}</ol>, U)}
        {node(8, 'Evidence', (
          <>
            <b>{e.label}</b> {U ? <span className="chip bad">missing</span> : <span className={'chip ' + (e.state === 'ready' ? 'ok' : 'warn')}>{e.state}</span>}
            {!U && <div className="note">Used in: {p.usedIn.join('; ')}</div>}
          </>
        ), false)}
      </ol>
    </Modal>
  );
}
