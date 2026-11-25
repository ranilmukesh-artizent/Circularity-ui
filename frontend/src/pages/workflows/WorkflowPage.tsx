/** A workflow's own page (frWfPage): header, Workflow studio · Settings · History · Documentation. */
import { useCallback, useEffect, useRef, useState, type PointerEvent as RPointerEvent } from 'react';
import { useNavigate } from 'react-router';
import { fmtNumber } from '../../api/format';
import { useBackend } from '../../api/useBackend';
import { can } from '../../api/session';
import { sessionScoped } from '../../api/view';
import {
  ago, hashId, history, mergeChecks, nowMs, NOWF, publishedVersion, publishWorkflow, republishVer, runCounts, runErrors, runFigures,
  runFromLast, runOrder, runQuality, saveWorkflow, savedOf, serverChecks, setWorkflowStatus, type Check, sourceCategoryLabel,
  stepInfo, systemOf, templateOf, testRunWorkflow, trigText, usedBy, validate, wfStat, workflow, WF_H, WF_W, type TestRun, type Trigger, type Workflow,
} from '../../api/workflows';
import { Icon } from '../../components/Icon';
import type { GraphApi } from '../../components/graph/GraphView';
import { autoLayout as layout } from '../../components/graph/layout';
import { openAsk } from '../../utils/askBus';
import { toast } from '../../components/toast';
import { refused, useAction } from '../../hooks/useAction';
import { draftOf, edit, reload, setPin, undoRedo, useDrafts, type Draft } from './draftStore';
import { CanvasView, canvasOps, ChecksPanel, Inspector, Palette, TaskInstances, type Sel } from './Canvas';
import { IconTile } from '../../components/kit/IconTile';
import { Panel } from '../../components/kit/Panel';
import { Ring } from '../../components/kit/Ring';
import { Segmented } from '../../components/kit/Segmented';
import { useTick } from '../../hooks/useTick';
import { QuickActions, WorkflowMenu } from './WorkflowMenus';
import { SourceMark, WorkflowStatus } from './WorkflowMarks';
import { DeleteModal, FailedRecordsModal, RunViewModal } from './WorkflowModals';
import { VersionsPanel } from './VersionsPanel';
import { applyFix, duplicate, exportOne, runNow, saveTemplate, studioHref } from './workflowActions';
import { errorLog, failedAfter, retriesOf } from './investigation';

type Tab = 'studio' | 'settings' | 'history' | 'docs';
type View = 'overview' | 'details' | 'flow';
type ModalState = { k: 'del' } | { k: 'run'; run: string } | { k: 'failed' } | null;
const TRIGS: [string, string][] = [['schedule', 'On a schedule'], ['event', 'On event'], ['approval', 'On approval'], ['file', 'On file arrival'], ['case', 'On case request'], ['manual', 'Manual only']];
const stamp = (ts: number) => new Date(ts).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
/** The demo keeps the open tab across workflows (S.frWfTab) and the canvas view (S.frWfView). */
const keptView = sessionScoped<View>(() => 'details');

export function WorkflowPage({ id, query }: { id: string; query: URLSearchParams }) {
  useBackend();
  useDrafts();
  useTick(1000);
  const nav = useNavigate();
  const d = draftOf(id), wf = workflow(id);
  if (!d || !wf) {
    return (
      <div className="empty"><b>No workflow {id}</b>It may have been deleted. <button className="lnk" onClick={() => nav(studioHref())}>All workflows</button></div>
    );
  }
  return <Loaded key={id} w={wf} d={d} query={query} />;
}

