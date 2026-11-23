/* Canonical Models, Event Streams (with the event drawer), Conflict Queue and Manual Import. */
import { useState } from 'react';
import { Link } from 'react-router';
import { fmtDate } from '../../api/format';
import { useBackend } from '../../api/useBackend';
import {
  ackKind, canon, canonExample, CASE_REASONS, CASE_TEMPLATES, caseExists, commitImport, conflictPage, escalateConflict, events, facilities, mappings, pct, rbPath, resolveConflict,
  sampleCsv, sources, tenantList, type Conflict, type ConflictChoice, type StreamEvent,
} from '../../api/integration';
import { can } from '../../api/session';
import { sessionScoped } from '../../api/view';
import { onActivateKey } from '../../utils/keys';
import { Drawer } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { JsonView } from '../../components/kit/JsonView';
import { Kpi } from '../../components/kit/Kpi';
import { canMgr, NOMGR } from './FabricContext';
import { sum } from './fabricFormat';

/* ---- Canonical models ---- */
export function Models() {
  useBackend();
  const C = canon(), f = sum(C.map((c) => c.fields.length)), src = sources().filter((s) => mappings(s.id).length).length;
  return (
    <>
      <div className="frkpis fr3">
        <Kpi ic="layers" h="dec" v={C.length} l="Canonical models" />
        <Kpi ic="list" h="money" v={f} l="Fields across models" />
        <Kpi ic="mapping" h="int" v={src} l="Sources mapped in" />
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
              <details className="dd"><summary>Example from RT-1048</summary><JsonView variant="tokens" value={canonExample(m.n)} /></details>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

/* ---- Event streams ---- */
const efKept = sessionScoped(() => ({ dir: '', issues: false, q: '' }));
const evTime = (ts: StreamEvent['ts']) => fmtDate(ts) + ' ' + new Date(ts).toISOString().slice(11, 16);

export function Events({ onOpen }: { onOpen: (id: string) => void }) {
  useBackend();
  const ef = efKept.current;
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
        <Kpi ic="stream" h="int" v={n} l="Events in the stream" />
        <Kpi ic="download" h="money" v={inn} l="Inbound" />
        <Kpi ic="send" h="dec" v={n - inn} l="Outbound" />
        <Kpi ic="alert" h="alert" v={err} l="Errors, duplicates and escalations" />
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
                <tr key={e.id} style={{ cursor: 'pointer' }} tabIndex={0} onClick={() => onOpen(e.id)} onKeyDown={onActivateKey(() => onOpen(e.id))}>
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
      <JsonView variant="tokens" value={{ event: e.id, type: e.type, at: new Date(e.ts).toISOString(), caseId: e.caseId, decisionId: e.decisionId, approvalRef: e.approval, instructionVersion: e.ver, destination: e.dest, acknowledgement: e.ack, idempotencyKey: e.key, retries: e.retries || 0 }} />
    </Drawer>
  );
}

/* ---- Conflict queue ---- */
const CF_PAGE = 60;
export function Conflicts() {
  useBackend();
  const [n, setN] = useState(CF_PAGE);
  const P = conflictPage(n), C = P.list;
  const action = useAction();
  const resolve = async (id: string) => {
    if (!canMgr()) return toast(NOMGR);
    const r = await action.run(() => resolveConflict(id));
    if (!r.ok) return;
    toast(`${id} resolved: ${r.output.authority} is authoritative for ${r.output.kind.toLowerCase()}.`);
  };
  const escalate = async (id: string) => {
    const r = await action.run(() => escalateConflict(id), { silent: ['duplicate'] });
    if (!r.ok && r.error.code !== 'duplicate') return;
    toast('Escalated to the data owner. The conflict stays open and dependent routes stay held.');
  };
  /* plan 6 B2: keep another source's value or enter one, with a reason (the choice holds until a source's value changes) */
  const [pick, setPick] = useState<(ConflictChoice & { id: string }) | null>(null);
  const choose = async () => {
    if (!pick || !canMgr()) return;
    if (!pick.reason?.trim()) return toast('Give a reason when you do not keep the value of the system with authority.');
    if (pick.choose === 'value' && !pick.value?.trim()) return toast('Enter the value to keep.');
    const r = await action.run(() => resolveConflict(pick.id, pick));
    if (!r.ok) return;
    setPick(null);
    toast(r.output.choose === 'value' ? `${pick.id} resolved with the value you entered.` : `${pick.id} resolved: ${r.output.keptName}'s value is kept for ${r.output.kind.toLowerCase()}.`);
  };
  const others = (c: Conflict) => (c.values ?? [{ source: '', src: c.b.src, val: c.b.val }]).filter((v) => v.source !== c.authorityId);
  const resolvedNote = (c: Conflict) => {
    const note = c.resolved?.note;
    return note && !note.includes('(the system with authority)') && note !== 'The sources agree again' ? note + '.' : `Resolved in favour of ${c.authority}.`;
  };
  return (
    <>
      <div className="frkpis fr3">
        <Kpi ic="conflict" h="dec" v={P.open} l="Open conflicts" />
        <Kpi ic="checks" h="int" v={P.closed} l="Resolved or escalated" />
        <Kpi ic="graph" h="money" v={P.systems} l="Systems involved" />
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
              {c.status === 'open' && c.escalated && <div className="note" style={{ marginTop: 8 }}>Escalated to {c.escalated.to || 'the data owner'} by {c.escalated.by}.</div>}
              {c.status === 'open' ? (
                canMgr() && (
                  <>
                    <div className="row" style={{ marginTop: 12 }}>
                      <button className="btn sm pri" onClick={() => resolve(c.id)}>Accept {c.authority}</button>
                      <button className="btn sm" onClick={() => escalate(c.id)}>Escalate to owner</button>
                      {pick?.id !== c.id && (
                        <button className="btn sm" onClick={() => setPick({ id: c.id, choose: 'other', source: others(c)[0]?.source || undefined, reason: '' })}>Choose another value</button>
                      )}
                    </div>
                    {pick?.id === c.id && (
                      <div className="panel flat" style={{ padding: 10, marginTop: 10 }}>
                        {others(c).map((v) => (
                          <label key={v.source || v.src} className="row" style={{ gap: 6 }}>
                            <input type="radio" name={'cf-' + c.id} checked={pick.choose === 'other' && (pick.source ?? '') === v.source}
                              onChange={() => setPick({ ...pick, choose: 'other', source: v.source || undefined })} />
                            Keep {v.src}: <b>{v.val}</b>
                          </label>
                        ))}
                        <label className="row" style={{ gap: 6 }}>
                          <input type="radio" name={'cf-' + c.id} checked={pick.choose === 'value'} onChange={() => setPick({ ...pick, choose: 'value' })} />
                          Enter a value
                        </label>
                        {pick.choose === 'value' && (
                          <div className="fld"><label htmlFor={'cfv-' + c.id}>Value</label>
                            <input id={'cfv-' + c.id} value={pick.value ?? ''} onChange={(e) => setPick({ ...pick, value: e.target.value })} /></div>
                        )}
                        <div className="fld"><label htmlFor={'cfr-' + c.id}>Reason (kept in the audit trail)</label>
                          <input id={'cfr-' + c.id} value={pick.reason ?? ''} onChange={(e) => setPick({ ...pick, reason: e.target.value })} /></div>
                        <div className="note">The choice holds until a source sends a different value; then the conflict opens again.</div>
                        <div className="row" style={{ marginTop: 8 }}>
                          <button className="btn sm pri" onClick={choose}>Resolve</button>
                          <button className="btn sm" onClick={() => setPick(null)}>Cancel</button>
                        </div>
                      </div>
                    )}
                  </>
                )
              ) : <div className="note" style={{ marginTop: 10 }}>{resolvedNote(c)} Held routes were released for re-evaluation.</div>}
            </div>
          </div>
        ))}
      </div>
      {C.length < P.total && (
        <div className="row" style={{ marginTop: 14, justifyContent: 'center' }}>
          <span className="note">Showing {C.length} of {P.total}</span>
          <button className="btn" onClick={() => setN(C.length + CF_PAGE)}>Show more</button>
        </div>
      )}
    </>
  );
}

