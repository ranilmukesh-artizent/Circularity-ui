/**
 * Change flow mode's working state (plan 10, T2): the proposal waiting for the person, the last apply (for Undo) and how
 * each turn ended. One module-level value, so the transcript turn and the column's Proposals section show the same
 * thing. Every write here is the person's own `flow.saveDraft` through the surface the Modeler registered
 * (`applyGraph`), never the assistant's (rule 10): the assistant only proposes; Undo is a saveDraft of the earlier graph.
 */
import { useSyncExternalStore } from 'react';
import { applyProposal, applySuggestion, ruleSuggestions, saveDraft, type Proposal, type RuleSuggestion, type RuleSuggestions } from '../../../api/modeler';
import type { FlowGraph } from '../../../api/types';
import { undoAvailable, undoNote } from '../../../pages/modeler/proposal';
import { currentSurface, onSurfaceChange, type FlowSurface } from '../../../utils/workSurface';

/** A graph as text with its keys in order: the server's copy and the page's copy compare equal whatever their key order. */
export function canon(v: unknown): string {
  const sort = (x: unknown): unknown =>
    Array.isArray(x) ? x.map(sort) : x && typeof x === 'object' ? Object.fromEntries(Object.entries(x as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : 1)).map(([k, y]) => [k, sort(y)])) : x;
  return JSON.stringify(sort(v));
}

export interface Pending {
  flowId: number;
  proposal: Proposal;
  /** the person's sentence, or the suggestion's text */
  text: string;
  key: number | null;
  /** the working graph when it was proposed: if it differs at apply time, the draft changed under the proposal */
  baseJson: string;
  /** how it is saved: the person's own flow.saveDraft with the assistant's note */
  save(flowId: number): ReturnType<typeof applyProposal>;
}

export interface Applied {
  flowId: number;
  label: string;
  text: string;
  before: FlowGraph;
  afterJson: string;
  key: number | null;
}

export type Outcome = 'applied' | 'dismissed' | 'undone';

export interface SuggestionsState {
  flowId: number;
  data: RuleSuggestions | null;
  busy: boolean;
  error: string;
}

export interface ChangeState {
  pending: Pending | null;
  /** the rules the approvers' overrides suggest (flow.suggestions, a read), for Watching, Proposals and the empty state */
  suggestions: SuggestionsState | null;
  applied: Applied | null;
  outcomes: Record<number, Outcome>;
  /** the draft changed under the pending proposal (2.10) */
  stale: boolean;
  /** how many agent columns show the Proposals section (while one does, a turn does not repeat the card) */
  sections: number;
}

let state: ChangeState = { pending: null, suggestions: null, applied: null, outcomes: {}, stale: false, sections: 0 };
const listeners = new Set<() => void>();
const set = (p: Partial<ChangeState>) => {
  state = { ...state, ...p };
  listeners.forEach((l) => l());
};

export const changeState = (): ChangeState => state;
export const useChange = (): ChangeState => useSyncExternalStore((l) => (listeners.add(l), () => listeners.delete(l)), changeState, changeState);
export const flowSurface = (): FlowSurface | null => {
  const s = currentSurface();
  return s?.kind === 'flow' ? s : null;
};

/** Read the suggestions from overrides (flow.suggestions) for the open flow; keeps the last answer while it refreshes. */
export async function loadSuggestions(flowId: number): Promise<void> {
  const keep = state.suggestions?.flowId === flowId ? state.suggestions.data : null;
  set({ suggestions: { flowId, data: keep, busy: true, error: '' } });
  try {
    const data = await ruleSuggestions(flowId);
    if (state.suggestions?.flowId === flowId) set({ suggestions: { flowId, data, busy: false, error: '' } });
  } catch (e) {
    if (state.suggestions?.flowId === flowId) set({ suggestions: { flowId, data: keep, busy: false, error: (e as Error).message } });
  }
}

/** The Proposals section mounts itself here; true while any is mounted. */
export function mountSections(): () => void {
  set({ sections: state.sections + 1 });
  return () => set({ sections: Math.max(0, state.sections - 1) });
}

