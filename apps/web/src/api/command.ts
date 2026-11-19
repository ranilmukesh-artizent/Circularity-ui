/**
 * Command Center (#/command/<section>): typed reads over the demo's Command Center helpers (ccScope, ccExRows,
 * aomeItems, handedRows …) and the few view settings the demo keeps on S (S.cc filters, S.ccMode, S.ccOps, S.opScope).
 * Every figure is computed by the engine exactly as index.html does; pages only draw.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import { bump, engine } from '../engine/engine';
import { invoke } from './actions';
import type { Account, ActionResult } from './types';

type Any = any;
const g = () => engine();
const fn = <T = Any>(name: string): T => g()<T>(name);
const S = (): Any => g()('S');
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

// ---------------------------------------------------------------- layout and view settings

export const SECTIONS = ['kpis', 'exceptions', 'aome', 'handed', 'approvals', 'outcomes', 'charts', 'actions', 'signals', 'value', 'health'];
export const ccLayout = (): CcLayout => fn<() => CcLayout>('ccLayout')();
export const ccSecOK = (L: CcLayout, k: string): boolean => fn<(L: CcLayout, k: string) => boolean>('ccSecOK')(L, k);
/** The section shown for #/command/<a> (falls back to key figures, like the demo's ccSec). */
export const ccSection = (a: string | null): string => fn<(L: CcLayout, r: { a: string | null }) => string>('ccSec')(ccLayout(), { a });
export const ccKeys = (L: CcLayout): string[] => L.kpis.filter((x) => fn<Any>('FEAT').uplift || x !== 'uplift');
export const ccSecLabel = (k: string): string =>
  (fn<{ id: string; kids: string[][] }[]>('NAV').find((x) => x.id === 'command')?.kids.find((x) => x[0] === k) ?? [k, 'Key figures'])[1];
export const ccSecDesc = (k: string): string => fn<Record<string, string>>('CC_DESC')[k] ?? '';

export const ccFilters = (): CcFilters => S().cc;
export function setCcFilters(patch: Partial<CcFilters>): void {
  Object.assign(S().cc, patch);
  bump();
}
/** "Clear all": every filter, the search and the tenant menu. */
export function clearCcFilters(): void {
  Object.assign(S().cc, { site: '', cls: '', route: '', stage: '', reason: '', due: '', view: '', q: '' });
  S().tenant = 'All';
  bump();
}
/** The demo's ccPick: "stage:approval", "route:resale", "reason:Missing evidence", "due:d5" toggle a filter. */
export function ccPick(arg: string): void {
  const i = arg.indexOf(':'), k = arg.slice(0, i), v = arg.slice(i + 1), f = S().cc;
  if (k === 'stage') f.stage = v === '' || f.stage === v ? '' : v;
  else if (k === 'route') f.route = f.route === v ? '' : v;
  else if (k === 'reason') f.reason = f.reason === v ? '' : v;
  else if (k === 'due') f.due = f.due === v ? '' : v;
  bump();
}

export const ccMode = (): 'senior' | 'operational' => (S().ccMode === 'senior' ? 'senior' : 'operational');
export function setCcMode(v: 'senior' | 'operational'): void {
  S().ccMode = v;
  fn<() => void>('ccSave')();
  bump();
}
export const ccOps = (): boolean => !!S().ccOps;
export function setCcOps(v: boolean): void {
  S().ccOps = v;
  fn<() => void>('ccSave')();
  bump();
}

/** Operational scope: Planner and Engineer default to their home site and can widen it; a Warehouse Manager is locked. */
export function opScopeInfo(): { home: string; scope: string; locked: boolean } {
  return { home: fn<() => string>('opHome')(), scope: fn<() => string>('opScope')(), locked: !!S().acct?.warehouse };
}
export function toggleOpScope(): void {
  const s = S();
  s.opScope = fn<() => string>('opScope')() ? '' : fn<() => string>('opHome')();
  bump();
}

export const clockText = (): string => fn<() => string>('ccClockText')();
/** May the account open this route ("integration/map", "product/RT-1048")? */
export const rbPath = (p: string): boolean => fn<(p: string) => boolean>('rbPath')(p);
export const kfmt = (n: number): string => fn<(n: number) => string>('kfmt')(n);
export const tFmt = (n: number): string => fn<(n: number) => string>('tFmt')(n);
export const asModel = (c: CcCase): string => fn<(c: CcCase) => string>('asModel')(c);
/** Icon key of the thumbnail for an asset class (the demo's thumb()). */
export const clsIcon = (cls: string): string => fn<Record<string, string>>('CLS_ICON')[cls] ?? 'batch';