function Loaded({ w, d, query }: { w: Workflow; d: Draft; query: URLSearchParams }) {
  const nav = useNavigate();
  const mgr = can('manageWorkflows');
  const [tab, setTab] = useState<Tab>('studio');
  const [sel, setSel] = useState<Sel>(null);
  const [view, setView0] = useState<View>(keptView.current);
  const setView = (v: View) => { keptView.current = v; setView0(v); };
  const [mini, setMini] = useState(true);
  const [wide, setWide] = useState(false);
  const [modal, setModal] = useState<ModalState>(null);
  const [ghost, setGhost] = useState<{ label: string; x: number; y: number } | null>(null);
  const apiRef = useRef<GraphApi | null>(null);
  const checksRef = useRef<HTMLDivElement>(null);

  // ---- the test run, painted on the canvas; starts from the workflow's last real run. A test run is a dry run of the
  //      draft on the server (workflow.testRun, plan 6 C9): real records through every step, nothing written.
  const runRef = useRef<TestRun | null | undefined>(undefined);
  if (runRef.current === undefined) runRef.current = runFromLast(w.id);
  const [, setRunV] = useState(0);
  const action = useAction();
  const paint = () => setRunV((x) => x + 1);
  const lastSeen = useRef(w.lastRun?.id);
  // a real run that finishes while no test run is shown is painted, like the demo
  useEffect(() => {
    if (w.lastRun?.id !== lastSeen.current) {
      lastSeen.current = w.lastRun?.id;
      if (!runRef.current) { runRef.current = runFromLast(w.id); paint(); }
    }
  });
  const run = runRef.current ?? null;
  const clearRun = useCallback(() => { runRef.current = null; paint(); }, []);

  const g = d.graph;
  // the server's full checks for this draft (live sources, the fields records really carry) merged with the browser's:
  // asked 600 ms after the last edit, and again before Validate, Test run and Publish (plan 6 follow-up, G2)
  const gStamp = JSON.stringify(g);
  const [srv, setSrv] = useState<Check[] | null>(null);
  const asked = useRef('');
  const checkOnServer = useCallback(async (graph: typeof g): Promise<Check[] | null> => {
    const stamp = JSON.stringify(graph);
    asked.current = stamp;
    const c = await serverChecks(w.id, graph);
    if (asked.current === stamp && c) setSrv(c); // a later edit asked again: its answer wins
    return c;
  }, [w.id]);
  useEffect(() => {
    const t = setTimeout(() => { void checkOnServer(JSON.parse(gStamp)); }, 600);
    return () => clearTimeout(t);
  }, [gStamp, checkOnServer]);
  const checks = mergeChecks(validate(g, w.kind), srv, g);
  /** The checks with a fresh server answer for the draft as it is now (the button's moment, not the last debounce). */
  const checksNow = async (): Promise<Check[]> => mergeChecks(validate(g, w.kind), (await checkOnServer(g)) ?? srv, g);
  const firstErr = (er: Check[]) => (er.length ? ' First: ' + er[0].msg : '');
  // a test run carries the records that really went in and out of each step
  const counts = run?.counts ?? runCounts(w.id, g, run ? run.states : null);
  const ops = canvasOps(d, w.kind, setSel, clearRun);

  /** Run the draft dry on the server; `approved` continues past Human approval (a dry run stops there: held). */
  async function dryRun(approved: boolean, prev?: TestRun) {
    const order = runOrder(g), now = nowMs();
    const r: TestRun = {
      status: 'running', states: Object.fromEntries(order.map((x) => [x, prev && prev.states[x] !== 'waiting' && prev.states[x] !== 'held' ? prev.states[x] : 'queued'])),
      dur: prev ? { ...prev.dur } : {}, order, i: 0, approved, t0: prev?.t0 ?? now, id: prev?.id ?? 'RUN-' + hashId(w.id + now).slice(0, 5).toUpperCase(), trig: 'Manual', dry: true,
    };
    runRef.current = r;
    paint();
    // records pinned on a step (Pin this input) start the run from that step
    const pin = Object.entries(d.pins).find(([id, recs]) => recs.length && g.nodes.some((n) => n.id === id));
    const res = await testRunWorkflow(w.id, g, approved, undefined, pin ? { node_id: pin[0], records: pin[1] } : undefined);
    if (runRef.current !== r) return; // cleared, or a new run started, while the server ran it
    if (refused(res, 4200)) { runRef.current = null; paint(); return; }
    const o = res.output;
    Object.assign(r, { status: o.status, states: o.states, dur: o.dur, order: o.order, i: o.order.length, counts: o.counts, samples: o.samples, rows: o.rows, held: o.held, note: o.note });
    paint();
    if (o.status !== 'held') toast('Test run ' + (o.status === 'failed' ? 'failed' : 'finished') + ': ' + fmtNumber(o.rows) + ' records' + (o.note ? '. ' + o.note : '') + '. Nothing was written.', 4200);
  }
  async function testRun() {
    const er = (await checksNow()).filter((x) => x.sev === 'error'), e = er.length;
    if (e) { toast(`Fix ${e} error${e > 1 ? 's' : ''} before running. The checks below say what and why.` + firstErr(er), 6000); scrollChecks(); return; }
    if (tab !== 'studio') setTab('studio');
    void dryRun(false);
  }
  function approve() {
    const r = runRef.current;
    if (!r || r.status !== 'held') return;
    // a test run is a dry run: whoever may run it approves its simulated Human approval; nothing is sent
    if (r.dry ? !mgr : !can('approve')) return toast(r.dry ? NOWF() : 'Your role cannot approve. Switch to Approver to continue the run.');
    void dryRun(true, r);
    toast('Approved in the test run. Simulated approval (dry run): nothing is sent to any system.');
  }
  const scrollChecks = () => checksRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });

  async function validateNow() {
    const all = await checksNow();
    const e = all.filter((x) => x.sev === 'error').length, wn = all.filter((x) => x.sev === 'warn').length;
    toast(e ? `${e} error${e > 1 ? 's' : ''} to fix before this can run.` : wn ? `No errors. ${wn} warning${wn > 1 ? 's' : ''} to review.` : 'No errors or warnings. This workflow is ready to run.');
    if (tab === 'studio') scrollChecks();
  }

  // ---- save, publish, discard, reset, back
  /** What was just saved: the copy keeps it until the backend's newer graph arrives (with the API it comes a moment later). */
  const kept = (): Partial<Draft> => ({ graph: d.graph, name: d.name, owner: d.owner, trig: d.trig, retries: d.retries, alert: d.alert, hist: { s: [JSON.stringify(d.graph)], i: 0 } });
  const body = () => ({ id: w.id, name: d.name, owner: d.owner, trig: d.trig, graph: d.graph, note: w.aiNote || '', retries: d.retries, alert: d.alert });
  async function save() {
    if (!mgr) return toast(NOWF());
    if (!d.name.trim()) return toast('Enter a workflow name before saving.');
    const r = await action.run(() => saveWorkflow(body()), 4200);
    if (!r.ok) return;
    reload(w.id, kept());
    toast(r.output.name + ' saved as v' + r.output.ver + '.');
  }
  async function publish() {
    if (!mgr) return toast(NOWF());
    if (w.status === 'published') {
      const r = await action.run(() => setWorkflowStatus(w.id, 'draft'), 4200);
      if (r.ok) toast(d.name + ' unpublished. It will no longer run on its trigger.');
      return;
    }
    const er = (await checksNow()).filter((x) => x.sev === 'error');
    if (er.length) { toast('Cannot publish: ' + er.length + ' error' + (er.length > 1 ? 's' : '') + ' in the checks. Fix them first.' + firstErr(er), 6000); scrollChecks(); return; }
    if (d.dirty) {
      // the name, owner and trigger are part of the change, so they are saved with the graph first
      if (!d.name.trim()) return toast('Enter a workflow name before saving.');
      const s = await action.run(() => saveWorkflow(body()), 4200);
      if (!s.ok) return;
    }
    const r = await action.run(() => publishWorkflow(w.id));
    if (!r.ok) { if (/error/.test(r.error.message)) scrollChecks(); return; }
    reload(w.id, kept());
    toast(r.output.name + ' published as v' + r.output.ver + '. It runs on its trigger: ' + r.output.trig + '.');
  }
  /** Publish v{x}: a published workflow's newer saved version (not the unsaved draft), as History's Publish does. */
  async function republish() {
    if (!mgr) return toast(NOWF());
    const r = await action.run(() => publishWorkflow(w.id), 4200);
    if (!r.ok) { if (/error/.test(r.error.message)) scrollChecks(); return; }
    toast(`v${r.output.ver} published. Runs now use it.` + (d.dirty ? ' Your unsaved changes are still a draft: save and publish them to run them.' : ''));
  }
  const newer = republishVer(w), pubVer = publishedVersion(w.id);
  function discard() {
    const s = savedOf(w.id);
    if (!s) return;
    clearRun();
    setSel(null);
    reload(w.id, { graph: s.graph, name: s.name, owner: s.owner, trig: s.trig, retries: s.retries ?? 3, alert: s.alert || 'A run fails', hist: { s: [JSON.stringify(s.graph)], i: 0 } });
    toast('Changes discarded. Back to v' + w.ver + '.');
  }
  function reset() {
    clearRun();
    setSel(null);
    edit(w.id, (dd) => { dd.graph = templateOf(w.id); }, { track: true });
    toast('Workflow reset to its template. Save to keep it.');
  }
  function back() {
    if (d.dirty && !d.warned) {
      edit(w.id, (dd) => { dd.warned = true; }, { dirty: true });
      return toast('You have unsaved changes. Save or Discard them, or choose All workflows again to leave them unsaved.');
    }
    edit(w.id, (dd) => { dd.warned = false; }, { dirty: d.dirty });
    nav(studioHref());
  }
  const meta = (f: (x: Draft) => void) => edit(w.id, f);
  /** A run setting (ACT.frWfSet): kept in the copy, so Save sends it with the workflow. */
  const setRun = (f: (x: Draft) => void) => { meta(f); toast('Saved with the workflow.'); };
  async function dup() {
    const nid = await duplicate(w.id);
    if (nid) nav(studioHref(nid));
  }

  // ---- canvas tools
  /** dagre lays every step out left to right (components/graph/layout.ts), then the view fits. */
  function autoLayout() {
    const pos = layout(g.nodes.map((n) => ({ id: n.id, w: WF_W, h: WF_H })), g.edges);
    edit(w.id, (dd) => {
      dd.graph.nodes.forEach((n) => { const p = pos[n.id]; if (p) { n.x = Math.max(0, Math.round(p.x / 8) * 8); n.y = Math.max(0, Math.round(p.y / 8) * 8); } });
    }, { track: true });
    clearRun();
    toast('Steps laid out left to right in run order.');
    setTimeout(() => apiRef.current?.fit(), 50);
  }
  function pick(nid: string) {
    const n = g.nodes.find((x) => x.id === nid);
    if (!n) return;
    setSel({ t: 'n', id: nid });
    apiRef.current?.center(n.x + WF_W / 2, n.y + WF_H / 2);
    document.getElementById('wfView')?.scrollIntoView({ block: 'nearest' });
  }
  function toggleFail(nid: string) {
    edit(w.id, (dd) => { const n = dd.graph.nodes.find((x) => x.id === nid); if (n) n.fail = !n.fail; }, { dirty: d.dirty });
    clearRun();
  }

  // ---- palette: drag onto the canvas, or click / Enter to add at a free spot
  function palDown(e: RPointerEvent, key: string, label: string) {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    const sx = e.clientX, sy = e.clientY, touch = e.pointerType === 'touch';
    let moved = false;
    const move = (ev: PointerEvent) => {
      if (!moved && Math.hypot(ev.clientX - sx, ev.clientY - sy) < 6) return;
      if (touch) return;
      moved = true;
      setGhost({ label, x: ev.clientX, y: ev.clientY });
    };
    const end = (ev: PointerEvent) => {
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', end);
      document.removeEventListener('pointercancel', cancel);
      setGhost(null);
      if (!moved) return ops.add(key);
      const api = apiRef.current, r = api?.bounds();
      if (api && r && ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom) {
        const p = api.screenToFlow({ x: ev.clientX, y: ev.clientY });
        ops.add(key, p.x - WF_W / 2, p.y - WF_H / 2);
      }
    };
    const cancel = () => {
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', end);
      document.removeEventListener('pointercancel', cancel);
      setGhost(null);
    };
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', end);
    document.addEventListener('pointercancel', cancel);
  }

  const s = systemOf(w), l = w.last, stat = wfStat(w);
  const invest = query.get('run') === 'last' || (l && l.state === 'failed');
  const phone = typeof window !== 'undefined' && window.innerWidth <= 860;

  const head = (
    <>
      <nav className="frbc" aria-label="Breadcrumb">
        <span>Integration</span><Icon name="chevR" /><span>Connection Fabric</span><Icon name="chevR" />
        <button className="lnk" onClick={back}>Workflow Studio</button><Icon name="chevR" /><b>{d.name}</b>
      </nav>
      <div className="wfbar frwfh">
        <button className="iconbtn" aria-label="All workflows" onClick={back}><Icon name="back" /></button>
        {s ? <SourceMark s={s} /> : <IconTile ic="bot" h="agent" cls="sm" />}
        <div className="wfname"><label className="sr" htmlFor="wfName">Workflow name</label>
          <input id="wfName" value={d.name} maxLength={80} onChange={(e) => meta((x) => { x.name = e.target.value; })} /></div>
        <span id="wfStat">{w.running ? <WorkflowStatus k="running" /> : <WorkflowStatus k={stat} />}</span>
        <span className="note num">{w.id} · v{w.ver}</span>
        {newer && pubVer && <span className="chip y" id="wfPubVer" title={`Runs use v${pubVer}. Publish v${newer} from More actions to make runs use it.`}>Runs v{pubVer} · v{newer} not published</span>}
        {l && <span className="note">Last run {ago(nowMs() - l.ts)}</span>}
        <span id="wfDirty">{d.dirty && <span className="chip y">Unsaved changes</span>}</span>
        <span className="grow" />
        <WorkflowMenu summaryCls="btn" summary={<>More actions <Icon name="chevD" /></>}>
          {mgr && <button role="menuitem" id="wfSaveB" disabled={!d.dirty} onClick={save}><Icon name="check" /><span>Save</span></button>}
          <button role="menuitem" id="wfDiscB" disabled={!d.dirty} onClick={discard}><Icon name="undo" /><span>Discard changes</span></button>
          <button role="menuitem" onClick={reset}><Icon name="rotate" /><span>Reset to template</span></button>
          {mgr && newer && <button role="menuitem" id="wfRepubB" onClick={republish}><Icon name="upload" /><span>Publish v{newer}</span></button>}
          {mgr && <button role="menuitem" onClick={publish}><Icon name="upload" /><span>{w.status === 'published' ? 'Unpublish' : 'Publish'}</span></button>}
          {mgr && <button role="menuitem" onClick={dup}><Icon name="copy" /><span>Duplicate</span></button>}
          {mgr && <button role="menuitem" onClick={() => saveTemplate(w.id)}><Icon name="file" /><span>Save as template</span></button>}
          <button role="menuitem" onClick={() => exportOne(w.id)}><Icon name="download" /><span>Export JSON</span></button>
          {mgr && <button role="menuitem" className="dng" onClick={() => setModal({ k: 'del' })}><Icon name="trash" /><span>Delete</span></button>}
        </WorkflowMenu>
        <button className="btn" onClick={validateNow}><Icon name="checks" /> Validate</button>
        <button className="btn" onClick={testRun}><Icon name="play" /> Test run</button>
        {mgr && <button className="btn pri" onClick={() => runNow(w.id)}><Icon name="play" /> Run now</button>}
      </div>
      <p className="note frwfd">{w.desc}</p>
      <Segmented name="wftab" label="Workflow sections" cur={tab} onPick={setTab}
        items={[['studio', 'Workflow studio'], ['settings', 'Settings'], ['history', 'History'], ['docs', 'Documentation']]} />
    </>
  );

  const modals = (
    <>
      {modal?.k === 'del' && <DeleteModal id={w.id} onClose={() => setModal(null)} onDeleted={() => { setModal(null); nav(studioHref()); }} />}
      {modal?.k === 'run' && <RunViewModal id={w.id} runId={modal.run} onClose={() => setModal(null)} onFailed={() => setModal({ k: 'failed' })} />}
      {modal?.k === 'failed' && <FailedRecordsModal id={w.id} onClose={() => setModal(null)} />}
    </>
  );

  if (tab === 'settings') {
    // a Scheduler or Event trigger block on the canvas sets the trigger (the server reads it the same way: triggers.from_graph)
    const tb = d.graph.nodes.find((n) => n.k === 'xf' && (n.ref === 'x_sched' || n.ref === 'x_evtrig'));
    const evType = tb?.ref === 'x_evtrig' && typeof tb.cfg?.event_type === 'string' ? tb.cfg.event_type.trim() : '';
    const bt: Trigger | null = !tb ? null : tb.ref === 'x_sched' ? { t: 'schedule', min: Number(tb.cfg?.interval_min ?? 60) } : { t: 'event' };
    const t = bt ?? d.trig;
    const byBlock = tb ? 'Set by the ' + (tb.ref === 'x_sched' ? 'Scheduler' : 'Event trigger') + ' block' + (evType ? ' (event type ' + evType + ')' : '') + '.' : '';
    return (
      <>{head}
        <Panel title="Settings">
          <div className="wfset frwset">
            <div className="fld"><label htmlFor="wfTrig">Trigger</label>
              <select id="wfTrig" value={t.t} disabled={!!bt} aria-describedby={bt ? 'wfTrigBy' : undefined} onChange={(e) => meta((x) => { x.trig = (e.target.value === 'schedule' ? { t: 'schedule', min: 15 } : { t: e.target.value }) as Trigger; })}>
                {TRIGS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              {bt && <div className="note" id="wfTrigBy">{byBlock}</div>}</div>
            {t.t === 'schedule' && <div className="fld" style={{ width: 120 }}><label htmlFor="wfMin">Every (min)</label>
              {bt ? <input id="wfMin" type="number" value={t.min} readOnly disabled aria-describedby="wfTrigBy" />
                : <input id="wfMin" type="number" min={1} max={1440} defaultValue={t.min} onChange={(e) => { const m = +e.target.value; if (m >= 1 && m <= 1440) meta((x) => { x.trig = { t: 'schedule', min: m }; }); }} />}</div>}
            <div className="fld"><label htmlFor="wfOwn">Owner (role or team)</label>
              <input id="wfOwn" value={d.owner} maxLength={60} onChange={(e) => meta((x) => { x.owner = e.target.value; })} /></div>
            <div className="fld"><label htmlFor="frRetry">Retries</label>
              <select id="frRetry" value={String(d.retries)} onChange={(e) => setRun((x) => { x.retries = +e.target.value; })}>
                {[0, 1, 3, 5].map((n) => <option key={n}>{n}</option>)}
              </select></div>
            <div className="fld"><label htmlFor="frAlert">Alert when</label>
              <select id="frAlert" value={d.alert} onChange={(e) => setRun((x) => { x.alert = e.target.value; })}>
                {['A run fails', 'Two runs fail in a row', 'Success rate drops below 95%', 'Never'].map((o) => <option key={o}>{o}</option>)}
              </select></div>
          </div>
          <p className="note">Changes are saved with the workflow; publish to apply them to the running version.</p>
        </Panel>
        {modals}
      </>
    );
  }
  if (tab === 'history') {
    return <>{head}<VersionsPanel w={w} dirty={d.dirty} /><Panel title="Runs" sub="Every run of this workflow that happened, latest first"><RunsTable w={w} n={100} onView={(r) => setModal({ k: 'run', run: r })} /></Panel>{modals}</>;
  }
  if (tab === 'docs') {
    const o = runOrder(g);
    return (
      <>{head}
        <Panel title="Documentation" right={<button className="btn sm" onClick={() => openAsk(`Explain the workflow ${w.name} (${w.id}).`)}><Icon name="spark" /> Explain this workflow</button>}>
          <div className="frdoc">
            <p>{w.desc}</p>
            <p className="note">Generated from the workflow graph · {g.nodes.length} steps, {g.edges.length} links · {trigText(d.trig)} · owner {d.owner}</p>
            <ol>{o.map((sid) => {
              const n = g.nodes.find((x) => x.id === sid)!, i = stepInfo(n);
              const nx = g.edges.filter((e) => e.a === sid).map((e) => g.nodes.find((x) => x.id === e.b)).filter(Boolean).map((x) => stepInfo(x!).label);
              return <li key={sid}><b>{i.label}</b> <span className="chip line">{i.tag}</span><p>{i.desc}{nx.length ? ' Then: ' + nx.join(', ') + '.' : ''}</p></li>;
            })}</ol>
          </div>
        </Panel>
        {modals}
      </>
    );
  }

  const toolbar = (
    <div className="frcvt" role="toolbar" aria-label="Canvas tools">
      <button className="iconbtn sm" id="frUndo" aria-label="Undo" disabled={d.hist.i <= 0} onClick={() => { undoRedo(w.id, -1); clearRun(); }}><Icon name="undo" /></button>
      <button className="iconbtn sm" id="frRedo" aria-label="Redo" disabled={d.hist.i >= d.hist.s.length - 1} onClick={() => { undoRedo(w.id, 1); clearRun(); }}><Icon name="redo" /></button>
      <button className="btn sm" onClick={autoLayout}>Auto layout</button>
      <button className="iconbtn sm" aria-label="Show or hide the minimap" onClick={() => setMini((m) => !m)}><Icon name="minimap" /></button>
      <span className="grow" />
      <Segmented name="wfview" label="Canvas view" cur={view} onPick={setView} items={[['overview', 'Overview'], ['details', 'Details'], ['flow', 'Data flow']]} />
      <button className="btn sm cxwb" aria-pressed={wide} onClick={() => setWide((x) => !x)}>{wide ? 'Show panels' : 'Expand canvas'}</button>
    </div>
  );
  const hasInsp = !!sel && (sel.t === 'n' ? g.nodes.some((n) => n.id === sel.id) : g.edges.some((e) => e.id === sel.id));

  return (
    <>
      {head}
      {invest && l && l.state === 'failed' && <Investigation w={w} mgr={mgr} onRun={() => runNow(w.id)} />}
      <div className={'frwfg' + (wide ? ' cxwide' : '')}>
        <div className={'wf frwf' + (hasInsp ? '' : ' noinsp') + (phone ? ' ro' : '')} data-view={view}>
          <Palette w={w} onDown={palDown} onKeyAdd={(k) => ops.add(k)} />
          <CanvasView w={w} d={d} sel={sel} run={run} checks={checks} counts={counts} flow={view === 'flow'} mini={mini} readOnly={phone}
            onSel={setSel} ops={ops} changed={clearRun} apiRef={apiRef} toolbar={toolbar} />
          <Inspector d={d} sel={sel} checks={checks} ops={ops} onFail={toggleFail} run={run} onPin={(id, recs) => { setPin(w.id, id, recs); toast(recs.length ? 'Input pinned. The next test run starts from this step.' : 'Input unpinned.'); }} />
        </div>
        <aside className="frwfr"><Details w={w} d={d} mgr={mgr} onDup={dup} onDelete={() => setModal({ k: 'del' })} /></aside>
      </div>
      <div className="frwfb">
        <Panel title="Recent runs" right={<button className="lnk" onClick={() => setTab('history')}>View all →</button>}>
          <div id="frRuns"><RunsTable w={w} n={5} onView={(r) => setModal({ k: 'run', run: r })} /></div>
        </Panel>
        <Panel title="Data quality (latest run)"><div id="frDq"><DataQuality w={w} run={run} onFailed={() => setModal({ k: 'failed' })} /></div></Panel>
      </div>
      <div className="wfbot" ref={checksRef}>
        <ChecksPanel g={g} checks={checks} onPick={pick} />
        <TaskInstances g={g} run={run} retries={retriesOf(run?.id === w.lastRun?.id ? w.lastRun : undefined, d)} onPick={pick} onApprove={approve} onClear={clearRun} />
      </div>
      {ghost && <div className="wfghost" style={{ left: ghost.x, top: ghost.y }}>{ghost.label}</div>}
      {modals}
    </>
  );
}

