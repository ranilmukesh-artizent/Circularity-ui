// @vitest-environment jsdom
// View data: opens pre-filtered, chips come off, headers sort, Esc closes, an empty selection says so, Export CSV only for those who may.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_FILTER } from '../../../api/analytics';
import { LABELS, sample } from '../charts/testRows';
import { DataDrawer } from './DataDrawer';
import { facet, measures, type ViewSpec } from './dataView';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const spec: ViewSpec = {
  title: 'Where returned assets go', chart: 'flow', section: 'pipeline', measure: measures.count,
  facets: [facet.route('resale', LABELS), facet.status('reconciled')],
};

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });

const show = (over: Partial<Parameters<typeof DataDrawer>[0]> = {}) => {
  const onClose = vi.fn(), onOpenRow = vi.fn();
  act(() => root.render(<DataDrawer spec={spec} rows={sample()} filter={DEFAULT_FILTER} period="Jan to Mar" labels={LABELS} canExport onClose={onClose} onOpenRow={onOpenRow} {...over} />));
  return { onClose, onOpenRow };
};
const body = () => document.body;
const rowCount = () => body().querySelectorAll('tbody tr').length;
const click = (el: Element | null) => act(() => { (el as HTMLElement).click(); });

describe('DataDrawer', () => {
  it('opens on the rows behind the part that was clicked, and says how many, for how long and for whom', () => {
    show();
    expect(body().querySelector('h2')?.textContent).toBe('Where returned assets go');
    expect(body().textContent).toContain('5 rows · Jan to Mar · Customer A, Customer B');
    expect([...body().querySelectorAll('.dd-chip')].map((c) => c.textContent)).toEqual(['Route: Resale×', 'Status: reconciled×']);
    expect(rowCount()).toBe(5);
    expect(body().querySelector('.dd-sum')?.textContent).toContain('These 5 rows add up to 5 decisions, the figure you opened.');
  });

  it('takes a chip off to widen the rows, and stops claiming it is the figure that was opened', () => {
    show();
    click(body().querySelector('button[aria-label="Remove filter Route: Resale"]'));
    expect(rowCount()).toBe(11);
    expect(body().querySelector('.dd-sum')?.textContent).not.toContain('you opened');
  });

  it('sorts by a header and says so with aria-sort', () => {
    show();
    const th = body().querySelector('th[aria-sort]') as HTMLElement;
    expect(th.getAttribute('aria-sort')).toBe('none');
    const actual = [...body().querySelectorAll('th')].find((h) => h.textContent?.includes('Actual'))!;
    click(actual.querySelector('button'));
    expect([...body().querySelectorAll('th')].find((h) => h.textContent?.includes('Actual'))!.getAttribute('aria-sort')).toBe('ascending');
    click([...body().querySelectorAll('th')].find((h) => h.textContent?.includes('Actual'))!.querySelector('button'));
    expect([...body().querySelectorAll('th')].find((h) => h.textContent?.includes('Actual'))!.getAttribute('aria-sort')).toBe('descending');
  });

  it('shows a totals row and a dash for an empty cell', () => {
    show({ spec: { ...spec, facets: [facet.status('pending')] } });
    expect(body().querySelector('tfoot')?.textContent).toContain('Total, 2 rows');
    expect(body().querySelector('tbody td .dd-nil')?.textContent).toBe('—');
  });

  it('closes on Escape', () => {
    const { onClose } = show();
    act(() => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); });
    expect(onClose).toHaveBeenCalled();
  });

  it('opens a row on a click and on Enter', () => {
    const { onOpenRow } = show();
    const tr = body().querySelector('tbody tr') as HTMLElement;
    click(tr);
    expect(onOpenRow).toHaveBeenCalledWith(expect.stringMatching(/^RT-/), 'decisions');
    act(() => { tr.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); });
    expect(onOpenRow).toHaveBeenCalledTimes(2);
  });

  it('says what to do when nothing matches, and the search box narrows to nothing', () => {
    show();
    const q = body().querySelector('input[type="search"]') as HTMLInputElement;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(q, 'no such case');
      q.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(body().querySelector('.dd-empty')?.textContent).toContain('No rows match.');
    click([...body().querySelectorAll('.dd-empty button')].find((b) => b.textContent?.includes('Clear')) ?? null);
    expect(rowCount()).toBe(14);
  });

  it('offers Export CSV only when the account may export these rows', () => {
    show();
    expect([...body().querySelectorAll('button')].some((b) => b.textContent === 'Export CSV')).toBe(true);
    act(() => root.unmount());
    root = createRoot(host);
    show({ canExport: false });
    expect([...body().querySelectorAll('button')].some((b) => b.textContent === 'Export CSV')).toBe(false);
  });
});