// ---------------------------------------------------------------- scope and metrics

export const ccScope = (): CcScope => fn<() => CcScope>('ccScope')();
export const ccRows = (): CcRows => fn<() => CcRows>('ccRows')();
export function ccMetrics(rows: CcRows): CcMetrics {
  const m = fn<(r: CcRows) => Any>('metrics')(rows);
  return {
    act: m.act, base: m.base, uplift: m.uplift, avoided: m.avoided, days: m.days || null, rcCount: m.rc.length,
    p50: sum(m.rc.map((r: Any) => r.p50)), co2e: sum(m.rc.map((r: Any) => r.co2e)),
  };
}
const series = (f: (r: Any) => number): number[] => fn<Any>('ccSeries')(f, fn<() => Any[]>('visRows')());
const delta = (s: number[]): Delta | null => fn<Any>('ccDelta')(s);
const ccNet = (c: CcCase): number => (c.recommendation ? c.recommendation.net : 0);

export const visCaseCount = (): number => fn<() => unknown[]>('visCases')().length;
export const visRowCount = (): number => fn<() => unknown[]>('visRows')().length;
export const sourceCount = (): number => fn<unknown[]>('SOURCES').length;
export const workflowCount = (): number => S().wf?.list.length ?? 0;

// ---------------------------------------------------------------- key figures (the demo's ccKpiSet)

export interface KpiTile {
  key: string; cls: string; icon: string; label: string; val: string; sub: string; delta: Delta | null; spark: number[] | null;
  /** what selecting the tile does: filter (ccPick arg), scroll to a section, open a route, or clear the filters */
  act: { kind: 'pick'; arg: string } | { kind: 'section'; sec: string } | { kind: 'go'; to: string } | { kind: 'clear' };
  tip: string;
}

