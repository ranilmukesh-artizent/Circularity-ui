/**
 * Command Center (#/command/<section>): typed reads over GET /api/screens/command/* (di/screens/command.py has the
 * mapping), with the filters and view settings as query parameters. The filters, the senior view's "operational
 * queues" toggle and the widened operational scope live in this module; the Admin's senior/operational choice is a
 * view setting (view.ts). A CcScope or CcRows is only a handle for the current filters: read it through the functions
 * below, never its fields. Pages only draw.
 */
import { invoke } from './actions';
import { cached, ref, session, withQuery } from './client';
import { asOfNow, fmtDY, kfmt as kfmtLocal, rgTime } from './home';
import { accounts, canRoute } from './session';
import { bump } from './store';
import type { Account, ActionResult } from './types';
import { setView, view } from './view';

const sum = (a: number[]) => a.reduce((x, y) => x + (y || 0), 0);

// ---------------------------------------------------------------- types

export interface CcRec { id: string; net: number; p10: number; p90: number; plan: string; demandStatus?: string }
export interface CcCase {
  id: string; assetId: string; product: string; qty: number; owner: string; location: string; cls: string;
  stage: string; assessment: string; grade?: string; timing?: string; reevalReason?: string;
  recommendation?: CcRec | null; chosen?: CcRec | null;
  blocked?: { action: string; gateName: string; owner: string } | null;
  submitted?: { by: string } | null;
  _st: string; _left: number; _risk: Record<string, number>; _var: number; _val: number; _due: string; _score: number; _pri?: 'High' | 'Medium' | 'Low';
}
export interface CcScope { all: CcCase[]; act: CcCase[]; util: Record<string, number>; net: number }
export interface CcLayout {
  sub: string; kpis: string[]; charts?: string[]; row?: string[];
  aome?: number; handed?: number; inbox?: number; outcomes?: number; actions?: number; ops?: number; fin?: number;
  senior?: number; exceptions?: number; health?: 'full' | 'strip';
}
export interface CcFilters { site: string; cls: string; route: string; stage: string; reason: string; due: string; view: string; q: string; months: number }
/** Closed decisions (ROWS in the demo); opaque to pages. */
export type CcRows = { readonly __rows: unique symbol }[];
export interface CcMetrics { act: number; base: number; uplift: number; avoided: number; days: number | null; rcCount: number; p50: number; co2e: number }
export interface Delta { txt: string; arrow: string; cls: 'ok' | 'bad' }

// ---------------------------------------------------------------- local view state and the endpoints

const CC0: CcFilters = { site: '', cls: '', route: '', stage: '', reason: '', due: '', view: '', q: '', months: 12 };
/** The filters and toggles the demo kept on S, per signed-in account (reset when another account signs in). */
const local = { id: '', cc: { ...CC0 }, ops: false, widen: false };
function st() {
  const id = session()?.account.id ?? '';
  if (id !== local.id) Object.assign(local, { id, cc: { ...CC0 }, ops: false, widen: false });
  return local;
}
/** The handles handed out for a scope and the closed decisions (the figures come from the endpoints). */
const SCOPE: CcScope = { all: [], act: [], util: {}, net: 0 };
const ROWS = [] as unknown as CcRows;

const P = '/api/screens/command';
const get = <T>(path: string, q: Record<string, string | number | boolean> = {}): T => cached<T>(withQuery(P + path, q));
const tenantQ = () => view().tenant;
const modeQ = () => view().ccMode;
function scopeQ() {
  const f = st().cc;
  return { tenant: tenantQ(), site: f.site, cls: f.cls, route: f.route, months: f.months };
}

interface LayoutAnswer { layout: CcLayout | null; keys: string[]; sections: string[] }
interface KpisAnswer {
  tiles: KpiTile[]; insights: [string, string][]; metrics: CcMetrics; health: ReturnType<typeof healthStrip>;
  counts: { cases: number; rows: number; sources: number; workflows: number };
}
type CapRow = { k: string; label: string; u: number; cap: number; p: number; color: string; msg: string };
type VarRow = { reason: string; v: number; pct: number; w: number; color: string; tip: string };
interface ChartsAnswer {
  stages: Slice[]; due: Slice[]; routes: RouteBar[]; var: VarRow[]; combo: { mi: number; p: number; a: number; y: number }[];
  signals: Signal[]; capacity: CapRow[];
}
type ActionRow = Omit<OppRow, 'c'> & { case: CcCase };
interface InboxAnswer {
  requests: AccessRequest[]; scope: string[] | null; decisions_awaiting: number;
  cards: (Omit<ApprovalCard, 'steps'> & { kinds: string[]; steps?: string[] })[]; limit: number | null;
}
type OpScope = { home: string; scope: string; locked: boolean };

