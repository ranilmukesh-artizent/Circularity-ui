// @vitest-environment jsdom
// P9-7.6 (X-06): the back-test report page lays out the server's parts in the order of the pilot research's section 3.5.
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReplayReport, ReplayReportOut } from '../../api/replay';
import { BacktestReport, SECTIONS, waterfallTotal } from './BacktestReport';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); document.body.append(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });

const report = {
  run_id: 7, batch_id: 3, flow_ver: '2', n_items: 120, n_held_rows: 2, n_decided: 118, days: 40,
  route_mix: [{ route: 'redeploy', actual_pct: 40, flow_pct: 55 }],
  straight_through_pct: 71.2, approvals_per_day: 2.5, exceptions_per_day: 0.8,
  by_guardrail: [{ guardrail: 'TF-C', owner: 'Fleet manager', approvals: 4, exceptions: 1 }],
  uplift: { primary: 4.2, band80: [-1, 7.4], band95: [-3, 9], secondary: 3.2, bias: 0.9, conservative: 3.2, basis: 'modelled' },
  constraint_loss: 40, agreement_pct: 62.5, held_for_person: 12, actual_net: 1000, flow_net: 1180, repricing: 5,
  route_changes: [{ route: 'refurb', amount: 120 }, { route: 'redeploy', amount: 95 }],
  flips: [], leakage: [], data_quality: [{ reason: 'Fact condition has no date.', count: 2 }], method: 'x',
} as unknown as ReplayReport;

const out: ReplayReportOut = {
  run_id: 7, batch_id: 3, flow_id: 1, flow_ver: '2', dver: null, status: 'done', error: null, created_by: 'planner.a',
  created_at: '2026-11-26T10:00:00', finished_at: '2026-11-26T10:01:00', report,
  waterfall: [
    { step: 'Actual net', amount: 1000, kind: 'base' },
    { step: 'Same-route repricing (bias)', amount: 5, kind: 'delta' },
    { step: 'Route change to refurb', amount: 120, kind: 'delta' },
    { step: 'Route change to redeploy', amount: 95, kind: 'delta' },
    { step: 'Constraint losses', amount: -40, kind: 'delta' },
    { step: 'Net uplift', amount: 180, kind: 'result' },
  ],
  top_flips: [{ item_id: 'T001', from: 'resell', to: 'redeploy', delta: 410, reason: 'actual route excluded by Recall check: quarantined', gate: 'Recall check: quarantined', trace: 'step 1' }],
  method_note: 'As-of rule: the one fixed note. Sensitivity runs are not included.',
};

describe('P9-7.6 back-test report (X-06)', () => {
  it('x-06: the sections come in the order of section 3.5', () => {
    act(() => root.render(createElement(BacktestReport, { out })));
    const order = [...host.querySelectorAll('[data-bt-section]')].map((e) => e.getAttribute('data-bt-section'));
    expect(order).toEqual([...SECTIONS]);
    expect(SECTIONS).toEqual(['numbers', 'waterfall', 'flips', 'agreement', 'quality', 'method']);
  });

  it('x-06: the waterfall steps add up to the flow net and the method note is the server text as sent', () => {
    expect(waterfallTotal(out.waterfall)).toBe(report.flow_net);
    act(() => root.render(createElement(BacktestReport, { out })));
    expect(host.querySelectorAll('[data-bt-step]').length).toBe(6);
    expect(host.querySelector('[data-bt-method]')?.textContent).toBe(out.method_note);
    expect(host.querySelector('[data-bt-agreement]')?.textContent).toContain('12 of 118 items would wait for a person');
    expect(host.querySelector('[data-bt-flips]')?.textContent).toContain('Decided by Recall check: quarantined');
  });

  it('x-06: Export PDF prints the page', () => {
    const print = vi.fn();
    vi.stubGlobal('print', print);
    act(() => root.render(createElement(BacktestReport, { out })));
    act(() => (host.querySelector('[data-bt-export]') as HTMLButtonElement).click());
    expect(print).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });
});