export function kpiTiles(keys: string[], sc: CcScope, rows: CcRows): KpiTile[] {
  const m = fn<(r: CcRows) => Any>('metrics')(rows), s = S(), acct = s.acct as Account;
  const st = (x: string) => sc.all.filter((c) => c._st === x), ap = st('approval');
  const open = sc.all.filter((c) => c._st === 'approval' || c._st === 'reeval'), pot = sum(open.map(ccNet)), vr = sum(sc.all.map((c) => c._var));
  const sCnt = () => series(() => 1), sPred = () => series((r) => Math.max(0, r.p50)),
    sUp = () => series((r) => (r.status === 'reconciled' ? r.actual - r.baseline : 0)), sAct = () => series((r) => (r.status === 'reconciled' ? r.actual : 0));
  const cl = ap.filter((c) => c._left < 5).length, gaps = sc.all.filter((c) => c._st === 'need' || c._st === 'await_insp').length, yp = sum(m.rc.map((r: Any) => r.p50));
  const fmtN = fn<(n: number) => string>('fmtN');
  const pick = (arg: string) => ({ kind: 'pick' as const, arg }), go = (to: string) => ({ kind: 'go' as const, to }), sec = (x: string) => ({ kind: 'section' as const, sec: x });
  const SCROLL: Record<string, string> = { ccVar: 'kpis', ccApprovals: 'approvals', ccAome: 'aome', ccHanded: 'handed', ccSignals: 'signals' };
  const k = (key: string, cls: string, icon: string, label: string, val: string, sub: string, d: Delta | null, sp: number[] | null, act: KpiTile['act'], tip: string): KpiTile =>
    ({ key, cls, icon, label, val, sub, delta: d, spark: sp, act, tip });
  const riskPct = pot ? Math.round(vr / Math.max(1, pot + sum(sc.all.filter((c) => c._st === 'need' || c._st === 'await_insp' || c._st === 'noroute').map((c) => c._val))) * 100) : 0;
  const D: Record<string, () => KpiTile> = {
    scope: () => k('scope', '', 'batch', 'Assets in scope', fmtN(sc.all.length), sum(sc.all.map((c) => c.qty)).toLocaleString() + ' units · vs prior month', delta(sCnt()), sCnt(), { kind: 'clear' }, 'Returned assets matching the filters. The change compares closed decisions this month with last month.'),
    awaiting: () => k('awaiting', 'y', 'check', 'Awaiting approval', fmtN(ap.length), kfmt(sum(ap.map(ccNet))) + ' predicted net · with an Approver', null, null, pick('stage:approval'), 'Decisions you prepared that now wait for an Approver. Select to filter the table.'),
    awaitVal: () => k('awaitVal', 'ok', 'check', 'Awaiting approval', kfmt(sum(ap.map(ccNet))), ap.length + ' decisions · predicted net', null, null, pick('stage:approval'), 'Predicted net recovery of decisions waiting for your approval. Select to filter the table.'),
    gaps: () => k('gaps', 'bad', 'audit', 'Evidence gaps', fmtN(gaps), 'assets cannot be routed yet', null, null, pick('stage:need'), 'Assets waiting for inspection or missing evidence. They cannot get a recommendation until it arrives.'),
    closing: () => k('closing', cl ? 'bad' : 'ok', 'flag', 'Closing within 5 days', fmtN(cl), 'decision windows · act first', null, null, pick('due:d5'), 'Decisions awaiting approval whose window closes in under 5 days.'),
    potential: () => k('potential', 'ok', 'analytics', 'Potential recovery value', kfmt(pot), open.length + ' decisions open · predicted net', delta(sPred()), sPred(), pick('stage:approval'), 'Predicted net recovery of decisions that still need a person: awaiting approval plus re-evaluation. Select to filter the table.'),
    risk: () => k('risk', 'bad', 'flag', 'Value at risk', kfmt(vr), riskPct + '% of open value if no action', null, null, sec(SCROLL.ccVar), 'Predicted recovery value on open returns that would be lost over the next 30 days if nobody acts: missing evidence, condition getting worse, delayed approval, falling market prices or capacity limits. Select to see the breakdown by reason.'),
    inbox: () => { const n = fn<() => unknown[]>('inboxReqs')().length; return k('inbox', n ? 'y' : 'ok', 'access', 'Requests waiting', fmtN(n), 'tenant access and MCP proposals', null, null, sec('approvals'), 'Requests in the scopes you can decide. Select to open the Approvals inbox.'); },
    inspq: () => k('inspq', '', 'audit', 'Inspection queue', fmtN(st('await_insp').length), 'assets awaiting inspection', null, null, pick('stage:await_insp'), 'Returned assets with no inspection yet. Select to filter the table.'),
    gatefail: () => { const n = sc.all.filter((c) => c.blocked).length; return k('gatefail', n ? 'bad' : 'ok', 'flag', 'Failed gates', fmtN(n), 'exceptions waiting for evidence', null, null, pick('stage:need'), 'Cases where an eligibility gate failed or evidence is missing. No route is approvable until it passes.'); },
    graded: () => { const gr = sc.all.filter((c) => c.grade), ab = gr.filter((c) => c.grade === 'A' || c.grade === 'B').length; return k('graded', 'ok', 'check', 'Graded A or B', (gr.length ? Math.round(ab / gr.length * 100) : 0) + '%', ab + ' of ' + gr.length + ' graded assets', null, null, go('product/received'), 'Share of inspected assets in the top two condition grades.'); },
    parts: () => { const asParts = fn<Any>('asParts'), ah = fn<Any>('assetHealth'); const n = sc.all.filter((c) => asParts(c, ah(c)).some((p: Any) => p.st === 'Backorder')).length; return k('parts', n ? 'bad' : 'ok', 'pump', 'Parts on backorder', fmtN(n), 'assets with a part on backorder', null, null, go('product/received'), 'Assets with at least one component on backorder.'); },
    net: () => k('net', 'ok', 'analytics', 'Net recovery', kfmt(m.act), m.rc.length + ' reconciled decisions · ' + s.cc.months + ' months', delta(sAct()), sAct(), go('analytics/waterfall'), 'Actual net recovery on reconciled decisions in the period. Same as Analytics when filters match.'),
    uplift: () => k('uplift', 'y', 'trend', 'Uplift vs baseline', '+' + kfmt(m.uplift), 'closed decisions · ' + (m.base ? '+' + ((m.act / m.base - 1) * 100).toFixed(0) + '%' : '—') + ' vs sell-or-scrap', delta(sUp()), sUp(), go('analytics'), 'Additional net recovery on reconciled decisions compared with the sell-or-scrap baseline. Same number as Analytics.'),
    yield: () => k('yield', '', 'check', 'Recovery yield', (yp ? Math.round(m.act / yp * 100) : 0) + '%', 'actual ÷ predicted on reconciled', null, null, go('analytics/predicted'), 'Actual net recovery divided by the predicted P50 on the same reconciled decisions.'),
    avoided: () => k('avoided', 'ok', 'export', 'Avoided spend', kfmt(m.avoided), 'ERP-confirmed purchases not made', null, null, go('analytics'), 'Purchases avoided by redeploying assets or using recovered parts, confirmed in ERP.'),
    co2m: () => k('co2m', 'ok', 'leaf', 'CO₂e avoided', (sum(m.rc.map((r: Any) => r.co2e)) / 1000).toFixed(0) + ' t', 'estimated on reconciled decisions', null, null, go('analytics/sustain'), 'Estimated embodied carbon avoided on reconciled decisions. Measured values are on Analytics.'),
    ihealth: () => { const t = fn<() => Any>('hhTotals')(); return k('ihealth', t.pct >= 95 ? 'ok' : 'bad', 'integration', 'Integration health', t.pct.toFixed(1) + '%', 'successful syncs and events · 24 h', null, null, go('integration/map'), 'Share of syncs and events in the last 24 hours that succeeded.'); },
    srcattn: () => { const l = fn<Any[]>('SOURCES').filter((x) => x.status === 'stale' || x.status === 'unavailable'); return k('srcattn', l.length ? 'bad' : 'ok', 'flag', 'Sources needing attention', fmtN(l.length), l.map((x) => x.name).join(', ') || 'all sources fresh', null, null, go('integration/map'), 'Sources that are stale or not connected.'); },
    wffail: () => { fn<() => void>('wfInit')(); const wfStat = fn<Any>('wfStat'); const n = s.wf.list.filter((w: Any) => wfStat(w) === 'failing').length; return k('wffail', n ? 'bad' : 'ok', 'play', 'Failing workflows', fmtN(n), 'published, last run failed', null, null, go('integration/studio'), 'Published workflows whose last run failed.'); },
    conf: () => { const n = fn<Any[]>('CONFLICTS').filter((c) => c.status === 'open').length; return k('conf', n ? 'bad' : 'ok', 'integration', 'Open conflicts', fmtN(n), 'systems that disagree', null, null, go('integration/conflicts'), 'Records where two systems disagree. Dependent routes stay held until resolved.'); },
    aome: () => { const n = aomeItems().length; return k('aome', n ? 'y' : 'ok', 'flag', 'Actions on me', fmtN(n), 'items whose next step is yours', null, null, sec('aome'), 'Everything waiting on you: notifications, requests, cases to submit, approve, inspect or confirm. Select to open Actions on me.'); },
    whcases: () => k('whcases', '', 'batch', 'Assets at ' + (acct.warehouse || 'your site'), fmtN(sc.all.length), sum(sc.all.map((c) => c.qty)).toLocaleString() + ' units · current location', null, null, go('product/received'), 'Returned assets whose current location is your warehouse.'),
    handed: () => { const n = sc.all.filter((c) => c.stage === 'approved' || c.stage === 'executing').length; return k('handed', '', 'integration', 'Handed off', fmtN(n), 'with enterprise systems · awaiting outcome', null, null, sec('handed'), 'Approved instructions sent to ERP, EAM or WMS that have not reported an outcome yet.'); },
    capwh: () => { const w = acct.warehouse || 'Warehouse 1', cap = fn<Record<string, number>>('CC_CAP')[w], p = (sc.util[w] || 0) / cap; return k('capwh', p >= 0.85 ? 'bad' : 'ok', 'flag', 'Capacity used', Math.round(p * 100) + '%', (sc.util[w] || 0) + ' of ' + cap + ' planned slots', null, null, sec('signals'), 'Utilisation of your warehouse against its configured planning capacity.'); },
    props: () => { const l = fn<() => Any[]>('myReqs')().filter((r) => r.kind === 'mcp'); return k('props', 'y', 'mcp', 'My MCP proposals', fmtN(l.filter((r) => r.status === 'pending').length) + ' pending', l.filter((r) => r.status === 'approved').length + ' approved · ' + l.filter((r) => r.status === 'declined').length + ' declined', null, null, go('mcp/proposals'), 'Servers you proposed and their review status.'); },
  };
  return keys.map((x) => D[x]());
}

