/**
 * Product · Decision Workbench: Returned assets (received) and Expected returns (renderProduct, queueTable,
 * expectedTable, kpiStrip, openCase, expDetail, ntCallout in index.html).
 */
import { useEffect, useState, useSyncExternalStore } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { invoke } from '../../api/actions';
import { fmtDate, fmtDateYear, money } from '../../api/format';
import { useBackend } from '../../api/useBackend';
import {
  asModel, caseById, classLabel, demoCaseId, demoVisible, expectedCount, expectedStage, expectedVisible, facilities, isCaseId, journeyHref, journeyTitle, leaseSource,
  myOpenNotes, routeAllowed, routeInfo, visibleCases, type Case, type Expected,
} from '../../api/product';
import { canPage, tenants } from '../../api/session';
import { sessionScoped } from '../../api/view';
import { Icon } from '../../ui/Icon';
import { onActivateKey } from '../../ui/keys';
import { Drawer } from '../../ui/Overlay';
import { toast } from '../../ui/toast';
import { AssessChip, CondChip, EvRow, Signals, StageChip, Thumb } from './AssetChips';
import { JourneyGuide, JourneyStrip } from './Journey';

// ---------- view state (the demo's S.q / S.sel): kept for the session, like the demo ----------
type SortK = 'priority' | 'id' | 'product' | 'assetId' | 'owner' | 'received' | 'location' | 'condition' | 'assessment' | 'net';
interface Q {
  kpi: 'all' | 'ready' | 'awaiting' | 'need' | 'approval'; text: string; cond: string; loc: string; owner: string; assess: string;
  sortK: SortK; sortD: 1 | -1; limit: number; group: boolean; open: Record<string, boolean>; sel: string | null;
}
const q = sessionScoped<Q>(() => ({ kpi: 'all', text: '', cond: '', loc: '', owner: '', assess: '', sortK: 'priority', sortD: 1, limit: 25, group: false, open: {}, sel: null }));
const subs = new Set<() => void>();
function setQ(p: Partial<Q>) {
  q.current = { ...q.current, ...p };
  subs.forEach((f) => f());
}
const useQ = () => useSyncExternalStore((f) => (subs.add(f), () => subs.delete(f)), () => q.current);

const PRIO = ['RT-1048', 'RT-1049', 'RT-1050', 'RT-1051', 'RT-1052'];
const SORT: Record<SortK, (c: Case) => string | number> = {
  priority: (c) => (c.hero || c.id === 'RT-1062' || c.id === 'RT-1044' ? (PRIO.indexOf(c.id) >= 0 ? PRIO.indexOf(c.id) : 9) : 99) * 1e9 - +new Date(c.received),
  id: (c) => c.id, product: (c) => c.product, assetId: (c) => c.assetId, owner: (c) => c.owner, received: (c) => +new Date(c.received),
  location: (c) => c.location, condition: (c) => c.condition, assessment: (c) => c.assessment,
  net: (c) => (c.recommendation ? c.recommendation.net : -1e9),
};

function queueRows(f: Q): Case[] {
  let rows = visibleCases();
  if (f.kpi === 'ready') rows = rows.filter((c) => c.assessment === 'Ready');
  if (f.kpi === 'awaiting') rows = rows.filter((c) => c.assessment === 'Pending');
  if (f.kpi === 'need') rows = rows.filter((c) => c.assessment === 'Review' || c.assessment === 'Partial');
  if (f.kpi === 'approval') rows = rows.filter((c) => c.stage === 'awaiting_approval');
  if (f.text) {
    const t = f.text.toLowerCase();
    rows = rows.filter((c) => (c.id + ' ' + c.assetId + ' ' + c.product + ' ' + c.owner + ' ' + c.location).toLowerCase().includes(t));
  }
  if (f.cond) rows = rows.filter((c) => c.condition === f.cond);
  if (f.loc) rows = rows.filter((c) => c.location === f.loc);
  if (f.owner) rows = rows.filter((c) => c.owner === f.owner);
  if (f.assess) rows = rows.filter((c) => c.assessment === f.assess);
  const v = SORT[f.sortK], d = f.sortD;
  return [...rows].sort((a, b) => (v(a) > v(b) ? d : v(a) < v(b) ? -d : 0));
}

