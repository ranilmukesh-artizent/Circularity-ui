// @vitest-environment jsdom
// UI audit gap 8: the product photo of a pack class.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../api/session', () => ({ can: () => true, canPage: () => true }));
vi.mock('../../api/actions', () => ({ invoke: vi.fn() }));

import type { CaseRec } from '../../api/case';
import { Photo } from './CaseBlocks';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); document.body.append(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });
const rec = (over: Partial<CaseRec>) => ({ id: 'MC-1', product: 'Infusion pump', mfr: 'Acme', cls: 'infusion_pump', qty: 1, ...over }) as unknown as CaseRec;

describe('UI audit gaps 8 and C8: Photo', () => {
  it.each(['infusion_pump', 'car_ice', 'radio', 'ev_pack', 'alternator', 'excavator_20t', 'laptop', 'zeppelin'])(
    'a %s case draws the class tile: no image, so never undefined.webp or an industrial photo', (cls) => {
      act(() => root.render(<Photo c={rec({ cls })} />));
      expect(host.querySelector('img')).toBeNull();
      expect(host.querySelector('.classart svg')).not.toBeNull();
      expect(host.querySelector('.classart')?.textContent).toBe(cls);
    });

  it('a demo class keeps its photo', () => {
    act(() => root.render(<Photo c={rec({ cls: 'motor' })} />));
    expect(host.querySelector('img')?.getAttribute('src')).toBe('assets/products/motor.webp');
    expect(host.querySelector('.classart')).toBeNull();
  });

  it('a photo that fails to load falls back to the tile', () => {
    act(() => root.render(<Photo c={rec({ cls: 'pump' })} />));
    act(() => { host.querySelector('img')!.dispatchEvent(new Event('error')); });
    expect(host.querySelector('img')).toBeNull();
    expect(host.querySelector('.classart')).not.toBeNull();
  });
});
