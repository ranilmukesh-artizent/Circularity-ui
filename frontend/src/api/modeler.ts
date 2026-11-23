/**
 * The Modeler (plan 8, MVP-4.3): one decision flow per template and org unit, its checks, compiled rules, history and
 * log, read from GET /api/screens/modeler (backend/di/services/screens/modeler.py). Every change is a flow.* action
 * (backend/di/services/actions/modeler.py): a person edits a draft and submits it, a different person approves it (a
 * shadow run starts) and publishes it. A successful write invalidates the Modeler read and the case reads
 * (invalidation.ts, the `flow` family). simulateFlow is a read action run on demand, not cached.
 */
import { invoke } from './actions';
import { cached, withQuery } from './client';
import type { ActionResult, FlowGraph, ModelerScreen, SimResult } from './types';

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
export const rejectFlow = (flowId: number, reason: string): Promise<Done> => invoke('flow.reject', { flow_id: flowId, reason });
export const publishFlow = (flowId: number): Promise<Done> => invoke('flow.publish', { flow_id: flowId });
export const discardFlow = (flowId: number): Promise<Done> => invoke('flow.discard', { flow_id: flowId });
export const rollbackFlow = (flowId: number): Promise<Done> => invoke('flow.rollback', { flow_id: flowId });

/** The graph (or the saved draft) against the published rules on the open queue; rejects with the refusal message. */
export async function simulateFlow(flowId: number, graph?: FlowGraph): Promise<SimResult> {
  const r = await invoke<SimResult>('flow.simulate', graph ? { flow_id: flowId, graph } : { flow_id: flowId });
  if (!r.ok) throw new Error(r.error.message);
  return r.output;
}
