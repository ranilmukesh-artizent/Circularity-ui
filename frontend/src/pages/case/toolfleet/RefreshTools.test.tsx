// @vitest-environment jsdom
// Plan 9, P9-5.2 (CR-02): the refresh tools list, its totals line and the low confidence hold.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { RefreshTool } from '../../../api/refresh';
import { RefreshTools, totalsLine } from './RefreshTools';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const tool = (over: Partial<RefreshTool>): RefreshTool => ({
  serial: 'CMH-1', cls: 'CMH', action: 'keep', reason: 'Life left 60%: keep', rul_pct: 60, confidence: 'High', flag: null,
  end_of_parts: null, successor: null, ...over,
});
const TOOLS = [
  tool({}),
  tool({ serial: 'CMH-2', action: 'swap', rul_pct: 21, reason: 'Life left 21% is under 25%: like-life swap' }),
  tool({ serial: 'CRH-1', cls: 'CRH', action: 'upgrade', reason: 'Parts for CRH end 2027-03-31, before the next term ends 2028-01-05: upgrade to TF-CRH2', flag: 'life estimate low confidence', confidence: 'Low' }),
];

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));

describe('RefreshTools', () => {
  it('words the totals', () => {
    expect(totalsLine({ keep: 11, swap: 2, upgrade: 1 })).toBe('keep 11, swap 2, upgrade 1');
  });
  it('lists each tool with action, life and reason, and the totals', () => {
    act(() => root.render(<RefreshTools tools={TOOLS} totals={{ keep: 1, swap: 1, upgrade: 1 }} hold={null} />));
    expect(host.querySelector('[data-testid="rf-tools-totals"]')?.textContent).toBe('keep 1, swap 1, upgrade 1');
    const rows = host.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(3);
    expect(rows[1].textContent).toContain('Like-life swap');
    expect(rows[1].textContent).toContain('21%');
    expect(rows[1].textContent).toContain('Life left 21% is under 25%: like-life swap');
    expect(rows[2].textContent).toContain('upgrade to TF-CRH2');
    expect(rows[2].textContent).toContain('life estimate low confidence');
    expect(host.querySelector('[data-testid="rf-tools-hold"]')).toBeNull();
  });
  it('says when a person must decide', () => {
    act(() => root.render(<RefreshTools tools={TOOLS} totals={{ keep: 1, swap: 1, upgrade: 1 }} hold="confidence" />));
    expect(host.querySelector('[data-testid="rf-tools-hold"]')?.textContent).toContain('low confidence');
  });
  it('renders nothing without tools', () => {
    act(() => root.render(<RefreshTools tools={[]} totals={{ keep: 0, swap: 0, upgrade: 0 }} hold={null} />));
    expect(host.innerHTML).toBe('');
  });
});