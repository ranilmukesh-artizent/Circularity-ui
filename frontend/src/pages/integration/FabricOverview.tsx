/* Overview (5.6): tiles, search, category pills, featured banner, Recommended for you, All integrations. */
import { useRef, useState, type KeyboardEvent } from 'react';
import { useBackend } from '../../api/useBackend';
import { available, connected, frCats, integrations, needsAttention, recommendations, sources, typeOf, type Integration, type Rec } from '../../api/integration';
import { sessionScoped } from '../../api/view';
import { Icon } from '../../components/Icon';
import { toast } from '../../components/toast';
import { Kpi } from '../../components/kit/Kpi';
import { VendorLogo } from '../../components/kit/VendorLogo';
import { canMgr, useInt } from './FabricContext';
import { when } from './fabricFormat';
import { FabricStatus } from './FabricStatus';
import { SourceMenu } from './SourceMenu';

type SortKey = 'name' | 'cat' | 'status' | 'last';
// kept while the session lasts, like the demo's S.frOv
const ovKept = sessionScoped(() => ({ q: '', cat: '', sort: 'name' as SortKey, dir: 1 }));

export function Overview() {
  useBackend();
  const ui = useInt();
  const ov = ovKept.current;
  const [q, setQ] = useState(ov.q);
  const [cat, setCat] = useState(ov.cat);
  const [sort, setSort] = useState<[SortKey, number]>([ov.sort, ov.dir]);
  const all = integrations(), conn = connected(), attn = sources().filter(needsAttention), av = available();
  const cats = frCats().map((c) => [c, all.filter((x) => x.cat === c).length] as [string, number]).filter((c) => c[1]);
  const ql = q.trim().toLowerCase();
  const key: Record<SortKey, (x: Integration) => string | number> = { name: (x) => x.vendor.toLowerCase(), status: (x) => x.status, last: (x) => -(x.last || 0), cat: (x) => x.cat };
  const k = key[sort[0]];
  const list = all
    .filter((x) => (!cat || x.cat === cat) && (!ql || (x.vendor + ' ' + x.name + ' ' + x.cat + ' ' + x.owner).toLowerCase().includes(ql)))
    .sort((a, b) => (k(a) > k(b) ? 1 : k(a) < k(b) ? -1 : 0) * sort[1]);
  const recs = recommendations();
  const allRef = useRef<HTMLDivElement>(null);

  const pickCat = (c: string) => { ov.cat = c; setCat(c); };
  const setQuery = (v: string) => { ov.q = v; setQ(v); };
  const sortBy = (s: SortKey) => setSort(([k0, d]) => { const n: [SortKey, number] = [s, k0 === s ? -d : 1]; ov.sort = n[0]; ov.dir = n[1]; return n; });
  const th = (s: SortKey, l: string) => (
    <th><button className="frsort" aria-label={'Sort by ' + l} onClick={() => sortBy(s)}>{l}{sort[0] === s ? (sort[1] > 0 ? ' ▲' : ' ▼') : ''}</button></th>
  );
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter' || !q.trim()) return;
    e.preventDefault();
    if (/^(connect|add|set ?up|integrate|hook up|link)\b/i.test(q.trim())) {
      const t = q.toLowerCase(), m = available().find((c) => t.includes(c.vendor.toLowerCase().split(' ')[0]) || t.includes(typeOf(c.type).label.toLowerCase()) || t.includes(typeOf(c.type).short.toLowerCase()));
      if (m) return ui.connect(m.id);
    }
  };
  const recAct = (x: Rec) => {
    if (x.act === 'frOpenSrc') ui.openSource(x.arg, 'ov');
    else if (x.act === 'frInvestigate') ui.go('integration/studio/' + x.arg + '?run=last');
    else ui.connect(x.arg);
  };
  const pills = [['', 'All', all.length] as [string, string, number]].concat(cats.map((c) => [c[0], c[0], c[1]]));

  return (
    <div id="frOverview">
      <div className="frkpis fr3">
        <Kpi ic="sync" h="int" v={conn.length} l="Connected" sub="systems sending data" k="connected" />
        <Kpi ic="alert" h="dec" v={attn.length} l="Needs attention" sub="stale, failing, expiring or not connected" k="attention" />
        <Kpi ic="grid" h="money" v={av.length} l="Available" sub="in the catalogue, not yet connected" k="available" />
      </div>
      <div className="frbar">
        <div className="frsrch">
          <Icon name="search" />
          <label className="sr" htmlFor="frOvQ">Search integrations</label>
          <input id="frOvQ" type="search" placeholder="Search integrations, or say “connect our HR system”" value={q} autoComplete="off" onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey} />
        </div>
        <label className="sr" htmlFor="frOvC">Category</label>
        <select className="sel" id="frOvC" value={cat} onChange={(e) => pickCat(e.target.value)}>
          <option value="">All categories</option>
          {cats.map((c) => <option key={c[0]} value={c[0]}>{c[0]}</option>)}
        </select>
      </div>
      <div className="frpills" role="group" aria-label="Category">
        {pills.map((c) => (
          <button key={c[0]} className="frpill" aria-pressed={cat === c[0]} onClick={() => pickCat(c[0])}>{c[1]} <span>{c[2]}</span></button>
        ))}
      </div>
      <section className="frfeat">
        <div>
          <span className="frfk">Featured</span>
          <h2>Build a connected enterprise</h2>
          <p>Bring every system that holds evidence about an asset into one governed fabric, and send approved instructions back to the system that does the work.</p>
          <button className="btn pri" onClick={() => allRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>Explore integrations →</button>
        </div>
        <ul>
          {[['shield', 'Role-based access and audit on every connection', 'Who can read, write and change each connection, recorded in the audit log'], ['sync', 'Real-time sync', 'Event-driven and scheduled, with retries and replay'], ['building', 'Multi-tenant', 'Each customer’s data stays inside its tenant']].map((x) => (
            <li key={x[0]}><Icon name={x[0]} /><span><b>{x[1]}</b><small>{x[2]}</small></span></li>
          ))}
        </ul>
      </section>
      <div className="sh"><div><h2>Recommended for you</h2><p className="note" style={{ margin: '2px 0 0' }}>Ranked by the agent from open gaps in your evidence and workflows.</p></div></div>
      <div className="frrecs">
        {recs.map((x, i) => (
          <article className="frrec" key={i}>
            <VendorLogo vendor={x.s ? x.s.vendor : x.v} />
            <div className="frrech"><b>{x.v}</b><span className="note">{x.t}</span></div>
            <p>{x.line}</p>
            <div className="frrecf">
              <FabricStatus k={x.st} />
              <span className="row">
                <button className="lnk" onClick={() => toast('Why ' + x.v + ' is recommended: ' + x.why + ' Ranked from open gaps in your evidence and workflows; nothing is connected or changed until you choose Connect or Manage.', 7000)}>
                  Why recommended
                </button>
                <button className={'btn sm ' + (x.btn === 'Connect' ? 'pri' : '')} onClick={() => recAct(x)}>{x.btn}</button>
              </span>
            </div>
          </article>
        ))}
      </div>
      <div className="sh" id="frAllInt" ref={allRef}>
        <div><h2>All integrations</h2><p className="note" style={{ margin: '2px 0 0' }}>{conn.length} connected · {av.length} available · {all.length} in the catalogue</p></div>
      </div>
      <div className="frall">
        <nav className="frcatl" aria-label="Categories">
          {[['', 'All categories', all.length] as [string, string, number]].concat(cats.map((c) => [c[0], c[0], c[1]])).map((c) => (
            <button key={c[0]} aria-pressed={cat === c[0]} onClick={() => pickCat(c[0])}>{c[1]}<span>{c[2]}</span></button>
          ))}
        </nav>
        <div className="panel">
          <div className="tw">
            <table className="t frint">
              <thead><tr>{th('name', 'Integration')}{th('cat', 'Type')}{th('status', 'Status')}{th('last', 'Last sync')}<th>Owner</th><th><span className="sr">Actions</span></th></tr></thead>
              <tbody id="frIntBody">
                {list.length ? list.map((x) => <IntRow key={x.id} x={x} />) : (
                  <tr><td colSpan={6}><div className="empty"><b>No integration matches</b>Clear the search or pick another category.</div></td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

/** A row of All integrations: a connected source (opens its drawer), a catalogue entry (opens Connect), or a source
 *  just connected whose record the sources list has not brought yet (neither: shown pending, nothing to open). */
export function IntRow({ x }: { x: Integration }) {
  const ui = useInt();
  const s = x.src, c = x.c;
  const name = <><VendorLogo vendor={x.vendor} /><span><b>{x.vendor}</b><span className="note">{x.name}</span></span></>;
  return (
    <tr data-int={x.id}>
      <td>
        {s || c ? (
          <button className="frintn" onClick={() => (s ? ui.openSource(s.id, 'ov') : ui.connect(c!.id))}>{name}</button>
        ) : (
          <span className="frintn" aria-busy="true">{name}</span>
        )}
      </td>
      <td>{x.cat}</td>
      <td><FabricStatus k={x.status} t={s && s.syncing ? 'Syncing' : null} /></td>
      <td className="num note nowrap">{x.last ? when(x.last) : '—'}</td>
      <td>{x.owner}</td>
      <td className="r">
        {s ? <SourceMenu s={s} /> : !c ? <span className="note">Connecting…</span> : canMgr() ? <button className="btn sm pri" onClick={() => ui.connect(c.id)}>Connect</button> : <span className="note">Available</span>}
      </td>
    </tr>
  );
}