// ---------------------------------------------------------------- charts and panels

export interface Slice { k: string; label: string; v: number; color: string }
export const CC_STAGES = (): [string, string, string][] => fn('CC_STAGES');
export function stageSlices(sc: CcScope): Slice[] {
  return CC_STAGES().map(([k, label, color]) => ({ k: 'stage:' + k, label, v: sc.all.filter((x) => x._st === k).length, color }));
}
export function dueSlices(sc: CcScope): Slice[] {
  return fn<[string, string, string][]>('CC_DUE').map(([k, label, color]) => ({ k: 'due:' + k, label, v: sc.act.filter((x) => x._due === k).length, color }));
}
export interface RouteBar { id: string; label: string; v: number; net: number; color: string }
export function routeBars(sc: CcScope): RouteBar[] {
  return fn<Any[]>('ROUTES').map((r) => {
    const a = sc.all.filter((c) => c.recommendation && c.recommendation.id === r.id);
    return { id: r.id, label: r.short, v: sum(a.map((c) => c.qty)), net: sum(a.map(ccNet)), color: r.color };
  }).filter((x) => x.v > 0);
}
const VAR_COL: Record<string, string> = { 'Delayed approval': 'var(--bad)', 'Condition deterioration': '#D9651E', 'Missing evidence': '#D4A800', 'Market price decline': 'var(--chart4)', 'Capacity constraints': 'var(--chart5)' };
const VAR_TIP: Record<string, string> = {
  'Delayed approval': 'Decisions whose window is closing. The offer or demand can lapse.',
  'Condition deterioration': 'Monthly value decay of the asset class while it waits.',
  'Missing evidence': 'Value of assets that cannot be routed yet. Estimated from similar closed decisions.',
  'Market price decline': 'Resale recommendations priced from stale market comparables.',
  'Capacity constraints': 'Repair-centre load is above 75%, so prep may slip.',
};
export function varReasons(sc: CcScope): { reason: string; v: number; pct: number; w: number; color: string; tip: string }[] {
  const reasons = fn<string[]>('CC_REASONS'), by: Record<string, number> = {};
  reasons.forEach((r) => (by[r] = 0));
  sc.all.forEach((c) => Object.keys(c._risk).forEach((k) => (by[k] += c._risk[k])));
  const tot = sum(Object.values(by)) || 1, mx = Math.max(1, ...Object.values(by));
  return reasons.map((r) => ({ reason: r, v: by[r], pct: Math.round(by[r] / tot * 100), w: by[r] / mx * 100, color: VAR_COL[r], tip: VAR_TIP[r] }));
}
export const monthLabel = (mi: number): string => fn<string[]>('MONTHS')[mi];
/** Predicted and actual net recovery by month on reconciled decisions (the value realisation combo chart). */
export function comboData(rows: CcRows, months: number): { mi: number; p: number; a: number; y: number }[] {
  const rc = (rows as unknown as Any[]).filter((r) => r.status === 'reconciled'), out = [];
  for (let mi = 12 - months; mi < 12; mi++) {
    const p = sum(rc.filter((r) => r.mi === mi).map((r) => r.p50)), a = sum(rc.filter((r) => r.mi === mi).map((r) => r.actual));
    out.push({ mi, p, a, y: p ? a / p * 100 : 0 });
  }
  return out;
}