// ---------- page ----------
export function ReturnedAssetsPage({ view, focus }: { view: 'received' | 'expected'; focus: string | null }) {
  useBackend();
  const nav = useNavigate();
  const [exp, setExp] = useState<Expected | null>(null);
  const f = useQ();
  const sel = f.sel ? caseById(f.sel) : undefined;
  const jid = view === 'received' ? (isCaseId(focus) ? focus! : demoCaseId()) : null;
  const showJourney = !!jid && demoVisible(jid);

  useEffect(() => {
    document.title = 'Product · Circularity Decision Workbench';
  }, []);
  useEffect(() => {
    if (view !== 'received' || !focus) return;
    const t = window.setTimeout(() => {
      const row = document.getElementById('qr-' + focus);
      if (row && row.getBoundingClientRect().bottom > window.innerHeight) row.scrollIntoView({ block: 'center' });
    }, 40);
    return () => window.clearTimeout(t);
  }, [view, focus]);

  return (
    <>
      {showJourney && <JourneyStrip id={jid!} at={0} />}
      <NoteCallouts />
      <div className="phead">
        <div>
          <h1>Returned assets</h1>
          <p>
            Inspect the inventory, establish readiness, evaluate the best use. Each case below runs steps 2–5 of the journey; once approved,
            the instruction goes to your enterprise systems, which carry out the work.
          </p>
        </div>
        <div className="row">
          <div className="seg" role="group" aria-label="View">
            <button aria-pressed={view === 'received'} onClick={() => nav('/product/received')}>Received</button>
            <button aria-pressed={view === 'expected'} onClick={() => nav('/product/expected')}>Expected ({expectedCount()})</button>
          </div>
          {canPage('product', 'pools') && <a className="btn" href="#/product/pools">Pool optimizer</a>}
        </div>
      </div>
      {view === 'received' ? (
        <>
          <KpiStrip f={f} />
          <div style={{ height: 14 }} />
          <QueueTable f={f} focus={focus} />
        </>
      ) : (
        <ExpectedTable onOpen={setExp} />
      )}
      {sel && <CaseDrawer c={sel} onClose={() => setQ({ sel: null })} />}
      {exp && <ExpectedDrawer e={exp} onClose={() => setExp(null)} />}
      {showJourney && <JourneyGuide id={jid!} at={0} />}
    </>
  );
}

/** Notifications addressed to this account (ntCallout): shown on its landing page too. */
function NoteCallouts() {
  const l = myOpenNotes().slice(-2);
  const dp = demoCaseId();
  return (
    <>
      {l.map((n) => {
        const id = (n.ids || []).find((x) => x === dp) || (n.ids || [])[0];
        const ok = !!id && !!caseById(id) && demoVisible(id);
        return (
          <div key={n.id} className="callout ntcall" role="status">
            <span><b>From {n.from}:</b> {n.title} · {n.msg}</span>
            <span className="sp" />
            {ok && <a className="btn sm" href={'#/product/received?focus=' + id}>Show {id}</a>}
            <button className="btn sm pri" onClick={async () => {
              const r = await invoke('notify.acknowledge', { id: n.id });
              if (r.ok) toast('Acknowledged. The sender sees it is in hand.');
              else toast(r.error.message);
            }}>Acknowledge</button>
          </div>
        );
      })}
    </>
  );
}

function KpiStrip({ f }: { f: Q }) {
  const v = visibleCases(), n = (fn: (c: Case) => boolean) => v.filter(fn).length;
  const items: [Q['kpi'], string, number, string][] = [
    ['all', 'returned assets', v.length, 'received this cycle'],
    ['ready', 'ready to evaluate', n((c) => c.assessment === 'Ready'), 'evidence complete'],
    ['awaiting', 'awaiting inspection', n((c) => c.assessment === 'Pending'), 'no route evaluated yet'],
    ['need', 'need information', n((c) => c.assessment === 'Review' || c.assessment === 'Partial'), 'exception or missing evidence'],
    ['approval', 'awaiting approval', n((c) => c.stage === 'awaiting_approval'), 'a person decides (step 5)'],
  ];
  return (
    <div className="kpis" role="group" aria-label="Filter queue by status">
      {items.map((i) => (
        <button key={i[0]} className="kpi" aria-pressed={f.kpi === i[0]} onClick={() => setQ({ kpi: i[0], limit: 25 })}>
          <div className="v num">{i[2]}</div>
          <div className="l">{i[1]}</div>
          <div className="s">{i[3]}</div>
        </button>
      ))}
    </div>
  );
}

