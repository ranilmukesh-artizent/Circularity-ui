/**
 * Ask's starter questions (UI pack audit E17). The demo's role starters (AF_STARTERS, never changed) lead on Home and
 * for the industrial pack; on a case or flow of another pack the server's pack questions lead and one demo starter
 * follows. The server (GET /api/ask/starters) already filtered by the role's pages; this only orders and trims.
 */
import type { AssistantContext } from '../types';

export const MAX_STARTERS = 6;
const NEW_PAGES = new Set(['modeler', 'agents', 'mywork']);

/** Up to two questions from what the person is looking at (2.10). */
export function contextStarters(ctx: AssistantContext): string[] {
  return ctx.caseId ? [`Why this route for ${ctx.caseId}?`] : [];
}

/** The page's own request to the server: the flow's template is the section on the Modeler. */
export function startersQuery(ctx: AssistantContext): { page: string; section?: string; case_id?: string } {
  return { page: ctx.page, section: ctx.flow?.template ?? ctx.section, case_id: ctx.caseId };
}

export function selectStarters(
  demo: string[],
  server: { pack: string | null; starters: { text: string }[] },
  ctx: AssistantContext,
): string[] {
  const remote = server.starters.map((s) => s.text);
  // the demo has no Modeler, Agents or My work: its starters are about other pages
  const own = NEW_PAGES.has(ctx.page) ? [] : demo.slice(0, 4);
  // a case or flow of a non-industrial pack: its questions first, one demo starter after
  const list = server.pack ? [...remote, ...contextStarters(ctx), ...own.slice(0, 1)] : [...own, ...contextStarters(ctx), ...remote];
  return [...new Set(list)].slice(0, MAX_STARTERS);
}

/** Plain words for the tools Ask may call (backend/di/services/ask/tools.py); an unknown tool reads as its own name. */
const TOOL_WORDS: Record<string, string> = {
  get_case: 'the case record', get_case_evidence: 'the case evidence', list_eligible_routes: 'the eligible routes',
  predict_outcomes: 'predicted outcomes', find_demand: 'open demand', optimize_pool: 'the pool plan',
  get_model_validation: 'the model checks', get_decision_flow: 'the decision flow', list_cases: 'the open cases',
  get_case_run: 'the case run', what_if: 'a what-if', explain_kpi: 'a figure', get_inbox: 'what needs you',
  device_question: 'the device records', list_workflows: 'the workflows', get_workflow: 'a workflow',
  get_workflow_run: 'a workflow run',
};
// the action ids the rules' fallback reports (ACTION_TOOLS and the MCP tools' actions)
Object.assign(TOOL_WORDS, {
  'cases.list': 'the open cases', 'case.get': 'the case record', 'case.evidence': 'the case evidence', 'case.routes': 'the eligible routes',
  'case.trace': 'the case run', 'case.whatIf': 'a what-if', 'kpi.explain': 'a figure', 'inbox.get': 'what needs you',
  'device.question': 'the device records', 'workflow.list': 'the workflows', 'workflow.get': 'a workflow', 'workflow.runGet': 'a workflow run',
  'flow.get': 'the decision flow', 'demand.find': 'open demand', 'pool.optimize': 'the pool plan', 'analytics.models': 'the model checks',
  'ask.fallback': 'the rules',
});
export const toolWords = (name: string): string => TOOL_WORDS[name] ?? name.replace(/_/g, ' ');

/** "Used: the case record, the open cases": each tool once, in the order called, first letter capital. */
export function usedLine(tools: { name: string }[]): string {
  const w = [...new Set(tools.map((t) => toolWords(t.name)))];
  return w.length ? 'Used: ' + w.join(', ') : '';
}

/** The inputs of a call as "case_id RT-1048, question price after launch"; nothing when it took none. */
export function argsText(args: Record<string, unknown>): string {
  return Object.entries(args)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${k.replace(/_/g, ' ')} ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join(', ');
}