export interface Signal { t: string; n: string; note: string; lvl: string; act: string; ic: string }
const ICON_KEYS = ['flag', 'audit', 'trend', 'refresh', 'pump', 'integration'];
export function signals(sc: CcScope): Signal[] {
  const ICON = fn<Record<string, string>>('ICON');
  return fn<(sc: CcScope) => Any[]>('ccSignals')(sc)
    .filter((x) => x.act.indexOf('go:') !== 0 || rbPath(x.act.slice(3)))
    .map((x) => ({ ...x, ic: ICON_KEYS.find((k) => ICON[k] === x.ic) ?? 'flag' }));
}
export function capacity(sc: CcScope): { k: string; label: string; u: number; cap: number; p: number; color: string; msg: string }[] {
  const CAP = fn<Record<string, number>>('CC_CAP'), LBL = fn<Record<string, string>>('CAP_LBL');
  return Object.keys(CAP).map((k) => {
    const u = sc.util[k] || 0, p = u / CAP[k];
    return { k, label: LBL[k] || k, u, cap: CAP[k], p, color: p >= 0.9 ? 'var(--bad)' : p >= 0.75 ? '#D4A800' : 'var(--ok)', msg: p >= 0.9 ? 'Over limit risk' : p >= 0.75 ? 'Tight' : 'Within limit' };
  });
}
export function healthStrip(): { pct: number; live: number; stale: number; manual: number; unavailable: number } {
  const t = fn<() => Any>('hhTotals')(), st: Record<string, number> = { live: 0, stale: 0, manual: 0, unavailable: 0 };
  fn<Any[]>('SOURCES').forEach((x) => st[x.status]++);
  return { pct: t.pct, live: st.live, stale: st.stale, manual: st.manual, unavailable: st.unavailable };
}
export function insights(sc: CcScope): [string, string][] {
  const o: [string, string][] = [], cl = sc.all.filter((c) => c._st === 'approval' && c._left < 5).length, ap = sc.all.filter((c) => c._st === 'approval').length;
  if (ap) o.push(['stage:approval', ap + ' decisions await approval' + (cl ? ', ' + cl + ' close within 5 days' : '')]);
  const by: Record<string, number> = {};
  sc.all.forEach((c) => Object.keys(c._risk).forEach((k) => (by[k] = (by[k] || 0) + c._risk[k])));
  const tot = sum(Object.values(by)), top = Object.entries(by).sort((a, b) => b[1] - a[1])[0];
  if (top) o.push(['reason:' + top[0], kfmt(tot) + ' at risk, mostly ' + top[0].toLowerCase() + ' (' + Math.round(top[1] / tot * 100) + '%)']);
  if ((fn<(id: string) => Any>('SRC')('mkt') || {}).status === 'stale') o.push(['route:resale', 'Market feed is stale, so resale prices carry a warning']);
  const ne = sc.all.filter((c) => c._st === 'need' || c._st === 'await_insp').length;
  if (ne) o.push(['stage:need', ne + ' assets cannot be routed until evidence arrives']);
  return o.slice(0, 4);
}

