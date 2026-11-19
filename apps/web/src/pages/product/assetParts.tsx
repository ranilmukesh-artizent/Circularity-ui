/** Building blocks of Asset & Product Intelligence (asPanel, provB, asPhoto, asRing, asCond, asProduct, asEcon …). */
import { createContext, useContext, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { fmtDateYear } from '../../api/format';
import {
  addDays, asHex, asModel, asMoney, asRMA, asReceipt, asRev, asSC, asSerial, asTitle, assetEcon, assetEligibility, assetEvents, assetRelated,
  badgeTip, caseStageKey, catalogueValue, classInfo, exFx, gateNames, inr, learnVersion, localCurrency, myCases, partPrices, partsAvailability,
  prepCost, prepParts, rateCardId, routeInfo, type Case, type Health,
} from '../../api/product';
import { Icon } from '../../ui/Icon';
import { Thumb } from './chips';

// ---------- context: the asset in view and the page's view state ----------
export interface AsCtx {
  c: Case; h: Health; local: boolean;
  setLocal: (v: boolean) => void; openTab: (t: string) => void; compare: (id?: string) => void; snapshot: () => void; zoom: (src: string, alt: string) => void;
}
export const AssetCtx = createContext<AsCtx | null>(null);
export const useAsset = () => useContext(AssetCtx)!;
/** asMoney with the page's currency choice. */
export const useMoney = () => {
  const { local } = useAsset();
  return (v: number) => asMoney(v, local);
};

const AS_IMG: Record<string, string> = { motor: 'motor', pump: 'pump', control: 'control', drill: 'powertool', batch: 'powertool', it: 'it' };
export const photoSrc = (cls: string) => 'assets/products/' + AS_IMG[cls] + '.webp';

export function Panel({ t, tab, cls, badge, id, children }: { t: ReactNode; tab?: string; cls?: string; badge?: ReactNode; id?: string; children: ReactNode }) {
  const { openTab } = useAsset();
  return (
    <section className={'panel aspn ' + (cls || '')} id={id}>
      <div className="ph">
        <h3>{t}</h3>
        {badge}
        {tab && <button className="lnk" onClick={() => openTab(tab)}>View details</button>}
      </div>
      <div className="pb">{children}</div>
    </section>
  );
}

const PROV = { ret: 'Retrieved', mod: 'Model', rul: 'Rules' };
/** Where a card's figures come from: retrieved, model or rules (provB). */
export function Prov({ k, sys }: { k: 'ret' | 'mod' | 'rul'; sys: string }) {
  const tip = {
    ret: 'Retrieved from ' + sys + '. Circularity reads it and does not change it.',
    mod: 'Predicted by ' + sys + '. A model output, not a recorded fact.',
    rul: 'Computed by ' + sys + ' from fixed rules, not a model.',
  }[k];
  return <span className={'aszb ' + k} data-prov={k} data-tip={tip}>{PROV[k]} · {sys}</span>;
}

export const AfBadge = ({ k }: { k: string }) => (
  <span className={'afb afb-' + k.toLowerCase().replace(/[^a-z]+/g, '')} data-tip={badgeTip(k)}>{k}</span>
);

/** The product photo, with the class icon as a fallback; click to enlarge (the CXO lightbox). */
export function Photo({ x, cls, noZoom }: { x: Case; cls?: string; noZoom?: boolean }) {
  const { zoom } = useAsset();
  const [broken, setBroken] = useState(false);
  const alt = `${x.product}, ${x.mfr}`;
  return (
    <div className={'asimg ' + (cls || '')}>
      {!broken && (
        <img src={photoSrc(x.cls)} alt={alt} loading="lazy" onError={() => setBroken(true)}
          onClick={noZoom ? undefined : () => zoom(photoSrc(x.cls), alt)} />
      )}
      <span className="asph" hidden={!broken}>
        <Thumb cls={x.cls} />
        <span>{classInfo(x.cls).label}</span>
      </span>
      {x.qty > 1 && <span className="asqty">×{x.qty}</span>}
    </div>
  );
}

/** Ring of segments with a centre figure (asRing, asQuality). */
function Donut({ size, r, w, segs, score, label }: { size: number; r: number; w: number; segs: [string, number][]; score: number; label: string }) {
  const c0 = size / 2, cc = 2 * Math.PI * r;
  let off = 0;
  return (
    <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label}>
      <circle cx={c0} cy={c0} r={r} fill="none" stroke="var(--panel3)" strokeWidth={w} />
      {segs.map(([col, frac], i) => {
        const l = frac * cc, d = Math.max(0, l - 2);
        const el = <circle key={i} cx={c0} cy={c0} r={r} fill="none" stroke={col} strokeWidth={w} strokeDasharray={`${d} ${cc - d}`} strokeDashoffset={-off} transform={`rotate(-90 ${c0} ${c0})`} />;
        off += l;
        return el;
      })}
      {size === 120 ? (
        <>
          <text x="60" y="60" textAnchor="middle" fontSize="26" fontWeight="800" fill="var(--ink)" style={{ fontFamily: 'var(--f-display)' }}>{score}</text>
          <text x="60" y="76" textAnchor="middle" fontSize="10.5" fill="var(--ink2)">/100</text>
        </>
      ) : (
        <>
          <text x="55" y="54" textAnchor="middle" fontSize="22" fontWeight="800" fill="var(--ink)" style={{ fontFamily: 'var(--f-display)' }}>{score}</text>
          <text x="55" y="69" textAnchor="middle" fontSize="10" fill="var(--ink2)">/100</text>
        </>
      )}
    </svg>
  );
}

