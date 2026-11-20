/* Source Map (5.9): tiles, filters, Graph · List · Matrix, a system tree and a detail panel. List is the tile grid (intMap). */
import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { useBackend } from '../../api/useBackend';
import {
  ackKind, allMappings, canon, catOf, connMethods, smLog as smLogEntries, connected, events, exceptions, failedRecords, fieldCount, frCats, frDecisions, hourly, mappings,
  needsAttention, publishedWorkflowCount, series, source, sources, srcAgeText, srcCatNote, srcCats, srcFailing, srcFresh, srcModels, successRate, syncAllLive, syncHistory, tableCount,
  tableModel, tableModelIds, totals, vHue, workflows, type Source,
} from '../../api/integration';
import { Icon } from '../../ui/Icon';
import { toast } from '../../ui/toast';
import { canMgr, FrIt, FrKpi, FrSeg, FrSt, fmtN, NOMGR, SrcMenu, StChip, sum, TestSteps, useInt, Vlogo, when } from './ui';
import { FlowDiagram } from './FlowDiagram';

type View = 'graph' | 'list' | 'matrix';
const sm = {
  view: (window.innerWidth <= 860 ? 'list' : 'graph') as View, sel: null as string | null, links: true, q: '', cat: '', st: '', z: null as number | null,
  tree: 'sys', tab: 'ov', hl: null as string | null, tq: '',
};
const grid = { q: '', cat: '', st: '', me: '' };

const dotOf = (s: Source) => (s.disconnected || s.status === 'unavailable' ? 'bad' : s.status === 'stale' || srcFailing(s) ? 'warn' : s.paused ? 'line' : s.status === 'manual' ? 'line' : 'ok');
const tblNames = (id: string) => tableModel(id)?.t.map((t) => t.n) ?? [];

export function SourceMap() {
  useBackend();
  const ui = useInt();
  const [, setV] = useState(0);
  const up = (f: () => void) => { f(); setV((x) => x + 1); };
  const list = sources().filter((s) => (!sm.cat || catOf(s) === sm.cat) && (!sm.st || (sm.st === 'attention' ? needsAttention(s) : s.status === sm.st)) && (!sm.q.trim() || (s.name + ' ' + s.vendor + ' ' + s.owner).toLowerCase().includes(sm.q.trim().toLowerCase())));
  const cats = frCats().filter((c) => sources().some((s) => catOf(s) === c));
  const sel = (id: string | null) => up(() => { sm.sel = id; sm.hl = null; sm.tab = 'ov'; if (sm.view === 'list' && id) ui.openSource(id, 'ov'); });
  const def = source(sm.sel) || sources().find((s) => s.status === 'stale') || sources().find(needsAttention) || sources()[0];

  return (
    <div className="frsm" data-view={sm.view}>
      <div className="frkpis" id="frSmTiles"><SmTiles /></div>
      <div className="frbar">
        <div className="frsrch">
          <Icon name="search" />
          <label className="sr" htmlFor="frSmQ">Search systems</label>
          <input id="frSmQ" type="search" placeholder="Search systems, tables or fields…" value={sm.q} autoComplete="off" onChange={(e) => up(() => { sm.q = e.target.value; grid.q = e.target.value; })} />
        </div>
        <label className="sr" htmlFor="frSmSys">System</label>
        <select className="sel" id="frSmSys" value={sm.sel ?? ''} onChange={(e) => sel(e.target.value || null)}>
          <option value="">All systems</option>
          {sources().map((s) => <option key={s.id} value={s.id}>{s.vendor}</option>)}
        </select>
        <label className="sr" htmlFor="frSmCat">Category</label>
        <select className="sel" id="frSmCat" value={sm.cat} onChange={(e) => up(() => { sm.cat = e.target.value; })}>
          <option value="">All categories</option>
          {cats.map((c) => <option key={c}>{c}</option>)}
        </select>
        <label className="sr" htmlFor="frSmSt">Status</label>
        <select className="sel" id="frSmSt" value={sm.st} onChange={(e) => up(() => { sm.st = e.target.value; })}>
          <option value="">All statuses</option>
          {[['live', 'Live'], ['attention', 'Needs attention'], ['stale', 'Stale'], ['manual', 'Manual import'], ['unavailable', 'Not connected']].map((o) => <option key={o[0]} value={o[0]}>{o[1]}</option>)}
        </select>
        <label className="tog frlinks"><input type="checkbox" checked={sm.links} onChange={(e) => up(() => { sm.links = e.target.checked; })} /> Show field links</label>
        <span className="grow" />
        <FrSeg<View> items={[['graph', 'Graph', 'graph'], ['list', 'List', 'list'], ['matrix', 'Matrix', 'matrix']]} cur={sm.view} onPick={(v) => up(() => { sm.view = v; })} label="Source map view" />
      </div>
      {sm.view === 'list' ? (
        <div className="frsml"><TileGrid /></div>
      ) : (
        <div className="frsmg">
          <aside className="panel frtree" aria-label="Systems and tables"><Tree onSel={sel} up={up} /></aside>
          <div className="panel frsmc">{sm.view === 'matrix' ? <Matrix list={list} onSel={sel} /> : <Graph list={list} onSel={sel} up={up} />}</div>
          <aside className="panel frsmp" id="frSmPanel"><SmPanel s={def} tab={sm.tab} setTab={(t) => up(() => { sm.tab = t; })} /></aside>
        </div>
      )}
    </div>
  );
}

