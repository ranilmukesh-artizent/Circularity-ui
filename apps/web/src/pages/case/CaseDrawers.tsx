/**
 * The dialogs and side panels the case pages open (the demo's ACT.exSrc, exSrcAll, viewInstr, tiRaw, trace, snapshot,
 * sources and models), drawn as React and opened through the page's CaseUi.modal.
 */
import { Suspense, type ReactNode } from 'react';
import { modelStats, modelVersions } from '../../api/analytics';
import { fmtD, fmtDY, inr, isoT, refList, type CaseAnalysis, type CaseRec, type Prov } from '../../api/case';
import { ApiError } from '../../api/client';
import { money } from '../../api/format';
import { canPage } from '../../api/session';
import { toast } from '../../ui/toast';
import { ExMethod, Json } from './kit';
import { hashId } from './tabs/EarlyTabs';
import type { CaseUi } from './ui';

const EX_FX_AT = '2026-10-06';
const asOf = () => new Date(refList<string>('AS_OF'));
const addDays = (d: Date, n: number) => new Date(d.getTime() + n * 864e5);
const closeBtn = (ui: CaseUi) => <button className="btn" onClick={() => ui.modal(null)}>Close</button>;
const ExFoot = () => <p className="note">Source systems hold rupees; Circularity decides in dollars at ₹83.5. The lines add up exactly to each term.</p>;
const exSigned = (v: number) => (v > 0 ? '+' : v < 0 ? '−' : '') + inr(Math.abs(v));

/** Where one term of a route comes from: its lines with method and source, and the actual once confirmed (exTraceHTML). */
export function ExTrace({ c, a, ri, ti, withAct }: { c: CaseRec; a: CaseAnalysis; ri: number; ti: number; withAct?: boolean }) {
  const r = c.routes[ri], t = r?.terms[ti], o = a.routes[ri]?.terms?.[ti];
  if (!r || !t || !o) return <p className="note">No cost trace for this term.</p>;
  let act: ReactNode = null;
  const chosen = c.chosen || c.recommendation;
  if (withAct && c.outcome && chosen && chosen.id === r.id && chosen.plan === r.plan) {
    const k = (c.outcome.lines || []).findIndex((x) => x.label === t.label), ol = c.outcome.lines[k];
    if (ol) {
      const A = a.view.actuals[k] || [], fx = refList<number>('EX_FX');
      act = (
        <>
          <h4 className="exah">Actual {money(ol.act)} <span className="note">{inr(Math.round(ol.act * fx))} · confirmed by Finance</span></h4>
          {A.length ? (
            <div className="tw">
              <table className="t static tight exact">
                <tbody>
                  {A.map((x, i) => <tr key={i}><td><b>{x[0]}</b><div className="note">{x[3]} · {x[4]}</div></td><td className="note">{x[1]}</td><td className="r num">{exSigned(x[2])}</td></tr>)}
                  <tr><td colSpan={2}><b>Difference</b></td><td className="r num"><b>{exSigned(A.reduce((s, x) => s + x[2], 0))}</b></td></tr>
                </tbody>
              </table>
            </div>
          ) : <p className="note">Came in as predicted.</p>}
        </>
      );
    }
  }
  return (
    <div className="extr">
      <p className="extrh">
        <b className="num">{money(t.amt)}</b> <span className="note">= {t.amt < 0 ? '−' : ''}{inr(o.inr)} at ₹{refList<number>('EX_FX')} to the dollar (rate dated {fmtDY(EX_FX_AT)})</span> <ExMethod m={o.method} />
      </p>
      <p className="note" style={{ margin: '0 0 8px' }}>{o.sys}{o.rec ? ' · ' + o.rec : ''}</p>
      <div className="tw">
        <table className="t static tight exlines">
          <thead><tr><th>Line</th><th>Calculation</th><th>Method and source</th><th className="r">₹</th><th className="r">$</th></tr></thead>
          <tbody>
            {o.lines.map((l, i) => (
              <tr key={i}>
                <td><b>{l.item}</b>{l.why && <div className="note">{l.why}</div>}</td>
                <td className="note">{l.calc}</td>
                <td><ExMethod m={l.method} /><div className="note">{l.sys}{l.rec ? ' · ' + l.rec : ''}</div></td>
                <td className="r num">{inr(l.inr)}</td>
                <td className="r num note">{money(l.inr / refList<number>('EX_FX'))}</td>
              </tr>
            ))}
            <tr><td colSpan={3}><b>{t.label}</b></td><td className="r num"><b>{inr(o.inr)}</b></td><td className="r num"><b>{money(Math.abs(t.amt))}</b></td></tr>
          </tbody>
        </table>
      </div>
      <p className="ink2" style={{ margin: '8px 0 0' }}>{o.why}</p>
      {act}
    </div>
  );
}

