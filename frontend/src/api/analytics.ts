/**
 * Analytics (#/analytics): closed decisions (the demo's ROWS), their metrics and the reference lists the charts use.
 * GET /api/screens/analytics (rows, metrics, model_stats, telemetry_unavailable, orgs), the read action
 * analytics.models, and the reference lists (di/services/screens/analytics.py has the mapping).
 */
import { invoke, read } from './actions';
import { cached, packClasses, ref, withQuery } from './client';
import type { ActionResult } from './types';
import { view } from './view';

export interface Override { rec: string; exec: string; reason: string; cf: number; delta: number }
export interface ClosedRow {
  id: string; mi: number; tenant: string; site: string; cls: string; route: string; model: string; assetId: string; snapshot: string;
  status: 'reconciled' | 'pending' | 'cancelled' | 'expired';
  p10: number; p50: number; p90: number; actual: number | null; baseline: number;
  days: number | null; baseDays: number; avoided: number; co2e: number; co2m: number | null;
  pool: { g: number; o: number } | null; ero: number; comp: string; equip: string; override: Override | null;
}
export interface Route { id: string; name: string; short: string; color: string }
export interface ModelVersion { v: string; released: string }
export interface ModelStats { v: string; n: number; mape: number; bias: number; cov: number }
export interface Metrics {
  rc: ClosedRow[]; base: number; act: number; uplift: number; avoided: number; days: number; baseDays: number;
  pend: number; liveOpen: number; unresolved: number; canc: number; exp: number; n: number;
}
/** org: an org unit id (plan 8 MVP-10.1, the group roll-up): only the cases of its subtree; '' every case. */
export interface AnalyticsFilter { tenant: string; cls: string; route: string; from: number; to: number; model: string; org?: string }
export const DEFAULT_FILTER: AnalyticsFilter = { tenant: '', cls: '', route: '', from: 0, to: 11, model: '', org: '' };
/** An org unit the account may pick, depth first with its depth (for an indented select). */
export interface OrgOption { id: string; name: string; kind: string; depth: number }

// ---------------------------------------------------------------- API answer
interface Answer { rows: ClosedRow[]; metrics: Omit<Metrics, 'rc'>; model_stats: (ModelStats | null)[]; telemetry_unavailable: boolean; orgs: OrgOption[] }
/** Which answer a rows array came from, so metrics(rows) can use that answer's totals. */
const answerOf = new WeakMap<ClosedRow[], Answer>();
let last: Answer | null = null;

function answer(f: AnalyticsFilter = DEFAULT_FILTER): Answer {
  const a = cached<Answer>(withQuery('/api/screens/analytics', { ...f, tenant_filter: view().tenant }));
  answerOf.set(a.rows, a);
  last = a;
  return a;
}

// ---------------------------------------------------------------- reference lists
export const months = (): string[] => ref('MONTHS');
export const routes = (): Route[] => ref('ROUTES');
export const modelVersions = (): ModelVersion[] => ref('MODELS');
/** The demo's classes, then the ones the packs add (labels for every class a closed decision may carry). */
export const assetClasses = (): Record<string, { label: string }> => ({ ...ref('CLASSES'), ...packClasses() });
/** The asset-class filter's options: the demo's classes exactly for the industrial pack (the default), plus the pack classes
 *  only when another pack or template is selected. */
export const classOptions = (pack = 'industrial'): Record<string, { label: string }> =>
  pack === 'industrial' ? { ...ref('CLASSES') } : { ...ref('CLASSES'), ...packClasses() };
export const classIcon = (cls: string): string => ref('CLS_ICON')[cls] ?? 'box';
export const equipmentModels = (): string[] => ref('EQUIP').map((x) => x.m);
export const components = (): string[] => ref('COMPS');
export const routeById = (id: string): Route => routes().find((r) => r.id === id) ?? { id, name: id, short: id, color: '#999' };

// ---------------------------------------------------------------- rows and metrics
/** Closed decisions the account may see (tenant scope and the top-bar tenant filter), narrowed by the page's filters. */
export function analyticsRows(f: AnalyticsFilter): ClosedRow[] {
  return answer(f).rows;
}

const med = (a: number[]): number => {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y), m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

