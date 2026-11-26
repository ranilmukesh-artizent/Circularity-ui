import type { RefreshMatch as Row } from '../../../api/refresh';

const SOURCE = { stock: 'refurbished stock', return: 'return planned to refurbish' } as const;

/** The target life of the swaps: the median life of the tools kept ("Target life 60%"), or '' without swaps. */
export const targetLine = (rows: Row[]): string => (rows.length ? `Target life ${rows[0].target}%` : '');

/** One swap's matched unit: id, life, distance from the target and where it comes from, or why none fits (plan 9, P9-5.3, CR-03). */
export const unitLine = (r: Row): string =>
  r.unit_id
    ? `${r.unit_id}, ${r.rul}% life, ${r.distance} from the target, ${r.source ? SOURCE[r.source] : ''}`
    : `no like-life unit: ${r.why ?? 'none fits'}`;

/** The like-life match of each swapped tool. It proposes; a unit is reserved when a person approves. */
export function RefreshMatch({ match }: { match: Row[] }) {
  if (match.length === 0) return null;
  return (
    <div data-testid="rf-match">
      <p style={{ margin: '12px 0 4px' }} data-testid="rf-match-target">{targetLine(match)}</p>
      <table className="tbl">
        <thead><tr><th>Swap</th><th>Class</th><th>Unit</th><th>Life</th><th>Distance</th><th>Source</th></tr></thead>
        <tbody>
          {match.map((r) => (
            <tr key={r.need_id} data-serial={r.serial} data-cls={r.cls} data-unit={r.unit_id ?? ''}>
              {r.unit_id ? (
                <>
                  <td>{r.serial}</td><td>{r.cls}</td><td>{r.unit_id}</td><td>{r.rul}%</td><td>{r.distance}</td>
                  <td>{r.source ? SOURCE[r.source] : ''}</td>
                </>
              ) : (
                <>
                  <td>{r.serial}</td><td>{r.cls}</td><td colSpan={4}>{unitLine(r)}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