function SmTiles() {
  const conn = connected(), tbl = sum(sources().map((s) => tableCount(s.id))), fm = sum(Object.values(allMappings()).map((r) => r.length));
  const W = workflows(), act = publishedWorkflowCount(), t = totals(), hh = hourly();
  const nw = sources().filter((s) => s.frConnectedAt && Date.now() - s.frConnectedAt < 30 * 864e5).length, nwf = W.filter((w) => w.frNew).length;
  return (
    <>
      <FrKpi ic="graph" h="int" v={conn.length} l="Connected sources" k="connected" d={nw ? <span className="frd good">▲ {nw} this month</span> : undefined} />
      <FrKpi ic="database" h="money" v={tbl} l="Tables modelled" k="tables" />
      <FrKpi ic="link" h="dec" v={fm} l="Field mappings" k="fields" />
      <FrKpi ic="sync" h="insp" v={act} l="Active workflows" k="workflows" d={nwf ? <span className="frd good">▲ {nwf} this month</span> : undefined} />
      <FrKpi ic="activity" h="int" v={t.pct.toFixed(1) + '%'} l="Integration health" sub="last 24 hours" sp={hh.map((b) => b.ok / (b.ok + b.warn + b.bad || 1))} k="health" />
    </>
  );
}

function Tree({ onSel, up }: { onSel: (id: string) => void; up: (f: () => void) => void }) {
  const tq = sm.tq.toLowerCase(), S = sources(), list = S.filter((s) => !tq || (s.vendor + ' ' + s.name).toLowerCase().includes(tq)), tbl = sum(S.map((s) => tableCount(s.id)));
  return (
    <>
      <div className="frtabs" role="tablist">
        <button role="tab" aria-selected={sm.tree !== 'tbl'} onClick={() => up(() => { sm.tree = 'sys'; })}>Systems <span className="frtn2">{S.length}</span></button>
        <button role="tab" aria-selected={sm.tree === 'tbl'} onClick={() => up(() => { sm.tree = 'tbl'; })}>Tables <span className="frtn2">{tbl}</span></button>
      </div>
      <div className="frsrch sm">
        <Icon name="search" />
        <label className="sr" htmlFor="frTq">Search the tree</label>
        <input id="frTq" type="search" placeholder={'Search ' + (sm.tree === 'tbl' ? 'tables' : 'systems') + '…'} value={sm.tq} onChange={(e) => up(() => { sm.tq = e.target.value; })} />
      </div>
      <div className="frtreeb" id="frTreeB">
        {sm.tree === 'tbl'
          ? S.filter((s) => tableCount(s.id) && (!tq || (s.vendor + ' ' + tblNames(s.id).join(' ')).toLowerCase().includes(tq))).map((s) => (
            <details key={s.id}>
              <summary><Vlogo vendor={s.vendor} /> {s.vendor} <span className="note">({tableCount(s.id)})</span></summary>
              {tblNames(s.id).map((n) => <button key={n} className="frti" onClick={() => onSel(s.id)}><span className="mono">{n}</span></button>)}
            </details>
          ))
          : frCats().map((c) => {
            const it = list.filter((s) => catOf(s) === c);
            return it.length ? (
              <details open key={c}>
                <summary>{c} <span className="note">({it.length})</span></summary>
                {it.map((s) => (
                  <button key={s.id} className="frti" aria-pressed={sm.sel === s.id} onClick={() => onSel(s.id)}>
                    <i className={'dotc ' + dotOf(s)} /><Vlogo vendor={s.vendor} /><span>{s.vendor}</span>
                  </button>
                ))}
              </details>
            ) : null;
          })}
      </div>
    </>
  );
}