// ---------------------------------------------------------------- filters

export interface FilterOptions {
  tenants: { value: string; label: string; disabled?: boolean }[];
  sites: string[]; classes: [string, string][]; routes: [string, string, string][];
}
export function filterOptions(): FilterOptions {
  const P = fn<() => Any>('pol')(), sc = P && P.tenantScoped, al = fn<() => string[]>('allowedTenants')();
  const tenants: FilterOptions['tenants'] = [{ value: 'All', label: sc ? 'All my tenants' : 'All tenants' }];
  fn<string[]>('TENANTS').forEach((t) => tenants.push(al.includes(t) ? { value: t, label: t } : { value: t, label: t + ' · locked', disabled: true }));
  return {
    tenants,
    sites: fn<string[]>('FACILITIES'),
    classes: Object.entries(fn<Record<string, { label: string }>>('CLASSES')).map(([k, v]) => [k, v.label]),
    routes: fn<Any[]>('ROUTES').map((r) => [r.id, r.name, r.short]),
  };
}
export const tenantAllowed = (t: string): boolean => t === 'All' || fn<(t: string) => boolean>('tenantOK')(t);
export const classLabel = (k: string): string => fn<Record<string, { label: string }>>('CLASSES')[k]?.label ?? k;
export const routeShort = (id: string): string => fn<(r: string) => { short: string }>('rid')(id).short;

// ---------------------------------------------------------------- actions to prioritise (the ranked table)

