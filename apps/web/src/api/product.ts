/**
 * Product area (Decision Workbench lists and Asset & Product Intelligence): typed reads.
 * Engine mode: the demo's own helpers (visCases, assetHealth, asEvents, caseRul …), so numbers match index.html.
 * With VITE_BACKEND=api: GET /api/screens/product/returned, /expected, /journey/{id}, /asset/{id} and /pools, the
 * reference lists, the session and the view settings (apps/api/di/screens/product.py has the mapping).
 *
 * In api mode a case from the lists (visibleCases, myCases, caseById, assetRelated, skuUnits) is the list row: the
 * fields the queue, the drawer, the journey and compare read, with its recommendation in brief. The asset page reads
 * the full record with assetCase(id); the per-case figures (assetHealth, caseRul …) come from that asset's answer.
 */
import { engine } from '../engine/engine';
import { API } from './backend';
import { cached, ref, session, withQuery } from './client';
import { money } from './format';
import { canRoute, currentAccount, rolePolicy } from './session';
import { setView, view } from './view';

/* eslint-disable @typescript-eslint/no-explicit-any */
const g = <T = any>(name: string): T => engine()<T>(name);
/** An engine helper by name, typed by where it is assigned. */
const fn = <F extends (...a: any[]) => any>(name: string): F => ((...a: Parameters<F>) => g<F>(name)(...a)) as F;

// ---------- shapes (only the fields the pages read) ----------
export type GateResult = 'pass' | 'fail' | 'skip' | 'warn';
export type EvState = 'ready' | 'missing' | 'partial' | 'stale' | 'conflict';
export interface Term { label: string; amt: number; kind: string }
export interface CaseRoute {
  id: string; plan: string; net: number; p10: number; p90: number; terms: Term[]; gates: GateResult[]; gateNotes?: string[];
  excluded?: boolean; failReason?: string; failGate?: number; demandLabel?: string; demandStatus?: string;
}
export interface Evidence { k: string; label: string; state: EvState; source: string; fresh: string; note?: string }
export interface Blocked { gateName: string; reason: string; owner: string; action: string }
export interface Case {
  id: string; assetId: string; product: string; cls: string; owner: string; received: Date | string; location: string;
  condition: string; assessment: string; stage: string; qty: number; grade?: string | null; age: number; mfr: string;
  engLife: string; nextInspection: string; spec: Record<string, string>; model?: string; hero?: boolean;
  recommendation: CaseRoute | null; chosen?: CaseRoute | null; routes: CaseRoute[]; evidence: Evidence[]; blocked: Blocked | null;
  demand: { site?: string; lease?: string; confirmed?: boolean; internal?: boolean; parts?: boolean };
  approval: { ref: string; by: string } | null; exec: unknown; outcome: { net: number } | null; snapshot?: { id: string } | null;
  requested?: unknown;
}
export interface ClassInfo { label: string; plural: string; pre: string; pnew: number; tau: number }
export interface Expected {
  id: string; product: string; cls: string; owner: string; date: string; signal: string; range: string; loc: string; contract: string; customer: string;
  reason: string; expiry: Date; lease: { start: Date; end: Date; months: number }; wh: string; wRange: string;
  outcome: { probs: Record<string, number>; likely: string; prob: number; window: string; modelled: boolean };
  run_stage?: string;
}
export interface Note { id: string; to: string; from: string; title: string; msg: string; status: string; ids?: string[] }

// ---------- api answers ----------
export type SigState = 'done' | 'part' | 'todo' | 'block';
/** A case as the lists send it (di/screens/product.py row()). */
type Row = Case & { model: string; serial: string; stage_key: string; health: number; signals: [string, string, SigState][] };
interface Returned { cases: Row[]; expected_count: number; notes: Note[] }
type ExpectedRow = Omit<Expected, 'expiry' | 'lease'> & { expiry: string; lease: { start: string; end: string; months: number } };
interface ExpectedAnswer { rows: ExpectedRow[]; count: number; source: { vendor: string; freshMin?: number } }
interface JourneyAnswer { visible: boolean; progress?: number; established?: string[] }

