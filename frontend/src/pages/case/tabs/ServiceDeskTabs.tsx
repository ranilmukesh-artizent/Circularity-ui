/** The Ticket tab of a service-desk case (P9-4.3, SD-01): ticket number, account code, market, site, loaner promised and one row
 * per tool (serial, family, age, fault or "unclear", cover) with the result of the contract right and recall checks. Starts
 * stage 6 of a service-desk case (tabs/index.tsx). */
import { serviceDeskView } from '../../../api/serviceDesk';
import { Kv } from '../CaseBlocks';
import { estimateLine, estimateStatus, gateLine, keyUsed, lineProblem, lineSummary, money, ticketLine } from '../serviceDesk';
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

/** The Estimate tab (P9-4.4, SD-02): per tool the point estimate, its range, the confidence, the match count and key used, the
 * price lines with what each cites, and whether it is priced without a technician or a draft with the reason. The numbers are
 * the server's: computed from similar past repairs, never written by a model. */
export function EstimateTab({ c }: TabProps) {
  const v = serviceDeskView(c);
  if (!v) return null;
  return (
    <>
      {v.lines.map((l) => {
        const e = l.estimate;
        return (
          <div key={l.n} className="stpad" aria-label={`Estimate for ${l.serial}`}>
            <h4>{l.n}. {l.serial} · {lineSummary(l)}</h4>
            {!e ? <p>No estimate yet.</p> : (
              <>
                <Kv rows={[
                  ['Estimate', e.n ? estimateLine(e) : 'No estimate'],
                  ['Matches', e.n ? `${e.n} similar repairs, ${keyUsed(e.key_used)}` : 'None in the last 3 years'],
                  ['Pricing', estimateStatus(e)],
                ]} />
                {e.lines.length > 0 && (
                  <table aria-label={`Price lines for ${l.serial}`}>
                    <thead><tr><th>Line</th><th>Amount</th><th>Basis</th><th>Cites</th></tr></thead>
                    <tbody>
                      {e.lines.map((p) => (
                        <tr key={p.label}><td>{p.label}</td><td>{money(p.amount, e.currency)}</td><td>{p.basis}</td><td>{p.cites}</td></tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            )}
          </div>
        );
      })}
    </>
  );
}