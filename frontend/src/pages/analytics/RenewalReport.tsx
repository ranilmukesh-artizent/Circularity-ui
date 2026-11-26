import { renewalReport, type RenewalRate, type RenewalReport } from '../../api/analytics';
import { Panel } from '../../components/kit/Panel';

const pct = (x: number | null) => (x === null ? 'No contracts' : (x * 100).toFixed(0) + '%');
const cell = (r: RenewalRate) => (r.n === 0 ? 'None ended' : `${pct(r.rate)} (${r.renewed} of ${r.n})`);

/** The "Contract renewals" section: the renewal rate with and without a proposal, the like-for-like segments, what the proposals
 *  predicted against the recorded outcomes, and the caveat verbatim. Counts from the fleet's contracts, never a model's words. */
export function RenewalView({ report }: { report: RenewalReport }) {
  const c = report.compared;
  return (
    <section className="sect" data-testid="renewals" aria-label="Contract renewals">
      <Panel title="Contract renewals" sub={`${report.since} to ${report.until}`}>
        <div className="row" style={{ gap: 24 }}>
          <div data-k="with"><b className="num">{pct(report.with_proposal.rate)}</b><div className="note">With a proposal: {cell(report.with_proposal)}</div></div>
          <div data-k="without"><b className="num">{pct(report.without_proposal.rate)}</b><div className="note">Without a proposal: {cell(report.without_proposal)}</div></div>
        </div>
        {report.segments.length > 0 && (
          <table className="t static tight" style={{ marginTop: 12 }}>
            <thead><tr><th>Market</th><th>Size</th><th>With a proposal</th><th>Without a proposal</th></tr></thead>
            <tbody>
              {report.segments.map((s) => (
                <tr key={s.market + s.size}><td>{s.market}</td><td>{s.size}</td><td>{cell(s.with_proposal)}</td><td>{cell(s.without_proposal)}</td></tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="note" data-k="compared" style={{ marginBottom: 0 }}>
          {c.n === 0
            ? 'No refresh case has recorded an outcome in this period yet.'
            : `Proposals predicted ${pct(c.predicted_rate)} renewal; ${pct(c.actual_rate)} of ${c.n} renewed. ` +
              (c.fee_error_pct === null ? '' : `Renewed fees were ${c.fee_error_pct.toFixed(1)}% from the fee proposed. `) +
              `Swaps accepted: ${c.swaps_accepted}.`}
        </p>
        <p className="note" data-k="caveat">{report.caveat}</p>
      </Panel>
    </section>
  );
}

/** Analytics › Packs: the renewals of the last two years in the account's org units. */
export function RenewalSection() {
  return <RenewalView report={renewalReport({ since: '', until: '' })} />;
}
