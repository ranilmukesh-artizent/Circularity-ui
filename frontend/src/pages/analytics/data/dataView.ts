/**
 * View data (plan 11, G2): the table behind every Analytics figure. One table, two sources: the closed decisions the page
 * already holds (counted in the browser, so a mark and its rows cannot disagree) and the server's rows endpoint (open cases,
 * pack cases; see api/analyticsRows.ts). Everything here is pure: filters ("facets"), the columns, sort, search, paging,
 * totals, the reconciliation sentence and the CSV text.
 */
import type { ClosedRow } from '../../../api/analytics';
import type { RowsAnswer, RowColumnKind } from '../../../api/analyticsRows';
import { fmtDateYear, money } from '../../../api/format';

export type Kind = 'text' | 'money' | 'int' | 'days' | 'kg' | 'pct' | 'date' | 'status';
export type Cell = string | number | null;
export interface Column { key: string; label: string; kind: Kind; unit?: string; total?: boolean; noExport?: boolean }
export type DataRow = Record<string, Cell> & { id: string };

/** One removable filter behind a figure: the chip says what it is, `test` keeps the rows it matches. */
export interface Facet { id: string; label: string; test: (r: ClosedRow) => boolean }
/** What the figure adds up, so the rows can prove it ("These 1,277 rows add up to $2.31M"). */
export interface Measure { label: string; unit: 'usd' | 'count' | 'days' | 'kg'; of: (r: ClosedRow) => number; agg?: 'sum' | 'median' }
export const median = (a: number[]): number => {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y), m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
export interface ViewSpec {
  /** the chart's one-line title: the drawer's title */
  title: string;
  /** which chart opened it, and the page section that gates it (role access) */
  chart: string;
  section: string;
  /** decisions are counted in the browser; cases come from the server */
  source?: 'decisions' | 'cases';
  /** server filter key (source "cases") */
  key?: string;
  /** the pack chart only: cases opened in the last N days (0 = all) */
  days?: number;
  facets: Facet[];
  /** chips shown without a remove button (a server filter) */
  fixedChips?: string[];
  measure?: Measure;
  /** one sentence under the title, e.g. why some rows are left out */
  note?: string;
  /** false when the server has no chart of this name to journal an export under (a built analysis) */
  exportable?: boolean;
}

export interface Labels { months: string[]; classes: Record<string, string>; routes: Record<string, string> }

export interface DataSet {
  title: string; subtitle: string; columns: Column[]; rows: DataRow[];
  /** rows that match the filters; `shown` is how many are on this page */
  total: number; shown: number; offset: number;
  totals: Record<string, number> | null; sum: { label: string; value: number; unit: Measure['unit']; agg?: 'sum' | 'median' } | null;
  truncated: boolean; canExport: boolean; note?: string;
}

export interface TableState { removed: string[]; sort: { key: string; dir: 'asc' | 'desc' } | null; q: string; page: number }
export const PAGE_SIZE = 50;
export const EXPORT_CAP = 5000;
export const emptyState = (): TableState => ({ removed: [], sort: null, q: '', page: 0 });

// ---------------------------------------------------------------- facets
export const STATUS_LABEL: Record<ClosedRow['status'], string> = {
  reconciled: 'Reconciled', pending: 'Pending', cancelled: 'Demand cancelled', expired: 'Offer expired',
};
const carried = (r: ClosedRow) => r.status === 'reconciled' || r.status === 'pending';