/** A suggestion from overrides as a pending proposal (it is saved with its own note, as the old panel did). */
export function pendingOfSuggestion(sg: RuleSuggestion, sf: FlowSurface): Pending {
  return {
    flowId: sf.flowId,
    proposal: { ...sg.proposal, note: 'Suggested from overrides: ' + sg.text, read_by: 'rules', text: sg.text },
    text: sg.text, key: null, baseJson: canon(sf.graph()),
    save: (flowId) => applySuggestion(flowId, sg),
  };
}

/** A sentence's proposal as a pending one (saved with the server's note "Proposed by the assistant: <text>"). */
export const pendingOfSentence = (p: Proposal, text: string, key: number | null, sf: FlowSurface): Pending => ({
  flowId: sf.flowId, proposal: p, text, key, baseJson: canon(sf.graph()), save: (flowId) => applyProposal(flowId, p),
}); // prettier-ignore

/** Hold a proposal for the person and draw it dashed on the canvas; replaces an earlier one. */
export function setPending(p: Pending): void {
  flowSurface()?.showProposal(p.proposal);
  set({ pending: p, stale: false });
}

/** Drop the pending proposal (Dismiss, Rephrase, a new sentence): nothing was saved. */
export function dismissPending(): void {
  const p = state.pending;
  flowSurface()?.showProposal(null);
  set({ pending: null, stale: false, outcomes: p?.key != null ? { ...state.outcomes, [p.key]: 'dismissed' } : state.outcomes });
}

/**
 * Apply to draft (or Apply and adjust, which then selects the new rule): the person's own saveDraft through the
 * Modeler's surface. Refuses, with `stale`, when the working graph is no longer the one the proposal was made on.
 */
export async function applyPending(adjust: boolean): Promise<boolean> {
  const sf = flowSurface();
  const pd = state.pending;
  const g = pd?.proposal.graph;
  if (!sf || !pd || !g || !sf.canEdit || pd.proposal.kind === 'blocked') return false;
  await sf.flush();
  const before = sf.graph();
  if (canon(before) !== pd.baseJson) {
    set({ stale: true });
    return false;
  }
  const nodeId = adjust ? pd.proposal.node_id : null;
  if (!(await sf.applyGraph(g, nodeId, () => pd.save(sf.flowId)))) return false;
  sf.showProposal(null);
  set({
    pending: null, stale: false,
    applied: { flowId: sf.flowId, label: pd.proposal.label ?? pd.text, text: pd.text, before, afterJson: canon(g), key: pd.key },
    outcomes: pd.key != null ? { ...state.outcomes, [pd.key]: 'applied' } : state.outcomes,
  });
  if (adjust && nodeId) sf.select(nodeId, 'inspector');
  return true;
}

/** Undo is on offer while the draft still equals what the apply saved. */
export function canUndo(s: ChangeState = state): boolean {
  const sf = flowSurface();
  return !!(s.applied && sf && sf.flowId === s.applied.flowId && undoAvailable(s.applied.afterJson, canon(sf.graph())));
}

/** Undo: the person's own saveDraft of the graph before the apply, noted in the journal (2.7). */
export async function undoApplied(): Promise<boolean> {
  const a = state.applied;
  const sf = flowSurface();
  if (!a || !sf || !canUndo()) {
    set({ applied: null });
    return false;
  }
  if (!(await sf.applyGraph(a.before, null, () => saveDraft(a.flowId, a.before, undoNote(a.text))))) return false;
  set({ applied: null, outcomes: a.key != null ? { ...state.outcomes, [a.key]: 'undone' } : state.outcomes });
  return true;
}

// leaving the flow (or opening another) drops what was held for it: a proposal is about one flow's draft. A page that
// re-registers its surface on every change passes through null for an instant, so a missing surface is judged a tick later.
function reconcile(): void {
  const id = flowSurface()?.flowId;
  const pending = state.pending && state.pending.flowId !== id ? null : state.pending;
  const applied = state.applied && state.applied.flowId !== id ? null : state.applied;
  const suggestions = state.suggestions && state.suggestions.flowId !== id ? null : state.suggestions;
  if (pending !== state.pending || applied !== state.applied || suggestions !== state.suggestions) set({ pending, applied, suggestions, stale: false });
}
onSurfaceChange(() => {
  if (flowSurface()) reconcile();
  else setTimeout(() => !flowSurface() && reconcile(), 0);
});
