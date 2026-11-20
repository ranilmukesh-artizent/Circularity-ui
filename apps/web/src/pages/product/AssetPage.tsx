/**
 * Asset & Product Intelligence (#/product/asset/<CASE_ID>): everything about one returned asset, split into what the enterprise
 * systems supplied (Retrieved data) and what Circularity predicts (Predictions), with per-role detail tabs (assetPage in index.html).
 */
import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { fmtDate, fmtDateYear, fmtNumber, money } from '../../api/format';
import { useBackend } from '../../api/useBackend';
import {
  addDays, asHex, asModel, asSerial, asTitle, assetCase, assetFacts, assetHealth, assetRelated, assetTabAllowed, baseline, caseById, caseDemand,
  caseDiag, caseRul, classInfo, closedLastYear, confidence, demoVisible, diagKind, gateNames, journeyHref, leaseTrail, locName,
  myCases, partsAvailability, provenance, recert, rememberAsset, returnHistory, routeAllowed, routeInfo, skuUnits, snapshotTime, termMethod, upliftEnabled,
  valueOrder, valueState, type Case,
} from '../../api/product';
import { currentAccount } from '../../api/session';
import { sessionScoped } from '../../api/view';
import { Icon } from '../../ui/Icon';
import { onActivateKey } from '../../ui/keys';
import { Drawer, Modal, useOverlay } from '../../ui/Overlay';
import { toast } from '../../ui/toast';
import {
  AfBadge, AssetCtx, Condition, CostBuild, CostInputs, Econ, Eligibility, HealthRing, Panel, Photo, ProductSpecs, Prov, Quality, Related,
  Tbl, Timeline, useAsset, useMoney, type AsCtx,
} from './AssetPanels';
import { StageChip } from './AssetChips';
import { JourneyGuide, JourneyStrip } from './Journey';

const AS_TABS: [string, string][] = [
  ['overview', 'Overview'], ['lifecycle', 'Lifecycle'], ['condition', 'Condition'], ['product', 'Product & Components'], ['economic', 'Economic Analysis'],
  ['eligibility', 'Eligibility & Compliance'], ['data', 'Data & Evidence'], ['related', 'Related Assets'],
];
const AS_PARENT: Record<string, 'known' | 'pred'> = {
  known: 'known', pred: 'pred', overview: 'known', lifecycle: 'known', condition: 'known', product: 'known', data: 'known', related: 'known', economic: 'pred', eligibility: 'pred',
};
const AS_PAGES: Record<'known' | 'pred', string> = { known: 'Retrieved data', pred: 'Predictions' };

// view state kept for the session, as the demo's S.at.cur and S.skuF
type SkuF = { sku: string; k: 'g' | 'r'; v: string } | null;
type AsView = { local: boolean; skuF: SkuF };
const view = sessionScoped<AsView>(() => ({ local: false, skuF: null }));
const subs = new Set<() => void>();
const setView = (p: Partial<AsView>) => { view.current = { ...view.current, ...p }; subs.forEach((f) => f()); };
const useView = () => useSyncExternalStore((f) => (subs.add(f), () => subs.delete(f)), () => view.current);

/**
 * The photo lightbox (the CXO view's cxLb): a click anywhere or Esc (the overlay stack) closes it, and focus goes back
 * to the photo that opened it.
 */