type Edge = { a: string; b: string; col: string; n?: number; t?: string; dash?: boolean };
function Graph({ list, onSel, up }: { list: Source[]; onSel: (id: string) => void; up: (f: () => void) => void }) {
  const C = canon(), D = frDecisions();
  const view = useRef<HTMLDivElement>(null), world = useRef<HTMLDivElement>(null), nodes = useRef(new Map<string, HTMLDivElement>());
  const [geo, setGeo] = useState<{ w: number; h: number; p: Record<string, { x: number; y: number; w: number }>; fit: number }>({ w: 0, h: 0, p: {}, fit: 1 });
  const E: Edge[] = [];
  list.forEach((s) => Object.entries(srcModels(s)).forEach(([m, rows]) => E.push({ a: 's:' + s.id, b: 'c:' + m, col: `hsl(${vHue(s.vendor)} 62% 52%)`, n: rows.length, t: rows.map((r) => r[0] + ' → ' + r[2]).join('\n') })));
  D.forEach((d) => d[2].forEach((m) => E.push({ a: 'c:' + m, b: 'd:' + d[0], col: 'var(--muted)', dash: true })));
  const hl = sm.hl || (sm.sel ? 's:' + sm.sel : null), rel = new Set<string>();
  if (hl) {
    rel.add(hl);
    let grow = true;
    while (grow) {
      grow = false;
      E.forEach((e) => {
        if (rel.has(e.a) && !rel.has(e.b) && hl[0] !== 'd') { rel.add(e.b); grow = true; }
        if (rel.has(e.b) && !rel.has(e.a) && hl[0] !== 's' && !(hl[0] === 'c' && e.a[0] === 'c')) { rel.add(e.a); grow = true; }
      });
    }
  }
  const key = list.map((s) => s.id).join(',');
  useLayoutEffect(() => {
    const w = world.current, v = view.current;
    if (!w || !v) return;
    const p: Record<string, { x: number; y: number; w: number }> = {};
    nodes.current.forEach((e, k) => { if (e.isConnected) p[k] = { x: e.offsetLeft, y: e.offsetTop + e.offsetHeight / 2, w: e.offsetWidth }; });
    const fit = Math.max(0.5, Math.min(1, Math.floor(((v.clientWidth - 8) / w.scrollWidth) * 100) / 100));
    setGeo({ w: w.scrollWidth, h: w.scrollHeight, p, fit });
  }, [key]);
  const z = sm.z ?? geo.fit;
  const ref = (k: string) => (e: HTMLDivElement | null) => { if (e) nodes.current.set(k, e); else nodes.current.delete(k); };
  const node = (k: string, cls: string, body: ReactNode, onClick: () => void, label?: string) => (
    <div key={k} ref={ref(k)} className={'frgn ' + cls + (hl && !rel.has(k) ? ' dim' : '')} data-gn={k} tabIndex={0} role="button" aria-label={label} onClick={onClick}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } }}>{body}</div>
  );
  const hlToggle = (k: string) => up(() => { sm.hl = sm.hl === k ? null : k; });
  const zoom = (a: number) => up(() => { sm.z = a === 0 ? null : Math.max(0.5, Math.min(1.4, Math.round(((sm.z ?? geo.fit) + a * 0.1) * 10) / 10)); });
  return (
    <>
      <div className="frgtool">
        <div className="wfzoom" role="group" aria-label="Zoom">
          <button aria-label="Zoom out" onClick={() => zoom(-1)}><Icon name="zout" /></button>
          <span>{Math.round(z * 100)}%</span>
          <button aria-label="Zoom in" onClick={() => zoom(1)}><Icon name="zin" /></button>
          <button aria-label="Fit" onClick={() => zoom(0)}><Icon name="max" /></button>
        </div>
        <span className="note">{list.length} systems → {C.length} canonical models → {D.length} models and decisions. Select a node to highlight its paths.</span>
      </div>
      <div className="frgv" id="frGv" ref={view}>
        <div className="frgw" id="frGw" ref={world} style={{ transform: `scale(${z})` }}>
          <svg className="frge" id="frGe" aria-hidden="true" width={geo.w} height={geo.h}>
            {E.map((e, i) => {
              const a = geo.p[e.a], b = geo.p[e.b];
              if (!a || !b) return null;
              const x1 = a.x + a.w, y1 = a.y, x2 = b.x, y2 = b.y, mx = (x1 + x2) / 2, on = !hl || (rel.has(e.a) && rel.has(e.b));
              return (
                <g key={i} className={on ? '' : 'dim'}>
                  <path d={`M${x1} ${y1}C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`} stroke={e.col} fill="none" strokeWidth={on && hl ? 2.4 : 1.6} strokeDasharray={e.dash ? '4 4' : undefined} />
                  {sm.links && !!e.n && (
                    <g className="frgl"><title>{e.t}</title><rect x={mx - 13} y={(y1 + y2) / 2 - 9} width="26" height="16" rx="8" /><text x={mx} y={(y1 + y2) / 2 + 3} textAnchor="middle">{e.n}</text></g>
                  )}
                </g>
              );
            })}
          </svg>
          <div className="frgcol">
            {list.length ? list.map((s) => node('s:' + s.id, 'frgs' + (sm.sel === s.id ? ' on' : ''), (
              <><Vlogo vendor={s.vendor} /><span><b>{s.vendor}</b><span className="note">{tableCount(s.id)} tables · {fieldCount(s.id)} fields</span></span><i className={'dotc ' + dotOf(s)} /></>
            ), () => onSel(s.id), s.vendor)) : <div className="empty"><b>No system matches</b>Clear the filters.</div>}
          </div>
          <div className="frgcol mid">
            {C.map((c) => {
              const n = sum(sources().map((s) => (srcModels(s)[c.n] || []).length));
              return <div key={c.n} style={{ display: 'contents' }}>{node('c:' + c.n, 'frgc', (
                <><FrIt ic="database" h="dec" cls="sm" /><span><b>{c.n}</b><span className="note">Canonical model v{c.v} · {n} mapped field{n === 1 ? '' : 's'}</span></span></>
              ), () => hlToggle('c:' + c.n))}</div>;
            })}
          </div>
          <div className="frgcol">
            {D.map((d) => <div key={d[0]} style={{ display: 'contents' }}>{node('d:' + d[0], 'frgd', (
              <><FrIt ic={d[0] === 'dc' ? 'tasks' : d[0] === 'rc' ? 'scale' : 'bot'} h="agent" cls="sm" /><span><b>{d[1]}</b><span className="note">{d[0] === 'dc' || d[0] === 'rc' ? 'Decision step' : 'Model'}</span></span></>
            ), () => hlToggle('d:' + d[0]))}</div>)}
          </div>
        </div>
        <div className="frgmini" aria-hidden="true">
          <i style={{ height: Math.min(100, list.length * 4) + '%' }} /><i style={{ height: C.length * 5 + '%' }} /><i style={{ height: D.length * 5 + '%' }} />
        </div>
      </div>
    </>
  );
}