// ---------------------------------------------------------------- panels
function RunsTable({ w, n, onView }: { w: Workflow; n: number; onView: (run: string) => void }) {
  const L = history(w.id).slice(0, n), F = runFigures(w.id);
  if (!L.length) return <div className="empty"><b>No runs yet</b>Runs appear here once the workflow is published and its trigger fires.</div>;
  const seeded = L.some((_, i) => F[i] && !F[i].real);
  const num = (v: number | null | undefined) => (v == null ? '—' : fmtNumber(v));
  return (
    <>
      <div className="tw"><table className="t static tight">
        <thead><tr><th>Run ID</th><th>Status</th><th>Start time</th><th className="r">Duration</th><th className="r">Records (in / out)</th><th className="r">Held</th><th>Triggered by</th><th /></tr></thead>
        <tbody>{L.map((r, i) => {
          // a run still in progress (the API's worker job) has no duration or record count yet. A run that happened in
          // the app shows the server's figures (its held records are the ones View failed records lists); a seeded run
          // of the demo's history keeps the demo's estimate (as the Monitor keeps its seeded figures)
          const f = F[i], going = r.state === 'running';
          const est = f && !f.real ? runErrors(w.id, r) : 0;
          const rin = f?.real ? f.in : r.rows, held = going ? null : f?.real ? f.held : est;
          const out = going ? null : f?.real ? f.out : r.state === 'failed' ? 0 : r.rows - est;
          return (
            <tr key={r.id + r.ts} className={r.state === 'failed' ? 'frfail' : ''}>
              <td className="mono">{r.id}</td><td><WorkflowStatus k={r.state === 'failed' ? 'failed' : going ? 'running' : 'success'} /></td>
              <td className="num nowrap">{stamp(r.ts)}</td><td className="r num">{going || r.dur == null ? '—' : r.dur + ' s'}</td>
              <td className="r num">{going || rin == null ? '—' : fmtNumber(rin) + ' / ' + num(out)}</td>
              <td className={'r num ' + (held ? 'neg' : '')}>{num(held)}</td><td>{r.trig}</td>
              <td><button className="btn sm" onClick={() => onView(r.id)}>View</button></td>
            </tr>
          );
        })}</tbody>
      </table></div>
      {seeded && <p className="note" id="frRunsSeeded">Seeded runs from the demo's history never ran in the app: their out and held figures are the demo's estimate.</p>}
    </>
  );
}

