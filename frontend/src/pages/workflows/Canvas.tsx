/**
 * The Airflow-style canvas (the demo's wf* canvas code): palette, nodes and edges with drag to move, drag from the
 * right dot to connect, select and Delete, arrow keys, pan and zoom, minimap, inspector, checks and task instances.
 * The canvas itself is the shared GraphView (xyflow, P9-8.13); this file says what a step may do.
 * It edits the page's working copy (draftStore.ts); Save and Publish send it through invoke().
 */
import { useEffect, useState, type MutableRefObject, type PointerEvent as RPointerEvent, type ReactNode } from 'react';
import { fmtNumber } from '../../api/format';
import { can } from '../../api/session';
import {
  actTypes, agentsUsing, blockOperations, blockResources, blockSpecOf, nodeSettings, settingErrors, CH, channelsOf, deliverMap, deliverOf, fixedStep, frTransforms, mappings, mapTarget,
  NOWF, nowMs, RUN_CHIP, RUN_LABEL, runTimes, sourceGroups, sourceLabel, sources, source, sourceShortLabel, stepInfo, tools,
  transforms, canLink, WF_H, WF_W, WF_WH, worldWidth, type Check, type Counts, type RunState, type SampleRec, type TestRun, type WfGraph, type WfNode, type Workflow,
} from '../../api/workflows';
import { Icon } from '../../components/Icon';
import { onActivateKey } from '../../utils/keys';
import { toast } from '../../components/toast';
import { BlockSettings } from './BlockSettings';
import { edit, nextId, setCfg, type Draft } from './draftStore';
import { NodeSamples, nodeIo } from '../../components/graph/NodeSamples';
import { GraphView, type GEdge, type GNode, type GraphApi } from '../../components/graph/GraphView';
import { placeMissing } from '../../components/graph/layout';
import { StepNode, type StepData } from './StepNode';
import { GRIP_SVG, LOCK_SVG, SourceMark, StateChip, TileMark } from './WorkflowMarks';

export type Sel = { t: 'n' | 'e'; id: string } | null;
export const FIXMSG = 'Fixed steps belong to Circularity and cannot be moved or removed.';
const ICO: Partial<Record<RunState, string>> = { success: '✓', warning: '✓', failed: '✕', upstream_failed: '!', running: '…', held: '⏸' };
const POOL = (n: WfNode) => (n.k === 'conn' || n.k === 'wconn' ? 'source_pool' : n.k === 'xf' || n.k === 'map' ? 'transform_pool' : n.k === 'tool' ? 'agent_pool' : 'platform_pool');
const hms = (ms: number) => new Date(ms).toTimeString().slice(0, 8);
const DOT: Record<string, string> = { live: 'ok', stale: 'warn', manual: '', unavailable: 'bad' };

/** Shared canvas operations (wfAdd, wfLink, wfDel, wfDelEdge). `changed` clears the test run. */
export function canvasOps(d: Draft, kind: 'pipe' | 'dec', setSel: (s: Sel) => void, changed: () => void) {
  const WW = worldWidth(kind);
  function free() {
    for (let x = 24; x <= WW - WF_W - 24; x += 200)
      for (let y = 24; y <= WF_WH - WF_H - 24; y += 80)
        if (!d.graph.nodes.some((n) => Math.abs(n.x - x) < WF_W + 16 && Math.abs(n.y - y) < WF_H + 16)) return { x, y };
    return { x: 24, y: 24 };
  }
  return {
    add(key: string, x?: number, y?: number) {
      const [k, ref] = key.split(':') as [WfNode['k'], string];
      if (x == null || y == null) ({ x, y } = free());
      const n: WfNode = { id: '', k, ref, x: Math.max(0, Math.round(x / 8) * 8), y: Math.max(0, Math.round(y / 8) * 8) };
      edit(d.id, (dd) => { n.id = nextId(dd, 'n'); dd.graph.nodes.push(n); }, { track: true });
      changed();
      setSel({ t: 'n', id: n.id });
      toast(stepInfo(n).label + ' added. Drag from its right dot to connect it.');
    },
    link(a: string, b: string): boolean {
      const why = canLink(d.graph, a, b);
      if (why) { toast(why); return false; }
      edit(d.id, (dd) => dd.graph.edges.push({ id: nextId(dd, 'e'), a, b, locked: false }), { track: true });
      changed();
      setSel({ t: 'n', id: b });
      return true;
    },
    delEdge(id: string) {
      const e = d.graph.edges.find((x) => x.id === id);
      if (!e) return;
      if (e.locked) return toast('That connection is part of the fixed structure.');
      edit(d.id, (dd) => { dd.graph.edges = dd.graph.edges.filter((x) => x.id !== id); }, { track: true });
      setSel(null);
      changed();
    },
    del(sel: Sel) {
      if (!sel) return;
      if (sel.t === 'e') return this.delEdge(sel.id);
      const n = d.graph.nodes.find((x) => x.id === sel.id);
      if (!n) return;
      if (n.k === 'fixed') return toast(FIXMSG);
      edit(d.id, (dd) => {
        dd.graph.nodes = dd.graph.nodes.filter((x) => x.id !== n.id);
        dd.graph.edges = dd.graph.edges.filter((x) => x.a !== n.id && x.b !== n.id);
      }, { track: true });
      setSel(null);
      changed();
    },
  };
}

