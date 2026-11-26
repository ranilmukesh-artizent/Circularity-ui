// @vitest-environment jsdom
// Plan 9, P9-3.13 (TF-08): the live queue plan of the org's open tool returns.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { PlanView } from '../../../api/toolFleet';
import { PlanSection, orderText } from './PlanSection';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const base: PlanView = {
  holds: null, headline: null, contested: [], lost: [], kinds: {}, gain: 0, fcfs: 0, total: 0, slots: 8, refurb_n: 0,
};
const HOLDER: PlanView = {
  ...base, holds: 'FC-30117-R', headline: 'This return takes FC-30117-R', contested: ['FC-30117-R'], kinds: { 'FC-30117-R': 'lease renewal' },
  gain: 1250, fcfs: 8000, total: 9250,
};
const LOSER: PlanView = {
  ...HOLDER, holds: null, lost: [{ order: 'FC-30117-R', to: 'RT-1102', gain: 1250 }],
  headline: 'FC-30117-R (Brightline Mechanical) is planned for RT-1102, where it adds more across the queue',
};

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const render = (p: PlanView | null) => {
  act(() => root.render(<PlanSection plan={p} />));
  return host;
};

describe('PlanSection', () => {
  it('names the order this return takes, the contested orders and the gain over first come, first served', () => {
    const h = render(HOLDER);
    expect(h.querySelector('[data-testid="tf-plan-headline"]')?.textContent).toBe('This return takes FC-30117-R');
    expect(h.querySelector('[data-testid="tf-plan-contested"]')?.textContent).toBe('Contested orders: lease renewal FC-30117-R');
    expect(h.querySelector('[data-testid="tf-plan-gain"]')?.textContent).toContain('adds $1,250 over first come, first served');
  });
  it('says why a return lost the order it wanted', () => {
    const h = render(LOSER);
    expect(h.querySelector('[data-testid="tf-plan-headline"]')?.textContent).toBe(
      'FC-30117-R (Brightline Mechanical) is planned for RT-1102, where it adds more across the queue',
    );
    expect(h.querySelector('[data-testid="tf-plan-lost"]')?.textContent).toBe('FC-30117-R goes to RT-1102, which gains $1,250 more from it.');
  });
  it('renders nothing for a return in no contest', () => {
    expect(render(base).innerHTML).toBe('');
    expect(render(null).innerHTML).toBe('');
  });
  it('writes an order with its kind when the plan names one', () => {
    expect(orderText('SO-1', { 'SO-1': 'sales order' })).toBe('sales order SO-1');
    expect(orderText('X-9', {})).toBe('X-9');
  });
});
