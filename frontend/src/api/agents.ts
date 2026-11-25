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
 *
 * Plan 9 P9-2.3: `useAgents().llm` lists the language models (Admin); setLlmModel is llm.setModel. Agents never run it.
 */
import { invoke, read } from './actions';
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
  /** the stage of the chain the run is at (a stage id), null once it has finished */
  stage: string | null;
  reason: string | null;
  /** what the run waits for from a person */
  waiting: { kind: 'proposal'; proposal: number } | { kind: string; case_id: string | null } | null;
  created_at: string;
  updated_at: string;
  steps: RunStep[];
}

/** Why the hold policy held a call for a person (plan 9, P9-2.4, I-10): `detail` is the sentence to show. */
export type HoldReasonKind = 'risk' | 'value' | 'confidence' | 'taint' | 'destructive' | 'autonomy';
export interface HoldReason { reason: HoldReasonKind; detail: string }

/** The reasons as one line, "Value $900 is above the $600 limit · Confidence 0.62 is below 0.75"; empty when there are none. */
export const reasonText = (reasons?: HoldReason[]): string => (reasons ?? []).map((r) => r.detail).join(' · ');

export interface AgentProposal {
  id: number;
  agent: string;
  agentName: string;
  action: string;
  title: string;
  /** What the agent recommends, in its own words (its reason, else what the action is for). */
  why?: string;
  /** Why the hold policy held it (empty for a proposal held before plan 9). */
  reasons?: HoldReason[];
  input: Record<string, unknown>;
  case_id: string | null;
  run_id: string | null;
  at: string;
  /** The agent acted for this signed-in person: they may only reject it (proposal.accept refuses them, maker-checker). */
  own?: boolean;
}

/** Shown in place of Accept on a proposal the person's own agent prepared. */
export const OWN_PROPOSAL_NOTE = "Your agent's proposal: another person accepts it.";

export interface CatalogTool {
  name: string;
  action: string;
  title: string;
  description: string;
  risk: string;
  input_schema: Record<string, unknown>;
  agent_allowed: boolean;
  /** may an agent call it: yes, held for a person (it prepares, a person runs), or no */
  agent_mode: 'yes' | 'held' | 'no';
  /** the action has a handler on the server */
  implemented: boolean;
}

export interface AgentsScreen {
  agents: AgentRow[];
  orgs: string[];
  mcp_tools: string[];
  runs: AgentRun[];
  proposals: AgentProposal[];
  tools: CatalogTool[];
  /** the language models (Admin; an empty list for other roles) */
  llm: LlmModel[];
  can: { manage: boolean };
}

export type LlmRole = 'ask' | 'agent' | 'author' | 'judge';

/** A language model the router may use (plan 9, P9-2.3): its limits, use this minute and today, and any cooldown. */
export interface LlmModel {
  id: string;
  provider: 'groq' | 'test';
  model: string;
  roles: LlmRole[];
  rpm: number;
  tpm: number;
  rpd: number;
  enabled: boolean;
  priority: number;
  used_minute: { requests: number; tokens: number };
  used_day: { requests: number; tokens: number };
  /** the model is out of the chain until this time (an ISO timestamp), else null */
  cooling_until: string | null;
}

/**
 * The tools that fit a few words, the best `limit` (ten by default), among those the signed-in account may call and an
 * agent may use (`tools.find`, backend/di/services/actions/tools.py; plan 9 P9-2.12). A blank query or a refusal gives none.
 */
export async function findTools(query: string, limit = 10): Promise<CatalogTool[]> {
  if (!query.trim()) return [];
  const r = await invoke<{ tools: CatalogTool[] }>('tools.find', { query: query.trim(), limit });
  return r.ok ? r.output.tools : [];
}

/** The Agents page (Suspense read cache). */
export const useAgents = (): AgentsScreen => cached<AgentsScreen>('/api/screens/agents');

export type AgentPatch = Partial<Pick<AgentRow, 'name' | 'org_scope' | 'tools' | 'autonomy' | 'enabled'>>;

/** Change an agent: stop or start it, its autonomy, tools or org scope (Admin, manageAgents). */
export const updateAgent = (id: string, patch: AgentPatch): Promise<ActionResult<AgentRow>> => invoke('agent.update', { id, ...patch });

export type Playbook = 'case_autopilot' | 'stage_chain';

/** The D1 words for the chain's stage ids (plan 9, P9-2.1). */
const STAGE_LABELS: Record<string, string> = {
  intake: 'Intake',
  condition: 'Condition and life',
  demand: 'Demand',
  fit_for_use: 'Fit-for-use',
  valuation: 'Valuation',
  disposition: 'Disposition',
  follow_through: 'Follow-through',
  analytics: 'Analytics',
};

/** The chain's stage ids in order (the stage calibration picker, P9-2.9). */
export const STAGE_OPTIONS: string[] = Object.keys(STAGE_LABELS);

/** A stage's display name; an unknown id shows as it is. */
export const stageLabel = (id: string): string => STAGE_LABELS[id] ?? id;

