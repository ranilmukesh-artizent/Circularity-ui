/**
 * The Agents page (plan 8, MVP-11.8): the agent registry, the agents' runs, the proposals waiting for a person and the
 * tool catalogue, read from GET /api/screens/agents (backend/di/services/screens/agents.py). Admin changes an agent
 * with agent.update and starts a playbook run on a case with agent.startRun (backend/di/services/actions/agents.py); the signed-in person accepts or rejects a proposal with
 * proposal.accept and proposal.reject (backend/di/services/actions/proposals.py). Agents never run these. A successful
 * write invalidates every read (invalidation.ts: the `agent` family and unknown families refresh everything).
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
