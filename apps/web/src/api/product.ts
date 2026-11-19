/**
 * Product area (Decision Workbench lists and Asset & Product Intelligence): typed reads over the engine.
 * Every figure comes from the demo's own helpers (visCases, assetHealth, asEvents, caseRul …), so numbers match index.html.
 */
import { engine } from '../engine/engine';

/* eslint-disable @typescript-eslint/no-explicit-any */
const g = <T = any>(name: string): T => engine()<T>(name);
const fn = <A extends unknown[], R>(name: string) => (...a: A): R => g<(...x: A) => R>(name)(...a);

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
}
export interface Note { id: string; to: string; from: string; title: string; msg: string; status: string; ids?: string[] }

// ---------- cases and scope ----------
/** Returned assets in view: tenant, warehouse and the top-bar tenant filter applied. */
export const visibleCases = (): Case[] => g<() => Case[]>('visCases')();
/** Every case the account may see, ignoring the top-bar tenant filter. */
export const myCases = (): Case[] => g<() => Case[]>('myCases')();
export const caseById = (id: string | null | undefined): Case | undefined => (id ? g<Record<string, Case>>('CASE_BY_ID')[id] : undefined);
export const isCaseId = (id: string | null | undefined): boolean => !!caseById(id);
export const classInfo = (cls: string): ClassInfo => g<Record<string, ClassInfo>>('CLASSES')[cls];
export const routeInfo = (id: string): { name: string; short: string } => g<(r: string) => { name: string; short: string }>('rid')(id);
export const facilities = (): string[] => g<string[]>('FACILITIES');
export const tenantOK = fn<[string], boolean>('tenantOK');
/** The last asset opened on Asset intelligence, else the first visible case (rbLastAsset). */
export const lastAssetId = (): string => g<() => string>('rbLastAsset')();
export function rememberAsset(id: string) {
  g<{ lastAsset?: string }>('S').lastAsset = id;
}
/** Would the account be allowed to open this route ("integration/map", "audit/log")? */
export const routeAllowed = (path: string): boolean => !!g<(p: string) => boolean>('rbPath')(path);
export const poolsEnabled = (): boolean => !!g<{ pools: boolean }>('FEAT').pools;
export const upliftEnabled = (): boolean => !!g<{ uplift: boolean }>('FEAT').uplift;

/** Signals: received, diagnostics, certification, economic path (sigOf). */
export type SigState = 'done' | 'part' | 'todo' | 'block';
export const signals = (c: Case): [string, string, SigState][] => g<(c: Case) => [string, string, SigState][]>('sigOf')(c);

// ---------- expected returns ----------
export const expectedVisible = (): Expected[] => g<() => Expected[]>('expVis')();
/** The count on the Expected toggle: tenant and warehouse scope, not the tenant filter (as the demo). */
export const expectedCount = (): number => {
  const ok = g<(e: Expected) => boolean>('whOK');
  return g<Expected[]>('EXPECTED').filter((e) => tenantOK(e.owner) && ok(e)).length;
};
export const leaseSource = (): { vendor: string; freshMin?: number } =>
  g<(id: string) => { vendor: string; freshMin?: number } | undefined>('SRC')('lease') ?? { vendor: 'Contract Management', freshMin: 0 };
/** The agent layer's run marker on an expected return: the case run starts at lease end (stage 1 or 2). */
export function expectedStage(e: Expected): string | null {
  const st = g<{ t: string }[] | undefined>('typeof AF_STAGES==="undefined"?undefined:AF_STAGES');
  if (!st) return null;
  const day = +String(e.date).split(' ')[0], n = day - 2 > new Date(g<Date>('AS_OF')).getUTCDate() ? 1 : 2;
  return 'Stage ' + n + ' · ' + st[n - 1].t;
}
export const classLabel = (cls: string): string => classInfo(cls).label;

// ---------- notifications on the landing page ----------
export function myOpenNotes(): Note[] {
  const S = g<{ acct: { id: string } | null; notes: Note[] }>('S');
  if (!S.acct) return [];
  return S.notes.filter((n) => n.to === S.acct!.id && n.status === 'open');
}

