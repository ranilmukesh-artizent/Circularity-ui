import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  applyProposal: vi.fn(async () => ({ ok: true, output: { id: 1, checks: [] } })),
  applySuggestion: vi.fn(),
  saveDraft: vi.fn(async () => ({ ok: true, output: { id: 1, checks: [] } })),
  ruleSuggestions: vi.fn(),
}));
vi.mock('../../../api/modeler', () => m);

import type { FlowGraph } from '../../../api/types';
import { registerSurface, type FlowSurface } from '../../../utils/workSurface';
import { applyPending, canUndo, canon, changeState, dismissPending, pendingOfSentence, setPending, undoApplied } from './changeStore';
import type { Proposal } from '../../../api/modeler';

const n = (id: string) => ({ id, t: 'rule', x: 0, y: 0, label: id, sub: '', h: 60, lock: false }) as never;
const before: FlowGraph = { nodes: [n('a')], edges: [] };
const after: FlowGraph = { nodes: [n('a'), n('b')], edges: [] };
const proposal = { kind: 'rule', text: 'Never x', graph: after, node_id: 'b', rid: 'IR-02', label: 'IR-02: never x', guard: null, checks: [], sim: null, msg: '', note: 'Proposed by the assistant: Never x', read_by: 'rules' } as Proposal;

/** A surface the way the Modeler page implements it: applyGraph runs the call, then the page's graph is the proposed one. */
function surface(canEdit = true) {
  let graph = before;
  const sf = {
    kind: 'flow', flowId: 4, name: 'Industrial returns', template: 'industrial', org: 'workspace', canEdit, draftVer: 2,
    graph: () => graph, flush: vi.fn(async () => {}), showProposal: vi.fn(), select: vi.fn(),
    applyGraph: vi.fn(async (g: FlowGraph, _id: string | null, call: () => Promise<{ ok: boolean }>) => ((await call()).ok ? ((graph = g), true) : false)),
  } satisfies Partial<FlowSurface> as unknown as FlowSurface;
  return { sf, edit: (g: FlowGraph) => (graph = g) };
}

const tick = () => new Promise((r) => setTimeout(r, 5));

beforeEach(() => {
  vi.clearAllMocks();
  registerSurface(null);
});

describe('canon', () => {
  it('compares graphs whatever their key order', () => {
    expect(canon({ a: 1, b: { d: 1, c: [{ y: 1, x: 2 }] } })).toBe(canon({ b: { c: [{ x: 2, y: 1 }], d: 1 }, a: 1 }));
    expect(canon({ a: 1 })).not.toBe(canon({ a: 2 }));
  });
});

describe('Apply to draft, Undo and the stale draft (plan 10, 2.7 and 2.10)', () => {
  it('applies as the person (the proposal\'s own saveDraft through the surface), then offers Undo', async () => {
    const { sf } = surface();
    registerSurface(sf);
    setPending(pendingOfSentence(proposal, 'Never x', 1, sf));
    expect(sf.showProposal).toHaveBeenCalledWith(proposal);
    expect(await applyPending(false)).toBe(true);
    expect(m.applyProposal).toHaveBeenCalledWith(4, proposal);
    expect(sf.applyGraph).toHaveBeenCalledWith(after, null, expect.any(Function));
    expect(changeState().pending).toBeNull();
    expect(changeState().outcomes[1]).toBe('applied');
    expect(canUndo()).toBe(true);
  });

  it('Apply and adjust selects the new rule in the Inspector', async () => {
    const { sf } = surface();
    registerSurface(sf);
    setPending(pendingOfSentence(proposal, 'Never x', 1, sf));
    await applyPending(true);
    expect(sf.applyGraph).toHaveBeenCalledWith(after, 'b', expect.any(Function));
    expect(sf.select).toHaveBeenCalledWith('b', 'inspector');
  });

  it('Undo is the person\'s own saveDraft of the earlier graph, noted; the journal names what it undoes', async () => {
    const { sf } = surface();
    registerSurface(sf);
    setPending(pendingOfSentence(proposal, 'Never x', 1, sf));
    await applyPending(false);
    expect(await undoApplied()).toBe(true);
    expect(m.saveDraft).toHaveBeenCalledWith(4, before, "Undid the assistant's change: Never x");
    expect(changeState().applied).toBeNull();
    expect(changeState().outcomes[1]).toBe('undone');
  });

  it('Undo goes away once the draft was edited afterwards, and does nothing', async () => {
    const { sf, edit } = surface();
    registerSurface(sf);
    setPending(pendingOfSentence(proposal, 'Never x', 1, sf));
    await applyPending(false);
    edit({ nodes: [n('a'), n('b'), n('c')], edges: [] });
    expect(canUndo()).toBe(false);
    expect(await undoApplied()).toBe(false);
    expect(m.saveDraft).not.toHaveBeenCalled();
  });

  it('refuses, as stale, when the working graph is no longer the one the proposal was made on', async () => {
    const { sf, edit } = surface();
    registerSurface(sf);
    setPending(pendingOfSentence(proposal, 'Never x', 1, sf));
    edit({ nodes: [n('a'), n('z')], edges: [] });
    expect(await applyPending(false)).toBe(false);
    expect(changeState().stale).toBe(true);
    expect(m.applyProposal).not.toHaveBeenCalled();
  });

  it('never applies for a person without edit rights, nor a blocked proposal', async () => {
    const ro = surface(false);
    registerSurface(ro.sf);
    setPending(pendingOfSentence(proposal, 'Never x', 1, ro.sf));
    expect(await applyPending(false)).toBe(false);
    const rw = surface();
    registerSurface(rw.sf);
    setPending(pendingOfSentence({ ...proposal, kind: 'blocked' }, 'Never x', 2, rw.sf));
    expect(await applyPending(false)).toBe(false);
    expect(m.applyProposal).not.toHaveBeenCalled();
  });

  it('Dismiss clears the canvas and records it; leaving the flow drops what was held', async () => {
    const { sf } = surface();
    registerSurface(sf);
    setPending(pendingOfSentence(proposal, 'Never x', 3, sf));
    dismissPending();
    expect(sf.showProposal).toHaveBeenLastCalledWith(null);
    expect(changeState().outcomes[3]).toBe('dismissed');
    setPending(pendingOfSentence(proposal, 'Never x', 4, sf));
    registerSurface(null);
    registerSurface(sf); // a page re-registering on every change passes through null for an instant: nothing is dropped
    await tick();
    expect(changeState().pending).not.toBeNull();
    registerSurface(null);
    await tick();
    expect(changeState().pending).toBeNull();
  });
});