/** The latest real run's records read, passed and held, and the fields its held records failed on most (the server's
 *  `quality`: the same held records as the Runs table and View failed records). A dry test run on the canvas shows its
 *  own figures, labelled as such; a workflow that never ran in the app has none. */
function DataQuality({ w, run, onFailed }: { w: Workflow; run: TestRun | null; onFailed: () => void }) {
  const q = runQuality(w.id);
  const ring = (tot: number, held: number, l: string) => (
    <Ring segs={[{ v: Math.max(0, tot - held), c: 'var(--ok)', l: 'Passed' }, { v: held, c: 'var(--bad)', l }]}
      center={tot ? ((Math.max(0, tot - held) / tot) * 100).toFixed(1) + '%' : '—'} sub="valid records" />
  );
  const failed = <div className="row" style={{ marginTop: 10 }}><button className="btn sm" disabled={!q?.held} onClick={onFailed}>View failed records ({fmtNumber(q?.held ?? 0)})</button></div>;
  if (run?.dry && run.status !== 'running' && run.rows != null) {
    return (
      <>
        <p className="note" id="frDqDry" style={{ marginTop: 0 }}><b>Test run (dry)</b>: {fmtNumber(run.rows)} sampled records, {fmtNumber(run.held ?? 0)} would be held. Nothing was written.</p>
        {ring(run.rows, run.held ?? 0, 'Would be held')}
        {q && <p className="note">Latest real run {q.run}: {fmtNumber(q.held)} held.</p>}
        {failed}
      </>
    );
  }
  if (!q) return <div className="empty"><b>No real run yet</b>The figures appear after the workflow's first run in the app.</div>;
  const by = new Map<string, { n: number; rules: string[] }>();
  q.groups.forEach((x) => { const e = by.get(x.field) ?? { n: 0, rules: [] }; e.n += x.n; if (!e.rules.includes(x.rule)) e.rules.push(x.rule); by.set(x.field, e); });
  const flds = [...by].sort((a, b) => b[1].n - a[1].n).slice(0, 5), top = flds.length ? flds[0][1].n : 1;
  return (
    <>
      <p className="note" style={{ marginTop: 0 }}>Run {q.run}{q.state === 'failed' ? ' (failed)' : ''}: {q.in == null ? 'no records counted' : fmtNumber(q.in) + ' records read'}.</p>
      {ring(q.in ?? 0, q.held, 'Held')}
      {flds.length > 0 && <>
        <h4 style={{ margin: '14px 0 6px' }}>Fields that failed most</h4>
        {flds.map(([f, e]) => (
          <div key={f} className="meter"><span className="mono" title={'Rules: ' + e.rules.join(', ')} style={{ width: 150, overflow: 'hidden', textOverflow: 'ellipsis' }}>{f}</span>
            <div className="bar"><i style={{ width: (e.n / top) * 100 + '%' }} /></div><b className="num" style={{ width: 40, textAlign: 'right' }}>{fmtNumber(e.n)}</b></div>
        ))}
      </>}
      {failed}
    </>
  );
}