function Lightbox({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const box = useRef<HTMLElement>(null);
  useOverlay(onClose, box);
  useEffect(() => box.current?.focus(), []);
  return (
    <div id="cxLb" className="cxlb" role="presentation" onClick={onClose}>
      <figure ref={box} role="dialog" aria-modal="true" aria-label="Product photo" tabIndex={-1}>{children}</figure>
    </div>
  );
}

const routeShort = (x: Case) => { const r = x.chosen || x.recommendation; return r ? routeInfo(r.id).short : 'No route yet'; };
const skuMatch = (x: Case, f: SkuF) => !f || (f.k === 'g' ? (x.grade || '—') === f.v : routeShort(x) === f.v);

export function AssetPage({ id, zone }: { id: string | null; zone: string | null }) {
  useBackend();
  const nav = useNavigate();
  const v = useView();
  const c = assetCase(id);
  const [tab, setTab] = useState<string>(zone === 'predicted' ? 'pred' : 'known');
  const [snap, setSnap] = useState(false);
  const [cmp, setCmp] = useState<string | null | undefined>(undefined); // undefined: closed; null: opened from the menu
  const [lb, setLb] = useState<{ src: string; alt: string } | null>(null);

  // a new link resets the view to the zone it names (the demo's S.at.hash check)
  useEffect(() => setTab(zone === 'predicted' ? 'pred' : 'known'), [c?.id, zone]);
  const cid = c?.id;
  useEffect(() => {
    if (!cid) return;
    rememberAsset(cid);
    document.title = 'Product · Circularity Decision Workbench';
  }, [cid]);
  useEffect(() => {
    if (!zone) return;
    const t = window.setTimeout(() => {
      const z = document.getElementById(zone === 'predicted' ? 'aszPred' : 'aszKnown');
      z?.scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    }, 40);
    return () => window.clearTimeout(t);
  }, [c?.id, zone]);

  const h = useMemo(() => (c ? assetHealth(c) : null), [c]);
  if (!c || !h) {
    return (
      <div className="empty">
        <b>Asset not found</b>Choose a returned asset from <a href="#/product/received">Returned assets</a>.
      </div>
    );
  }
  const cur = !AS_PARENT[tab] || (!['known', 'pred', 'overview'].includes(tab) && !assetTabAllowed(tab)) ? 'known' : tab;
  const ctx: AsCtx = {
    c, h, local: v.local,
    setLocal: (local) => setView({ local }),
    openTab: (t) => {
      if (!assetTabAllowed(t)) return toast('That tab is not part of the ' + (currentAccount()?.role ?? '') + ' view.');
      setTab(t);
    },
    compare: (x) => setCmp(x ?? null),
    snapshot: () => (c.snapshot ? setSnap(true) : toast('No decision yet, so no evidence snapshot exists.')),
    zoom: (src, alt) => setLb({ src, alt }),
  };
  const zoneGo = (z: 'known' | 'pred') => {
    setTab(z);
    nav('/product/asset/' + c.id + '?zone=' + (z === 'pred' ? 'predicted' : 'known'));
  };
  const jOn = demoVisible(c.id);

  return (
    <AssetCtx.Provider value={ctx}>
      {jOn && <JourneyStrip id={c.id} at={1} />}
      <div className="as">
        <AssetHead />
        <SkuStrip f={v.skuF} />
        <div id="asBody">
          {cur === 'known' || cur === 'pred' || cur === 'overview' ? (
            <Overview page={AS_PARENT[cur]} zone={zone} onZone={zoneGo} />
          ) : (
            <>
              <nav className="crumbs ascr2" aria-label="Asset page">
                <button className="lnk" onClick={() => setTab(AS_PARENT[cur])}>{AS_PAGES[AS_PARENT[cur]]}</button> <span>›</span>{' '}
                <b>{(AS_TABS.find((x) => x[0] === cur) || [cur, cur])[1]}</b>
              </nav>
              {cur === 'lifecycle' && <TabLifecycle />}
              {cur === 'condition' && <TabCondition />}
              {cur === 'product' && <TabProduct />}
              {cur === 'economic' && <TabEconomic />}
              {cur === 'eligibility' && <TabEligibility />}
              {cur === 'data' && <TabData />}
              {cur === 'related' && <TabRelated />}
            </>
          )}
        </div>
      </div>
      {snap && <SnapshotDrawer c={c} onClose={() => setSnap(false)} />}
      {cmp !== undefined && <CompareModal id={cmp} onClose={() => setCmp(undefined)} />}
      {lb && (
        <Lightbox onClose={() => setLb(null)}>
          <img src={lb.src} alt={lb.alt} />
          <figcaption>
            {c.product} · {c.assetId} · {c.id}{c.grade ? ' · Grade ' + c.grade : ''}
            <span className="note"> · Click or Esc to close</span>
          </figcaption>
        </Lightbox>
      )}
      {jOn && <JourneyGuide id={c.id} at={1} />}
    </AssetCtx.Provider>
  );
}

// ---------- head: breadcrumb, unit picker, actions, photo, facts and health ----------
function AssetHead() {
  const { c, h, compare, snapshot } = useAsset();
  const nav = useNavigate();
  const [menu, setMenu] = useState(false);
  const link = window.location.href.split('#')[0] + '#/product/asset/' + c.id;
  useEffect(() => {
    if (!menu) return;
    const f = (e: MouseEvent) => { if (!(e.target as HTMLElement).closest('.asmenu')) setMenu(false); };
    document.addEventListener('click', f);
    return () => document.removeEventListener('click', f);
  }, [menu]);
  const act = (f: () => void) => () => { setMenu(false); f(); };
  const copy = () => {
    const u = window.location.href;
    (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(() => toast('Link copied.'), () => toast('Copy this link: ' + u, 6000));
  };
  return (
    <>
      <nav className="crumbs ascr" aria-label="Breadcrumb">
        <Link to="/product/received">Assets</Link> <span>›</span> <span>{classInfo(c.cls).plural}</span> <span>›</span> <span>{asModel(c)}</span> <span>›</span> <b>{c.assetId}</b>
      </nav>
      <div className="phead asph2">
        <div className="row" style={{ gap: 14, flexWrap: 'nowrap', alignItems: 'flex-start' }}>
          <span className="asico"><Icon name="product" /></span>
          <div>
            <h1>Asset &amp; Product Intelligence</h1>
            <p>Unified lifecycle view with evidence from enterprise systems to support circularity decisions.</p>
          </div>
        </div>
        <div className="row asact">
          <AssetSelect />
          <a className="btn" href={link} target="_blank" rel="noopener">Open in new tab</a>
          <details className="asmenu" open={menu}>
            <summary className="btn pri" onClick={(e) => { e.preventDefault(); setMenu((m) => !m); }}>Actions <span aria-hidden="true">▾</span></summary>
            <div className="asmenu-list" role="menu">
              <button role="menuitem" onClick={act(() => nav('/product/' + c.id))}>Open decision analysis</button>
              <button role="menuitem" onClick={act(snapshot)}>Evidence snapshot</button>
              <button role="menuitem" onClick={act(copy)}>Copy link</button>
              <button role="menuitem" onClick={act(() => compare())}>Compare similar assets</button>
              <button role="menuitem" onClick={act(() => window.setTimeout(() => window.print(), 200))}>Print or save as PDF</button>
            </div>
          </details>
        </div>
      </div>
      <section className="aship">
        <div className="asphoto"><Photo x={c} /></div>
        <div className="asmain">
          <div className="asttl">
            <h2>{asTitle(c)}</h2>
            <span className="note">{Object.values(c.spec || {}).slice(0, 3).join(' · ')}</span>
            <span className="chip line">{classInfo(c.cls).label}</span>
            <StageChip c={c} />
          </div>
          <dl className="asfacts">
            {assetFacts(c).map((f) => <div key={f[0]}><dt>{f[0]}</dt><dd>{f[1]}</dd></div>)}
          </dl>
        </div>
        <div className="ashealth">
          <h3>Overall asset health</h3>
          <HealthRing h={h} />
          <div className="note" style={{ marginTop: 6 }}>{h.est ? 'Estimated: no inspection grade yet.' : 'Grade ' + c.grade + ' · modelled from grade, age and class life.'}</div>
        </div>
      </section>
    </>
  );
}

/** Product (SKU) → Customer → Unit (assetSelect). */
function AssetSelect() {
  const { c } = useAsset();
  const nav = useNavigate();
  const { skuF } = useView();
  const all = myCases(), m = asModel(c);
  const cnt = (l: Case[], fn: (x: Case) => string) => l.reduce<Record<string, number>>((o, x) => { const k = fn(x); o[k] = (o[k] || 0) + 1; return o; }, {});
  const mc = cnt(all, asModel), cc = cnt(all.filter((x) => asModel(x) === m), (x) => x.owner);
  const f = skuF && skuF.sku === m + '|' + c.owner ? skuF : null;
  const units = skuUnits(c).filter((x) => x.id === c.id || skuMatch(x, f));
  const byId = (a: Case, b: Case) => (a.id < b.id ? -1 : 1);
  const pickModel = (v: string) => {
    const l = myCases().filter((x) => asModel(x) === v).sort(byId), p = l.find((x) => x.owner === c.owner) || l[0];
    setView({ skuF: null });
    if (p) nav('/product/asset/' + p.id);
  };
  const pickCust = (v: string) => {
    const l = myCases().filter((x) => asModel(x) === asModel(c) && x.owner === v).sort(byId);
    setView({ skuF: null });
    if (l[0]) nav('/product/asset/' + l[0].id);
  };
  const label = (x: Case) => {
    const r = x.chosen || x.recommendation;
    return `${asSerial(x)} · ${x.assetId} · ${x.grade ? 'Grade ' + x.grade : 'Not graded'} · ${r ? routeShort(x) + ' · ' + money(r.net) + ' est.' : 'No route yet'} · ${x.location}`;
  };
  return (
    <div className="skusel" role="group" aria-label="Choose a returned unit">
      <label htmlFor="skuM">Product (SKU)
        <select className="sel" id="skuM" value={m} onChange={(e) => pickModel(e.target.value)}>
          {Object.keys(mc).sort().map((k) => <option key={k} value={k}>{k} ({mc[k]})</option>)}
        </select>
      </label>
      <label htmlFor="skuC">Customer
        <select className="sel" id="skuC" value={c.owner} onChange={(e) => pickCust(e.target.value)}>
          {Object.keys(cc).sort().map((k) => <option key={k} value={k}>{k} ({cc[k]})</option>)}
        </select>
      </label>
      <label htmlFor="asSw">Unit{f && <> <span className="note">(filtered)</span></>}
        <select className="sel asw" id="asSw" value={c.id} onChange={(e) => nav('/product/asset/' + e.target.value)}>
          {units.map((x) => <option key={x.id} value={x.id}>{label(x)}</option>)}
        </select>
      </label>
    </div>
  );
}

/** How many units of this product came back from this customer, by grade and route (skuStrip). */
function SkuStrip({ f: f0 }: { f: SkuF }) {
  const { c } = useAsset();
  const m = asModel(c), l = skuUnits(c), key = m + '|' + c.owner, f = f0 && f0.sku === key ? f0 : null;
  const g: Record<string, number> = {}, rt: Record<string, number> = {};
  l.forEach((x) => { const k = x.grade || '—'; g[k] = (g[k] || 0) + 1; const rk = routeShort(x); rt[rk] = (rt[rk] || 0) + 1; });
  const closed = closedLastYear(c);
  const pick = (k: 'g' | 'r', v: string) => {
    const on = !!f && f.k === k && f.v === v, nf = on ? null : { sku: key, k, v };
    setView({ skuF: nf });
    const n = l.filter((x) => skuMatch(x, nf)).length;
    toast(on ? 'Showing every unit.' : n + ' unit' + (n === 1 ? '' : 's') + ' match. Choose one in Unit.');
  };
  const chip = (k: 'g' | 'r', v: string, n: number) => (
    <button key={k + v} className="skuc" aria-pressed={!!f && f.k === k && f.v === v} onClick={() => pick(k, v)}>
      {k === 'g' ? (v === '—' ? 'Not graded' : 'Grade ' + v) : v} <b className="num">{n}</b>
    </button>
  );
  return (
    <section className="panel skus" id="skuStrip" aria-label="Units of this product">
      <div className="pb">
        <div className="skuh">
          <b>{m} · {c.owner}</b>
          <span className="skun"><b className="num">{l.length}</b> unit{l.length === 1 ? '' : 's'} returned now</span>
          <span className="note">{fmtNumber(closed)} more closed in the last 12 months</span>
        </div>
        <div className="skur">
          <span className="note">By inspection grade <span className="aszb ret" style={{ marginLeft: 4 }}>Retrieved</span></span>
          {Object.keys(g).sort().map((k) => chip('g', k, g[k]))}
        </div>
        <div className="skur">
          <span className="note">By recommended route <span className="aszb mod" style={{ marginLeft: 4 }}>Model</span></span>
          {Object.entries(rt).sort((a, b) => b[1] - a[1]).map(([k, n]) => chip('r', k, n))}
        </div>
        <p className="note" style={{ margin: 0 }}>
          Each returned unit of the same product has its own condition, life, value and route. Choose one in <b>Unit</b> above
          {f ? '; the Unit list shows only the units that match your selection' : ''}.
        </p>
      </div>
    </section>
  );
}

// ---------- the two pages: Retrieved data and Predictions (asOverview) ----------
function Overview({ page, zone, onZone }: { page: 'known' | 'pred'; zone: string | null; onZone: (z: 'known' | 'pred') => void }) {
  const { c } = useAsset();
  const ok = assetTabAllowed;
  const ws = c.cls === 'motor' || c.cls === 'pump' ? 'MRO' : 'Inspection';
  if (page === 'known') {
    return (
      <div className="aszs">
        <div className={'asz known ' + (zone === 'known' ? 'on' : '')} id="aszKnown" aria-labelledby="aszKh">
          <header className="aszh">
            <span className="aszk">Retrieved data · journey step 1, supply evidence</span>
            <h2 id="aszKh">Retrieved from enterprise systems</h2>
            <p className="note">Facts pulled from MRO, EAM, QMS, ERP, WMS and PLM. Each card names its source. Circularity reads these; it does not change them.</p>
            <button className="lnk aszsw" onClick={() => onZone('pred')}>See what Circularity predicts for this asset →</button>
          </header>
          <LeasePanel />
          <div className="asz2 aszw">
            <Panel t="Diagnostic condition" badge={<Prov k="ret" sys={ws} />}><KnownDiag /></Panel>
            <Panel t="Certified period" badge={<Prov k="ret" sys="QMS" />}><KnownCert /></Panel>
          </div>
          {ok('condition') && <Panel t="Inspection findings" tab="condition" badge={<Prov k="ret" sys="Inspection" />}><Condition /></Panel>}
          <Panel t="Cost inputs" badge={<Prov k="ret" sys="OMS, PLM, EAM, procurement" />} id="asCostCard"><CostInputs /></Panel>
          {ok('lifecycle') && <Panel t="Lifecycle evidence timeline" tab="lifecycle" cls="aszw" badge={<Prov k="ret" sys="ERP, EAM, WMS" />}><Timeline ret /></Panel>}
          {ok('lifecycle') && <Panel t="Return history of this unit" badge={<Prov k="ret" sys="Lease, WMS" />}><ReturnHistory /></Panel>}
          {ok('related') && <Panel t="Related assets and fleet context" tab="related" badge={<Prov k="ret" sys="ERP" />}><Related /></Panel>}
          {ok('product') && <Panel t="Product specs" tab="product" cls="aszw" badge={<Prov k="ret" sys="PLM, ERP" />}><ProductSpecs ret /></Panel>}
        </div>
      </div>
    );
  }
  return (
    <div className="aszs">
      <div className={'asz pred ' + (zone === 'predicted' ? 'on' : '')} id="aszPred" aria-labelledby="aszPh">
        <header className="aszh">
          <span className="aszk">Predictions · eligibility, demand, life and value for this asset</span>
          <h2 id="aszPh">Predicted and computed by Circularity</h2>
          <p className="note">Model estimates and rule results, each labelled with what produced it. Recommended routes and values appear only on this page.</p>
          <button className="lnk aszsw" onClick={() => onZone('known')}>← Retrieved data</button>
        </header>
        <Panel t="Commercial value" cls="aszw" badge={<Prov k="mod" sys="Recommendation service" />} id="asValueCard"><PredRec /></Panel>
        {ok('eligibility') && <Panel t="Eligibility and gates" tab="eligibility" badge={<Prov k="rul" sys="Gate engine" />} id="asEligCard"><Eligibility /></Panel>}
        <Panel t="Matched demand" badge={<Prov k="rul" sys="Demand matching" />} id="asDemandCard"><MatchedDemand /></Panel>
        <Panel t="Estimated remaining useful life" badge={<Prov k="mod" sys={'RUL model ' + (c.model || '')} />} id="asRulCard"><PredRul /></Panel>
        {ok('data') && <Panel t="Data and evidence quality" tab="data" badge={<Prov k="rul" sys="Evidence scoring" />}><Quality /></Panel>}
        {ok('economic') && (
          <Panel t="Economic intelligence" tab="economic" cls="aszw" badge={<Prov k="mod" sys="Prediction model" />} id="asEconCard">
            <Econ /><CostBuild /><PredRoutes />
          </Panel>
        )}
      </div>
    </div>
  );
}

/** Lease end, return and transit: added to Retrieved data by the agent layer (afLeaseHTML). */
function LeasePanel() {
  const { c } = useAsset();
  const L = leaseTrail(c);
  if (!L) return null;
  const kv = (rows: [string, ReactNode][]) => <dl className="afkv">{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>;
  return (
    <section className="panel aflease" id="afLease">
      <div className="ph"><h3>Lease end, return and transit</h3><span className="sp" /><AfBadge k="Retrieved" /></div>
      <div className="pb afl3">
        <div>
          <h5>1 · Lease ends</h5>
          {kv([['Lease', L.lease], ['Ended', fmtDateYear(L.end)], ['Customer intent', L.intent], ['Usage', L.usage]])}
          <p className="note">Lease management · CRM</p>
        </div>
        <div>
          <h5>2 · Return authorised</h5>
          {kv([['Authorisation', L.rma + ' · ' + fmtDate(L.auth)], ['Fees', L.fee ? money(L.fee) : 'None'], ['Replacement order', L.repl || 'None'], ['Book value', money(L.book) + ' · acquired ' + fmtDateYear(L.acq)]])}
          <p className="note">Lease management · ERP finance</p>
        </div>
        <div>
          <h5>3 · Pickup and transit</h5>
          {kv([['Picked up', fmtDate(L.pickup) + ' · ' + L.carrier], ['Arrived', fmtDate(L.eta)], ['Freight', money(L.freight)], ['Received', c.location + ' · ' + fmtDate(c.received)]])}
          <p className="note">TMS / 3PL · WMS</p>
        </div>
      </div>
    </section>
  );
}

function KnownDiag() {
  const { c } = useAsset();
  const D = caseDiag(c);
  if (!D) return <div className="asfig"><b>Not inspected yet</b><span className="note">Waiting for the inspection report</span></div>;
  return (
    <div className="asfig">
      <span className="note">{D.metric}</span>
      <b className="big">{D.value}</b>
      {c.grade && <span>Inspection grade <b>{c.grade}</b></span>}
      <span className="note">{D.source} · {D.at}</span>
      {diagKind(c.cls) !== 'grade' && <span className="note">Value modelled from grade, age and class</span>}
    </div>
  );
}

function KnownCert() {
  const { c } = useAsset();
  const R = caseRul(c);
  if (!R) return <div className="asfig"><b>No certified period</b><span className="note">{c.engLife || 'Not assessed'}</span></div>;
  return (
    <div className="asfig">
      <span className="note">Certified operating period</span>
      <b className="big num">{R.certMonths} months</b>
      <span className="note">{R.basis}</span>
      <span className="note mono">{R.certRef}</span>
      <span className="note">Circularity reads this certificate; it does not certify equipment.</span>
    </div>
  );
}

function ReturnHistory() {
  const { c } = useAsset();
  const l = returnHistory(c);
  return (
    <>
      <p className="note" style={{ margin: '0 0 6px' }}>This unit has come back {l.length} time{l.length === 1 ? '' : 's'} before this return.</p>
      <ol className="asrh">
        {l.map((x, i) => (
          <li key={i}>
            <b>Returned {fmtDateYear(x.at)} by {x.cust}</b>
            <span className="chip line">Grade {x.grade}</span>
            <span>{x.dec} · {x.site}</span>
            <span className="note">{x.ref}{x.der ? ' · derived from lease history' : ''}</span>
          </li>
        ))}
      </ol>
    </>
  );
}

function PredRul() {
  const { c, h } = useAsset();
  const R = caseRul(c);
  return (
    <>
      {R ? (
        <div className="asfig">
          <span className="note">Estimated remaining useful life</span>
          <b className="big num">{R.estLow}–{R.estHigh} months</b>
          <span className="note">Most likely {R.estMonths} months · modelled range. The certified period on the left is the firm figure.</span>
        </div>
      ) : (
        <div className="asfig"><b>No estimate yet</b><span className="note">Needs an inspection grade</span></div>
      )}
      <h4 style={{ fontSize: 12.5, margin: '10px 0 4px', color: 'var(--ink2)' }}>Component health <span className="note">(modelled from grade and age)</span></h4>
      {h.comps.map((x) => <div key={x.n} className="asrow"><span>{x.n}</span><span className={'chip ' + x.cls}>{x.st}</span></div>)}
    </>
  );
}

const AS_VST = { pending: ['Pending evaluation', 'line'], predicted: ['Predicted, not committed', 'y'], committed: ['Committed', 'ok'], actual: ['Predicted vs actual', 'ok'] };
/** Commercial value: pending, predicted, committed against the order, or predicted vs actual (asPredRec). */
function PredRec() {
  const { c } = useAsset();
  const r = c.chosen || c.recommendation, vs = valueState(c);
  const chip = <span className={'chip ' + AS_VST[vs][1]} id="asVState" data-vstate={vs}>{AS_VST[vs][0]}</span>;
  if (!r) {
    return (
      <div className="asrec">
        <div>{chip}</div>
        <div className="empty"><b>Evaluated in steps 2–4</b>{c.blocked ? c.blocked.reason : 'Evidence is needed before any route is priced.'}</div>
      </div>
    );
  }
  const M = caseDemand(c), rc = recert(c, r), R = caseRul(c), hz = M && R ? Math.min(rc ? rc.need : M.horizonMonths, R.certMonths) : null;
  const cf = confidence(c, r), base = baseline(c), up = base == null || r.id === 'resale' ? null : r.net - base, vo = valueOrder(c), o = c.outcome, dv = o ? o.net - r.net : 0;
  return (
    <div className="asrec">
      <div className="row" style={{ gap: 8 }}>
        {chip}
        <span className="note">
          {vs === 'predicted' ? 'A prediction until the plan is approved and handed off.' : vs === 'committed' ? 'Approved and handed off; the actual comes back after step 9.' : 'Actual confirmed by Finance.'}
        </span>
      </div>
      <div className="asrect">{r.plan}</div>
      <div className="asrecv"><b className="num">{money(r.net)}</b><span className="note num">predicted net · P10–P90 {money(r.p10)} to {money(r.p90)}</span></div>
      {r.id === 'redeploy' && M && M.order && (
        <div className="asrow" id="asOrderLine">
          <span>Order line <span className="note">IBM Sterling OMS · need-by {fmtDateYear(M.needBy!)} · replaces planned {M.avoidedPo}</span></span>
          <b><span className="mono">{M.order} line {M.line}</span> · {c.owner} · {locName(M.shipTo)}</b>
        </div>
      )}
      {vs !== 'predicted' && (
        <div className="asrow" id="asVOrder">
          <span>Committed against <span className="note">{vo ? (vo.ack ? 'returned by ' + vo.sys : 'matched order; ERP confirms it on acknowledgement') : 'order reference pending'}</span></span>
          <b>{vo ? <>{vo.kind} <span className="mono">{vo.ref}</span></> : 'Approval ' + (c.approval?.ref ?? '')}</b>
        </div>
      )}
      {vs === 'actual' && o && (
        <>
          <div className="asrow"><span>Actual net <span className="note">confirmed by Finance</span></span><b className="num">{money(o.net)}</b></div>
          <div className="asrow"><span>Variance</span><b className={'num ' + (dv < 0 ? 'tx-bad' : 'tx-ok')}>{dv === 0 ? 'None' : (dv > 0 ? '+' : '−') + money(Math.abs(dv))}</b></div>
        </>
      )}
      <div className="asrow"><span>Confidence</span><b>{cf}</b></div>
      {up != null && upliftEnabled() && (
        <div className="asrow" data-tip="Current practice: sell the asset as-is or scrap it. Uplift is the predicted gain of the recommended route over the best of those.">
          <span>Uplift vs sell as-is or scrap</span><b className={'num ' + (up >= 0 ? 'tx-ok' : 'tx-bad')}>{up >= 0 ? '+' : '−'}{money(Math.abs(up))}</b>
        </div>
      )}
      {hz != null && <div className="asrow"><span>Demand horizon <span className="note">capped at the certified period</span></span><b className="num">{hz} months</b></div>}
      {rc && <div className="asrow"><span className="chip warn">Needs re-certification</span><span className="note">Demand needs {rc.need} months; certified for {rc.cert}</span></div>}
      <div className="row" style={{ marginTop: 6 }}>
        {vs === 'actual'
          ? <a className="btn pri sm" href={'#/' + journeyHref(10, c.id)}>Line by line, step 10 →</a>
          : <Link className="btn pri sm" to={'/product/' + c.id}>Evaluate treatments →</Link>}
      </div>
    </div>
  );
}

/** The demand Circularity matched for this asset (asDemand). */
function MatchedDemand() {
  const { c } = useAsset();
  const d = c.demand || {}, M = caseDemand(c), R = caseRul(c), rows: ReactNode[] = [];
  const row = (l: string, v: string, st: string, t: string, n: string) => (
    <div key={l} className="asrow"><span><b>{l}</b><div className="note">{n}</div></span><span className="right"><b className="mono">{v}</b> <span className={'chip ' + t}>{st}</span></span></div>
  );
  if (M && M.order) {
    rows.push(row('Customer contract demand', M.order + ' · ' + c.owner + ', ' + (M.site || '—'), M.confirmed ? 'Confirmed' : 'Forecast', M.confirmed ? 'ok' : 'warn',
      `Replacement under ${c.owner}'s contract: line ${M.line} in IBM Sterling OMS, ship to ${locName(M.shipTo)}, need-by ${fmtDateYear(M.needBy!)}. It accepts a certified refurbished unit; orders that require a new unit are never matched.`));
    if (R) {
      const ok = R.certMonths >= M.horizonMonths;
      rows.push(row('Certified life needed', M.horizonMonths + ' months needed · ' + R.certMonths + ' certified', ok ? 'Covered' : 'Re-certify', ok ? 'ok' : 'warn',
        'The contract needs this much life; the certified period comes from QMS (' + R.certRef + '). Redeploy is subject to it.'));
    }
  }
  if (d.lease) rows.push(row('Re-lease opportunity', d.lease, 'Forecast', 'warn', 'Opportunity in CRM and lease management, where a contract is likely to be extended'));
  if (d.parts) rows.push(row('Internal parts demand', 'Open requests', 'Forecast', 'warn', 'Parts requests from repair work orders'));
  if (!rows.length) return <div className="empty"><b>No contract demand matched</b>Only external market routes apply.</div>;
  return (
    <>
      {rows}
      <p className="note" style={{ margin: '6px 0 0' }}>
        Matched by Circularity from orders, contracts and opportunities in ERP and CRM. The routes that use this demand are priced in step 3.
      </p>
    </>
  );
}

function PredRoutes() {
  const { c } = useAsset();
  const m = useMoney();
  const rs = (c.routes || []).filter((r) => !r.excluded).sort((a, b) => b.net - a.net).slice(0, 4), rec = c.chosen || c.recommendation;
  if (!rs.length) return null;
  return (
    <>
      <h4 style={{ fontSize: 12.5, margin: '14px 0 4px', color: 'var(--ink2)' }}>Predicted value by route</h4>
      <Tbl head={[['Route'], ['Net', 'r'], ['P10 to P90', 'r']]} rows={rs.map((r, i) => (
        <tr key={i} className={rec && r === rec ? 'sel' : ''}>
          <td>{r.plan || routeInfo(r.id).name}</td><td className="r num"><b>{m(r.net)}</b></td><td className="r num">{m(r.p10)} to {m(r.p90)}</td>
        </tr>
      ))} />
    </>
  );
}

// ---------- detail views ----------
const WO_TYPES = ['Preventive maintenance', 'Inspection', 'Bearing and seal replacement', 'Corrective repair', 'Calibration and test', 'Firmware and settings update'];
function TabLifecycle() {
  const { c } = useAsset();
  const dep = addDays(new Date(c.received), -Math.round(c.age * 365) + 90), n = Math.max(2, Math.round(c.age * 1.4) + (asHex(c, 'wo') % 3)), K = classInfo(c.cls);
  const wo = Array.from({ length: Math.min(n, 8) }, (_, i) => {
    const d = addDays(dep, Math.round(((i + 1) / (n + 1)) * (c.age * 365 - 120))), t = WO_TYPES[asHex(c, 'wt' + i) % WO_TYPES.length];
    const cost = Math.round(K.pnew * c.qty * (0.004 + (asHex(c, 'wc' + i) % 30) / 1500));
    return (
      <tr key={i}>
        <td className="mono">WO-{90000 + (asHex(c, 'wn' + i) % 9999)}</td><td className="num nowrap">{fmtDateYear(d)}</td><td>{t}</td><td>{i % 3 === 2 ? 'FSM' : 'EAM'}</td>
        <td className="r num">{money(cost)}</td><td><span className="chip ok">Closed</span></td>
      </tr>
    );
  });
  return (
    <>
      <Panel t="Lifecycle evidence timeline"><Timeline full /></Panel>
      <Panel t="Service history">
        <Tbl head={[['Work order'], ['Date'], ['Type'], ['System'], ['Cost', 'r'], ['Status']]} rows={wo} />
        <div className="note" style={{ marginTop: 6 }}>Showing {wo.length} of {n} recorded work orders. Costs are estimates.</div>
      </Panel>
    </>
  );
}

const EV_ST: Record<string, [string, string]> = { ready: ['Complete', 'ok'], partial: ['Partial', 'warn'], stale: ['Stale', 'warn'], missing: ['Missing', 'bad'], conflict: ['Conflict', 'bad'] };
function TabCondition() {
  const { c, h, zoom } = useAsset();
  const ev = (c.evidence || []).filter((e) => ['insp', 'eng', 'photo', 'svc'].includes(e.k)), pos = ['36% 60%', '70% 40%', '20% 30%', '55% 85%'];
  const src = 'assets/products/' + ({ motor: 'motor', pump: 'pump', control: 'control', drill: 'powertool', batch: 'powertool', it: 'it' } as Record<string, string>)[c.cls] + '.webp';
  return (
    <>
      <div className="asg2 r1b">
        <Panel t="Inspection findings" badge={<Prov k="ret" sys="Inspection" />}><Condition /></Panel>
        <Panel t="Component condition">
          {h.comps.map((x) => (
            <div key={x.n} className="asrow">
              <span>{x.n}</span>
              <span className="asmeter"><i style={{ width: Math.round(x.h * 100) + '%', background: x.cls === 'ok' ? 'var(--ok)' : x.cls === 'warn' ? '#D4A800' : 'var(--bad)' }} /></span>
              <b className="num">{Math.round(x.h * 100)}</b>
              <span className={'chip ' + x.cls}>{x.st}</span>
            </div>
          ))}
        </Panel>
      </div>
      <Panel t="Inspection evidence">
        <Tbl head={[['Evidence'], ['Source'], ['State'], ['Detail']]} rows={ev.map((e) => (
          <tr key={e.k}>
            <td>{e.label}</td><td>{e.source}</td>
            <td><span className={'chip ' + ((EV_ST[e.state] || [])[1] || 'line')}>{(EV_ST[e.state] || [e.state])[0]}</span></td>
            <td className="note">{e.note || 'Updated ' + e.fresh}</td>
          </tr>
        ))} />
      </Panel>
      <Panel t="Photos">
        <div className="asgal">
          {pos.map((p, i) => {
            const alt = `${c.product} view ${i + 1}`, open = () => zoom(src, alt);
            return (
              <div key={i} className="asimg zoomg" style={{ '--op': p } as React.CSSProperties} role="button" tabIndex={0} onClick={open} onKeyDown={onActivateKey(open)}>
                <img src={src} alt={alt} loading="lazy" />
              </div>
            );
          })}
        </div>
        <div className="note" style={{ marginTop: 6 }}>Close-up crops of the product photo. Inspection photos attach here when they arrive from the inspection system.</div>
      </Panel>
    </>
  );
}

function TabProduct() {
  const { c, h } = useAsset();
  const K = classInfo(c.cls);
  const parts = partsAvailability(c, h);
  const bom = h.comps.map((x, i) => {
    const p = parts[i], lead = p.st === 'In stock' ? '2–3 days' : p.st === 'Limited' ? '7–10 days' : '21+ days', alt = asHex(c, 'alt' + x.n) % 3 !== 0;
    return (
      <tr key={x.n}>
        <td><b>{x.n}</b></td><td className="mono">{K.pre}-{String(1000 + (asHex(c, 'pn' + x.n) % 8999))}</td>
        <td><span className={'chip ' + x.cls}>{x.st}</span></td><td className={'tx-' + p.cls}><b>{p.st}</b></td>
        <td className="r num">{p.q}</td><td className="num">{lead}</td>
        <td>{alt ? <span className="chip ok">Approved alternate</span> : <span className="chip line">None approved</span>}</td>
      </tr>
    );
  });
  return (
    <>
      <Panel t="Product specs" badge={<Prov k="ret" sys="PLM, ERP" />}><ProductSpecs /></Panel>
      <Panel t="Bill of materials and parts">
        <Tbl head={[['Component'], ['Part number'], ['Health'], ['Availability'], ['In stock', 'r'], ['Lead time'], ['Alternates']]} rows={bom} />
        <div className="note" style={{ marginTop: 6 }}>Component health is modelled from grade and age.</div>
      </Panel>
    </>
  );
}

function TabEconomic() {
  const { c } = useAsset();
  const m = useMoney();
  const rs = (c.routes || []).slice().sort((a, b) => b.net - a.net), rec = c.recommendation;
  const rows = rs.map((r, i) => {
    const isR = !!rec && r === rec;
    return (
      <tr key={i} className={isR ? 'sel' : ''}>
        <td><b>{r.plan || routeInfo(r.id).name}</b><div className="note">{r.demandLabel || ''}</div></td>
        <td className="r num"><b>{m(r.net)}</b></td>
        <td className="r num">{m(r.p10)} to {m(r.p90)}</td>
        <td>{isR ? <span className="chip y">Recommended</span> : r.excluded ? <span className="chip bad" data-tip={r.failReason || ''}>Excluded</span> : <span className="chip ok">Eligible</span>}</td>
      </tr>
    );
  });
  const terms = rec ? rec.terms.map((t, i) => {
    const mt = termMethod(c, rec, t);
    return (
      <tr key={i}>
        <td>{t.label} <span className={'exm ' + mt.cls} data-tip={mt.tip}>{mt.m}</span></td>
        <td className={'r num ' + (t.amt < 0 ? 'tx-bad' : 'tx-ok')}>{m(t.amt)}</td>
      </tr>
    );
  }) : [];
  return (
    <>
      <Panel t="Economic intelligence"><Econ /><CostBuild /></Panel>
      <div className="asg2 r1b">
        <Panel t="Route comparison"><Tbl head={[['Route'], ['Net', 'r'], ['P10 to P90', 'r'], ['Status']]} rows={rows} /></Panel>
        <Panel t="How the recommended net is built">
          {rec ? (
            <Tbl head={[['Term'], ['Amount', 'r']]} rows={[...terms, <tr key="net"><td><b>Predicted net</b></td><td className="r num"><b>{m(rec.net)}</b></td></tr>]} />
          ) : (
            <div className="empty"><b>No recommendation yet</b>Evidence is missing, so no route has been priced.</div>
          )}
        </Panel>
      </div>
    </>
  );
}

function TabEligibility() {
  const { c } = useAsset();
  const r = c.recommendation || (c.routes || [])[0], G = gateNames();
  const gs = r ? r.gates.map((x, i) => (
    <tr key={i}>
      <td><b>{i + 1}. {G[i]}</b></td>
      <td><span className={'chip ' + { pass: 'ok', fail: 'bad', skip: 'line', warn: 'warn' }[x]}>{{ pass: 'Passed', fail: 'Failed', skip: 'Not reached', warn: 'Warning' }[x]}</span></td>
      <td className="note">{(r.gateNotes || [])[i] || (x === 'fail' ? r.failReason : '')}</td>
    </tr>
  )) : [];
  const ex = (c.routes || []).filter((x) => x.excluded).map((x, i) => (
    <tr key={i}><td>{x.plan || routeInfo(x.id).name}</td><td>{G[x.failGate ?? -1] || '—'}</td><td className="note">{x.failReason}</td></tr>
  ));
  return (
    <>
      <Panel t="Eligibility and compliance"><Eligibility /></Panel>
      <Panel t={'Six eligibility gates' + (r ? ' · ' + (r.plan || routeInfo(r.id).short) : '')}>
        <Tbl head={[['Gate'], ['Result'], ['Reason']]} rows={gs} />
        <div className="note" style={{ marginTop: 6 }}>A failed gate withholds the route. No agent or connector can waive it. Policy version POL-3.2.</div>
      </Panel>
      {ex.length > 0 && <Panel t="Routes withheld"><Tbl head={[['Route'], ['Failed gate'], ['Reason']]} rows={ex} /></Panel>}
    </>
  );
}

function TabData() {
  const { c, snapshot } = useAsset();
  const nav = useNavigate();
  const rows = (c.evidence || []).map((e) => (
    <tr key={e.k}>
      <td><b>{e.label}</b></td><td>{e.source}</td>
      <td><span className={'chip ' + (EV_ST[e.state] || ['', ''])[1]}>{(EV_ST[e.state] || [e.state])[0]}</span></td>
      <td className="num">{e.state === 'missing' ? '—' : e.fresh}</td><td className="note">{e.note || ''}</td>
    </tr>
  ));
  return (
    <>
      <div className="asg2 r1c">
        <Panel t="Data and evidence quality"><Quality /></Panel>
        <Panel t="Where this comes from">
          <p className="note" style={{ marginTop: 0 }}>
            Every item is fetched from the system that owns it, with its source, freshness and confidence. The full request and processing trail is in the audit log.
          </p>
          <div className="row" style={{ marginTop: 10 }}>
            {routeAllowed('audit/log') && <button className="btn" onClick={() => nav('/audit/log')}>Open audit log</button>}
            <button className="btn" onClick={snapshot}>Evidence snapshot</button>
            {routeAllowed('integration/map') && <button className="btn" onClick={() => nav('/integration/map')}>Source map</button>}
          </div>
        </Panel>
      </div>
      <Panel t="All evidence items"><Tbl head={[['Evidence'], ['Source'], ['State'], ['Updated'], ['Note']]} rows={rows} /></Panel>
    </>
  );
}

function TabRelated() {
  const { c, compare } = useAsset();
  const nav = useNavigate();
  const pool = myCases().filter((x) => x.id !== c.id && x.cls === c.cls);
  const all = pool.slice().sort((a, b) => (b.owner === c.owner ? 1 : 0) - (a.owner === c.owner ? 1 : 0) || (a.id < b.id ? -1 : 1)).slice(0, 14);
  const rows = all.map((x) => {
    const hh = assetHealth(x), n = x.recommendation ? x.recommendation.net : null;
    return (
      <tr key={x.id}>
        <td>
          <div className="row" style={{ gap: 10, flexWrap: 'nowrap' }}>
            <Photo x={x} cls="xs" noZoom />
            <span><b>{asSerial(x)}</b><div className="note">{x.id} · {x.assetId}</div></span>
          </div>
        </td>
        <td>{x.owner}</td><td>{x.location}</td><td>{x.grade ? 'Grade ' + x.grade : '—'}</td>
        <td className="r num">{hh.score}</td><td className="r num">{n == null ? '—' : money(n)}</td><td><StageChip c={x} /></td>
        <td className="nowrap">
          <span className="tacts" style={{ display: 'inline-flex' }}>
            <button className="tbtn" onClick={() => nav('/product/asset/' + x.id)}>Open</button>
            <button className="tbtn" onClick={() => compare(x.id)}>Compare</button>
          </span>
        </td>
      </tr>
    );
  });
  return (
    <Panel t="Related assets and fleet context">
      <Tbl head={[['Asset'], ['Owner'], ['Site'], ['Grade'], ['Health', 'r'], ['Net', 'r'], ['Status'], ['']]} rows={rows} />
      <div className="note" style={{ marginTop: 6 }}>
        Showing the {all.length} closest of {pool.length} {classInfo(c.cls).plural.toLowerCase()}: same customer first, then by return number.
      </div>
    </Panel>
  );
}

// ---------- overlays ----------
/** Compare this asset with up to three similar ones (asCompare). */
function CompareModal({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { c } = useAsset();
  const rel = assetRelated(c).filter((x) => x.id !== id);
  const first = id ? caseById(id) : undefined;
  const cols = [c, ...[...(first ? [first] : []), ...rel].slice(0, 3)];
  const val = (x: Case, k: string): string => {
    const hh = assetHealth(x), ev = x.evidence || [];
    const q = Math.round(((ev.filter((e) => e.state === 'ready').length + 0.5 * ev.filter((e) => e.state === 'partial' || e.state === 'stale').length) / Math.max(1, ev.length)) * 100);
    return ({
      id: x.id + ' · ' + x.assetId, owner: x.owner, site: x.location, age: x.age + ' years', grade: x.grade ? 'Grade ' + x.grade : 'Not graded', health: hh.score + ' / 100',
      life: x.engLife, route: x.recommendation ? x.recommendation.plan || routeInfo(x.recommendation.id).short : 'None yet', net: x.recommendation ? money(x.recommendation.net) : '—', q: q + ' / 100',
    } as Record<string, string>)[k];
  };
  const rows = [['id', 'Return · asset'], ['owner', 'Owner'], ['site', 'Site'], ['age', 'Age'], ['grade', 'Condition'], ['health', 'Health score'], ['life', 'Engineering life'], ['route', 'Recommended route'], ['net', 'Predicted net'], ['q', 'Data confidence']];
  return (
    <Modal title="Compare similar assets" wide onClose={onClose} foot={<button className="btn ghost" onClick={onClose}>Close</button>}>
      <div className="tw">
        <table className="t static tight ascmp">
          <thead>
            <tr>
              <th />
              {cols.map((x, i) => (
                <th key={x.id}><Photo x={x} cls="xs" noZoom /><div>{asSerial(x)}{i === 0 && <> <span className="chip y">This asset</span></>}</div></th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r[0]}><td className="note">{r[1]}</td>{cols.map((x) => <td key={x.id}>{val(x, r[0])}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}

/** What was known when the decision was made (ACT.snapshot). */
function SnapshotDrawer({ c, onClose }: { c: Case; onClose: () => void }) {
  const ps = c.evidence.map((e) => provenance(c, e)), full = ps.filter((p) => p.status === 'available').length;
  const chip = (s: string) => s === 'available' ? <span className="chip ok">Full provenance</span> : s === 'partial' ? <span className="chip warn">Partial provenance</span> : <span className="chip bad">Provenance unavailable</span>;
  return (
    <Drawer wide title="Evidence snapshot" sub={`${c.id} · ${c.snapshot!.id}`} onClose={onClose}
      foot={<a className="btn" href="#/audit">Open audit log for {c.id}</a>}>
      <div className="callout info">
        Immutable record of what was known when the decision was made. Retraining or new evidence creates a new snapshot; it never overwrites this one.
      </div>
      <dl className="kv" style={{ margin: '14px 0' }}>
        <dt>Snapshot</dt><dd>{c.snapshot!.id}</dd>
        <dt>Taken</dt><dd>{snapshotTime(c)}</dd>
        <dt>Policy · models</dt><dd>POL-3.2 · {c.model} family</dd>
        <dt>Provenance</dt><dd><b>{full}</b> of {ps.length} items with full provenance{ps.length - full ? `; ${ps.length - full} partial or unavailable` : ''}</dd>
      </dl>
      {c.evidence.map((e, i) => (
        <details key={e.k} className="dd prov" open>
          <summary>
            <span className={'ev ' + e.state} style={{ display: 'inline-grid', verticalAlign: 'middle', border: 0, padding: 0, marginRight: 8 }}>
              <span className="ic">{e.state === 'ready' ? '✓' : '!'}</span>
            </span>
            <b>{e.label}</b> {chip(ps[i].status)}
          </summary>
          <div style={{ padding: '4px 0 14px' }}>
            <div className="note">{e.source}{e.state === 'missing' ? '' : ' · ' + e.fresh}{e.note ? ' · ' + e.note : ''}</div>
            <div className="row" style={{ marginTop: 8 }}><span className="note">{ps[i].id}</span></div>
          </div>
        </details>
      ))}
    </Drawer>
  );
}
