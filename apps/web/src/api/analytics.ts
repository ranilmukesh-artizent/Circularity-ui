/** Analytics (#/analytics): closed decisions (the demo's ROWS), their metrics and the reference lists the charts use. */
import { engine } from '../engine/engine';
import { read } from './actions';

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

export const months = (): string[] => e()<string[]>('MONTHS');
export const routes = (): Route[] => e()<Route[]>('ROUTES');
export const modelVersions = (): ModelVersion[] => e()<ModelVersion[]>('MODELS');
export const assetClasses = (): Record<string, { label: string }> => e()<Record<string, { label: string }>>('CLASSES');
export const classIcon = (cls: string): string => e()<Record<string, string>>('CLS_ICON')[cls] ?? 'box';
export const equipmentModels = (): string[] => e()<{ m: string }[]>('EQUIP').map((x) => x.m);
export const components = (): string[] => e()<string[]>('COMPS');
export const routeById = (id: string): Route => routes().find((r) => r.id === id) ?? { id, name: id, short: id, color: '#999' };

/** Closed decisions the account may see (tenant scope and the top-bar tenant filter), narrowed by the page's filters. */
export function analyticsRows(f: AnalyticsFilter): ClosedRow[] {
  return e()<() => ClosedRow[]>('visRows')().filter(
    (r) => (!f.tenant || r.tenant === f.tenant) && (!f.cls || r.cls === f.cls) && (!f.route || r.route === f.route) &&
      r.mi >= f.from && r.mi <= f.to && (!f.model || r.model === f.model),
  );
}
export const metrics = (rows: ClosedRow[]): Metrics => e()<(r: ClosedRow[]) => Metrics>('metrics')(rows);
export const modelStats = (v: string): ModelStats | null => e()<(v: string) => ModelStats | null>('modelStats')(v);
export const closedRow = (id: string): ClosedRow | undefined => e()<ClosedRow[]>('ROWS').find((r) => r.id === id);

/** $1.23M / $123k / $12 (the demo's kfmt). */
export const kfmt = (n: number): string => e()<(n: number) => string>('kfmt')(n);
/** 12.3% (the demo's pct). */
export const pct = (n: number, d = 0): string => e()<(n: number, d: number) => string>('pct')(n, d);
export const sum = (a: number[]): number => a.reduce((s, x) => s + x, 0);

/** The ESG telemetry source is not connected (the sustainability callout says so). */
export const telemetryUnavailable = (): boolean =>
  (e()<(id: string) => { status: string } | undefined>('SRC')('iot') ?? { status: 'unavailable' }).status === 'unavailable';

/** A journey-step chip (the demo's stp(n)): the number, label, kind and description shown on panels. */
export function journeyStep(n: number): { n: number; label: string; kind: string; desc: string } {
  const m = e()<(n: number) => number>('jmap')(n);
  const j = e()<[number, string, string, string][]>('JSTEPS')[m - 1];
  return { n: m, label: j[1], kind: j[2], desc: j[3] };
}

export interface ModelAccuracy {
  decisions: number; band_pct: number; within_band: number; within_band_pct: number; target_coverage_pct: number;
  versions: { version: string; released: string; decisions: number; error_pct: number; bias_pct: number; coverage_pct: number }[];
}
/** The agent's answer beside predicted vs actual: the read action analytics.models (the demo's analytics.accuracy intent). */
export const modelAccuracy = (): ModelAccuracy => read<ModelAccuracy>('analytics.models');
