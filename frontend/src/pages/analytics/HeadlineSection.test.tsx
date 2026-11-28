// @vitest-environment jsdom
// Plan 11, D1: the headline of a pack in Analytics. Formatting and proportions are pure; the section is drawn from what the server sent.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { HeadlineFigure, PackHeadline as HeadlineData } from '../../api/analytics';
import { Headline } from './HeadlineSection';
import {
  basisTag, carbonSetNote, emptySentence, figureBasis, formatDays, formatFigure, formatKg, formatUsd, gradeRows, periodLabel, routeBars,
} from './headlineFigures';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const fig = (o: Partial<HeadlineFigure> & Pick<HeadlineFigure, 'id'>): HeadlineFigure => ({
  label: o.id, value: 1, unit: 'count', n: 1, of: 1, basis: 'counted', needs: 'Needs a case.', note: '', ...o,
});

const data: HeadlineData = {
  pack: 'device', name: 'Device recommerce', route_word: 'channel', period: { days: 90, since: '2026-08-01', until: '2026-10-30' },
  cases: 6, closed: 3, carbon_sets: ['cfs-2026.2'],
  figures: [
    fig({ id: 'net', label: 'Net recovered', value: 220, unit: 'usd', n: 3, of: 3, basis: 'modelled', note: 'Expected at approval, not yet reconciled' }),
    fig({ id: 'sell_through', label: 'Sell-through', value: 75, unit: 'pct', n: 3, of: 4 }),
    fig({ id: 'days', label: 'Median days to sell', value: 4, unit: 'days', n: 3, of: 3 }),
    fig({ id: 'listed', label: 'Still listed', value: 1, unit: 'count', n: 1, of: 4 }),
    fig({ id: 'carbon', label: 'Carbon avoided, estimated', value: null, unit: 'kg', n: 0, of: 3, basis: 'estimated', needs: 'At least one closed case whose route carries a carbon factor.' }),
  ],
  routes: [{ id: 'offers', name: 'Offers', n: 2, closed: 2, net: 170 }, { id: 'buynow', name: 'Buy Now', n: 1, closed: 0, net: 30 }],
  grades: {
    routes: [{ id: 'offers', name: 'Offers' }, { id: 'buynow', name: 'Buy Now' }],
    rows: [{ grade: 'A', total: 3, cells: { offers: 2, buynow: 1 } }, { grade: 'B', total: 0, cells: { offers: 0, buynow: 0 } }],
  },
};

describe('headline formatting', () => {
  it('says money, percent, days and carbon the way the page reads them', () => {
    expect(formatUsd(1234.4)).toBe('$1,234');
    expect(formatUsd(-50)).toBe('−$50');
    expect(formatFigure({ value: 66.666, unit: 'pct' })).toBe('66.7%');
    expect(formatDays(0.2)).toBe('Under 1 day');
    expect(formatDays(1)).toBe('1 day');
    expect(formatDays(2.5)).toBe('2.5 days');
    expect(formatKg(30)).toBe('30 kg');
    expect(formatKg(1500)).toBe('1.5 t');
    expect(formatFigure({ value: 12345, unit: 'count' })).toBe('12,345');
    expect(formatFigure({ value: null, unit: 'usd' })).toBeNull();
    expect(formatFigure({ value: 0, unit: 'usd' })).toBe('$0');
  });

  it('states each figure with its count and period', () => {
    expect(periodLabel(90)).toBe('last 90 days');
    expect(figureBasis({ id: 'sell_through', n: 3, of: 4 }, 90)).toBe('3 of 4 cases on a sale channel, last 90 days');
    expect(figureBasis({ id: 'net', n: 1, of: 1 }, 30)).toBe('1 closed case, last 30 days');
    expect(figureBasis({ id: 'days', n: 3, of: 3 }, 90)).toBe('median of 3 closed cases, last 90 days');
    expect(figureBasis({ id: 'open', n: 1, of: 4 }, 90)).toBe('1 of 4 cases opened, last 90 days');
    expect(basisTag('modelled')).toBe('Modelled');
    expect(basisTag('estimated')).toBe('Estimated');
    expect(basisTag('counted')).toBeNull();
    expect(carbonSetNote([])).toBe('');
    expect(carbonSetNote(['cfs-2026.2'])).toContain('cfs-2026.2');
  });

  it('draws bars against the largest route and tints against the largest cell, with no division by zero', () => {
    const bars = routeBars(data.routes);
    expect(bars[0]).toMatchObject({ closedShare: 1, openShare: 0, sold: '100%', net: '$170' });
    expect(bars[1]).toMatchObject({ closedShare: 0, openShare: 0.5, sold: '0%' });
    expect(routeBars([])).toEqual([]);
    const g = gradeRows(data.grades);
    expect(g[0]!.cells.map((c) => c.strength)).toEqual([1, 0.5]);
    expect(g[1]!.cells.every((c) => c.strength === 0)).toBe(true);
    expect(gradeRows({ routes: [], rows: [] })).toEqual([]);
  });

  it('words the empty period without a number it does not have', () => {
    expect(emptySentence({ name: 'Device recommerce', period: data.period })).toContain('No device recommerce cases were opened in the last 90 days');
  });
});

