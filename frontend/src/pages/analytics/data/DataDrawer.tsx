/**
 * View data: the drawer that shows the records behind a figure, filtered to the bar, band or cell that was opened.
 * Closed decisions are counted from the rows the page holds (so the figure and its rows cannot disagree); live cases come
 * from the server (GET /api/screens/analytics/rows). Row Back works because the drawer stays mounted under a row's detail.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { AnalyticsFilter, ClosedRow } from '../../../api/analytics';
import { downloadRowsCsv, fetchRows, journalExport } from '../../../api/analyticsRows';
import { Drawer } from '../../../components/Overlay';
import { toast } from '../../../components/toast';
import { downloadCsv } from '../../../utils/csv';
import { DataTable } from './DataTable';
import {
  activeFacets, DECISION_COLUMNS, emptyState, exportRows, fmtInt, localDataset, nextSort, PAGE_SIZE, reconcileLine, rowCount, serverDataset, toCsv,
  type DataRow, type DataSet, type Labels, type TableState, type ViewSpec,
} from './dataView';
import './dataDrawer.css';

interface Props {
  spec: ViewSpec;
  /** the closed decisions the page holds, already narrowed by its filters */
  rows: ClosedRow[];
  filter: AnalyticsFilter;
  period: string;
  labels: Labels;
  canExport: boolean;
  onClose: () => void;
  /** open one row's detail on top of this table (Back returns here) */
  onOpenRow?: (id: string, source: 'decisions' | 'cases') => void;
}

function useServerSet(spec: ViewSpec, filter: AnalyticsFilter, st: TableState) {
  const remote = spec.source === 'cases';
  const [out, setOut] = useState<{ data: DataSet | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: remote });
  useEffect(() => {
    if (!remote) return;
    let live = true;
    const t = window.setTimeout(() => {
      setOut((o) => ({ ...o, loading: true, error: null }));
      fetchRows({
        source: 'cases', chart: spec.chart, key: spec.key ?? 'all', days: spec.days, filter, sort: st.sort?.key, dir: st.sort?.dir, q: st.q, limit: PAGE_SIZE, offset: st.page * PAGE_SIZE,
      }).then(
        (a) => live && setOut({ data: serverDataset(a, st.page * PAGE_SIZE), error: null, loading: false }),
        (e: Error) => live && setOut((o) => ({ ...o, error: e.message || 'The rows could not be loaded.', loading: false })),
      );
    }, st.q ? 220 : 0);
    return () => { live = false; window.clearTimeout(t); };
  }, [remote, spec, filter, st.sort, st.q, st.page]);
  return out;
}

