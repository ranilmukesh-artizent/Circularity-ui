// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FlowGraph, FlowNode, ModelerScreen } from '../../api/types';

const toasts = vi.hoisted(() => [] as string[]);
vi.mock('../../components/toast', () => ({ toast: (m: string) => { toasts.push(m); } }));

import { FlowCanvas } from './FlowCanvas';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

/** jsdom does no layout: the stubs React Flow's own testing guide asks for. */
class ResizeObserverStub {
  constructor(private cb: ResizeObserverCallback) {}
  observe(target: Element) { setTimeout(() => this.cb([{ target } as ResizeObserverEntry], this as unknown as ResizeObserver), 0); }
  unobserve() {}
  disconnect() {}
}
class DOMMatrixStub { m22 = 1; }

beforeAll(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  Object.assign(globalThis, { ResizeObserver: ResizeObserverStub, DOMMatrixReadOnly: DOMMatrixStub });
  Object.defineProperties(HTMLElement.prototype, {
    offsetHeight: { get() { return parseFloat(this.style.height) || 1; } },
    offsetWidth: { get() { return parseFloat(this.style.width) || 1; } },
  });
  (SVGElement.prototype as unknown as { getBBox: () => object }).getBBox = () => ({ x: 0, y: 0, width: 0, height: 0 });
});

let host: HTMLDivElement, root: Root;
beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  toasts.length = 0;
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const n = (id: string, t: FlowNode['t'], x: number, y: number, extra: Partial<FlowNode> = {}): FlowNode => ({
  id, t, x, y, label: id, sub: '', h: 112, lock: !['rule', 'path', 'step'].includes(t), ...extra,
}); // prettier-ignore
const graph: FlowGraph = {
  nodes: [n('gate', 'gate', 100, 40), n('r1', 'rule', 100, 190, { rid: 'BR-01', action: 'exclude', path: null, owner: 'Ops' })],
  edges: [{ id: 'gate>r1', a: 'gate', b: 'r1', l: '' }],
};
const screen = {
  band: [60, 10, 300, 200, 'Core prediction and agents · fixed'],
  template: { paths: [] },
  flow: { returned: null },
} as unknown as ModelerScreen;

function mount(over: Partial<Parameters<typeof FlowCanvas>[0]> = {}) {
  const calls = { remove: [] as string[], disc: [] as string[], conn: [] as string[], move: [] as string[] };
  const props = {
    s: screen, graph, selected: null, bad: new Set<string>(), editable: true,
    onSelect: () => {}, onMove: (id: string) => calls.move.push(id), onMoved: () => {},
    onConnect: (a: string, b: string) => calls.conn.push(a + '>' + b), onRemove: (id: string) => calls.remove.push(id),
    onDisconnect: (id: string) => calls.disc.push(id),
    ...over,
  };
  return { calls, go: () => act(async () => { root.render(<div style={{ width: 900, height: 500 }}><FlowCanvas {...props} /></div>); await new Promise((r) => setTimeout(r, 20)); }) };
}
const press = (key: string) => act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true })); });

describe('Modeler canvas on xyflow (P9-8.14)', () => {
  it('draws every node with its lock and the band label', async () => {
    const m = mount();
    await m.go();
    expect(host.querySelectorAll('.mdl-node')).toHaveLength(2);
    expect(host.textContent).toContain('Core prediction and agents · fixed');
    expect(host.querySelector('[data-node="gate"] .mdl-lock')).not.toBeNull();
  });

  it('a lock node delete is a no-op: nothing is removed, the person is told', async () => {
    const m = mount({ selected: 'gate' });
    await m.go();
    await press('Delete');
    expect(m.calls.remove).toEqual([]);
    expect(toasts).toContain('Locked steps cannot be removed.');
  });

  it('Delete on a rule node asks the page to remove it', async () => {
    const m = mount({ selected: 'r1' });
    await m.go();
    await press('Delete');
    expect(m.calls.remove).toEqual(['r1']);
  });

  it('a read-only canvas removes nothing', async () => {
    const m = mount({ selected: 'r1', editable: false });
    await m.go();
    await press('Delete');
    expect(m.calls.remove).toEqual([]);
  });

  it('a proposed rule node has class prop', async () => {
    const m = mount({ proposed: 'r1' });
    await m.go();
    expect(host.querySelector('[data-node="r1"]')!.classList.contains('prop')).toBe(true);
    expect(host.querySelector('[data-node="gate"]')!.classList.contains('prop')).toBe(false);
  });
});