export interface OppRow {
  c: CcCase; trigger: string; action: string; cons: string; btn: string; conf: number | null; deadline: string; left: number;
}
export function oppRows(sc: CcScope): CcCase[] {
  const f = S().cc, q = String(f.q).trim().toLowerCase();
  let l = f.stage && ['exec', 'approved'].includes(f.stage) ? sc.all.slice().sort((a, b) => b._score - a._score) : sc.act;
  l = l.filter((c) => (!f.stage || c._st === f.stage) && (!f.due || c._due === f.due) && (!f.reason || c._risk[f.reason] > 0)
    && (!q || (c.id + ' ' + c.assetId + ' ' + c.product + ' ' + c.owner).toLowerCase().includes(q)));
  return l;
}
export function oppRow(c: CcCase, sc: CcScope): OppRow {
  const rid = fn<(r: string) => { name: string }>('rid'), CAP = fn<Record<string, number>>('CC_CAP');
  const r = c.recommendation;
  const trigger = c._st === 'approval' ? 'Recommendation awaiting approval' : c._st === 'reeval' ? c.reevalReason || 'Conditions changed'
    : c._st === 'need' ? 'Evidence gap: ' + (c.blocked ? c.blocked.gateName : 'condition') : c._st === 'await_insp' ? 'Awaiting inspection'
      : c._st === 'noroute' ? 'No route passed the gates' : 'In motion';
  const action = r ? r.plan || rid(r.id).name : c.blocked ? c.blocked.action : 'Request inspection';
  const cons = c.blocked ? c.blocked.owner + ' input needed' : r && r.demandStatus === 'forecast' ? 'Forecast demand only'
    : c.location === 'Repair centre' && sc.util['Repair centre'] / CAP['Repair centre'] >= 0.75 ? 'Repair capacity' : 'None';
  const btn = c._st === 'approval' ? 'Review' : c._st === 'reeval' ? 'Re-evaluate' : c._st === 'exec' || c._st === 'approved' ? 'Track' : 'Investigate';
  const conf = r ? Math.max(30, Math.min(97, Math.round((1 - (r.p90 - r.p10) / (2 * Math.max(Math.abs(r.net), 1))) * 100))) : null;
  const dl = fn<(d: Date, n: number) => Date>('addDays')(fn<Date>('AS_OF'), c._left);
  return { c, trigger, action, cons, btn, conf, deadline: fn<(d: Date) => string>('fmtD')(dl), left: c._left };
}

// ---------------------------------------------------------------- exceptions and Notify

export interface ExRow {
  id: string; base: string; wh: string; title: string; value: number; count: number; sev: 'High' | 'Medium' | 'Low'; trend: string; go?: string;
  items: { id: string; model: string; v: number }[];
  note: { status: string; ackBy?: string; toLabel: string } | null;
}
export function exRows(sc: CcScope): ExRow[] {
  const exNote = fn<(x: Any) => Any>('exNote'), am = fn<(c: Any) => string>('asModel');
  return fn<(sc: CcScope) => Any[]>('ccExRows')(sc).map((x) => ({
    id: x.id, base: x.base, wh: x.wh, title: x.title, value: x.value, count: x.count, sev: x.sev, trend: x.trend, go: x.go,
    items: x.items.map((i: Any) => ({ id: i.c.id, model: am(i.c), v: i.v })),
    note: exNote(x) ?? null,
  }));
}
/** The account the exception is routed to by default (the demo's exOwner). */
export const exOwner = (x: ExRow): string => fn<(x: ExRow) => string>('exOwner')(x);
export const notifyRecipients = (): Account[] => fn<Account[]>('ACCOUNTS').filter((a) => a.role !== 'Executive');
export function sendNotification(x: ExRow, to: string, sev: string, msg: string): ActionResult<{ id: string; to: string }> {
  return invoke('notify.send', { ex_id: x.id, title: x.wh + ' · ' + x.title, to, sev, msg, ids: x.items.map((i) => i.id).slice(0, 40) });
}
export const acknowledge = (id: string): ActionResult => invoke('notify.acknowledge', { id });

// ---------------------------------------------------------------- Actions on me, handed off, outcomes

export interface AomeItem { t: string; d: string; btn: string; act?: string; arg?: string; go?: string }
export const aomeItems = (): AomeItem[] => fn<() => AomeItem[]>('aomeItems')();

export interface HandedRow { id: string; label: string; sys: string; ref: string | null; age: number; over: boolean }
export function handedRows(): HandedRow[] {
  return fn<() => Any[]>('handedRows')().map((x) => ({ id: x.c.id, label: x.a.label, sys: x.a.sys, ref: x.last ? x.last.ack.ref : null, age: x.age, over: x.over }));
}
export function awaitingApproval(): { decider: string; rows: { id: string; location: string; plan: string; submitted: boolean }[] } {
  const ap = fn<() => CcCase[]>('opScoped')().filter((c) => c.stage === 'awaiting_approval');
  return {
    decider: S().deleg.decisions ? 'Approver' : 'Admin',
    rows: ap.map((c) => ({ id: c.id, location: c.location, plan: c.recommendation ? c.recommendation.plan : '—', submitted: !!c.submitted })),
  };
}
export function outcomesToConfirm(): { rows: { id: string; product: string; assetId: string; plan: string; net: number | null }[]; done: number } {
  const v = fn<() => CcCase[]>('visCases')();
  return {
    rows: v.filter((c) => c.stage === 'closed' && !(c as Any).outcome).map((c) => {
      const r = c.chosen || c.recommendation;
      return { id: c.id, product: c.product, assetId: c.assetId, plan: r ? r.plan : '—', net: r ? r.net : null };
    }),
    done: v.filter((c) => (c as Any).outcome).length,
  };
}

