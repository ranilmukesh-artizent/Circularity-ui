/**
 * Build an analysis (plan 11): pick one measure and up to two ways to break it down; the answer is counted from the closed
 * decisions the page holds, so each bar or cell opens exactly the rows it adds up (View data). Pure; the form is AnalysisBuilder.tsx.
 */
import type { ClosedRow } from '../../api/analytics';
import { facet, formatMeasure, median, measures, type Facet, type Labels, type Measure, type ViewSpec } from './data/dataView';

export type MeasureId = 'uplift' | 'net' | 'days' | 'override' | 'count';
export type DimId = 'route' | 'cls' | 'tenant' | 'month' | 'model';
export type Unit = 'usd' | 'days' | 'pct' | 'count';
export interface Analysis { measure: MeasureId; by: DimId[] }

export const MEASURES: { id: MeasureId; label: string; unit: Unit; means: string }[] = [
  { id: 'uplift', label: 'Gain per case over the baseline', unit: 'usd', means: 'average of actual net minus the agreed baseline, reconciled cases' },
  { id: 'net', label: 'Net recovered', unit: 'usd', means: 'actual net value, reconciled cases added up' },
  { id: 'days', label: 'Days to realize', unit: 'days', means: 'median days from decision to actuals, reconciled cases' },
  { id: 'override', label: 'Override rate', unit: 'pct', means: 'share of reconciled cases where a person chose another route' },
  { id: 'count', label: 'Decisions', unit: 'count', means: 'every decision, whatever its status' },
];
export const DIMS: { id: DimId; label: string }[] = [
  { id: 'route', label: 'Route' }, { id: 'cls', label: 'Asset class' }, { id: 'tenant', label: 'Tenant' }, { id: 'month', label: 'Month' }, { id: 'model', label: 'Model version' },
];
export const EXAMPLES: { label: string; a: Analysis }[] = [
  { label: 'Gain per case by route', a: { measure: 'uplift', by: ['route'] } },
  { label: 'Net recovered by asset class', a: { measure: 'net', by: ['cls'] } },
  { label: 'Days to realize by route', a: { measure: 'days', by: ['route'] } },
  { label: 'Override rate by model version', a: { measure: 'override', by: ['model'] } },
  { label: 'Decisions by tenant and route', a: { measure: 'count', by: ['tenant', 'route'] } },
];

const mOf = (id: MeasureId) => MEASURES.find((m) => m.id === id)!;
const dOf = (id: DimId) => DIMS.find((d) => d.id === id)!;
const dimKey = (r: ClosedRow, d: DimId): string => (d === 'route' ? r.route : d === 'cls' ? r.cls : d === 'tenant' ? r.tenant : d === 'month' ? String(r.mi) : r.model);
const dimLabel = (d: DimId, k: string, l: Labels): string => (d === 'route' ? l.routes[k] : d === 'cls' ? l.classes[k] : d === 'month' ? l.months[+k] : k) ?? k;
const dimFacet = (d: DimId, k: string, l: Labels): Facet =>
  d === 'route' ? facet.route(k, l) : d === 'cls' ? facet.cls(k, l) : d === 'tenant' ? facet.tenant(k) : d === 'month' ? facet.month(+k, l) : facet.model(k);

/** Which rows a measure looks at: all decisions for a count, reconciled ones for the rest. */
const base = (m: MeasureId, rows: ClosedRow[]) => (m === 'count' ? rows : rows.filter((r) => r.status === 'reconciled'));

export function measureValue(m: MeasureId, rows: ClosedRow[]): number | null {
  const a = base(m, rows);
  if (!a.length) return null;
  switch (m) {
    case 'uplift': return a.reduce((s, r) => s + (r.actual ?? 0) - r.baseline, 0) / a.length;
    case 'net': return a.reduce((s, r) => s + (r.actual ?? 0), 0);
    case 'days': return median(a.map((r) => r.days ?? 0));
    case 'override': return a.filter((r) => r.override).length / a.length;
    default: return a.length;
  }
}

export interface Group { keys: string[]; label: string; value: number | null; n: number; facets: Facet[] }
export interface Result {
  analysis: Analysis; title: string; groups: Group[]; total: number | null; n: number; rowLabels: string[]; colLabels: string[]; summary: string;
}

const NUM = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });
export function formatValue(v: number | null, unit: Unit): string {
  if (v == null) return '–';
  if (unit === 'usd') return formatMeasure(v, 'usd');
  if (unit === 'days') return NUM.format(v) + ' days';
  if (unit === 'pct') return NUM.format(v * 100) + '%';
  return NUM.format(v);
}

