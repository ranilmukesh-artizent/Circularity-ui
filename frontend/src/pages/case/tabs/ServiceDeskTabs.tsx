/** The Ticket tab of a service-desk case (P9-4.3, SD-01): ticket number, account code, market, site, loaner promised and one row
 * per tool (serial, family, age, fault or "unclear", cover) with the result of the contract right and recall checks. Starts
 * stage 6 of a service-desk case (tabs/index.tsx). */
import { serviceDeskView } from '../../../api/serviceDesk';
import { Kv } from '../CaseBlocks';
import { gateLine, lineProblem, lineSummary, ticketLine } from '../serviceDesk';
import type { TabProps } from './index';

export function TicketTab({ c }: TabProps) {
  const v = serviceDeskView(c);
  if (!v) return null;
  const rows: [string, string][] = [
    ['Ticket', ticketLine(v)],
    ['Account', v.account ?? 'Not given'],
    ['Market', v.market ?? 'Not given'],
    ['Site', v.site ?? 'Not given'],
    ['Loaner promised', v.loanerPromised ? 'Yes' : 'No'],
  ];
  return (
    <>
      <Kv rows={rows} />
      <table className="stpad" aria-label="Tools on the ticket">
        <thead><tr><th>#</th><th>Serial</th><th>Tool</th><th>Checks</th></tr></thead>
        <tbody>
          {v.lines.map((l) => {
            const bad = lineProblem(l);
            return (
              <tr key={l.n} style={bad ? { color: 'var(--bad)', background: 'var(--bad-soft)' } : undefined} title={bad ?? undefined}>
                <td>{l.n}</td><td>{l.serial}</td><td>{lineSummary(l)}</td>
                <td>{l.gates.map((g) => <div key={g.id}>{gateLine(g)}</div>)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}