/** Start an agent's playbook on a case (Admin, manageAgents; agent.startRun). The agent acts as the signed-in person. */
export const startRun = (
  agent: string,
  caseId: string,
  playbook: Playbook = 'case_autopilot',
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
  /** a price model's factors; a stage calibration's steps (`raw` confidence to `cal`ibrated, P9-2.9) */
  factors: { route?: string; cls?: string; factor?: number; raw?: number; cal?: number }[];
  /** n outcome rows (decided outcomes for a stage calibration); the mean absolute error of the active model and of this one on them (null without rows) */
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

/**
 * Fit a candidate calibration of a pack's stage confidence on what people accepted or rejected (manageFlows;
 * stage.fitCalibration, plan 9 P9-2.9). It is stored as a model of template `<pack>.stage.<stage>`; propose and promote follow.
 * The server refuses it with fewer than 20 decided outcomes.
 */
export const fitStageCalibration = (pack: string, stage: string): Promise<ActionResult<ModelVersion>> =>
  invoke('stage.fitCalibration', { pack, stage });

/** The pack and stage of a stage calibration model (template `<pack>.stage.<stage>`), or null for a price model. */
export const stageCalibrationOf = (template: string): { pack: string; stage: string } | null => {
  const [pack, stage] = template.split('.stage.');
  return pack && stage ? { pack, stage } : null;
};

/** Propose a candidate for promotion (manageFlows; model.propose). */
export const proposeModel = (id: string): Promise<ActionResult<ModelVersion>> => invoke('model.propose', { id });

/** Approve the promotion: the candidate becomes the active model (approve.flows; never its maker or proposer). */
export const promoteModel = (id: string): Promise<ActionResult<{ id: string; status: string; retired: string | null }>> =>
  invoke('model.promote', { id });

export type LlmModelPatch = Partial<Pick<LlmModel, 'enabled' | 'priority' | 'roles' | 'rpm' | 'tpm' | 'rpd'>>;

/** Switch a language model on or off, order it, or change its roles or limits (Admin, manageAgents; llm.setModel). */
export const setLlmModel = (id: string, patch: LlmModelPatch): Promise<ActionResult<LlmModel>> => invoke('llm.setModel', { id, ...patch });

/** One span of a run (plan 9, P9-2.6, I-12): a `run`, `stage`, `model` response, `tool` call or `action` the pipeline ran. */
export interface TraceSpan {
  span_id: string;
  trace_id: string;
  parent_id: string | null;
  name: string;
  kind: 'run' | 'stage' | 'model' | 'tool' | 'action';
  started_at: string;
  ended_at: string;
  status: 'ok' | 'error';
  /** `di.*` and `gen_ai.*` attributes (the model, its tokens, which model of the chain answered, the stage) */
  attrs: Record<string, unknown>;
  children: TraceSpan[];
}

export interface TraceStage {
  stage: string;
  agent: string;
  kind: string;
  autonomy: 'recommend' | 'limits' | 'alone';
  status: 'done' | 'skipped' | 'held' | 'waiting' | 'exception';
  confidence: number | null;
  threshold: number;
  /** what the stage read: the source system, its record and how old it was */
  sources: Record<string, unknown>[];
  reasons: HoldReason[];
  at: string;
}

export interface TraceCall { n: number; tool: string; ok: boolean; held: number | null; input: Record<string, unknown>; at: string }
export interface TraceProposal { id: number; action: string; status: string; case_id: string | null; reasons: HoldReason[]; decided_by: string | null }
export interface TracePause { by: string; on: boolean; at: string }

/** Everything one run did (`agent.runTrace`, backend/di/repositories/run_trace.py); `run` is null for a case with no run. */
export interface RunTrace {
  run: {
    id: string; agent: string; agentName: string; playbook: string; case_id: string | null; status: AgentRun['status']; step: number;
    reason: string | null; waiting: string | null; model: string | null; model_route: string | null;
    tokens: { input: number | null; output: number | null } | null; created_at: string; updated_at: string;
  } | null;
  stages: TraceStage[];
  calls: TraceCall[];
  spans: TraceSpan[];
  journal: { seq: number; action: string; actor: string; preparer: string | null; at: string }[];
  proposals: TraceProposal[];
  pauses: TracePause[];
}

/** Nest spans by `parent_id` (a flat list in start order, or an already nested tree): a `tool` span lands under its `model`
 * span. A span whose parent is not in the list is a root. */
export function spanTree(spans: readonly TraceSpan[]): TraceSpan[] {
  const flat: TraceSpan[] = [];
  const take = (list: readonly TraceSpan[]) => list.forEach((s) => (flat.push({ ...s, children: [] }), take(s.children ?? [])));
  take(spans);
  const by = new Map(flat.map((s) => [s.span_id, s]));
  const roots: TraceSpan[] = [];
  for (const s of flat) {
    const parent = s.parent_id ? by.get(s.parent_id) : undefined;
    (parent ? parent.children : roots).push(s);
  }
  return roots;
}

/** The tree as rows for a table: each span with its depth, parents first. */
export const spanRows = (tree: readonly TraceSpan[], depth = 0): { span: TraceSpan; depth: number }[] =>
  tree.flatMap((s) => [{ span: s, depth }, ...spanRows(s.children, depth + 1)]);

/** How long a span took, in milliseconds. */
export const spanMs = (s: Pick<TraceSpan, 'started_at' | 'ended_at'>): number => Math.max(0, Date.parse(s.ended_at) - Date.parse(s.started_at));

/** The run view's data (Suspense read cache): the run `runId`, or the latest run on `caseId`. */
export function runTrace(q: { runId: string } | { caseId: string }): RunTrace {
  const t = read<RunTrace>('agent.runTrace', 'runId' in q ? { run_id: q.runId } : { case_id: q.caseId });
  return { ...t, spans: spanTree(t.spans) };
}

/** The pause switch: stop (`on` false) or start an agent (Admin; the journaled `agent.setEnabled`). */
export const setAgentEnabled = (id: string, on: boolean): Promise<ActionResult<{ id: string; on: boolean }>> =>
  invoke('agent.setEnabled', { id, on });
