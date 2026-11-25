/**
 * A live case: the Decision Workbench stage pages (#/product/<ID>/stage/<n>), the case Overview and Full analysis.
 *
 * The API answers with two documents, and the pages draw everything from them:
 * - CaseScreen = GET /api/screens/case/{id}: the case record, the run, each stage's tag and summary, the landing
 *   stage, the next step, the active hand-off clock, the approval role and limit, the connected sources.
 * - CaseAnalysis = GET /api/screens/case/{id}/analysis: what the detail tabs and Full analysis are made of.
 * Both are read through the cache (client.ts).
 * Formatting, the what-if assumptions and the remembered tabs are frontend-only (backend/di/services/screens/case.py has the
 * mapping table).
 */
import type { PackStage } from './analytics';
import { ApiError, cached, invalidate, ref, withQuery } from './client';
import type { Reference } from './reference';
import { fmtDate, fmtDateYear, fmtNumber, money } from './format';
import { bump, onSessionChange } from './store';
import type { ActionResult } from './types';
import { sessionScoped, view } from './view';

// ---------- records ----------
export interface CostTerm { kind: string; label: string; amt: number }
/** A route's CO2e provenance (P9-1.12): the factor set, the label and each factor with its value, source and year. */
export interface Co2Prov { set: string; label: string; factors: { name: string; value: number; source: string; year: number }[]; transportKg: number | null }
export interface Route {
  id: string; plan: string; net: number; p10: number; p90: number; why?: string; target?: string; unc?: string;
  excluded?: boolean; failReason?: string; failGate?: number; terms: CostTerm[]; gates: string[]; gateNotes?: string[];
  co2?: number | null; co2Prov?: Co2Prov | null;
  demandStatus?: string; demandLabel?: string; variant?: string; vendor?: string; refurbDelta?: number | null; poolNet?: number;
  hold?: { forecast: number; holding: number; headline: number; sellNow: number; opp: string; review: string; days: number; fallback: number };
  components?: { n: string; dest: string; ref: string; v: number }[];
}
export interface Evidence { k: string; label: string; state: string; source: string; note?: string; fresh?: string }
export interface ExecStep { k?: string; label: string; sys: string; state: string; ack?: { by: string; ref: string; at: string } | null }
export interface Prediction { src: string; inputs: string; model: string; ver: string; result: string; range: string; conf: string }
export interface OutcomeLine { label: string; kind: string; pred: number; act: number; model: string | null; ver: string | null; src?: string | null }
/** One gate result on a case (backend/di/services/cases/gate_hold.py, plan 9 P9-1.2). */
export interface GateEvidenceOnFile { type: string; label: string; source: string; at: string; value?: Record<string, unknown> }
export interface GateRow {
  id: string; name: string; type: string; stage: string; stageLabel: string; passed: boolean;
  kind: 'block' | 'require_step' | 'require_approval' | 'close_block'; routes: string[]; routeNames: string[]; hold: boolean;
  step: string | null; owner: string; evidence: GateEvidenceOnFile[]; missing: string[]; reason: string; locked: boolean;
}
/** A case held until evidence arrives; `batch` names the lot batch it was opened in. */
export interface GateHold { gates: string[]; since: string; batch: string | null }
export interface RequiredStep { gate: string; step: string; owner: string }
export interface BatchStatus { ref: string; total: number; held: number; released: number }
export interface CaseRec {
  id: string; owner: string; location: string; assetId: string; product: string; mfr: string; cls: string; qty: number; age: number;
  received: string; stage: string; grade?: string; condition: string; assessment: string; engLife: string; nextInspection?: string;
  horizon?: string; timing?: string; model?: string; kind?: string; facts?: string[]; predictions?: Prediction[] | null;
  spec?: Record<string, string>; demand?: { site?: string; lease?: string; parts?: boolean; internal?: boolean; confirmed?: boolean } | null;
  routes: Route[]; recommendation: Route | null; chosen?: Route | null; override?: boolean | null; reevalReason?: string;
  submitted?: { by: string; at: string } | null;
  approval?: { ref: string; by: string; at: string; rationale: string; spend?: number | null; terms?: string } | null;
  packet?: { rationale: string; at: string; by: string; prep?: string | null } | null;
  outcome?: { net: number; by?: string; at?: string; order?: string | null; lines: OutcomeLine[] } | null;
  exec?: { ref: string; decisionId: string; approvedAt?: string; instruction?: number; steps: ExecStep[] } | null;
  blocked?: { action: string; owner: string; reason: string; gateName?: string } | null;
  requested?: { ref: string; at: string } | null;
  evidence: Evidence[];
  gates?: GateRow[]; gateHold?: GateHold | null; requiredSteps?: RequiredStep[]; batch?: BatchStatus | null;
  snapshot?: { id: string; items?: number } | null;
}