export function HealthRing({ h }: { h: Health }) {
  const cols: Record<string, string> = { Excellent: 'var(--ok)', Good: '#5FAE7B', Fair: '#D4A800', Poor: 'var(--bad)' };
  const tot = Object.values(h.band).reduce((a, b) => a + b, 0) || 1;
  const segs = Object.keys(cols).filter((k) => h.band[k]).map((k) => [cols[k], h.band[k] / tot] as [string, number]);
  return (
    <div className="asring">
      <Donut size={120} r={48} w={14} segs={segs} score={h.score} label={`Overall asset health ${h.score} out of 100`} />
      <div className="asleg">
        {Object.keys(cols).map((k) => (
          <div key={k}><i style={{ background: cols[k] }} /><span>{k}</span><b className="num">{Math.round(((h.band[k] || 0) / tot) * 100)}%</b></div>
        ))}
      </div>
    </div>
  );
}

export function Row({ l, v, cls }: { l: ReactNode; v: ReactNode; cls?: string }) {
  return <div className={'asrow' + (cls ? ' ' + cls : '')}><span>{l}</span>{v}</div>;
}

export function Timeline({ full, ret }: { full?: boolean; ret?: boolean }) {
  const { c } = useAsset();
  const ev = assetEvents(c).filter((e) => !ret || e.k !== 'dec');
  let cur = ev.findIndex((e) => e.s !== 'done');
  if (cur < 0) cur = ev.length - 1;
  return (
    <ol className={'astl ' + (full ? 'full' : '')}>
      {ev.map((e, i) => (
        <li key={e.k} className={`${e.s} ${i === cur ? 'cur' : ''}`} data-tip={e.t + ' · ' + e.note}>
          <span className="dot">{e.s === 'done' ? '✓' : e.s === 'warn' ? '●' : ''}</span>
          <b>{e.t}</b>
          <span className="d num">{e.d}</span>
          {e.sub && <span className="note">{e.sub}</span>}
          <span className="note">{e.src}</span>
          {full && <span className="nt">{e.note}</span>}
        </li>
      ))}
    </ol>
  );
}

