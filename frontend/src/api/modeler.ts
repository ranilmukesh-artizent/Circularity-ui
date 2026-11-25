/**
 * The Modeler (plan 8, MVP-4.3): one decision flow per template and org unit, its checks, compiled rules, history and
 * log, read from GET /api/screens/modeler (backend/di/services/screens/modeler.py), with the org's customer overlay of
 * the pack (`overlay`, plan 9 P9-1.3: the overlay.* actions of backend/di/services/actions/overlays.py). Every change is a flow.* action
 * (backend/di/services/actions/modeler.py): a person edits a draft and submits it, a different person approves it (a
 * shadow run starts) and publishes it. A successful write invalidates the Modeler read and the case reads
 * (invalidation.ts, the `flow` family). simulateFlow and ruleSuggestions are read actions run on demand, not cached;
 * the last simulation's per-node counts are kept per flow for the canvas badges (useSimNodes, P9-8.15).
 */
import { useSyncExternalStore } from 'react';
import { invoke } from './actions';
import { cached, withQuery } from './client';
import { saveMarketTable, testMarketTable, type Jdm, type MarketTable } from './marketTables';
import type { ActionResult, FlowGraph, ModelerScreen, OverlayConflict, OverlayOp, SimResult } from './types';

/** The Modeler page for a template and an org unit (Suspense read cache). */
export const useModeler = (template: string, org: string): ModelerScreen =>
  cached<ModelerScreen>(withQuery('/api/screens/modeler', { template: template || null, org: org || null }));

type Done = ActionResult<{ id: number; status?: string; log?: string }>;

export const saveDraft = (flowId: number, graph: FlowGraph): Promise<ActionResult<{ id: number; checks: ModelerScreen['checks'] }>> =>
  invoke('flow.saveDraft', { flow_id: flowId, graph });

export const forkFlow = (template: string, org: string): Promise<ActionResult<{ id: number; flow_id: number }>> =>
  invoke('flow.fork', { template_key: template, org_unit_id: org });

export const submitFlow = (flowId: number): Promise<Done> => invoke('flow.submit', { flow_id: flowId });
export const approveFlow = (flowId: number): Promise<Done> => invoke('flow.approve', { flow_id: flowId });
export const rejectFlow = (flowId: number, reason: string, nodeId?: string): Promise<Done> =>
  invoke('flow.reject', { flow_id: flowId, reason, ...(nodeId ? { node_id: nodeId } : {}) });
export const publishFlow = (flowId: number): Promise<Done> => invoke('flow.publish', { flow_id: flowId });
export const discardFlow = (flowId: number): Promise<Done> => invoke('flow.discard', { flow_id: flowId });
export const rollbackFlow = (flowId: number): Promise<Done> => invoke('flow.rollback', { flow_id: flowId });

/** The assistant's proposal for a plain-language change (flow.propose, MVP-5.2): nothing is saved until applied. */
export interface Proposal {
  kind: 'rule' | 'step' | 'blocked' | 'unclear';
  text: string;
  graph: FlowGraph | null;
  node_id: string | null;
  rid: string | null;
  label: string | null;
  guard: string | null;
  checks: ModelerScreen['checks'];
  sim: SimResult | null;
  msg: string;
  /** the saveDraft note that applies it: "Proposed by the assistant: <text>" */
  note: string;
  read_by: 'rules' | 'rules+model';
}

/** A plain-language change read into a checked, simulated proposal; rejects with the refusal message. */
export async function proposeChange(flowId: number, text: string): Promise<Proposal> {
  const r = await invoke<Proposal>('flow.propose', { flow_id: flowId, text });
  if (!r.ok) throw new Error(r.error.message);
  return r.output;
}

/** Apply a proposal: the person's own saveDraft of its graph, with the assistant's note in the journal. */
export const applyProposal = (flowId: number, p: Proposal): Promise<ActionResult<{ id: number; checks: ModelerScreen['checks'] }>> =>
  invoke('flow.saveDraft', { flow_id: flowId, graph: p.graph, source: 'assistant', note: p.note });

/** How many cases reach a node and leave it towards the decision in a simulation, and up to three of them (P9-8.15). */
export interface NodeFlow { in: number; out: number; examples: string[] }
/** What flow.simulate answers: the Impact numbers and, per node, how the open queue flows through it. */
export type SimWithNodes = SimResult & { per_node?: Record<string, NodeFlow> };

// the last simulation's per-node counts of each flow, so the canvas and the inspector can show them without the Impact
// panel passing them down; a new simulation of the flow replaces them
const lastNodes = new Map<number, Record<string, NodeFlow>>();
const watchers = new Set<() => void>();
/** The per-node counts of the flow's last simulation in this session, or undefined (none yet, or a template without them). */
export function useSimNodes(flowId: number | undefined): Record<string, NodeFlow> | undefined {
  return useSyncExternalStore((f) => (watchers.add(f), () => watchers.delete(f)), () => (flowId == null ? undefined : lastNodes.get(flowId)));
}