// ---------- the demo path (journey strip on Returned assets and Asset intelligence) ----------
export const demoCaseId = (): string => g<() => string>('dpId')();
/** The case's journey can be walked by this account (tenant, warehouse, case and asset pages). */
export const demoVisible = (id: string): boolean => !!g<(id: string) => boolean>('dpVisible')(id);
export type JStep = [number, string, string, string]; // n, title, kind, description
export const journeySteps = (): JStep[] => g<JStep[]>('JSTEPS');
/** Link (without "#/") for journey step n (0 = Start · Returned assets). */
export const journeyHref = (n: number, id: string): string => g<{ h: (id: string) => string }[]>('JG')[n].h(id);
export const journeyProgress = (c: Case): number => g<(c: Case) => number>('jgProg')(c);
export const journeyEstablished = (c: Case, n: number): string => g<(c: Case, n: number) => string>('jgEst')(c, n);
export const journeyWaiting = (c: Case, n: number, s: string): string => g<(c: Case, n: number, s: string) => string>('jgWait')(c, n, s);
export const journeyNextText = (n: number): string => g<string[]>('JG_NEXT')[n];
export const journeyTitle = (n: number): string => g<(n: number) => string>('jgT')(n);
export const journeyLabel = (n: number): string => g<(n: number) => string>('jgL')(n);
export const continueLabel = (n: number): string => g<Record<string, string>>('RG_CONT').en.replace('{n}', String(n));

// ---------- pools ----------
export interface PoolResult { greedy: { total: number }; optimal: { total: number }; uplift: number; supplies: { id: string }[]; dests: { id: string }[] }
export const pool = (id: string): PoolResult | undefined => g<Record<string, PoolResult>>('POOLS')[id];

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

export const asModel = fn<[Case], string>('asModel');
export const asTitle = fn<[Case], string>('asTitle');
export const asSerial = fn<[Case], string>('asSerial');
export const asRev = fn<[Case], string>('asRev');
export const asReceipt = fn<[Case], string>('asReceipt');
export const asRMA = fn<[Case], string>('asRMA');
export const asSC = fn<[Case], string>('asSC');
export const asLease = fn<[Case], string>('asLease');
export const asHex = fn<[Case, string], number>('asHex');
export const assetHealth = fn<[Case], Health>('assetHealth');
export const assetFacts = fn<[Case], [string, string][]>('assetFacts');
export const assetEvents = fn<[Case], LifeEvent[]>('asEvents');
export const assetRelated = fn<[Case], Case[]>('assetRelated');
export const skuUnits = fn<[Case], Case[]>('skuUnits');
export const returnHistory = fn<[Case], ReturnRec[]>('asReturnHistory');
export const partsAvailability = fn<[Case, Health], { n: string; st: string; cls: 'ok' | 'warn' | 'bad'; q: number }[]>('asParts');
export const partPrices = fn<[Case, Health], PartPrice[]>('asPartPrices');
export const catalogueValue = fn<[Case], number>('asCatalogue');
export const prepCost = fn<[Case], number>('asPrepCost');
export const prepParts = (c: Case, r: CaseRoute): PrepParts | null => g<(c: Case, r: CaseRoute) => PrepParts | null>('exPrepParts')(c, r) || null;
export const exFx = (): number => g<number>('EX_FX');
export const inr = fn<[number], string>('inr');
export const rateCardId = (): string => g<{ id: string }>('RATE_CARD').id;
export const learnVersion = fn<[Case, string], string>('learnVer');
export const caseRul = (c: Case): Rul | null => g<(c: Case) => Rul | null>('caseRul')(c) || null;
export const caseDemand = (c: Case): Demand | null => g<(c: Case) => Demand | null>('caseDemand')(c) || null;
export const caseDiag = (c: Case): { metric: string; value: string; source: string; at: string } | null => g<(c: Case) => any>('caseDiag')(c) || null;
export const diagKind = (cls: string): string => (g<Record<string, string[]>>('DIAG')[cls] || ['', 'pct'])[1];
export const recert = (c: Case, r: CaseRoute): { need: number; cert: number } | null => g<(c: Case, r: CaseRoute) => any>('recert')(c, r) || null;
export const confidence = fn<[Case, CaseRoute], string>('tiConf');
export const valueOrder = (c: Case): { kind: string; ref: string; ack?: unknown; sys: string } | null => g<(c: Case) => any>('valueOrder')(c) || null;
export const valueState = fn<[Case], 'pending' | 'predicted' | 'committed' | 'actual'>('asValState');
export const baseline = (c: Case): number | null => g<(c: Case) => number | null>('asBaseline')(c);
export const locName = fn<[string | null], string>('locName');
export const caseStageKey = fn<[Case], string>('ccStage');
export const gateNames = (): string[] => g<string[]>('GATES');
export const assetTabAllowed = (t: string): boolean => !!g<(t: string) => boolean>('asTabOK')(t);
export const addDays = (d: Date | string, n: number): Date => g<(d: Date | string, n: number) => Date>('addDays')(d, n);

