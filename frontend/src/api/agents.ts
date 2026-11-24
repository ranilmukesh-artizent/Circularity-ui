/**
 * The Agents page (plan 8, MVP-11.8): the agent registry, the agents' runs, the proposals waiting for a person and the
 * tool catalogue, read from GET /api/screens/agents (backend/di/services/screens/agents.py). Admin changes an agent
 * with agent.update and starts a playbook run on a case with agent.startRun (backend/di/services/actions/agents.py); the signed-in person accepts or rejects a proposal with
 * proposal.accept and proposal.reject (backend/di/services/actions/proposals.py). Agents never run these. A successful
 * write invalidates every read (invalidation.ts: the `agent` family and unknown families refresh everything).
 *
 * Plan 8 UI gaps: Admin registers an agent (agent.register; a tool no agent may use is refused by the server). The Models
 * panel reads GET /api/screens/agents/models; a Planner or Admin fits a candidate (model.fit) and proposes it
 * (model.propose), a different person with approve.flows promotes it (model.promote). Agents never run these.
 */
import { invoke } from './actions';
import { cached } from './client';
import type { ActionResult } from './types';

export type Autonomy = 'read' | 'propose' | 'act';

export interface AgentRow {
  id: string;
  name: string;
  kind: 'internal' | 'external';
  autonomy: Autonomy;
  enabled: boolean;
  org_scope: string[];
  tools: string[];
  created_by: string | null;
}

interface RunStep {
  n: number;
  tool: string;
  ok: boolean;
  /** the refusal, or the proposal the call was held as */
  note: string | null;
  at: string;
}

export interface AgentRun {
  id: string;
  agent: string;
  agentName: string;
  playbook: string;
  case_id: string | null;
  status: 'running' | 'waiting' | 'done' | 'failed' | 'stopped';
  step: number;
  reason: string | null;
  /** what the run waits for from a person */
  waiting: { kind: 'proposal'; proposal: number } | { kind: string; case_id: string | null } | null;
  created_at: string;
  updated_at: string;
  steps: RunStep[];
}

export interface AgentProposal {
  id: number;
  agent: string;
  agentName: string;
  action: string;
  title: string;
  input: Record<string, unknown>;
  case_id: string | null;
  run_id: string | null;
  at: string;
}

interface CatalogTool {
  name: string;
  action: string;
  title: string;
  description: string;
  risk: string;
  input_schema: Record<string, unknown>;
  agent_allowed: boolean;
}

export interface AgentsScreen {
  agents: AgentRow[];
  orgs: string[];
  mcp_tools: string[];
  runs: AgentRun[];
  proposals: AgentProposal[];
  tools: CatalogTool[];
  can: { manage: boolean };
}

/** The Agents page (Suspense read cache). */
export const useAgents = (): AgentsScreen => cached<AgentsScreen>('/api/screens/agents');

export type AgentPatch = Partial<Pick<AgentRow, 'name' | 'org_scope' | 'tools' | 'autonomy' | 'enabled'>>;

/** Change an agent: stop or start it, its autonomy, tools or org scope (Admin, manageAgents). */
export const updateAgent = (id: string, patch: AgentPatch): Promise<ActionResult<AgentRow>> => invoke('agent.update', { id, ...patch });

/** Start an agent's playbook on a case (Admin, manageAgents; agent.startRun). The agent acts as the signed-in person. */
export const startRun = (
  agent: string,
  caseId: string,
  playbook = 'case_autopilot',
): Promise<ActionResult<{ run_id: string; agent: string; playbook: string; case_id: string }>> =>
  invoke('agent.startRun', { agent, case_id: caseId, playbook });

/** Run the action an agent prepared, as the signed-in person. */
export const acceptProposal = (id: number): Promise<ActionResult<{ id: number; status: string; action: string }>> =>
  invoke('proposal.accept', { id });

/** Close an agent's proposal without running it. */
export const rejectProposal = (id: number, reason: string): Promise<ActionResult<{ id: number; status: string }>> =>
  invoke('proposal.reject', { id, reason });

export type AgentKind = AgentRow['kind'];

export interface NewAgent {
  id: string;
  name: string;
  kind: AgentKind;
  tools: string[];
  org_scope: string[];
  autonomy: Autonomy;
}

/** Register an agent (Admin, manageAgents; agent.register). The server refuses a tool no agent may use. */
export const registerAgent = (a: NewAgent): Promise<ActionResult<{ id: string }>> => invoke('agent.register', { ...a });

export interface ModelVersion {
  id: string;
  template: string;
  status: 'candidate' | 'active' | 'retired';
  created_by: string;
  approved_by: string | null;
  created_at: string;
  factors: { route: string; cls: string; factor: number }[];
  /** n outcome rows; the mean absolute error of the active model and of this one on them (null without rows) */
  metrics: { n: number; active_id: string | null; mae_active: number | null; mae_candidate: number | null };
  proposal: { by: string; at: string } | null;
  /** why the signed-in person may not propose or approve it, else null */
  blocks: { propose: string | null; promote: string | null };
}

export interface ModelsScreen {
  /** the base predictor's model version */
  base: string;
  /** the active calibration model of each template, or null */
  active: Record<string, string | null>;
  models: ModelVersion[];
  can: { fit: boolean; promote: boolean };
}

/** The Models panel (Suspense read cache). */
export const useModels = (): ModelsScreen => cached<ModelsScreen>('/api/screens/agents/models');

/** Fit a candidate calibration model on the confirmed outcomes (manageFlows; model.fit). */
export const fitModel = (template = 'industrial'): Promise<ActionResult<ModelVersion>> => invoke('model.fit', { template });

/** Propose a candidate for promotion (manageFlows; model.propose). */
export const proposeModel = (id: string): Promise<ActionResult<ModelVersion>> => invoke('model.propose', { id });

/** Approve the promotion: the candidate becomes the active model (approve.flows; never its maker or proposer). */
export const promoteModel = (id: string): Promise<ActionResult<{ id: string; status: string; retired: string | null }>> =>
  invoke('model.promote', { id });
