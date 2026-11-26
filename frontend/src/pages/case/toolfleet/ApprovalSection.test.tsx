// @vitest-environment jsdom
// Plan 9, P9-3.15 (TF-09): who approves a tool return, by policy or by a person with the reason.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { ApprovalView } from '../../../api/toolFleet';
import { ApprovalSection } from './ApprovalSection';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const BASE: ApprovalView = {
  kind: 'person', role: 'Fleet manager', appRole: 'Approver', reasons: ['Repair $702 is over $600 (GR-14)'], confidence: null, policy: null, by: null,
  holds: [{ id: 'GR-14', reason: 'Repair $702 is over $600 (GR-14)', owner: 'Fleet manager' }],
  text: 'Waits for the Fleet manager: Repair $702 is over $600 (GR-14)',
};

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const render = (a: ApprovalView | null) => {
  act(() => root.render(<ApprovalSection approval={a} />));
  return host;
};

describe('ApprovalSection', () => {
  it('renders nothing before the case is valued', () => {
    expect(render(null).innerHTML).toBe('');
  });

  it('says who the decision waits for and why', () => {
    const h = render(BASE);
    expect(h.querySelector('[data-testid="tf-approval-text"]')?.textContent).toBe('Waits for the Fleet manager: Repair $702 is over $600 (GR-14)');
    expect(h.querySelector('.chip')?.textContent).toBe('Person');
    expect(h.querySelector('[data-testid="tf-approval-holds"]')).toBeNull();
  });

  it('says the policy that approved it, with its version and owner', () => {
    const h = render({
      ...BASE, kind: 'policy', role: null, appRole: null, reasons: [], holds: [], policy: { id: 'SP-1', ver: 1, owner: 'admin' }, by: 'policy SP-1 v1',
      text: 'Approved by policy SP-1 v1 (owner admin)',
    });
    expect(h.querySelector('[data-testid="tf-approval-text"]')?.textContent).toBe('Approved by policy SP-1 v1 (owner admin)');
    expect(h.querySelector('.chip')?.textContent).toBe('Policy');
  });

  it('lists the other holds after the first', () => {
    const h = render({ ...BASE, holds: [...BASE.holds, { id: 'TF-CONF', reason: "Confidence 0.50 is under the flow's 0.75", owner: 'Fleet desk' }] });
    expect(h.querySelector('[data-testid="tf-approval-holds"]')?.textContent).toBe("Confidence 0.50 is under the flow's 0.75");
  });
});
