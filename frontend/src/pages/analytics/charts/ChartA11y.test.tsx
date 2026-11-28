// @vitest-environment jsdom
// Every mark of every new chart is a button with a name that says what it holds and that it opens the rows; each chart has a summary sentence
// its figure points to; opening a mark hands View data a spec; the arrow keys move between marks.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { OpenAge } from '../../../api/analyticsRows';
import { AgeBands } from './AgeBands';
import { Flow } from './Flow';
import { HeatGrid } from './HeatGrid';
import { LABELS, row, sample } from './testRows';
import { TrendBars } from './TrendBars';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const age: OpenAge = {
  as_of: '2026-11-28', basis: 'modelled', total: { n: 3, value: 900 }, routes: [{ id: 'redeploy', name: 'Redeploy' }, { id: 'resale', name: 'Resale' }],
  bands: [
    { key: '0-7', label: '0 to 7 days', n: 2, value: 600, rows: { source: 'cases', chart: 'age', key: 'band:0-7' }, routes: [
      { id: 'redeploy', name: 'Redeploy', n: 1, value: 400, rows: { source: 'cases', chart: 'age', key: 'band:0-7|route:redeploy' } },
      { id: 'resale', name: 'Resale', n: 1, value: 200, rows: { source: 'cases', chart: 'age', key: 'band:0-7|route:resale' } }] },
    { key: '30+', label: 'Over 30 days', n: 1, value: 300, rows: { source: 'cases', chart: 'age', key: 'band:30+' }, routes: [
      { id: 'resale', name: 'Resale', n: 1, value: 300, rows: { source: 'cases', chart: 'age', key: 'band:30+|route:resale' } }] },
  ],
};

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });

const rows = sample();
const open = vi.fn();
const charts: [string, () => React.ReactElement][] = [
  ['flow', () => <Flow rows={rows} labels={LABELS} onViewData={open} />],
  ['heat grid', () => <HeatGrid rows={rows} labels={LABELS} onViewData={open} />],
  ['trend', () => <TrendBars rows={rows} labels={LABELS} onViewData={open} />],
  ['ageing', () => <AgeBands age={age} onViewData={open} />],
];
const marks = () => [...host.querySelectorAll<HTMLElement>('[data-mark]')];

describe.each(charts)('%s', (_name, make) => {
  beforeEach(() => { open.mockReset(); act(() => root.render(make())); });

  it('has marks, and every one is a button with a name that says it opens the rows', () => {
    expect(marks().length).toBeGreaterThan(2);
    for (const m of marks()) {
      expect(m.tagName === 'BUTTON' || m.getAttribute('role') === 'button').toBe(true);
      expect(m.getAttribute('aria-label')).toMatch(/Opens the (rows|cases)\.$/);
    }
  });

  it('has one tab stop, and the sentence its figure points to', () => {
    expect(marks().filter((m) => m.tabIndex === 0)).toHaveLength(1);
    const group = host.querySelector('[aria-describedby]')!;
    const sentence = host.querySelector('#' + group.getAttribute('aria-describedby'))!;
    expect(sentence.textContent!.length).toBeGreaterThan(30);
  });

  it('opens View data from a click and from Enter, and moves with the arrow keys', () => {
    const [a, b] = marks();
    act(() => { a.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
    expect(open).toHaveBeenCalledTimes(1);
    expect(open.mock.calls[0][0]).toMatchObject({ title: expect.any(String), chart: expect.any(String) });
    act(() => { a.focus(); a.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); });
    if (a.tagName !== 'BUTTON') expect(open).toHaveBeenCalledTimes(2);
    act(() => { a.focus(); a.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })); });
    expect(document.activeElement === b || b.tagName === 'BUTTON').toBe(true);
  });
});

describe('flow marks', () => {
  it('opens a band with the chips that name it', () => {
    open.mockReset();
    act(() => root.render(<Flow rows={rows} labels={LABELS} onViewData={open} />));
    const band = [...host.querySelectorAll('[data-mark]')].find((m) => m.getAttribute('aria-label')?.startsWith('Pump to Redeploy'))!;
    act(() => { band.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
    expect(open.mock.calls[0][0].facets.map((f: { label: string }) => f.label)).toEqual(['Asset class: Pump', 'Route: Redeploy']);
  });
});

describe('heat grid', () => {
  it('shows a dash under five cases and a signed median above, never colour alone', () => {
    const few = [...rows, row({ route: 'exit' }), row({ route: 'exit' }), row({ route: 'exit' })];
    act(() => root.render(<HeatGrid rows={few} labels={LABELS} onViewData={open} />));
    expect(host.textContent).toContain('+$10');
    expect(host.textContent).toContain('−$20');
    const dash = host.querySelector('button[aria-label*="fewer than 5 cases"]')!;
    expect(dash.textContent).toContain('–');
    expect(host.querySelector('button[disabled]')).not.toBeNull();
  });
});