// ---------- stages ----------
export interface StageDef { n: number; k: string; t: string; trig: string; agent: string; person: string; sys: string[] }
export interface Phase { k: string; t: string; n: number[]; h: string }
export interface RunStage { n: number; t: string; label: string; state: string; result?: string; at?: string | null; by?: string; blocked?: { owner?: string; reason?: string } | null }
export interface Run { stage: number; stages: RunStage[]; done?: boolean }
export type TagKind = 'done' | 'todo' | 'block' | 'wait' | 'cur';
export interface StageTag { k: TagKind; icon: string; word: string; who?: string; since?: string | null; why?: string }
/** A fact of a stage, with the kind of provenance (ret, mod, rul, rec) and the system behind it. */
export interface Fact { l: string; v: string; k: string; sys: string }
export interface StageData { res: string; facts: Fact[]; docs: string[]; mean: string; when?: string | null; who: string }
export interface NextStep { kind: 'act' | 'ack' | 'approve' | 'wait' | 'blocked' | 'done'; n: number; label: string; action?: string; input?: Record<string, unknown>; role?: string }
export interface Clock { level?: number; lim?: string; to?: string | null; due?: string; due2?: string }
export interface Source { id: string; short?: string; name: string; vendor: string; mode: string; status: string; freshMin?: number | null }

/** A tool-fleet case's place in its org's queue plan (backend/di/services/cases/replan.py, P9-1.4): the named order it
 * holds, the orders it competes for, the ones another return got (`to` its case id, `gain` what it gains from the order)
 * and a short name for each order ("lease renewal"). */
export interface QueuePlan { holds: string | null; contested: string[]; lost: { order: string; to: string; gain: number }[]; kinds: Record<string, string> }

/** One entry of a case's custody list (backend/di/services/cases/record_match.py, P9-1.10): append-only, oldest first. */
export interface CustodyEntry { at: string; event: 'received' | 'matched' | 'moved' | 'released'; source: string | null; location: string | null; by: string }
/** Whether the pack's system of record holds the asset: the system's name, the record's key and how long ago it synced, or the
 * role the exception went to. */
export interface RecordMatchView {
  found: boolean; system: string; key: string | null; syncedAt: string | null; syncedMinutesAgo?: number; since: string | null; owner: string | null;
}

/** GET /api/screens/case/{id} */
export interface CaseScreen {
  case: CaseRec; model: string; serial: string; run: Run; tags: StageTag[]; stages: StageData[];
  landing: number | 'overview'; next: NextStep; clock: Clock | null;
  approval: { role: 'Approver' | 'Admin'; limit: number | null }; sources: Record<string, Source>;
  plan?: QueuePlan | null; recordMatch?: RecordMatchView | null; custody?: CustodyEntry[];
  packStages?: PackStage[] | null;
}