describe('the headline section', () => {
  let host: HTMLDivElement, root: Root;
  beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
  beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
  afterEach(() => act(() => root.unmount()));

  it('shows the figures, labels the modelled and estimated ones, and says what a missing figure needs', () => {
    act(() => root.render(<Headline h={data} onDays={() => undefined} />));
    const net = host.querySelector('[data-fig="net"]')!;
    expect(net.textContent).toContain('$220');
    expect(net.textContent).toContain('Modelled');
    expect(net.textContent).toContain('3 closed cases, last 90 days');
    expect(host.querySelector('[data-fig="sell_through"] dd')?.textContent).toBe('75%');
    const carbon = host.querySelector('[data-fig="carbon"]')!;
    expect(carbon.textContent).not.toContain('Estimated'); // no value, so no tag: only what the figure needs
    expect(carbon.textContent).toContain('At least one closed case whose route carries a carbon factor.');
    expect(host.textContent).toContain('Cases and net by channel');
    expect(host.textContent).toContain('Grade to channel');
    expect(host.querySelectorAll('.phl-grid tbody tr')).toHaveLength(2);
  });

  it('tags a carbon figure that has a value as estimated and names its factor set', () => {
    const withCarbon = { ...data, figures: data.figures.map((f) => (f.id === 'carbon' ? { ...f, value: 30, n: 2, of: 3 } : f)) };
    act(() => root.render(<Headline h={withCarbon} onDays={() => undefined} />));
    const carbon = host.querySelector('[data-fig="carbon"]')!;
    expect(carbon.textContent).toContain('30 kg');
    expect(carbon.textContent).toContain('Estimated');
    expect(carbon.textContent).toContain('2 of 3 closed cases carry a factor, last 90 days');
    expect(carbon.textContent).toContain('cfs-2026.2');
  });

  it('asks the page for another period', () => {
    let got = 0;
    act(() => root.render(<Headline h={data} onDays={(d) => { got = d; }} />));
    const sel = host.querySelector('select')!;
    act(() => { sel.value = '30'; sel.dispatchEvent(new Event('change', { bubbles: true })); });
    expect(got).toBe(30);
  });

  it('shows one sentence when the period holds no case', () => {
    act(() => root.render(<Headline h={{ ...data, cases: 0, closed: 0, routes: [], grades: { routes: [], rows: [] } }} onDays={() => undefined} />));
    expect(host.querySelector('[data-testid="headline-empty"]')?.textContent).toContain('No device recommerce cases');
    expect(host.querySelector('.phl-figs')).toBeNull();
  });
});
