// @vitest-environment jsdom
// Plan 9, P9-3.17 (TF-10): the steps after the approval with their executing systems, then realised against predicted.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { FollowThroughView } from '../../../api/toolFleet';
import { FollowThroughSection } from './FollowThroughSection';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const BASE: FollowThroughView = {
  ref: 'APR-2026-10-3161',
  slaHours: 48,
  steps: [
    { k: 'repair', label: 'Refurbishment work order', system: 'MRO · Depot repair', state: 'done', status: 'acknowledged', ack: { by: 'MRO', ref: 'WO-47349', at: '2026-10-08', sim: false }, waiting: null, error: null },
    { k: 'lease', label: 'Lease contract', system: 'Fleet contract system · re-issue', state: 'active', status: 'sent', ack: null, waiting: null, error: null },
    { k: 'finance', label: 'Actual costs posted', system: 'ERP · finance', state: 'todo', status: null, ack: null, waiting: null, error: null },
  ],
  outcome: null,
};

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const render = (f: FollowThroughView | null) => {
  act(() => root.render(<FollowThroughSection followThrough={f} />));
  return host;
};
const text = (h: HTMLElement, id: string) => h.querySelector(`[data-testid="${id}"]`)?.textContent;

describe('FollowThroughSection', () => {
  it('renders nothing before the approval', () => {
    expect(render(null).innerHTML).toBe('');
  });

  it('names each step with its system and where it stands', () => {
    const h = render(BASE);
    expect(text(h, 'tf-ft-repair')).toContain('acknowledged WO-47349');
    expect(text(h, 'tf-ft-lease')).toContain('Fleet contract system · re-issue');
    expect(text(h, 'tf-ft-lease')).toContain('sent, waiting for the system');
    expect(text(h, 'tf-ft-finance')).toContain('to do');
    expect(h.querySelector('[data-testid="tf-ft-outcome"]')).toBeNull();
  });

  it('says a failed step and a simulated acknowledgement', () => {
    const steps = [{ ...BASE.steps[0], ack: { by: 'MRO', ref: 'WO-1', at: 'x', sim: true } }, { ...BASE.steps[1], status: 'failed', error: 'No returned CMH line' }, BASE.steps[2]];
    const h = render({ ...BASE, steps });
    expect(text(h, 'tf-ft-repair')).toContain('acknowledged WO-1 (simulated)');
    expect(text(h, 'tf-ft-lease')).toContain('failed: No returned CMH line');
  });

  it('shows realised against predicted within the tolerance', () => {
    const h = render({ ...BASE, outcome: { actual: 950, predicted: 1000, variance: -50, tolerance: 100, flagged: false, task: null } });
    expect(text(h, 'tf-ft-outcome')).toBe('Realised $950 against predicted $1,000 (−$50, tolerance $100) Within tolerance');
  });

  it('says Finance is checking a variance above the tolerance', () => {
    const h = render({ ...BASE, outcome: { actual: 850, predicted: 1000, variance: -150, tolerance: 100, flagged: true, task: 7 } });
    expect(text(h, 'tf-ft-outcome')).toContain('Finance is checking the variance');
  });
});