/** "Where this number comes from" for one term (ACT.exSrc). */
export function openExSrc(ui: CaseUi, c: CaseRec, a: CaseAnalysis, ri: number, ti: number) {
  const r = c.routes[ri];
  if (!r || !r.terms[ti]) return;
  ui.modal({
    title: 'Where this number comes from', sub: r.terms[ti].label + ' · ' + r.plan + ' · ' + c.id, wide: true, drawer: true,
    body: <><ExTrace c={c} a={a} ri={ri} ti={ti} withAct /><ExFoot /></>,
  });
}
/** Every term of a route (ACT.exSrcAll). */
export function openExSrcAll(ui: CaseUi, c: CaseRec, a: CaseAnalysis, ri: number) {
  const r = c.routes[ri];
  if (!r) return;
  ui.modal({
    title: 'Where every number comes from', sub: r.plan + ' · ' + money(r.net) + ' · ' + c.id, wide: true, drawer: true,
    body: <>{r.terms.map((t, i) => <section key={i} className="exall"><h3>{t.label}</h3><ExTrace c={c} a={a} ri={ri} ti={i} withAct /></section>)}<ExFoot /></>,
  });
}
/** Work instructions: the payload with its expiry (ACT.viewInstr). */
export function openPayload(ui: CaseUi, c: CaseRec, a: CaseAnalysis) {
  const p = { ...(a.instruction || {}), expiresAt: addDays(asOf(), 7).toISOString().slice(0, 10) };
  ui.modal({
    title: 'Work instructions · ' + c.id, foot: closeBtn(ui),
    body: <><p className="ink2" style={{ marginTop: 0 }}>Every outbound message carries a decision identifier, approval reference, instruction version, destination and acknowledgement. Retries are idempotent.</p><Json o={p} /></>,
  });
}
/** The raw instruction (ACT.tiRaw). */
export function openRaw(ui: CaseUi, c: CaseRec, a: CaseAnalysis) {
  ui.modal({
    title: 'Instruction payload · ' + c.id, foot: closeBtn(ui),
    body: <><p className="ink2" style={{ marginTop: 0 }}>{c.exec ? 'This is what was sent.' : 'This is exactly what will be sent once a person approves. Nothing has been sent yet.'}</p><Json o={a.instruction} /></>,
  });
}

// ---------- provenance ----------
type FullProv = Prov & {
  mode?: string; auth?: string; file?: string | null; fileNote?: string; table?: string | null; column?: string | null; row?: number | null; rowsTotal?: number;
  observedAt?: string; request?: string; checksum?: string; processing?: string[]; partialWhy?: string;
};
const PU = <span className="chip bad" style={{ height: 'auto', padding: '1px 8px' }}>Provenance unavailable</span>;
const fv = (v: ReactNode) => (v == null || v === '' ? PU : v);
const ProvChip = ({ p }: { p: Prov }) =>
  p.status === 'available' ? <span className="chip ok">Full provenance</span> : p.status === 'partial' ? <span className="chip warn">Partial provenance</span> : <span className="chip bad">Provenance unavailable</span>;
