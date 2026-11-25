// @vitest-environment jsdom
import { act, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { WfGraph, Workflow } from '../../api/workflows';

/** The facade reads the backend; the canvas needs only these. Everything else is the real module. */
const backend = vi.hoisted(() => new Map<string, WfGraph>());
const toasts = vi.hoisted(() => [] as string[]);
vi.mock('../../components/toast', () => ({ toast: (m: string) => { toasts.push(m); } }));
vi.mock('../../api/workflows', async (orig) => ({
  ...(await orig<typeof import('../../api/workflows')>()),
  workflow: (id: string) => (backend.has(id) ? { id, name: id, owner: 'Ops', trig: { t: 'manual' }, dirty: false } : undefined),
  graphOf: (id: string) => JSON.parse(JSON.stringify(backend.get(id))),
  graphStamp: () => '1|1',
  serverDraftOf: () => null,
  saveDraft: async () => ({ ok: true, output: {} }),
  discardDraft: async () => ({ ok: true, output: {} }),
  stepInfo: (n: { id: string; k: string }) => ({ label: 'Step ' + n.id, sub: 'sub', tag: n.k === 'fixed' ? 'Fixed · core' : 'Movable · step', desc: '', in: n.id !== 'a', out: true }),
  nodeMark: () => ({ ic: 'workflow', h: 'insp' }),
  RUN_LABEL: () => ({}),
  canLink: (_g: WfGraph, a: string, b: string) => (a === 'a' && b === 'c' ? 'A cannot send straight to C.' : null),
}));

import { draftOf, forget, useDrafts } from './draftStore';
import { CanvasView, canvasOps, FIXMSG, type Sel } from './Canvas';

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
  forget('W1');
  backend.clear();
});

/** a (fixed) → b → c; `placed` false drops the coordinates, as a generated graph has none. */
function seed(placed: boolean) {
  const at = (x: number) => (placed ? { x, y: 40 } : {});
  backend.set('W1', {
    nodes: [
      { id: 'a', k: 'fixed', ref: 'canon', ...at(0) }, { id: 'b', k: 'xf', ref: 'x_utc', ...at(300) }, { id: 'c', k: 'act', ref: 'email', ...at(600) },
    ] as WfGraph['nodes'],
    edges: [{ id: 'e1', a: 'a', b: 'b', locked: true }],
  });
}

let ops: ReturnType<typeof canvasOps>;
function Harness({ first }: { first: Sel }) {
  useDrafts();
  const d = draftOf('W1')!;
  const [sel, setSel] = useState<Sel>(first);
  ops = canvasOps(d, 'pipe', setSel, () => {});
  return (
    <div style={{ width: 900, height: 500 }}>
      <CanvasView w={{ kind: 'pipe', last: null } as unknown as Workflow} d={d} sel={sel} run={null} checks={[]} counts={{}} flow={false} mini readOnly={false}
        onSel={setSel} ops={ops} changed={() => {}} apiRef={{ current: null }} toolbar={null} />
    </div>
  );
}
const mount = async (first: Sel = null) => { await act(async () => { root.render(<Harness first={first} />); await new Promise((r) => setTimeout(r, 20)); }); };
const press = (key: string) => act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true })); });

describe('Studio canvas on xyflow (P9-8.13)', () => {
  it('renders every node of a graph that has no positions, and stores the layout it made', async () => {
    seed(false);
    await mount();
    expect(host.querySelectorAll('.wfn')).toHaveLength(3);
    const g = draftOf('W1')!.graph;
    expect(g.nodes.every((n) => Number.isFinite(n.x) && Number.isFinite(n.y))).toBe(true);
    expect(draftOf('W1')!.dirty).toBe(false);
  });

  it('keeps the stored positions of a placed graph', async () => {
    seed(true);
    await mount();
    expect(draftOf('W1')!.graph.nodes.map((n) => n.x)).toEqual([0, 300, 600]);
  });

  it('a fixed node cannot be deleted: the FIXMSG toast, the node stays', async () => {
    seed(true);
    await mount({ t: 'n', id: 'a' });
    await press('Delete');
    expect(toasts).toContain(FIXMSG);
    expect(draftOf('W1')!.graph.nodes.map((n) => n.id)).toContain('a');
  });

  it('Delete removes a movable node and its links', async () => {
    seed(true);
    await mount({ t: 'n', id: 'b' });
    await press('Delete');
    expect(draftOf('W1')!.graph.nodes.map((n) => n.id)).toEqual(['a', 'c']);
    expect(draftOf('W1')!.graph.edges).toHaveLength(0);
  });

  it('an arrow key moves a movable node by 8 px and refuses a fixed one', async () => {
    seed(true);
    await mount({ t: 'n', id: 'b' });
    await press('ArrowRight');
    expect(draftOf('W1')!.graph.nodes.find((n) => n.id === 'b')!.x).toBe(308);
  });

  it('an arrow key on a fixed node toasts FIXMSG and does not move it', async () => {
    seed(true);
    await mount({ t: 'n', id: 'a' });
    await press('ArrowDown');
    expect(toasts).toContain(FIXMSG);
    expect(draftOf('W1')!.graph.nodes[0].y).toBe(40);
  });

  it('a connection canLink refuses is not added, and says why', async () => {
    seed(true);
    await mount();
    expect(ops.link('a', 'c')).toBe(false);
    expect(toasts).toContain('A cannot send straight to C.');
    expect(draftOf('W1')!.graph.edges).toHaveLength(1);
    expect(ops.link('b', 'c')).toBe(true);
    expect(draftOf('W1')!.graph.edges).toHaveLength(2);
  });
});
