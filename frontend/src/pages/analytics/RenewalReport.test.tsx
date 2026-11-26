// @vitest-environment jsdom
// P9-5.7 (CR-07): the renewals section shows both rates, the segments, the prediction against the outcome and the caveat verbatim.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { RenewalReport } from '../../api/analytics';
import { RenewalView } from './RenewalReport';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));

const CAVEAT = 'Contracts that got a proposal may differ from those that did not (for example larger or better accounts). This comparison is observational; a 20% region publish is the proof.';
const report: RenewalReport = {
  since: '2024-10-08', until: '2026-10-07', basis: 'observed', caveat: CAVEAT,
  with_proposal: { n: 30, renewed: 20, rate: 20 / 30 }, without_proposal: { n: 30, renewed: 10, rate: 1 / 3 },
  segments: [{ market: 'US', size: 'small', with_proposal: { n: 20, renewed: 13, rate: 0.65 }, without_proposal: { n: 0, renewed: 0, rate: null } }],
  compared: { n: 1, predicted_rate: 0.8, actual_rate: 1, fee_error_pct: 10, swaps_accepted: 1 },
};

describe('P9-5.7 RenewalView', () => {
  it('shows the two rates with their counts and the segment table', () => {
    act(() => root.render(<RenewalView report={report} />));
    expect(host.querySelector('[data-k="with"]')?.textContent).toContain('67%');
    expect(host.querySelector('[data-k="with"]')?.textContent).toContain('20 of 30');
    expect(host.querySelector('[data-k="without"]')?.textContent).toContain('33%');
    expect(host.querySelector('tbody')?.textContent).toContain('US');
    expect(host.querySelector('tbody')?.textContent).toContain('13 of 20');
    expect(host.querySelector('tbody')?.textContent).toContain('None ended');
  });

  it('shows the prediction against the outcome and the caveat verbatim', () => {
    act(() => root.render(<RenewalView report={report} />));
    expect(host.querySelector('[data-k="compared"]')?.textContent).toBe('Proposals predicted 80% renewal; 100% of 1 renewed. Renewed fees were 10.0% from the fee proposed. Swaps accepted: 1.');
    expect(host.querySelector('[data-k="caveat"]')?.textContent).toBe(CAVEAT);
  });

  it('says so when no outcome is recorded', () => {
    const empty = { ...report, segments: [], with_proposal: { n: 0, renewed: 0, rate: null }, compared: { ...report.compared, n: 0 } };
    act(() => root.render(<RenewalView report={empty} />));
    expect(host.querySelector('[data-k="compared"]')?.textContent).toContain('No refresh case has recorded an outcome');
    expect(host.querySelector('table')).toBeNull();
  });
});
