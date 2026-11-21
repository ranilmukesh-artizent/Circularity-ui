/** The workflow list (frWfList): tiles, filters, the table with Open / Investigate and ⋯, bulk actions, and the right column. */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fmtNumber } from '../../api/format';
import { useBackend } from '../../api/useBackend';
import { can } from '../../api/session';
import { sessionScoped } from '../../api/view';
import {
  ago, ageShort, attention, nowMs, recentRuns, RUN_LABEL, source, sources, systemOf, trigText, wfStat, workflows, type Workflow, type WfStat,
} from '../../api/workflows';
import { openAsk } from '../../ui/askBus';
import { Icon } from '../../ui/Icon';
import { isDirty, useDrafts } from './draftStore';
import { IconTile } from '../../ui/kit/IconTile';
import { Kpi } from '../../ui/kit/Kpi';
import { Panel } from '../../ui/kit/Panel';
import { Ring } from '../../ui/kit/Ring';
import { Timeline } from '../../ui/kit/Timeline';
import { useTick } from '../../ui/useTick';
import { WorkflowMenu } from './WorkflowMenus';
import { SourceMark, WorkflowStatus } from './WorkflowMarks';
import { DeleteModal, NewWorkflowModal } from './WorkflowModals';
import { WorkflowBuilder } from './WorkflowBuilder';
import { bulk, duplicate, exportOne, runNow, studioHref, toggle } from './workflowActions';

interface Filters { q: string; type: string; sys: string; st: string; sort: 'last' | 'name' | 'ok' | 'status'; pg: number }
/** The filters survive leaving the list and coming back, like the demo's S.wf.f. */
const kept = sessionScoped<Filters>(() => ({ q: '', type: '', sys: '', st: '', sort: 'last', pg: 0 }));
const PER = 20;

function filterList(L: Workflow[], f: Filters): Workflow[] {
  const q = f.q.trim().toLowerCase();
  const out = L.filter((w) => (!f.type || w.cat === f.type) && (!f.st || wfStat(w) === f.st) && (!f.sys || w.src === f.sys)
    && (!q || (w.name + ' ' + w.id + ' ' + w.owner + ' ' + (w.src ? source(w.src).vendor : '')).toLowerCase().includes(q)));
  const rank: Record<WfStat, number> = { failing: 0, paused: 1, draft: 2, published: 3 };
  const key = { last: (w: Workflow) => -(w.last ? w.last.ts : 0), name: (w: Workflow) => w.name.toLowerCase(), ok: (w: Workflow) => (w.runsN ? w.okN / w.runsN : 2), status: (w: Workflow) => rank[wfStat(w)] }[f.sort];
  return out.sort((a, b) => (key(a) > key(b) ? 1 : key(a) < key(b) ? -1 : 0));
}

