/* Canonical Models, Event Streams (with the event drawer), Conflict Queue and Manual Import. */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { fmtDate } from '../../api/format';
import { useBackend } from '../../api/hooks';
import {
  ackKind, canon, canonExample, caseExists, commitImport, conflicts, escalateConflict, events, facilities, jsonHtml, mappings, pct, rbPath, resolveConflict,
  sampleCsv, sources, tenantList, type StreamEvent,
} from '../../api/integration';
import { Drawer } from '../../ui/Overlay';
import { toast } from '../../ui/toast';
import { canMgr, FrKpi, Html, NOMGR, sum } from './ui';

/* ---- Canonical models ---- */
export function Models() {
  useBackend();
  const C = canon(), f = sum(C.map((c) => c.fields.length)), src = sources().filter((s) => mappings(s.id).length).length;
  return (
    <>
      <div className="frkpis fr3">
        <FrKpi ic="layers" h="dec" v={C.length} l="Canonical models" />
        <FrKpi ic="list" h="money" v={f} l="Fields across models" />
        <FrKpi ic="mapping" h="int" v={src} l="Sources mapped in" />
      </div>
      <p className="ink2" style={{ marginTop: 0, maxWidth: '75ch' }}>
        Adapters map vendor-specific records into these versioned canonical models, so the AI services evaluate assets and demand the same way across platforms. Adapters never invent data a source does not hold.
      </p>
      <div className="grid g2">
        {C.map((m) => (
          <div className="panel" key={m.n}>
            <div className="ph"><h3>{m.n}</h3><span className="chip y">v{m.v}</span></div>
            <div className="pb">
              <p style={{ margin: '0 0 10px' }} className="ink2">{m.purpose}</p>
              <div className="row" style={{ gap: 5, marginBottom: 10 }}>{m.fields.map((x) => <span key={x} className="chip line mono" style={{ fontSize: 11 }}>{x}</span>)}</div>
              <div className="note">Fed by {m.sources.join(' · ')}</div>
              <details className="dd"><summary>Example from RT-1048</summary><pre className="code"><Html html={jsonHtml(canonExample(m.n))} /></pre></details>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

/* ---- Event streams ---- */
const ef = { dir: '', issues: false, q: '' };
const evTime = (ts: StreamEvent['ts']) => fmtDate(ts) + ' ' + new Date(ts).toISOString().slice(11, 16);

export function Events({ onOpen }: { onOpen: (id: string) => void }) {
  useBackend();
  const [, setV] = useState(0);
  const up = (f: () => void) => { f(); setV((x) => x + 1); };
  const E = events(), q = ef.q.toLowerCase();
  const rows = E.filter((e) => (!ef.dir || e.dir === ef.dir) && (!ef.issues || e.ack !== 'acknowledged') && (!ef.q || ((e.caseId || '') + (e.decisionId || '') + e.type + e.dest).toLowerCase().includes(q)));
  const n = E.length, ok = E.filter((e) => e.ack === 'acknowledged').length, dup = E.filter((e) => /duplicate/.test(e.ack)).length;
  const late = E.filter((e) => /late|out of order/.test(e.ack)).length, rt = E.filter((e) => /retry/.test(e.ack)).length;
  const inn = E.filter((e) => e.dir === 'in').length, err = E.filter((e) => /error|fail|duplicate|escalat/i.test(e.ack || '')).length;
  return (
    <>
      <div className="frkpis fr4">
        <FrKpi ic="stream" h="int" v={n} l="Events in the stream" />
        <FrKpi ic="download" h="money" v={inn} l="Inbound" />
        <FrKpi ic="send" h="dec" v={n - inn} l="Outbound" />
        <FrKpi ic="alert" h="alert" v={err} l="Errors, duplicates and escalations" />
      </div>
      <div className="grid g4" style={{ marginBottom: 14 }}>
        {([[n, 'events in stream'], [pct(ok / n, 0), 'acknowledged first time'], [dup + ' · ' + rt, 'duplicates caught · retries'], [late, 'late or out of order, reconciled']] as [string | number, string][]).map((x) => (
          <div className="panel flat" style={{ padding: 12 }} key={x[1]}>
            <div className="num" style={{ font: '800 24px var(--f-display)' }}>{x[0]}</div>
            <div className="note">{x[1]}</div>
          </div>
        ))}
      </div>
      <div className="panel">
        <div className="filters">
          <div className="seg">
            {[['', 'All'], ['out', 'Outbound'], ['in', 'Inbound']].map(([k, l]) => <button key={k} aria-pressed={ef.dir === k} onClick={() => up(() => { ef.dir = k; })}>{l}</button>)}
          </div>
          <label className="tog"><input type="checkbox" checked={ef.issues} onChange={(e) => up(() => { ef.issues = e.target.checked; })} /> Only retries, duplicates, late and conflicts</label>
          <input type="search" placeholder="Filter by case, decision or destination" aria-label="Filter events" value={ef.q} onChange={(e) => up(() => { ef.q = e.target.value; })} />
        </div>
        <div className="tw" style={{ maxHeight: 560, overflow: 'auto' }}>
          <table className="t stream">
            <thead><tr><th>Time</th><th>Dir</th><th>Event</th><th>Case</th><th>Decision</th><th>Approval</th><th className="r">Ver</th><th>Destination</th><th>Acknowledgement</th><th>Idempotency key</th></tr></thead>
            <tbody>
              {rows.length ? rows.slice(0, 70).map((e) => (
                <tr key={e.id} style={{ cursor: 'pointer' }} onClick={() => onOpen(e.id)}>
                  <td className="num nowrap">{evTime(e.ts)}</td>
                  <td><span className={'chip ' + (e.dir === 'out' ? 'dk' : 'line')}>{e.dir === 'out' ? 'Out' : 'In'}</span></td>
                  <td className="mono">{e.type}</td>
                  <td>{e.caseId && caseExists(e.caseId) ? (rbPath('product/' + e.caseId) ? <Link to={'/product/' + e.caseId} onClick={(x) => x.stopPropagation()}>{e.caseId}</Link> : e.caseId) : '—'}</td>
                  <td className="mono">{e.decisionId || '—'}</td>
                  <td className="mono">{e.approval || '—'}</td>
                  <td className="r num">{e.ver || '—'}</td>
                  <td>{e.dest}</td>
                  <td><span className={'chip ' + ackKind(e.ack)}>{e.ack}</span></td>
                  <td className="mono">{e.key}</td>
                </tr>
              )) : <tr><td colSpan={10}><div className="empty"><b>No events match</b>Clear the filters, or approve a case in Product to create one.</div></td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

export function EventDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const e = events().find((x) => x.id === id);
  if (!e) return null;
  const link = e.caseId && caseExists(e.caseId) && rbPath('product/' + e.caseId);
  return (
    <Drawer title={e.type} sub={e.id} onClose={onClose} foot={link ? <Link className="btn" to={'/product/' + e.caseId} onClick={onClose}>Open {e.caseId}</Link> : undefined}>
      <div className="row" style={{ marginBottom: 10 }}>
        <span className={'chip ' + (e.dir === 'out' ? 'dk' : 'line')}>{e.dir === 'out' ? 'Outbound' : 'Inbound'}</span>
        <span className={'chip ' + ackKind(e.ack)}>{e.ack}</span>
      </div>
      {e.note && <div className="callout" style={{ marginBottom: 12 }}>{e.note}</div>}
      <pre className="code">
        <Html html={jsonHtml({ event: e.id, type: e.type, at: new Date(e.ts).toISOString(), caseId: e.caseId, decisionId: e.decisionId, approvalRef: e.approval, instructionVersion: e.ver, destination: e.dest, acknowledgement: e.ack, idempotencyKey: e.key, retries: e.retries || 0 })} />
      </pre>
    </Drawer>
  );
}

/* ---- Conflict queue ---- */
export function Conflicts() {
  useBackend();
  const C = conflicts(), o = C.filter((c) => c.status === 'open').length;
  const resolve = (id: string) => {
    if (!canMgr()) return toast(NOMGR);
    const r = resolveConflict(id);
    if (!r.ok) return toast(r.error.message);
    toast(`${id} resolved: ${r.output.authority} is authoritative for ${r.output.kind.toLowerCase()}.`);
  };
  const escalate = (id: string) => {
    const r = escalateConflict(id);
    if (!r.ok && r.error.code !== 'duplicate') return toast(r.error.message);
    toast('Escalated to the data owner. The conflict stays open and dependent routes stay held.');
  };
  return (
    <>
      <div className="frkpis fr3">
        <FrKpi ic="conflict" h="dec" v={o} l="Open conflicts" />
        <FrKpi ic="checks" h="int" v={C.length - o} l="Resolved or escalated" />
        <FrKpi ic="graph" h="money" v={new Set(C.flatMap((c) => [c.a.src, c.b.src])).size} l="Systems involved" />
      </div>
      <p className="ink2" style={{ marginTop: 0, maxWidth: '75ch' }}>
        When two systems disagree, Circularity names the source with authority, flags the conflict and holds any dependent route. It does not pick silently.
      </p>
      <div className="grid g3">
        {C.map((c) => (
          <div className="panel" key={c.id} style={{ borderTop: '4px solid ' + (c.status === 'open' ? 'var(--bad)' : 'var(--ok)') }}>
            <div className="ph"><h3>{c.kind}</h3><span className={'chip ' + (c.status === 'open' ? 'bad' : 'ok')}>{c.status === 'open' ? 'Open · ' + c.since : 'Resolved'}</span></div>
            <div className="pb">
              <b>{c.asset}</b>
              <div className="grid g2" style={{ margin: '10px 0' }}>
                <div className="panel flat" style={{ padding: 8 }}><div className="note">{c.a.src}</div><b>{c.a.val}</b></div>
                <div className="panel flat" style={{ padding: 8 }}><div className="note">{c.b.src}</div><b>{c.b.val}</b></div>
              </div>
              <dl className="kv"><dt>Source authority</dt><dd>{c.authority}</dd><dt>Impact</dt><dd>{c.impact}</dd></dl>
              {c.status === 'open' ? (
                canMgr() && (
                  <div className="row" style={{ marginTop: 12 }}>
                    <button className="btn sm pri" onClick={() => resolve(c.id)}>Accept {c.authority}</button>
                    <button className="btn sm" onClick={() => escalate(c.id)}>Escalate to owner</button>
                  </div>
                )
              ) : <div className="note" style={{ marginTop: 10 }}>Resolved in favour of {c.authority}. Held routes were released for re-evaluation.</div>}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

/* ---- Manual import ---- */
type Row = { asset_id: string; qty: string; grade: string; location: string; owner: string; received: string; errors: string[]; warn: string[] };
type Csv = { rows: Row[]; ok: number; err: number; committed?: boolean };
const imp: { text: string; csv: Csv | null } = { text: '', csv: null };

function validateCsv(t: string): Csv | string {
  const lines = t.split(/\r?\n/).filter(Boolean), hd = lines[0].split(',').map((x) => x.trim().toLowerCase());
  const need = ['asset_id', 'qty', 'condition_grade', 'location', 'owner', 'received'], miss = need.filter((n) => !hd.includes(n));
  if (miss.length) return 'Missing required column: ' + miss.join(', ');
  const F = facilities(), T = tenantList();
  const rows = lines.slice(1).map((l) => {
    const c = l.split(',').map((x) => x.trim()), o: Record<string, string> = {};
    hd.forEach((h, i) => { o[h] = c[i] || ''; });
    const errors: string[] = [], warn: string[] = [];
    if (!/^(MTR|PMP|CTL|DRL|BAT|ITE)-\d{4}$/.test(o.asset_id)) errors.push('asset_id does not match a known class pattern');
    if (!/^[1-9]\d*$/.test(o.qty)) errors.push('qty must be a positive whole number');
    let g = o.condition_grade;
    if (/^[ABCD]\+$/.test(g)) { warn.push(g + ' mapped to ' + g[0]); g = g[0]; } else if (!/^[ABCD]$/.test(g)) errors.push('grade must be A–D');
    if (!F.includes(o.location)) errors.push('unknown location "' + o.location + '"');
    if (!T.includes(o.owner)) errors.push('owner is not a tenant on this account');
    let d = o.received;
    if (/^\d{4}\/\d{2}\/\d{2}$/.test(d)) { warn.push('date reformatted'); d = d.replace(/\//g, '-'); } else if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) errors.push('received must be YYYY-MM-DD');
    return { asset_id: o.asset_id, qty: o.qty, grade: g, location: o.location, owner: o.owner, received: d, errors, warn };
  });
  return { rows, ok: rows.filter((r) => !r.errors.length).length, err: rows.filter((r) => r.errors.length).length };
}

export function Import() {
  useBackend();
  const [, setV] = useState(0);
  const up = (f: () => void) => { f(); setV((x) => x + 1); };
  const st = imp.csv, mgr = canMgr();
  const validate = () => {
    const t = imp.text.trim();
    if (!t) return toast('Add a CSV file or rows first.');
    const r = validateCsv(t);
    if (typeof r === 'string') { up(() => { imp.csv = { rows: [], ok: 0, err: 0 }; }); return toast(r); }
    up(() => { imp.csv = r; });
  };
  const file = (f: File | undefined) => {
    if (!f) return;
    if (f.size > 200000) return toast('File is over 200 KB. Split it into smaller batches.');
    const r = new FileReader();
    r.onload = () => { up(() => { imp.text = String(r.result); imp.csv = null; }); toast('Loaded ' + f.name + '. Choose Validate.'); };
    r.readAsText(f);
  };
  const commit = () => {
    if (!st) return;
    const r = commitImport(st.ok, st.err, st.rows);
    if (!r.ok) return toast(r.error.message);
    up(() => { st.committed = true; });
    toast(st.ok + ' rows loaded for evaluation. They are tagged manual and will not trigger any instruction.', 4200);
  };
  return (
    <>
      <div className="callout" style={{ marginBottom: 14 }}>
        <b>Supports evaluation, not live automation.</b> A controlled CSV import lets you try Circularity where an API or partner feed does not exist yet. Imported rows are tagged manual, carry no live freshness, and cannot trigger outbound instructions.
      </div>
      <div className="grid g2" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.3fr)' }}>
        <div className="panel">
          <div className="ph"><h3>1. Provide a file</h3></div>
          <div className="pb">
            <div className="fld"><label htmlFor="csvf">Approved CSV file</label><input id="csvf" type="file" accept=".csv,text/csv" disabled={!mgr} onChange={(e) => file(e.target.files?.[0])} /></div>
            <div className="fld">
              <label htmlFor="csvt">Or paste rows</label>
              <textarea id="csvt" className="code" style={{ minHeight: 190, whiteSpace: 'pre' }} spellCheck={false} readOnly={!mgr} placeholder="asset_id,qty,condition_grade,location,owner,received"
                value={imp.text} onChange={(e) => up(() => { imp.text = e.target.value; })} />
            </div>
            <div className="row">
              <button className="btn" onClick={() => up(() => { imp.text = sampleCsv(); imp.csv = null; })}>Load sample file</button>
              <button className="btn pri" onClick={validate}>Validate</button>
            </div>
            <div className="note" style={{ marginTop: 8 }}>Required columns: asset_id, qty, condition_grade, location, owner, received.</div>
          </div>
        </div>
        <div className="panel">
          <div className="ph"><h3>2. Validation preview</h3>{st && <span className={'chip ' + (st.err ? 'warn' : 'ok')}>{st.ok} ready · {st.err} rejected</span>}</div>
          {st ? (
            <>
              <div className="tw">
                <table className="t static">
                  <thead><tr><th>Row</th><th>Asset</th><th className="r">Qty</th><th>Grade</th><th>Location</th><th>Owner</th><th>Received</th><th>Result</th></tr></thead>
                  <tbody>
                    {st.rows.map((r, i) => (
                      <tr key={i}>
                        <td>{i + 2}</td><td className="mono">{r.asset_id}</td><td className="r num">{r.qty}</td><td>{r.grade}</td><td>{r.location}</td><td>{r.owner}</td><td className="num">{r.received}</td>
                        <td>
                          {r.errors.length ? <><span className="chip bad" data-tip={r.errors.join('; ')} title={r.errors.join('; ')}>Rejected</span><div className="note">{r.errors[0]}</div></>
                            : r.warn.length ? <><span className="chip warn">Normalised</span><div className="note">{r.warn.join('; ')}</div></> : <span className="chip ok">Ready</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="filters" style={{ borderTop: '1px solid var(--line2)', borderBottom: 0 }}>
                <span className="note grow">Rejected rows are never partially loaded. {st.committed && <b>Loaded for evaluation.</b>}</span>
                {mgr && <button className="btn pri" disabled={!(st.ok && !st.committed)} onClick={commit}>Load {st.ok} rows for evaluation</button>}
              </div>
            </>
          ) : <div className="empty"><b>Nothing validated yet</b>Load the sample file or paste rows, then choose Validate.</div>}
        </div>
      </div>
    </>
  );
}