function Matrix({ list, onSel }: { list: Source[]; onSel: (id: string) => void }) {
  const C = canon();
  return (
    <>
      <div className="tw frmx">
        <table className="t static tight">
          <thead><tr><th>System</th>{C.map((c) => <th key={c.n} className="r" title={c.purpose}>{c.n}</th>)}<th className="r">Total</th></tr></thead>
          <tbody>
            {list.map((s) => {
              const m = srcModels(s), bad = s.status === 'stale' || s.status === 'unavailable';
              return (
                <tr key={s.id}>
                  <td><button className="frintn" onClick={() => onSel(s.id)}><Vlogo vendor={s.vendor} /><span><b>{s.vendor}</b><span className="note">{s.name}</span></span></button></td>
                  {C.map((c) => {
                    const r = m[c.n];
                    return (
                      <td key={c.n} className="r num">
                        {r ? <span className={'frmc ' + (bad || !r.length ? 'bad' : 'ok')} title={r.length ? r.map((x) => x[0] + ' → ' + x[2]).join('\n') : 'Target model with no field mapping yet'}>{r.length}</span> : <span className="note">·</span>}
                      </td>
                    );
                  })}
                  <td className="r num"><b>{mappings(s.id).length}</b></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="note" style={{ margin: '8px 4px 0' }}>Red cells: the source is stale or not connected, or it targets the model with no field mapping yet.</p>
    </>
  );
}

function SyncTable({ s, n }: { s: Source; n: number }) {
  const L = syncHistory(s);
  return L.length ? (
    <table className="t static tight">
      <tbody>
        {L.slice(0, n).map((r, i) => (
          <tr key={i}><td className="num nowrap">{when(r.ts)}</td><td>{r.ok ? <FrSt k="success" /> : <FrSt k="failed" />}</td><td className="r num">{fmtN(r.rows)} records</td><td className="r num note">{String(r.dur)}</td></tr>
        ))}
      </tbody>
    </table>
  ) : <p className="note">No syncs yet.</p>;
}

function SmPanel({ s, tab, setTab }: { s?: Source; tab: string; setTab: (t: string) => void }) {
  const ui = useInt();
  if (!s) return <div className="empty"><b>Select a system</b>Its connection, usage and sync history appear here.</div>;
  const CM = connMethods(), M = mappings(s.id), T: [string, string][] = [['ov', 'Overview'], ['tbl', 'Tables (' + tableCount(s.id) + ')'], ['fld', 'Fields (' + M.length + ')'], ['sync', 'Sync'], ['set', 'Settings']];
  let body: ReactNode;
  if (tab === 'tbl') body = tableCount(s.id) ? (
    <>
      <ul className="frtl2">{tableModel(s.id)!.t.map((t) => <li key={t.n}><b className="mono">{t.n}</b><span className="note">{t.desc || ''}</span></li>)}</ul>
      <a className="lnk" href="#/integration/tables" onClick={(e) => { e.preventDefault(); ui.go('integration/tables'); }}>Open Source Tables →</a>
    </>
  ) : <p className="note">No table model for this system yet.</p>;
  else if (tab === 'fld') body = (
    <>
      {M.length ? (
        <table className="t static tight"><thead><tr><th>Source field</th><th>Canonical field</th></tr></thead>
          <tbody>{M.map((r, i) => <tr key={i}><td className="mono">{r[0]}</td><td className="mono">{r[2]}</td></tr>)}</tbody></table>
      ) : <p className="note">No field mapping defined yet.</p>}
      {canMgr() && <button className="btn sm" onClick={() => ui.openSource(s.id, 'map')}><Icon name="spark" /> Suggest mappings</button>}
    </>
  );
  else if (tab === 'sync') body = <SyncTable s={s} n={20} />;
  else if (tab === 'set') body = (
    <>
      <dl className="frdl">
        <dt>Connector</dt><dd>{CM[s.method] ? CM[s.method].label : s.mode}</dd><dt>Mode</dt><dd>{s.mode}</dd><dt>Auth</dt><dd>{s.auth}</dd><dt>Owner</dt><dd>{s.owner}</dd>
        <dt>Config version</dt><dd className="mono">v{s.cfgVer}</dd>
      </dl>
      <button className="btn sm" onClick={() => ui.openSource(s.id, 'ov')}><Icon name="edit" /> Open configuration</button>
    </>
  );
  else body = (
    <>
      <p className="ink2" style={{ marginTop: 0 }}>{s.inputs}</p>
      <h4>Connection details</h4>
      <dl className="frdl">
        <dt>Instance URL</dt><dd className="mono">{s.url || '—'}</dd><dt>Environment</dt><dd><span className="chip ok">{s.env || 'Production'}</span></dd>
        <dt>Auth type</dt><dd>{s.auth}</dd><dt>Connected by</dt><dd>{s.owner} · integration owner</dd><dt>Last sync</dt><dd>{srcAgeText(s)}</dd>
      </dl>
      <h4>Usage (last 30 days)</h4>
      <div className="frust">
        <div><span className="note">Records synced</span><b className="num">{fmtN(sum(series(s, 30)))}</b></div>
        <div><span className="note">Success rate</span><b className="num">{s.status === 'unavailable' ? '—' : successRate(s) + '%'}</b></div>
        <div><span className="note">Failed records</span><b className="num">{fmtN(failedRecords(s, 30))}</b></div>
      </div>
      <h4>Recent sync history</h4>
      <SyncTable s={s} n={3} />
      <div id="frSmTest"><TestSteps id={s.id} /></div>
    </>
  );
  const stk = s.disconnected ? 'disconnected' : s.paused ? 'paused' : s.status === 'live' ? 'live' : s.status;
  return (
    <>
      <div className="frsph">
        <Vlogo vendor={s.vendor} />
        <div><h3>{s.vendor}</h3><span className="note">{s.name} · {CM[s.method] ? CM[s.method].label : s.mode}</span></div>
        <FrSt k={stk} />
      </div>
      <div className="frtabs" role="tablist">{T.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>)}</div>
      <div className="pb">{body}</div>
      <div className="frspf">
        {canMgr() && <button className="btn sm pri" onClick={() => ui.test(s.id)}><Icon name="play" /> Test connection</button>}
        <SrcMenu s={s} />
      </div>
    </>
  );
}

/* ---- the List view: the Source map tile grid with chips, filters, dependencies, activity and side panels (intMap) ---- */
const barBg = (v: number): CSSProperties => (v < 70 ? { background: 'var(--bad)' } : v < 85 ? { background: '#D4A800' } : {});

function Tile({ s }: { s: Source }) {
  const ui = useInt();
  const CM = connMethods()[s.method], unav = s.status === 'unavailable', pend = !unav && s.lastSync == null, fr = srcFresh(s);
  const meter = (l: string, v: number) => (
    <div className="meter">
      <span style={{ width: 78 }}>{l}</span>
      <div className="bar"><i style={{ width: (unav || pend ? 0 : v) + '%', ...barBg(v) }} /></div>
      <b className="num" style={{ width: 34, textAlign: 'right' }}>{unav || pend ? '—' : v + '%'}</b>
    </div>
  );
  const unm = !unav && !mappings(s.id).length;
  const stop = (f: () => void) => (e: React.MouseEvent) => { e.stopPropagation(); f(); };
  return (
    <div className={'tile ' + s.status + (s.syncing ? ' syncing' : '')} data-sid={s.id} tabIndex={0} role="button" aria-label={s.name + ', ' + s.vendor + '. Open configuration.'}
      onClick={() => ui.openSource(s.id, 'conn')} onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); ui.openSource(s.id, 'conn'); } }}>
      <div className="row between" style={{ marginBottom: 6, flexWrap: 'nowrap' }}>
        <span className="row" style={{ gap: 9, flexWrap: 'nowrap', minWidth: 0 }}><Vlogo vendor={s.vendor} /><b className="tname">{s.name}</b></span>
        {s.syncing ? <span className="chip y">Syncing</span> : <StChip s={s.status} />}
      </div>
      <div className="note vline">
        <span className="mbadge" data-tip={CM.tip}>{CM.badge}</span>
        <span className="vtxt">{s.vendor}{CM.sched && s.interval ? ' · ' + s.interval + ' min' : ''}</span>
      </div>
      {meter('Freshness', fr)}{meter('Complete', s.compl)}{meter('Confidence', s.conf)}
      {s.syncing && <div className="sprog" aria-hidden="true"><i style={{ width: (s.syncPct || 0) + '%' }} /></div>}
      <div className="row between note" style={{ marginTop: 8, flexWrap: 'nowrap' }}>
        <span>{s.syncing ? 'Syncing… ' + (s.syncPct || 0) + '%' : srcAgeText(s)}</span>
        <span>{s.step.map((n) => 'S' + n).join(' ')}</span>
      </div>
      <div className="tfoot">
        <span className="note">{fmtN(s.records)} records{unm && <> · <b className="unm">No field mapping</b></>}</span>
        <span className="tacts">
          <button className="tbtn" aria-label={'Edit ' + s.name} onClick={stop(() => ui.openSource(s.id, 'conn'))}>Edit</button>
          {canMgr() && (
            <>
              <button className="tbtn" disabled={!!(s.syncing || unav || s.status === 'manual')} aria-label={'Sync ' + s.name + ' now'} onClick={stop(() => ui.sync(s.id))}>Sync</button>
              <button className="tbtn dng" aria-label={'Delete ' + s.name} onClick={stop(() => ui.remove(s.id))}>Delete</button>
            </>
          )}
        </span>
      </div>
    </div>
  );
}

