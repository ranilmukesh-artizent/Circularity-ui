import type { RefreshApproval, RefreshPricing as Pricing } from '../../../api/refresh';

const fmt = (n: number, currency: string): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n);

/** "Renewal likelihood 71% with a proposal (59% without)": the server's computed rate, not a promise. */
export const likelihoodLine = (p: Pricing): string =>
  `Renewal likelihood ${Math.round(p.renewal_likelihood * 100)}% with a proposal (${Math.round(p.renewal_without * 100)}% without)`;

/** The proposal's money and who approves it (plan 9, P9-5.4, CR-04). Every figure is the server's; the basis says the odds are modelled. */
export function RefreshPricing({ pricing, approval }: { pricing: Pricing | null; approval: RefreshApproval | null }) {
  if (!pricing) return null;
  const c = pricing.currency;
  return (
    <div data-testid="rf-pricing">
      <p style={{ margin: '12px 0 4px' }} data-testid="rf-fee">
        Fee a month {fmt(pricing.current_fee_month, c)} now, {fmt(pricing.proposed_fee_month, c)} proposed for {pricing.term_months} months;
        saving against new units {fmt(pricing.saving_vs_new, c)}
      </p>
      <p style={{ margin: '4px 0' }} data-testid="rf-likelihood">{likelihoodLine(pricing)}</p>
      <p className="note" data-testid="rf-basis">{pricing.renewal_basis}. Modelled, not a promise.</p>
      {pricing.credits.length > 0 && (
        <table className="tbl" data-testid="rf-credits">
          <thead><tr><th>Upgraded tool</th><th>Credit</th></tr></thead>
          <tbody>
            {pricing.credits.map((x) => (
              <tr key={x.serial}><td>{x.serial}</td><td>{fmt(x.amount, c)}</td></tr>
            ))}
            <tr><td>Total credits</td><td data-testid="rf-credit-total">{fmt(pricing.credit_total, c)}</td></tr>
          </tbody>
        </table>
      )}
      <p className="note" data-testid="rf-cites">
        Terms v{pricing.rate_card_version}, refresh fees v{pricing.fees_version}, credit rules v{pricing.credit_rules_version}
      </p>
      {approval && (
        <p style={{ margin: '4px 0' }} data-testid="rf-approval">
          <span className="chip warn">Person</span> <span data-testid="rf-approval-text">{approval.text}</span>
        </p>
      )}
    </div>
  );
}
