/**
 * The canvas edits a copy of each workflow (the demo edits S.wf.cur in place and marks it dirty). The copy lives here,
 * per workflow, so leaving the page and coming back keeps unsaved changes, and the list can say "unsaved changes".
 * Save and Publish send the copy through invoke(); Discard reloads the last saved version.
 */
import { useSyncExternalStore } from 'react';
import { graphOf, graphStamp, workflow, type Trigger, type WfGraph } from '../../api/workflows';

export interface Draft {
  id: string;
  graph: WfGraph;
  name: string;
  owner: string;
  trig: Trigger;
  dirty: boolean;
  /** "Leave with unsaved changes" was already warned once. */
  warned: boolean;
  /** ver|updated of the backend's graph this copy was taken from. */
  base: string;
  /** Undo / redo snapshots of the graph. */
  hist: { s: string[]; i: number };
  seq: number;
}

const drafts = new Map<string, Draft>();
let version = 0;
const subs = new Set<() => void>();
const emit = () => { version++; subs.forEach((f) => f()); };

export function useDrafts(): number {
  return useSyncExternalStore((f) => (subs.add(f), () => subs.delete(f)), () => version);
}

const baseOf = (id: string) => graphStamp(id);

function fresh(id: string): Draft {
  const w = workflow(id)!;
  const graph = graphOf(id);
  return {
    id, graph, name: w.name, owner: w.owner, trig: { ...w.trig }, dirty: !!w.dirty, warned: false, base: baseOf(id),
    hist: { s: [JSON.stringify(graph)], i: 0 }, seq: 100,
  };
}

/** The working copy for a workflow. A copy that is clean, or one an agent has since replaced, is refreshed from the backend. */
export function draftOf(id: string): Draft | null {
  const w = workflow(id);
  if (!w) { drafts.delete(id); return null; }
  let d = drafts.get(id);
  if (!d || (d.base !== baseOf(id) && (!d.dirty || w.dirty))) {
    d = fresh(id);
    drafts.set(id, d);
  }
  return d;
}

/** Does the list show "unsaved changes" for this workflow? */
export function isDirty(id: string): boolean {
  const d = drafts.get(id);
  return d ? d.dirty : !!workflow(id)?.dirty;
}

/** Change the copy. `track` adds an undo step; `dirty` marks it unsaved. */
export function edit(id: string, f: (d: Draft) => void, o: { dirty?: boolean; track?: boolean } = {}) {
  const d = draftOf(id);
  if (!d) return;
  f(d);
  if (o.dirty !== false) d.dirty = true;
  if (o.track) {
    const snap = JSON.stringify(d.graph), h = d.hist;
    if (h.s[h.i] !== snap) {
      h.s.length = h.i + 1;
      h.s.push(snap);
      if (h.s.length > 40) h.s.shift();
      h.i = h.s.length - 1;
    }
  }
  emit();
}

export function undoRedo(id: string, step: -1 | 1) {
  const d = draftOf(id);
  if (!d) return;
  const i = d.hist.i + step;
  if (i < 0 || i >= d.hist.s.length) return;
  d.hist.i = i;
  d.graph = JSON.parse(d.hist.s[i]);
  d.dirty = true;
  emit();
}

/** Replace the copy with the backend's version (after Save, Publish or Discard). */
export function reload(id: string, patch?: Partial<Draft>) {
  if (!workflow(id)) { drafts.delete(id); emit(); return; }
  const d = fresh(id);
  Object.assign(d, { dirty: false }, patch);
  drafts.set(id, d);
  emit();
}

export function forget(id: string) {
  drafts.delete(id);
  emit();
}

/** A step or connection id not used in the copy yet. */
export function nextId(d: Draft, p: string): string {
  const used = new Set([...d.graph.nodes.map((n) => n.id), ...d.graph.edges.map((x) => x.id)]);
  let id = p + ++d.seq;
  while (used.has(id)) id = p + ++d.seq;
  return id;
}