/** The graph (or the saved draft) against the published rules on the open queue; rejects with the refusal message. */
export async function simulateFlow(flowId: number, graph?: FlowGraph, params?: Partial<Record<'market' | 'labor' | 'lease' | 'slots', number>>): Promise<SimWithNodes> {
  const input = { flow_id: flowId, ...(graph ? { graph } : {}), ...(params ? { params } : {}) };
  const r = await invoke<SimWithNodes>('flow.simulate', input);
  if (!r.ok) throw new Error(r.error.message);
  if (r.output.per_node) lastNodes.set(flowId, r.output.per_node); else lastNodes.delete(flowId);
  watchers.forEach((f) => f());
  return r.output;
}

/** A prefer rule suggested by repeated Approver overrides (flow.suggestions, MVP-12.3; audit U8), drafted as a proposal. */
export interface RuleSuggestion {
  dim: string;
  value: string;
  path: string;
  overrides: number;
  decisions: number;
  share: number;
  text: string;
  rule: Record<string, unknown>;
  proposal: Omit<Proposal, 'note' | 'read_by'>;
}

export interface RuleSuggestions {
  flow_id: number;
  /** the journaled decisions of this flow's cases that were read */
  decisions: number;
  groups: { template: string; from: string; to: string; n: number }[];
  suggestions: RuleSuggestion[];
}

/** The rules the overrides of this flow's decisions suggest; nothing is saved. Rejects with the refusal message. */
export async function ruleSuggestions(flowId: number): Promise<RuleSuggestions> {
  const r = await invoke<RuleSuggestions>('flow.suggestions', { flow_id: flowId });
  if (!r.ok) throw new Error(r.error.message);
  return r.output;
}

/** Apply a suggestion to the draft: the person's own saveDraft of its graph. Submitting and publishing stay separate. */
export const applySuggestion = (flowId: number, s: RuleSuggestion): Promise<ActionResult<{ id: number; checks: ModelerScreen['checks'] }>> =>
  invoke('flow.saveDraft', { flow_id: flowId, graph: s.proposal.graph, source: 'assistant', note: 'Suggested from overrides: ' + s.text });

type OverlayDone = ActionResult<{ status: string; log?: string }>;

/** Save the customer overlay's draft (tighten-only: the server refuses a weakening or a skipped compliance rule). */
export const saveOverlay = (pack: string, org: string, ops: OverlayOp[], resolved?: string[]): Promise<OverlayDone> =>
  invoke('overlay.save', { pack_key: pack, org_unit_id: org, ops, ...(resolved?.length ? { resolved } : {}) });

export const submitOverlay = (pack: string, org: string): Promise<OverlayDone> => invoke('overlay.submit', { pack_key: pack, org_unit_id: org });
export const approveOverlay = (pack: string, org: string): Promise<OverlayDone> => invoke('overlay.approve', { pack_key: pack, org_unit_id: org });
export const rejectOverlay = (pack: string, org: string, reason: string): Promise<OverlayDone> =>
  invoke('overlay.reject', { pack_key: pack, org_unit_id: org, reason });

/** Move the overlay onto the pack's newer version as a draft; the answer lists its conflicts and notes. */
export const rebaseOverlay = (pack: string, org: string): Promise<ActionResult<{ status: string; ops: number; conflicts: OverlayConflict[]; notes: string[]; log: string }>> =>
  invoke('overlay.rebase', { pack_key: pack, org_unit_id: org });

type PackDone = ActionResult<{ id?: number; status: string; log?: string }>;

/** Import a pack document as a draft version for an org (none: every org, Admin only); refused with the part that failed. */
export const importPack = (doc: unknown, org?: string): Promise<PackDone> => invoke('pack.import', { doc, ...(org ? { org_unit_id: org } : {}) });
export const submitPack = (id: number): Promise<PackDone> => invoke('pack.submit', { id });
export const approvePack = (id: number): Promise<PackDone> => invoke('pack.approve', { id });
export const rejectPack = (id: number, reason: string): Promise<PackDone> => invoke('pack.reject', { id, reason });

// ---- decision tables in the editor (plan 9, P9-8.16): the marketTable.* actions of P9-4.2, one table store, no second path
export { useMarketTables as decisionTable } from './marketTables';
/** Save the editor's graph as a draft (your own draft is edited in place; otherwise a new version starting on `validFrom`). */
export const saveDecisionTable = (t: MarketTable, body: Jdm, validFrom: string, own: boolean) =>
  saveMarketTable({ pack: t.pack, flow: t.flow, market: t.market, name: t.name, kind: 'decision_table', valid_from: validFrom, ...(t.org_unit_id ? { org_unit_id: t.org_unit_id } : {}), body, ...(own ? { id: t.id } : {}) }); // prettier-ignore
/** "Test this decision": the stored version on sample inputs; answers the outputs and the matched row. */
export const testDecisionTable = testMarketTable;
