// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Check } from '../../api/types';

vi.mock('../../components/Icon', () => ({ Icon: ({ name }: { name: string }) => <svg data-icon={name} /> }));

import { ChecksPanel } from './ChecksPanel';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement;
let root: Root;
beforeAll(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
});
beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const checks: Check[] = [
  { level: 'fail', msg: 'IR-01 has no path to an outcome', node_id: 'r1' },
  { level: 'warn', msg: 'IR-02 never matches an open case', node_id: 'r2' },
  { level: 'ok', msg: 'Every outcome reaches owner approval', node_id: null },
];

describe('ChecksPanel', () => {
  it('draws a failing check with the alert icon and selects its step on click', () => {
    const onSelect = vi.fn();
    act(() => root.render(<ChecksPanel checks={checks} onSelect={onSelect} />));
    const fail = host.querySelector('li.fail')!;
    expect(fail.querySelector('svg')?.getAttribute('data-icon')).toBe('alert');
    act(() => fail.querySelector('button')!.click());
    expect(onSelect).toHaveBeenCalledWith('r1');
  });
  it('uses the check icon for a pass and no ✓ ✕ ! glyph anywhere', () => {
    act(() => root.render(<ChecksPanel checks={checks} onSelect={() => {}} />));
    expect(host.querySelector('li.ok svg')?.getAttribute('data-icon')).toBe('check');
    expect(host.textContent).not.toMatch(/[✓✕⚠]/);
    expect(host.querySelector('.ic')).toBeNull();
  });
  it('says how many checks block, in sentence case', () => {
    act(() => root.render(<ChecksPanel checks={checks} onSelect={() => {}} />));
    expect(host.textContent).toContain('1 blocking');
    expect(host.querySelector('h3')?.textContent).toBe('Checks');
  });
});