/** Every field of an item's provenance (provTable). */
function ProvTable({ p }: { p: FullProv }) {
  if (p.status === 'unavailable') return <div className="callout bad"><b>Provenance unavailable.</b> {p.reason}</div>;
  const rows: [string, string | null | undefined][] = [
    ['Source system', p.sourceName + ' (' + p.vendor + ')'], ['Access', p.auth + ' · ' + p.mode], ['File name / path', p.file], ['Table / sheet', p.table], ['Column', p.column],
    ['Row / record', p.record ? `${p.record} (row ${(p.row ?? 0).toLocaleString()} of ${(p.rowsTotal ?? 0).toLocaleString()})` : null], ['Exact value', p.value],
    ['Exact fetch timestamp', p.fetchedAt && isoT(p.fetchedAt)], ['Observed at source', p.observedAt && isoT(p.observedAt)], ['Request / query', p.request], ['Payload checksum', p.file ? p.checksum : null],
  ];
  return (
    <>
      <table className="t static"><tbody>
        {rows.map(([k, v]) => <tr key={k}><td style={{ width: 170, color: 'var(--muted)' }}>{k}</td><td className={/path|query|checksum|Column|Table/.test(k) ? 'mono' : undefined}>{fv(v)}</td></tr>)}
      </tbody></table>
      {p.partialWhy && <div className="note" style={{ marginTop: 6 }}>{p.partialWhy}</div>}
      {(p.notes || []).map((n, i) => <div key={i} className="callout" style={{ marginTop: 8 }}>{n}</div>)}
    </>
  );
}
function provCsv(id: string, p: FullProv) {
  const f = { provenance_id: p.id, case: id, item: p.label, source: p.sourceName, file: p.file, table: p.table, column: p.column, record: p.record, value: p.value, fetched_at: p.fetchedAt, request: p.request, checksum: p.checksum };
  const csv = 'field,value\n' + Object.entries(f).map(([a, b]) => `${a},"${String(b == null ? 'Provenance unavailable' : b).replace(/"/g, '""')}"`).join('\n');
  const el = document.createElement('a');
  el.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  el.download = `provenance-${p.id}.csv`;
  el.click();
  toast('Exported ' + p.id);
}
/** The data trace of one evidence item: source, file, table, row, value, fetch, processing, use (ACT.trace). */
export function openTrace(ui: CaseUi, c: CaseRec, a: CaseAnalysis, k: string) {
  const i = c.evidence.findIndex((x) => x.k === k), e = c.evidence[i], p = a.provenance[i] as FullProv;
  if (!e || !p) return;
  const U = p.status === 'unavailable', noF = U || !p.file;
  const node = (n: number, t: string, body: ReactNode, miss: boolean) => <li key={n} className={'tn ' + (miss ? 'miss' : '')}><span className="tnum">{n}</span><b>{t}</b><div>{body}</div></li>;
  ui.modal({
    title: 'Data trace · ' + e.label, wide: true,
    foot: <>{!U && <button className="btn" onClick={() => provCsv(c.id, p)}>Export record</button>}{closeBtn(ui)}</>,
    body: (
      <>
        <p className="ink2" style={{ marginTop: 0 }}>{c.id} · {c.assetId}. Each step is recorded by the Connection Fabric; a step with no record is shown as unavailable and is never inferred. <ProvChip p={p} /></p>
        <ol className="trace">
          {node(1, 'Source', U ? fv(null) : <>{p.sourceName}<div className="note">{p.vendor} · {p.mode}</div></>, U)}
          {node(2, 'File', noF ? fv(null) : <><span className="mono">{p.file}</span><div className="note">{p.fileNote}</div></>, noF)}
          {node(3, 'Table / sheet', noF || !p.table ? fv(null) : <><span className="mono">{p.table}</span><div className="note">column <span className="mono">{p.column}</span></div></>, noF || !p.table)}
          {node(4, 'Row', U || !p.record ? fv(null) : <>{p.record}<div className="note">row {(p.row ?? 0).toLocaleString()} of {(p.rowsTotal ?? 0).toLocaleString()}</div></>, U || !p.record)}
          {node(5, 'Data', U ? fv(null) : <b>{p.value}</b>, U)}
          {node(6, 'Fetch time', U ? fv(null) : <><span className="num">{p.fetchedAt && isoT(p.fetchedAt)}</span><div className="note">{p.request}</div></>, U)}
          {node(7, 'Processing', U ? fv(null) : <ol style={{ margin: 0, paddingLeft: 16 }}>{(p.processing || []).map((x, j) => <li key={j}>{x}</li>)}</ol>, U)}
          {node(8, 'Evidence', <><b>{e.label}</b> {U ? <span className="chip bad">missing</span> : <span className={'chip ' + (e.state === 'ready' ? 'ok' : 'warn')}>{e.state}</span>}{!U && <div className="note">Used in: {p.usedIn.join('; ')}</div>}</>, false)}
        </ol>
      </>
    ),
  });
}
/** The evidence snapshot: what was known when the decision was made, with each item's provenance (ACT.snapshot). */
export function openSnapshot(ui: CaseUi, c: CaseRec, a: CaseAnalysis) {
  if (!c.snapshot) return toast('No decision yet, so no evidence snapshot exists.');
  const ps = a.provenance as FullProv[], full = ps.filter((p) => p.status === 'available').length;
  ui.modal({
    title: 'Evidence snapshot', sub: `${c.id} · ${c.snapshot.id}`, wide: true, drawer: true,
    foot: <a className="btn" href="#/audit" onClick={() => ui.modal(null)}>Open audit log for {c.id}</a>,
    body: (
      <>
        <div className="callout info">Immutable record of what was known when the decision was made. Retraining or new evidence creates a new snapshot; it never overwrites this one.</div>
        <dl className="kv" style={{ margin: '14px 0' }}>
          <dt>Snapshot</dt><dd>{c.snapshot.id}</dd><dt>Taken</dt><dd>{isoT(a.snapshot_time)}</dd><dt>Policy · models</dt><dd>POL-3.2 · {c.model} family</dd>
          <dt>Provenance</dt><dd><b>{full}</b> of {ps.length} items with full provenance{ps.length - full ? `; ${ps.length - full} partial or unavailable` : ''}</dd>
        </dl>
        {c.evidence.map((e, i) => (
          <details key={e.k} className="dd prov" open>
            <summary>
              <span className={'ev ' + e.state} style={{ display: 'inline-grid', verticalAlign: 'middle', border: 0, padding: 0, marginRight: 8 }}><span className="ic">{e.state === 'ready' ? '✓' : '!'}</span></span>
              <b>{e.label}</b> <ProvChip p={ps[i]} />
            </summary>
            <div style={{ padding: '4px 0 14px' }}>
              <ProvTable p={ps[i]} />
              <div className="row" style={{ marginTop: 8 }}><button className="btn sm" onClick={() => openTrace(ui, c, a, e.k)}>View Data Trace</button><span className="note">{ps[i].id}</span></div>
            </div>
          </details>
        ))}
      </>
    ),
  });
}
/** Source records behind each input (ACT.sources). */
export function openSources(ui: CaseUi, c: CaseRec) {
  ui.modal({
    title: 'Source records', sub: `${c.id} · ${c.assetId}`, drawer: true,
    body: (
      <>
        <p className="ink2" style={{ marginTop: 0 }}>Every input keeps its source system, record reference, observation and retrieval time, freshness, completeness and confidence.</p>
        <div className="tw">
          <table className="t static">
            <thead><tr><th>Input</th><th>Source</th><th>Record</th><th>Observed</th><th>Fresh</th><th className="r">Compl.</th><th className="r">Conf.</th></tr></thead>
            <tbody>
              {c.evidence.map((e, i) => {
                const h = parseInt(hashId(c.id + e.k).slice(0, 4), 16), miss = e.state === 'missing';
                return (
                  <tr key={e.k}>
                    <td>{e.label.replace(/ (available|verified|retrieved|checked|current)$/, '')}</td><td>{e.source}</td>
                    <td className="num">{miss ? '—' : ['WO', 'INS', 'REC', 'CFG', 'TST', 'IMG'][i % 6] + '-' + (20000 + h)}</td>
                    <td className="num">{miss ? '—' : fmtD(addDays(asOf(), -(h % 5)))}</td><td>{miss ? '—' : e.fresh}</td>
                    <td className="r num">{miss ? '—' : 85 + (h % 15) + '%'}</td><td className="r num">{miss ? '—' : 80 + (h % 19) + '%'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </>
    ),
  });
}
const pct = (n: number, d = 0) => (n * 100).toFixed(d) + '%';
function ModelRows() {
  let rows;
  try {
    rows = modelVersions().map((m) => ({ m, s: modelStats(m.v) }));
  } catch (e) {
    if (e instanceof ApiError) return <p className="note">Validation figures are on the Analytics page.</p>;
    throw e;
  }
  return (
    <table className="t static">
      <thead><tr><th>Version</th><th className="r">Closed</th><th className="r">Error (MAPE)</th><th className="r">Bias</th><th className="r">P10–P90 coverage</th></tr></thead>
      <tbody>
        {rows.map(({ m, s }) => (
          <tr key={m.v}>
            <td><b>{m.v}</b><div className="note">{fmtDY(m.released)}</div></td>
            <td className="r num">{s ? s.n : '—'}</td><td className="r num">{s ? pct(s.mape, 1) : '—'}</td>
            <td className={'r num ' + (s && s.bias < 0 ? 'neg' : '')}>{s ? (s.bias * 100).toFixed(1) + '%' : '—'}</td><td className="r num">{s ? pct(s.cov) : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
/** Model versions and their validation against actual outcomes (ACT.models). */
export function openModels(ui: CaseUi) {
  ui.modal({
    title: 'Model versions and validation', sub: 'Compared with actual outcomes', drawer: true,
    foot: canPage('analytics') ? <a className="btn pri" href="#/analytics" onClick={() => ui.modal(null)}>Open Analytics</a> : undefined,
    body: (
      <>
        <p className="ink2" style={{ marginTop: 0 }}>Each prediction names its model version. Error shrinks as outcomes feed back; early versions were optimistic.</p>
        <Suspense fallback={<p className="note">Loading…</p>}><ModelRows /></Suspense>
        <div className="note" style={{ margin: '10px 0' }}>Negative bias: the model over-predicted. Overrides and pending cases are excluded.</div>
      </>
    ),
  });
}