function TileGrid() {
  const ui = useInt();
  const [, setV] = useState(0);
  const up = (f: () => void) => { f(); setV((x) => x + 1); };
  const S = sources(), CM = connMethods(), C = srcCats(), N = srcCatNote(), q = grid.q.trim().toLowerCase();
  const list = S.filter((s) => (!grid.cat || s.cat === grid.cat) && (!grid.st || s.status === grid.st) && (!grid.me || s.method === grid.me) && (!q || (s.name + ' ' + s.vendor + ' ' + s.owner + ' ' + s.mode + ' ' + CM[s.method].label + ' ' + s.id).toLowerCase().includes(q)));
  const filt = !!(grid.q || grid.st || grid.me);
  const cnt: Record<string, number> = { live: 0, stale: 0, manual: 0, unavailable: 0 };
  S.forEach((s) => cnt[s.status]++);
  const chip = (k: string, cls: string, t: string) => cnt[k] ? (
    <button className={'chip ' + cls + ' chipb'} aria-pressed={grid.st === k} onClick={() => up(() => { grid.st = grid.st === k ? '' : k; })}>{cnt[k]} {t}</button>
  ) : null;
  const dep = S.filter((s) => s.status === 'unavailable' || s.status === 'stale' || s.status === 'manual');
  const add = (c: string) => <button className="tile addt" onClick={() => ui.addSource(c)}><span className="plus">+</span><b>Add source</b><span className="note">{C[c]}</span></button>;
  const syncAll = () => { if (!canMgr()) return toast(NOMGR); toast('Sync started for ' + syncAllLive() + ' live sources.'); };
  return (
    <>
      <div className="hkpis" id="smKpi"><SmKpis /></div>
      <div className="smbar">
        <div className="row smchips" id="smChips">
          <span className="chip line">{S.length} sources</span>
          {chip('live', 'ok', 'live')}{chip('stale', 'warn', 'stale')}{chip('manual', 'dk', 'manual')}{chip('unavailable', 'bad', 'unavailable')}
        </div>
        <span className="grow" />
        <input type="search" id="smQ" className="smq" placeholder="Search system, vendor or owner" value={grid.q} aria-label="Search sources" onChange={(e) => up(() => { grid.q = e.target.value; })} />
        <label className="sr" htmlFor="smCat">Category</label>
        <select className="sel" id="smCat" value={grid.cat} onChange={(e) => up(() => { grid.cat = e.target.value; })}>
          <option value="">All categories</option>
          {Object.keys(C).map((c) => <option key={c} value={c}>{C[c]}</option>)}
        </select>
        <label className="sr" htmlFor="smMeth">Connection method</label>
        <select className="sel" id="smMeth" value={grid.me} onChange={(e) => up(() => { grid.me = e.target.value; })}>
          <option value="">All methods</option>
          {Object.keys(CM).map((c) => <option key={c} value={c}>{CM[c].label}</option>)}
        </select>
        {canMgr() && <><button className="btn" onClick={syncAll}>Sync all</button><button className="btn pri" onClick={() => ui.addSource('')}>+ Add source</button></>}
      </div>
      <p className="note" style={{ margin: '0 0 4px' }}>
        Each system is configured on its own. Each source shows how it connects: native connector, JDBC, API extractor, event API, Delta Sharing or flat file. Select one to edit it. <span className="livedot"><i />Live</span>
      </p>
      <div id="smGrid">
        {!list.length && filt ? (
          <div className="empty"><b>No sources match</b>Clear the search or status filter, or add a new source.<div style={{ marginTop: 10 }}><button className="btn sm" onClick={() => up(() => Object.assign(grid, { q: '', cat: '', st: '', me: '' }))}>Clear filters</button></div></div>
        ) : Object.keys(C).filter((c) => !grid.cat || grid.cat === c).map((c) => {
          const it = list.filter((x) => x.cat === c);
          if (!it.length && filt) return null;
          return (
            <div key={c}>
              <h3 className="catH">{C[c]}<span className="note">{N[c]} · {it.length} connected</span></h3>
              <div className="tiles">{it.map((s) => <Tile key={s.id} s={s} />)}{!filt && canMgr() && add(c)}</div>
            </div>
          );
        })}
      </div>
      {!!dep.length && (
        <div className="callout bad" style={{ marginTop: 14 }}>
          <b>Integration dependencies.</b>{' '}
          {dep.map((s, i) => (
            <span key={s.id}>{i ? '; ' : ''}<button className="lnk" onClick={() => ui.openSource(s.id, 'conn')}>{s.name} ({s.vendor})</button> is {s.status === 'unavailable' ? 'not connected' : s.status === 'stale' ? 'stale' : 'a manual import'}</span>
          ))}. Circularity names these as dependencies rather than inventing data.
        </div>
      )}
      <div className="sect">
        <div className="sh"><h2>Sync activity</h2><span className="livedot"><i />Streaming</span></div>
        <div className="panel" id="smLog" aria-live="off"><SmLogList /></div>
      </div>
      <div className="grid g3 smside" id="smSide" style={{ marginTop: 16, alignItems: 'start' }}><SmSide /></div>
      <div className="sect"><div className="sh"><h2>How data flows</h2></div><FlowDiagram /></div>
    </>
  );
}

