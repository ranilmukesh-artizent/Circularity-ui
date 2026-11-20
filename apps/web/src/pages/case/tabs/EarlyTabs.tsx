/** The detail tabs of stages 1 to 5 (stData's tabs: afLeaseHTML, stKv, stSysTab, stEvTable, asCostInputs, asCond, asKnownDiag, asKnownCert). */
import type { CSSProperties, ReactNode } from 'react';
import { exNum, fmtD, fmtDY, inr, refList, stages, type CaseAnalysis, type CaseRec } from '../../../api/case';
import { money } from '../../../api/format';
import { VendorLogo } from '../../../ui/kit/VendorLogo';
import { AfBadge, CasePanel, Kv, ProvB, SourceStatus, ST_SYS, locOf, photoSrc, Photo } from '../CaseBlocks';
import type { TabProps } from './index';

// ---------- shared ----------
export function hashId(s: string): string {
  let h = 2166136261;
  for (const ch of s) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); }
  return (h >>> 0).toString(16).toUpperCase().padStart(8, '0');
}
/** The demo's asHex: a hash of the case id, for the illustrative figures. */
export const asHex = (c: CaseRec, k: string): number => parseInt(hashId(c.id + k), 16) || 0;
const asOf = () => new Date(refList<string>('AS_OF'));
const addDays = (d: string | Date, n: number) => new Date(new Date(d).getTime() + n * 864e5);
/** Days since a date, at the as-of time (afDays). */
export const afDays = (d: string | Date): number => Math.max(0, Math.round((asOf().getTime() - new Date(d).getTime()) / 864e5));
const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// ---------- stage 1 ----------
/** Lease end, return and transit (afLeaseHTML). */
export function LeaseTab({ c, a }: TabProps) {
  const L = a.lease;
  const kv = (rows: [string, string][]) => <dl className="afkv">{rows.map(([t, d]) => <div key={t}><dt>{t}</dt><dd>{d}</dd></div>)}</dl>;
  return (
    <section className="panel aflease" id="afLease">
      <div className="ph"><h3>Lease end, return and transit</h3><span className="sp"></span><AfBadge k="Retrieved" /></div>
      <div className="pb afl3">
        <div><h5>1 · Lease ends</h5>{kv([['Lease', L.lease], ['Ended', fmtDY(L.end)], ['Customer intent', L.intent], ['Usage', L.usage]])}<p className="note">Lease management · CRM</p></div>
        <div><h5>2 · Return authorised</h5>{kv([['Authorisation', L.rma + ' · ' + fmtD(L.auth)], ['Fees', L.fee ? money(L.fee) : 'None'], ['Replacement order', L.repl || 'None'], ['Book value', money(L.book) + ' · acquired ' + fmtDY(L.acq)]])}<p className="note">Lease management · ERP finance</p></div>
        <div><h5>3 · Pickup and transit</h5>{kv([['Picked up', fmtD(L.pickup) + ' · ' + L.carrier], ['Arrived', fmtD(L.eta)], ['Freight', money(L.freight)], ['Received', c.location + ' · ' + fmtD(c.received)]])}<p className="note">TMS / 3PL · WMS</p></div>
      </div>
    </section>
  );
}
export function CustomerTab({ c, a, s }: TabProps) {
  const L = a.lease;
  return <Kv rows={[['Customer', c.owner], ['Customer site', locOf(a, L.lane.from)], ['Intent', L.intent], ['Usage', L.usage], ['Asset', c.assetId + ' · ' + s.serial], ['Product', s.model + ' · ' + c.mfr]]} />;
}
/** The systems a stage names, with their connection status (stSysTab). */
export function SystemsTab({ s }: TabProps) {
  return (
    <ul className="stsys stpad">
      {stages()[0].sys.map((n) => {
        const src = s.sources[ST_SYS[n]];
        return (
          <li key={n}>
            {src && <VendorLogo vendor={src.vendor} />}
            <span><b>{n}</b><span className="note">{src ? src.vendor + ' · ' + src.mode : 'Circularity'}</span></span>
            {src && <SourceStatus k={src.status === 'live' ? 'live' : src.status === 'stale' ? 'stale' : src.status === 'manual' ? 'manual' : 'unavailable'} />}
          </li>
        );
      })}
    </ul>
  );
}

