import { afterEach, describe, expect, it, vi } from 'vitest';
import type { WfGraph } from '../../api/workflows';

/** A fake of the workflow facade the drafts read: the list entry, the backend's graph and its version stamp. */
const backend = vi.hoisted(() => new Map<string, { w: { id: string; name: string; owner: string; trig: { t: string; min?: number }; dirty: boolean }; graph: WfGraph; stamp: string }>());
/** The working copies kept on the server (workflow.draft.save / discard), and the calls made. */
const server = vi.hoisted(() => ({ drafts: new Map<string, Record<string, unknown>>(), saves: [] as Record<string, unknown>[], discards: [] as string[] }));
vi.mock('../../api/workflows', () => ({
  workflow: (id: string) => backend.get(id)?.w,
  graphOf: (id: string) => JSON.parse(JSON.stringify(backend.get(id)?.graph ?? { nodes: [], edges: [] })),
  graphStamp: (id: string) => backend.get(id)?.stamp ?? '',
  serverDraftOf: (id: string) => server.drafts.get(id) ?? null,
  saveDraft: async (d: { id: string }) => { server.saves.push(JSON.parse(JSON.stringify(d))); server.drafts.set(d.id, JSON.parse(JSON.stringify(d))); return { ok: true, output: { id: d.id, at: '' } }; },
  discardDraft: async (id: string) => { server.discards.push(id); server.drafts.delete(id); return { ok: true, output: { id, discarded: true } }; },
}));

import { AUTOSAVE_MS, draftOf, edit, forget, isDirty, nextId, reload, setCfg, undoRedo } from './draftStore';

const graph = (...ids: string[]): WfGraph => ({
  nodes: ids.map((id, i) => ({ id, k: 'xf', ref: 'x_utc', x: i * 200, y: 0 })),
  edges: ids.slice(1).map((b, i) => ({ id: 'e' + i, a: ids[i], b, locked: false })),
});
function seed(id: string, o: { dirty?: boolean; stamp?: string; g?: WfGraph } = {}) {
  backend.set(id, {
    w: { id, name: 'Ingest · ' + id, owner: 'Ops', trig: { t: 'schedule', min: 30 }, dirty: !!o.dirty },
    graph: o.g ?? graph('a', 'b'), stamp: o.stamp ?? '1.0|100',
  });
}
const addNode = (id: string) => (d: { graph: WfGraph }) => { d.graph.nodes.push({ id, k: 'xf', ref: 'x_utc', x: 0, y: 0 }); };

afterEach(() => {
  for (const id of backend.keys()) forget(id);
  backend.clear();
  server.drafts.clear();
  server.saves.length = 0;
  server.discards.length = 0;
  vi.useRealTimers();
});

describe('draftOf', () => {
  it('is null for a workflow the backend does not have', () => {
    expect(draftOf('WF-404')).toBeNull();
  });
  it('copies the backend graph, name, owner and trigger, stamped with the version it came from', () => {
    seed('WF-1');
    const d = draftOf('WF-1')!;
    expect(d).toMatchObject({ id: 'WF-1', name: 'Ingest · WF-1', owner: 'Ops', trig: { t: 'schedule', min: 30 }, dirty: false, warned: false, base: '1.0|100', seq: 100 });
    expect(d.graph).toEqual(graph('a', 'b'));
    expect(d.graph).not.toBe(backend.get('WF-1')!.graph);
    expect(d.trig).not.toBe(backend.get('WF-1')!.w.trig);
    expect(d.hist).toEqual({ s: [JSON.stringify(graph('a', 'b'))], i: 0 });
  });
  it('copies the run settings, with the demo\'s defaults (3 retries, alert when a run fails)', () => {
    seed('WF-1');
    expect(draftOf('WF-1')).toMatchObject({ retries: 3, alert: 'A run fails' });
    seed('WF-2');
    Object.assign(backend.get('WF-2')!.w, { retries: 0, alert: 'Never' });
    expect(draftOf('WF-2')).toMatchObject({ retries: 0, alert: 'Never' });
  });
  it('keeps the same copy while the backend version is unchanged', () => {
    seed('WF-1');
    expect(draftOf('WF-1')).toBe(draftOf('WF-1'));
  });
  it('takes over the backend dirty flag for a new copy', () => {
    seed('WF-1', { dirty: true });
    expect(draftOf('WF-1')!.dirty).toBe(true);
  });
});

describe('dirty detection', () => {
  it('isDirty follows the backend until a copy exists, then the copy', () => {
    seed('WF-1', { dirty: true });
    seed('WF-2');
    expect(isDirty('WF-1')).toBe(true);
    expect(isDirty('WF-2')).toBe(false);
    expect(isDirty('WF-404')).toBe(false);
    edit('WF-2', addNode('c'));
    expect(isDirty('WF-2')).toBe(true);
  });
  it('an edit marks the copy unsaved unless told not to', () => {
    seed('WF-1');
    edit('WF-1', (d) => { d.name = 'Renamed'; }, { dirty: false });
    expect(draftOf('WF-1')).toMatchObject({ name: 'Renamed', dirty: false });
    edit('WF-1', (d) => { d.owner = 'Finance'; });
    expect(draftOf('WF-1')).toMatchObject({ owner: 'Finance', dirty: true });
  });
  it('an edit to a missing workflow does nothing', () => {
    const f = vi.fn();
    edit('WF-404', f);
    expect(f).not.toHaveBeenCalled();
  });
});

