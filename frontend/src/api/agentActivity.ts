/**
 * Agent activity (UI audit 2026-11-26, gaps 12 and 15), read only: what each agent did on the cases of the signed-in
 * person's tenants, from GET /api/screens/agent-activity (backend/di/services/screens/agent_activity.py). A person
 * decides a held proposal in My work, on Home or in the assistant (`ProposalRow`), never here.
 *
 * Gap 15: `runAutopilot` starts the case autopilot on a case as the signed-in Planner or Approver (agent.startRun,
 * permission runAgent). The run only prepares: the server holds every write of it for a person.
 */
import { startRun } from './agents';
import { cached } from './client';
import type { ActionResult } from './types';

export type ActivityKind = 'held' | 'accepted' | 'rejected' | 'refused' | 'run';

export interface ActivityEvent {
  id: string;
  at: string;
  agent: string;
  agentName: string;
  kind: ActivityKind;
  title: string;
  detail: string;
  case_id: string | null;
  pack: string;
  run_id: string | null;
  proposal_id: number | null;
}

export interface AgentActivity {
  events: ActivityEvent[];
  agents: { id: string; name: string }[];
  packs: { key: string; name: string }[];
  can: { runAgent: boolean };
}

export const useAgentActivity = (): AgentActivity => cached<AgentActivity>('/api/screens/agent-activity');

/** The agent that runs the case autopilot (the server's DI_AUTOPILOT_AGENT default). */
export const CASE_AUTOPILOT_AGENT = 'coordinator';

/** Run the case autopilot on a case (propose only for a Planner or Approver). */
export const runAutopilot = (caseId: string): Promise<ActionResult<{ run_id: string }>> => startRun(CASE_AUTOPILOT_AGENT, caseId);