export function WorkflowList({ query }: { query: URLSearchParams }) {
  useBackend();
  useDrafts();
  useTick(1000);
  const nav = useNavigate();
  const mgr = can('manageWorkflows');
  const [f, setF0] = useState<Filters>(() => {
    const st = query.get('st'), q = query.get('q');
    return st || q ? { ...kept.current, st: st ?? kept.current.st, q: q ?? kept.current.q, pg: 0 } : kept.current;
  });
  const setF = (p: Partial<Filters>) => setF0((o) => (kept.current = { ...o, ...p }));
  const [sel, setSel] = useState<Set<string>>(new Set());
  // ?new=1 (Home's "New workflow" quick action, the demo's wfNew) opens the New workflow dialog at once
  // ?build=<description> (Ask's "Refine in Workflow Studio") opens Build with AI with that description
  const [modal, setModal] = useState<{ k: 'new' } | { k: 'del'; id: string } | { k: 'ai'; prompt: string } | null>(() =>
    mgr && query.get('build') !== null ? { k: 'ai', prompt: query.get('build') ?? '' } : mgr && query.get('new') === '1' ? { k: 'new' } : null);
  const build = query.get('build');
  useEffect(() => {
    // Ask can hand over a description while the list is already open
    if (mgr && build !== null) setModal((m) => (m?.k === 'ai' && m.prompt === build ? m : { k: 'ai', prompt: build }));
  }, [build, mgr]);

  const all = workflows();
  sources(); // the system column and filter read the sources: load them with the list, not row by row
  const c = { published: 0, draft: 0, paused: 0, failing: 0 };
  all.forEach((w) => c[wfStat(w)]++);
  const srcN = new Set(all.filter((w) => w.src).map((w) => w.src)).size;
  const sys = [...new Set(all.filter((w) => w.src).map((w) => w.src as string))].map(source).filter((s) => !s.deleted);
  const L = filterList(all, f), pages = Math.max(1, Math.ceil(L.length / PER)), pg = Math.min(f.pg, pages - 1), shown = L.slice(pg * PER, pg * PER + PER);
  const open = (id: string) => nav(studioHref(id));
  const pick = (id: string, on: boolean) => setSel((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n; });

  function doBulk(a: 'run' | 'pause' | 'export' | 'clear') {
    if (a !== 'clear') bulk(a, [...sel]);
    if (a !== 'export' || !mgr) setSel(new Set());
  }

  return (
    <div className="frwfl">
      <div className="frwfm">
        <div className="frkpis fr4" id="wfChips">
          <Kpi ic="workflow" h="dec" v={all.length} n={all.length} l="Total workflows" sub={'Across ' + srcN + ' source systems'} k="total" />
          <Kpi ic="checks" h="int" v={c.published} n={c.published} l="Published" sub="Running and healthy" k="published" />
          <Kpi ic="alert" h="alert" v={c.failing} n={c.failing} l="Failing" sub="Needs attention" k="failing" />
          <Kpi ic="file" h="neutral" v={c.draft + c.paused} n={c.draft + c.paused} l="Draft or paused" sub={c.draft + ' not yet published · ' + c.paused + ' paused'} k="draft" />
        </div>
        <div className="frbar">
          <div className="frsrch">
            <Icon name="search" />
            <label className="sr" htmlFor="frWfQ">Search workflows</label>
            <input id="frWfQ" type="search" placeholder="Search workflows, owners or systems…" value={f.q} autoComplete="off" onChange={(e) => setF({ q: e.target.value, pg: 0 })} />
          </div>
          <label className="sr" htmlFor="wfTypeF">Type</label>
          <select className="sel" id="wfTypeF" value={f.type} onChange={(e) => setF({ type: e.target.value, pg: 0 })}>
            <option value="">All types</option>{['Ingest', 'Outbound', 'Decision'].map((t) => <option key={t}>{t}</option>)}
          </select>
          <label className="sr" htmlFor="frWfSys">System</label>
          <select className="sel" id="frWfSys" value={f.sys} onChange={(e) => setF({ sys: e.target.value, pg: 0 })}>
            <option value="">All systems</option>{sys.map((s) => <option key={s.id} value={s.id}>{s.vendor}</option>)}
          </select>
          <label className="sr" htmlFor="frWfSt">Status</label>
          <select className="sel" id="frWfSt" value={f.st} onChange={(e) => setF({ st: e.target.value, pg: 0 })}>
            <option value="">All statuses</option>
            {[['published', 'Published'], ['failing', 'Failing'], ['paused', 'Paused'], ['draft', 'Draft']].map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select>
          <label className="sr" htmlFor="frWfSort">Sort</label>
          <select className="sel" id="frWfSort" value={f.sort} onChange={(e) => setF({ sort: e.target.value as Filters['sort'] })}>
            {[['last', 'Last run (recent)'], ['name', 'Name (A–Z)'], ['ok', '24 h success (lowest)'], ['status', 'Status (failing first)']].map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select>
          <span className="grow" />
          {mgr && <button className="btn" onClick={() => setModal({ k: 'ai', prompt: '' })}><Icon name="spark" /> Build with AI</button>}
          {mgr && <button className="btn pri" onClick={() => setModal({ k: 'new' })}><Icon name="plus" /> New workflow</button>}
        </div>
        <div className="frbulk" id="frWfBulk" hidden={!sel.size}>
          {sel.size > 0 && <>
            <b>{sel.size} selected</b>
            {mgr && <button className="btn sm" onClick={() => doBulk('run')}><Icon name="play" /> Run</button>}
            {mgr && <button className="btn sm" onClick={() => doBulk('pause')}><Icon name="pause" /> Pause</button>}
            <button className="btn sm" onClick={() => doBulk('export')}><Icon name="download" /> Export</button>
            <button className="lnk" onClick={() => doBulk('clear')}>Clear</button>
          </>}
        </div>
        <div className="panel">
          <div className="tw">
            <table className="t wftbl frwft">
              <thead><tr>
                <th className="frck"><input type="checkbox" aria-label="Select all on this page" checked={shown.length > 0 && shown.every((w) => sel.has(w.id))}
                  onChange={(e) => { const on = e.target.checked; setSel((s) => { const n = new Set(s); shown.forEach((w) => (on ? n.add(w.id) : n.delete(w.id))); return n; }); }} /></th>
                <th>Workflow</th><th>Type</th><th>Source system</th><th>Trigger</th><th>Status</th><th>Last run</th><th>24 h success</th><th>Owner</th><th>Actions</th>
              </tr></thead>
              <tbody id="wfBody">
                {shown.map((w) => <Row key={w.id} w={w} sel={sel.has(w.id)} onPick={pick} onOpen={open} onDelete={() => setModal({ k: 'del', id: w.id })}
                  onInvestigate={() => nav(studioHref(w.id) + '?run=last')} onDup={() => { duplicate(w.id); }} mgr={mgr} />)}
                {!shown.length && <tr><td colSpan={10}><div className="empty"><b>No workflows match</b>Clear the filters or create a new workflow.</div></td></tr>}
              </tbody>
            </table>
          </div>
          <div className="frpager" id="frWfPager">
            <span className="note">Showing {L.length ? pg * PER + 1 : 0}–{Math.min(L.length, pg * PER + PER)} of {L.length} workflows · 20 per page</span>
            <span className="row">{Array.from({ length: pages }, (_, i) => (
              <button key={i} className={'btn sm' + (i === pg ? ' pri' : '')} aria-label={'Page ' + (i + 1)} aria-current={i === pg ? 'page' : undefined} onClick={() => setF({ pg: i })}>{i + 1}</button>
            ))}</span>
          </div>
        </div>
        <p className="note" style={{ margin: '8px 2px 0' }}>Each workflow stands alone: one source system in and one canonical model out, or one target system per outbound instruction. <span className="livedot"><i />Live</span></p>
      </div>
      <aside className="frwfs" id="frWfSide"><Side c={c} total={all.length} onInvestigate={(id) => nav(studioHref(id) + '?run=last')} /></aside>
      {modal?.k === 'new' && <NewWorkflowModal onClose={() => setModal(null)} onCreated={(id) => { setModal(null); open(id); }} />}
      {modal?.k === 'ai' && <WorkflowBuilder key={modal.prompt} initialPrompt={modal.prompt} onClose={() => { setModal(null); if (build !== null) nav(studioHref(), { replace: true }); }} onCreated={(id) => { setModal(null); open(id); }} />}
      {modal?.k === 'del' && <DeleteModal id={modal.id} onClose={() => setModal(null)} onDeleted={() => setModal(null)} />}
    </div>
  );
}

function Row({ w, sel, mgr, onPick, onOpen, onDelete, onInvestigate, onDup }: {
  w: Workflow; sel: boolean; mgr: boolean; onPick: (id: string, on: boolean) => void; onOpen: (id: string) => void; onDelete: () => void; onInvestigate: () => void; onDup: () => void;
}) {
  const s = systemOf(w), st = wfStat(w), l = w.last, ok = w.runsN ? Math.round((w.okN / w.runsN) * 100) : null, up = !!s?.paused, fail = st === 'failing';
  const L = RUN_LABEL();
  return (
    <tr data-wid={w.id} className={fail ? 'frfail' : ''}>
      <td className="frck"><input type="checkbox" aria-label={'Select ' + w.name} checked={sel} onChange={(e) => onPick(w.id, e.target.checked)} /></td>
      <td><button className="lnk b" onClick={() => onOpen(w.id)}>{w.name}</button><div className="note">{w.id} · v{w.ver}{isDirty(w.id) ? ' · unsaved changes' : ''}</div></td>
      <td><span className="chip line">{w.cat}</span></td>
      <td>{s
        ? <span className="frsys"><SourceMark s={s} /><span><b>{s.deleted ? 'Deleted source' : s.short || s.name}</b><span className="note">{s.vendor}</span></span></span>
        : <span className="frsys"><IconTile ic="bot" h="agent" cls="sm" /><span><b>Decision</b><span className="note">Circularity</span></span></span>}</td>
      <td className="frtrig">{trigText(w.trig)}</td>
      <td>{w.running ? <WorkflowStatus k="running" /> : up ? <WorkflowStatus k="paused" t="Paused upstream" /> : <WorkflowStatus k={st} />}</td>
      <td>{l ? <>
        <span className={'frlr ' + l.state}><i />{L[l.state]}</span>
        <div className="note nowrap"><span className="num">{ageShort(nowMs() - l.ts)}</span> ago</div>
        {fail && l.note && <div className="frwhy" title={l.note}>{l.note}</div>}
      </> : <span className="note">Never run</span>}</td>
      <td className="frsucc">{ok == null ? <span className="note">—</span> : <>
        <span className={'num ' + (ok >= 95 ? '' : ok >= 80 ? 'frmid' : 'neg')}>{ok}%</span>
        <i className="frbar1"><b style={{ width: ok + '%', background: ok >= 95 ? 'var(--ok)' : ok >= 80 ? 'var(--h-dec)' : 'var(--bad)' }} /></i>
      </>}</td>
      <td>{w.owner}</td>
      <td className="nowrap"><span className="tacts frta">
        {fail ? <button className="btn sm frinv" onClick={onInvestigate}>Investigate</button> : <button className="btn sm" onClick={() => onOpen(w.id)}>Open</button>}
        <WorkflowMenu summaryCls="iconbtn sm" label={'More actions for ' + w.name} summary={<Icon name="more" />}>
          <button role="menuitem" onClick={() => onOpen(w.id)}><Icon name="edit" /><span>Edit</span></button>
          {mgr && <button role="menuitem" onClick={() => runNow(w.id)} disabled={w.running}><Icon name="play" /><span>Run now</span></button>}
          {mgr && (w.status === 'draft'
            ? <button role="menuitem" onClick={() => toggle(w.id)}><Icon name="upload" /><span>Publish</span></button>
            : <button role="menuitem" onClick={() => toggle(w.id)}><Icon name={w.status === 'paused' ? 'play' : 'pause'} /><span>{w.status === 'paused' ? 'Resume' : 'Pause'}</span></button>)}
          {mgr && <button role="menuitem" onClick={onDup}><Icon name="copy" /><span>Duplicate</span></button>}
          <button role="menuitem" onClick={() => exportOne(w.id)}><Icon name="download" /><span>Export JSON</span></button>
          {mgr && <button role="menuitem" className="dng" onClick={onDelete}><Icon name="trash" /><span>Delete</span></button>}
        </WorkflowMenu>
      </span></td>
    </tr>
  );
}

function Side({ c, total, onInvestigate }: { c: Record<WfStat, number>; total: number; onInvestigate: (id: string) => void }) {
  const at = attention();
  const soon = () => openAsk('Which workflows are failing and why?');
  return (
    <>
      {at.length > 0 && (
        <section className="panel frp frwatt"><div className="pb">
          <div className="frattnh"><Icon name="alert" /><div><b>{at.length} item{at.length > 1 ? 's' : ''} need attention</b><p className="note">Resolve failing workflows and expired credentials to keep data fresh.</p></div></div>
          <ol className="frtl">{at.map((a, i) => (
            <li key={i}><IconTile ic={a.ic} h={a.h} cls="sm" />
              <div className="frtlb"><b>{a.t}</b><span className="note">{a.s}</span>
                <span className="frtlx">{a.go && <button className="lnk" onClick={() => onInvestigate(a.go!)}>Investigate</button>}<button className="lnk" onClick={soon}><Icon name="spark" /> Diagnose</button></span>
              </div></li>
          ))}</ol>
        </div></section>
      )}
      <Panel title="Workflow health" id="frWfRing">
        <Ring segs={[{ v: c.published, c: 'var(--ok)', l: 'Published' }, { v: c.failing, c: 'var(--bad)', l: 'Failing' }, { v: c.draft + c.paused, c: 'var(--muted)', l: 'Draft or paused' }]}
          center={((c.published / (total || 1)) * 100).toFixed(1) + '%'} sub="Healthy" />
      </Panel>
      <Panel title="Recent activity" right={<span className="livedot"><i />Live</span>}>
        <div id="wfRuns">
          <Timeline empty="Runs appear here as workflows fire on their triggers." rows={recentRuns().slice(0, 6).map((x) => ({
            key: x.id + x.ts, ic: 'workflow', h: x.state === 'failed' ? 'alert' : 'int', t: x.name,
            s: x.state === 'failed' ? 'Failed' + (x.note ? ' (' + x.note + ')' : '') : x.state === 'running' ? 'Running' : 'Completed · ' + fmtNumber(x.rows) + ' records',
            ago: ago(nowMs() - x.ts), st: <WorkflowStatus k={x.state === 'failed' ? 'failed' : x.state === 'running' ? 'running' : 'completed'} />,
          }))} />
        </div>
      </Panel>
    </>
  );
}

