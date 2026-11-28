/** The records table of View data: sticky header, sortable columns, money right-aligned in tabular numerals, a totals row. */
import { alignsRight, ariaSort, cellText, rowCount, type Column, type DataRow, type TableState } from './dataView';
import { onActivateKey } from '../../../utils/keys';

const STATUS_CHIP: Record<string, string> = { Reconciled: 'ok', Pending: 'warn', Open: 'warn', Closed: 'ok' };

function Cell({ c, v }: { c: Column; v: DataRow[string] }) {
  const t = cellText(v, c);
  if (c.kind === 'status' && typeof v === 'string') return <span className={'chip ' + (STATUS_CHIP[v] ?? 'line')}>{v}</span>;
  const neg = typeof v === 'number' && v < 0 && c.kind === 'money';
  return <span className={neg ? 'neg' : v == null ? 'dd-nil' : undefined}>{t}</span>;
}

export function DataTable({ columns, rows, totals, total, sort, onSort, onOpen, caption }: {
  columns: Column[]; rows: DataRow[]; totals: Record<string, number> | null; total: number; sort: TableState['sort'];
  onSort: (key: string) => void; onOpen?: (row: DataRow) => void; caption: string;
}) {
  return (
    <table className="dd-table">
      <caption className="sr">{caption}</caption>
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.key} scope="col" aria-sort={ariaSort(sort, c.key)} className={alignsRight(c) ? 'r' : undefined}>
              <button type="button" className="dd-sort" onClick={() => onSort(c.key)} aria-label={`Sort by ${c.label}`}>
                <span>{c.label}</span>
                <i aria-hidden="true" className={'dd-caret ' + (sort?.key === c.key ? sort.dir : '')} />
              </button>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr
            key={r.id} tabIndex={onOpen ? 0 : undefined} className={onOpen ? 'dd-open' : undefined}
            onClick={onOpen ? () => onOpen(r) : undefined} onKeyDown={onOpen ? onActivateKey(() => onOpen(r)) : undefined}
          >
            {columns.map((c, i) => (
              <td key={c.key} className={(alignsRight(c) ? 'r num ' : '') + (i === 0 ? 'dd-id' : '')}>
                {i === 0 ? <b>{cellText(r[c.key], c)}</b> : <Cell c={c} v={r[c.key]} />}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
      {totals && rows.length > 0 && (
        <tfoot>
          <tr>
            {columns.map((c, i) => (
              <td key={c.key} className={alignsRight(c) ? 'r num' : undefined}>
                {i === 0 ? `Total, ${rowCount(total)}` : c.key in totals ? cellText(totals[c.key], c) : ''}
              </td>
            ))}
          </tr>
        </tfoot>
      )}
    </table>
  );
}