/** How a cost line was produced (Retrieved, Contracted, Modelled), from the explain trace. */
export function termMethod(c: Case, r: CaseRoute, t: Term): { m: string; cls: string; tip: string } {
  const m = g<(c: Case, r: CaseRoute, t: Term) => { method: string }>('exTrace')(c, r, t).method;
  const mc = g<Record<string, [string, string]>>('EX_MC')[m] || ['', m];
  return { m, cls: mc[0], tip: mc[1] };
}

/** Closed decisions of this product for this customer in the last 12 months (skuStrip). */
export function closedLastYear(c: Case): number {
  const m = asModel(c);
  const cut = addDays(g<Date>('AS_OF'), -365);
  return g<{ equip: string; tenant: string; date: string }[]>('ROWS').filter(
    (r) => String(r.equip).replace(/s$/, '') === m && r.tenant === c.owner && new Date(r.date) >= cut,
  ).length;
}

/** asMoney: USD, or the regional currency chosen in settings. */
export function asMoney(v: number, local: boolean): string {
  if (!local) return g<(n: number) => string>('money')(v);
  const c = localCurrency();
  return (v < 0 ? '−' : '') + c[0] + Math.abs(Math.round(v * c[1])).toLocaleString(c[2]);
}
export const localCurrency = (): [string, number, string] => g<Record<string, [string, number, string]>>('RG_CUR')[g<{ rg: { cur: string } }>('S').rg.cur];

/** Economic intelligence figures (asEcon): recovery, cost, net, service history, resale demand and price. */
export function assetEcon(c: Case) {
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
  type Row = { cls: string; route: string; status: string; actual: number; q: number; mi: number };
  const rs = g<Row[]>('ROWS').filter((x) => x.cls === c.cls && x.route === 'resale' && x.status === 'reconciled' && x.actual > 0);
  const by = Array(12).fill(0) as number[];
  rs.forEach((x) => { by[x.mi]++; });
  const med = g<(a: number[]) => number>('med');
  const unit = (a: Row[]) => med(a.map((x) => x.actual / x.q));
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
export function assetEligibility(c: Case) {
  const d = c.demand || {}, spec = c.spec || {}, r = c.recommendation || (c.routes || [])[0] || null;
  const yr = new Date(c.received).getUTCFullYear() - Math.max(0, Math.round(c.age)) + Math.min(6, Math.round(classInfo(c.cls).tau / 2));
  const warrOk = yr >= new Date(g<Date>('AS_OF')).getUTCFullYear();
  const sil = /SIL/.test(spec['Safety rating'] || ''), lith = ['drill', 'batch', 'it'].includes(c.cls), erase = c.cls === 'it' && spec['Data erasure'] === 'Pending';
  const rows: [string, string, string, string][] = [
    ['Ownership', c.owner, 'Eligible for all treatments', 'ok'],
    ['Contract terms', d.lease ? 'Lease ' + asLease(c) + ' ended, no restriction on reuse' : 'No contract restriction on file', d.lease ? 'Verified' : 'Not on file', d.lease ? 'ok' : 'line'],
    ['Warranty', warrOk ? 'Active until ' + yr : 'Expired (' + yr + ')', warrOk ? 'Active' : '—', warrOk ? 'ok' : 'line'],
    ['Safety and regulatory', sil ? 'Safety-rated unit (' + spec['Safety rating'] + ')' : 'No open safety alerts', sil ? 'Review' : 'Compliant', sil ? 'warn' : 'ok'],
    ['Environmental', erase ? 'Data erasure certificate pending' : lith ? 'Lithium battery handling required' : 'No special handling', erase || lith ? 'Follow guidelines' : 'Compliant', erase || lith ? 'warn' : 'ok'],
  ];
  return { rows, route: r };
}

/** Lease end, return and transit (the agent layer's afLease): lease, return authorisation, pickup and arrival. */
export interface LeaseTrail {
  lease: string; end: Date; intent: string; usage: string; rma: string; auth: Date; fee: number; repl: string | null; book: number; acq: Date;
  pickup: Date; carrier: string; eta: Date; freight: number;
}
export const leaseTrail = (c: Case): LeaseTrail | null => {
  const f = g<((c: Case) => LeaseTrail) | undefined>('typeof afLease==="undefined"?undefined:afLease');
  return f ? f(c) : null;
};
export const badgeTip = (k: string): string => g<Record<string, string>>('AF_BADGE_TIP')[k] || k;

// ---------- evidence snapshot ----------
export interface Provenance { id: string; status: 'available' | 'partial' | 'unavailable' }
export const provenance = (c: Case, e: Evidence): Provenance => g<(c: Case, e: Evidence) => Provenance>('provFor')(c, e);
export const snapshotTime = (c: Case): string => g<(d: Date) => string>('isoT')(g<(c: Case) => Date>('snapTime')(c));
