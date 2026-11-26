import { stageLabel, type AgentRow, type AgentRun, type AgentsScreen, type PackStageAgents } from '../../api/agents';

/**
 * What the Agents page shows a business person (UI audit gaps 14 and 21): the agents grouped under their pack, each with its
 * stage, what it does, its autonomy, whether it is on, and its last run. Pure: no model id, no tool id.
 */

export type StageLevel = PackStageAgents['autonomy'];

/** The three levels of a stage, in the words of Compose's Agents step. */
export const STAGE_AUTONOMY: Record<StageLevel, string> = { recommend: 'Recommend only', limits: 'Act within limits', alone: 'Act alone' };

/** What a level means for the person reading it. */
export const STAGE_AUTONOMY_NOTE: Record<StageLevel, string> = {
  recommend: 'Prepares a recommendation; a person decides.',
  limits: 'Acts while the value, the confidence and the volume stay inside its limits; otherwise holds for a person.',
  alone: 'Acts without waiting for a person, except where a rule or guardrail holds it.',
};

/** Shown beside every level: the actions no agent may take, whatever the level (FORBIDDEN_ACTIONS on the server). */
export const NEVER_ALONE =
  'Even when it acts alone, an agent never takes the actions reserved for a person: approving, overriding, declining or changing access. Those are held for a person every time.';

const STAGE_DOES: Record<string, string> = {
  'stage-lease': 'Reads the lease and the customer’s intent when a lease ends.',
  'stage-return': 'Checks the return is authorised before anything moves.',
  'stage-transit': 'Follows the pickup and the transit.',
  'stage-intake': 'Checks what arrived against what was expected and asks for what is missing.',
  'stage-condition': 'Reads the condition and remaining life of the asset.',
  'stage-demand': 'Looks for buyers, sites and parts demand.',
  'stage-fit': 'Checks the asset is fit for its next use.',
  'stage-valuation': 'Values each route and ranks them.',
  'stage-disposition': 'Prepares the decision on what to do with the asset.',
  'stage-follow': 'Follows the instruction through to the enterprise systems.',
  'stage-outcome': 'Records what actually happened.',
  'stage-reconcile': 'Reconciles the outcome with the books and the forecast.',
};

const OTHER_DOES: Record<string, string> = {
  assembler: 'Gathers the evidence of a case.',
  finder: 'Finds demand and outcomes for an asset.',
  gap: 'Asks for the evidence that is missing.',
  coordinator: 'Prepares the handoff to the enterprise systems.',
  reconciler: 'Reconciles outcomes.',
  briefer: 'Writes the briefing of your day.',
  analyst: 'Explains the analytics.',
  integrator: 'Helps connect and map source systems.',
  auditor: 'Answers questions from the audit trail.',
  ask: 'Answers questions in Ask Circularity.',
  'recover-chain': 'Runs the twelve stages of a case in order.',
  'recover-exceptions': 'Explains exceptions and prepares the next step.',
  'recover-config': 'Helps set up packs and rules.',
};

/** `get_case_evidence` as words. */
export const plainTool = (id: string): string => id.replace(/[._]/g, ' ');

/** One sentence on what an agent does. */
export function agentSummary(a: AgentRow): string {
  const known = STAGE_DOES[a.id] ?? OTHER_DOES[a.id];
  if (known) return known;
  if (a.kind === 'external') return `An outside agent with ${a.tools.length} ${a.tools.length === 1 ? 'tool' : 'tools'}.`;
  return a.tools.length ? `Uses ${a.tools.slice(0, 3).map(plainTool).join(', ')}${a.tools.length > 3 ? ' and more' : ''}.` : 'Reads and explains.';
}

/** The newest run an agent took part in: its own run, or a stage of a chain run it worked on. */
export function lastRunOf(agentId: string, runs: AgentRun[]): AgentRun | null {
  const mine = runs.filter((r) => r.agent === agentId || r.journey?.some((j) => j.status !== 'Queued' && j.agent.split(', ').includes(agentId)));
  return mine.reduce<AgentRun | null>((best, r) => (best === null || r.updated_at > best.updated_at ? r : best), null);
}

export interface AgentLine {
  agent: AgentRow;
  /** the stage it runs, for a stage agent */
  stageLabel: string | null;
  autonomy: StageLevel | null;
  summary: string;
  last: AgentRun | null;
}

export interface AgentGroup {
  key: string;
  title: string;
  note: string;
  rows: AgentLine[];
  /** a pack the org has but with no stage agent yet: shown as "not set up", with a link to set it up in the Modeler */
  notSetUp?: boolean;
}

/** Stage agents under each pack (every pack the org has; one with no stage agent is marked not set up), then the platform's other agents, then outside agents. */
export function agentGroups(s: Pick<AgentsScreen, 'agents' | 'packs' | 'runs'>): AgentGroup[] {
  const byId = new Map(s.agents.map((a) => [a.id, a]));
  const used = new Set<string>();
  const line = (a: AgentRow, stage: string | null = null, autonomy: StageLevel | null = null): AgentLine => ({
    agent: a, stageLabel: stage === null ? null : stageLabel(stage), autonomy, summary: agentSummary(a), last: lastRunOf(a.id, s.runs),
  }); // prettier-ignore
  const groups: AgentGroup[] = s.packs.map((p) => {
    const rows = p.stages.flatMap((st) => {
      const a = byId.get(st.agent);
      if (!a) return [];
      used.add(a.id);
      return [line(a, st.stage, st.autonomy)];
    });
    return { key: p.key, title: p.name, note: 'One agent per stage of the journey', rows, notSetUp: rows.length === 0 };
  });
  const rest = s.agents.filter((a) => !used.has(a.id));
  const platform = rest.filter((a) => a.kind === 'internal').map((a) => line(a));
  const outside = rest.filter((a) => a.kind === 'external').map((a) => line(a));
  return [
    ...groups,
    { key: 'platform', title: 'Platform agents', note: 'Work across every pack', rows: platform },
    { key: 'outside', title: 'Outside agents', note: 'Registered by an admin, connected over MCP', rows: outside },
  ].filter((g) => g.rows.length > 0 || g.notSetUp);
}