export const analysisTitle = (a: Analysis): string => `${mOf(a.measure).label}${a.by.length ? ' by ' + a.by.map((d) => dOf(d).label.toLowerCase()).join(' and ') : ''}`;

export function runAnalysis(rows: ClosedRow[], a: Analysis, l: Labels): Result {
  const unit = mOf(a.measure).unit;
  const sel = base(a.measure, rows);
  const keysOf = (d: DimId) => {
    const ks = [...new Set(sel.map((r) => dimKey(r, d)))];
    if (d === 'month') return ks.sort((x, y) => +x - +y);
    const order = d === 'route' ? Object.keys(l.routes) : d === 'cls' ? Object.keys(l.classes) : [];
    return ks.sort((x, y) => (order.includes(x) ? order.indexOf(x) : 999) - (order.includes(y) ? order.indexOf(y) : 999) || x.localeCompare(y));
  };
  const [d1, d2] = a.by;
  const lists = a.by.map(keysOf);
  const combos: string[][] = !d1 ? [[]] : !d2 ? lists[0].map((k) => [k]) : lists[0].flatMap((k) => lists[1].map((k2) => [k, k2]));
  const groups: Group[] = combos.map((keys) => {
    const part = sel.filter((r) => keys.every((k, i) => dimKey(r, a.by[i]) === k));
    return { keys, label: keys.map((k, i) => dimLabel(a.by[i], k, l)).join(', '), value: measureValue(a.measure, part), n: part.length, facets: keys.map((k, i) => dimFacet(a.by[i], k, l)) };
  }).filter((g) => g.n > 0);
  if (d1 && !d2 && d1 !== 'month') groups.sort((x, y) => (y.value ?? -Infinity) - (x.value ?? -Infinity));
  const total = measureValue(a.measure, sel);
  const ranked = groups.filter((g) => g.value != null).sort((x, y) => (y.value ?? 0) - (x.value ?? 0));
  const word = a.measure === 'count' ? 'decisions' : 'cases';
  let summary: string;
  if (!sel.length) summary = 'No decisions match, so there is nothing to compare.';
  else if (!d1) summary = `${formatValue(total, unit)} across ${NUM.format(sel.length)} ${word}.`;
  else if (ranked.length < 2) summary = `${ranked[0]?.label ?? 'One group'}: ${formatValue(ranked[0]?.value ?? null, unit)} (${NUM.format(ranked[0]?.n ?? 0)} ${word}).`;
  else {
    const hi = ranked[0], lo = ranked[ranked.length - 1];
    summary = `Highest: ${hi.label} at ${formatValue(hi.value, unit)} (${NUM.format(hi.n)} ${word}). Lowest: ${lo.label} at ${formatValue(lo.value, unit)} (${NUM.format(lo.n)} ${word}). Overall ${formatValue(total, unit)}.`;
  }
  return {
    analysis: a, title: analysisTitle(a), groups, total, n: sel.length, summary,
    rowLabels: d2 ? lists[0].map((k) => dimLabel(d1, k, l)) : [], colLabels: d2 ? lists[1].map((k) => dimLabel(d2, k, l)) : [],
  };
}

/** What the drawer shows for one group: the rows it counted, the chips that name it, and what they add up to. */
export function groupSpec(a: Analysis, g: Group | null): ViewSpec {
  const m = a.measure;
  const measure: Measure = m === 'uplift' ? measures.uplift : m === 'net' ? measures.net : m === 'days' ? { label: 'median days to realize', unit: 'days', of: (r) => r.days ?? 0, agg: 'median' } : measures.count;
  return {
    title: analysisTitle(a), chart: 'analysis', section: 'waterfall', exportable: false,
    facets: [...(m === 'count' ? [] : [facet.status('reconciled')]), ...(g?.facets ?? [])], measure,
    note: m === 'override' ? 'The rate counts reconciled cases where a person chose another route; those cases are listed here with their reasons.' : undefined,
  };
}

// ---------------------------------------------------------------- saved analyses (this browser)
const KEY = 'circ-saved-analyses';
export interface SavedAnalysis { name: string; a: Analysis }
export function loadSaved(): SavedAnalysis[] {
  try {
    const v: unknown = JSON.parse(window.localStorage.getItem(KEY) ?? '[]');
    return Array.isArray(v) ? (v as SavedAnalysis[]).filter((s) => s && typeof s.name === 'string' && s.a && mOf(s.a.measure) && Array.isArray(s.a.by)) : [];
  } catch { return []; }
}
export function storeSaved(list: SavedAnalysis[]): boolean {
  try { window.localStorage.setItem(KEY, JSON.stringify(list.slice(0, 20))); return true; } catch { return false; }
}