function Details({ w, d, mgr, onDup, onDelete }: { w: Workflow; d: Draft; mgr: boolean; onDup: () => void; onDelete: () => void }) {
  const nav = useNavigate();
  const s = systemOf(w), every = d.trig.t === 'schedule' ? d.trig.min ?? null : null;
  const tags = [w.cat, s ? sourceCategoryLabel(s) : 'Decision', s?.short, w.status === 'published' ? 'Production' : 'Draft'].filter((x, i, a): x is string => !!x && a.indexOf(x) === i);
  const uses = s ? usedBy(s.id).length : 0;
  const qa = [
    ...(mgr ? [{ l: 'Duplicate workflow', ic: 'copy', on: onDup }, { l: 'Save as template', ic: 'file', on: () => saveTemplate(w.id) }] : []),
    { l: 'Export (JSON)', ic: 'download', on: () => exportOne(w.id) },
    ...(mgr ? [{ l: 'Delete workflow', ic: 'trash', on: onDelete }] : []),
  ];
  return (
    <>
      <Panel title="Workflow details" id="frWfDet">
        <dl className="frdl">
          <dt>Name</dt><dd>{w.name}</dd><dt>Description</dt><dd className="note">{w.desc}</dd><dt>Version</dt><dd>v{w.ver}</dd>
          <dt>Status</dt><dd><WorkflowStatus k={wfStat(w)} /></dd><dt>Owner</dt><dd>{w.owner}</dd><dt>Trigger</dt><dd>{trigText(w.trig)}</dd>
          <dt>Last run</dt><dd>{w.last ? <>{stamp(w.last.ts)} <WorkflowStatus k={w.last.state === 'failed' ? 'failed' : 'success'} /></> : '—'}</dd>
          <dt>Next run</dt><dd>{every && w.last && w.status === 'published' ? new Date(w.last.ts + every * 60000).toTimeString().slice(0, 5) : '—'}</dd>
          <dt>Success rate (24 h)</dt><dd>{w.runsN ? Math.round((w.okN / w.runsN) * 100) + '%' : '—'}</dd>
          <dt>Average duration</dt><dd>{w.last ? w.last.dur + ' s' : '—'}</dd>
        </dl>
      </Panel>
      <Panel title="Tags"><div className="row">{tags.map((t) => <span key={t} className="chip line">{t}</span>)}</div></Panel>
      {s && (
        <Panel title="Related systems">
          <div className="frrel"><SourceMark s={s} /><span><b>{s.vendor}</b><span className="note mono">{s.url || '—'}</span><span className="note">Used by {uses} workflow{uses === 1 ? '' : 's'}</span></span><WorkflowStatus k={s.status === 'live' ? 'live' : s.status} /></div>
          <button className="lnk" onClick={() => nav('/integration/map?src=' + encodeURIComponent(s.id))}>Open connection →</button>
        </Panel>
      )}
      <Panel title="Quick actions" cls="frwqa"><QuickActions rows={qa} /></Panel>
    </>
  );
}

