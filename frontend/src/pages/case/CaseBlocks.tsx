/**
 * Small building blocks of the case pages, ported from the demo's markup helpers (asPanel, provB, stProv, afBadge,
 * stTag, stKv, stp, frSt, stPva, rangeBar, exMethod, exClockChip, stLogos, asPhoto, stageChip, asTbl). Same classes
 * and text, so the demo's CSS applies. The shared ones (frIt, frPanel, frTl, vlogo, jsonHtml) are in src/components/kit.
 */
import { useState, type CSSProperties, type ReactNode } from 'react';
import {
  exTs, refList, refreshEvidence, srcAge, stages, type CaseAnalysis, type CaseRec, type Clock, type Source, type StageTag,
} from '../../api/case';
import { money } from '../../api/format';
import { IconTile } from '../../components/kit/IconTile';
import { KeyedStatus, type StatusTable } from '../../components/kit/StatusPill';
import { VendorLogo } from '../../components/kit/VendorLogo';
import { useAction } from '../../hooks/useAction';
import { caseActions } from './caseActions';

export const hue = (h: string, k?: number) => ({ '--c': `var(--h-${h})`, ...(k != null ? { '--k': k } : {}) }) as CSSProperties;

/** A panel of the case pages (asPanel): a title with an optional badge, no subtitle. */
export function CasePanel({ t, badge, cls, id, children }: { t: ReactNode; badge?: ReactNode; cls?: string; id?: string; children: ReactNode }) {
  return (
    <section className={'panel aspn ' + (cls || '')} id={id}>
      <div className="ph"><h3>{t}</h3>{badge}</div>
      <div className="pb">{children}</div>
    </section>
  );
}

const PROV: Record<string, string> = { ret: 'Retrieved', mod: 'Model', rul: 'Rules' };
/** Where a figure comes from: retrieved, model or rules (provB). */
export function ProvB({ k, sys }: { k: string; sys: string }) {
  const tip = ({
    ret: 'Retrieved from ' + sys + '. Circularity reads it and does not change it.',
    mod: 'Predicted by ' + sys + '. A model output, not a recorded fact.',
    rul: 'Computed by ' + sys + ' from fixed rules, not a model.',
  } as Record<string, string>)[k];
  return <span className={'aszb ' + k} data-prov={k} data-tip={tip}>{PROV[k]} · {sys}</span>;
}
/** The systems each stage names, mapped onto the connected sources (ST_SYS). */
export const ST_SYS: Record<string, string> = {
  'Lease management': 'lease', CRM: 'crm', 'Customer portal': 'crm', 'ERP finance': 'erp', ERP: 'erp', Finance: 'erp', 'ERP procurement': 'proc',
  'TMS / 3PL': 'tms', WMS: 'wms', 'Repair orders': 'repair', Repair: 'repair', MRO: 'repair', OMS: 'oms', TMS: 'tms', Inspection: 'insp', PLM: 'plm', EAM: 'eam', Remarketing: 'dlr',
};
/** A fact's provenance: retrieved from a connected source (with its freshness), rules, a model, or recorded (stProv). */
export function StProv({ k, sys, src, estimate }: { k: string; sys: string; src: Record<string, Source>; estimate?: boolean }) {
  if (k === 'rec') return <span className="aszb rec" data-prov="rec" data-tip="Recorded in Circularity when it happened: who acted and when.">Recorded · Circularity</span>;
  const s = src[ST_SYS[sys] || sys];
  return (
    <>
      <ProvB k={k} sys={s ? s.vendor + (k === 'ret' && s.freshMin != null ? ' · ' + srcAge(s.freshMin) + (s.freshMin < 1 ? '' : ' ago') : '') : sys} />
      {estimate && <EstimateBadge />}
    </>
  );
}
/** A fact that is an estimate, not a read (a car's grade without a completed inspection, P9-9.7). */
export const EstimateBadge = () => (
  <span className="aszb mod" data-prov="estimate" data-tip="An estimate, not a recorded read: the inspection is missing or not done yet. The decision is held until a person confirms it.">estimate</span>
);
/** The evidence types a gate that is stale or has no check on file can have re-run at the source (`evidence.refresh`, P9-9.9). */
export const REFRESHABLE = ['recall_check'];
/** The evidence type of a failed gate's stale evidence that can be re-checked, or null. */
export const staleType = (g: { passed: boolean; missingTypes?: string[] }): string | null =>
  g.passed ? null : ((g.missingTypes ?? []).find((t) => REFRESHABLE.includes(t)) ?? null);