// ---------------------------------------------------------------- Approvals inbox

export interface AccessRequest {
  id: string; kind: 'tenant' | 'mcp'; status: 'pending' | 'approved' | 'declined'; by: string; at: string; tenant?: string; reason?: string;
  decidedBy?: string; decidedAt?: string; note?: string;
  server?: { name: string; owner: string; purpose: string; tools: string[]; access: 'read' | 'write'; data: string };
  kindLabel: string; canDecide: boolean;
}
const toReq = (r: Any): AccessRequest => ({ ...r, kindLabel: fn<Record<string, string>>('REQ_KIND')[r.kind], canDecide: fn<(r: Any) => boolean>('canDecide')(r) });
export const inboxRequests = (): AccessRequest[] => fn<() => Any[]>('inboxReqs')().map(toReq);
/** What Admin delegated to the Approver (null for Admin, who sees every scope). */
export function inboxScope(): string[] | null {
  if (S().acct?.role !== 'Approver') return null;
  const dlab = fn<(d: Any) => string>('dlab');
  return fn<Any[]>('DELEG').filter((d) => S().deleg[d[0]]).map(dlab);
}
export const decisionsAwaiting = (): number => fn<() => CcCase[]>('visCases')().filter((c) => c.stage === 'awaiting_approval').length;
export const decideRequest = (id: string, decision: 'approve' | 'decline', note: string): ActionResult<{ status: string }> =>
  invoke('access.decideRequest', { id, decision, note });
export const requestById = (id: string): AccessRequest | undefined => {
  const r = S().reqs.find((x: Any) => x.id === id);
  return r ? toReq(r) : undefined;
};

/** Submitted decisions as approval cards, by value then deadline, each with its pre-approval check (afApprovalQueue). */
export interface ApprovalCard { id: string; plan: string; net: number; model: string; owner: string; timing: string; submittedBy: string; risks: string[]; steps: string[] }
export function approvalCards(): ApprovalCard[] {
  const q = fn<() => Any[]>('afApprovalQueue')(), am = fn<(c: Any) => string>('asModel'), TPL = fn<Record<string, [string, string][]>>('STEP_TPL');
  return q.map((x) => ({
    id: x.c.id, plan: x.c.recommendation.plan, net: x.net, model: am(x.c), owner: x.c.owner, timing: x.c.timing || '', submittedBy: x.c.submitted.by,
    risks: x.risks.map((r: Any) => r.text), steps: (TPL[x.c.recommendation.id] || []).map((s) => s[0] + ' → ' + s[1]),
  }));
}
export const approvalLimit = (): number => fn<(a: Account) => number>('afLimitFor')(S().acct);

// ---------------------------------------------------------------- integration health (Developer and Admin)

export interface HealthDetail {
  ok: number; warn: number; bad: number; run: number; pct: number;
  hours: { ok: number; warn: number; bad: number }[];
  exceptions: { src: string; obj: string; issue: string; sev: 'High' | 'Medium' | 'Low'; st: string }[];
  exceptionCount: number;
  events: { id: string; ts: number; dest: string; type: string; ack: string; kind: string }[];
}
export function healthDetail(): HealthDetail {
  const t = fn<() => Any>('hhTotals')(), ex = fn<() => Any[]>('smExceptions')(), ackKind = fn<(a: string) => string>('ackKind');
  return {
    ok: t.ok, warn: t.warn, bad: t.bad, run: t.run, pct: t.pct,
    hours: S().hh.map((b: Any) => ({ ok: b.ok, warn: b.warn, bad: b.bad })),
    exceptions: ex.slice(0, 6), exceptionCount: ex.length,
    events: fn<Any[]>('EVENTS').slice(0, 6).map((e) => ({ id: e.id, ts: e.ts, dest: e.dest, type: e.type, ack: e.ack, kind: ackKind(e.ack) })),
  };
}