export const facet = {
  route: (id: string, l: Labels): Facet => ({ id: 'route:' + id, label: 'Route: ' + (l.routes[id] ?? id), test: (r) => r.route === id }),
  cls: (id: string, l: Labels): Facet => ({ id: 'cls:' + id, label: 'Asset class: ' + (l.classes[id] ?? id), test: (r) => r.cls === id }),
  month: (i: number, l: Labels): Facet => ({ id: 'mi:' + i, label: 'Month: ' + (l.months[i] ?? i), test: (r) => r.mi === i }),
  status: (s: ClosedRow['status']): Facet => ({ id: 'status:' + s, label: 'Status: ' + STATUS_LABEL[s].toLowerCase(), test: (r) => r.status === s }),
  carriedOut: (): Facet => ({ id: 'carried', label: 'Status: carried out', test: carried }),
  tenant: (t: string): Facet => ({ id: 'tenant:' + t, label: 'Tenant: ' + t, test: (r) => r.tenant === t }),
  model: (v: string): Facet => ({ id: 'model:' + v, label: 'Model: ' + v, test: (r) => r.model === v }),
  override: (reason?: string): Facet => ({
    id: 'override:' + (reason ?? ''), label: reason ? 'Override: ' + reason : 'Overridden by a person',
    test: (r) => !!r.override && (reason === undefined || r.override.reason === reason),
  }),
  equip: (e: string): Facet => ({ id: 'equip:' + e, label: 'Equipment: ' + e, test: (r) => r.equip === e }),
  comp: (c: string): Facet => ({ id: 'comp:' + c, label: 'Component: ' + c, test: (r) => r.comp === c }),
  erosion: (): Facet => ({ id: 'ero', label: 'Value lost to repair or early failure', test: (r) => r.ero > 0 }),
  avoided: (): Facet => ({ id: 'avoided', label: 'Confirmed avoided spend', test: (r) => r.avoided > 0 }),
  withCo2: (): Facet => ({ id: 'co2', label: 'Carbon figure on the case', test: (r) => r.co2e > 0 }),
  scored: (): Facet => ({ id: 'scored', label: 'Scored against the prediction', test: (r) => r.status === 'reconciled' && r.route !== 'exit' && !r.override && r.p50 > 0 }),
  /** a facet that wraps a free predicate (an existing chart's selection) */
  custom: (label: string, test: (r: ClosedRow) => boolean): Facet => ({ id: 'custom:' + label, label, test }),
};

export const measures = {
  uplift: { label: 'recovered above the baseline', unit: 'usd', of: (r: ClosedRow) => (r.actual ?? 0) - r.baseline } satisfies Measure,
  net: { label: 'net recovered', unit: 'usd', of: (r: ClosedRow) => r.actual ?? 0 } satisfies Measure,
  avoided: { label: 'avoided spend', unit: 'usd', of: (r: ClosedRow) => r.avoided } satisfies Measure,
  count: { label: 'decisions', unit: 'count', of: () => 1 } satisfies Measure,
  co2: { label: 'CO2e avoided (estimated)', unit: 'kg', of: (r: ClosedRow) => r.co2e } satisfies Measure,
};

// ---------------------------------------------------------------- columns
export const DECISION_COLUMNS: Column[] = [
  { key: 'id', label: 'Case', kind: 'text' },
  { key: 'month', label: 'Month', kind: 'text' },
  { key: 'tenant', label: 'Tenant', kind: 'text' },
  { key: 'cls', label: 'Asset class', kind: 'text' },
  { key: 'route', label: 'Route', kind: 'text' },
  { key: 'status', label: 'Status', kind: 'status' },
  { key: 'model', label: 'Model', kind: 'text' },
  { key: 'asset', label: 'Asset', kind: 'text' },
  { key: 'p50', label: 'Predicted P50', kind: 'money' },
  { key: 'actual', label: 'Actual', kind: 'money', total: true },
  { key: 'baseline', label: 'Baseline', kind: 'money', total: true },
  { key: 'vs', label: 'Vs baseline', kind: 'money', total: true },
  { key: 'days', label: 'Days', kind: 'days' },
  { key: 'avoided', label: 'Avoided', kind: 'money', total: true },
  { key: 'co2e', label: 'CO2e estimated', kind: 'kg', unit: 'kg', total: true },
  { key: 'co2m', label: 'CO2e measured', kind: 'kg', unit: 'kg' },
  { key: 'reason', label: 'Override reason', kind: 'text', noExport: true },
];

const REASON_MAX = 200;
export function toDataRow(r: ClosedRow, l: Labels): DataRow {
  const rec = r.status === 'reconciled';
  return {
    id: r.id, month: (l.months[r.mi] ?? '').slice(0, 3), tenant: r.tenant, cls: l.classes[r.cls] ?? r.cls, route: l.routes[r.route] ?? r.route,
    status: STATUS_LABEL[r.status], model: r.model, asset: r.assetId, p50: r.p50, actual: r.actual, baseline: r.baseline, vs: rec ? (r.actual ?? 0) - r.baseline : null,
    days: r.days, avoided: r.avoided || null, co2e: r.co2e || null, co2m: r.co2m,
    reason: r.override ? r.override.reason.slice(0, REASON_MAX) : null,
  };
}