/** Inspection findings (asCond). */
export function Condition() {
  const { c } = useAsset();
  const insEv = (c.evidence || []).find((e) => e.k === 'insp') || { state: 'missing' };
  const g = c.grade, spec = c.spec || {};
  const lbl = g ? ({ A: 'Excellent condition', B: 'Good condition', C: 'Fair condition', D: 'Poor condition' } as Record<string, string>)[g] : c.assessment === 'Pending' ? 'Not inspected' : 'Assessment incomplete';
  const tone = g ? ({ A: 'ok', B: 'ok', C: 'warn', D: 'bad' } as Record<string, string>)[g] : 'line';
  const test = insEv.state === 'ready' ? ['Pass', 'ok'] : insEv.state === 'partial' ? ['Not run', 'warn'] : ['Not available', 'line'];
  const wear = g ? ({ A: 'Minimal', B: 'Light', C: 'Moderate', D: 'Heavy' } as Record<string, string>)[g] : '—';
  const wearT = g ? ({ A: 'ok', B: 'ok', C: 'warn', D: 'bad' } as Record<string, string>)[g] : 'line';
  const cos = g ? (g === 'A' ? ['None', 'ok'] : g === 'B' ? ['Minor scratches', 'ok'] : g === 'C' ? ['Dents and scuffs', 'warn'] : ['Visible damage', 'bad']) : ['—', 'line'];
  const key = ({
    motor: ['Insulation resistance', g ? 'Within limits' : 'Not tested'], pump: ['Pressure test', g ? 'Holds rated pressure' : 'Not tested'],
    control: ['Self-diagnostic', g ? 'No faults logged' : 'Not run'], drill: ['Battery cycles', String(spec['Battery cycles'] || '—')],
    batch: ['Calibration', spec['Calibration'] || '—'], it: ['Battery health', spec['Battery health'] || '—'],
  } as Record<string, string[]>)[c.cls] || ['Key test', '—'];
  const insD = c.assessment === 'Pending' ? 'Not yet inspected' : fmtDateYear(addDays(c.received, 1 + (asHex(c, 'ins') % 3)));
  const row = (l: string, v: string, t: string) => <div className="asrow"><span>{l}</span><b className={t === 'line' ? '' : 'tx-' + t}>{v}</b></div>;
  return (
    <div className="ascond">
      <div className="ascl">
        <div className="asclose"><Photo x={c} cls="zoom" /></div>
        <div className="ascs">
          <div className="note">Latest inspection</div>
          <b className="num">{insD}</b>
          <div className="note">Site: {c.location}</div>
          <span className={'chip ' + tone} style={{ marginTop: 6 }}>{lbl}</span>
        </div>
      </div>
      <div className="asrows">
        {row('Functional test', test[0], test[1])}{row('Wear level', wear, wearT)}{row('Cosmetic damage', cos[0], cos[1])}{row(key[0], key[1], 'ok')}
      </div>
    </div>
  );
}

/** Product specs, component health and parts availability (asProduct). */
export function ProductSpecs({ ret }: { ret?: boolean }) {
  const { c, h, openTab } = useAsset();
  const K = classInfo(c.cls), spec = Object.entries(c.spec || {}), parts = partsAvailability(c, h);
  return (
    <div className="aspi">
      <div className="aspa">
        <div className="row" style={{ flexWrap: 'nowrap', gap: 12, marginBottom: 10 }}>
          <Photo x={c} cls="sm" />
          <div><b>{asTitle(c)}</b><div className="note">{K.label}</div></div>
        </div>
        <dl className="asdl">
          <div><dt>Product family</dt><dd>{K.plural}</dd></div>
          <div><dt>Product line</dt><dd>{asModel(c)}</dd></div>
          <div><dt>Revision</dt><dd>{asRev(c)} (current)</dd></div>
          <div><dt>Category</dt><dd>{K.label}</dd></div>
        </dl>
        <h4>Technical specifications</h4>
        <div className="asspec">
          {spec.length ? spec.map(([k, v]) => <div key={k}><span>{k}</span><b>{v}</b></div>) : <div className="note">No specification recorded.</div>}
        </div>
      </div>
      {!ret && (
        <div className="aspb">
          <h4>Component health <span className="note">(modelled)</span></h4>
          {h.comps.map((x) => <div key={x.n} className="asrow"><span>{x.n}</span><span className={'chip ' + x.cls}>{x.st}</span></div>)}
          <button className="lnk" onClick={() => openTab('product')}>View BOM and parts</button>
        </div>
      )}
      <div className="aspc">
        <h4>Parts availability</h4>
        {parts.map((x) => (
          <div key={x.n} className="asrow">
            <span>{x.n}</span>
            <span className={'tx-' + x.cls}><b>{x.st}</b>{x.q ? <> <span className="note num">{x.q}</span></> : null}</span>
          </div>
        ))}
        <button className="lnk" onClick={() => openTab('product')}>View alternative parts</button>
      </div>
    </div>
  );
}

