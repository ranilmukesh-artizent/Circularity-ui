// @vitest-environment jsdom
// P9-8.15: a node's input, output and held records; table or JSON; "Pin this input".
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { NodeSamples, nodeIo } from './NodeSamples';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });

const input = [{ ext_id: 'PO-1', resource: 'orders', data: { qty: 3, site: 'Dallas' } }, { ext_id: 'PO-2', resource: 'orders', data: { qty: 5, site: 'Austin' } }];
const output = [{ ext_id: 'PO-1', resource: 'orders', data: { qty: 3 } }];
const held = [{ ext_id: 'PO-2', resource: 'orders', rule: 'required', field: 'site', reason: 'Site is missing' }];

const click = (el: Element | null | undefined) => act(() => { (el as HTMLElement).dispatchEvent(new MouseEvent('click', { bubbles: true })); });
const byText = (sel: string, t: string) => [...host.querySelectorAll(sel)].find((e) => e.textContent?.trim() === t);

describe('NodeSamples', () => {
  it('switches between table and JSON', () => {
    act(() => root.render(<NodeSamples input={input} output={output} held={[]} />));
    expect(host.querySelector('table')).not.toBeNull();
    expect(host.textContent).toContain('PO-2');
    click(byText('button', 'JSON'));
    expect(host.querySelector('table')).toBeNull();
    expect(host.querySelector('pre.code')?.textContent).toContain('"ext_id": "PO-1"');
    click(byText('button', 'Table'));
    expect(host.querySelector('table')).not.toBeNull();
  });

  it('shows the output tab and the held tab with each reason', () => {
    act(() => root.render(<NodeSamples input={input} output={output} held={held} />));
    click(byText('[role=tab]', 'Output'));
    expect(host.querySelectorAll('tbody tr')).toHaveLength(1);
    click(byText('[role=tab]', 'Held (1)'));
    expect(host.textContent).toContain('Site is missing');
    expect(host.textContent).toContain('required');
  });

  it('pins the input records', () => {
    const onPin = vi.fn();
    act(() => root.render(<NodeSamples input={input} output={output} held={[]} onPin={onPin} />));
    click(byText('button', 'Pin this input'));
    expect(onPin).toHaveBeenCalledWith(input);
    act(() => root.render(<NodeSamples input={input} output={output} held={[]} onPin={onPin} pinned />));
    expect(byText('button', 'Pinned. Unpin')).toBeDefined();
  });
});

describe('nodeIo', () => {
  it('reads "in → out" and "in → out · n held"', () => {
    expect(nodeIo({ in: 3, out: 3, rej: 0 })).toBe('3 → 3');
    expect(nodeIo({ in: 3, out: 2, rej: 1 })).toBe('3 → 2 · 1 held');
  });
});