function SmKpis() {
  const t = totals(), conn = sources().filter((s) => s.status !== 'unavailable').length, tbl = sum(tableModelIds().map((k) => tableModel(k)?.t.length ?? 0));
  const pub = publishedWorkflowCount();
  const k = (cls: string, ic: string, v: ReactNode, l: string) => (
    <div className={'hkpi ' + cls}><span className="kic"><Icon name={ic} /></span><div><b className="num">{v}</b><span>{l}</span></div></div>
  );
  return <>{k('ok', 'integration', conn, 'Connected sources')}{k('info', 'product', tbl, 'Tables modelled')}{k('y', 'play', pub, 'Workflows published')}{k('warn', 'flag', exceptions().length, 'Mappings need attention')}{k('ok', 'check', t.pct.toFixed(1) + '%', 'Integration health')}</>;
}

function SmLogList() {
  const L = smLogEntries();
  return L.length ? (
    <>
      {L.map((l, i) => {
        const s = source(l.id);
        return (
          <div className={'lg ' + l.kind} key={i}>
            <span className="num lt">{new Date(l.ts).toTimeString().slice(0, 8)}</span>
            {s && <Vlogo vendor={s.vendor} />}
            <span className="lm"><b>{s ? s.name : 'Removed'}</b> <span className="note">{s ? s.vendor : '—'}</span> · {l.text}</span>
          </div>
        );
      })}
    </>
  ) : <div className="empty"><b>No activity yet</b>Syncs, edits and credential changes appear here as they happen.</div>;
}