const P = '/api/screens/product';
const returned = (tenant: string = view().tenant) => cached<Returned>(withQuery(P + '/returned', { tenant }));
const myRows = (): Row[] => returned('All').cases;
let rowIdx: { of: Row[]; by: Map<string, Row> } | null = null;
function rowById(id: string): Row | undefined {
  const rows = myRows();
  if (rowIdx?.of !== rows) rowIdx = { of: rows, by: new Map(rows.map((r) => [r.id, r])) };
  return rowIdx.by.get(id);
}
const rowsOf = (ids: string[]): Case[] => ids.map(rowById).filter((x): x is Row => !!x);
const expectedAns = () => {
  const a = cached<ExpectedAnswer>(withQuery(P + '/expected', { tenant: view().tenant }));
  return { ...a, rows: expCache(a.rows) };
};
/** ISO times to Dates once per answer, as the pages do date arithmetic on them. */
let expDates: { of: ExpectedRow[]; rows: Expected[] } | null = null;
function expCache(rows: ExpectedRow[]): Expected[] {
  if (expDates?.of !== rows) {
    expDates = {
      of: rows,
      rows: rows.map((e) => ({ ...e, expiry: new Date(e.expiry), lease: { ...e.lease, start: new Date(e.lease.start), end: new Date(e.lease.end) } })),
    };
  }
  return expDates.rows;
}
const journeyAns = (id: string) => cached<JourneyAnswer>(P + '/journey/' + encodeURIComponent(id));

// ---------- cases and scope ----------
/** Returned assets in view: tenant, warehouse and the top-bar tenant filter applied. */
export const visibleCases = (): Case[] => (API ? returned().cases : g<() => Case[]>('visCases')());
/** Every case the account may see, ignoring the top-bar tenant filter. */
export const myCases = (): Case[] => (API ? myRows() : g<() => Case[]>('myCases')());
/** A case by id; in api mode the list row (undefined outside the account's tenants and warehouse). */
export const caseById = (id: string | null | undefined): Case | undefined =>
  !id ? undefined : API ? rowById(id) : g<Record<string, Case>>('CASE_BY_ID')[id];
export const isCaseId = (id: string | null | undefined): boolean =>
  API ? !!id && id in cached<Record<string, unknown>>('/api/screens/nav/scope') : !!caseById(id);
export const classInfo = (cls: string): ClassInfo => (API ? ref<Record<string, ClassInfo>>('CLASSES') : g<Record<string, ClassInfo>>('CLASSES'))[cls];
export const routeInfo = (id: string): { name: string; short: string } =>
  API
    ? ref<{ id: string; name: string; short: string }[]>('ROUTES').find((x) => x.id === id) ?? { name: id, short: id }
    : g<(r: string) => { name: string; short: string }>('rid')(id);