// ---------- stage 2 ----------
export function AuthTab({ a }: TabProps) {
  const L = a.lease;
  return <Kv rows={[['Return authorisation', L.rma], ['Authorised on', fmtDY(L.auth)], ['Early-return fee', L.fee ? money(L.fee) : 'None'], ['Replacement order', L.repl || 'None']]} />;
}
export function FinanceTab({ c, a }: TabProps) {
  const L = a.lease;
  return <Kv rows={[['Book value', money(L.book)], ['Acquired', fmtDY(L.acq)], ['Age', c.age + ' years'], ['Quantity', String(c.qty)]]} />;
}

// ---------- stage 3 ----------
export function LaneTab({ a }: TabProps) {
  const l = a.lease.lane;
  return <Kv rows={[['From', l.from + ' · ' + locOf(a, l.from)], ['To', l.to + ' · ' + locOf(a, l.to)], ['Distance', exNum(l.km) + ' km'], ['Mode', l.mode], ['Carrier', a.lease.carrier]]} />;
}
export function LaneCostTab({ a }: TabProps) {
  const L = a.lease, RC = refList<{ id: string; carrier: string }>('RATE_CARD');
  return <Kv rows={[['Calculation', L.lane.calc], ['Freight in rupees', inr(L.lane.inr)], ['Freight in dollars', money(L.freight) + ' at ₹' + refList<number>('EX_FX')], ['Rate card', RC.id + ' · ' + RC.carrier]]} />;
}