const layoutA = () => get<LayoutAnswer>('/layout', { mode: modeQ() });
const kpisA = () => get<KpisAnswer>('/kpis', { ...scopeQ(), mode: modeQ() });
const chartsA = () => get<ChartsAnswer>('/charts', scopeQ());
function actionsA() {
  const f = st().cc;
  return get<{ rows: ActionRow[]; total: number }>('/actions', { ...scopeQ(), stage: f.stage, due: f.due, reason: f.reason, q: f.q });
}
const exA = () => get<{ rows: ExRow[]; awaiting: { id: string; plan: string | null; net: number }[] }>('/exceptions', scopeQ());
const aomeA = () => get<{ items: AomeItem[]; scope: OpScope }>('/aome', { all: st().widen, tenant: tenantQ() });
const handedA = () => get<{ handed: HandedRow[]; awaiting: ReturnType<typeof awaitingApproval>; scope: OpScope }>('/handed', { all: st().widen, tenant: tenantQ() });
const outcomesA = () => get<ReturnType<typeof outcomesToConfirm>>('/outcomes', { tenant: tenantQ() });
const inboxA = () => get<InboxAnswer>('/inbox', { tenant: tenantQ() });

// ---------------------------------------------------------------- layout and view settings

export const SECTIONS = ['kpis', 'exceptions', 'aome', 'handed', 'approvals', 'outcomes', 'charts', 'actions', 'signals', 'value', 'health'];
export const ccLayout = (): CcLayout => layoutA().layout ?? { sub: '', kpis: [] };
/** Does the layout have this section, and may the account open it? */
export const ccSecOK = (_L: CcLayout, k: string): boolean => layoutA().sections.includes(k);
/** The section shown for #/command/<a> (falls back to key figures, like the demo's ccSec). */
export const ccSection = (a: string | null): string => (a && layoutA().sections.includes(a) ? a : 'kpis');
export const ccKeys = (_L: CcLayout): string[] => layoutA().keys;
export const ccSecLabel = (k: string): string =>
  (ref<{ id: string; kids: string[][] }[]>('NAV').find((x) => x.id === 'command')?.kids.find((x) => x[0] === k) ?? [k, 'Key figures'])[1];
export const ccSecDesc = (k: string): string => ref<Record<string, string>>('CC_DESC')[k] ?? '';

export const ccFilters = (): CcFilters => st().cc;
export function setCcFilters(patch: Partial<CcFilters>): void {
  st().cc = { ...st().cc, ...patch };
  bump();
}
/** "Clear all": every filter, the search and the tenant menu. */
export function clearCcFilters(): void {
  const clear = { site: '', cls: '', route: '', stage: '', reason: '', due: '', view: '', q: '' };
  st().cc = { ...st().cc, ...clear };
  setView({ tenant: 'All' }); // bumps
}
/** The demo's ccPick: "stage:approval", "route:resale", "reason:Missing evidence", "due:d5" toggle a filter. */
export function ccPick(arg: string): void {
  const i = arg.indexOf(':'), k = arg.slice(0, i), v = arg.slice(i + 1), f = { ...st().cc };
  if (k === 'stage') f.stage = v === '' || f.stage === v ? '' : v;
  else if (k === 'route') f.route = f.route === v ? '' : v;
  else if (k === 'reason') f.reason = f.reason === v ? '' : v;
  else if (k === 'due') f.due = f.due === v ? '' : v;
  st().cc = f;
  bump();
}

export const ccMode = (): 'senior' | 'operational' => (view().ccMode === 'senior' ? 'senior' : 'operational');
export function setCcMode(v: 'senior' | 'operational'): void {
  setView({ ccMode: v });
}
export const ccOps = (): boolean => st().ops;
export function setCcOps(v: boolean): void {
  st().ops = v;
  bump();
}

/** Operational scope: Planner and Engineer default to their home site and can widen it; a Warehouse Manager is locked. */
export function opScopeInfo(): { home: string; scope: string; locked: boolean } {
  return aomeA().scope;
}
export function toggleOpScope(): void {
  st().widen = !st().widen;
  bump();
}

/** "07 Oct 2026, 09:30" (UTC), or the date and time in the region's time zone (the demo's ccClockText). */
export const clockText = (): string => {
  const d = asOfNow();
  return view().rg.tz === 'UTC' ? fmtDY(ref<string>('AS_OF')) + ', ' + d.toISOString().slice(11, 16) : rgTime(d);
};
/** May the account open this route ("integration/map", "product/RT-1048")? */
export const rbPath = (p: string): boolean => {
  const [page, a, b] = p.split('/');
  return canRoute({ page, a: a ?? null, b: b ?? null }) === true;
};
export const kfmt = kfmtLocal;
export const tFmt = (n: number): string => (n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(Math.round(n)));
export const asModel = (c: CcCase): string => {
  const e = ref<{ cls: string; m: string }[]>('EQUIP').find((x) => x.cls === c.cls);
  return e ? e.m.replace(/s$/, '') : c.product;
};
/** Icon key of the thumbnail for an asset class (the demo's thumb()). */
export const clsIcon = (cls: string): string => ref<Record<string, string>>('CLS_ICON')[cls] ?? 'batch';