/** "Re-check" beside a stale evidence fact: runs the check again at its source; the page shows the new result. */
export function RecheckButton({ caseId, type }: { caseId: string; type: string }) {
  const act = useAction();
  return (
    <button type="button" className="btn sm" data-recheck={type} disabled={act.pending} onClick={() => { void act.run(() => refreshEvidence(caseId, type)); }}>
      {act.pending ? 'Re-checking…' : 'Re-check'}
    </button>
  );
}
/** What a route must disclose to a buyer, from the gates (a title brand, P9-9.8): one line per route, nothing when none. */
export function Disclosures({ r }: { r: { disclosures?: string[] } }) {
  if (!r.disclosures?.length) return null;
  return <p className="note" data-disclosures="route"><b>Disclose:</b> {r.disclosures.join('; ')}</p>;
}
/** Retrieved / Model / Rules / Draft / Prepared by agent (afBadge). */
export function AfBadge({ k }: { k: string }) {
  const tip = refList('AF_BADGE_TIP')[k] || k;
  return <span className={'afb afb-' + k.toLowerCase().replace(/[^a-z]+/g, '')} data-tip={tip}>{k}</span>;
}
/** A stage's state in words and shape (stTag). */
export function Tag({ t, big }: { t: Pick<StageTag, 'k' | 'icon' | 'word'>; big?: boolean }) {
  return <span className={`sttag st-${t.k}${big ? ' big' : ''}`}><i aria-hidden="true">{t.icon}</i>{t.word}</span>;
}
/** Label and value rows (stKv). */
export function Kv({ rows, pad = true }: { rows: [string, ReactNode][]; pad?: boolean }) {
  return <dl className={'stkv' + (pad ? ' stpad' : '')}>{rows.map(([l, v]) => <div key={l}><dt>{l}</dt><dd>{v}</dd></div>)}</dl>;
}
/** A document reference with a copy button (stDoc). */
export const Doc = ({ r }: { r: string }) => (
  <span className="stdoc">
    <span className="mono">{r}</span>
    <button className="lnk stcp" aria-label={'Copy ' + r} onClick={() => caseActions.copy(r)}>Copy</button>
  </span>
);
/** The journey step a block belongs to (stp; `short` is stpn). */
export function Stp({ n, short }: { n: number; short?: boolean }) {
  const m = jmap(n), j = refList('JSTEPS')[m - 1];
  if (!j) return null;
  return (
    <span className={'stp ' + (j[2] === 'built' ? '' : j[2])} title={'Journey step ' + m + ': ' + j[1] + (short ? '' : ' — ' + j[3])}>
      <b>{m}</b>{short ? null : j[1]}
    </span>
  );
}
/** The demo's jmap: the journey's old step numbers onto the ten stages. */
const jmap = (n: number): number => [0, 5, 6, 6, 6, 7, 8, 8, 8, 9, 10][n] || n;
const SRC_ST: StatusTable = { live: ['Live', 'ok'], stale: ['Stale', 'warn'], manual: ['Manual import', 'line'], unavailable: ['Not connected', 'bad'] };
/** A source's connection state with a dot (frSt). */
export const SourceStatus = ({ k, t }: { k: string; t?: string }) => <KeyedStatus k={k} t={t} table={SRC_ST} />;
/** Predicted against actual: two columns and the variance (stPva). */
export function Pva({ pred, act }: { pred: number; act: number }) {
  const mx = Math.max(Math.abs(pred), Math.abs(act)) || 1, d = act - pred, w = (v: number) => Math.round((Math.abs(v) / mx) * 100);
  const dv = (d < 0 ? '−' : '+') + money(Math.abs(d));
  return (
    <div className="stpva" role="img" aria-label={`Predicted ${money(pred)}, actual ${money(act)}, variance ${dv}`}>
      <div><span className="note">Predicted</span><b className="num">{money(pred)}</b><i style={{ width: w(pred) + '%' }}></i></div>
      <div><span className="note">Actual</span><b className="num">{money(act)}</b><i className="a" style={{ width: w(act) + '%' }}></i></div>
      <div className={'stpvd ' + (d < 0 ? 'neg' : 'pos')}><span className="note">Variance</span><b className="num">{dv}</b></div>
    </div>
  );
}
/** P10, P50 and P90 on a bar (rangeBar). */
export function RangeBar({ p10, p50, p90, lo, hi }: { p10: number; p50: number; p90: number; lo: number; hi: number }) {
  const sc = (v: number) => Math.max(0, Math.min(100, ((v - lo) / (hi - lo || 1)) * 100));
  return (
    <div className="range" data-tip={`P10 ${money(p10)} · P50 ${money(p50)} · P90 ${money(p90)}`}>
      <div className="tr"></div>
      <div className="bd" style={{ left: sc(p10) + '%', width: Math.max(2, sc(p90) - sc(p10)) + '%' }}></div>
      <div className="md" style={{ left: sc(p50) + '%' }}></div>
    </div>
  );
}
const EX_MC_TIP: Record<string, [string, string]> = {
  Retrieved: ['exm-r', 'Read as-is from the source system'], Contracted: ['exm-c', 'A contracted price or rate held in the source system'],
  Modelled: ['exm-m', 'Predicted by a model, or solved from the other lines'],
};
/** How a cost line is known (exMethod). */
export const ExMethod = ({ m }: { m: string }) => <span className={'exm ' + (EX_MC_TIP[m] || [''])[0]} data-tip={(EX_MC_TIP[m] || ['', m])[1]}>{m}</span>;
/** A hand-off step's clock: due, or escalated (exClockChip). */
export function ExClockChip({ k }: { k: Clock | null | undefined }) {
  if (!k) return null;
  if (k.level) return <div><span className="chip bad">Escalated to {k.to}</span><div className="note">limit passed {exTs((k.level === 2 ? k.due2 : k.due)!)}</div></div>;
  return k.due ? <div className="note">due {exTs(k.due)}</div> : null;
}
/** The system logos a stage names (stLogos). */
export function StageLogos({ n, src }: { n: number; src: Record<string, Source> }) {
  const seen = new Set<string>();
  return (
    <>
      {stages()[n - 1].sys.map((s) => {
        const so = src[ST_SYS[s]];
        if (!so) {
          if (s === 'Circularity') return <span key={s} className="stsy"><IconTile ic="spark" h="agent" cls="xs" /><span>Circularity</span></span>;
          return <span key={s} className="stsy"><span>{s}</span></span>;
        }
        if (seen.has(so.id)) return null;
        seen.add(so.id);
        return <span key={s} className="stsy" data-tip={s + ' · ' + so.vendor}><VendorLogo vendor={so.vendor} /><span>{s}</span></span>;
      })}
    </>
  );
}
const AS_IMG: Record<string, string> = { motor: 'motor', pump: 'pump', control: 'control', drill: 'powertool', batch: 'powertool', it: 'it' };
export const photoSrc = (cls: string) => 'assets/products/' + AS_IMG[cls] + '.webp';
/** The product photo, with the class name as a fallback (asPhoto). */
export function Photo({ c, cls }: { c: CaseRec; cls?: string }) {
  const [broken, setBroken] = useState(false);
  const label = refList('CLASSES')[c.cls]?.label ?? c.cls;
  return (
    <div className={'asimg ' + (cls || '')}>
      {!broken && <img src={photoSrc(c.cls)} alt={`${c.product}, ${c.mfr}`} onError={() => setBroken(true)} />}
      <span className="asph" hidden={!broken}><span>{label}</span></span>
      {c.qty > 1 && <span className="asqty">×{c.qty}</span>}
    </div>
  );
}
/** The case's stage as a chip (stageChip). */
export function StageChip({ c }: { c: CaseRec }) {
  switch (c.stage) {
    case 'awaiting_approval': return <span className="chip y">Awaiting approval</span>;
    case 'approved': return <span className="chip dk">Approved · handing off</span>;
    case 'executing': return <span className="chip ok" data-tip="Instruction sent; the enterprise system carries out the work and reports the outcome">Handed off</span>;
    case 'reeval': return <span className="chip warn">Re-evaluate</span>;
    case 'none': return c.blocked ? <span className="chip bad">Needs evidence</span> : <span className="chip line">—</span>;
    case 'closed': return <span className="chip ok">Closed</span>;
    default: return null;
  }
}
/** A table (asTbl). */
export function Tbl({ head, rows, cls, id }: { head: [string, string?][]; rows: ReactNode[]; cls?: string; id?: string }) {
  return (
    <div className="tw">
      <table className={'t static tight ' + (cls || '')} id={id}>
        <thead><tr>{head.map(([h, c], i) => <th key={i} className={c || ''}>{h}</th>)}</tr></thead>
        <tbody>{rows.length ? rows : <tr><td colSpan={head.length}><div className="empty"><b>Nothing to show</b></div></td></tr>}</tbody>
      </table>
    </div>
  );
}
/** Loc name, or the code when unknown. */
export const locOf = (a: CaseAnalysis, k: string | null | undefined) => (k && a.view.locs[k]?.name) || k || '—';