/** Economic intelligence tiles, service costs, resale demand and price (asEcon). */
export function Econ() {
  const { c, local, setLocal } = useAsset();
  const m = useMoney();
  const e = assetEcon(c), K = classInfo(c.cls), r = e.r;
  const tile = (ic: string, cls: string, l: string, v: string, s: string) => (
    <div className={'asec ' + cls}>
      <span className="kic"><Icon name={ic} /></span>
      <div><span className="note">{l}</span><b className="num">{v}</b><span className="note">{s}</span></div>
    </div>
  );
  return (
    <div className="asecon">
      <div className="seg" role="group" aria-label="Currency" style={{ marginBottom: 12 }}>
        <button aria-pressed={!local} onClick={() => setLocal(false)}>USD</button>
        <button aria-pressed={local} onClick={() => setLocal(true)}>Local currency ({localCurrency()[0]})</button>
      </div>
      <div className="asecs">
        {tile('analytics', 'ok', 'Estimated recovery value', (r ? '' : '~') + m(e.pos), r ? 'Gross of costs' : 'Estimate, evidence needed')}
        {tile('flag', 'bad', 'Expected treatment cost', r ? m(e.neg) : '—', r ? 'Prep, transfer, risk' : 'No route yet')}
        {tile('trend', 'y', 'Predicted net recovery', (r ? '' : '~') + m(e.net), e.rg != null ? '± ' + e.rg + '% (P10–P90)' : 'Not yet predicted')}
      </div>
      <div className="asec3">
        <div>
          <h4>Historical costs (last {Math.round(e.age)} years)</h4>
          {([['Maintenance', e.mt], ['Parts replaced', e.pr], ['Total service cost', e.sv], ['Average cost per year', e.avg]] as [string, number][]).map((x) => (
            <div key={x[0]} className="asrow"><span>{x[0]}</span><b className="num">{m(x[1])}</b></div>
          ))}
          <div className="note" style={{ marginTop: 4 }}>Estimated from the service history.</div>
        </div>
        <div>
          <h4>Market demand (resale)</h4>
          <span className={'chip ' + e.demand[1]}>{e.demand[0]}</span>
          <div className="asbars" role="img" aria-label={`Resale sales per month for ${K.plural}`}>
            {e.bars.map((v, i) => (
              <span key={i} data-tip={`${e.months[i]} · ${v} resale sales`}>
                <i style={{ height: Math.max(6, (v / e.mx) * 100) + '%' }} />
                <em>{e.months[i]}</em>
              </span>
            ))}
          </div>
        </div>
        <div>
          <h4>Comparable resale value</h4>
          <div className="note">Avg. market price</div>
          <b className="num" style={{ font: '800 20px var(--f-display)' }}>{e.price ? m(e.price) : '—'}</b>
          <div className="note" style={{ marginTop: 8 }}>Price trend</div>
          <b className={e.trend >= 0 ? 'tx-ok' : 'tx-bad'}>{e.trend >= 0 ? '▲' : '▼'} {Math.abs(e.trend).toFixed(0)}%</b> <span className="note">last 3 months</span>
        </div>
      </div>
    </div>
  );
}

/** "How do you get the cost?": catalogue, RMA, repair scope and contracted part prices (asCostInputs). */
export function CostInputs() {
  const { c, h } = useAsset();
  const m = useMoney();
  const pp = partPrices(c, h);
  const row = (l: string, src: string, v: ReactNode) => (
    <div className="asrow"><span><b>{l}</b><div className="note">{src}</div></span><span className="right">{v}</span></div>
  );
  return (
    <>
      {row('Catalogue value', 'PLM / ERP product catalogue', <b className="num">{m(catalogueValue(c))}</b>)}
      {row('Return authorisation', 'IBM Sterling OMS (forward and reverse orders)', <><b className="mono">{asRMA(c)}</b><div className="note">received under {asReceipt(c)} (WMS)</div></>)}
      {row('Repair scope', 'EAM diagnostics', c.grade ? (pp.length ? pp.map((p) => p.n + ' (' + p.st.toLowerCase() + ')').join(', ') : 'No part needs replacing') : 'Waiting for EAM diagnostics')}
      {row('Contracted part prices', 'SAP Ariba · supplier contract ' + asSC(c) + ' · held in ₹', pp.length ? pp.map((p, i) => (
        <div key={i} className="num">{p.n}{p.inr ? <> <span className="note">{p.qty} × {inr(p.inr / (p.qty || 1))}</span></> : null} <b>{m(p.price)}</b></div>
      )) : '—')}
      <p className="note" style={{ margin: '6px 0 0' }}>Circularity reads these figures. The preparation cost is predicted from them on the Predictions page (step 2).</p>
    </>
  );
}

