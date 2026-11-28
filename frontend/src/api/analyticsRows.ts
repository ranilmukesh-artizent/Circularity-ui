/**
 * Analytics "View data" (plan 11): the rows behind a chart, from the server. Pages call only this facade.
 *   GET /api/screens/analytics/rows?source=&chart=&key=&<the page's filters>&sort=&dir=&q=&limit=&offset=
 *   GET /api/screens/analytics/rows.csv?<the same>            the CSV of the selection (journalled by the server)
 *   GET /api/screens/analytics/open-age                       open decisions by age and route, with value at risk
 * The server's own contract is the docstring of backend/di/services/screens/analytics_rows.py. Closed decisions are also
 * counted in the browser (pages/analytics/data/dataView.ts) from the rows the page loads; the server answers for live cases.
 */
import { invoke } from './actions';
import { accessToken, cached, http, withQuery } from './client';
import type { AnalyticsFilter } from './analytics';
import type { ActionResult } from './types';
import { view } from './view';

/** What opens the rows behind a number (the server hands these out with every figure it counts). */
export interface RowsRef { source: 'decisions' | 'cases'; chart: string; key: string }
export interface RowsQuery extends RowsRef {
  filter?: AnalyticsFilter; /** the pack chart only: cases opened in the last N days (0 = all) */ days?: number; sort?: string; dir?: 'asc' | 'desc'; q?: string; limit?: number; offset?: number;
}
/** The server's column kinds. */
export type RowColumnKind = 'text' | 'money' | 'number' | 'date' | 'days' | 'percent';
export interface RowColumn { key: string; label: string; kind: RowColumnKind; unit?: string | null }
export interface RowsAnswer {
  title: string; subtitle: string; columns: RowColumn[]; rows: Record<string, string | number | null>[];
  /** rows after the search box; `of` before it (the figure's own count) */
  total: number; of: number; shown: number; period: string; tenants: string[];
  totals: Record<string, number>; sum: { label: string; value: number; unit: string; n: number } | null; truncated: boolean; can_export: boolean;
}

/** The query string of a rows read: the page's filters narrow the rows as they narrow the charts. */
export function rowsPath(q: RowsQuery, csv = false): string {
  const f = q.filter;
  return withQuery('/api/screens/analytics/rows' + (csv ? '.csv' : ''), {
    source: q.source, chart: q.chart, key: q.key,
    tenant: f?.tenant, cls: f?.cls, route: f?.route, from: f?.from, to: f?.to, model: f?.model, org: f?.org,
    tenant_filter: view().tenant, days: q.days, sort: q.sort, dir: q.dir, q: q.q?.trim(), limit: csv ? undefined : q.limit, offset: csv ? undefined : q.offset,
  });
}

export const fetchRows = (q: RowsQuery): Promise<RowsAnswer> => http<RowsAnswer>(rowsPath(q));

/** Save the CSV the server writes (it journals the export). A plain link cannot carry the sign-in token, so the file is fetched and saved. */
export async function downloadRowsCsv(q: RowsQuery, name: string): Promise<void> {
  const token = accessToken();
  const res = await fetch(rowsPath(q, true), { headers: token ? { Authorization: 'Bearer ' + token } : {} });
  if (!res.ok) throw new Error('The export was refused (' + res.status + ').');
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Journal an export the browser builds itself (closed decisions): who exported which figure. A person only; best effort for the caller. */
export const journalExport = (ref: RowsRef): Promise<ActionResult> => invoke('analytics.export', { ...ref });

// ---------------------------------------------------------------- open decisions by age
export interface AgeRoute { id: string; name: string; n: number; value: number; rows: RowsRef }
export interface AgeBand { key: string; label: string; n: number; value: number; rows: RowsRef; routes: AgeRoute[] }
export interface OpenAge {
  as_of: string; basis: string; total: { n: number; value: number }; routes: { id: string; name: string }[]; bands: AgeBand[];
}
/** Open decisions (live cases awaiting approval) by days since received and proposed route, over the cases the account may see. */
export const useOpenAge = (org = ''): OpenAge => cached<OpenAge>(withQuery('/api/screens/analytics/open-age', { tenant_filter: view().tenant, org }));