// ---------- the analysis ----------
export interface TraceLine { item: string; calc: string; inr: number; method: string; sys: string; rec: string; why: string }
export interface Trace { label: string; kind: string; usd: number; inr: number; lines: TraceLine[]; why: string; method: string; sys: string; rec: string; sign: number }
export interface Prov {
  id: string; key: string; label: string; status: string; state?: string; sourceName?: string; vendor?: string; record?: string | null;
  value?: string; fetchedAt?: string; reason?: string; usedIn: string[]; notes?: string[];
}
export interface RankRow { route: string; plan: string; gross: number; cost: number; net: number; days: number; prob: number; life: string; co2: number | null }
export interface PlanStep {
  n: number; k: string; label: string; sys: string; app: string; act: string; docs: string[]; planned: boolean; owner: string; lim: string;
  state: string; clock: Clock | null; why: string;
}
export interface Leg { n?: number; from: string; to: string; km: number; inr: number; mode: string; calc: string; etd: string; eta: string; transit?: number; carrier: string; readyAt?: string }
export interface Move { stops: string[]; legs: Leg[]; stage: { code?: string; why: string } | null; to: string | null; src: string; d0: string; need: string | null; eta: string | null; slack: number | null }
export interface WhatIf { k: string; t: string; d: string; on: boolean }
export interface Rul { estMonths: number; estLow: number; estHigh: number; certMonths: number; basis: string; certRef: string }
export interface Demand { order: string | null; site?: string; lease?: string; confirmed: boolean; horizonMonths: number; line: number | null; shipTo: string | null; needBy: string | null; avoidedPo: string | null; oms: string }
export interface Lease {
  lease: string; end: string; intent: string; usage: string; rma: string; auth: string; fee: number; repl: string | null; book: number; acq: string;
  pickup: string; eta: string; carrier: string; freight: number; lane: { from: string; to: string; km: number; inr: number; mode: string; calc: string };
}
export interface StepView { k: string | null; label: string; sys: string; state: string; ack: ExecStep['ack']; app: string; doc_ref: string | null; owner: string; doc: [string, string]; note: string }
export interface Health { score: number; comps: { n: string; h: number; st: string; cls: string }[]; band: Record<string, number>; est?: boolean }
export interface Loc { name: string; win: string; city?: string; bin?: string; bay?: string; days?: number[] }
export interface Risk { level: 'ok' | 'warn' | 'bad'; text: string; detail: string }
export interface RoutesRead {
  eligible: { rank: number; plan: string; route: string; net: number; behind: number }[];
  excluded: { plan: string; route: string; gate: string; reason: string }[];
  tie: { text: string } | null;
}
export interface SavedScenario { id: string; name: string; top: string; scen: Scen; w: Weights }
export interface CaseAnalysis {
  case_id: string; provenance: Prov[]; snapshot_time: string;
  routes: { id: string; plan: string; conf: string; terms: Trace[] | null }[];
  ranking: RankRow[]; flips: { txt: string; pct: number | null; to: string }[];
  rul: Rul | null; demand: Demand | null; plan: PlanStep[]; move: Move | null; what_if: WhatIf[];
  prep_parts: { mode: string; parts: unknown[]; labH: number } | null; lease: Lease; rationale: string; spend: Record<string, number>;
  instruction: Record<string, unknown> | null; journal: { id: string; by: string; prep?: string | null; at: string }[];
  evidence_pack: unknown;
  view: {
    steps: StepView[]; delivered: string; value_order: { ref: string; kind: string; sys: string; ack: boolean } | null;
    actuals: [string, string, number, string, string][][]; stage_label: string;
    routes_read: RoutesRead; evidence_read: { items: { label: string; state: string; system: string }[] }; risks: Risk[];
    health: Health; diag: { metric: string; value: string; source: string; at: string } | null;
    parts: { n: string; st: string; cls: string; q: number }[]; part_prices: { n: string; st: string; price: number; pn?: string; qty?: number; inr?: number }[];
    catalogue: number; sc: string; rma: string; receipt: string; title: string; serial: string; facts: [string, string][];
    repair_load: number; fac_code: string | null; locs: Record<string, Loc>; scenarios: SavedScenario[];
  };
}

// ---------- reading the two documents ----------
const casePath = (id: string) => '/api/screens/case/' + encodeURIComponent(id);

/** The case screen, or null when there is no such case or the account may not open it. */
export function caseScreen(id: string): CaseScreen | null {
  try {
    return cached<CaseScreen>(casePath(id));
  } catch (e) {
    if (e instanceof ApiError) return null;
    throw e; // a pending fetch (Suspense)
  }
}
/** Why a case cannot be opened: 'missing' (no such case) or 'refused' (tenant, warehouse or page access). */
export function caseRefusal(id: string): 'missing' | 'refused' | null {
  try {
    cached(casePath(id));
    return null;
  } catch (e) {
    if (e instanceof ApiError) return e.status === 404 ? 'missing' : 'refused';
    throw e;
  }
}
const screenOf = (c: CaseRec | string): CaseScreen => {
  const s = caseScreen(typeof c === 'string' ? c : c.id);
  if (!s) throw new Error('No case ' + (typeof c === 'string' ? c : c.id));
  return s;
};
/** The analysis behind the detail tabs and Full analysis (tenant filter: the repair centre's load). */
export function caseAnalysis(id: string): CaseAnalysis {
  return cached<CaseAnalysis>(withQuery(casePath(id) + '/analysis', { tenant: view().tenant }));
}

