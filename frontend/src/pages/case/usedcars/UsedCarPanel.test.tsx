// @vitest-environment jsdom
// Plan 9 UI audit gap 7: the used-car panel shows title, odometer, recall, channels and the questions link; other packs get nothing.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { CaseRec } from '../../../api/case';
import { UsedCarPanel } from './UsedCarPanel';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));

const CAR = {
  id: 'RT-9', template: 'used_cars', vehicle: { vin: '1HGCM82633A004352' },
  title: { status: 'clear', lien_open: false }, odometer: { photo_reading: 41230, lease_record: 41100, return_kind: 'lease_end' },
  recall: { checked_at: '2026-10-01T08:00:00+00:00', open: false },
  routes: [{ id: 'auction', plan: 'Auction', net: 1900, p10: 1800, p90: 2000, terms: [{ kind: 'v', label: 'Hammer price', amt: 2100 }], gates: [] }],
  recommendation: { id: 'auction' }, gates: [],
} as unknown as CaseRec;

describe('UsedCarPanel', () => {
  it('shows the checks, the channels and the questions link', () => {
    act(() => root.render(<UsedCarPanel c={CAR} />));
    const t = host.textContent ?? '';
    expect(t).toContain('Title clear · no open lien');
    expect(t).toContain('Photo 41,230 mi · lease record 41,100 mi · 130 mi apart');
    expect(t).toContain('No open recall');
    expect(t).toContain('Auction');
    expect(t).toContain('Net $1,900 · recommended');
    expect(host.querySelector('a[href="#/analytics/packs"]')).not.toBeNull();
  });
  it('renders nothing for another pack', () => {
    act(() => root.render(<UsedCarPanel c={{ ...CAR, template: 'device' } as CaseRec} />));
    expect(host.textContent).toBe('');
  });
});