describe('graph stamps: refreshing the copy when the backend changes', () => {
  it('a clean copy is replaced by the new backend version', () => {
    seed('WF-1');
    draftOf('WF-1');
    seed('WF-1', { stamp: '1.1|200', g: graph('a', 'b', 'c') });
    const d = draftOf('WF-1')!;
    expect(d.base).toBe('1.1|200');
    expect(d.graph.nodes.map((n) => n.id)).toEqual(['a', 'b', 'c']);
  });
  it('an unsaved copy is kept when the backend version moves on', () => {
    seed('WF-1');
    edit('WF-1', addNode('mine'));
    seed('WF-1', { stamp: '1.1|200', g: graph('x') });
    const d = draftOf('WF-1')!;
    expect(d.base).toBe('1.0|100');
    expect(d.graph.nodes.map((n) => n.id)).toEqual(['a', 'b', 'mine']);
  });
  it('an unsaved copy is replaced when an agent saved a dirty version in the backend', () => {
    seed('WF-1');
    edit('WF-1', addNode('mine'));
    seed('WF-1', { stamp: '1.1|200', g: graph('agent'), dirty: true });
    const d = draftOf('WF-1')!;
    expect(d.graph.nodes.map((n) => n.id)).toEqual(['agent']);
    expect(d.dirty).toBe(true);
  });
  it('a copy is dropped once the workflow is deleted', () => {
    seed('WF-1');
    draftOf('WF-1');
    backend.delete('WF-1');
    expect(draftOf('WF-1')).toBeNull();
    expect(isDirty('WF-1')).toBe(false);
  });
});

describe('undo and redo', () => {
  it('tracked edits add history steps; identical snapshots are not repeated', () => {
    seed('WF-1');
    edit('WF-1', addNode('c'), { track: true });
    edit('WF-1', () => undefined, { track: true });
    expect(draftOf('WF-1')!.hist.s).toHaveLength(2);
    expect(draftOf('WF-1')!.hist.i).toBe(1);
  });
  it('steps back and forward and marks the copy unsaved', () => {
    seed('WF-1');
    edit('WF-1', addNode('c'), { track: true, dirty: false });
    undoRedo('WF-1', -1);
    expect(draftOf('WF-1')!.graph.nodes.map((n) => n.id)).toEqual(['a', 'b']);
    expect(draftOf('WF-1')!.dirty).toBe(true);
    undoRedo('WF-1', 1);
    expect(draftOf('WF-1')!.graph.nodes.map((n) => n.id)).toEqual(['a', 'b', 'c']);
  });
  it('does nothing past either end', () => {
    seed('WF-1');
    undoRedo('WF-1', -1);
    expect(draftOf('WF-1')).toMatchObject({ dirty: false, hist: { i: 0 } });
    undoRedo('WF-1', 1);
    expect(draftOf('WF-1')!.hist.i).toBe(0);
  });
  it('a new edit after undo drops the redo steps', () => {
    seed('WF-1');
    edit('WF-1', addNode('c'), { track: true });
    undoRedo('WF-1', -1);
    edit('WF-1', addNode('d'), { track: true });
    const h = draftOf('WF-1')!.hist;
    expect(h.s.map((s) => (JSON.parse(s) as WfGraph).nodes.map((n) => n.id).join())).toEqual(['a,b', 'a,b,d']);
    undoRedo('WF-1', 1);
    expect(draftOf('WF-1')!.graph.nodes.map((n) => n.id)).toEqual(['a', 'b', 'd']);
  });
  it('keeps at most 40 snapshots', () => {
    seed('WF-1');
    for (let i = 0; i < 50; i++) edit('WF-1', addNode('n' + i), { track: true });
    const h = draftOf('WF-1')!.hist;
    expect(h.s).toHaveLength(40);
    expect(h.i).toBe(39);
  });
});

describe('reload and forget', () => {
  it('reload replaces the copy with the backend version, clean, with the patch applied', () => {
    seed('WF-1', { dirty: true });
    edit('WF-1', addNode('mine'));
    reload('WF-1', { warned: true });
    expect(draftOf('WF-1')).toMatchObject({ dirty: false, warned: true });
    expect(draftOf('WF-1')!.graph).toEqual(graph('a', 'b'));
  });
  it('reload of a deleted workflow drops the copy', () => {
    seed('WF-1');
    edit('WF-1', addNode('mine'));
    backend.delete('WF-1');
    reload('WF-1');
    seed('WF-1');
    expect(draftOf('WF-1')!.graph).toEqual(graph('a', 'b'));
  });
  it('forget drops unsaved changes', () => {
    seed('WF-1');
    edit('WF-1', addNode('mine'));
    forget('WF-1');
    expect(isDirty('WF-1')).toBe(false);
    expect(draftOf('WF-1')!.graph).toEqual(graph('a', 'b'));
  });
});