/** A static list of the demo (reference data). */
export const refList = <K extends keyof Reference>(name: K): Reference[K] => ref(name);

// ---------- the case and its stages ----------
export const caseById = (id: string): CaseRec | undefined => caseScreen(id)?.case;

export const stages = (): StageDef[] => refList('AF_STAGES');
export const phases = (): Phase[] => refList('ST_PH');
export const phaseOf = (n: number): Phase => phases().find((p) => p.n.includes(n))!;
export const stageTitle = (n: number): string => stages()[n - 1].t;
/** What a stage that has not started will do (JSTEPS_AF). */
export const stageWillHappen = (n: number): string => refList('JSTEPS_AF')[n - 1][3];
export const runOf = (c: CaseRec): Run => screenOf(c).run;
// the run argument is accepted for the callers' convenience; the tags come with the run
export const stageState = (c: CaseRec, n: number, _run?: Run): StageTag => screenOf(c).tags[n - 1];
export const stageSentence = (_c: CaseRec, n: number, t: StageTag): string =>
  'Stage ' + n + ', ' + stageTitle(n) + ': ' + (t.k === 'wait' ? 'waiting on ' + t.who + (t.since ? ' since ' + when(t.since) : '')
    : t.k === 'done' ? 'done' + (t.since ? ' ' + when(t.since) : '') : t.k === 'block' ? 'blocked: ' + (t.why || '') : t.k === 'cur' ? 'the case is here now' : 'not reached yet');
