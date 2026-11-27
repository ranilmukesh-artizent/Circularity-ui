/**
 * Product area (Decision Workbench lists and Asset & Product Intelligence): typed reads.
 * GET /api/screens/product/returned, /expected, /journey/{id}, /asset/{id} and /pools, the reference lists, the
 * session and the view settings (backend/di/services/screens/product.py has the mapping).
 *
 * A case from the lists (visibleCases, myCases, caseById, assetRelated, skuUnits) is the list row: the fields the
 * queue, the drawer, the journey and compare read, with its recommendation in brief. The asset page reads the full
 * record with assetCase(id); the per-case figures (assetHealth, caseRul …) come from that asset's answer.
 */
import { cached, classLabelOf, invalidate, ref, session, withQuery } from './client';
export { classLabelOf };
import { money } from './format';
import { canRoute, currentAccount, rolePolicy } from './session';
import { setView, view } from './view';

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
/** A case as the lists send it (di/services/screens/product.py row()). */
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
export const visibleCases = (): Case[] => returned().cases;
/** Every case the account may see, ignoring the top-bar tenant filter. */
export const myCases = (): Case[] => myRows();
/** A case by id: the list row (undefined outside the account's tenants and warehouse). */
export const caseById = (id: string | null | undefined): Case | undefined => (!id ? undefined : rowById(id));
export const isCaseId = (id: string | null | undefined): boolean => !!id && id in cached<Record<string, unknown>>('/api/screens/nav/scope');
const SCOPE_PATH = '/api/screens/nav/scope';
const CASE_SHAPE = /^RT-\d+$/;
const probed = new Map<string, number>(); // case id -> when the list was last read again for it
const PROBE_EVERY_MS = 5000;
/**
 * Should the link to `id` make the case list (nav/scope) load again? Yes, when it looks like a case id and is not in the
 * list read at sign-in, and the list was not read again for it in the last few seconds: a case opened since (by a scan, an
 * agent, another person) is unknown to the cache, not missing. The route then waits for the new answer instead of showing
 * the list page; a really missing id is answered by the server (the case page says so).
 */
export function shouldReloadScope(id: string | null | undefined, known: boolean, lastProbe?: number, now = Date.now()): boolean {
  return !!id && !known && CASE_SHAPE.test(id) && (lastProbe === undefined || now - lastProbe >= PROBE_EVERY_MS);
}
/** Load the case list again for a link to a case it does not hold yet (see shouldReloadScope); false when nothing was done. */
export function reloadScopeFor(id: string | null | undefined): boolean {
  if (!id || !shouldReloadScope(id, isCaseId(id), probed.get(id))) return false;
  probed.set(id, Date.now());
  invalidate((k) => k[0] === 'GET' && k[1] === SCOPE_PATH);
  return true;
}
export const classInfo = (cls: string): ClassInfo => ref('CLASSES')[cls];
export const routeInfo = (id: string): { name: string; short: string } =>
  ref('ROUTES').find((x) => x.id === id) ?? { name: id, short: id };
