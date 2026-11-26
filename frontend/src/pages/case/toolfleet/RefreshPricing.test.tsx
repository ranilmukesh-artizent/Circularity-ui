// @vitest-environment jsdom
// Plan 9, P9-5.4 (CR-04): the proposal's fee, saving, renewal likelihood with its basis, credits and who approves.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { RefreshApproval, RefreshPricing as Pricing } from '../../../api/refresh';
import { RefreshPricing, likelihoodLine } from './RefreshPricing';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const pricing = (over: Partial<Pricing> = {}): Pricing => ({
  currency: 'USD', rate_card_version: 1, fees_version: 1, credit_rules_version: 1, term_months: 12, current_fee_month: 770, proposed_fee_month: 702,
  saving_vs_new: 410, renewal_likelihood: 0.71, renewal_without: 0.59, renewal_basis: 'US contracts of large size, 5 ended in two years with a proposal, 4 renewed: modelled, observational (A section 3.4)',
  credits: [{ serial: 'CRH-1', amount: 210, rule_version: 1 }, { serial: 'CRH-2', amount: 210, rule_version: 1 }], credit_total: 420, credit_total_usd: 420,
  lines: [], routes: [], best: 'proposal', uplift: 100, ...over,
});
const sales: RefreshApproval = { kind: 'person', role: 'Sales', text: 'Waits for Sales: credits $420 are over $300', holds: [] };
const desk: RefreshApproval = { kind: 'person', role: 'Fleet desk', text: 'Waits for the Fleet desk', holds: [] };

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const q = (id: string) => host.querySelector(`[data-testid="${id}"]`)?.textContent;

describe('RefreshPricing', () => {
  it('words the likelihood', () => {
    expect(likelihoodLine(pricing())).toBe('Renewal likelihood 71% with a proposal (59% without)');
  });
  it('shows fees, saving, likelihood with its basis and the modelled caveat', () => {
    act(() => root.render(<RefreshPricing pricing={pricing()} approval={sales} />));
    expect(q('rf-fee')).toContain('$770 now, $702 proposed for 12 months');
    expect(q('rf-fee')).toContain('saving against new units $410');
    expect(q('rf-likelihood')).toBe('Renewal likelihood 71% with a proposal (59% without)');
    expect(q('rf-basis')).toContain('modelled, observational');
    expect(q('rf-basis')).toContain('Modelled, not a promise');
    expect(q('rf-cites')).toBe('Terms v1, refresh fees v1, credit rules v1');
  });
  it('lists the credit of each tool and the total, and says Sales waits', () => {
    act(() => root.render(<RefreshPricing pricing={pricing()} approval={sales} />));
    expect(host.querySelectorAll('[data-testid="rf-credits"] tbody tr')).toHaveLength(3);
    expect(q('rf-credit-total')).toBe('$420');
    expect(q('rf-approval-text')).toBe('Waits for Sales: credits $420 are over $300');
  });
  it('says the Fleet desk waits under the limit', () => {
    act(() => root.render(<RefreshPricing pricing={pricing({ credits: [], credit_total: 0, credit_total_usd: 0 })} approval={desk} />));
    expect(q('rf-approval-text')).toBe('Waits for the Fleet desk');
    expect(host.querySelector('[data-testid="rf-credits"]')).toBeNull();
  });
  it('shows another currency in its own', () => {
    act(() => root.render(<RefreshPricing pricing={pricing({ currency: 'EUR' })} approval={desk} />));
    expect(q('rf-fee')).toContain('€770');
  });
  it('renders nothing without pricing', () => {
    act(() => root.render(<RefreshPricing pricing={null} approval={null} />));
    expect(host.innerHTML).toBe('');
  });
});
