// @vitest-environment jsdom
// Plan 9, P9-5.1 (CR-01, CR-08): the refresh panel's window sentence on both bases, and its lines.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RefreshView } from '../../../api/refresh';
import { RefreshPanel, windowLine } from './RefreshPanel';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const m = vi.hoisted(() => ({ view: null as unknown }));
vi.mock('../../../api/refresh', () => ({ refreshView: () => m.view }));

const LINE = { serial: 'CMH-1', cls: 'CMH', model: 'CMH-12 Pro', fee: 55, months: 33 };
const view = (over: Partial<RefreshView>): RefreshView => ({
  case_id: 'RT-1',
  contract: { id: 'FC-30121', customer: 'Brightline Mechanical', market: 'US', start: '2024-07-01', end: '2027-06-30', notice: '2027-01-05', term_months: 36, status: 'active' },
  window: { opens: '2026-10-07', basis: 'notice' },
  lines: [LINE, { ...LINE, serial: 'CMH-2' }],
  tools: [], tools_totals: { keep: 0, swap: 0, upgrade: 0 }, tools_hold: null, match: [], pricing: null, approval: null, execution: null, outcome: null,
  ...over,
});
const BY_END = view({ contract: { ...view({}).contract, notice: null }, window: { opens: '2027-04-01', basis: 'end' } });

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const text = (ui: React.ReactNode) => {
  act(() => root.render(ui));
  return host.textContent ?? '';
};

describe('window sentence', () => {
  it('counts back from the notice date', () => {
    expect(windowLine(view({}))).toBe('90 days before the notice date 5 Jan 2027');
  });
  it('counts back from the end date without a notice date', () => {
    expect(windowLine(BY_END)).toBe('90 days before the contract end date 30 Jun 2027');
  });
});

describe('RefreshPanel', () => {
  it('renders the notice-date basis sentence, the contract and the lines', () => {
    m.view = view({});
    const t = text(<RefreshPanel caseId="RT-1" />);
    expect(t).toContain('90 days before the notice date 5 Jan 2027');
    expect(t).toContain('FC-30121');
    expect(t).toContain('2 lines');
    expect(host.querySelectorAll('[data-testid="rf-lines"] tbody tr')).toHaveLength(2);
  });
  it('renders the end-date basis sentence', () => {
    m.view = BY_END;
    expect(text(<RefreshPanel caseId="RT-1" />)).toContain('90 days before the contract end date 30 Jun 2027');
  });
});