// ---------------------------------------------------------------- filter, sort, page
/** The search box matches the case id, the model, the asset id and the site (what a person types to find a record). */
export const matchesQuery = (r: ClosedRow, q: string): boolean => {
  const n = q.trim().toLowerCase();
  return !n || [r.id, r.model, r.assetId, r.site].some((x) => x.toLowerCase().includes(n));
};

export const activeFacets = (spec: ViewSpec, st: TableState): Facet[] => spec.facets.filter((f) => !st.removed.includes(f.id));

export function filterRows(rows: ClosedRow[], spec: ViewSpec, st: TableState): ClosedRow[] {
  const fs = activeFacets(spec, st);
  return rows.filter((r) => fs.every((f) => f.test(r)) && matchesQuery(r, st.q));
}

const cmp = (a: Cell, b: Cell, dir: 1 | -1): number => {
  if (a == null && b == null) return 0;
  if (a == null) return 1; // empty cells go last in either direction
  if (b == null) return -1;
  return (typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b), 'en', { numeric: true })) * dir;
};

/** Sorted by the header the person clicked; without one, the largest value first (as the old drill-through did). Ties keep the case id order. */
export function sortRows(rows: DataRow[], sort: TableState['sort']): DataRow[] {
  const out = [...rows];
  if (!sort) return out.sort((a, b) => Math.abs(Number(b.actual ?? b.p50 ?? 0)) - Math.abs(Number(a.actual ?? a.p50 ?? 0)) || cmp(a.id, b.id, 1));
  const dir = sort.dir === 'asc' ? 1 : -1;
  return out.sort((a, b) => cmp(a[sort.key], b[sort.key], dir) || cmp(a.id, b.id, 1));
}

/** The next sort when a header is clicked: ascending, then descending, then the default order. */
export function nextSort(cur: TableState['sort'], key: string): TableState['sort'] {
  if (!cur || cur.key !== key) return { key, dir: 'asc' };
  return cur.dir === 'asc' ? { key, dir: 'desc' } : null;
}

export function sumColumns(rows: DataRow[], cols: Column[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const c of cols) if (c.total) out[c.key] = rows.reduce((s, r) => s + (typeof r[c.key] === 'number' ? (r[c.key] as number) : 0), 0);
  return out;
}

export function sentencePeriod(l: Labels, from: number, to: number): string {
  const a = (l.months[from] ?? '').slice(0, 3), b = (l.months[to] ?? '').slice(0, 3);
  return from === to ? a : `${a} to ${b}`;
}

const int = new Intl.NumberFormat('en-US');
export const fmtInt = (n: number): string => int.format(n);
/** "1 row", "2 rows": the count with its noun in the right number. */
export const rowCount = (n: number): string => `${fmtInt(n)} ${n === 1 ? 'row' : 'rows'}`;
const compactUsd = (n: number): string => {
  const a = Math.abs(n), s = n < 0 ? '−' : '';
  return a >= 1e6 ? s + '$' + (a / 1e6).toFixed(2) + 'M' : a >= 1e4 ? s + '$' + Math.round(a / 1e3) + 'k' : money(n);
};
export function formatMeasure(v: number, unit: Measure['unit']): string {
  if (unit === 'usd') return compactUsd(v);
  if (unit === 'kg') return Math.abs(v) >= 1000 ? (v / 1000).toFixed(1) + ' t' : Math.round(v) + ' kg';
  if (unit === 'days') return v.toFixed(1) + ' days';
  return fmtInt(v);
}

/** "These 1,277 rows add up to $2.31M recovered above the baseline, the figure you opened." */
export function reconcileLine(total: number, sum: DataSet['sum'], opened = true): string {
  const rows = rowCount(total);
  if (!sum) return `${rows} match.`;
  if (sum.agg === 'median') return `The median across ${total === 1 ? 'this row' : `these ${rows}`} is ${formatMeasure(sum.value, sum.unit)} ${sum.label}${opened ? ', the figure you opened' : ''}.`;
  return `${total === 1 ? 'This row adds' : `These ${rows} add`} up to ${formatMeasure(sum.value, sum.unit)} ${sum.label}${opened ? ', the figure you opened' : ''}.`;
}

export function subtitleOf(total: number, period: string, tenants: string[]): string {
  return [rowCount(total), period, tenants.join(', ')].filter(Boolean).join(' · ');
}