function QueueTable({ f, focus }: { f: Q; focus: string | null }) {
  const rows = queueRows(f), shown = rows.slice(0, f.limit), total = visibleCases().length;
  const dp = demoCaseId();
  const sort = (k: SortK) => setQ(f.sortK === k ? { sortD: f.sortD === 1 ? -1 : 1 } : { sortK: k, sortD: 1 });
  const th = (k: SortK, l: string, cls = '') => (
    <th className={cls} aria-sort={f.sortK === k ? (f.sortD > 0 ? 'ascending' : 'descending') : 'none'}>
      <button onClick={() => sort(k)}>{l}{f.sortK === k ? (f.sortD > 0 ? ' ↑' : ' ↓') : ''}</button>
    </th>
  );
  const opts = (arr: string[]) => arr.map((x) => <option key={x} value={x}>{x}</option>);
  const open = (id: string) => setQ({ sel: id });

  const row = (c: Case) => (
    <tr key={c.id} className={`${f.sel === c.id ? 'sel' : ''} ${focus === c.id ? 'dpfocus' : ''}`} id={'qr-' + c.id} tabIndex={0}
      onClick={() => open(c.id)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget && (e.preventDefault(), open(c.id))}>
      <td><b>{c.id}</b>{c.id === dp && demoVisible(c.id) && <span className="chip y dpstart">Start here</span>}</td>
      <td>
        <div className="row" style={{ gap: 8, flexWrap: 'nowrap' }}>
          <Thumb cls={c.cls} />
          <span>{c.product}{c.qty > 1 && <> <span className="note">×{c.qty}</span></>}</span>
        </div>
      </td>
      <td className="num nowrap">
        <Link className="lnk" to={'/product/asset/' + c.id} data-tip="Open asset intelligence" onClick={(e) => e.stopPropagation()}>{c.assetId}</Link>
      </td>
      <td className="nowrap">{c.owner}</td>
      <td className="num nowrap">{fmtDate(c.received)}</td>
      <td className="nowrap">{c.location}</td>
      <td><CondChip c={c} /></td>
      <td><AssessChip c={c} /></td>
      <td><StageChip c={c} /><Signals c={c} /></td>
      <td className="r num nowrap">
        {c.recommendation
          ? <><b>{money(c.recommendation.net)}</b> <span className="note">{routeInfo(c.recommendation.id).short}</span></>
          : <span className="note">Not priced yet</span>}
      </td>
    </tr>
  );

  const groups = () => {
    const gm: Record<string, Case[]> = {};
    rows.forEach((c) => { const k = asModel(c) + '|' + c.owner; (gm[k] = gm[k] || []).push(c); });
    const pv = (l: Case[]) => l.reduce((s, c) => s + ((c.chosen || c.recommendation)?.net || 0), 0);
    return Object.entries(gm).sort((a, b) => b[1].length - a[1].length || pv(b[1]) - pv(a[1])).map(([k, l]) => {
      const [m, o] = k.split('|');
      const gr = [...new Set(l.map((c) => c.grade).filter(Boolean) as string[])].sort();
      const on = !!f.open[k];
      const toggle = () => setQ({ open: { ...f.open, [k]: !on } });
      return [
        <tr key={k} className="skug" aria-expanded={on} tabIndex={0} onClick={toggle} onKeyDown={onActivateKey(toggle)}>
          <td colSpan={10}>
            <span className="skut">
              <span className="car" aria-hidden="true">›</span>
              <span>{m} · {o}</span>
              <span className="chip line">{l.length} unit{l.length === 1 ? '' : 's'}</span>
              <span className="note">
                {gr.length ? 'grades ' + (gr.length > 1 ? gr[0] + '–' + gr[gr.length - 1] : gr[0]) : 'not graded yet'} · {money(pv(l))} predicted
              </span>
            </span>
          </td>
        </tr>,
        ...(on ? l.map(row) : []),
      ];
    });
  };

  const body = f.group ? groups() : shown.map(row);
  return (
    <div className="panel">
      <div className="filters">
        <input type="search" placeholder="Search by product, asset ID, owner or return number" value={f.text} aria-label="Search returned assets"
          onChange={(e) => setQ({ text: e.target.value, limit: 25 })} />
        <select className="sel" aria-label="Condition" value={f.cond} onChange={(e) => setQ({ cond: e.target.value })}>
          <option value="">Condition</option>{opts(['Inspected', 'Grade A', 'Grade B', 'Grade C', 'Test required', 'Not inspected', 'Mixed'])}
        </select>
        <select className="sel" aria-label="Location" value={f.loc} onChange={(e) => setQ({ loc: e.target.value })}>
          <option value="">Location</option>{opts(facilities())}
        </select>
        <select className="sel" aria-label="Owner" value={f.owner} onChange={(e) => setQ({ owner: e.target.value })}>
          <option value="">Owner</option>{opts(tenants())}
        </select>
        <select className="sel" aria-label="Assessment" value={f.assess} onChange={(e) => setQ({ assess: e.target.value })}>
          <option value="">Assessment</option>{opts(['Ready', 'Review', 'Pending', 'Partial'])}
        </select>
        <button className="btn ghost sm" onClick={() => setQ({ kpi: 'all', text: '', cond: '', loc: '', owner: '', assess: '', limit: 25 })}>Clear filters</button>
        <div className="seg" role="group" aria-label="Rows" style={{ marginLeft: 'auto' }}>
          <button aria-pressed={!f.group} onClick={() => setQ({ group: false })}>List</button>
          <button aria-pressed={f.group} onClick={() => setQ({ group: true })}>Group by product</button>
        </div>
      </div>
      <div className="tw">
        <table className="t">
          <thead>
            <tr>
              {th(f.sortK === 'priority' ? 'priority' : 'id', 'Return')}{th('product', 'Product')}{th('assetId', 'Asset ID')}{th('owner', 'Owner')}
              {th('received', 'Received')}{th('location', 'Location')}{th('condition', 'Condition')}{th('assessment', 'Assessment')}
              <th>Status</th>{th('net', 'Best next action', 'r')}
            </tr>
          </thead>
          <tbody>
            {body.length ? body : (
              <tr><td colSpan={11}><div className="empty"><b>No returns match these filters</b>Clear filters to see all {total} returns.</div></td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="filters" style={{ borderTop: '1px solid var(--line2)', borderBottom: 0, justifyContent: 'space-between' }}>
        <span className="note">
          {f.group ? 'Grouped by product and customer: ' + rows.length + ' units' : 'Showing ' + shown.length + ' of ' + rows.length}. Physical inventory
          remains controlled by the source system.
        </span>
        {!f.group && rows.length > shown.length && <button className="btn sm" onClick={() => setQ({ limit: f.limit + 25 })}>Show 25 more</button>}
      </div>
    </div>
  );
}

/** The returned-asset panel (openCase). */
function CaseDrawer({ c, onClose }: { c: Case; onClose: () => void }) {
  const nav = useNavigate();
  const ev = c.evidence, ready = ev.filter((e) => e.state === 'ready').length;
  const dp = demoVisible(c.id) && !c.blocked;
  const go = (p: string) => { onClose(); nav('/' + p); };
  const foot = dp ? (
    <>
      <button className="btn" onClick={() => go('product/' + c.id)}>Evaluate treatments</button>
      <button className="btn pri" onClick={() => go(journeyHref(1, c.id))}>Next: {journeyTitle(1)} <Icon name="arrow" /></button>
    </>
  ) : (
    <button className="btn pri" onClick={() => go('product/' + c.id)}>{c.blocked ? 'Open exception' : 'Evaluate selected asset'} <Icon name="arrow" /></button>
  );
  return (
    <Drawer title={`${c.id} · ${c.product}`} sub={`Returned asset · ${c.owner}`} foot={foot} onClose={onClose}>
      <div className="row" style={{ gap: 14, marginBottom: 12 }}>
        <Thumb cls={c.cls} style={{ width: 64, height: 52 }} />
        <div>
          <div className="row"><b style={{ fontSize: 16 }}>{c.product}</b><AssessChip c={c} /></div>
          <div className="note">{c.assetId} · {c.owner} · {c.location}{c.qty > 1 ? ' · ' + c.qty + ' units' : ''}</div>
        </div>
      </div>
      <dl className="kv" style={{ marginBottom: 14 }}>
        <dt>Condition</dt><dd><CondChip c={c} /></dd>
        <dt>Service-life evidence</dt><dd>{c.engLife}</dd>
        <dt>Received</dt><dd>{fmtDateYear(c.received)}</dd>
        <dt>Status</dt><dd><StageChip c={c} /></dd>
        {c.recommendation && <><dt>Best next action</dt><dd><b>{c.recommendation.plan}</b> · {money(c.recommendation.net)}</dd></>}
      </dl>
      <details className="dd" open>
        <summary>Details</summary>
        <dl className="kv">
          {Object.entries(c.spec).map(([k, v]) => <FragmentKV key={k} k={k} v={v} />)}
          <dt>Manufacturer</dt><dd>{c.mfr}</dd>
          <dt>Age</dt><dd>{c.age} years</dd>
        </dl>
      </details>
      <h4 style={{ margin: '14px 0 4px' }}>Evidence readiness <span className="note">{ready} of {ev.length} ready</span></h4>
      {ev.map((e) => <EvRow key={e.k} e={e} />)}
      {c.blocked && (
        <div className="callout bad" style={{ marginTop: 12 }}>
          <b>{c.blocked.gateName} gate</b>
          <br />
          {c.blocked.reason}
        </div>
      )}
    </Drawer>
  );
}
const FragmentKV = ({ k, v }: { k: string; v: string }) => <><dt>{k}</dt><dd>{v}</dd></>;

// ---------- expected returns ----------
function ExpectedTable({ onOpen }: { onOpen: (e: Expected) => void }) {
  const src = leaseSource();
  const rows = expectedVisible();
  return (
    <>
      <div className="callout info" style={{ marginBottom: 12 }} id="expNote">
        <b>Expected returns are derived from contract and lease expiry in the Contract Management application</b> ({src.vendor}). They are planning
        signals; nothing is committed until the asset is received and inspected. Likely outcomes are modelled from contract terms and past outcomes
        (buyouts, extensions, early terminations).
      </div>
      <div className="panel">
        <div className="tw">
          <table className="t" id="expTab">
            <thead>
              <tr>
                <th>Contract ID</th><th>Customer</th><th>Asset</th><th>Lease period</th><th>Contract expiry</th><th>Likely outcome</th>
                <th>Expected return</th><th>Site</th><th>Planning range</th><th>Source application</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => {
                const st = expectedStage(e);
                return (
                  <tr key={e.id} tabIndex={0} onClick={() => onOpen(e)} onKeyDown={onActivateKey(() => onOpen(e))}>
                    <td data-l="Contract"><b className="mono">{e.contract}</b><div className="note">{e.id} · {e.reason}</div></td>
                    <td data-l="Customer">{e.customer}</td>
                    <td data-l="Asset">
                      <div className="row" style={{ gap: 8, flexWrap: 'nowrap' }}>
                        <Thumb cls={e.cls} />
                        <span>{e.product}<div className="note">{classLabel(e.cls)}</div></span>
                      </div>
                    </td>
                    <td className="num nowrap" data-l="Lease period">
                      {fmtDate(e.lease.start)} {e.lease.start.getUTCFullYear()} – {fmtDate(e.lease.end)}
                      <div className="note">{e.lease.months} months</div>
                    </td>
                    <td className="num nowrap" data-l="Expiry">{fmtDateYear(e.expiry)}</td>
                    <td data-l="Likely outcome">
                      <b>{e.outcome.likely}</b> <span className="note num">{e.outcome.prob}%</span>
                      {!e.outcome.modelled && <div className="note">No history: expiry = return</div>}
                    </td>
                    <td className="num nowrap" data-l="Expected return">{e.outcome.window}</td>
                    <td data-l="Site">{e.loc}<div className="note">{e.wh}</div></td>
                    <td className="num" data-l="Planning range">{e.range}<div className="note" data-tip="Weighted by the probability of return">weighted {e.wRange}</div></td>
                    <td data-l="Source">
                      <span className="chip line" data-tip={'Contract / Lease Management application: ' + src.vendor + '. Its role here is to supply contract and lease expiry.'}>
                        Contract Management
                      </span>
                    </td>
                    <td data-l="Status">
                      <span className="chip line">Conditional</span>
                      {st && <> <span className="chip line afrun" data-tip="A case run starts at lease end">{st}</span></>}
                    </td>
                  </tr>
                );
              })}
              {!rows.length && (
                <tr><td colSpan={11}><div className="empty"><b>No expected returns in your scope</b>Contracts that expire soon appear here.</div></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function ExpectedDrawer({ e, onClose }: { e: Expected; onClose: () => void }) {
  const nav = useNavigate();
  const src = leaseSource();
  const t0 = +e.lease.start, t1 = +e.expiry, t2 = t1 + 12 * 864e5, pos = (t: number) => Math.round(((t - t0) / (t2 - t0)) * 100);
  const foot = routeAllowed('integration/map') ? <button className="btn" onClick={() => { onClose(); nav('/integration/map'); }}>Open source</button> : undefined;
  return (
    <Drawer title={`${e.contract} · ${e.product}`} sub={'Expected return · ' + e.id} foot={foot} onClose={onClose}>
      <div className="callout">
        Conditional plan derived from contract <b className="mono">{e.contract}</b> in the Contract Management application. Nothing is reserved or
        promised until receipt and inspection establish actual availability.
      </div>
      <h4 style={{ margin: '14px 0 6px' }}>Contract summary</h4>
      <dl className="kv">
        <dt>Customer</dt><dd>{e.customer}</dd>
        <dt>Return reason</dt><dd>{e.reason} · {e.signal}</dd>
        <dt>Lease period</dt><dd>{fmtDateYear(e.lease.start)} – {fmtDateYear(e.lease.end)} ({e.lease.months} months)</dd>
        <dt>Contract expiry</dt><dd>{fmtDateYear(e.expiry)}</dd>
        <dt>Receiving at</dt><dd>{e.loc} · {e.wh}</dd>
        <dt>Planning range</dt><dd>{e.range} (class prior, not decision-grade) · weighted by return probability {e.wRange}</dd>
      </dl>
      <h4 style={{ margin: '14px 0 6px' }}>Lease timeline</h4>
      <div className="exptl" role="img" aria-label="Lease start, contract expiry and expected return window">
        <span className="bar" style={{ display: 'block', height: 8, margin: '18px 0 6px' }}>
          <i style={{ width: pos(t1) + '%', background: 'var(--chart3)' }} />
        </span>
        <div className="row between note num">
          <span>Start {fmtDate(e.lease.start)}</span><span>Expiry {fmtDate(e.expiry)}</span><span>Return {e.outcome.window}</span>
        </div>
      </div>
      <h4 style={{ margin: '14px 0 6px' }}>
        Likely outcome{' '}
        <span className="note">{e.outcome.modelled ? 'modelled from contract terms and past outcomes' : 'no outcome history: expiry is treated as the return'}</span>
      </h4>
      <table className="t static tight">
        <tbody>
          {Object.entries(e.outcome.probs).map(([k, v]) => <tr key={k}><td>{k}</td><td className="r num"><b>{v}%</b></td></tr>)}
        </tbody>
      </table>
      <h4 style={{ margin: '14px 0 6px' }}>Source</h4>
      <dl className="kv">
        <dt>Source application</dt><dd>Contract Management · {src.vendor}</dd>
        <dt>Freshness</dt><dd>Updated {src.freshMin || 0} min ago</dd>
      </dl>
    </Drawer>
  );
}