function SmSide() {
  const ui = useInt();
  const t = totals(), hh = hourly(), r = 54, c = 2 * Math.PI * r, n = t.ok + t.warn + t.bad || 1;
  let off = 0;
  const seg = (v: number, col: string) => {
    const l = (v / n) * c, e = <circle key={col} cx="70" cy="70" r={r} fill="none" stroke={col} strokeWidth="16" strokeDasharray={`${l} ${c - l}`} strokeDashoffset={-off} transform="rotate(-90 70 70)" />;
    off += l;
    return e;
  };
  const mx = Math.max(...hh.map((b) => b.ok + b.warn + b.bad)), all = exceptions(), ex = all.slice(0, 6), ev = events().slice(0, 6), sevc = { High: 'bad', Medium: 'warn', Low: 'line' };
  return (
    <>
      <div className="panel">
        <div className="ph"><h3>Integration health</h3><span className="note">Last 24 hours</span></div>
        <div className="pb">
          <div className="hlth">
            <svg viewBox="0 0 140 140" width="132" height="132" role="img" aria-label={t.pct.toFixed(1) + ' percent healthy'}>
              <circle cx="70" cy="70" r={r} fill="none" stroke="var(--panel3)" strokeWidth="16" />
              {seg(t.ok, 'var(--ok)')}{seg(t.warn, '#D4A800')}{seg(t.bad, 'var(--bad)')}
              <text x="70" y="68" textAnchor="middle" fontSize="22" fontWeight="800" fill="var(--ink)">{t.pct.toFixed(1)}%</text>
              <text x="70" y="86" textAnchor="middle" fontSize="11" fill="var(--ink2)">Healthy</text>
            </svg>
            <div className="hleg">
              <div><i style={{ background: 'var(--ok)' }} />Successful<b className="num">{fmtN(t.ok)}</b></div>
              <div><i style={{ background: '#D4A800' }} />Warnings<b className="num">{fmtN(t.warn)}</b></div>
              <div><i style={{ background: 'var(--bad)' }} />Failures<b className="num">{fmtN(t.bad)}</b></div>
              <div><i style={{ background: 'var(--ink2)' }} />In progress<b className="num">{t.run}</b></div>
            </div>
          </div>
          <div className="hbars" aria-hidden="true">
            {hh.map((b, i) => (
              <span key={i} data-tip={`${String(i).padStart(2, '0')}:00 · ${b.ok} successful, ${b.warn} warnings, ${b.bad} failures`}>
                <i style={{ height: (b.bad / mx) * 100 + '%', background: 'var(--bad)' }} /><i style={{ height: (b.warn / mx) * 100 + '%', background: '#D4A800' }} /><i style={{ height: (b.ok / mx) * 100 + '%', background: 'var(--ok)' }} />
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="panel">
        <div className="ph"><h3>Mapping exceptions</h3><span className={'chip ' + (ex.length ? 'warn' : 'ok')}>{all.length} open</span></div>
        <div className="tw">
          <table className="t static tight">
            <thead><tr><th>System</th><th>Issue</th><th>Severity</th><th>Status</th></tr></thead>
            <tbody>
              {ex.length ? ex.map((e, i) => (
                <tr key={i}><td><b>{e.src}</b><div className="note">{e.obj}</div></td><td>{e.issue}</td><td><span className={'chip ' + sevc[e.sev]}>{e.sev}</span></td><td><span className={'chip ' + (e.st === 'Open' ? 'line' : 'y')}>{e.st}</span></td></tr>
              )) : <tr><td colSpan={4}><div className="empty"><b>No exceptions</b>Every connected system is mapped and fresh.</div></td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      <div className="panel">
        <div className="ph"><h3>Recent integration events</h3><button className="lnk" onClick={() => ui.go('integration/events')}>View all</button></div>
        <div className="tw">
          <table className="t static tight">
            <thead><tr><th>Time</th><th>System</th><th>Event</th><th>Status</th></tr></thead>
            <tbody>
              {ev.map((e) => (
                <tr key={e.id} style={{ cursor: 'pointer' }} onClick={() => ui.openEvent(e.id)}>
                  <td className="num nowrap">{new Date(e.ts).toISOString().slice(11, 19)}</td><td>{e.dest}</td><td className="mono">{e.type}</td>
                  <td><span className={'chip ' + ackKind(e.ack)}>{e.ack.length > 16 ? e.ack.slice(0, 15) + '…' : e.ack}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
