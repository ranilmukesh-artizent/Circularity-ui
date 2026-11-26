// @vitest-environment jsdom
// Plan 9, P9-3.12 (TF-07): the six paths valued against the live named demand.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { PathView } from '../../../api/toolFleet';
import { PathsSection, netLine, tagsOf } from './PathsSection';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const path = (k: string, over: Partial<PathView> = {}): PathView => ({
  k, name: k, ok: true, net: 1000, gross: 1100, cost: 100, hold: 0, why: `why ${k}`, dest: null,
  lines: [{ type: 'v', label: `value of ${k}`, basis: 'a basis', amt: 1100 }, { type: 'c', label: 'Clean and inspect', basis: '2% of new', amt: 100 }],
  ...over,
});
const PATHS = [
  path('release', {
    net: 3200, lines: [{ type: 'v', label: "Fleet renewal FC-30117-R · Brightline Mechanical, 12 months in today's money", basis: '$410 a month × 12', amt: 3300 }, { type: 'c', label: 'Clean and inspect', basis: '2% of new', amt: 100 }],
  }),
  path('refurb', { ok: false, net: 0, why: 'Grade A needs only a clean and inspect (priced under Re-issue and Pre-owned sale)' }),
  path('redeploy', { net: 900 }), path('resell', { net: 1500 }), path('harvest', { net: 800 }), path('exit', { net: 100 }),
];

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const render = () => {
  act(() => root.render(<PathsSection paths={PATHS} best="release" second="resell" standard="release" uplift={1700} />));
  return host;
};

describe('path lines', () => {
  it('tags the best, the second best and the standard route', () => {
    const m = { best: 'release', second: 'resell', standard: 'release' };
    expect(tagsOf('release', m)).toEqual(['Best', 'Standard route']);
    expect(tagsOf('resell', m)).toEqual(['Second best']);
    expect(tagsOf('exit', m)).toEqual([]);
  });
  it('says the net of a ready path and the reason of a blocked one', () => {
    expect(netLine(PATHS[0])).toBe('Net $3,200');
    expect(netLine(PATHS[1])).toContain('Grade A needs only a clean and inspect');
  });
});

describe('PathsSection', () => {
  it('shows six rows with the value lines, the tags and the uplift', () => {
    const h = render();
    expect(h.querySelectorAll('details')).toHaveLength(6);
    expect(h.querySelector('[data-testid="tf-path-release"]')?.textContent).toContain("Fleet renewal FC-30117-R · Brightline Mechanical, 12 months in today's money");
    expect(h.querySelector('[data-testid="tf-path-release"]')?.textContent).toContain('Standard route');
    expect(h.querySelector('[data-testid="tf-path-resell"]')?.textContent).toContain('Second best');
    expect(h.querySelector('[data-testid="tf-uplift"]')?.textContent).toBe('Uplift over the standard route: $1,700');
  });
  it('shows a blocked path with its reason', () => {
    const t = render().querySelector('[data-testid="tf-path-refurb"]')?.textContent ?? '';
    expect(t).toContain('Blocked');
    expect(t).toContain('Grade A needs only a clean and inspect');
  });
  it('renders nothing without paths', () => {
    act(() => root.render(<PathsSection paths={[]} />));
    expect(host.innerHTML).toBe('');
  });
});