function Investigation({ w, mgr, onRun }: { w: Workflow; mgr: boolean; onRun: () => void }) {
  const r = w.lastRun, bad = r?.order.find((x) => r.states[x] === 'failed'), g = draftOf(w.id)!.graph, n = bad ? g.nodes.find((x) => x.id === bad) : undefined;
  if (!r || !n) return null;
  const i = stepInfo(n), q = runQuality(w.id), tries = retriesOf(r, w);
  const mine = q && r.key && q.key === r.key ? q : null; // the held records of this run (a seeded run has none)
  const soon = () => openAsk(`Why did ${w.name} (${w.id}) fail at ${i.label} in run ${r.id}, and how do I fix it?`);
  return (
    <section className="panel frinvp" id="frInvest">
      <div className="ph">
        <div><h3><Icon name="alert" /> Investigation · {r.id}</h3><span className="note">{i.label} {failedAfter(tries)} · {ago(nowMs() - r.ts)}</span></div>
        <span className="row">
          <button className="btn sm" onClick={soon}><Icon name="spark" /> Diagnose</button>
          <button className="btn sm" onClick={soon}><Icon name="spark" /> Fix</button>
          {mgr && <button className="btn sm pri" onClick={onRun}><Icon name="play" /> Run now</button>}
        </span>
      </div>
      <div className="pb frinvg">
        <div><h4>Error log</h4><pre className="frlog">{errorLog(tries, r, i.label)}</pre></div>
        <div><h4>Held records</h4>
          {!mine ? <p className="note">This failed run is the demo's seeded history: nothing was held for real. Run now to see what a real run holds.</p>
            : mine.groups.length ? (
              <table className="t static tight"><thead><tr><th>Step</th><th>Field</th><th>Rule</th><th className="r">Records</th></tr></thead>
                <tbody>{mine.groups.map((x) => <tr key={x.step + x.field + x.rule}><td>{x.label}</td><td className="mono">{x.field}</td><td>{x.rule}</td><td className="r num neg">{fmtNumber(x.n)}</td></tr>)}</tbody></table>
            ) : <p className="note">The run held no records.</p>}
          {w.frFix
            ? <p className="callout ok" style={{ marginTop: 8 }}><b>Fix applied.</b> {w.frFix} Run now to confirm.</p>
            : mgr && <button className="btn sm" style={{ marginTop: 8 }} onClick={() => applyFix(w.id)}>Apply the suggested fix</button>}
        </div>
      </div>
    </section>
  );
}