describe('nextId', () => {
  it('counts up from the copy sequence, skipping ids already used by steps or connections', () => {
    seed('WF-1', { g: { nodes: [{ id: 'n101', k: 'xf', ref: 'x_utc', x: 0, y: 0 }], edges: [{ id: 'n102', a: 'n101', b: 'n101', locked: false }] } });
    const d = draftOf('WF-1')!;
    expect(nextId(d, 'n')).toBe('n103');
    expect(d.seq).toBe(103);
    expect(nextId(d, 'e')).toBe('e104');
  });
});

describe('setCfg (block settings)', () => {
  it('sets one setting, marks the copy unsaved and can be undone', () => {
    seed('WF-1');
    setCfg('WF-1', 'a', 'currency', 'EUR');
    const d = draftOf('WF-1')!;
    expect(d.dirty).toBe(true);
    expect(d.graph.nodes[0].cfg).toEqual({ currency: 'EUR' });
    setCfg('WF-1', 'a', 'rate_date', 'run');
    expect(d.graph.nodes[0].cfg).toEqual({ currency: 'EUR', rate_date: 'run' });
    undoRedo('WF-1', -1);
    expect(draftOf('WF-1')!.graph.nodes[0].cfg).toEqual({ currency: 'EUR' });
    undoRedo('WF-1', -1);
    expect(draftOf('WF-1')!.graph.nodes[0].cfg).toBeUndefined();
    undoRedo('WF-1', 1);
    expect(draftOf('WF-1')!.graph.nodes[0].cfg).toEqual({ currency: 'EUR' });
  });
  it('ignores a step that is not in the copy', () => {
    seed('WF-1');
    setCfg('WF-1', 'zz', 'currency', 'EUR');
    expect(draftOf('WF-1')!.graph.nodes.every((n) => n.cfg === undefined)).toBe(true);
  });
});

describe('drafts on the server (plan 6 C9)', () => {
  it('autosaves an unsaved copy after two seconds of quiet, once per burst of changes', async () => {
    vi.useFakeTimers();
    seed('WF-1');
    edit('WF-1', addNode('c'), { track: true });
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS - 500);
    edit('WF-1', addNode('d'), { track: true });
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS - 1);
    expect(server.saves).toEqual([]);
    await vi.advanceTimersByTimeAsync(1);
    expect(server.saves).toHaveLength(1);
    expect(server.saves[0]).toMatchObject({ id: 'WF-1', name: 'Ingest · WF-1', owner: 'Ops', retries: 3, alert: 'A run fails', base: '1.0|100' });
    expect((server.saves[0].graph as WfGraph).nodes.map((n) => n.id)).toEqual(['a', 'b', 'c', 'd']);
  });
  it('does not autosave a change that leaves the copy clean', async () => {
    vi.useFakeTimers();
    seed('WF-1');
    edit('WF-1', (d) => { d.warned = true; }, { dirty: false });
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS * 2);
    expect(server.saves).toEqual([]);
  });
  it('undo and redo are autosaved too', async () => {
    vi.useFakeTimers();
    seed('WF-1');
    edit('WF-1', addNode('c'), { track: true });
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    undoRedo('WF-1', -1);
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(server.saves).toHaveLength(2);
    expect((server.saves[1].graph as WfGraph).nodes.map((n) => n.id)).toEqual(['a', 'b']);
  });
  it('a reload (no copy in memory) takes up the copy kept on the server, still unsaved', async () => {
    vi.useFakeTimers();
    seed('WF-1');
    edit('WF-1', (d) => { d.name = 'Renamed'; addNode('c')(d); }, { track: true });
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    forgetLocal('WF-1'); // what a page reload or a new sign-in does: the memory is gone, the server keeps the copy
    const d = draftOf('WF-1')!;
    expect(d).toMatchObject({ name: 'Renamed', dirty: true, base: '1.0|100' });
    expect(d.graph.nodes.map((n) => n.id)).toEqual(['a', 'b', 'c']);
    expect(isDirty('WF-1')).toBe(true);
  });
  it('Save, Publish or Discard (reload) drops the copy on the server and cancels a pending autosave', async () => {
    vi.useFakeTimers();
    seed('WF-1');
    edit('WF-1', addNode('c'), { track: true });
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    edit('WF-1', addNode('d'), { track: true });
    reload('WF-1');
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS * 2);
    expect(server.saves).toHaveLength(1);
    expect(server.discards).toEqual(['WF-1']);
    expect(server.drafts.has('WF-1')).toBe(false);
    forgetLocal('WF-1');
    expect(draftOf('WF-1')).toMatchObject({ dirty: false });
  });
  it('does not ask the server to discard a copy it never kept', () => {
    seed('WF-1');
    draftOf('WF-1');
    reload('WF-1');
    expect(server.discards).toEqual([]);
  });
});

/** Drop the in-memory copies as a page reload does (the module state is fresh; the server keeps its copies). */
function forgetLocal(id: string) {
  const keep = new Map(server.drafts);
  forget(id);
  server.drafts.clear();
  keep.forEach((v, k) => server.drafts.set(k, v));
  server.discards.length = 0;
}