/** How the preparation cost is built (asCostBuild). */
export function CostBuild() {
  const { c, h } = useAsset();
  const m = useMoney();
  const r = c.chosen || c.recommendation, prep = prepCost(c);
  if (!r || !prep) return null;
  const P = prepParts(c, r);
  const head = (
    <h4 style={{ fontSize: 12.5, margin: '14px 0 4px', color: 'var(--ink2)' }}>How the preparation cost is built <span className="note">({r.plan})</span></h4>
  );
  if (!P) {
    const parts = partPrices(c, h).reduce((s, p) => s + p.price, 0), lab = prep - parts;
    return (
      <>
        {head}
        <div className="ascb" id="asCostBuild">
          <div className="asrow"><span>Contracted parts <span className="note">supplier contract {asSC(c)}, retrieved</span></span><b className="num">{m(parts)}</b></div>
          <div className="asrow"><span>Labour, machine and transfer <span className="note">prep-cost-time {learnVersion(c, 'prep-cost-time')}, predicted</span></span><b className="num">{m(lab)}</b></div>
          <div className="asrow"><span><b>Preparation cost</b></span><b className="num">{m(prep)}</b></div>
        </div>
      </>
    );
  }
  const fx = exFx(), u = (v: number) => m(v / fx);
  const row = (l: string, n: string, v: number, cl?: string) => (
    <div className={'asrow' + (cl ? ' ' + cl : '')}><span>{l} <span className="note">{n}</span></span><b className="num">{u(v)}</b></div>
  );
  const mc = P.ops.reduce((s, o) => s + o.inr, 0), tr = P.legs.reduce((s, l) => s + l.inr, 0), rest = P.B - P.P;
  return (
    <>
      {head}
      <div className="ascb" id="asCostBuild">
        {row('Contracted parts', P.parts.length + ' part' + (P.parts.length === 1 ? '' : 's') + ' · SAP Ariba ' + asSC(c) + ' · ' + inr(P.P), P.P)}
        {row('Labour, machine and transfer', inr(rest), rest)}
        {row('Labour', P.labH + ' h × ' + inr(P.rate) + ' · Oracle Depot Repair, standard ' + P.std + ' h, solved last', P.lab, 'ascbs')}
        {P.ops.length > 0 && row('Machine time', P.ops.map((o) => o.name.toLowerCase() + ' ' + o.h + ' h').join(', '), mc, 'ascbs')}
        {P.legs.length > 0 && row('Transport', P.legs.length + ' leg' + (P.legs.length > 1 ? 's' : '') + ' · ShipLane TMS ' + rateCardId(), tr, 'ascbs')}
        {!!P.pack && row('Packing and handling', 'Manhattan Active WM', P.pack, 'ascbs')}
        <div className="asrow"><span><b>Preparation cost</b> <span className="note">{inr(P.B)} at ₹{fx}</span></span><b className="num">{m(prep)}</b></div>
      </div>
    </>
  );
}

/** Ownership, contract, warranty, safety, environment and the six gates (asElig). */
export function Eligibility() {
  const { c } = useAsset();
  const { rows, route: r } = assetEligibility(c);
  const g = r ? r.gates : null, gl = gateNames();
  const word = { pass: 'passed', fail: 'failed', skip: 'not reached', warn: 'passed with a warning' };
  return (
    <div className="aselig">
      {rows.map((x) => (
        <div key={x[0]} className="asrow"><span><b>{x[0]}</b><div className="note">{x[1]}</div></span><span className={'chip ' + x[3]}>{x[2]}</span></div>
      ))}
      <div className="asgates">
        <span className="note">Six eligibility gates{r ? ' for ' + (r.plan || routeInfo(r.id).short) : ''}</span>
        <div className="asgl">
          {g ? g.map((x, i) => <span key={i} className={'asgate ' + x} data-tip={gl[i] + ': ' + word[x]} />) : <span className="note">Not evaluated yet</span>}
        </div>
        {g && <b className="num">{g.filter((x) => x === 'pass').length} of 6 passed</b>}
      </div>
    </div>
  );
}