export const stageData = (c: CaseRec, n: number): StageData => screenOf(c).stages[n - 1];
/** Where a case opens for the signed-in role: a stage number or 'overview'. */
export const landing = (c: CaseRec): number | 'overview' => screenOf(c).landing;
export const nextStep = (c: CaseRec): NextStep => screenOf(c).next;
export const sources = (c: CaseRec): Record<string, Source> => screenOf(c).sources;
/** A tool-fleet case's queue plan; null for other templates. */
export const queuePlan = (c: CaseRec): QueuePlan | null => screenOf(c).plan ?? null;
/** Whether the pack's system of record holds the case's asset; null for a pack without one. */
export const recordMatch = (c: CaseRec): RecordMatchView | null => screenOf(c).recordMatch ?? null;
/** The case's custody list, oldest first (empty for the industrial pack). */
export const custody = (c: CaseRec): CustodyEntry[] => screenOf(c).custody ?? [];
/** The stage agents of the case's pack with their autonomy (P9-1.13); null for the industrial demo's cases. */
export const packStages = (c: CaseRec): PackStage[] | null => screenOf(c).packStages ?? null;
/** "07 Oct 14:20" (time only when it is not midnight UTC; the demo's stWhen). */
export function when(d: string | Date | null | undefined): string {
  if (!d) return '';
  const t = new Date(d), h = t.getUTCHours(), m = t.getUTCMinutes();
  return fmtDate(t) + (h || m ? ' ' + String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') : '');
}
/** Lower-case the first letter, as the demo's sentences do. */
export const lc = (t: string): string => (t ? t.charAt(0).toLowerCase() + t.slice(1) : t);
/** Route (without "#/") of a stage, the Overview or Full analysis. */
export function stageHref(id: string, n: number | 'overview' | 'full', tab?: string | null): string {
  return 'product/' + id + (n === 'overview' ? '/overview' : n === 'full' ? '/full' : '/stage/' + n + (tab ? '?tab=' + tab : ''));
}
/** Approvals go to the Approver when decisions are delegated, otherwise to Admin. */
export const approverRole = (c: CaseRec): 'Approver' | 'Admin' => screenOf(c).approval.role;
/** The active instruction step's time-limit clock (escalation), if any. */
export const activeClock = (c: CaseRec): Clock | null => screenOf(c).clock;
/** Approval limit of the signed-in account (Infinity when unlimited). */
export const approvalLimit = (c: CaseRec): number => screenOf(c).approval.limit ?? Infinity;
export const assetModel = (c: CaseRec): string => screenOf(c).model;
export const assetSerial = (c: CaseRec): string => screenOf(c).serial;

// ---------- remembered detail tab per case and stage (the demo's S.stTabs) ----------
const tabs = sessionScoped<Record<string, string>>(() => ({}));
export const rememberedTab = (id: string, n: number): string | undefined => tabs.current[id + '|' + n];
export function rememberTab(id: string, n: number, k: string): void {
  tabs.current[id + '|' + n] = k;
}

// ---------- approval card ----------
export const eligibleRoutes = (c: CaseRec): Route[] => c.routes.filter((x) => !x.excluded).sort((a, b) => b.net - a.net);
/** The preparation cost, as the spend the approval authorises (defaultSpend). */
export const defaultSpend = (_c: CaseRec, r: Route): number => Math.round(-r.terms.filter((t) => t.kind === 'prep' && t.amt < 0).reduce((a, t) => a + t.amt, 0));
/** The rationale the agent drafted (packet, or a fresh draft). */
export const draftRationale = (c: CaseRec): string => (c.packet ? c.packet.rationale : caseAnalysis(c.id).rationale);
/** The raw instruction that approval sends. */
export const instruction = (c: CaseRec): Record<string, unknown> | null => caseAnalysis(c.id).instruction;
/** Spend and sale terms the approval card proposes for a route (ACT.approve's terms()). */
export function approvalTerms(c: CaseRec, t: Route): string {
  return t.id === 'redeploy' ? `Transfer to ${t.target || 'receiving site'} by ${c.timing || 'Day 10'}; cancel planned purchase PO-${48000 + parseInt(c.id.slice(3))}`
    : t.id === 'resale' ? `Minimum acceptable price ${money(Math.max(0, t.p10))} · offer valid 14 days · fees as quoted`
    : t.id === 'hold' ? 'Review on 14 Nov 2026; re-evaluate if OPP-7712 is cancelled'
    : t.id === 'exit' ? 'Collection within 5 days; custody certificate required'
    : 'Reserve stock; release if the demand line is cancelled';
}
/** The evidence pack (JSON) for download. */
export const evidencePack = (id: string): unknown => caseAnalysis(id).evidence_pack;

// ---------- the enterprise systems ----------
/**
 * "Check for the next acknowledgement". The worker sends each instruction and the systems acknowledge on their own
 * (B13b): there is nothing to trigger, so the case is read again and the answer says where it stands.
 */
export async function checkAcknowledgement(c: CaseRec): Promise<ActionResult<{ label: string; by: string; ref_label: string }>> {
  const before = c.exec?.steps.filter((y) => y.state === 'done').length ?? 0;
  invalidate();
  const a = c.exec?.steps.find((y) => y.state === 'active');
  return { ok: false, error: { code: 'conflict', message: a ? `No new acknowledgement yet: ${lc(a.label)} is with ${a.sys.split(' · ')[0]}. Acknowledgements arrive here as the systems send them${before ? ` (${before} so far)` : ''}.` : 'Every instruction is acknowledged.' } };
}
// ---------- formatting (the demo's helpers, frontend-only) ----------
export const fmtD = fmtDate;
export const fmtDY = fmtDateYear;
export const fmtN = fmtNumber;
/** ₹1,23,456 */
export const inr = (n: number): string => (n < 0 ? '−' : '') + '₹' + Math.abs(Math.round(n)).toLocaleString('en-IN');
export const exNum = (n: number): string => Math.round(n).toLocaleString('en-IN');
const exHH = (h: number) => String(Math.floor(h)).padStart(2, '0') + ':' + String(Math.round((h % 1) * 60)).padStart(2, '0');
/** "07 Oct 14:20" */
export const exTs = (d: string | Date): string => { const t = new Date(d); return fmtDate(t) + ' ' + exHH(t.getUTCHours() + t.getUTCMinutes() / 60); };
/** "2026-10-07 09:14:30 UTC" */
export const isoT = (d: string | Date): string => new Date(d).toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC');
export const srcAge = (m: number): string => (m < 1 ? 'just now' : m < 60 ? Math.round(m) + ' min' : m < 2880 ? Math.round(m / 60) + ' h' : Math.round(m / 1440) + ' days');
/** $1.23M / $123k / $12 */
export const kfmt = (n: number): string => { const a = Math.abs(n), s = n < 0 ? '−' : ''; return a >= 1e6 ? s + '$' + (a / 1e6).toFixed(2) + 'M' : a >= 1e3 ? s + '$' + Math.round(a / 1e3) + 'k' : s + '$' + Math.round(a); };
/** "+30%" */
export const scenAdj = (v: number): string => { const p = Math.round((v - 1) * 100); return (p > 0 ? '+' : '') + p + '%'; };
/** The day of a move, counted from its Day 0 (exMove's day()). */
export const moveDay = (m: Move, d: string | Date): number => {
  const dd = (x: Date) => Date.UTC(x.getUTCFullYear(), x.getUTCMonth(), x.getUTCDate());
  return Math.round((dd(new Date(d)) - new Date(m.d0).getTime()) / 864e5);
};
export const locName = (a: CaseAnalysis, k: string | null | undefined): string => (k && a.view.locs[k]?.name) || k || '—';

// ---------- what-if assumptions and the Workbench's view state (the demo's S.scen and S.ti; frontend-only) ----------
export type ScenKey = 'purchase' | 'cost' | 'service' | 'market';
export interface Scen { purchase: number; cost: number; service: number; market: number; demandOff?: boolean; partUnavail?: boolean; newOnly?: boolean; certShort?: boolean }
export interface Weights { net: number; time: number; env: number; serv: number }
interface Ti { apply: string; w: Weights; sel: string[] | null; selFor: string | null; focus: string | null; diffOnly: boolean; xtab: 'why' | 'assume' | 'flip'; expand: Record<string, boolean>; caseId: string | null }
const BASE: Scen = { purchase: 1, cost: 1, service: 1, market: 1, demandOff: false, partUnavail: false, newOnly: false, certShort: false };
const TI0 = (): Ti => ({ apply: '', w: { net: 50, time: 20, env: 15, serv: 15 }, sel: null, selFor: null, focus: null, diffOnly: false, xtab: 'why', expand: {}, caseId: null });
let S: Scen = { ...BASE };
const ti: Ti = TI0();
// the next user starts from the base assumptions and default weights, even on the case the last one had open
onSessionChange(() => {
  S = { ...BASE };
  Object.assign(ti, TI0());
});
export const scen = (): Scen => S;
export function setScen(patch: Partial<Scen>): void {
  S = { ...S, ...patch };
  bump();
}
export function resetScen(): void {
  S = { ...BASE };
  ti.apply = '';
  bump();
}
export const tiView = (): Readonly<Ti> => ti;
export function setTi(patch: Partial<Ti>): void {
  Object.assign(ti, patch);
  bump();
}
/** A new case starts at the base assumptions (the demo resets S.scen when the case in view changes). */
export function enterCase(id: string): void {
  if (ti.caseId === id) return;
  Object.assign(ti, { caseId: id, apply: '', diffOnly: false, xtab: 'why', sel: null, selFor: null, focus: null });
  S = { ...BASE };
}
export const scenActive = (): boolean => S.purchase !== 1 || S.cost !== 1 || S.service !== 1 || S.market !== 1 || !!S.demandOff || !!S.partUnavail || !!S.newOnly;

const KIND_MULT: Record<string, ScenKey> = { purchase: 'purchase', prep: 'cost', fees: 'cost', service: 'service', sale: 'market', parts: 'market', material: 'market', lease: 'market' };
const SCEN_WHY = {
  ecm: 'Critical component failed and no replacement is available in supplier contracts, so EAM and QMS cannot re-certify its remaining life',
  newonly: 'The demand line requires a new unit; a refurbished unit cannot be supplied',
  demand: 'Confirmed demand cancelled in this scenario',
};
export interface ScenRow { r: Route; ex: boolean; why: string | null; sn: number; rank?: number }
export interface ScenRoutes { all: ScenRow[]; el: ScenRow[] }
/** Every route under the assumptions in view, and the eligible ones ranked (scenRoutes). */
export function scenRoutes(c: CaseRec): ScenRoutes {
  const net = (r: Route) => Math.round(r.terms.reduce((a, t) => a + t.amt * (S[KIND_MULT[t.kind]] || 1), 0));
  const all = c.routes.map((r) => {
    const dem = !!S.demandOff && r.demandStatus === 'confirmed' && (r.id === 'redeploy' || r.id === 'intparts') && c.id !== 'RT-1052';
    const ecm = !!S.partUnavail && ['redeploy', 'relase', 'resale'].includes(r.id);
    const nw = !!S.newOnly && r.id === 'redeploy' && r.demandStatus === 'confirmed';
    return {
      r, ex: !!r.excluded || dem || ecm || nw,
      why: r.excluded ? null : ecm ? SCEN_WHY.ecm : nw ? SCEN_WHY.newonly : dem ? SCEN_WHY.demand : null,
      sn: scenActive() && (!ti.apply || ti.apply === r.plan) ? net(r) : r.net,
    } as ScenRow;
  });
  const el = all.filter((x) => !x.ex).sort((a, b) => b.sn - a.sn);
  el.forEach((x, i) => (x.rank = i + 1));
  return { all, el };
}
const TI_SERV: Record<string, number> = { redeploy: 1, relase: 0.85, resale: 0.4, intparts: 0.2, extparts: 0.15, material: 0.05, exit: 0 };
export interface TiRow extends RankRow { r: Route; x: ScenRow; fit: number }
/** The predicted outcome of each eligible route under the assumptions, with the Fit score of the weights (tiRows). */
export function tiRows(c: CaseRec, a: CaseAnalysis, sr: ScenRoutes): TiRow[] {
  const base = (r: Route) => a.ranking.find((z) => z.route === r.id && z.plan === r.plan) ?? baseRow(c, r);
  const rows: TiRow[] = sr.el.map((x) => ({ ...base(x.r), net: x.sn, r: x.r, x, fit: 0 }));
  if (!rows.length) return rows;
  const mn = (v: number[]) => Math.min(...v), mx = (v: number[]) => Math.max(...v);
  const nets = rows.map((z) => z.net), ds = rows.map((z) => z.days), cs = rows.map((z) => z.co2 ?? 0), W = ti.w, ws = W.net + W.time + W.env + W.serv || 1;
  rows.forEach((z) => {
    const nn = (z.net - mn(nets)) / (mx(nets) - mn(nets) || 1), tt = 1 - (z.days - mn(ds)) / (mx(ds) - mn(ds) || 1), ee = ((z.co2 ?? 0) - mn(cs)) / (mx(cs) - mn(cs) || 1), ss = (z.prob / 100) * (TI_SERV[z.r.id] || 0);
    z.fit = Math.round((100 * (W.net * nn + W.time * tt + W.env * ee + W.serv * ss)) / ws);
  });
  return rows;
}
/** A route the base ranking does not hold (eligible only in a scenario): gross and cost from its terms. */
function baseRow(_c: CaseRec, r: Route): RankRow {
  const sum = (f: (t: CostTerm) => boolean) => r.terms.filter(f).reduce((s, t) => s + t.amt, 0);
  return { route: r.id, plan: r.plan, gross: sum((t) => t.amt > 0), cost: sum((t) => t.amt < 0), net: r.net, days: 0, prob: 0, life: '—', co2: 0 };
}
export interface TieValue { k: string; label: string; a: string; b: string; w: 'a' | 'b' | null }
export interface Tie { near: boolean; gap: number; pct?: number; a: TiRow; b: TiRow; decidedBy?: string | null; preferred?: TiRow; values?: TieValue[] }
export const TB_RULES: [string, string, string][] = [['risk', 'Risk / confidence', 'gap ≥ 5 points'], ['demand', 'Demand certainty', 'confirmed beats forecast'], ['cycle', 'Cycle time', 'gap ≥ 3 days'], ['rul', 'Remaining useful life', 'gap ≥ 6 months'], ['co2', 'Carbon', 'gap ≥ 10%']];
/** When the top two are within 5% or $250, the first secondary factor with a meaningful gap decides (tieBreak). */
export function tieBreak(a0: CaseAnalysis, rows: TiRow[]): Tie | null {
  if (!rows || rows.length < 2) return null;
  const a = rows[0], b = rows[1], gap = a.net - b.net, lim = Math.max(250, Math.abs(a.net) * 0.05);
  if (gap > lim) return { near: false, gap, a, b };
  const R = a0.rul, life = (z: TiRow) => (R && ['redeploy', 'resale', 'relase'].includes(z.r.id) ? R.estMonths : 0), dem = (z: TiRow) => (z.r.demandStatus === 'confirmed' ? 1 : 0);
  type F = [string, number, number, (x: number, y: number) => 'a' | 'b' | null, (v: number) => string];
  const Fs: F[] = [
    ['risk', a.prob, b.prob, (x, y) => (Math.abs(x - y) >= 5 ? (x > y ? 'a' : 'b') : null), (v) => v + '%'],
    ['demand', dem(a), dem(b), (x, y) => (x !== y ? (x > y ? 'a' : 'b') : null), (v) => (v ? 'confirmed' : 'forecast')],
    ['cycle', a.days, b.days, (x, y) => (Math.abs(x - y) >= 3 ? (x < y ? 'a' : 'b') : null), (v) => v + ' days'],
    ['rul', life(a), life(b), (x, y) => (Math.abs(x - y) >= 6 ? (x > y ? 'a' : 'b') : null), (v) => (v ? v + ' months' : 'none')],
  ];
  const values: TieValue[] = Fs.map((f) => ({ k: f[0], label: TB_RULES.find((t) => t[0] === f[0])![1], a: f[4](f[1]), b: f[4](f[2]), w: f[3](f[1], f[2]) }));
  // Carbon last (P9-1.12): a route with no CO2e figure has no carbon decision, shown as a dash.
  const co2Win = a.co2 == null || b.co2 == null ? null : Math.abs(a.co2 - b.co2) >= 0.1 * Math.max(a.co2, b.co2, 1) ? (a.co2 > b.co2 ? 'a' : 'b') : null;
  values.push({ k: 'co2', label: TB_RULES.find((t) => t[0] === 'co2')![1], a: a.co2 == null ? '—' : fmtNumber(a.co2) + ' kg', b: b.co2 == null ? '—' : fmtNumber(b.co2) + ' kg', w: co2Win });
  const d = values.find((v) => v.w);
  return { near: true, gap, pct: Math.round((gap / Math.max(1, Math.abs(a.net))) * 100), a, b, decidedBy: d ? d.k : null, preferred: d && d.w === 'b' ? b : a, values };
}
export function tieText(t: Tie | null): string {
  if (!t || !t.near) return '';
  const p = t.preferred!, v = t.values!.find((x) => x.k === t.decidedBy), me = p === t.a ? 'a' : 'b', ot = me === 'a' ? 'b' : 'a';
  return `${t.a.r.plan} and ${t.b.r.plan} are within ${money(t.gap)} (${t.pct}%). ` + (v ? `${p.r.plan} is preferred because ${v.label.toLowerCase()} decides: ${v[me]} against ${v[ot]}.` : 'No secondary factor separates them, so net value decides.');
}
/** A redeployment or re-lease whose demand outlasts the certified period needs recertification (recert). */
export function recert(a: CaseAnalysis, r: Route | null | undefined): { need: number; cert: number } | null {
  if (!r || !['redeploy', 'relase'].includes(r.id)) return null;
  const R = a.rul, D = a.demand;
  if (!R || !D) return null;
  const need = S.certShort ? Math.max(D.horizonMonths, R.certMonths + 12) : D.horizonMonths;
  return need > R.certMonths ? { need, cert: R.certMonths } : null;
}
/** The assumptions changed from base, in words (tiChanged). */
export function scenChanged(): string[] {
  const o: string[] = [];
  ([['purchase', 'Avoided purchase price'], ['cost', 'Preparation, parts and fees'], ['service', 'Service exposure'], ['market', 'Resale price']] as [ScenKey, string][]).forEach(([k, l]) => {
    if (S[k] !== 1) o.push(l + ' ' + scenAdj(S[k]));
  });
  if (S.demandOff) o.push('Confirmed demand cancelled');
  if (S.partUnavail) o.push('Critical part unavailable');
  if (S.newOnly) o.push('Customer requires a new unit');
  if (S.certShort) o.push('Certification shorter than demand');
  if (ti.apply) o.push('Applied to ' + ti.apply + ' only');
  return o;
}
/** Confidence of a route (tiConf). */
export const confidence = (a: CaseAnalysis, r: Route): string => a.routes.find((x) => x.id === r.id && x.plan === r.plan)?.conf ?? 'Medium';
/** The evidence snapshot, one item per evidence (cxEvidence). */
export interface SnapshotItem { k: string; label: string; ready: boolean; available: boolean; value: string; system: string; record: string; fetchedAt: string }
export function snapshotItems(c: CaseRec, a: CaseAnalysis): SnapshotItem[] {
  return c.evidence.map((e, i) => {
    const p = a.provenance[i], ok = p?.status === 'available';
    return { k: e.k, label: e.label, ready: e.state === 'ready', available: ok, value: ok ? String(p.value) : '—', system: String(p?.vendor || p?.sourceName || e.source), record: String(p?.record || '—'), fetchedAt: ok && p.fetchedAt ? new Date(p.fetchedAt).toISOString().slice(11, 16) + ' UTC' : '' };
  });
}