export function metrics(rows: ClosedRow[]): Metrics {
  const rc = rows.filter((r) => r.status === 'reconciled');
  const a = answerOf.get(rows);
  if (a) return { ...a.metrics, rc };
  // rows the page narrowed itself: the demo's metrics over them (awaiting-approval cases from the last answer)
  const base = sum(rc.map((r) => r.baseline)), act = sum(rc.map((r) => r.actual ?? 0));
  const pend = rows.filter((r) => r.status === 'pending').length, liveOpen = last?.metrics.liveOpen ?? 0;
  return {
    rc, base, act, uplift: act - base, avoided: sum(rc.map((r) => r.avoided)),
    days: med(rc.map((r) => r.days ?? 0)), baseDays: med(rc.map((r) => r.baseDays)),
    pend, liveOpen, unresolved: pend + liveOpen,
    canc: rows.filter((r) => r.status === 'cancelled').length, exp: rows.filter((r) => r.status === 'expired').length, n: rows.length,
  };
}

export function modelStats(v: string): ModelStats | null {
  const a = last ?? answer();
  return a.model_stats.find((s) => s?.v === v) ?? null;
}

export function closedRow(id: string): ClosedRow | undefined {
  return (last ?? answer()).rows.find((r) => r.id === id);
}

// ---------------------------------------------------------------- formatting
/** $1.23M / $123k / $12 (the demo's kfmt). */
export function kfmt(n: number): string {
  const a = Math.abs(n), s = n < 0 ? '−' : '';
  return a >= 1e6 ? s + '$' + (a / 1e6).toFixed(2) + 'M' : a >= 1e3 ? s + '$' + Math.round(a / 1e3) + 'k' : s + '$' + Math.round(a);
}
/** 12.3% (the demo's pct). */
export const pct = (n: number, d = 0): string => (n * 100).toFixed(d) + '%';
export const sum = (a: number[]): number => a.reduce((s, x) => s + x, 0);

/** The org units the account may roll the page up to (the org select). */
export function analyticsOrgs(): OrgOption[] {
  return (last ?? answer()).orgs ?? [];
}

/** The ESG telemetry source is not connected (the sustainability callout says so). */
export function telemetryUnavailable(): boolean {
  return (last ?? answer()).telemetry_unavailable;
}

/** A journey-step chip (the demo's stp(n)): the number, label, kind and description shown on panels. */
export function journeyStep(n: number): { n: number; label: string; kind: string; desc: string } {
  const m = ref('JMAP')[n] ?? n;
  const j = ref('JSTEPS')[m - 1];
  return { n: m, label: j[1], kind: j[2], desc: j[3] };
}

export interface ModelAccuracy {
  decisions: number; band_pct: number; within_band: number; within_band_pct: number; target_coverage_pct: number;
  versions: { version: string; released: string; decisions: number; error_pct: number; bias_pct: number; coverage_pct: number }[];
}
/** The agent's answer beside predicted vs actual: the read action analytics.models (the demo's analytics.accuracy intent). */
export const modelAccuracy = (): ModelAccuracy => read<ModelAccuracy>('analytics.models');

// ---------------------------------------------------------------- the Packs tab (plan 9, P9-1.13)
/** One KPI of a pack, as the server computed it from the pack's own measure (backend/di/services/modeler/kpis.py). `value` is null for "No data yet". */
export interface PackKpi {
  id: string; label: string; definition: string; value: number | null;
  /** "%", "$" or "" */
  unit: string; trend: { period: string; value: number }[];
  /** why a measure the grammar refused shows no value, else null */
  error: string | null;
}
/** An analytics question of a pack, answered: bars of {key, value} and up to five example case ids. */
export interface PackQuestion { question: string; chart: string; rows: { key: string; value: number }[]; examples: string[] }
/** A stage of the pack with its agent and autonomy. */
export interface PackStage { key: string; label: string; agent: string; autonomy: 'recommend' | 'limits' | 'alone' }
/** GET /api/screens/analytics/pack?key= */
export interface PackViewData {
  key: string; name: string; packs: { key: string; name: string }[]; kpis: PackKpi[]; questions: PackQuestion[];
  /** how many of the pack's cases the account sees (0: the pack has no data for it yet) */
  cases: number;
  /** the pack's own worked questions (asked with `device.question`), empty for a pack with none */
  worked_questions: { id: string; question: string }[];
  /** the pack has contract renewals to report */
  renewals: boolean;
  suggestion_rules: Record<string, unknown>[]; stages: PackStage[];
}
/** The Packs tab: the pack's KPIs, questions and stages over the cases of that pack the account may see ("" picks the first pack with KPIs and cases, else industrial). */
export const usePackView = (key: string): PackViewData => cached<PackViewData>(withQuery('/api/screens/analytics/pack', { key }));

