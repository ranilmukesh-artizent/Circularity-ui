import { refreshView, type RefreshView } from '../../../api/refresh';
import { money } from '../../../api/format';
import { Panel } from '../../../components/kit/Panel';
import { RefreshExecution } from './RefreshExecution';
import { RefreshLevers } from './RefreshLevers';
import { RefreshMatch } from './RefreshMatch';
import { RefreshPricing } from './RefreshPricing';
import { RefreshTools } from './RefreshTools';

const day = (iso: string): string => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const DAY_MS = 86_400_000;

/** "90 days before the notice date 5 Jan 2027" (or "... the contract end date ..."): the window and what it counts back from. */
export const windowLine = (v: RefreshView): string => {
  const { opens, basis } = v.window;
  const from = basis === 'notice' ? v.contract.notice : v.contract.end;
  if (!opens || !from) return 'The window has not been set.';
  const days = Math.round((new Date(from).getTime() - new Date(opens).getTime()) / DAY_MS);
  return `${days} days before the ${basis === 'notice' ? 'notice date' : 'contract end date'} ${day(from)}`;
};

/** The contract refresh case panel inside the case Overview (plan 9, P9-5.1): the contract, its window and its lines. */
export function RefreshPanel({ caseId }: { caseId: string }) {
  const v = refreshView(caseId);
  const k = v.contract;
  return (
    <Panel title="Contract refresh" sub={`${k.id} · ${k.customer ?? 'customer not named'}${k.market ? ' · ' + k.market : ''}`}>
      <p style={{ margin: 0 }} data-testid="rf-window">
        Window opens {v.window.opens ? day(v.window.opens) : '—'}: {windowLine(v)}
      </p>
      <p className="note" data-testid="rf-contract">
        {k.status ?? 'status unknown'} · term {k.start ? day(k.start) : '—'} to {k.end ? day(k.end) : '—'}
        {k.term_months ? ` · ${k.term_months} months` : ''}
      </p>
      <p style={{ margin: '8px 0 4px' }} data-testid="rf-lines-count">{v.lines.length} lines</p>
      {v.lines.length > 0 && (
        <table className="tbl" data-testid="rf-lines">
          <thead><tr><th>Serial</th><th>Class</th><th>Model</th><th>Fee a month</th><th>Months on contract</th></tr></thead>
          <tbody>
            {v.lines.map((l) => (
              <tr key={l.serial}>
                <td>{l.serial}</td><td>{l.cls ?? '—'}</td><td>{l.model ?? '—'}</td>
                <td>{l.fee == null ? '—' : money(l.fee)}</td><td>{l.months ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <RefreshTools tools={v.tools} totals={v.tools_totals} hold={v.tools_hold} />
      <RefreshMatch match={v.match} />
      <RefreshPricing pricing={v.pricing} approval={v.approval} />
      {v.pricing && !v.execution && <RefreshLevers caseId={caseId} />}
      <RefreshExecution execution={v.execution} />
    </Panel>
  );
}