export function DataDrawer({ spec, rows, filter, period, labels, canExport, onClose, onOpenRow }: Props) {
  const [st, setSt] = useState<TableState>(emptyState);
  const search = useRef<HTMLInputElement>(null);
  const remote = spec.source === 'cases';
  const server = useServerSet(spec, filter, st);
  const local = useMemo(() => (remote ? null : localDataset(rows, spec, st, labels, period, canExport)), [remote, rows, spec, st, labels, period, canExport]);
  const data = remote ? server.data : local;
  const patch = (p: Partial<TableState>) => setSt((s) => ({ ...s, page: 0, ...p }));
  const chips = remote ? [] : activeFacets(spec, st);
  const removeChip = (id: string) => { patch({ removed: [...st.removed, id] }); search.current?.focus(); };
  const clearAll = () => { patch({ removed: spec.facets.map((f) => f.id), q: '' }); search.current?.focus(); };
  const filtered = chips.length < spec.facets.length || st.q !== '';

  const exportCsv = async () => {
    if (!data) return;
    if (remote) {
      try {
        await downloadRowsCsv({ source: 'cases', chart: spec.chart, key: spec.key ?? 'all', days: spec.days, filter, sort: st.sort?.key, dir: st.sort?.dir, q: st.q }, `circularity-${spec.chart}.csv`);
        toast('Exported ' + rowCount(data.total));
      } catch (e) { toast((e as Error).message); }
      return;
    }
    const j = await journalExport({ source: 'decisions', chart: spec.chart, key: 'all' });
    if (!j.ok) return toast('Not exported: ' + j.error.message);
    const all = exportRows(rows, spec, st, labels);
    downloadCsv(toCsv(DECISION_COLUMNS, all), `circularity-${spec.chart}.csv`);
    toast('Exported ' + rowCount(all.length));
  };

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const page = data ? Math.floor(data.offset / PAGE_SIZE) : 0;
  const open = onOpenRow ? (r: DataRow) => onOpenRow(r.id, remote ? 'cases' : 'decisions') : undefined;

  return (
    <Drawer title={spec.title} sub={data?.subtitle ?? (server.error ? 'Could not load the rows' : 'Loading the rows…')} wide onClose={onClose}>
      <div className="dd">
        <div className="dd-bar">
          <div className="dd-chips" role="group" aria-label="Filters on these rows">
            {chips.map((f) => (
              <span key={f.id} className="dd-chip">{f.label}
                <button type="button" aria-label={`Remove filter ${f.label}`} onClick={() => removeChip(f.id)}>×</button>
              </span>
            ))}
            {(spec.fixedChips ?? []).map((c) => <span key={c} className="dd-chip fixed">{c}</span>)}
            {chips.length > 1 && <button type="button" className="btn ghost sm" onClick={clearAll}>Clear filters</button>}
          </div>
          <div className="dd-search">
            <label className="sr" htmlFor="dd-q">{remote ? 'Search these rows' : 'Search by case, model, asset or site'}</label>
            <input
              id="dd-q" ref={search} type="search" name="q" autoComplete="off" spellCheck={false} value={st.q} placeholder={remote ? 'Search these rows…' : 'Search case, model, asset or site…'}
              onChange={(e) => patch({ q: e.target.value })}
            />
          </div>
          {(remote ? data?.canExport : canExport) && spec.exportable !== false && data && data.total > 0 && (
            <button type="button" className="btn sm" onClick={() => void exportCsv()}>Export CSV</button>
          )}
        </div>
        {data?.note && <p className="note dd-note">{data.note}</p>}
        {server.error && <p className="callout dd-note" role="alert">{server.error}</p>}
        {!data ? (
          <div className="dd-loading" role="status">{server.error ? '' : 'Loading the rows…'}</div>
        ) : data.total === 0 ? (
          <div className="dd-empty">
            <b>No rows match.</b>
            <span className="note">{filtered ? 'Remove a filter chip or clear the search box to see more.' : 'There is nothing behind this figure for your account.'}</span>
            {filtered && <button type="button" className="btn sm" onClick={clearAll}>Clear filters and search</button>}
          </div>
        ) : (
          <div className="dd-scroll" role="region" aria-label="Rows, scrolls both ways">
            <DataTable
              columns={data.columns} rows={data.rows} totals={data.totals} total={data.total} sort={st.sort} onOpen={open}
              onSort={(k) => patch({ sort: nextSort(st.sort, k) })} caption={`${spec.title}: ${data.subtitle}`}
            />
          </div>
        )}
        {data && (
          <div className="dd-foot">
            <p className="dd-sum" aria-live="polite">
              {filtered && !remote ? `${fmtInt(data.total)} of ${rowCount(rows.length)} after your filters. ` : ''}
              {reconcileLine(data.total, data.sum, !filtered)}
              {data.truncated ? ' The export holds the first 5,000 rows.' : ''}
            </p>
            {data.total > 0 && (
              <div className="dd-pager">
                <span>Rows {fmtInt(data.offset + 1)} to {fmtInt(data.offset + data.shown)} of {fmtInt(data.total)}</span>
                <button type="button" className="btn sm" disabled={page === 0} onClick={() => setSt((s) => ({ ...s, page: page - 1 }))}>Previous</button>
                <button type="button" className="btn sm" disabled={page + 1 >= pages} onClick={() => setSt((s) => ({ ...s, page: page + 1 }))}>Next</button>
              </div>
            )}
          </div>
        )}
      </div>
    </Drawer>
  );
}
