/** Dialogs: New workflow, Delete, a run's details and the failed records (wfNewRender, wfDelAsk, frRunView, frFailed). */
import { useState } from 'react';
import { fmtNumber } from '../../api/format';
import { can } from '../../api/session';
import {
  createWorkflow, deleteWorkflow, deliverOf, failedRows, graphOf, history, readableSources, runCounts, runFigures, runQuality, RUN_CHIP, RUN_LABEL,
  runTimes, sourceExists, sourceLabel, source, stepInfo, templates, workflow, writableSources, type TestRun,
} from '../../api/workflows';
import { Icon } from '../../components/Icon';
import { Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { refused } from '../../hooks/useAction';
import { forget } from './draftStore';
import { download } from '../../utils/download';
import { WorkflowStatus } from './WorkflowMarks';
import { fromTemplate, reprocess } from './workflowActions';

type NewType = 'ingest' | 'out' | 'dec' | 'blank';
const CH_NAME: Record<string, string> = { api: 'Outbound API call', event: 'Event trigger', file: 'Interface file', proc: 'Process orchestration' };

/** Where business rules live: Workflow Studio builds connection workflows only (P9-0.16). */
export function ModelerLink({ text }: { text?: string }) {
  return <a className="lnk" href="#/modeler"><Icon name="branch" /> {text ?? 'Open the Modeler'}</a>;
}

/** The type picker of New workflow: the decision type stays listed for the demo's three graphs, read only. */
export function TypePicker({ type, onChange }: { type: string; onChange: (v: string) => void }) {
  return (
    <div className="fld">
      <label htmlFor="nwType">Workflow type</label>
      <select id="nwType" value={type} onChange={(e) => onChange(e.target.value)}>
        <option value="ingest">Ingest pipeline · one source system into a canonical model</option>
        <option value="out">Outbound instruction · one target system</option>
        <option value="dec" disabled>Decision workflow (demo, read only) · business rules live in the Modeler</option>
        <option value="blank">Blank pipeline</option>
      </select>
      <div className="hint" data-testid="nwDecNote">Decision workflows are demo only and read only. Business rules live in the Modeler. <ModelerLink /></div>
    </div>
  );
}

export function NewWorkflowModal({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const first = readableSources().find((s) => s.read.length) ?? readableSources()[0];
  const [n, setN] = useState<{ type: NewType; src: string; ch: string; name: string }>({ type: 'ingest', src: first?.id ?? '', ch: 'api', name: '' });
  const list = n.type === 'ingest' ? readableSources() : writableSources();
  const chs = deliverOf(n.src).length ? deliverOf(n.src) : ['api'];
  const vendor = sourceExists(n.src) ? source(n.src).vendor : '';
  const auto = n.type === 'ingest' ? 'Ingest · ' + vendor : n.type === 'out' ? 'Outbound · ' + vendor : n.type === 'dec' ? 'Decision workflow' : 'New pipeline';

  function change(k: 'type' | 'src' | 'ch', v: string) {
    const x = { ...n, [k]: v };
    if (k === 'type') {
      const l = v === 'ingest' ? readableSources() : writableSources();
      if (!l.some((s) => s.id === x.src)) x.src = l[0]?.id ?? '';
    }
    if (k === 'type' || k === 'src') x.ch = (deliverOf(x.src)[0] ?? 'api');
    setN(x);
  }

  async function create() {
    const r = await createWorkflow({ type: n.type, src: n.src || '', ch: n.ch || '', name: n.name || '' });
    if (refused(r, 4200)) return;
    toast(r.output.name + ' created as a draft with only the blocks it needs to run. Add more from the palette, then Save and Publish.');
    onCreated(r.output.id);
  }
  async function pickTpl(id: string) {
    const nid = await fromTemplate(id);
    if (nid) onCreated(nid);
  }
  const tpls = templates();

  return (
    <Modal title="New workflow" onClose={onClose}
      foot={<><button className="btn ghost" onClick={onClose}>Cancel</button><button className="btn pri" onClick={create}>Create workflow</button></>}>
      <TypePicker type={n.type} onChange={(v) => change('type', v)} />
      {(n.type === 'ingest' || n.type === 'out') && (
        <div className="fld">
          <label htmlFor="nwSrc">{n.type === 'ingest' ? 'Source system' : 'Target system'}</label>
          <select id="nwSrc" value={n.src} onChange={(e) => change('src', e.target.value)}>
            {list.map((s) => <option key={s.id} value={s.id}>{sourceLabel(s)} · {s.vendor}</option>)}
          </select>
        </div>
      )}
      {n.type === 'out' && (
        <div className="fld">
          <label htmlFor="nwCh">Delivery method</label>
          <select id="nwCh" value={n.ch} onChange={(e) => change('ch', e.target.value)}>
            {chs.map((c) => <option key={c} value={c}>{CH_NAME[c]}</option>)}
          </select>
        </div>
      )}
      <div className="fld">
        <label htmlFor="nwName">Name</label>
        <input id="nwName" value={n.name} placeholder={auto} maxLength={80} onChange={(e) => setN({ ...n, name: e.target.value })} />
      </div>
      {tpls.length > 0 && <>
        <h4 style={{ margin: '14px 0 6px' }}>Your templates</h4>
        <div className="row">{tpls.map((t) => <button key={t.id} className="btn sm" onClick={() => pickTpl(t.id)}><Icon name="file" /> {t.name}</button>)}</div>
      </>}
    </Modal>
  );
}

export function DeleteModal({ id, onClose, onDeleted }: { id: string; onClose: () => void; onDeleted: () => void }) {
  const w = workflow(id);
  if (!w) return null;
  async function del() {
    const r = await deleteWorkflow(id);
    if (refused(r, 4200)) return;
    forget(id);
    toast(r.output.name + ' deleted.');
    onDeleted();
  }
  return (
    <Modal title={'Delete ' + w.name + '?'} onClose={onClose}
      foot={<><button className="btn ghost" onClick={onClose}>Cancel</button><button className="btn danger" onClick={del}>Delete workflow</button></>}>
      <p style={{ marginTop: 0 }}>This removes <b>{w.name}</b> ({w.id}, v{w.ver}) and stops its trigger. Source systems and run history are not affected.</p>
      {w.status === 'published' && <div className="callout">This workflow is published. Anything that depends on its trigger will stop running.</div>}
    </Modal>
  );
}

const stamp = (ts: number, o?: Intl.DateTimeFormatOptions) => new Date(ts).toLocaleString('en-GB', o);

export function RunViewModal({ id, runId, onClose, onFailed }: { id: string; runId: string; onClose: () => void; onFailed: () => void }) {
  const w = workflow(id);
  if (!w) return null;
  const H = history(id), at = H.findIndex((x) => x.id === runId), r = at >= 0 ? H[at] : undefined;
  const g = graphOf(id), run = w.lastRun && w.lastRun.id === runId ? w.lastRun : null;
  // the run's real figures (the same held records as the Runs table and View failed records); none for a seeded run
  const f = at >= 0 ? runFigures(id)[at] : undefined, fig = f?.real && r?.state !== 'running' ? f : null;
  const n = (v: number | null | undefined) => (v == null ? '—' : fmtNumber(v));
  const latest = !!run && runQuality(id)?.key === run.key; // View failed records lists the latest real run's records
  const T = run ? runTimes(run as unknown as TestRun) : null, c = runCounts(id, g, null), L = RUN_LABEL(), C = RUN_CHIP();
  return (
    <Modal title={w.name + ' · ' + runId} wide onClose={onClose}
      foot={<><button className="btn" onClick={onClose}>Close</button>{w.src && latest && <button className="btn" onClick={onFailed}>View failed records</button>}</>}>
      <dl className="frdl">
        <dt>Status</dt><dd><WorkflowStatus k={r?.state === 'failed' ? 'failed' : 'success'} /></dd>
        <dt>Started</dt><dd>{stamp(r?.ts ?? Date.now())}</dd>
        <dt>Duration</dt><dd>{r?.dur ?? '—'} s</dd>
        <dt>Triggered by</dt><dd>{r?.trig ?? '—'}</dd>
        {r?.note && <><dt>Reason</dt><dd>{r.note}</dd></>}
        {fig && <><dt>Records (in / out)</dt><dd className="num">{n(fig.in)} / {n(fig.out)}</dd><dt>Held</dt><dd className="num">{n(fig.held)}</dd></>}
      </dl>
      {run ? (
        <>
          <h4>Steps</h4>
          <div className="tw"><table className="t static tight">
            <thead><tr><th>Step</th><th>State</th><th className="r">Duration</th><th className="r">In</th><th className="r">Out</th></tr></thead>
            <tbody>{run.order.map((sid) => {
              const nd = g.nodes.find((x) => x.id === sid);
              if (!nd) return null;
              const st = run.states[sid], cc = c[sid] ?? { in: 0, out: 0 };
              return <tr key={sid}><td>{stepInfo(nd).label}</td><td><span className={'chip ' + (C[st] ?? 'line')}>{L[st] ?? st}</span></td>
                <td className="r num">{T && T[sid]?.ex ? T[sid].d + ' s' : '—'}</td><td className="r num">{fmtNumber(cc.in || 0)}</td><td className="r num">{fmtNumber(cc.out || 0)}</td></tr>;
            })}</tbody>
          </table></div>
        </>
      ) : <p className="note">Step timings are kept for the latest run; earlier runs keep their totals.</p>}
    </Modal>
  );
}

export function FailedRecordsModal({ id, onClose }: { id: string; onClose: () => void }) {
  const w = workflow(id);
  if (!w) return null;
  const L = failedRows(id), held = runQuality(id)?.held ?? L.length; // records (a record held on two fields is one)
  function csv() {
    const q = (v: string) => (/[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v);
    const rows = [['record', 'field', 'value', 'rule'], ...L.map((r) => [r.rec, r.field, r.value, r.rule])];
    download(w!.id + '-failed-records.csv', rows.map((r) => r.map(q).join(',')).join('\n'), 'text/csv');
    toast('Failed records exported as CSV.');
  }
  const done = w.frReproc;
  async function reproc() {
    if (await reprocess(id)) onClose();
  }
  return (
    <Modal title={'Failed records · ' + w.name} wide onClose={onClose}
      foot={<>
        <button className="btn" onClick={onClose}>Close</button>
        <button className="btn" onClick={csv} disabled={!L.length}><Icon name="download" /> Export CSV</button>
        {can('manageWorkflows') && <button className="btn pri" onClick={reproc} disabled={!L.length}>Reprocess</button>}
      </>}>
      {L.length ? (
        <>
          <p className="note" style={{ marginTop: 0 }}>{fmtNumber(held)} record{held === 1 ? '' : 's'} from the latest run broke a validation rule. They are held by the error handler, not dropped.{L.length >= 40 && ' The first 40 rows are listed.'}{done && <> <b>Reprocessed {done}.</b></>}</p>
          <div className="tw"><table className="t static tight">
            <thead><tr><th>Record</th><th>Field</th><th>Value</th><th>Rule broken</th></tr></thead>
            <tbody>{L.map((r, i) => <tr key={i}><td className="mono">{r.rec}</td><td className="mono">{r.field}</td><td className="mono">{r.value || <span className="note">(empty)</span>}</td><td>{r.rule}</td></tr>)}</tbody>
          </table></div>
        </>
      ) : <div className="empty"><b>No failed records</b>The latest run had no invalid rows.</div>}
    </Modal>
  );
}
