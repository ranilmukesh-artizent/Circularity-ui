// @vitest-environment jsdom
// P9-1.13 (X-09): a pack's view is drawn from the data it carries; a KPI id no page has heard of still renders.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { PackViewData } from '../../api/analytics';
import { kpiValue, PackView } from './PackView';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));

const view: PackViewData = {
  key: 'new_pack', name: 'New pack', packs: [{ key: 'new_pack', name: 'New pack' }],
  kpis: [
    { id: 'utilisation_gain', label: 'Utilisation gain', definition: 'mean net', value: 12.5, unit: '%', trend: [{ period: '2026-10', value: 10 }, { period: '2026-11', value: 12.5 }], error: null },
    { id: 'units_in', label: 'Units in', definition: 'cases', value: null, unit: '', trend: [], error: null },
  ],
  questions: [{ question: 'Where do units go?', chart: 'bar', rows: [{ key: 'rerent', value: 3 }, { key: 'dispose', value: 1 }], examples: ['RT-2001'] }],
  cases: 4, worked_questions: [], renewals: false,
  suggestion_rules: [],
  stages: [{ key: 'receive', label: 'Return and receive', agent: 'Intake', autonomy: 'alone' }],
};

describe('P9-1.13 PackView (X-09)', () => {
  it('renders the label and value of a KPI id it has never seen', () => {
    act(() => root.render(<PackView view={view} />));
    const tile = host.querySelector('[data-k="utilisation_gain"]');
    expect(tile?.textContent).toContain('Utilisation gain');
    expect(tile?.textContent).toContain('12.5%');
    expect(host.querySelector('[data-k="units_in"]')?.textContent).toContain('No data yet');
  });

  it('draws the question rows, the example cases and the stage agents from the data', () => {
    act(() => root.render(<PackView view={view} />));
    expect(host.textContent).toContain('Where do units go?');
    expect(host.textContent).toContain('rerent');
    expect(host.querySelector('a[href="#/product/RT-2001"]')?.textContent).toBe('RT-2001');
    expect(host.textContent).toContain('Return and receive: Intake (acts alone)');
    expect(host.textContent).toContain('This pack has no suggestion rules.');
  });

  it('shows one short empty state, not empty tiles, for a pack with no cases', () => {
    act(() => root.render(<PackView view={{ ...view, cases: 0, kpis: view.kpis.map((k) => ({ ...k, value: null })), questions: [] }} />));
    expect(host.querySelector('[data-testid="pack-empty"]')?.textContent).toContain('No New pack cases yet');
    expect(host.querySelector('[data-k="units_in"]')).toBeNull();
    expect(host.textContent).toContain('Return and receive: Intake');
  });

  it('formats a value by its unit', () => {
    expect(kpiValue({ value: 1234, unit: '$' })).toBe('$1,234');
    expect(kpiValue({ value: 33.33, unit: '%' })).toBe('33.3%');
    expect(kpiValue({ value: 5, unit: '' })).toBe('5');
    expect(kpiValue({ value: null, unit: '%' })).toBe('No data yet');
  });
});
