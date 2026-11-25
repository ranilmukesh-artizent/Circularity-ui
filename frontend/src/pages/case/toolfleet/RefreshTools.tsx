import type { RefreshView } from '../../../api/refresh';

const LABEL = { keep: 'Keep', swap: 'Like-life swap', upgrade: 'Upgrade' } as const;

/** "keep 11, swap 2, upgrade 1": the split of the contract's tools. */
export const totalsLine = (t: RefreshView['tools_totals']): string => `keep ${t.keep}, swap ${t.swap}, upgrade ${t.upgrade}`;

/** Each tool's choice for the next term, with its remaining life and reason (plan 9, P9-5.2, CR-02). */
export function RefreshTools({ tools, totals, hold }: { tools: RefreshView['tools']; totals: RefreshView['tools_totals']; hold: RefreshView['tools_hold'] }) {
  if (tools.length === 0) return null;
  return (
    <div data-testid="rf-tools">
      <p style={{ margin: '12px 0 4px' }} data-testid="rf-tools-totals">{totalsLine(totals)}</p>
      {hold === 'confidence' && (
        <p className="note" data-testid="rf-tools-hold">A life estimate is low confidence: a person decides before the proposal goes on.</p>
      )}
      <table className="tbl">
        <thead><tr><th>Serial</th><th>Class</th><th>Action</th><th>Life left</th><th>Reason</th></tr></thead>
        <tbody>
          {tools.map((t) => (
            <tr key={t.serial} data-action={t.action}>
              <td>{t.serial}</td>
              <td>{t.cls}</td>
              <td>{LABEL[t.action]}</td>
              <td>{t.rul_pct}%</td>
              <td>{t.reason}{t.flag ? <span className="note"> ({t.flag})</span> : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}