/* ---- Manual import ---- */
type Row = { asset_id: string; qty: string; grade: string; location: string; owner: string; received: string; errors: string[]; warn: string[] };
type Csv = { rows: Row[]; ok: number; err: number; committed?: boolean };
/** cases: open a case for each loaded row (plan 8), with this template and reason; each row's owner is its org unit. */
const impKept = sessionScoped<{ text: string; csv: Csv | null; cases: { on: boolean; template: string; reason: string } }>(() => ({
  text: '', csv: null, cases: { on: false, template: 'industrial', reason: 'lease_end' },
}));

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
  const imp = impKept.current;
  const st = imp.csv, mgr = canMgr();
  const action = useAction();
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
  const commit = async () => {
    if (!st) return;
    const oc = imp.cases.on ? { template: imp.cases.template, reason: imp.cases.reason, org_unit_id: '', asset_field: 'asset_id' } : undefined;
    const r = await action.run(() => commitImport(st.ok, st.err, st.rows, oc));
    if (!r.ok) return;
    up(() => { st.committed = true; });
    const o = r.output;
    const opened = o.cases_opened !== undefined ? ' ' + o.cases_opened + ' cases opened, ' + (o.cases_skipped ?? 0) + ' already open.' : '';
    toast(st.ok + ' rows loaded for evaluation. They are tagged manual and will not trigger any instruction.' + opened, 4200);
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
                {mgr && can('openCases') && (
                  <span className="row" style={{ gap: 6 }}>
                    <label><input type="checkbox" checked={imp.cases.on} disabled={st.committed} onChange={(e) => up(() => { imp.cases.on = e.target.checked; })} /> Open a case for each row</label>
                    <select aria-label="Template" value={imp.cases.template} disabled={!imp.cases.on || st.committed} onChange={(e) => up(() => { imp.cases.template = e.target.value; })}>
                      {CASE_TEMPLATES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <select aria-label="Reason" value={imp.cases.reason} disabled={!imp.cases.on || st.committed} onChange={(e) => up(() => { imp.cases.reason = e.target.value; })}>
                      {CASE_REASONS.map((x) => <option key={x} value={x}>{x}</option>)}
                    </select>
                  </span>
                )}
                {mgr && <button className="btn pri" disabled={!(st.ok && !st.committed)} onClick={commit}>Load {st.ok} rows for evaluation</button>}
              </div>
            </>
          ) : <div className="empty"><b>Nothing validated yet</b>Load the sample file or paste rows, then choose Validate.</div>}
        </div>
      </div>
    </>
  );
}
