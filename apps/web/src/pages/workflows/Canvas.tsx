/**
 * The Airflow-style canvas (the demo's wf* canvas code): palette, nodes and edges with drag to move, drag from the
 * right dot to connect, select and Delete, arrow keys, zoom, minimap, inspector, checks and task instances.
 * It edits the page's working copy (draftStore.ts); Save and Publish send it through invoke().
 */
import { useEffect, useRef, useState, type PointerEvent as RPointerEvent, type ReactNode } from 'react';
import { fmtNumber } from '../../api/format';
import { can } from '../../api/session';
import {
  actTypes, agentsUsing, CH, channelsOf, deliverMap, deliverOf, edgePath, fixedStep, frTransforms, iconTileHtml, logoHtml, mappings, mapTarget,
  nodeIconHtml, nowMs, RUN_CHIP, RUN_LABEL, runTimes, sourceGroups, sourceLabel, sources, source, sourceShortLabel, statusChipHtml, stepInfo, tools,
  transforms, canLink, WF_H, WF_W, WF_WH, worldWidth, type Check, type Counts, type RunState, type TestRun, type WfGraph, type WfNode, type Workflow,
} from '../../api/workflows';
import { Icon } from '../../ui/Icon';
import { onActivateKey } from '../../ui/keys';
import { toast } from '../../ui/toast';
import { edit, nextId, type Draft } from './draftStore';
import { GRIP_SVG, LOCK_SVG, Raw } from './kit';

export type Sel = { t: 'n' | 'e'; id: string } | null;
export const FIXMSG = 'Fixed steps belong to Circularity and cannot be moved or removed.';
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
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
      const n: WfNode = { id: '', k, ref, x: clamp(Math.round(x / 8) * 8, 0, WW - WF_W), y: clamp(Math.round(y / 8) * 8, 0, WF_WH - WF_H) };
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
  const XIC: Record<string, string> = { x_val: 'checks', x_utc: 'clock', x_fx: 'dollar', x_lookup: 'lookup', x_units: 'scale', x_ident: 'link', x_late: 'clock' };
  const xf = (id: string) => {
    const x = XF.find((y) => y.id === id), f = FR.find((y) => y.id === id);
    if (!x) return null;
    return it('xf:' + id, x.label, x.sub, <Raw html={iconTileHtml(f?.ic ?? XIC[id] ?? 'workflow', f?.group === 'orch' ? 'agent' : 'insp', 'sm')} />);
  };
  const mapIc = <Raw html={iconTileHtml('mapping', 'money', 'sm')} />;
  const S = sources();
  return (
    <aside className="wfpal" id="wfPal" aria-label="Components. Drag one onto the canvas, or press Enter to add it.">
      <div className="frpals"><label className="sr" htmlFor="frPalQ">Search components</label><Icon name="search" />
        <input id="frPalQ" type="search" placeholder="Search components" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <h4 className="frpalh">Sources</h4>
      {sourceGroups().map(([key, types, label]) => {
        const l = S.filter((s) => types.includes(s.type));
        return l.length ? grp('src_' + key, label, l.map((s) => it('conn:' + s.id, sourceLabel(s), s.vendor, <Raw html={logoHtml(s)} />, DOT[s.status]))) : null;
      })}
      <h4 className="frpalh">Transform</h4>
      {grp('frT', 'Transform steps', [
        ...(w.src ? [it('map:' + w.src, sourceShortLabel(w.src) + ' fields', 'Field mapping → ' + mapTarget(w.src), mapIc)] : []),
        ...['x_enrich', 'x_filter', 'x_agg', 'x_expr', 'x_lookup', 'x_join', 'x_val', 'x_utc', 'x_fx', 'x_units', 'x_ident', 'x_late'].map(xf),
      ])}
      <h4 className="frpalh">Orchestration</h4>
      {grp('frO', 'Orchestration steps', ['x_sched', 'x_evtrig', 'x_branch', 'x_loop', 'x_call', 'x_wait'].map(xf))}
      {grp('frB', 'Branches', ['x_err', 'x_audit', 'x_pub'].map(xf))}
      <h4 className="frpalh">More</h4>
      {grp('ing', 'Integration layer', XF.filter((x) => x.group === 'ingest').map((x) => xf(x.id)))}
      {grp('file', 'File exchange steps', XF.filter((x) => x.group === 'file').map((x) => xf(x.id)))}
      {grp('act', 'Delivery methods', actTypes().map((x) => it('act:' + x.id, x.label, x.sub, <Raw html={iconTileHtml('send', 'money', 'sm')} />)))}
      {grp('wr', 'Write to a system', S.filter((x) => x.write.length).map((x) => it('wconn:' + x.id, sourceLabel(x), x.write[0], <Raw html={logoHtml(x)} />, DOT[x.status])))}
      {grp('map', 'All field mappings', S.map((x) => it('map:' + x.id, sourceShortLabel(x.id) + ' fields', '→ ' + mapTarget(x.id), mapIc)))}
      <div className="frfixed"><b>{LOCK_SVG} Fixed Circularity steps</b><span className="note">Canonical models, evidence snapshot, decision and send instruction are placed by Circularity and cannot be re-wired or deleted.</span></div>
    </aside>
  );
}