// ---------------------------------------------------------------- scope and metrics

export const ccScope = (): CcScope => SCOPE;
export const ccRows = (): CcRows => ROWS;
export const ccMetrics = (_rows: CcRows): CcMetrics => kpisA().metrics;
/** Sizes of the scope: assets in it, those still needing a person, and their value at risk. */
export function scopeTotals(_sc: CcScope): { all: number; act: number; risk: number } {
  const c = chartsA(); // every asset is in one lifecycle stage; every open one in one due window
  return { all: sum(c.stages.map((x) => x.v)), act: sum(c.due.map((x) => x.v)), risk: sum(c.var.map((x) => x.v)) };
}

export const visCaseCount = (): number => kpisA().counts.cases;
export const visRowCount = (): number => kpisA().counts.rows;
export const sourceCount = (): number => kpisA().counts.sources;
export const workflowCount = (): number => kpisA().counts.workflows;

// ---------------------------------------------------------------- key figures (the demo's ccKpiSet)

export interface KpiTile {
  key: string; cls: string; icon: string; label: string; val: string; sub: string; delta: Delta | null; spark: number[] | null;
  /** what selecting the tile does: filter (ccPick arg), scroll to a section, open a route, or clear the filters */
  act: { kind: 'pick'; arg: string } | { kind: 'section'; sec: string } | { kind: 'go'; to: string } | { kind: 'clear' };
  tip: string;
}

/** The layout's tiles: the server's, for the current filters and view. */
export const kpiTiles = (_keys: string[], _sc: CcScope, _rows: CcRows): KpiTile[] => kpisA().tiles;

// ---------------------------------------------------------------- charts and panels

export interface Slice { k: string; label: string; v: number; color: string }
export const CC_STAGES = (): [string, string, string][] => ref('CC_STAGES');
export const stageSlices = (_sc: CcScope): Slice[] => chartsA().stages;
export const dueSlices = (_sc: CcScope): Slice[] => chartsA().due;
export interface RouteBar { id: string; label: string; v: number; net: number; color: string }
export const routeBars = (_sc: CcScope): RouteBar[] => chartsA().routes;
export const varReasons = (_sc: CcScope): VarRow[] => chartsA().var;
export const monthLabel = (mi: number): string => ref<string[]>('MONTHS')[mi];
/** Predicted and actual net recovery by month on reconciled decisions (the value realisation combo chart), for the
 *  filters' time horizon, which is what the page passes as `months`. */
export const comboData = (_rows: CcRows, _months: number): { mi: number; p: number; a: number; y: number }[] => chartsA().combo;

export interface Signal { t: string; n: string; note: string; lvl: string; act: string; ic: string }
/** Already without the routes the account cannot open; `ic` is the icon key. */
export const signals = (_sc: CcScope): Signal[] => chartsA().signals;
export const capacity = (_sc: CcScope): CapRow[] => chartsA().capacity;
export function healthStrip(): { pct: number; live: number; stale: number; manual: number; unavailable: number } {
  return kpisA().health;
}
export const insights = (_sc: CcScope): [string, string][] => kpisA().insights;

// ---------------------------------------------------------------- filters

export interface FilterOptions {
  tenants: { value: string; label: string; disabled?: boolean }[];
  sites: string[]; classes: [string, string][]; routes: [string, string, string][];
}
export function filterOptions(): FilterOptions {
  const scoped = !!session()?.tenant_scoped;
  const al = session()?.tenants ?? [];
  const tenants: FilterOptions['tenants'] = [{ value: 'All', label: scoped ? 'All my tenants' : 'All tenants' }];
  ref<string[]>('TENANTS').forEach((t) => tenants.push(al.includes(t) ? { value: t, label: t } : { value: t, label: t + ' · locked', disabled: true }));
  return {
    tenants,
    sites: ref<string[]>('FACILITIES'),
    classes: Object.entries(ref<Record<string, { label: string }>>('CLASSES')).map(([k, v]) => [k, v.label]),
    routes: ref<{ id: string; name: string; short: string }[]>('ROUTES').map((x) => [x.id, x.name, x.short]),
  };
}
export const tenantAllowed = (t: string): boolean => t === 'All' || !!session()?.tenants.includes(t);
export const classLabel = (k: string): string => ref<Record<string, { label: string }>>('CLASSES')[k]?.label ?? k;
export const routeShort = (id: string): string => ref<{ id: string; short: string }[]>('ROUTES').find((r) => r.id === id)?.short ?? id;

// ---------------------------------------------------------------- actions to prioritise (the ranked table)

