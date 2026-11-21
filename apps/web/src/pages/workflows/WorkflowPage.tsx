/** A workflow's own page (frWfPage): header, Workflow studio · Settings · History · Documentation. */
import { useCallback, useEffect, useRef, useState, type PointerEvent as RPointerEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { fmtNumber } from '../../api/format';
import { useBackend } from '../../api/useBackend';
import { can } from '../../api/session';
import { sessionScoped } from '../../api/view';
import {
  ago, analyze, evalStep, hashId, history, mappings, nowMs, NOWF, publishWorkflow, runCounts, runErrors,
  runFromLast, runOrder, saveWorkflow, savedOf, setWorkflowStatus, sourceCategoryLabel, sourceCompleteness,
  stepInfo, systemOf, templateOf, trigText, usedBy, validate, wfStat, workflow, WF_H, WF_W, WF_WH, worldWidth, type TestRun, type Trigger, type Workflow,
} from '../../api/workflows';
import { Icon } from '../../ui/Icon';
import { openAsk } from '../../ui/askBus';
import { toast } from '../../ui/toast';
import { useAction } from '../../ui/useAction';
import { draftOf, edit, reload, undoRedo, useDrafts, type Draft } from './draftStore';
import { CanvasView, canvasOps, ChecksPanel, FIXMSG, Inspector, Palette, TaskInstances, type Sel } from './Canvas';
import { IconTile } from '../../ui/kit/IconTile';
import { Panel } from '../../ui/kit/Panel';
import { Ring } from '../../ui/kit/Ring';
import { Segmented } from '../../ui/kit/Segmented';
import { useTick } from '../../ui/useTick';
import { QuickActions, WorkflowMenu } from './WorkflowMenus';
import { SourceMark, WorkflowStatus } from './WorkflowMarks';
import { DeleteModal, FailedRecordsModal, RunViewModal } from './WorkflowModals';
import { applyFix, duplicate, exportOne, runNow, saveTemplate, studioHref } from './workflowActions';
import { errorLog, failedAfter, retriesOf } from './investigation';

type Tab = 'studio' | 'settings' | 'history' | 'docs';
type View = 'overview' | 'details' | 'flow';
type ModalState = { k: 'del' } | { k: 'run'; run: string } | { k: 'failed' } | null;
const TRIGS: [string, string][] = [['schedule', 'On a schedule'], ['event', 'On event'], ['approval', 'On approval'], ['file', 'On file arrival'], ['case', 'On case request'], ['manual', 'Manual only']];
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
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
  const [z, setZ] = useState(0.72);
  const [view, setView0] = useState<View>(keptView.current);
  const setView = (v: View) => { keptView.current = v; setView0(v); };
  const [mini, setMini] = useState(true);
  const [wide, setWide] = useState(false);
  const [modal, setModal] = useState<ModalState>(null);
  const [ghost, setGhost] = useState<{ label: string; x: number; y: number } | null>(null);
  const viewRef = useRef<HTMLDivElement>(null);
  const checksRef = useRef<HTMLDivElement>(null);

  // ---- the test run (wfRun / wfStep), painted on the canvas; starts from the workflow's last real run
  const runRef = useRef<TestRun | null | undefined>(undefined);
  if (runRef.current === undefined) runRef.current = runFromLast(w.id);
  const timer = useRef(0);
  const [, setRunV] = useState(0);
  const action = useAction();
  const paint = () => setRunV((x) => x + 1);
  const lastSeen = useRef(w.lastRun?.id);
  useEffect(() => () => window.clearTimeout(timer.current), [w.id]);
  // a real run that finishes while no test run is shown is painted, like the demo
  useEffect(() => {
    if (w.lastRun?.id !== lastSeen.current) {
      lastSeen.current = w.lastRun?.id;
      if (!runRef.current) { runRef.current = runFromLast(w.id); paint(); }
    }
  });
  const run = runRef.current ?? null;
  const clearRun = useCallback(() => { window.clearTimeout(timer.current); runRef.current = null; paint(); }, []);

  const g = d.graph;
  const checks = validate(g, w.kind);
  const counts = runCounts(w.id, g, run ? run.states : null);
  const ops = canvasOps(d, w.kind, setSel, clearRun);
  const WW = worldWidth(w.kind);

  function step() {
    const r = runRef.current;
    if (!r || r.status !== 'running') return;
    const gg = draftOf(w.id)!.graph;
    if (r.i >= r.order.length) { r.status = Object.values(r.states).some((s) => s === 'failed') ? 'failed' : 'success'; paint(); return; }
    const sid = r.order[r.i], n = gg.nodes.find((x) => x.id === sid)!, st = evalStep(r, gg, n), quick = ['upstream_failed', 'waiting', 'skipped'].includes(st);
    if (!quick) { r.states[sid] = 'running'; paint(); }
    timer.current = window.setTimeout(() => {
      if (runRef.current !== r) return;
      r.states[sid] = st;
      if (st === 'held') { r.status = 'held'; analyze(gg).desc(sid).forEach((x) => (r.states[x] = 'waiting')); paint(); return; }
      r.i++;
      paint();
      step();
    }, quick ? 25 : 320);
  }
  function testRun() {
    const e = checks.filter((x) => x.sev === 'error').length;
    if (e) { toast(`Fix ${e} error${e > 1 ? 's' : ''} before running. The checks below say what and why.`); scrollChecks(); return; }
    clearRun();
    const order = runOrder(g), dur: Record<string, string> = {}, now = nowMs();
    order.forEach((x) => (dur[x] = (0.2 + (hashId(x + w.id).charCodeAt(0) % 20) / 10).toFixed(1)));
    const r: TestRun = { status: 'running', states: {}, dur, order, i: 0, approved: false, t0: now, id: 'RUN-' + hashId(w.id + now).slice(0, 5).toUpperCase(), trig: 'Manual' };
    order.forEach((x) => (r.states[x] = 'queued'));
    runRef.current = r;
    if (tab !== 'studio') setTab('studio');
    paint();
    step();
  }
  function approve() {
    const r = runRef.current;
    if (!r || r.status !== 'held') return;
    if (!can('approve')) return toast('Your role cannot approve. Switch to Approver to continue the run.');
    r.approved = true;
    r.status = 'running';
    step();
    toast('Approved in the test run. No instruction is sent to any system.');
  }
  const scrollChecks = () => checksRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });

  function validateNow() {
    const e = checks.filter((x) => x.sev === 'error').length, wn = checks.filter((x) => x.sev === 'warn').length;
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
    const er = checks.filter((x) => x.sev === 'error');
    if (er.length) { toast('Cannot publish: ' + er.length + ' error' + (er.length > 1 ? 's' : '') + ' in the checks. Fix them first.'); scrollChecks(); return; }
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
  // stable for a workflow (Loaded is keyed by id, so WW never changes in one instance): the fit below runs only when
  // the canvas is expanded, never on a later render, so a manual zoom stays
  const zoom = useCallback((a: number) => {
    if (a === 0) { const v = viewRef.current; setZ(clamp(Math.floor(((v ? v.clientWidth : 1000) - 8) / WW * 100) / 100, 0.5, 1.2)); }
    else setZ((x) => clamp(Math.round((x + a * 0.1) * 10) / 10, 0.5, 1.4));
  }, [WW]);
  useEffect(() => { if (wide) zoom(0); }, [wide, zoom]);
  function autoLayout() {
    const A = analyze(g), dep: Record<string, number> = {}, lay: Record<number, string[]> = {};
    runOrder(g).forEach((x) => (dep[x] = Math.max(0, ...A.pred[x].map((p) => (dep[p] || 0) + 1))));
    g.nodes.forEach((n) => (lay[dep[n.id] ?? 0] ??= []).push(n.id));
    const cols = Object.keys(lay).length, cw = Math.min(206, Math.floor((WW - WF_W - 48) / Math.max(1, cols - 1)));
    edit(w.id, (dd) => {
      Object.entries(lay).forEach(([k, l]) => l.forEach((nid, i) => {
        const n = dd.graph.nodes.find((x) => x.id === nid)!;
        n.x = 24 + +k * cw;
        n.y = clamp(Math.round((WF_WH / 2 - WF_H / 2 + (i - (l.length - 1) / 2) * 150) / 8) * 8, 8, WF_WH - WF_H - 8);
      }));
    }, { track: true });
    clearRun();
    toast('Steps laid out left to right in run order.');
  }
  function pick(nid: string) {
    const n = g.nodes.find((x) => x.id === nid);
    if (!n) return;
    setSel({ t: 'n', id: nid });
    const v = viewRef.current;
    if (v) { v.scrollTo({ left: Math.max(0, n.x * z - 80), top: Math.max(0, n.y * z - 120), behavior: 'smooth' }); v.scrollIntoView({ block: 'nearest' }); }
  }
  function toggleFail(nid: string) {
    edit(w.id, (dd) => { const n = dd.graph.nodes.find((x) => x.id === nid); if (n) n.fail = !n.fail; }, { dirty: d.dirty });
    clearRun();
  }

  // ---- keyboard: Delete removes, arrows move (Shift for 40 px)
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if (tab !== 'studio' || !sel || (e.target as Element).closest?.('input,select,textarea')) return;
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); ops.del(sel); return; }
      const m = ({ ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] } as Record<string, number[]>)[e.key];
      if (m && sel.t === 'n') {
        const n = g.nodes.find((x) => x.id === sel.id);
        if (!n) return;
        e.preventDefault();
        if (n.k === 'fixed') return toast(FIXMSG);
        const s = e.shiftKey ? 40 : 8;
        edit(w.id, (dd) => { const x = dd.graph.nodes.find((y) => y.id === n.id)!; x.x = clamp(x.x + m[0] * s, 0, WW - WF_W); x.y = clamp(x.y + m[1] * s, 0, WF_WH - WF_H); });
      }
    }
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  });

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
      const v = viewRef.current;
      if (!v) return;
      const r = v.getBoundingClientRect();
      if (ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom)
        ops.add(key, (ev.clientX - r.left + v.scrollLeft) / z - WF_W / 2, (ev.clientY - r.top + v.scrollTop) / z - WF_H / 2);
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
        {l && <span className="note">Last run {ago(nowMs() - l.ts)}</span>}
        <span id="wfDirty">{d.dirty && <span className="chip y">Unsaved changes</span>}</span>
        <span className="grow" />
        <WorkflowMenu summaryCls="btn" summary={<>More actions <Icon name="chevD" /></>}>
          {mgr && <button role="menuitem" id="wfSaveB" disabled={!d.dirty} onClick={save}><Icon name="check" /><span>Save</span></button>}
          <button role="menuitem" id="wfDiscB" disabled={!d.dirty} onClick={discard}><Icon name="undo" /><span>Discard changes</span></button>
          <button role="menuitem" onClick={reset}><Icon name="rotate" /><span>Reset to template</span></button>
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
    const t = d.trig;
    return (
      <>{head}
        <Panel title="Settings">
          <div className="wfset frwset">
            <div className="fld"><label htmlFor="wfTrig">Trigger</label>
              <select id="wfTrig" value={t.t} onChange={(e) => meta((x) => { x.trig = (e.target.value === 'schedule' ? { t: 'schedule', min: 15 } : { t: e.target.value }) as Trigger; })}>
                {TRIGS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></div>
            {t.t === 'schedule' && <div className="fld" style={{ width: 120 }}><label htmlFor="wfMin">Every (min)</label>
              <input id="wfMin" type="number" min={1} max={1440} defaultValue={t.min} onChange={(e) => { const m = +e.target.value; if (m >= 1 && m <= 1440) meta((x) => { x.trig = { t: 'schedule', min: m }; }); }} /></div>}
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
    return <>{head}<Panel title="History" sub="Every run of this workflow, latest first"><RunsTable w={w} n={100} onView={(r) => setModal({ k: 'run', run: r })} /></Panel>{modals}</>;
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
      <div className="wfzoom" role="group" aria-label="Zoom">
        <button aria-label="Zoom out" onClick={() => zoom(-1)}><Icon name="zout" /></button><span id="wfZ">{Math.round(z * 100)}%</span>
        <button aria-label="Zoom in" onClick={() => zoom(1)}><Icon name="zin" /></button><button aria-label="Fit to width" onClick={() => zoom(0)}><Icon name="max" /></button>
      </div>
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
          <CanvasView w={w} d={d} z={z} sel={sel} run={run} checks={checks} counts={counts} flow={view === 'flow'} mini={mini}
            onSel={setSel} ops={ops} changed={clearRun} viewRef={viewRef} toolbar={toolbar} />
          <Inspector d={d} sel={sel} checks={checks} ops={ops} onFail={toggleFail} />
        </div>
        <aside className="frwfr"><Details w={w} d={d} mgr={mgr} onDup={dup} onDelete={() => setModal({ k: 'del' })} /></aside>
      </div>
      <div className="frwfb">
        <Panel title="Recent runs" right={<button className="lnk" onClick={() => setTab('history')}>View all →</button>}>
          <div id="frRuns"><RunsTable w={w} n={5} onView={(r) => setModal({ k: 'run', run: r })} /></div>
        </Panel>
        <Panel title="Data quality (latest run)"><div id="frDq"><DataQuality w={w} counts={counts} onFailed={() => setModal({ k: 'failed' })} /></div></Panel>
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
  const L = history(w.id).slice(0, n);
  if (!L.length) return <div className="empty"><b>No runs yet</b>Runs appear here once the workflow is published and its trigger fires.</div>;
  return (
    <div className="tw"><table className="t static tight">
      <thead><tr><th>Run ID</th><th>Status</th><th>Start time</th><th className="r">Duration</th><th className="r">Records (in / out)</th><th className="r">Errors</th><th>Triggered by</th><th /></tr></thead>
      <tbody>{L.map((r) => {
        // a run still in progress (the API's worker job) has no duration or record count yet
        const going = r.state === 'running', rej = going ? 0 : runErrors(w.id, r);
        return (
          <tr key={r.id + r.ts} className={r.state === 'failed' ? 'frfail' : ''}>
            <td className="mono">{r.id}</td><td><WorkflowStatus k={r.state === 'failed' ? 'failed' : going ? 'running' : 'success'} /></td>
            <td className="num nowrap">{stamp(r.ts)}</td><td className="r num">{going ? '—' : r.dur + ' s'}</td>
            <td className="r num">{going ? '—' : fmtNumber(r.rows) + ' / ' + fmtNumber(r.state === 'failed' ? 0 : r.rows - rej)}</td>
            <td className={'r num ' + (rej ? 'neg' : '')}>{going ? '—' : fmtNumber(rej)}</td><td>{r.trig}</td>
            <td><button className="btn sm" onClick={() => onView(r.id)}>View</button></td>
          </tr>
        );
      })}</tbody>
    </table></div>
  );
}

function DataQuality({ w, counts, onFailed }: { w: Workflow; counts: Record<string, { in: number; out: number; rej: number }>; onFailed: () => void }) {
  const v = Object.values(counts).find((x) => x.rej > 0) ?? { in: w.last ? w.last.rows : 0, out: w.last ? w.last.rows : 0, rej: 0 };
  const tot = v.in || 0, err = v.rej, warn = w.src && systemOf(w)?.status === 'stale' ? Math.round(tot * 0.02) : 0, ok = Math.max(0, tot - err - warn);
  const compl = sourceCompleteness(w.src);
  const flds = mappings(w.src).slice(0, 5).map((m) => [m[0], Math.min(100, Math.max(60, (compl ?? 95) + 4 - (parseInt(hashId(w.id + m[0]), 16) % 7)))] as const);
  return (
    <>
      <Ring segs={[{ v: ok, c: 'var(--ok)', l: 'Valid' }, { v: warn, c: 'var(--h-dec)', l: 'Warnings' }, { v: err, c: 'var(--bad)', l: 'Errors' }]}
        center={tot ? ((ok / tot) * 100).toFixed(1) + '%' : '—'} sub="valid records" />
      {flds.length > 0 && <>
        <h4 style={{ margin: '14px 0 6px' }}>Field completeness</h4>
        {flds.map(([f, p]) => (
          <div key={f} className="meter"><span className="mono" style={{ width: 150, overflow: 'hidden', textOverflow: 'ellipsis' }}>{f}</span>
            <div className="bar"><i style={{ width: p + '%' }} /></div><b className="num" style={{ width: 40, textAlign: 'right' }}>{p}%</b></div>
        ))}
      </>}
      <div className="row" style={{ marginTop: 10 }}><button className="btn sm" disabled={!err} onClick={onFailed}>View failed records ({fmtNumber(err)})</button></div>
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
  const i = stepInfo(n), m = mappings(w.src).slice(0, 3), tries = retriesOf(r, w);
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
        <div><h4>Schema drift</h4>
          {m.length ? (
            <table className="t static tight"><thead><tr><th>Field</th><th>Expected</th><th>Received</th></tr></thead>
              <tbody>{m.map((f, k) => <tr key={k}><td className="mono">{f[0]}</td><td className="mono">{f[1]}</td><td className={'mono ' + (k === 0 ? 'neg' : '')}>{k === 0 ? f[1] + ' → renamed in source' : f[1]}</td></tr>)}</tbody></table>
          ) : <p className="note">No field-level drift recorded.</p>}
          {w.frFix
            ? <p className="callout ok" style={{ marginTop: 8 }}><b>Fix applied.</b> {w.frFix} Run now to confirm.</p>
            : mgr && <button className="btn sm" style={{ marginTop: 8 }} onClick={() => applyFix(w.id)}>Apply the suggested fix</button>}
        </div>
      </div>
    </section>
  );
}