export const facilities = (): string[] => (API ? ref<string[]>('FACILITIES') : g<string[]>('FACILITIES'));
export const tenantOK: (t: string) => boolean = API ? (t) => !!session()?.tenants.includes(t) : fn('tenantOK');
/** The last asset opened on Asset intelligence, else the first of the account's cases (rbLastAsset). */
export function lastAssetId(): string {
  if (!API) return g<() => string>('rbLastAsset')();
  const id = view().lastAsset;
  return id && rowById(id) ? id : myRows()[0]?.id ?? 'RT-1048';
}
export function rememberAsset(id: string) {
  if (!API) {
    g<{ lastAsset?: string }>('S').lastAsset = id;
    return;
  }
  if (view().lastAsset !== id) setView({ lastAsset: id });
}
/** Would the account be allowed to open this route ("integration/map", "audit/log")? */
export const routeAllowed = (path: string): boolean => {
  if (!API) return !!g<(p: string) => boolean>('rbPath')(path);
  const h = String(path).replace(/^#?\/?/, '').split('/');
  return canRoute({ page: h[0], a: h[1] || null, b: h[2] || null }) === true;
};
const feat = () => (API ? ref<Record<string, boolean>>('FEAT') : g<Record<string, boolean>>('FEAT'));
export const poolsEnabled = (): boolean => !!feat().pools;
export const upliftEnabled = (): boolean => !!feat().uplift;

/** Signals: received, diagnostics, certification, economic path (sigOf). */
export const signals = (c: Case): [string, string, SigState][] =>
  API ? (c as Row).signals ?? rowById(c.id)?.signals ?? [] : g<(c: Case) => [string, string, SigState][]>('sigOf')(c);

// ---------- expected returns ----------
export const expectedVisible = (): Expected[] => (API ? expectedAns().rows : g<() => Expected[]>('expVis')());
/** The count on the Expected toggle: tenant and warehouse scope, not the tenant filter (as the demo). */
export const expectedCount = (): number => {
  if (API) return returned().expected_count;
  const ok = g<(e: Expected) => boolean>('whOK');
  return g<Expected[]>('EXPECTED').filter((e) => tenantOK(e.owner) && ok(e)).length;
};
export const leaseSource = (): { vendor: string; freshMin?: number } =>
  API
    ? expectedAns().source
    : g<(id: string) => { vendor: string; freshMin?: number } | undefined>('SRC')('lease') ?? { vendor: 'Contract Management', freshMin: 0 };
/** The agent layer's run marker on an expected return: the case run starts at lease end (stage 1 or 2). */
export function expectedStage(e: Expected): string | null {
  if (API) return e.run_stage ?? null;
  const st = g<{ t: string }[] | undefined>('typeof AF_STAGES==="undefined"?undefined:AF_STAGES');
  if (!st) return null;
  const day = +String(e.date).split(' ')[0], n = day - 2 > new Date(g<Date>('AS_OF')).getUTCDate() ? 1 : 2;
  return 'Stage ' + n + ' · ' + st[n - 1].t;
}
export const classLabel = (cls: string): string => classInfo(cls).label;

// ---------- notifications on the landing page ----------
export function myOpenNotes(): Note[] {
  if (API) return session() ? returned().notes : [];
  const S = g<{ acct: { id: string } | null; notes: Note[] }>('S');
  if (!S.acct) return [];
  return S.notes.filter((n) => n.to === S.acct!.id && n.status === 'open');
}

// ---------- the demo path (journey strip on Returned assets and Asset intelligence) ----------
export const demoCaseId = (): string => (API ? 'RT-1048' : g<() => string>('dpId')());
/** The case's journey can be walked by this account (tenant, warehouse, case and asset pages). */
export const demoVisible = (id: string): boolean => (API ? !!session() && journeyAns(id).visible : !!g<(id: string) => boolean>('dpVisible')(id));
export type JStep = [number, string, string, string]; // n, title, kind, description
export const journeySteps = (): JStep[] => (API ? ref<JStep[]>('JSTEPS') : g<JStep[]>('JSTEPS'));
/** The demo's JG links (its functions are not in the reference lists). */
function jgHref(n: number, id: string): string {
  if (n === 0) return 'product/received?focus=' + id;
  if (n === 1) return 'product/asset/' + id + '?zone=known&jstep=1';
  const step = n <= 3 ? '2' : n === 4 ? '3' : '5';
  const at = n >= 6 && n <= 9 ? '&at=handoff' : n === 10 ? '&at=reconcile' : '';
  return 'product/' + id + '?step=' + step + at + '&jstep=' + n;
}
/** Link (without "#/") for journey step n (0 = Start · Returned assets). */
export const journeyHref = (n: number, id: string): string => (API ? jgHref(n, id) : g<{ h: (id: string) => string }[]>('JG')[n].h(id));
export const journeyProgress = (c: Case): number => (API ? journeyAns(c.id).progress ?? 0 : g<(c: Case) => number>('jgProg')(c));
export const journeyEstablished = (c: Case, n: number): string =>
  API ? journeyAns(c.id).established?.[n] ?? '' : g<(c: Case, n: number) => string>('jgEst')(c, n);
/** Not reached on these pages with the API (the runs are past steps 0 and 1), so empty there. */
export const journeyWaiting = (c: Case, n: number, s: string): string => (API ? '' : g<(c: Case, n: number, s: string) => string>('jgWait')(c, n, s));
export const journeyNextText = (n: number): string => (API ? ref<string[]>('JG_NEXT') : g<string[]>('JG_NEXT'))[n];
export const journeyTitle = (n: number): string => (API ? (n ? journeySteps()[n - 1][1] : 'Returned assets') : g<(n: number) => string>('jgT')(n));
export const journeyLabel = (n: number): string => (API ? (n ? 'Step ' + n + ' · ' + journeyTitle(n) : 'Start · Returned assets') : g<(n: number) => string>('jgL')(n));
export const continueLabel = (n: number): string =>
  (API ? ref<Record<string, string>>('RG_CONT') : g<Record<string, string>>('RG_CONT')).en.replace('{n}', String(n));

// ---------- pools ----------
export interface PoolResult { greedy: { total: number }; optimal: { total: number }; uplift: number; supplies: { id: string }[]; dests: { id: string }[] }
export const pool = (id: string): PoolResult | undefined =>
  API ? cached<{ pools: Record<string, PoolResult> }>(P + '/pools').pools[id] : g<Record<string, PoolResult>>('POOLS')[id];

// ---------- asset intelligence ----------
export interface Health { score: number; comps: { n: string; h: number; st: string; cls: 'ok' | 'warn' | 'bad' }[]; band: Record<string, number>; est: boolean }
export interface LifeEvent { k: string; t: string; d: string; sub?: string; src: string; s: 'done' | 'warn' | 'pending'; note: string }
export interface Rul { certMonths: number; certRef: string; basis: string; estLow: number; estHigh: number; estMonths: number }
export interface Demand { order: string | null; site?: string; lease?: string; confirmed: boolean; horizonMonths: number; line: number | null; shipTo: string | null; needBy: string | null; avoidedPo: string | null }
export interface ReturnRec { cust: string; at: Date; dec: string; grade: string; site: string; ref: string; der: boolean }
export interface PartPrice { n: string; st: string; price: number; pn?: string; qty?: number; inr?: number }
export interface PrepParts {
  parts: { name: string }[]; ops: { name: string; h: number; inr: number }[]; legs: { inr: number }[]; pack: number;
  labH: number; rate: number; std: number; lab: number; B: number; P: number;
}
export interface Diag { metric: string; value: string; source: string; at: string }
export interface ValueOrder { kind: string; ref: string; ack?: unknown; sys: string }
export type ValueState = 'pending' | 'predicted' | 'committed' | 'actual';
export interface Econ {
  r: CaseRoute | null; pos: number; neg: number; net: number; rg: number | null; age: number; mt: number; pr: number; sv: number; avg: number;
  bars: number[]; mx: number; months: string[]; demand: [string, string]; trend: number; price: number;
}
export type EligRow = [string, string, string, string];
/** Lease end, return and transit (the agent layer's afLease): lease, return authorisation, pickup and arrival. */
export interface LeaseTrail {
  lease: string; end: Date; intent: string; usage: string; rma: string; auth: Date; fee: number; repl: string | null; book: number; acq: Date;
  pickup: Date; carrier: string; eta: Date; freight: number;
}
export interface Provenance { id: string; status: 'available' | 'partial' | 'unavailable' }

/** GET /api/screens/product/asset/{id}. */
interface AssetAnswer {
  case: Case; health: Health; facts: [string, string][]; events: LifeEvent[]; return_history: (Omit<ReturnRec, 'at'> & { at: string })[];
  parts: { n: string; st: string; cls: 'ok' | 'warn' | 'bad'; q: number }[]; part_prices: PartPrice[]; catalogue: number; prep_cost: number;
  prep_parts: PrepParts | null; learn_version: string; rul: Rul | null; demand: Demand | null; diag: Diag | null;
  recert: { need: number; cert: number } | null; confidence: string | null; value_order: ValueOrder | null; value_state: ValueState;
  baseline: number | null; econ: Omit<Econ, 'r'>; eligibility: EligRow[]; lease_trail: Record<string, unknown> | null;
  provenance: (Provenance & { key: string })[]; snapshot_time: string | null; closed_last_year: number; term_methods: string[];
  related: string[]; units: string[];
}
const assetAns = (id: string) => cached<AssetAnswer>(P + '/asset/' + encodeURIComponent(id));
const A = (c: Case) => assetAns(c.id);

/**
 * The full case record the asset page shows: the given id, else the last asset opened (else the first case).
 * undefined when there is no such case in the account's tenants and warehouse.
 */
export function assetCase(id: string | null): Case | undefined {
  if (!API) return caseById(id || lastAssetId());
  const k = id || lastAssetId();
  return rowById(k) ? assetAns(k).case : undefined;
}

// identity figures: hashes of the case id (the demo's asHex and the helpers built on it), the same in every mode
function hashId(s: string): string {
  let h = 2166136261;
  for (const ch of s) {
    h ^= ch.charCodeAt(0);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(16).toUpperCase().padStart(8, '0');
}
const hex = (c: Case, k: string): number => parseInt(hashId(c.id + k), 16) || 0;
const modelOf = (c: Case): string => {
  const e = ref<{ cls: string; m: string }[]>('EQUIP').find((x) => x.cls === c.cls);
  return e ? e.m.replace(/s$/, '') : c.product;
};

export const asModel: (c: Case) => string = API ? modelOf : fn('asModel');
export const asTitle: (c: Case) => string = API
  ? (c) => { const m = modelOf(c); return m.toLowerCase().includes(String(c.mfr).split(' ')[0].toLowerCase()) ? m : c.mfr + ' ' + m; }
  : fn('asTitle');
export const asSerial: (c: Case) => string = API ? (c) => 'SN' + String(hex(c, 'sn')).slice(0, 7).padStart(7, '0') : fn('asSerial');
export const asRev: (c: Case) => string = API ? (c) => 'Rev ' + 'ABCDE'[hex(c, 'rv') % 5] : fn('asRev');
export const asReceipt: (c: Case) => string = API ? (c) => 'GR-' + (100000 + (hex(c, 'gr') % 900000)) : fn('asReceipt');
export const asRMA: (c: Case) => string = API ? (c) => 'RMA-' + (55800 + (hex(c, 'rma') % 900)) : fn('asRMA');
export const asSC: (c: Case) => string = API ? (c) => 'SC-' + (7000 + (hex(c, 'sc') % 900)) : fn('asSC');
export const asLease: (c: Case) => string = API ? (c) => 'LS-' + (4900 + (hex(c, 'cl') % 300)) : fn('asLease');
export const asHex: (c: Case, k: string) => number = API ? hex : fn('asHex');

/** The asset's health; for a list row (related assets, the fleet) only its score is sent. */
export const assetHealth: (c: Case) => Health = API
  ? (c) => {
      const r = c as Row;
      return typeof r.health === 'number' ? { score: r.health, comps: [], band: {}, est: !c.grade } : A(c).health;
    }
  : fn('assetHealth');
export const assetFacts: (c: Case) => [string, string][] = API ? (c) => A(c).facts : fn('assetFacts');
export const assetEvents: (c: Case) => LifeEvent[] = API ? (c) => A(c).events : fn('asEvents');
export const assetRelated: (c: Case) => Case[] = API ? (c) => rowsOf(A(c).related) : fn('assetRelated');
export const skuUnits: (c: Case) => Case[] = API ? (c) => rowsOf(A(c).units) : fn('skuUnits');
export const returnHistory: (c: Case) => ReturnRec[] = API ? (c) => A(c).return_history.map((x) => ({ ...x, at: new Date(x.at) })) : fn('asReturnHistory');
export const partsAvailability: (c: Case, h: Health) => { n: string; st: string; cls: 'ok' | 'warn' | 'bad'; q: number }[] = API
  ? (c) => A(c).parts
  : fn('asParts');
export const partPrices: (c: Case, h: Health) => PartPrice[] = API ? (c) => A(c).part_prices : fn('asPartPrices');
export const catalogueValue: (c: Case) => number = API ? (c) => A(c).catalogue : fn('asCatalogue');
export const prepCost: (c: Case) => number = API ? (c) => A(c).prep_cost : fn('asPrepCost');
/** The preparation build-up of the chosen (else recommended) route, which is the route the pages pass. */
export const prepParts = (c: Case, r: CaseRoute): PrepParts | null =>
  API ? A(c).prep_parts : g<(c: Case, r: CaseRoute) => PrepParts | null>('exPrepParts')(c, r) || null;
export const exFx = (): number => (API ? ref<number>('EX_FX') : g<number>('EX_FX'));
export const inr: (n: number) => string = API ? (n) => (n < 0 ? '−' : '') + '₹' + Math.abs(Math.round(n)).toLocaleString('en-IN') : fn('inr');
export const rateCardId = (): string => (API ? ref<{ id: string }>('RATE_CARD') : g<{ id: string }>('RATE_CARD')).id;
/** The learning version of a model ('prep-cost-time', the one the page shows). */
export const learnVersion: (c: Case, k: string) => string = API ? (c) => A(c).learn_version : fn('learnVer');
export const caseRul = (c: Case): Rul | null => (API ? A(c).rul : g<(c: Case) => Rul | null>('caseRul')(c) || null);
export const caseDemand = (c: Case): Demand | null => (API ? A(c).demand : g<(c: Case) => Demand | null>('caseDemand')(c) || null);
export const caseDiag = (c: Case): Diag | null => (API ? A(c).diag : g<(c: Case) => any>('caseDiag')(c) || null);
export const diagKind = (cls: string): string => ((API ? ref<Record<string, string[]>>('DIAG') : g<Record<string, string[]>>('DIAG'))[cls] || ['', 'pct'])[1];
/** Re-certification need for the chosen (else recommended) route, the route the page passes. */
export const recert = (c: Case, r: CaseRoute): { need: number; cert: number } | null =>
  API ? A(c).recert : g<(c: Case, r: CaseRoute) => any>('recert')(c, r) || null;
export const confidence: (c: Case, r: CaseRoute) => string = API ? (c) => A(c).confidence ?? '' : fn('tiConf');
export const valueOrder = (c: Case): ValueOrder | null => (API ? A(c).value_order : g<(c: Case) => any>('valueOrder')(c) || null);
export const valueState: (c: Case) => ValueState = API ? (c) => A(c).value_state : fn('asValState');
export const baseline = (c: Case): number | null => (API ? A(c).baseline : g<(c: Case) => number | null>('asBaseline')(c));

/** The demo's facilities and customer sites (LOCS), by code: the names locName prints. */
const LOC_NAMES: Record<string, string> = {
  'WH-PNQ-01': 'Warehouse 1 · Pune (Chakan)', 'WH-MAA-02': 'Warehouse 2 · Chennai (Sriperumbudur)', 'RC-HSR-01': 'Repair centre · Hosur',
  'LOC-PNQ-01': 'Pune Works (Site 1)', 'LOC-HSR-02': 'Hosur Assembly (Site 2)', 'LOC-CHN-03': 'Chennai Foundry (Site 3)', 'LOC-NSK-04': 'Nashik Plant (Site 4)',
  'LOC-VTZ-05': 'Vizag Port Yard (Site 5)', 'LOC-CBE-06': 'Coimbatore Mill (Site 6)', 'LOC-STV-07': 'Surat Textiles (Site 7)', 'LOC-IDR-08': 'Indore Packaging (Site 8)',
  'EXT-BOM': 'Dealer network hub · Mumbai (Bhiwandi)', 'EXT-BLR': 'Refurbisher auction hub · Bengaluru', 'PTN-MAA': 'Certified recycler · Chennai (Gummidipoondi)',
};
export const locName: (k: string | null) => string = API ? (k) => (k && LOC_NAMES[k]) || String(k) : fn('locName');
export const caseStageKey: (c: Case) => string = API ? (c) => (c as Row).stage_key ?? rowById(c.id)?.stage_key ?? '' : fn('ccStage');
export const gateNames = (): string[] => (API ? ref<string[]>('GATES') : g<string[]>('GATES'));
export const assetTabAllowed = (t: string): boolean => {
  if (!API) return !!g<(t: string) => boolean>('asTabOK')(t);
  const a = currentAccount();
  return !!a && !!rolePolicy(a.role)?.asTabs?.includes(t);
};
export const addDays = (d: Date | string, n: number): Date => new Date(new Date(d).getTime() + n * 864e5);

/** How a cost line was produced (Retrieved, Contracted, Modelled), from the explain trace. */
export function termMethod(c: Case, r: CaseRoute, t: Term): { m: string; cls: string; tip: string } {
  const m = API ? A(c).term_methods[r.terms.indexOf(t)] ?? '' : g<(c: Case, r: CaseRoute, t: Term) => { method: string }>('exTrace')(c, r, t).method;
  const mc = (API ? ref<Record<string, [string, string]>>('EX_MC') : g<Record<string, [string, string]>>('EX_MC'))[m] || ['', m];
  return { m, cls: mc[0], tip: mc[1] };
}

/** Closed decisions of this product for this customer in the last 12 months (skuStrip). */
export function closedLastYear(c: Case): number {
  if (API) return A(c).closed_last_year;
  const m = asModel(c);
  const cut = addDays(g<Date>('AS_OF'), -365);
  return g<{ equip: string; tenant: string; date: string }[]>('ROWS').filter(
    (r) => String(r.equip).replace(/s$/, '') === m && r.tenant === c.owner && new Date(r.date) >= cut,
  ).length;
}

/** asMoney: USD, or the regional currency chosen in settings. */
export function asMoney(v: number, local: boolean): string {
  if (!local) return money(v);
  const c = localCurrency();
  return (v < 0 ? '−' : '') + c[0] + Math.abs(Math.round(v * c[1])).toLocaleString(c[2]);
}
export const localCurrency = (): [string, number, string] =>
  API
    ? ref<Record<string, [string, number, string]>>('RG_CUR')[view().rg.cur]
    : g<Record<string, [string, number, string]>>('RG_CUR')[g<{ rg: { cur: string } }>('S').rg.cur];

/** Economic intelligence figures (asEcon): recovery, cost, net, service history, resale demand and price. */
export function assetEcon(c: Case): Econ {
  if (API) return { ...A(c).econ, r: c.recommendation };
  const r = c.recommendation, K = classInfo(c.cls), q = c.qty;
  const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
  const CC_EST = g<Record<string, number>>('CC_EST');
  const pos = r ? sum(r.terms.filter((t) => t.amt > 0).map((t) => t.amt)) : Math.round(CC_EST[c.cls] * q);
  const neg = r ? sum(r.terms.filter((t) => t.amt < 0).map((t) => t.amt)) : 0;
  const net = r ? r.net : Math.round(pos * 0.8);
  const rg = r ? Math.round(((r.p90 - r.p10) / 2 / Math.max(1, Math.abs(net))) * 100) : null;
  const age = Math.max(1, c.age);
  const mt = Math.round(K.pnew * q * 0.018 * age * (0.8 + (asHex(c, 'mt') % 50) / 100));
  const pr = Math.round(mt * (0.4 + (asHex(c, 'pr') % 40) / 100));
  const sv = Math.round((mt + pr) * (0.9 + (asHex(c, 'sv') % 30) / 100));
  const avg = Math.round(sv / age);
  type R = { cls: string; route: string; status: string; actual: number; q: number; mi: number };
  const rs = g<R[]>('ROWS').filter((x) => x.cls === c.cls && x.route === 'resale' && x.status === 'reconciled' && x.actual > 0);
  const by = Array(12).fill(0) as number[];
  rs.forEach((x) => { by[x.mi]++; });
  const med = g<(a: number[]) => number>('med');
  const unit = (a: R[]) => med(a.map((x) => x.actual / x.q));
  const last3 = rs.filter((x) => x.mi >= 9), prev3 = rs.filter((x) => x.mi >= 6 && x.mi < 9);
  const trend = prev3.length && last3.length ? (unit(last3) / unit(prev3) - 1) * 100 : 0;
  const price = rs.length ? Math.round(unit(rs) * q) : 0;
  const bars = by.slice(6), mx = Math.max(1, ...bars);
  const dem = (bars[3] + bars[4] + bars[5]) / Math.max(1, bars[0] + bars[1] + bars[2]);
  const demand: [string, string] = dem >= 1.1 ? ['Strong', 'ok'] : dem >= 0.9 ? ['Steady', 'warn'] : ['Softening', 'bad'];
  const months = g<string[]>('MONTHS').slice(6);
  return { r, pos, neg, net, rg, age, mt, pr, sv, avg, bars, mx, months, demand, trend, price };
}

/** Eligibility rows (asElig): ownership, contract, warranty, safety and environmental, plus the six gates. */
export function assetEligibility(c: Case): { rows: EligRow[]; route: CaseRoute | null } {
  const r = c.recommendation || (c.routes || [])[0] || null;
  if (API) return { rows: A(c).eligibility, route: r };
  const d = c.demand || {}, spec = c.spec || {};
  const yr = new Date(c.received).getUTCFullYear() - Math.max(0, Math.round(c.age)) + Math.min(6, Math.round(classInfo(c.cls).tau / 2));
  const warrOk = yr >= new Date(g<Date>('AS_OF')).getUTCFullYear();
  const sil = /SIL/.test(spec['Safety rating'] || ''), lith = ['drill', 'batch', 'it'].includes(c.cls), erase = c.cls === 'it' && spec['Data erasure'] === 'Pending';
  const rows: EligRow[] = [
    ['Ownership', c.owner, 'Eligible for all treatments', 'ok'],
    ['Contract terms', d.lease ? 'Lease ' + asLease(c) + ' ended, no restriction on reuse' : 'No contract restriction on file', d.lease ? 'Verified' : 'Not on file', d.lease ? 'ok' : 'line'],
    ['Warranty', warrOk ? 'Active until ' + yr : 'Expired (' + yr + ')', warrOk ? 'Active' : '—', warrOk ? 'ok' : 'line'],
    ['Safety and regulatory', sil ? 'Safety-rated unit (' + spec['Safety rating'] + ')' : 'No open safety alerts', sil ? 'Review' : 'Compliant', sil ? 'warn' : 'ok'],
    ['Environmental', erase ? 'Data erasure certificate pending' : lith ? 'Lithium battery handling required' : 'No special handling', erase || lith ? 'Follow guidelines' : 'Compliant', erase || lith ? 'warn' : 'ok'],
  ];
  return { rows, route: r };
}

export const leaseTrail = (c: Case): LeaseTrail | null => {
  if (API) {
    const L = A(c).lease_trail;
    if (!L) return null;
    const d = (k: string) => new Date(L[k] as string);
    return { ...(L as unknown as LeaseTrail), end: d('end'), auth: d('auth'), acq: d('acq'), pickup: d('pickup'), eta: d('eta') };
  }
  const f = g<((c: Case) => LeaseTrail) | undefined>('typeof afLease==="undefined"?undefined:afLease');
  return f ? f(c) : null;
};
export const badgeTip = (k: string): string => (API ? ref<Record<string, string>>('AF_BADGE_TIP') : g<Record<string, string>>('AF_BADGE_TIP'))[k] || k;

// ---------- evidence snapshot ----------
export const provenance = (c: Case, e: Evidence): Provenance => {
  if (!API) return g<(c: Case, e: Evidence) => Provenance>('provFor')(c, e);
  const l = A(c).provenance;
  return l.find((p) => p.key === e.k) ?? l[c.evidence.indexOf(e)] ?? { id: '', status: 'unavailable' };
};
export const snapshotTime = (c: Case): string => {
  if (!API) return g<(d: Date) => string>('isoT')(g<(c: Case) => Date>('snapTime')(c));
  const t = A(c).snapshot_time;
  return t ? new Date(t).toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC') : '—';
};