export interface OppRow {
  c: CcCase; trigger: string; action: string; cons: string; btn: string; conf: number | null; deadline: string; left: number;
}
export const oppRows = (_sc: CcScope): CcCase[] => actionsA().rows.map((r) => r.case);
export function oppRow(c: CcCase, _sc: CcScope): OppRow {
  const { case: _c, ...o } = actionsA().rows.find((r) => r.case.id === c.id)!; // eslint-disable-line @typescript-eslint/no-unused-vars
  return { c, ...o };
}

// ---------------------------------------------------------------- exceptions and Notify

export interface ExRow {
  id: string; base: string; wh: string; title: string; value: number; count: number; sev: 'High' | 'Medium' | 'Low'; trend: string; go?: string;
  items: { id: string; model: string; v: number }[];
  note: { status: string; ackBy?: string; toLabel: string } | null;
  /** the account it goes to by default (sent by the API) */
  owner?: string;
}
export const exRows = (_sc: CcScope): ExRow[] => exA().rows;
/** The account the exception is routed to by default (the demo's exOwner). */
export const exOwner = (x: ExRow): string => x.owner ?? 'approver';
/** The senior view's read-only queue: decisions awaiting approval in the scope, highest predicted net first. */
export const opsAwaiting = (_sc: CcScope): { id: string; plan: string | null; net: number }[] => exA().awaiting;
export const notifyRecipients = (): Account[] => accounts().filter((a) => a.role !== 'Executive');
export function sendNotification(x: ExRow, to: string, sev: string, msg: string): Promise<ActionResult<{ id: string; to: string }>> {
  return invoke<{ id: string; to: string }>('notify.send', { ex_id: x.id, title: x.wh + ' · ' + x.title, to, sev, msg, ids: x.items.map((i) => i.id).slice(0, 40) });
}
export const acknowledge = (id: string): Promise<ActionResult> => invoke('notify.acknowledge', { id });

// ---------------------------------------------------------------- Actions on me, handed off, outcomes

export interface AomeItem { t: string; d: string; btn: string; act?: string; arg?: string; go?: string }
export const aomeItems = (): AomeItem[] => aomeA().items;

export interface HandedRow { id: string; label: string; sys: string; ref: string | null; age: number; over: boolean }
export const handedRows = (): HandedRow[] => handedA().handed;
export function awaitingApproval(): { decider: string; rows: { id: string; location: string; plan: string; submitted: boolean }[] } {
  return handedA().awaiting;
}
export function outcomesToConfirm(): { rows: { id: string; product: string; assetId: string; plan: string; net: number | null }[]; done: number } {
  return outcomesA();
}

// ---------------------------------------------------------------- Approvals inbox

export interface AccessRequest {
  id: string; kind: 'tenant' | 'mcp'; status: 'pending' | 'approved' | 'declined'; by: string; at: string; tenant?: string; reason?: string;
  decidedBy?: string; decidedAt?: string; note?: string;
  server?: { name: string; owner: string; purpose: string; tools: string[]; access: 'read' | 'write'; data: string };
  kindLabel: string; canDecide: boolean;
}
export const inboxRequests = (): AccessRequest[] => inboxA().requests;
/** What Admin delegated to the Approver (null for Admin, who sees every scope). */
export const inboxScope = (): string[] | null => inboxA().scope;
export const decisionsAwaiting = (): number => inboxA().decisions_awaiting;
export const decideRequest = (id: string, decision: 'approve' | 'decline', note: string): Promise<ActionResult<{ status: string }>> =>
  invoke<{ status: string }>('access.decideRequest', { id, decision, note });
export const requestById = (id: string): AccessRequest | undefined => inboxA().requests.find((x) => x.id === id);

/** Submitted decisions as approval cards, by value then deadline, each with its pre-approval check (afApprovalQueue)
 *  and the instructions it would send ("<step> → <system>"). */
export interface ApprovalCard { id: string; plan: string; net: number; model: string; owner: string; timing: string; submittedBy: string; risks: string[]; steps: string[] }
export const approvalCards = (): ApprovalCard[] => inboxA().cards.map(({ kinds, steps, ...c }) => ({ ...c, steps: steps ?? kinds }));
export const approvalLimit = (): number => inboxA().limit ?? Infinity;

// ---------------------------------------------------------------- integration health (Developer and Admin)

export interface HealthDetail {
  ok: number; warn: number; bad: number; run: number; pct: number;
  hours: { ok: number; warn: number; bad: number }[];
  exceptions: { src: string; obj: string; issue: string; sev: 'High' | 'Medium' | 'Low'; st: string }[];
  exceptionCount: number;
  events: { id: string; ts: number | string; dest: string; type: string; ack: string; kind: string }[];
}
export const healthDetail = (): HealthDetail => get<HealthDetail>('/health');