// ---------- stage 4 ----------
const EV_ST: Record<string, [string, string]> = { ready: ['Complete', 'ok'], partial: ['Partial', 'warn'], stale: ['Stale', 'warn'], missing: ['Missing', 'bad'], conflict: ['Conflict', 'bad'] };
/** The evidence checklist (stEvTable). */
export function EvidenceListTab({ c }: TabProps) {
  return (
    <div id="aszKnown">
      <CasePanel t="Evidence readiness" badge={<ProvB k="rul" sys="Evidence scoring" />}>
        <div className="tw">
          <table className="t static tight">
            <thead><tr><th>Evidence</th><th>Source</th><th>State</th><th>Updated</th></tr></thead>
            <tbody>
              {(c.evidence || []).map((e) => (
                <tr key={e.k}>
                  <td><b>{e.label}</b>{e.note && <div className="note">{e.note}</div>}</td>
                  <td>{e.source}</td>
                  <td><span className={'chip ' + (EV_ST[e.state] || ['', 'line'])[1]}>{(EV_ST[e.state] || [e.state])[0]}</span></td>
                  <td className="num">{e.state === 'missing' ? '—' : e.fresh || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CasePanel>
    </div>
  );
}
export function LocationTab({ c, a }: TabProps) {
  const code = a.view.fac_code, Lc = (code && a.view.locs[code]) || null;
  return <Kv rows={[['Facility', c.location], ['Code', code || '—'], ['City', Lc?.city || '—'], ['Bin', Lc?.bin || '—'], ['Receiving days', (Lc?.days || []).map((d) => DOW[d]).join(', ') || '—']]} />;
}
export function HoldingTab({ c, a }: TabProps) {
  const r = c.chosen || c.recommendation, hold = r?.terms.find((t) => /Holding/i.test(t.label));
  return (
    <>
      <Kv rows={[['Days since receipt', String(afDays(c.received))], ['Holding and risk cost in the recommended route', hold ? money(hold.amt) : 'Not priced yet'], ['Cost inputs', 'See below']]} />
      <CasePanel t="Cost inputs" cls="asCostCard" badge={<ProvB k="ret" sys="OMS, PLM, EAM, procurement" />}><CostInputs c={c} a={a} /></CasePanel>
    </>
  );
}
/** The figures the preparation cost is predicted from (asCostInputs). */
function CostInputs({ c, a }: { c: CaseRec; a: CaseAnalysis }) {
  const v = a.view, pp = v.part_prices;
  const row = (l: string, src: string, val: ReactNode) => <div className="asrow"><span><b>{l}</b><div className="note">{src}</div></span><span className="right">{val}</span></div>;
  return (
    <>
      {row('Catalogue value', 'PLM / ERP product catalogue', <b className="num">{money(v.catalogue)}</b>)}
      {row('Return authorisation', 'IBM Sterling OMS (forward and reverse orders)', <><b className="mono">{v.rma}</b><div className="note">received under {v.receipt} (WMS)</div></>)}
      {row('Repair scope', 'EAM diagnostics', c.grade ? (pp.length ? pp.map((p) => p.n + ' (' + p.st.toLowerCase() + ')').join(', ') : 'No part needs replacing') : 'Waiting for EAM diagnostics')}
      {row('Contracted part prices', 'SAP Ariba · supplier contract ' + v.sc + ' · held in ₹', pp.length ? pp.map((p, i) => (
        <div key={i} className="num">{p.n}{p.inr ? <> <span className="note">{p.qty} × {inr(p.inr / (p.qty || 1))}</span></> : null} <b>{money(p.price)}</b></div>
      )) : '—')}
      <p className="note" style={{ margin: '6px 0 0' }}>Circularity reads these figures. The preparation cost is predicted from them on the Predictions page (step 2).</p>
    </>
  );
}

// ---------- stage 5 ----------
const ws = (c: CaseRec) => (c.cls === 'motor' || c.cls === 'pump' ? 'MRO' : 'Inspection');
/** Inspection findings (asCond). */
export function FindingsTab({ c }: TabProps) {
  const insEv = (c.evidence || []).find((e) => e.k === 'insp') || { state: 'missing' }, g = c.grade, spec = c.spec || {};
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
  const insD = c.assessment === 'Pending' ? 'Not yet inspected' : fmtDY(addDays(c.received, 1 + (asHex(c, 'ins') % 3)));
  const row = (l: string, v: string, t: string) => <div className="asrow"><span>{l}</span><b className={t === 'line' ? '' : 'tx-' + t}>{v}</b></div>;
  return (
    <CasePanel t="Inspection findings" badge={<ProvB k="ret" sys="Inspection" />}>
      <div className="ascond">
        <div className="ascl">
          <div className="asclose"><Photo c={c} cls="zoom" /></div>
          <div className="ascs">
            <div className="note">Latest inspection</div>
            <b className="num">{insD}</b>
            <div className="note">Site: {c.location}</div>
            <span className={'chip ' + tone} style={{ marginTop: 6 }}>{lbl}</span>
          </div>
        </div>
        <div className="asrows">{row('Functional test', test[0], test[1])}{row('Wear level', wear, wearT)}{row('Cosmetic damage', cos[0], cos[1])}{row(key[0], key[1], 'ok')}</div>
      </div>
    </CasePanel>
  );
}
/** Diagnostic condition (asKnownDiag). */
export function DiagTab({ c, a }: TabProps) {
  const D = a.view.diag, d = refList<Record<string, [string, string]>>('DIAG')[c.cls] || ['', 'pct'];
  return (
    <CasePanel t="Diagnostic condition" badge={<ProvB k="ret" sys={ws(c)} />}>
      {D ? (
        <div className="asfig">
          <span className="note">{D.metric}</span><b className="big">{D.value}</b>
          {c.grade && <span>Inspection grade <b>{c.grade}</b></span>}
          <span className="note">{D.source} · {D.at}</span>
          {d[1] !== 'grade' && <span className="note">Value modelled from grade, age and class</span>}
        </div>
      ) : <div className="asfig"><b>Not inspected yet</b><span className="note">Waiting for the inspection report</span></div>}
    </CasePanel>
  );
}
/** Certified period (asKnownCert). */
export function CertTab({ c, a }: TabProps) {
  const R = a.rul;
  return (
    <CasePanel t="Certified period" badge={<ProvB k="ret" sys="QMS" />}>
      {R ? (
        <div className="asfig">
          <span className="note">Certified operating period</span><b className="big num">{R.certMonths} months</b>
          <span className="note">{R.basis}</span><span className="note mono">{R.certRef}</span>
          <span className="note">Circularity reads this certificate; it does not certify equipment.</span>
        </div>
      ) : <div className="asfig"><b>No certified period</b><span className="note">{c.engLife || 'Not assessed'}</span></div>}
    </CasePanel>
  );
}
export function PhotosTab({ c }: TabProps) {
  return (
    <CasePanel t="Photos">
      <div className="asgal">
        {['36% 60%', '70% 40%', '20% 30%', '55% 85%'].map((p, i) => (
          <div key={i} className="asimg zoomg" style={{ '--op': p } as CSSProperties}><img src={photoSrc(c.cls)} alt={`${c.product} view ${i + 1}`} loading="lazy" /></div>
        ))}
      </div>
      <p className="note" style={{ margin: '6px 0 0' }}>Close-up crops of the product photo. Inspection photos attach here when they arrive from the inspection system.</p>
    </CasePanel>
  );
}