// ---------------------------------------------------------------- palette
function PalItem({ k, label, sub, icon, dot, onDown, onKey }: { k: string; label: string; sub: string; icon: ReactNode; dot?: string; onDown: (e: RPointerEvent, key: string, label: string) => void; onKey: (e: React.KeyboardEvent) => void }) {
  return (
    <button className="wfp frp2" data-pal={k} aria-label={'Add ' + label} onPointerDown={(e) => onDown(e, k, label)} onKeyDown={onKey}>
      {icon}<span className="tx"><span className="lb">{label}</span><span className="sb">{sub}</span></span>{dot != null && <span className={'dotc ' + dot} />}
    </button>
  );
}

export function Palette({ w, onDown, onKeyAdd }: { w: Workflow; onDown: (e: RPointerEvent, key: string, label: string) => void; onKeyAdd: (key: string) => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [q, setQ] = useState('');
  const ql = q.trim().toLowerCase();
  // keyboard: Enter / Space on a palette item adds it (the demo's click with detail 0)
  const keyAdd = (e: React.KeyboardEvent) => {
    const b = (e.target as HTMLElement).closest('.wfp') as HTMLElement | null;
    if (b && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onKeyAdd(b.dataset.pal!); }
  };
  const it = (key: string, label: string, sub: string, icon: ReactNode, dot?: string) =>
    !ql || (label + ' ' + sub).toLowerCase().includes(ql) ? <PalItem key={key} k={key} label={label} sub={sub} icon={icon} dot={dot} onDown={onDown} onKey={keyAdd} /> : null;

  if (w.kind !== 'pipe') {
    const def: Record<string, boolean> = { t_r: true, t_w: true };
    const sec = (k: string, h: string, items: ReactNode[]) => {
      const o = open[k] ?? !!def[k];
      return <div className="sec" key={k}><button className="wfh" aria-expanded={o} onClick={() => setOpen({ ...open, [k]: !o })}><span>{h}</span><span className="note">{items.length}</span></button>{o && items}</div>;
    };
    const old = (key: string, label: string, sub: string) => (
      <button key={key} className="wfp" data-pal={key} aria-label={'Add ' + label} onPointerDown={(e) => onDown(e, key, label)} onKeyDown={keyAdd}>
        <span className="grip">{GRIP_SVG}</span><span className="tx"><span className="lb">{label}</span><span className="sb">{sub}</span></span>
      </button>
    );
    return (
      <aside className="wfpal" id="wfPal" aria-label="Components. Drag one onto the canvas, or press Enter to add it.">
        {sec('t_r', 'Agent tools · read', tools().filter((t) => t.rw === 'read').map((t) => old('tool:' + t.id, t.id, 'Read')))}
        {sec('t_w', 'Agent tools · write', tools().filter((t) => t.rw === 'write').map((t) => old('tool:' + t.id, t.id, t.approval === 'human approval required' ? 'Needs approval' : 'Within agent scope')))}
      </aside>
    );
  }

  const grp = (k: string, h: string, body: ReactNode[]) => {
    const items = body.filter(Boolean);
    if (!items.length) return null;
    const o = ql ? true : open[k] ?? ['src_CRM', 'frT', 'frO'].includes(k);
    return <div className="sec" key={k}><button className="wfh" aria-expanded={o} onClick={() => setOpen({ ...open, [k]: !o })}><span>{h}</span></button>{o && items}</div>;
  };
  const XF = transforms(), FR = frTransforms();
  const XIC: Record<string, string> = { x_val: 'checks', x_utc: 'clock', x_fx: 'dollar', x_lookup: 'lookup', x_units: 'scale', x_ident: 'link', x_late: 'clock', x_env: 'shield', x_flag: 'alert' };
  const xf = (id: string) => {
    const x = XF.find((y) => y.id === id), f = FR.find((y) => y.id === id);
    if (!x) return null;
    return it('xf:' + id, x.label, x.sub, <TileMark ic={f?.ic ?? XIC[id] ?? 'workflow'} h={f?.group === 'orch' ? 'agent' : 'insp'} />);
  };
  const mapIc = <TileMark ic="mapping" h="money" />;
  const S = sources();
  return (
    <aside className="wfpal" id="wfPal" aria-label="Components. Drag one onto the canvas, or press Enter to add it.">
      <div className="frpals"><label className="sr" htmlFor="frPalQ">Search components</label><Icon name="search" />
        <input id="frPalQ" type="search" placeholder="Search components" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <h4 className="frpalh">Sources</h4>
      {sourceGroups().map(([key, types, label]) => {
        const l = S.filter((s) => types.includes(s.type));
        return l.length ? grp('src_' + key, label, l.map((s) => it('conn:' + s.id, sourceLabel(s), s.vendor, <SourceMark s={s} />, DOT[s.status]))) : null;
      })}
      <h4 className="frpalh">Transform</h4>
      {grp('frT', 'Transform steps', [
        ...(w.src ? [it('map:' + w.src, sourceShortLabel(w.src) + ' fields', 'Field mapping → ' + mapTarget(w.src), mapIc)] : []),
        ...['x_enrich', 'x_filter', 'x_agg', 'x_expr', 'x_lookup', 'x_join', 'x_val', 'x_utc', 'x_fx', 'x_units', 'x_ident', 'x_late', 'x_env', 'x_flag'].map(xf),
      ])}
      <h4 className="frpalh">Orchestration</h4>
      {grp('frO', 'Orchestration steps', ['x_sched', 'x_evtrig', 'x_branch', 'x_loop', 'x_call', 'x_wait'].map(xf))}
      {grp('frB', 'Branches', ['x_err', 'x_audit', 'x_pub', 'x_case'].map(xf))}
      <h4 className="frpalh">More</h4>
      {grp('ing', 'Integration layer', XF.filter((x) => x.group === 'ingest').map((x) => xf(x.id)))}
      {grp('file', 'File exchange steps', XF.filter((x) => x.group === 'file').map((x) => xf(x.id)))}
      {grp('act', 'Delivery methods', actTypes().map((x) => it('act:' + x.id, x.label, x.sub, <TileMark ic="send" h="money" />)))}
      {grp('wr', 'Write to a system', S.filter((x) => x.write.length).map((x) => it('wconn:' + x.id, sourceLabel(x), x.write[0], <SourceMark s={x} />, DOT[x.status])))}
      {grp('map', 'All field mappings', S.map((x) => it('map:' + x.id, sourceShortLabel(x.id) + ' fields', '→ ' + mapTarget(x.id), mapIc)))}
      <div className="frfixed"><b>{LOCK_SVG} Fixed Circularity steps</b><span className="note">Canonical models, evidence snapshot, decision and send instruction are placed by Circularity and cannot be re-wired or deleted.</span></div>
    </aside>
  );
}

// ---------------------------------------------------------------- canvas
const NODE_TYPES = { step: StepNode };

/** The canvas: the draft's steps and links on the shared GraphView (xyflow). Steps without coordinates are laid out with dagre and stored. */
export function CanvasView({ w, d, sel, run, checks, counts, flow, mini, readOnly, onSel, ops, changed, apiRef, toolbar }: {
  w: Workflow; d: Draft; sel: Sel; run: TestRun | null; checks: Check[]; counts: Record<string, Counts>; flow: boolean; mini: boolean; readOnly: boolean;
  onSel: (s: Sel) => void; ops: ReturnType<typeof canvasOps>; changed: () => void; apiRef: MutableRefObject<GraphApi | null>;
  toolbar: ReactNode;
}) {
  const g = d.graph;
  const missing = placeMissing(g.nodes.map((n) => ({ id: n.id, w: WF_W, h: WF_H, x: n.x, y: n.y })), g.edges);
  // a graph with no coordinates (generated, imported) is laid out once and the layout kept in the copy, without marking it changed
  useEffect(() => {
    if (!Object.keys(missing).length) return;
    edit(d.id, (dd) => { dd.graph.nodes.forEach((n) => { const p = missing[n.id]; if (p) { n.x = p.x; n.y = p.y; } }); }, { dirty: false });
  });

  const L = RUN_LABEL();
  const sevOf = (id: string) => {
    const sv = checks.filter((x) => x.id === id && x.sev !== 'info');
    return sv.some((x) => x.sev === 'error') ? 'error' : sv.length ? 'warn' : undefined;
  };
  const showCounts = !!(run || w.last);
  const color = (id: string) => {
    const n = g.nodes.find((x) => x.id === id), st = run?.states[id];
    return st === 'success' || st === 'warning' ? 'var(--ok)' : st === 'failed' ? 'var(--bad)' : st === 'upstream_failed' ? '#D9651E' : st === 'running' ? 'var(--yellow)' : n?.k === 'fixed' ? 'var(--ink)' : 'var(--mv-line)';
  };
  const gnodes: GNode[] = g.nodes.map((n) => {
    const st = run?.states[n.id], c = counts[n.id], p = missing[n.id] ?? n;
    const data: StepData = { n, st, stLabel: st ? L[st] : '', records: c && showCounts ? fmtNumber(c.out) + ' records' : '', io: c && run?.dry ? nodeIo(c) : undefined, pinned: !!d.pins[n.id]?.length, sev: sevOf(n.id) };
    return { id: n.id, x: p.x, y: p.y, w: WF_W, h: WF_H, type: 'step', data, selected: sel?.t === 'n' && sel.id === n.id, locked: n.k === 'fixed' };
  });
  const gedges: GEdge[] = g.edges.flatMap((e) => {
    const sa = run?.states[e.a], sb = run?.states[e.b], c = counts[e.a];
    if (!g.nodes.some((n) => n.id === e.a) || !g.nodes.some((n) => n.id === e.b)) return [];
    const st = sb === 'failed' ? 'bad' : sb === 'upstream_failed' ? 'up' : sb === 'running' ? 'run' : sa === 'success' || sa === 'warning' ? 'ok' : sa === 'failed' ? 'bad' : sa === 'upstream_failed' ? 'up' : '';
    return [{ id: e.id, a: e.a, b: e.b, selected: sel?.t === 'e' && sel.id === e.id, className: [e.locked ? 'lk' : '', st].join(' ').trim(), label: flow && c ? fmtNumber(c.out) : undefined }];
  });

  return (
    <div className="wfcanvas">
      {toolbar}
      <div className="wfview graphview" id="wfView">
        <GraphView nodes={gnodes} edges={gedges} nodeTypes={NODE_TYPES} readOnly={readOnly} minimap={mini} nodeColor={color} apiRef={apiRef}
          label="Workflow canvas. Select a step, then use arrow keys to move it or Delete to remove it."
          onSelect={onSel} onDelete={(s) => ops.del(s)} onConnect={(a, b) => { ops.link(a, b); }} onBlocked={() => toast(FIXMSG)}
          onMove={(id, x, y) => {
            edit(d.id, (dd) => {
              const n = dd.graph.nodes.find((q) => q.id === id);
              if (n) { n.x = Math.max(0, Math.round(x / 8) * 8); n.y = Math.max(0, Math.round(y / 8) * 8); }
            }, { track: true });
            changed();
          }}
          onNudge={(id, dx, dy) => {
            const n = g.nodes.find((q) => q.id === id);
            if (!n) return;
            if (n.k === 'fixed') return toast(FIXMSG);
            edit(d.id, (dd) => { const q = dd.graph.nodes.find((r) => r.id === id)!; q.x = Math.max(0, q.x + dx); q.y = Math.max(0, q.y + dy); });
          }} />
      </div>
      <div className="wflegend"><span><i className="f" />Fixed · owned by Circularity</span><span><i className="m" />Movable · yours to arrange</span><span><i className="fre" />Red · failed</span></div>
      <p className="frphone note">Read-only on a phone. Open on a larger screen to edit the canvas.</p>
    </div>
  );
}

// ---------------------------------------------------------------- inspector
export function Inspector({ d, sel, checks, ops, onFail, run, onPin }: { d: Draft; sel: Sel; checks: Check[]; ops: ReturnType<typeof canvasOps>; onFail: (id: string) => void; run?: TestRun | null; onPin?: (nodeId: string, records: SampleRec[]) => void }) {
  const g = d.graph;
  const node = (id: string) => g.nodes.find((n) => n.id === id);
  if (sel?.t === 'e') {
    const e = g.edges.find((x) => x.id === sel.id), a = e && node(e.a), b = e && node(e.b);
    if (e && a && b)
      return (
        <aside className="wfinsp" id="wfInsp"><div className="pb">
          <h3>Connection</h3><p><b>{stepInfo(a).label}</b> → <b>{stepInfo(b).label}</b></p>
          {e.locked ? <div className="callout">This connection belongs to the fixed structure of the workflow and cannot be removed.</div>
            : <div className="acts"><button className="btn sm" onClick={() => ops.delEdge(e.id)}>Remove connection</button></div>}
        </div></aside>
      );
  }
  const n = sel?.t === 'n' ? node(sel.id) : undefined;
  if (!n) return <aside className="wfinsp" id="wfInsp" />;
  const i = stepInfo(n), fx = n.k === 'fixed', mine = checks.filter((x) => x.id === n.id), ch = CH();
  let det: ReactNode = null;
  if (n.k === 'conn' || n.k === 'wconn') {
    const s = source(n.ref), wr = n.k === 'wconn';
    det = (
      <dl className="kv">
        <dt>Status</dt><dd><StateChip s={s.status} /></dd><dt>Mode</dt><dd>{s.mode}</dd><dt>Access</dt><dd>{s.auth}</dd>
        <dt>{wr ? 'Writes' : 'Reads'}</dt><dd>{(wr ? s.write : s.read).join(', ') || '—'}</dd>
        <dt>{wr ? 'Accepts' : 'Arrives as'}</dt><dd>{(wr ? deliverOf(n.ref).map((c) => ch.del[c]) : channelsOf(s).map((c) => ch.arr[c])).join(', ') || 'No supported channel'}</dd>
      </dl>
    );
  }
  if (n.k === 'xf') {
    const x = transforms().find((t) => t.id === n.ref);
    if (x?.ingest) det = <dl className="kv"><dt>Channel</dt><dd>{ch.ing[x.ingest]}</dd><dt>Sources that fit</dt><dd>{sources().filter((q) => channelsOf(q).includes(x.ingest!)).map((q) => sourceShortLabel(q.id)).join(', ')}</dd></dl>;
  }
  if (n.k === 'act') {
    const a = actTypes().find((t) => t.id === n.ref)!, dm = deliverMap();
    det = <dl className="kv"><dt>Accepted by</dt><dd>{Object.keys(dm).filter((k) => dm[k].includes(a.ch)).map(sourceShortLabel).join(', ')}</dd></dl>;
  }
  if (n.k === 'map') {
    const all = mappings(n.ref), m = all.slice(0, 5);
    det = m.length ? (
      <>
        <table className="t static"><thead><tr><th>Source</th><th>Canonical</th></tr></thead>
          <tbody>{m.map((r, k) => <tr key={k}><td className="mono">{r[0]}</td><td className="mono">{r[2]}</td></tr>)}</tbody></table>
        <div className="note" style={{ marginTop: 4 }}>{all.length} fields mapped. Rules are listed on the source adapter.</div>
      </>
    ) : <div className="callout bad">No field mapping exists for {sourceShortLabel(n.ref)} yet.</div>;
  }
  if (n.k === 'tool') {
    const t = tools().find((x) => x.id === n.ref)!, ag = agentsUsing(t.id);
    det = <dl className="kv"><dt>Type</dt><dd>{t.rw === 'write' ? 'Write' : 'Read'}</dd><dt>Approval</dt><dd>{t.approval}</dd><dt>Agents</dt><dd>{ag.join(', ') || 'None'}</dd></dl>;
  }
  const fields = fx ? fixedStep(n.ref)?.fields : undefined;
  if (fields) det = <div className="row" style={{ gap: 4, margin: '8px 0' }}>{fields.map((f) => <span key={f} className="chip line mono">{f}</span>)}</div>;
  const ins = g.edges.filter((e) => e.b === n.id), outs = g.edges.filter((e) => e.a === n.id);
  const opts = g.nodes.filter((x) => x.id !== n.id && !canLink(g, n.id, x.id));
  return (
    <aside className="wfinsp" id="wfInsp"><div className="pb">
      <div className="row" style={{ marginBottom: 6 }}><span className={'chip ' + (fx ? 'dk' : 'y')}>{fx ? 'Fixed' : 'Movable'}</span><span className="note">{i.tag.replace(/^Fixed · /, '')}</span></div>
      <h3>{i.label}</h3><p>{i.desc}</p>{det}
      <InspSection title="Settings">
        <BlockSettings key={n.id} nodeId={n.id} spec={blockSpecOf(n)} cfg={nodeSettings(n)} readonly={fx} errors={(f, v) => settingErrors(f, v, n)}
          resources={n.k === 'conn' ? blockResources()[n.ref] : undefined} operations={n.k === 'wconn' ? blockOperations()[n.ref] ?? [] : undefined}
          onChange={(k, v) => setCfg(d.id, n.id, k, v)} />
      </InspSection>
      {run?.dry && run.samples?.[n.id] && (
        <InspSection title="Records">
          <NodeSamples input={run.samples[n.id].before} output={run.samples[n.id].after} held={run.samples[n.id].held ?? []}
            onPin={onPin && n.k !== 'conn' ? (recs) => onPin(n.id, recs) : undefined} pinned={!!d.pins[n.id]?.length} />
        </InspSection>
      )}
      {mine.length > 0 && <InspSection title="Problems">{mine.map((m, k) => <div key={k} className={'callout ' + (m.sev === 'error' ? 'bad' : '')} style={{ marginBottom: 6 }}>{m.msg}</div>)}</InspSection>}
      <InspSection title="Connections">
        <EdgeList label="Receives from" edges={ins} name={(e) => stepInfo(node(e.a)!).label} none={!i.in ?'Nothing: this block starts the flow.' : 'Nothing yet. Connect a step into this one.'} onRemove={ops.delEdge} />
        {i.out && <EdgeList label="Sends to" edges={outs} name={(e) => stepInfo(node(e.b)!).label} none="Nothing yet. Choose the next step below." onRemove={ops.delEdge} />}
        {i.out && opts.length > 0 && <ConnectTo key={n.id} first={!outs.length} opts={opts.map((x) => ({ id: x.id, label: stepInfo(x).label }))} onPick={(to) => ops.link(n.id, to)} />}
      </InspSection>
      {fx ? <div className="callout" style={{ marginTop: 10 }}>Fixed step. It cannot be moved or removed, and its rules apply to everything wired through it.</div> : <>
        <InspSection title="Testing">
          <p className="note" style={{ margin: '0 0 6px' }}>Rehearse the failure path: the next run stops at this step and its error handling takes over.</p>
          <button className="btn sm" aria-pressed={!!n.fail} onClick={() => onFail(n.id)}>{n.fail ? 'Stop failing this step' : 'Fail this step in the next run'}</button>
        </InspSection>
        <div className="acts" style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--line)' }}>
          <button className="btn sm" onClick={() => ops.del(sel)}>Remove from workflow</button>
        </div>
      </>}
    </div></aside>
  );
}

function InspSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="wfsec" style={{ marginTop: 12 }}>
      <div className="note" style={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.04em', marginBottom: 6 }}>{title}</div>
      {children}
    </section>
  );
}

/** The block's links on one side, each removable unless it belongs to the fixed structure. */
function EdgeList({ label, edges, name, none, onRemove }: { label: string; edges: WfGraph['edges']; name: (e: WfGraph['edges'][number]) => string; none: string; onRemove: (id: string) => void }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div className="note">{label}</div>
      {edges.length ? (
        <ul className="wflinks" style={{ listStyle: 'none', padding: 0, margin: '4px 0 0' }}>
          {edges.map((e) => (
            <li key={e.id} className="row" style={{ justifyContent: 'space-between', gap: 6, padding: '3px 0' }}>
              <b>{name(e)}</b>
              {e.locked ? <span className="note" title="Part of the fixed structure; it cannot be removed.">Locked</span>
                : <button className="btn sm ghost" aria-label={'Remove the connection to ' + name(e)} title="Remove this connection" onClick={() => onRemove(e.id)}>Remove</button>}
            </li>
          ))}
        </ul>
      ) : <div className="note" style={{ marginTop: 2 }}><i>{none}</i></div>}
    </div>
  );
}

/** "Choose the next step" when the block sends nowhere yet; otherwise a button that opens the same picker. */
function ConnectTo({ first, opts, onPick }: { first: boolean; opts: { id: string; label: string }[]; onPick: (id: string) => void }) {
  const [open, setOpen] = useState(first);
  if (!open) return <button className="btn sm" onClick={() => setOpen(true)}>+ Add another connection</button>;
  return (
    <div>
      <label className="note" htmlFor="wfTo">{first ? 'Next step' : 'Also send to'}</label>
      <select className="sel" id="wfTo" value="" onChange={(e) => { if (e.target.value) { onPick(e.target.value); setOpen(false); } }}>
        <option value="">Choose a step</option>{opts.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
      </select>
    </div>
  );
}

// ---------------------------------------------------------------- checks and task instances
export function ChecksPanel({ g, checks, onPick }: { g: WfGraph; checks: Check[]; onPick: (id: string) => void }) {
  const e = checks.filter((x) => x.sev === 'error').length, wn = checks.filter((x) => x.sev === 'warn').length;
  const label = (id: string) => { const n = g.nodes.find((x) => x.id === id); return n ? stepInfo(n).label : id; };
  return (
    <div className="panel">
      <div className="ph"><h3>Checks</h3><span id="wfSum">{e ? <span className="chip bad">{e} error{e > 1 ? 's' : ''}</span> : <span className="chip ok">No errors</span>}{wn > 0 && <> <span className="chip warn">{wn} warning{wn > 1 ? 's' : ''}</span></>}</span></div>
      <div id="wfChecks">
        {checks.length ? checks.map((x, k) => (
          <button key={k} className="wfchk" onClick={() => onPick(x.id)}>
            <span className={'dotc ' + (x.sev === 'error' ? 'bad' : x.sev === 'warn' ? 'warn' : '')} /><span className="m"><b>{label(x.id)}</b> {x.msg}</span>
          </button>
        )) : <div className="empty"><b>Ready to run</b>Every step follows the fixed rules.</div>}
      </div>
    </div>
  );
}

/** The run's step table (wfRunHTML). Try: the tries a real run recorded per step (`run.attempts`, plan 6 C7); for a run
 * without them (a test run), a failed step shows the Retries setting (`retries`, the demo's fixed 3). */
export function TaskInstances({ g, run, retries = 3, onPick, onApprove, onClear }: { g: WfGraph; run: TestRun | null; retries?: number; onPick: (id: string) => void; onApprove: () => void; onClear: () => void }) {
  const [f, setF] = useState<{ q: string; st: string }>({ q: '', st: '' });
  const [peek, setPeek] = useState<string | null>(null); // the step whose test-run samples are open
  const L = RUN_LABEL(), C = RUN_CHIP(), by: Record<string, WfNode> = {};
  g.nodes.forEach((n) => (by[n.id] = n));
  let sum: ReactNode = null, body: ReactNode;
  if (!run) body = <div className="empty"><b>No run yet</b>Start a test run to see every step's state. A step that fails turns the steps after it orange (upstream failed).</div>;
  else {
    const T = runTimes(run), q = f.q.trim().toLowerCase(), cnt: Record<string, number> = {};
    run.order.forEach((id) => { if (by[id]) { const s = run.states[id]; cnt[s] = (cnt[s] || 0) + 1; } });
    const rows = run.order.filter((id) => by[id] && (!f.st || run.states[id] === f.st) && (!q || stepInfo(by[id]).label.toLowerCase().includes(q)));
    const m = ({ running: ['y', 'Running'], held: ['y', 'Awaiting approval'], failed: ['bad', 'Failed'], success: [run.warn ? 'warn' : 'ok', run.warn ? 'Success · stale' : 'Success'] } as Record<string, string[]>)[run.status];
    const tot = run.order.filter((id) => ['success', 'warning', 'failed'].includes(run.states[id])).reduce((a, id) => a + +run.dur[id], 0);
    sum = <>
      <span className={'chip ' + m[0]}>{m[1]}</span> <span className="note num">{run.id || 'Run'} · {hms(run.t0 || nowMs())} · {tot.toFixed(1)} s · {run.trig || 'Manual'}</span>
      {run.status === 'held' && (run.dry
        // a test run is a dry run: whoever may run it approves its simulated Human approval; real approvals stay with approvers
        ? <> <button className="btn sm pri" onClick={onApprove} aria-disabled={can('manageWorkflows') ? undefined : true} data-why={can('manageWorkflows') ? undefined : NOWF()}>Approve and continue</button> <span className="note" id="wfSimAppr">Simulated approval (dry run): nothing is sent.</span></>
        : <> <button className="btn sm pri" onClick={onApprove} aria-disabled={can('approve') ? undefined : true} data-why={can('approve') ? undefined : 'Your role cannot approve. Switch to Approver to continue the run.'}>Approve and continue</button></>)}
      {' '}<button className="btn sm ghost" onClick={onClear}>Clear run</button>
    </>;
    body = <>
      <div className="runcnt">{Object.keys(cnt).map((k) => <button key={k} className={'chip ' + C[k] + ' chipb'} aria-pressed={f.st === k} onClick={() => setF({ ...f, st: f.st === k ? '' : k })}>{cnt[k]} {L[k]}</button>)}</div>
      {run.dry && run.status !== 'running' && <p className="note" id="wfDryNote">Dry run on {fmtNumber(run.rows ?? 0)} sampled records. Nothing was written.{run.note ? ' ' + run.note + '.' : ''}</p>}
      <div className="tw" style={{ maxHeight: 340, overflow: 'auto' }}><table className="t tight">
        <thead><tr><th>Step</th><th>State</th><th>Start</th><th>End</th><th className="r">Duration</th><th className="r">Try</th>{run.counts && <th className="r">Records (in / out)</th>}<th>Pool</th></tr></thead>
        <tbody>{rows.length ? rows.flatMap((id) => {
          const n = by[id], st = run.states[id], t = T[id], ex = t?.ex, c = run.counts?.[id], sm = run.samples?.[id];
          const row = <tr key={id} tabIndex={0} onClick={() => onPick(id)} onKeyDown={onActivateKey(() => onPick(id))} style={{ cursor: 'pointer' }}>
            <td><b>{stepInfo(n).label}</b></td><td><span className={'chip ' + C[st]}>{ICO[st] ?? ''} {L[st]}</span></td>
            <td className="num nowrap">{ex ? hms(t.s) : '—'}</td><td className="num nowrap">{ex && st !== 'running' ? hms(t.e) : '—'}</td>
            <td className="r num">{ex && st !== 'running' ? t.d.toFixed(2) + ' s' : '—'}</td><td className="r num">{run.attempts?.[id] ?? (st === 'failed' ? Math.max(1, retries) : ex ? 1 : 0)}</td>
            {run.counts && <td className="r num nowrap">{c ? fmtNumber(c.in) + ' / ' + fmtNumber(c.out) + (c.rej ? ' · ' + fmtNumber(c.rej) + ' rejected' : '') : '—'}
              {sm && (sm.before.length > 0 || sm.after.length > 0) && <> <button className="lnk" aria-expanded={peek === id} onClick={(e) => { e.stopPropagation(); setPeek(peek === id ? null : id); }}>Samples</button></>}</td>}
            <td className="mono">{POOL(n)}</td>
          </tr>;
          return peek === id && sm ? [row, <tr key={id + ':s'}><td colSpan={8}><div className="frsamp" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 8 }}>
            <div><h4>Before</h4><pre className="frlog" style={{ maxHeight: 220, overflow: 'auto' }}>{sm.before.length ? JSON.stringify(sm.before, null, 2) : 'No records'}</pre></div>
            <div><h4>After</h4><pre className="frlog" style={{ maxHeight: 220, overflow: 'auto' }}>{sm.after.length ? JSON.stringify(sm.after, null, 2) : 'No records'}</pre></div>
          </div></td></tr>] : [row];
        }) : <tr><td colSpan={8}><div className="empty"><b>No steps match</b></div></td></tr>}</tbody>
      </table></div>
    </>;
  }
  return (
    <div className="panel wfrun">
      <div className="ph"><h3>Task instances</h3><span id="wfRunSum">{sum}</span></div>
      <div className="filters"><input type="search" placeholder="Search steps" aria-label="Search steps" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} /></div>
      <div id="wfRun">{body}</div>
    </div>
  );
}