/** Data confidence ring and key sources (asQuality). */
export function Quality() {
  const { c } = useAsset();
  const ev = c.evidence || [], n = ev.length || 1, cnt: Record<string, number> = { ready: 0, partial: 0, missing: 0, conflict: 0 };
  ev.forEach((e) => { const k = e.state === 'stale' ? 'partial' : e.state; cnt[k] = (cnt[k] || 0) + 1; });
  const score = Math.round(((cnt.ready + 0.5 * cnt.partial) / n) * 100), lab = score >= 85 ? 'Good' : score >= 65 ? 'Fair' : 'Low';
  const tone = score >= 85 ? 'ok' : score >= 65 ? 'warn' : 'bad', pc = (k: string) => Math.round(((cnt[k] || 0) / n) * 100);
  const cols: Record<string, string> = { ready: 'var(--ok)', partial: '#D4A800', missing: 'var(--chart7)', conflict: 'var(--bad)' };
  const segs = Object.keys(cols).filter((k) => cnt[k]).map((k) => [cols[k], cnt[k] / n] as [string, number]);
  const dot: Record<string, string> = { ready: 'ok', partial: 'warn', stale: 'warn', missing: 'bad', conflict: 'bad' };
  return (
    <div className="asq">
      <div className="asqr">
        <Donut size={110} r={44} w={12} segs={segs} score={score} label={`Data confidence ${score} out of 100`} />
        <div>
          <div className="note">Data confidence</div>
          <b className={'tx-' + tone}>{lab}</b>
          <div className="asleg" style={{ marginTop: 6 }}>
            {[['ready', 'Complete'], ['partial', 'Partial'], ['missing', 'Missing'], ['conflict', 'Inconsistent']].map((x) => (
              <div key={x[0]}><i style={{ background: cols[x[0]] }} /><span>{x[1]}</span><b className="num">{pc(x[0])}%</b></div>
            ))}
          </div>
        </div>
      </div>
      <h4>Key data sources</h4>
      <div className="assrc">
        {ev.slice(0, 6).map((e) => (
          <div key={e.k} className="asrow" data-tip={e.label + (e.note ? ' · ' + e.note : '')}>
            <span className="row" style={{ gap: 7, flexWrap: 'nowrap' }}><i className={'dotc ' + (dot[e.state] || '')} />{e.source}</span>
            <span className="note">{e.state === 'missing' ? 'No data' : 'Updated ' + e.fresh}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const STAGE_LABEL: Record<string, string> = {
  approval: 'Awaiting approval', exec: 'Under treatment', await_insp: 'Awaiting inspection', need: 'Needs information', approved: 'Approved', reeval: 'Re-evaluate', noroute: 'No route',
};
/** Up to three related assets as cards (asRelated). */
export function Related() {
  const { c, openTab } = useAsset();
  const rel = assetRelated(c);
  const all = myCases().filter((x) => x.id !== c.id && x.cls === c.cls).length;
  return (
    <>
      <div className="asrels">
        {rel.map((x) => (
          <Link key={x.id} className="asrel" to={'/product/asset/' + x.id}>
            <Photo x={x} cls="xs" noZoom />
            <span className="asrt">
              <b>{asSerial(x)}</b>
              <span className="note">{asModel(x)} · {x.assetId}</span>
              <span className="note">{x.owner === c.owner ? 'Same customer' : 'Other customer'} · {x.location} · {STAGE_LABEL[caseStageKey(x)]}</span>
            </span>
            <span className={'chip ' + (x.owner === c.owner ? 'y' : 'line')}>{x.owner === c.owner ? 'Similar' : 'Related'}</span>
          </Link>
        ))}
        {!rel.length && <div className="empty"><b>No related assets</b></div>}
      </div>
      <button className="lnk" style={{ marginTop: 8 }} onClick={() => openTab('related')}>View all ({all})</button>
    </>
  );
}

/** A small static table (asTbl). */
export function Tbl({ head, rows, cls }: { head: [string, string?][]; rows: ReactNode[]; cls?: string }) {
  return (
    <div className="tw">
      <table className={'t static tight ' + (cls || '')}>
        <thead><tr>{head.map((h, i) => <th key={i} className={h[1] || ''}>{h[0]}</th>)}</tr></thead>
        <tbody>
          {rows.length ? rows : <tr><td colSpan={head.length}><div className="empty"><b>Nothing to show</b></div></td></tr>}
        </tbody>
      </table>
    </div>
  );
}