/** The data set for a spec over the closed decisions the page holds: filtered, searched, sorted, one page, with totals over every match. */
export function localDataset(rows: ClosedRow[], spec: ViewSpec, st: TableState, l: Labels, period: string, canExport: boolean): DataSet {
  const all = filterRows(rows, spec, st);
  const tenants = [...new Set(rows.map((r) => r.tenant))].sort();
  const table = sortRows(all.map((r) => toDataRow(r, l)), st.sort);
  const pages = Math.max(1, Math.ceil(table.length / PAGE_SIZE));
  const offset = Math.min(st.page, pages - 1) * PAGE_SIZE;
  const page = table.slice(offset, offset + PAGE_SIZE);
  const m = spec.measure;
  return {
    title: spec.title, subtitle: subtitleOf(all.length, period, tenants), columns: DECISION_COLUMNS, rows: page, total: all.length, shown: page.length, offset,
    totals: sumColumns(table, DECISION_COLUMNS),
    sum: m ? { label: m.label, unit: m.unit, agg: m.agg, value: m.agg === 'median' ? median(all.map(m.of)) : all.reduce((s, r) => s + m.of(r), 0) } : null,
    truncated: false, canExport, note: spec.note,
  };
}

// ---------------------------------------------------------------- display and export
const usd = (n: number) => money(n);
/** A cell as text (the table and the CSV use the same words). `null` is an empty cell, shown as a dash. */
export function cellText(c: Cell, col: Pick<Column, 'kind' | 'unit'>): string {
  if (c == null || c === '') return '—';
  if (typeof c === 'string') return col.kind === 'date' && /^\d{4}-\d{2}-\d{2}$/.test(c) ? fmtDateYear(c) : c;
  switch (col.kind) {
    case 'money': return usd(c);
    case 'kg': return fmtInt(Math.round(c)) + ' kg';
    case 'days': return fmtInt(c) + (c === 1 ? ' day' : ' days');
    case 'pct': return c.toFixed(1) + '%';
    default: return fmtInt(c);
  }
}

const isNumeric = (k: Kind) => k === 'money' || k === 'int' || k === 'days' || k === 'kg' || k === 'pct';
export const alignsRight = (c: Pick<Column, 'kind'>): boolean => isNumeric(c.kind);

/** CSV text of the shown columns for every row (up to the cap): plain numbers, no free-text columns, text cells defused against spreadsheet formulas. */
export function toCsv(cols: Column[], rows: DataRow[]): string {
  const use = cols.filter((c) => !c.noExport);
  const esc = (v: Cell) => {
    if (v == null) return '';
    if (typeof v === 'number') return String(v);
    const t = /^[=+@\t\r]/.test(v) ? "'" + v : v;
    return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
  };
  return [use.map((c) => esc(c.label)).join(','), ...rows.slice(0, EXPORT_CAP).map((r) => use.map((c) => esc(r[c.key])).join(','))].join('\n');
}

/** Every row of the selection (not just the page), in the order on screen: what Export CSV writes. */
export function exportRows(rows: ClosedRow[], spec: ViewSpec, st: TableState, l: Labels): DataRow[] {
  return sortRows(filterRows(rows, spec, st).map((r) => toDataRow(r, l)), st.sort).slice(0, EXPORT_CAP);
}

/** aria-sort of a header. */
export const ariaSort = (sort: TableState['sort'], key: string): 'ascending' | 'descending' | 'none' =>
  sort?.key === key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none';

// ---------------------------------------------------------------- the server's answer (live cases)
const KIND: Record<RowColumnKind, Kind> = { text: 'text', money: 'money', number: 'int', date: 'date', days: 'days', percent: 'pct' };

/** The server's rows answer as the same table the closed decisions use. */
export function serverDataset(a: RowsAnswer, offset: number): DataSet {
  const columns: Column[] = a.columns.map((c) => ({ key: c.key, label: c.label, kind: KIND[c.kind] ?? 'text', unit: c.unit ?? undefined, total: c.key in a.totals }));
  const rows = a.rows.map((r, i) => ({ ...r, id: String(r.id ?? r.case ?? offset + i) })) as DataRow[];
  return {
    title: a.title, subtitle: a.subtitle, columns, rows, total: a.total, shown: a.shown, offset, totals: Object.keys(a.totals).length ? a.totals : null,
    sum: a.sum ? { label: a.sum.label, value: a.sum.value, unit: (['usd', 'count', 'days', 'kg'].includes(a.sum.unit) ? a.sum.unit : a.sum.unit === 'money' ? 'usd' : 'count') as Measure['unit'] } : null,
    truncated: a.truncated, canExport: a.can_export,
  };
}
