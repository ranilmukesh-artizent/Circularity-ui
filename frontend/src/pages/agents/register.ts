/**
 * The Register agent dialog's pure parts (plan 8 UI gaps): the id made from the name, the tools an agent may be given
 * and the checks before the form is sent. The server checks again (agent.register in
 * backend/di/services/actions/agents.py): the same id rule, and no action an agent may never run.
 */
import type { AgentsScreen, NewAgent } from '../../api/agents';

/** The server's rule: 2-64 lower-case letters, digits, dots, dashes or underscores, starting with a letter or digit. */
export const ID_RE = /^[a-z0-9][a-z0-9._-]{1,63}$/;

/** An agent id from its name: "Claims Helper 2" -> "claims-helper-2". */
export function idFromName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^[^a-z0-9]+|-+$/g, '')
    .slice(0, 64);
}

export interface ToolOption {
  id: string;
  /** an MCP tool, or an action of the tool catalogue */
  kind: 'mcp' | 'action';
  title: string;
}

/** The tools an agent may be given: every MCP tool, then the catalogue's actions an agent may call. The actions no
 * agent may run (approving, access, publishing, promoting models, registering agents ...) are never offered. */
export function toolOptions(s: Pick<AgentsScreen, 'mcp_tools' | 'tools'>): ToolOption[] {
  const mcp = s.mcp_tools.map((id): ToolOption => ({ id, kind: 'mcp', title: id }));
  const seen = new Set(s.mcp_tools);
  const acts = s.tools.filter((t) => t.agent_allowed && !seen.has(t.action)).map((t): ToolOption => ({ id: t.action, kind: 'action', title: t.title }));
  return [...mcp, ...acts];
}

/** What is wrong with the form, or '' when it can be sent. */
export function problem(a: NewAgent, taken: string[]): string {
  if (!a.name.trim()) return 'Give the agent a name.';
  if (!ID_RE.test(a.id)) return 'The id is 2 to 64 lower-case letters, digits, dots, dashes or underscores.';
  if (taken.includes(a.id)) return `An agent with the id ${a.id} is already registered.`;
  return '';
}