// ---------------------------------------------------------------- Contract renewals (plan 9, P9-5.7)
/** Renewals of a group of contracts: how many ended, how many renewed, the rate (null when none ended). */
export interface RenewalRate { n: number; renewed: number; rate: number | null }
/** One like-for-like segment: contracts of a market and a size band, with and without a proposal. */
export interface RenewalSegment { market: string; size: string; with_proposal: RenewalRate; without_proposal: RenewalRate }
/** What the proposals predicted against what happened, over the refresh cases that recorded an outcome. */
export interface RenewalCompared { n: number; predicted_rate: number | null; actual_rate: number | null; fee_error_pct: number | null; swaps_accepted: number }
/** GET /api/screens/analytics/renewals?since=&until= (backend/di/services/screens/analytics.py). Counts and ratios from the fleet's own contracts. */
export interface RenewalReport {
  since: string; until: string; basis: string; caveat: string;
  with_proposal: RenewalRate; without_proposal: RenewalRate; segments: RenewalSegment[]; compared: RenewalCompared;
}
/** The renewal rate with and without a proposal, per segment, and the proposals' predictions against the outcomes. An empty bound is the server's default (the last two years). */
export const renewalReport = (f: { since: string; until: string }): RenewalReport =>
  cached<RenewalReport>(withQuery('/api/screens/analytics/renewals', f));

// ---------------------------------------------------------------- Worked pack questions (plan 9, P9-6.17, DV-13)
/** One point of a worked question chart; `launch` marks the week a successor launched (line charts). */
export interface QuestionPoint { x: string; y: number | null; launch?: boolean }
/** What `device.question` answers: the computed sentence, the chart series and example records (every figure computed, never a models). */
export interface PackAnswer {
  question_id: string; question: string; as_of: string; sentence: string;
  chart: { kind: 'line' | 'bar'; series: { name: string; points: QuestionPoint[] }[] };
  examples: Record<string, string | number>[];
}
/** The action `device.question {question_id}`, over the records the account may see (the same call Ask makes). */
export const packQuestion = (id: string): PackAnswer => read<PackAnswer>('device.question', { question_id: id });

// ---------------------------------------------------------------- saved views (plan 9, P9-9.19, UC-20)
export type AlertOp = '>' | '>=' | '<' | '<=';
export interface ViewAlert { measure: string; op: AlertOp; threshold: number }
/** A saved worked question (view.list): `mine` is false for a view shared with the account's role; `measures` are what an alert may watch. */
export interface SavedView {
  id: number; org_unit_id: string; owner: string; pack: string; question_id: string; question: string; name: string;
  params: Record<string, unknown>; shared_with_roles: string[]; alert: ViewAlert | null; alert_active: boolean; mine: boolean; measures: string[];
}
/** The views the account owns or that are shared with its role (the read action view.list; an agent may read it too). */
export const savedViews = (): SavedView[] => read<{ views: SavedView[] }>('view.list').views;
/** Save a worked question as a view of an org unit (view.save: Admin, Planner, Approver, Executive, Finance, Engineer). */
export const saveView = (orgUnit: string, pack: string, questionId: string, name: string): Promise<ActionResult<SavedView>> =>
  invoke<SavedView>('view.save', { org_unit_id: orgUnit, pack, question_id: questionId, name, params: {} });
/** Replace the roles a view is shared with (view.share: its owner only; never an agent). */
export const shareView = (id: number, roles: string[]): Promise<ActionResult<SavedView>> => invoke<SavedView>('view.share', { view_id: id, roles });
/** Set the one alert of a view, or clear it (view.setAlert: its owner only; an agent's call is held for a person). */
export const setViewAlert = (id: number, alert: ViewAlert | null): Promise<ActionResult<SavedView>> =>
  invoke<SavedView>('view.setAlert', alert ? { view_id: id, ...alert } : { view_id: id, clear: true });
