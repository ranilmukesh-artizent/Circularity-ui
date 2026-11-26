// @vitest-environment jsdom
// Plan 9, P9-5.5 (CR-05): the proposal sent, the lines drafted and the units reserved, each with its system's reference.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { RefreshExecution as Execution } from '../../../api/refresh';
import { RefreshExecution } from './RefreshExecution';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const step = (kind: string, text: string, state: 'done' | 'active' | 'todo', ref: string | null) => ({ kind, system: 'x', state, ref, text });
const execution = (over: Partial<Execution> = {}): Execution => ({
  approval: 'APR-2026-10-3161', route: 'proposal', approver: 'Approver', valid_until: '2026-10-21', done: true, back: null,
  steps: [
    step('propsend', 'Proposal sent PR-40201', 'done', 'PR-40201'),
    step('propdraft', 'Contract lines drafted DL-40214', 'done', 'DL-40214'),
    step('propreserve', 'Units reserved RU-40227', 'done', 'RU-40227'),
  ],
  ...over,
});

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const q = (id: string) => host.querySelector(`[data-testid="${id}"]`)?.textContent;

describe('RefreshExecution', () => {
  it('shows the three steps with the reference each system returned', () => {
    act(() => root.render(<RefreshExecution execution={execution()} />));
    expect(q('rf-step-propsend')).toBe('Proposal sent PR-40201');
    expect(q('rf-step-propdraft')).toBe('Contract lines drafted DL-40214');
    expect(q('rf-step-propreserve')).toBe('Units reserved RU-40227');
    expect(host.textContent).toContain('Approved under APR-2026-10-3161 by Approver');
  });
  it('marks a step that is not done yet', () => {
    const e = execution({
      done: false,
      steps: [step('propsend', 'Proposal sent PR-40201', 'done', 'PR-40201'), step('propdraft', 'Draft the contract lines', 'active', null)],
    });
    act(() => root.render(<RefreshExecution execution={e} />));
    expect(q('rf-step-propdraft')).toContain('Draft the contract lines');
    expect(q('rf-step-propdraft')).toContain('in progress');
    expect(host.querySelector('[data-testid="rf-step-propdraft"]')?.getAttribute('data-state')).toBe('active');
  });
  it('says when the decision went back to the Fleet desk and why', () => {
    const back = { to: 'Fleet desk', reason: 'RU-7001 is already reserved for RF-9. Re-evaluate to propose another unit.' };
    act(() => root.render(<RefreshExecution execution={execution({ back })} />));
    expect(q('rf-back')).toContain('Back to the Fleet desk');
    expect(q('rf-back')).toContain('RU-7001 is already reserved for RF-9');
  });
  it('renders nothing before an approval', () => {
    act(() => root.render(<RefreshExecution execution={null} />));
    expect(host.innerHTML).toBe('');
  });
});
