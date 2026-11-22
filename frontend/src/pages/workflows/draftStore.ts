/**
 * The canvas edits a copy of each workflow (the demo edits S.wf.cur in place and marks it dirty). The copy lives here,
 * per workflow, so leaving the page and coming back keeps unsaved changes, and the list can say "unsaved changes".
 * Save and Publish send the copy through invoke(); Discard reloads the last saved version.
 *
 * The copy is also kept on the server (plan 6 C9): an unsaved copy is autosaved (workflow.draft.save) after
 * AUTOSAVE_MS of quiet, and when the workflow opens with no copy in memory (a reload, a new sign-in) the person's saved
 * copy is taken up again, still unsaved. Save, Publish, Discard and a restored version drop it (workflow.draft.discard).
 */
import { useSyncExternalStore } from 'react';
import { discardDraft, graphOf, graphStamp, saveDraft, serverDraftOf, workflow, type Trigger, type WfGraph } from '../../api/workflows';
import { sessionScoped } from '../../api/view';

export interface Draft {
  id: string;
  graph: WfGraph;
  name: string;
  owner: string;
  trig: Trigger;
  /** The run settings (Settings tab): retries 0, 1, 3 or 5 (default 3) and when to alert (default "A run fails"). */
  retries: number;
  alert: string;
  dirty: boolean;
  /** "Leave with unsaved changes" was already warned once. */
  warned: boolean;
  /** ver|updated of the backend's graph this copy was taken from. */
  base: string;
  /** Undo / redo snapshots of the graph. */
  hist: { s: string[]; i: number };
  seq: number;
}

// unsaved copies belong to the user who made them: a sign-in or sign-out drops them from memory (the server keeps them)
const drafts = sessionScoped(() => new Map<string, Draft>());
/** Workflows whose copy may be kept on the server (autosaved or taken up from there), so Save or Discard drops it. */
const onServer = sessionScoped(() => new Set<string>());
/** Two seconds of quiet before an unsaved copy is autosaved. */
export const AUTOSAVE_MS = 2000;
const timers = new Map<string, ReturnType<typeof setTimeout>>();
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
    id, graph, name: w.name, owner: w.owner, trig: { ...w.trig }, retries: w.retries ?? 3, alert: w.alert || 'A run fails',
    dirty: !!w.dirty, warned: false, base: baseOf(id),
    hist: { s: [JSON.stringify(graph)], i: 0 }, seq: 100,
  };
}

/** The person's copy kept on the server, taken up as an unsaved copy (null when there is none). */
function fromServer(id: string): Draft | null {
  const s = serverDraftOf(id);
  if (!s) return null;
  const d = fresh(id);
  Object.assign(d, {
    graph: s.graph, name: s.name, owner: s.owner ?? d.owner, trig: s.trig ? { ...s.trig } : d.trig, retries: s.retries ?? d.retries,
    alert: s.alert || d.alert, base: s.base ?? d.base, dirty: true, hist: { s: [JSON.stringify(s.graph)], i: 0 },
  });
  onServer.current.add(id);
  return d;
}

/** The working copy for a workflow: the one in memory, else the person's copy on the server, else the backend's
 *  version. A copy that is clean, or one an agent has since replaced, is refreshed from the backend. */
export function draftOf(id: string): Draft | null {
  const w = workflow(id);
  if (!w) { drafts.current.delete(id); return null; }
  let d = drafts.current.get(id);
  if (!d) {
    d = fromServer(id) ?? fresh(id);
    drafts.current.set(id, d);
  } else if (d.base !== baseOf(id) && (!d.dirty || w.dirty)) {
    d = fresh(id);
    drafts.current.set(id, d);
  }
  return d;
}

// ---- autosave (workflow.draft.save)
function cancel(id: string) {
  const t = timers.get(id);
  if (t !== undefined) clearTimeout(t);
  timers.delete(id);
}
/** Autosave the copy after AUTOSAVE_MS without another change. */
function schedule(id: string) {
  cancel(id);
  timers.set(id, setTimeout(() => { timers.delete(id); void push(id); }, AUTOSAVE_MS));
}
async function push(id: string) {
  const d = drafts.current.get(id);
  if (!d || !d.dirty) return;
  onServer.current.add(id);
  try {
    await saveDraft({ id, graph: d.graph, name: d.name, owner: d.owner, trig: d.trig, retries: d.retries, alert: d.alert, base: d.base });
  } catch {
    // best effort: the copy stays in memory and the next change tries again
  }
}
/** Drop the copy kept on the server, if there may be one. */
function drop(id: string) {
  cancel(id);
  if (!onServer.current.delete(id)) return;
  discardDraft(id).catch(() => undefined);
}

/** Does the list show "unsaved changes" for this workflow? */
export function isDirty(id: string): boolean {
  const d = drafts.current.get(id);
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
  if (d.dirty) schedule(id);
  emit();
}

/** Change one block setting of a step (an undo step; marks the copy unsaved). The server keeps only the settings that
 *  differ from the defaults, so setting a value back to its default needs no special case here. */
export function setCfg(id: string, nodeId: string, key: string, value: unknown) {
  edit(id, (d) => {
    const n = d.graph.nodes.find((x) => x.id === nodeId);
    if (n) n.cfg = { ...(n.cfg ?? {}), [key]: value };
  }, { track: true });
}

export function undoRedo(id: string, step: -1 | 1) {
  const d = draftOf(id);
  if (!d) return;
  const i = d.hist.i + step;
  if (i < 0 || i >= d.hist.s.length) return;
  d.hist.i = i;
  d.graph = JSON.parse(d.hist.s[i]);
  d.dirty = true;
  schedule(id);
  emit();
}

/** Replace the copy with the backend's version (after Save, Publish or Discard); the copy on the server goes. */
export function reload(id: string, patch?: Partial<Draft>) {
  drop(id);
  if (!workflow(id)) { drafts.current.delete(id); emit(); return; }
  const d = fresh(id);
  Object.assign(d, { dirty: false }, patch);
  drafts.current.set(id, d);
  emit();
}

/** Forget the copy (a deleted workflow, a restored version); the copy on the server goes too. */
export function forget(id: string) {
  drop(id);
  drafts.current.delete(id);
  emit();
}

/** A step or connection id not used in the copy yet. */
export function nextId(d: Draft, p: string): string {
  const used = new Set([...d.graph.nodes.map((n) => n.id), ...d.graph.edges.map((x) => x.id)]);
  let id = p + ++d.seq;
  while (used.has(id)) id = p + ++d.seq;
  return id;
}
