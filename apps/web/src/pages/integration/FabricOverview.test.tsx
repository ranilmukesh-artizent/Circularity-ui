// @vitest-environment jsdom
// All integrations' row (IntRow): a source just connected is listed before the sources list has its record; its row
// must not crash ("Cannot read properties of undefined (reading 'id')") and has nothing to open until it arrives.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CatalogItem, Integration, Source } from '../../api/integration';
import { IntCtx, type IntUI } from './FabricContext';

vi.mock('../../api/session', () => ({ can: () => true }));
vi.mock('../../api/useBackend', () => ({ useBackend: () => undefined }));
vi.mock('./SourceMenu', () => ({ SourceMenu: ({ s }: { s: Source }) => <span className="menu">{s.id}</span> }));

import { IntRow } from './FabricOverview';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
const ui = { openSource: vi.fn(), connect: vi.fn() };
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  ui.openSource.mockClear();
  ui.connect.mockClear();
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const base: Integration = { id: 'postgres', vendor: 'PostgreSQL', name: 'Database', cat: 'Data', type: 'db', status: 'connected', last: null, owner: 'Integration Engineering' };
const row = (x: Integration) => {
  act(() => root.render(<IntCtx.Provider value={ui as unknown as IntUI}><table><tbody><IntRow x={x} /></tbody></table></IntCtx.Provider>));
  return host.querySelector('tr')!;
};

describe('IntRow', () => {
  it('a source just connected, not yet in the sources list: pending, nothing to click, no crash', () => {
    const tr = row(base);
    expect(tr.querySelector('button')).toBeNull();
    expect(tr.querySelector('.frintn')?.getAttribute('aria-busy')).toBe('true');
    expect(tr.textContent).toContain('PostgreSQL');
    expect(tr.textContent).toContain('Connecting…');
  });

  it('a connected source opens its drawer', () => {
    const tr = row({ ...base, src: { id: 'postgres' } as Source });
    act(() => tr.querySelector<HTMLButtonElement>('button.frintn')!.click());
    expect(ui.openSource).toHaveBeenCalledWith('postgres', 'ov');
    expect(tr.querySelector('.menu')?.textContent).toBe('postgres');
  });

  it('a catalogue entry opens Connect', () => {
    const tr = row({ ...base, id: 'cat:postgres', status: 'available', c: { id: 'postgres' } as CatalogItem });
    act(() => tr.querySelector<HTMLButtonElement>('button.frintn')!.click());
    expect(ui.connect).toHaveBeenCalledWith('postgres');
    act(() => [...tr.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent === 'Connect')!.click());
    expect(ui.connect).toHaveBeenCalledTimes(2);
  });
});
