/**
 * Analytics (#/analytics): closed decisions (the demo's ROWS), their metrics and the reference lists the charts use.
 * With VITE_BACKEND=api: GET /api/screens/analytics (rows, metrics, model_stats, telemetry_unavailable), the read action
 * analytics.models, and the reference lists (di/screens/analytics.py has the mapping).
 */
import { engine } from '../engine/engine';
import { read } from './actions';
import { API } from './backend';
import { cached, ref, withQuery } from './client';
import { view } from './view';

const e = () => engine();

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
export interface AnalyticsFilter { tenant: string; cls: string; route: string; from: number; to: number; model: string }
export const DEFAULT_FILTER: AnalyticsFilter = { tenant: '', cls: '', route: '', from: 0, to: 11, model: '' };

// ---------------------------------------------------------------- API answer
interface Answer { rows: ClosedRow[]; metrics: Omit<Metrics, 'rc'>; model_stats: (ModelStats | null)[]; telemetry_unavailable: boolean }
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
export const months = (): string[] => (API ? ref<string[]>('MONTHS') : e()<string[]>('MONTHS'));
export const routes = (): Route[] => (API ? ref<Route[]>('ROUTES') : e()<Route[]>('ROUTES'));
export const modelVersions = (): ModelVersion[] => (API ? ref<ModelVersion[]>('MODELS') : e()<ModelVersion[]>('MODELS'));
export const assetClasses = (): Record<string, { label: string }> =>
  API ? ref<Record<string, { label: string }>>('CLASSES') : e()<Record<string, { label: string }>>('CLASSES');
export const classIcon = (cls: string): string =>
  (API ? ref<Record<string, string>>('CLS_ICON') : e()<Record<string, string>>('CLS_ICON'))[cls] ?? 'box';
export const equipmentModels = (): string[] => (API ? ref<{ m: string }[]>('EQUIP') : e()<{ m: string }[]>('EQUIP')).map((x) => x.m);
export const components = (): string[] => (API ? ref<string[]>('COMPS') : e()<string[]>('COMPS'));
export const routeById = (id: string): Route => routes().find((r) => r.id === id) ?? { id, name: id, short: id, color: '#999' };

// ---------------------------------------------------------------- rows and metrics
/** Closed decisions the account may see (tenant scope and the top-bar tenant filter), narrowed by the page's filters. */
export function analyticsRows(f: AnalyticsFilter): ClosedRow[] {
  if (API) return answer(f).rows;
  return e()<() => ClosedRow[]>('visRows')().filter(
    (r) => (!f.tenant || r.tenant === f.tenant) && (!f.cls || r.cls === f.cls) && (!f.route || r.route === f.route) &&
      r.mi >= f.from && r.mi <= f.to && (!f.model || r.model === f.model),
  );
}

const med = (a: number[]): number => {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y), m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

export function metrics(rows: ClosedRow[]): Metrics {
  if (!API) return e()<(r: ClosedRow[]) => Metrics>('metrics')(rows);
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
  if (!API) return e()<(v: string) => ModelStats | null>('modelStats')(v);
  const a = last ?? answer();
  return a.model_stats.find((s) => s?.v === v) ?? null;
}

export function closedRow(id: string): ClosedRow | undefined {
  if (!API) return e()<ClosedRow[]>('ROWS').find((r) => r.id === id);
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

/** The ESG telemetry source is not connected (the sustainability callout says so). */
export function telemetryUnavailable(): boolean {
  if (API) return (last ?? answer()).telemetry_unavailable;
  return (e()<(id: string) => { status: string } | undefined>('SRC')('iot') ?? { status: 'unavailable' }).status === 'unavailable';
}

/** A journey-step chip (the demo's stp(n)): the number, label, kind and description shown on panels. */
export function journeyStep(n: number): { n: number; label: string; kind: string; desc: string } {
  const m = API ? ref<number[]>('JMAP')[n] ?? n : e()<(n: number) => number>('jmap')(n);
  const j = (API ? ref<[number, string, string, string][]>('JSTEPS') : e()<[number, string, string, string][]>('JSTEPS'))[m - 1];
  return { n: m, label: j[1], kind: j[2], desc: j[3] };
}

export interface ModelAccuracy {
  decisions: number; band_pct: number; within_band: number; within_band_pct: number; target_coverage_pct: number;
  versions: { version: string; released: string; decisions: number; error_pct: number; bias_pct: number; coverage_pct: number }[];
}
/** The agent's answer beside predicted vs actual: the read action analytics.models (the demo's analytics.accuracy intent). */
export const modelAccuracy = (): ModelAccuracy => read<ModelAccuracy>('analytics.models');