// ---------------------------------------------------------------- canvas
export function CanvasView({ w, d, z, sel, run, checks, counts, flow, mini, onSel, ops, changed, viewRef, toolbar }: {
  w: Workflow; d: Draft; z: number; sel: Sel; run: TestRun | null; checks: Check[]; counts: Record<string, Counts>; flow: boolean; mini: boolean;
  onSel: (s: Sel) => void; ops: ReturnType<typeof canvasOps>; changed: () => void; viewRef: React.RefObject<HTMLDivElement>;
  toolbar: ReactNode;
}) {
  const g = d.graph, WW = worldWidth(w.kind), by: Record<string, WfNode> = {};
  g.nodes.forEach((n) => (by[n.id] = n));
  const drag = useRef<{ id: string; fixed: boolean; dx: number; dy: number; sx: number; sy: number; moved: boolean; warned?: boolean } | null>(null);
  const [link, setLink] = useState<{ from: string; x: number; y: number; hot: string | null } | null>(null);
  const linkRef = useRef(link);
  linkRef.current = link;

  const pt = (e: { clientX: number; clientY: number }) => {
    const v = viewRef.current!, r = v.getBoundingClientRect();
    return { x: (e.clientX - r.left + v.scrollLeft) / z, y: (e.clientY - r.top + v.scrollTop) / z };
  };
  const nodeAt = (x: number, y: number) => (document.elementFromPoint(x, y)?.closest('.wfn') as HTMLElement | null) ?? null;

  useEffect(() => {
    function move(e: PointerEvent) {
      const dr = drag.current;
      if (dr) {
        if (!dr.moved && Math.hypot(e.clientX - dr.sx, e.clientY - dr.sy) < 5) return;
        dr.moved = true;
        if (dr.fixed) { if (!dr.warned) { dr.warned = true; toast(FIXMSG); } return; }
        const p = pt(e);
        edit(d.id, (dd) => {
          const n = dd.graph.nodes.find((x) => x.id === dr.id);
          if (n) { n.x = clamp(Math.round((p.x - dr.dx) / 8) * 8, 0, WW - WF_W); n.y = clamp(Math.round((p.y - dr.dy) / 8) * 8, 0, WF_WH - WF_H); }
        }, { dirty: false });
        return;
      }
      const l = linkRef.current;
      if (l) {
        const p = pt(e), nd = nodeAt(e.clientX, e.clientY);
        const hot = nd && nd.dataset.id !== l.from && nd.querySelector('.port.in') ? nd.dataset.id! : null;
        setLink({ ...l, x: p.x, y: p.y, hot });
      }
    }
    function up(e: PointerEvent, cancel = false) {
      const dr = drag.current;
      if (dr) {
        drag.current = null;
        if (dr.moved && !dr.fixed && !cancel) { edit(d.id, () => {}, { track: true }); changed(); }
      }
      const l = linkRef.current;
      if (l) {
        setLink(null);
        if (!cancel) {
          const nd = nodeAt(e.clientX, e.clientY);
          if (nd && nd.querySelector('.port.in') && nd.dataset.id !== l.from) ops.link(l.from, nd.dataset.id!);
        }
      }
    }
    const cancel = (e: PointerEvent) => up(e, true);
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', up);
    document.addEventListener('pointercancel', cancel);
    return () => {
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', up);
      document.removeEventListener('pointercancel', cancel);
    };
  });

  function down(e: RPointerEvent) {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    const t = e.target as Element;
    const port = t.closest('.wfn .port.out');
    if (port) {
      const id = (port.closest('.wfn') as HTMLElement).dataset.id!;
      onSel({ t: 'n', id });
      const n = by[id];
      setLink({ from: id, x: n.x + WF_W, y: n.y + WF_H / 2, hot: null });
      e.preventDefault();
      return;
    }
    const nd = t.closest('.wfn') as HTMLElement | null;
    if (nd) {
      const id = nd.dataset.id!, n = by[id], p = pt(e);
      onSel({ t: 'n', id });
      drag.current = { id, fixed: n.k === 'fixed', dx: p.x - n.x, dy: p.y - n.y, sx: e.clientX, sy: e.clientY, moved: false };
      nd.focus({ preventScroll: true });
      e.preventDefault();
      return;
    }
    const eh = t.closest('.wfe .hit');
    if (eh) { onSel({ t: 'e', id: (eh.parentNode as SVGGElement).dataset.e! }); return; }
    if (sel) onSel(null);
  }

  const L = RUN_LABEL();
  const sevOf = (id: string) => {
    const sv = checks.filter((x) => x.id === id && x.sev !== 'info');
    return sv.some((x) => x.sev === 'error') ? 'error' : sv.length ? 'warn' : undefined;
  };
  const showCounts = !!(run || w.last);
  const color = (n: WfNode) => {
    const st = run?.states[n.id];
    return st === 'success' || st === 'warning' ? 'var(--ok)' : st === 'failed' ? 'var(--bad)' : st === 'upstream_failed' ? '#D9651E' : st === 'running' ? 'var(--yellow)' : n.k === 'fixed' ? 'var(--ink)' : 'var(--mv-line)';
  };

  return (
    <div className="wfcanvas">
      {toolbar}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- the canvas takes focus for its arrow-key and Delete shortcuts, as its label says */}
      <div className="wfview" id="wfView" ref={viewRef} tabIndex={0} role="group" aria-label="Workflow canvas. Select a step, then use arrow keys to move it or Delete to remove it." onPointerDown={down}>
        <div id="wfSizer" style={{ width: WW * z, height: WF_WH * z }}>
          <div id="wfWorld" style={{ width: WW, height: WF_WH, transform: `scale(${z})` }}>
            <svg className="wfe" width={WW} height={WF_WH} aria-hidden="true">
              <g id="wfEg">
                {g.edges.map((e) => {
                  const a = by[e.a], b = by[e.b];
                  if (!a || !b) return null;
                  const sa = run?.states[e.a], sb = run?.states[e.b];
                  const c = sb === 'failed' ? 'bad' : sb === 'upstream_failed' ? 'up' : sb === 'running' ? 'run' : sa === 'success' || sa === 'warning' ? 'ok' : sa === 'failed' ? 'bad' : sa === 'upstream_failed' ? 'up' : '';
                  const ty = b.y + WF_H / 2, tx = b.x - 1, path = edgePath(a.x + WF_W + 1, a.y + WF_H / 2, b.x - 9, b.y + WF_H / 2);
                  return (
                    <g key={e.id} data-e={e.id} className={[e.locked ? 'lk' : '', c, sel?.t === 'e' && sel.id === e.id ? 'sel' : ''].join(' ')}>
                      <path className="hit" d={path} /><path className="l" d={path} /><path className="ah" d={`M${tx - 1} ${ty}l-9 -5v10z`} />
                    </g>
                  );
                })}
                {flow && g.edges.map((e) => {
                  const a = by[e.a], b = by[e.b], c = counts[e.a];
                  if (!a || !b || !c) return null;
                  const x = (a.x + WF_W + b.x) / 2, y = (a.y + b.y) / 2 + WF_H / 2 - 6;
                  return <g key={'l' + e.id} className="frel"><rect x={x - 26} y={y - 9} width="52" height="16" rx="8" /><text x={x} y={y + 3} textAnchor="middle">{fmtNumber(c.out)}</text></g>;
                })}
                {link && by[link.from] && <path className="tmp" d={edgePath(by[link.from].x + WF_W + 1, by[link.from].y + WF_H / 2, link.x, link.y)} />}
              </g>
            </svg>
            {g.nodes.map((n) => {
              const i = stepInfo(n), fx = n.k === 'fixed', st = run?.states[n.id], c = counts[n.id];
              return (
                <div key={n.id} className={'wfn frn ' + (fx ? 'fixed' : 'mov') + (sel?.t === 'n' && sel.id === n.id ? ' sel' : '') + (n.fail ? ' inj' : '')}
                  data-id={n.id} data-sev={sevOf(n.id)} data-st={st} style={{ left: n.x, top: n.y }} tabIndex={0} role="button"
                  aria-label={`${i.label}. ${fx ? 'Fixed' : 'Movable'} ${i.tag.replace(/^Fixed · /, '')}.`} title={i.sub}>
                  {i.in && <span className={'port in' + (link?.hot === n.id ? ' hot' : '')} />}
                  {i.out && <span className="port out" />}
                  <span className="frnh"><Raw html={nodeIconHtml(n)} /><span className="frnt"><span className="lb">{i.label}</span><span className="sb">{i.sub}</span></span>{fx && <span className="frlk" aria-hidden="true">{LOCK_SVG}</span>}</span>
                  <span className="frnf"><span className="st">{st ? L[st] : ''}</span><span className="frrcn num" data-rc={n.id}>{c && showCounts ? fmtNumber(c.out) + ' records' : ''}</span></span>
                  <span className="tag">{i.tag}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="wfmini" id="wfMini" hidden={!mini}>
        <svg viewBox={`0 0 ${WW} ${WF_WH}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true">
          {g.nodes.map((n) => <rect key={n.id} x={n.x} y={n.y} width={WF_W} height={WF_H} rx="8" fill={color(n)} />)}
        </svg>
      </div>
      <div className="wflegend"><span><i className="f" />Fixed · owned by Circularity</span><span><i className="m" />Movable · yours to arrange</span><span><i className="fre" />Red · failed</span></div>
      <p className="frphone note">Read-only on a phone. Open on a larger screen to edit the canvas.</p>
    </div>
  );
}

// ---------------------------------------------------------------- inspector
export function Inspector({ d, sel, checks, ops, onFail }: { d: Draft; sel: Sel; checks: Check[]; ops: ReturnType<typeof canvasOps>; onFail: (id: string) => void }) {
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
        <dt>Status</dt><dd><Raw html={statusChipHtml(s.status)} /></dd><dt>Mode</dt><dd>{s.mode}</dd><dt>Access</dt><dd>{s.auth}</dd>
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
  const opts = g.nodes.filter((x) => x.id !== n.id && !canLink(g, n.id, x.id));
  return (
    <aside className="wfinsp" id="wfInsp"><div className="pb">
      <div className="row" style={{ marginBottom: 6 }}><span className={'chip ' + (fx ? 'dk' : 'y')}>{fx ? 'Fixed' : 'Movable'}</span><span className="note">{i.tag.replace(/^Fixed · /, '')}</span></div>
      <h3>{i.label}</h3><p>{i.desc}</p>{det}
      {mine.length > 0 && <div style={{ margin: '10px 0' }}>{mine.map((m, k) => <div key={k} className={'callout ' + (m.sev === 'error' ? 'bad' : '')} style={{ marginBottom: 6 }}>{m.msg}</div>)}</div>}
      <div className="acts">
        {i.out && opts.length > 0 && <>
          <label className="note" htmlFor="wfTo">Connect output to</label>
          <select className="sel" id="wfTo" value="" onChange={(e) => e.target.value && ops.link(n.id, e.target.value)}>
            <option value="">Choose a step</option>{opts.map((x) => <option key={x.id} value={x.id}>{stepInfo(x).label}</option>)}
          </select>
        </>}
        {fx ? <div className="callout">Fixed step. It cannot be moved or removed, and its rules apply to everything wired through it.</div> : <>
          <button className="btn sm" aria-pressed={!!n.fail} onClick={() => onFail(n.id)}>{n.fail ? 'Stop failing this step' : 'Fail this step in the next run'}</button>
          <button className="btn sm" onClick={() => ops.del(sel)}>Remove from workflow</button>
        </>}
      </div>
    </div></aside>
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

export function TaskInstances({ g, run, onPick, onApprove, onClear }: { g: WfGraph; run: TestRun | null; onPick: (id: string) => void; onApprove: () => void; onClear: () => void }) {
  const [f, setF] = useState<{ q: string; st: string }>({ q: '', st: '' });
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
      {run.status === 'held' && <> <button className="btn sm pri" onClick={onApprove} aria-disabled={can('approve') ? undefined : true} data-why={can('approve') ? undefined : 'Your role cannot approve. Switch to Approver to continue the run.'}>Approve and continue</button></>}
      {' '}<button className="btn sm ghost" onClick={onClear}>Clear run</button>
    </>;
    body = <>
      <div className="runcnt">{Object.keys(cnt).map((k) => <button key={k} className={'chip ' + C[k] + ' chipb'} aria-pressed={f.st === k} onClick={() => setF({ ...f, st: f.st === k ? '' : k })}>{cnt[k]} {L[k]}</button>)}</div>
      <div className="tw" style={{ maxHeight: 340, overflow: 'auto' }}><table className="t tight">
        <thead><tr><th>Step</th><th>State</th><th>Start</th><th>End</th><th className="r">Duration</th><th className="r">Try</th><th>Pool</th></tr></thead>
        <tbody>{rows.length ? rows.map((id) => {
          const n = by[id], st = run.states[id], t = T[id], ex = t?.ex;
          return <tr key={id} tabIndex={0} onClick={() => onPick(id)} onKeyDown={onActivateKey(() => onPick(id))} style={{ cursor: 'pointer' }}>
            <td><b>{stepInfo(n).label}</b></td><td><span className={'chip ' + C[st]}>{ICO[st] ?? ''} {L[st]}</span></td>
            <td className="num nowrap">{ex ? hms(t.s) : '—'}</td><td className="num nowrap">{ex && st !== 'running' ? hms(t.e) : '—'}</td>
            <td className="r num">{ex && st !== 'running' ? t.d.toFixed(2) + ' s' : '—'}</td><td className="r num">{st === 'failed' ? 3 : ex ? 1 : 0}</td><td className="mono">{POOL(n)}</td>
          </tr>;
        }) : <tr><td colSpan={7}><div className="empty"><b>No steps match</b></div></td></tr>}</tbody>
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
