// @vitest-environment jsdom
// Plan 9, P9-5.3 (CR-03): the like-life match of each swapped tool, or why no unit fits.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { RefreshMatch as Row } from '../../../api/refresh';
import { RefreshMatch, targetLine, unitLine } from './RefreshMatch';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const row = (over: Partial<Row>): Row => ({
  serial: 'CMH-2', need_id: 'RT-1:CMH-2', cls: 'CMH', target: 60, unit_id: 'RU-7012', rul: 58, distance: 2, source: 'stock', why: null, ...over,
});

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));

describe('RefreshMatch', () => {
  it('words the target and the unit', () => {
    expect(targetLine([row({})])).toBe('Target life 60%');
    expect(unitLine(row({}))).toBe('RU-7012, 58% life, 2 from the target, refurbished stock');
    expect(unitLine(row({ unit_id: null, why: 'every CMH unit is reserved' }))).toBe('no like-life unit: every CMH unit is reserved');
  });
  it('shows the matched unit with its life, distance and source', () => {
    act(() => root.render(<RefreshMatch match={[row({})]} />));
    expect(host.querySelector('[data-testid="rf-match-target"]')?.textContent).toBe('Target life 60%');
    const tr = host.querySelector('tbody tr') as HTMLElement;
    expect(tr.dataset.unit).toBe('RU-7012');
    expect(tr.textContent).toContain('58%');
    expect(tr.textContent).toContain('refurbished stock');
  });
  it('says why no unit fits', () => {
    act(() => root.render(<RefreshMatch match={[row({ unit_id: null, rul: null, distance: null, source: null, why: 'RU-7012 (58%) goes to RT-1, which it fits better' })]} />));
    expect(host.querySelector('tbody tr')?.textContent).toContain('no like-life unit: RU-7012 (58%) goes to RT-1');
  });
  it('renders nothing without swaps', () => {
    act(() => root.render(<RefreshMatch match={[]} />));
    expect(host.innerHTML).toBe('');
  });
});
