// @vitest-environment jsdom
// Plan 9, P9-3.12 (TF-07): the six paths valued against the live named demand.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { PathView } from '../../../api/toolFleet';
import { PathsSection, co2Text, hazardLine, netLine, tagsOf } from './PathsSection';

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
  it('shows the CO2e avoided with its factor source on a ready path only (P9-3.14, TF-13)', () => {
    const rel = { ...PATHS[0], co2: 83.5, co2Source: 'sample factors tf-co2-2026.1' };
    expect(co2Text(rel)).toBe('CO2e avoided 83.5 kg · sample factors tf-co2-2026.1');
    expect(co2Text(PATHS[0])).toBeNull();
    act(() => root.render(<PathsSection paths={[rel, { ...PATHS[1], co2: 70, co2Source: 'x' }]} best="release" />));
    expect(host.querySelector('[data-testid="tf-path-release-co2"]')?.textContent).toBe('CO2e avoided 83.5 kg · sample factors tf-co2-2026.1');
    expect(host.querySelector('[data-testid="tf-path-refurb-co2"]')).toBeNull();
  });
  it('renders nothing without paths', () => {
    act(() => root.render(<PathsSection paths={[]} />));
    expect(host.innerHTML).toBe('');
  });
});

describe('a battery pack (P9-3.19, TF-16)', () => {
  const BAT = [
    path('release', { ok: false, net: 0, why: 'State of health 62% is under the 80% this path needs' }),
    path('redeploy', { ok: false, net: 0, why: 'State of health 62% is under the 70% this path needs' }),
    path('resell', { ok: false, net: 0, why: 'Damaged battery transport: a damaged pack takes no standard lane and is not resold' }),
    path('exit', {
      name: 'Take-back recycling', net: -23,
      lines: [
        { type: 'v', label: 'Material credit (cells)', basis: 'recycler quote RQ-77', amt: 9 },
        { type: 'c', label: 'Hazardous transport (lithium-ion, UN 3480)', basis: 'dangerous goods, flat per pack', amt: 14 },
        { type: 'c', label: 'Take-back scheme fee', basis: 'producer take-back scheme', amt: 6 },
      ],
    }),
  ];
  it('says the hazardous-transport line of the take-back only', () => {
    expect(hazardLine(BAT[3])).toBe('Hazardous transport (lithium-ion, UN 3480): $14');
    expect(hazardLine(BAT[0])).toBeNull();
  });
  it('shows four rows, the take-back with its hazard line and the blocked ones with their reason', () => {
    act(() => root.render(<PathsSection paths={BAT} best="exit" standard="exit" />));
    expect(host.querySelectorAll('details')).toHaveLength(4);
    expect(host.querySelector('[data-testid="tf-path-exit-hazard"]')?.textContent).toBe('Hazardous transport (lithium-ion, UN 3480): $14');
    expect(host.querySelector('[data-testid="tf-path-exit"]')?.textContent).toContain('Take-back recycling');
    expect(host.querySelector('[data-testid="tf-path-resell"]')?.textContent).toContain('Damaged battery transport');
    expect(host.querySelector('[data-testid="tf-path-release-hazard"]')).toBeNull();
  });
});