export const facilities = (): string[] => ref('FACILITIES');
export const tenantOK = (t: string): boolean => !!session()?.tenants.includes(t);
/** The last asset opened on Asset intelligence, else the first of the account's cases (rbLastAsset). */
export function lastAssetId(): string {
  const id = view().lastAsset;
  return id && rowById(id) ? id : myRows()[0]?.id ?? 'RT-1048';
}
export function rememberAsset(id: string) {
  if (view().lastAsset !== id) setView({ lastAsset: id });
}
/** Would the account be allowed to open this route ("integration/map", "audit/log")? */
export const routeAllowed = (path: string): boolean => {
  const h = String(path).replace(/^#?\/?/, '').split('/');
  return canRoute({ page: h[0], a: h[1] || null, b: h[2] || null }) === true;
};
const feat = () => ref('FEAT');
export const upliftEnabled = (): boolean => !!feat().uplift;

/** Signals: received, diagnostics, certification, economic path (sigOf). */
export const signals = (c: Case): [string, string, SigState][] => (c as Row).signals ?? rowById(c.id)?.signals ?? [];

// ---------- expected returns ----------
export const expectedVisible = (): Expected[] => expectedAns().rows;
/** The count on the Expected toggle: tenant and warehouse scope, not the tenant filter (as the demo). */
export const expectedCount = (): number => returned().expected_count;
export const leaseSource = (): { vendor: string; freshMin?: number } => expectedAns().source;
/** The agent layer's run marker on an expected return: the case run starts at lease end (stage 1 or 2). */
export const expectedStage = (e: Expected): string | null => e.run_stage ?? null;
export const classLabel = (cls: string): string => classInfo(cls).label;

// ---------- notifications on the landing page ----------
export const myOpenNotes = (): Note[] => (session() ? returned().notes : []);

// ---------- the demo path (journey strip on Returned assets and Asset intelligence) ----------
export const demoCaseId = (): string => 'RT-1048';
/** The case's journey can be walked by this account (tenant, warehouse, case and asset pages). */
export const demoVisible = (id: string): boolean => !!session() && journeyAns(id).visible;
export type JStep = [number, string, string, string]; // n, title, kind, description
export const journeySteps = (): JStep[] => ref('JSTEPS');
/** Link (without "#/") for journey step n (0 = Start · Returned assets); the demo's JG links. */
export function journeyHref(n: number, id: string): string {
  if (n === 0) return 'product/received?focus=' + id;
  if (n === 1) return 'product/asset/' + id + '?zone=known&jstep=1';
  const step = n <= 3 ? '2' : n === 4 ? '3' : '5';
  const at = n >= 6 && n <= 9 ? '&at=handoff' : n === 10 ? '&at=reconcile' : '';
  return 'product/' + id + '?step=' + step + at + '&jstep=' + n;
}
export const journeyProgress = (c: Case): number => journeyAns(c.id).progress ?? 0;
export const journeyEstablished = (c: Case, n: number): string => journeyAns(c.id).established?.[n] ?? '';
/** Not reached on these pages (the runs are past steps 0 and 1), so empty. */
export const journeyWaiting = (_c: Case, _n: number, _s: string): string => '';
export const journeyNextText = (n: number): string => ref('JG_NEXT')[n];
export const journeyTitle = (n: number): string => (n ? journeySteps()[n - 1][1] : 'Returned assets');
export const journeyLabel = (n: number): string => (n ? 'Step ' + n + ' · ' + journeyTitle(n) : 'Start · Returned assets');
export const continueLabel = (n: number): string => ref('RG_CONT').en.replace('{n}', String(n));

// ---------- pools ----------
export interface PoolResult { greedy: { total: number }; optimal: { total: number }; uplift: number; supplies: { id: string }[]; dests: { id: string }[] }
export const pool = (id: string): PoolResult | undefined => cached<{ pools: Record<string, PoolResult> }>(P + '/pools').pools[id];

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
  const k = id || lastAssetId();
  return rowById(k) ? assetAns(k).case : undefined;
}

// identity figures: hashes of the case id (the demo's asHex and the helpers built on it)
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
  const e = ref('EQUIP').find((x) => x.cls === c.cls);
  return e ? e.m.replace(/s$/, '') : c.product;
};

export const asModel: (c: Case) => string = modelOf;
export const asTitle = (c: Case): string => { const m = modelOf(c); return m.toLowerCase().includes(String(c.mfr).split(' ')[0].toLowerCase()) ? m : c.mfr + ' ' + m; };
export const asSerial = (c: Case): string => 'SN' + String(hex(c, 'sn')).slice(0, 7).padStart(7, '0');
export const asRev = (c: Case): string => 'Rev ' + 'ABCDE'[hex(c, 'rv') % 5];
export const asReceipt = (c: Case): string => 'GR-' + (100000 + (hex(c, 'gr') % 900000));
export const asRMA = (c: Case): string => 'RMA-' + (55800 + (hex(c, 'rma') % 900));
export const asSC = (c: Case): string => 'SC-' + (7000 + (hex(c, 'sc') % 900));
export const asHex: (c: Case, k: string) => number = hex;

/** The asset's health; for a list row (related assets, the fleet) only its score is sent. */
export const assetHealth = (c: Case): Health => {
  const r = c as Row;
  return typeof r.health === 'number' ? { score: r.health, comps: [], band: {}, est: !c.grade } : A(c).health;
};
export const assetFacts = (c: Case): [string, string][] => A(c).facts;
export const assetEvents = (c: Case): LifeEvent[] => A(c).events;
export const assetRelated = (c: Case): Case[] => rowsOf(A(c).related);
export const skuUnits = (c: Case): Case[] => rowsOf(A(c).units);
export const returnHistory = (c: Case): ReturnRec[] => A(c).return_history.map((x) => ({ ...x, at: new Date(x.at) }));
export const partsAvailability = (c: Case, _h: Health): { n: string; st: string; cls: 'ok' | 'warn' | 'bad'; q: number }[] => A(c).parts;
export const partPrices = (c: Case, _h: Health): PartPrice[] => A(c).part_prices;
export const catalogueValue = (c: Case): number => A(c).catalogue;
export const prepCost = (c: Case): number => A(c).prep_cost;
/** The preparation build-up of the chosen (else recommended) route, which is the route the pages pass. */
export const prepParts = (c: Case, _r: CaseRoute): PrepParts | null => A(c).prep_parts;
export const exFx = (): number => ref('EX_FX');
export const inr = (n: number): string => (n < 0 ? '−' : '') + '₹' + Math.abs(Math.round(n)).toLocaleString('en-IN');
export const rateCardId = (): string => ref('RATE_CARD').id;
/** The learning version of a model ('prep-cost-time', the one the page shows). */
export const learnVersion = (c: Case, _k: string): string => A(c).learn_version;
export const caseRul = (c: Case): Rul | null => A(c).rul;
export const caseDemand = (c: Case): Demand | null => A(c).demand;
export const caseDiag = (c: Case): Diag | null => A(c).diag;
export const diagKind = (cls: string): string => (ref('DIAG')[cls] || ['', 'pct'])[1];
/** Re-certification need for the chosen (else recommended) route, the route the page passes. */
export const recert = (c: Case, _r: CaseRoute): { need: number; cert: number } | null => A(c).recert;
export const confidence = (c: Case, _r: CaseRoute): string => A(c).confidence ?? '';
export const valueOrder = (c: Case): ValueOrder | null => A(c).value_order;
export const valueState = (c: Case): ValueState => A(c).value_state;
export const baseline = (c: Case): number | null => A(c).baseline;

/** The demo's facilities and customer sites (LOCS), by code: the names locName prints. */
const LOC_NAMES: Record<string, string> = {
  'WH-PNQ-01': 'Warehouse 1 · Pune (Chakan)', 'WH-MAA-02': 'Warehouse 2 · Chennai (Sriperumbudur)', 'RC-HSR-01': 'Repair centre · Hosur',
  'LOC-PNQ-01': 'Pune Works (Site 1)', 'LOC-HSR-02': 'Hosur Assembly (Site 2)', 'LOC-CHN-03': 'Chennai Foundry (Site 3)', 'LOC-NSK-04': 'Nashik Plant (Site 4)',
  'LOC-VTZ-05': 'Vizag Port Yard (Site 5)', 'LOC-CBE-06': 'Coimbatore Mill (Site 6)', 'LOC-STV-07': 'Surat Textiles (Site 7)', 'LOC-IDR-08': 'Indore Packaging (Site 8)',
  'EXT-BOM': 'Dealer network hub · Mumbai (Bhiwandi)', 'EXT-BLR': 'Refurbisher auction hub · Bengaluru', 'PTN-MAA': 'Certified recycler · Chennai (Gummidipoondi)',
};
export const locName = (k: string | null): string => (k && LOC_NAMES[k]) || String(k);
export const caseStageKey = (c: Case): string => (c as Row).stage_key ?? rowById(c.id)?.stage_key ?? '';
export const gateNames = (): string[] => ref('GATES');
export const assetTabAllowed = (t: string): boolean => {
  const a = currentAccount();
  return !!a && !!rolePolicy(a.role)?.asTabs?.includes(t);
};
export const addDays = (d: Date | string, n: number): Date => new Date(new Date(d).getTime() + n * 864e5);

/** How a cost line was produced (Retrieved, Contracted, Modelled), from the explain trace. */
export function termMethod(c: Case, r: CaseRoute, t: Term): { m: string; cls: string; tip: string } {
  const m = A(c).term_methods[r.terms.indexOf(t)] ?? '';
  const mc = ref('EX_MC')[m] || ['', m];
  return { m, cls: mc[0], tip: mc[1] };
}

/** Closed decisions of this product for this customer in the last 12 months (skuStrip). */
export const closedLastYear = (c: Case): number => A(c).closed_last_year;

/** asMoney: USD, or the regional currency chosen in settings. */
export function asMoney(v: number, local: boolean): string {
  if (!local) return money(v);
  const c = localCurrency();
  return (v < 0 ? '−' : '') + c[0] + Math.abs(Math.round(v * c[1])).toLocaleString(c[2]);
}
export const localCurrency = (): [string, number, string, string] => ref('RG_CUR')[view().rg.cur];

/** Economic intelligence figures (asEcon): recovery, cost, net, service history, resale demand and price. */
export const assetEcon = (c: Case): Econ => ({ ...A(c).econ, r: c.recommendation });

/** Eligibility rows (asElig): ownership, contract, warranty, safety and environmental, plus the six gates. */
export function assetEligibility(c: Case): { rows: EligRow[]; route: CaseRoute | null } {
  const r = c.recommendation || (c.routes || [])[0] || null;
  return { rows: A(c).eligibility, route: r };
}

export const leaseTrail = (c: Case): LeaseTrail | null => {
  const L = A(c).lease_trail;
  if (!L) return null;
  const d = (k: string) => new Date(L[k] as string);
  return { ...(L as unknown as LeaseTrail), end: d('end'), auth: d('auth'), acq: d('acq'), pickup: d('pickup'), eta: d('eta') };
};
export const badgeTip = (k: string): string => ref('AF_BADGE_TIP')[k] || k;

// ---------- evidence snapshot ----------
export const provenance = (c: Case, e: Evidence): Provenance => {
  const l = A(c).provenance;
  return l.find((p) => p.key === e.k) ?? l[c.evidence.indexOf(e)] ?? { id: '', status: 'unavailable' };
};
export const snapshotTime = (c: Case): string => {
  const t = A(c).snapshot_time;
  return t ? new Date(t).toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC') : '—';
};
