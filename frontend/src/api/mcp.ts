/**
 * MCP & Tools: the governed tool catalog, agent registry, permission matrix, call log, enterprise MCP servers consumed
 * as a client, and the tool playground. Server proposals live in access.ts (they are access requests).
 *
 * backend/di/services/screens/mcp.py has the mapping: the agents, the permission matrix, the call log and the client servers
 * from GET /api/screens/mcp/*; the tools, hard rules, tenants, journey steps and risk labels are reference lists; the
 * action registry is GET /api/actions. The playground calls the real MCP server (POST /mcp, JSON-RPC tools/call,
 * backend/di/mcp/) as the signed-in account, so its calls land in the real call log. The agent test bench ran the
 * demo's in-browser agent layer and is not available yet (the server's Ask runs the safety checks: GET /api/checks).
 */
import { actionCatalog } from './actions';
import { accessToken, cached, invalidate, ref, withQuery } from './client';

export interface ToolInput { t: string; req: boolean; ex: unknown }
export interface Tool { id: string; desc: string; rw: 'read' | 'write'; step: number[]; approval: string; input: Record<string, ToolInput> }
export interface McpAgent { id: string; name: string; step: string; scopes: string[]; tools: string[]; limit: string; calls: number }
export interface ClientServer { id: string; name: string; owner: string; status: string; tools: string[]; used: string }
export interface ToolCall { ts: Date | string; agent: string; tool: string; caseId: string; tenant: string; lat: number; outcome: string; step: number }

type ApiCall = ToolCall & { openable: boolean };
const callsA = () => cached<{ calls: ApiCall[] }>('/api/screens/mcp/calls').calls;

/** A tool generated from the action catalogue (plan 9 P9-2.13), with the hints an MCP client reads. */
export interface GeneratedTool { tool: string; action: string; read_only: boolean; destructive: boolean; needs_person: boolean }
export interface GeneratedAgent { agent: string; name: string; tools: GeneratedTool[] }
/** Per registered agent, the tools generated from the action catalogue: GET /api/screens/mcp/generated. */
export const generatedTools = (): GeneratedAgent[] => cached<{ agents: GeneratedAgent[] }>('/api/screens/mcp/generated').agents;

export const tools = (): Tool[] => ref('TOOLS');
export const toolById = (id: string): Tool | undefined => tools().find((t) => t.id === id);
export const mcpAgents = (): McpAgent[] => cached<{ agents: McpAgent[] }>('/api/screens/mcp/agents').agents;
export const hardRules = (): string[] => ref('HARD_RULES').slice();
export const clientServers = (): ClientServer[] => cached<{ servers: ClientServer[] }>('/api/screens/mcp/client').servers.slice();
export const toolCalls = (): ToolCall[] => callsA().slice();
export const tenantList = (): string[] => ref('TENANTS');

/** A journey step as the demo's stp()/stpn() chips show it. */
export interface JourneyStep { n: number; name: string; status: string; desc: string }
export function journeyStep(n: number): JourneyStep {
  const m = ref('JMAP')[n] || n;
  const j = ref('JSTEPS')[m - 1];
  return { n: m, name: j[1], status: j[2] === 'built' ? '' : j[2], desc: j[3] };
}

/** The tool's MCP descriptor (name, inputSchema, annotations). */
export function toolSchema(t: Tool): unknown {
  const props: Record<string, { type: string }> = {}, req: string[] = [];
  Object.entries(t.input).forEach(([k, v]) => { props[k] = { type: v.t }; if (v.req) req.push(k); });
  return {
    name: t.id, description: t.desc, inputSchema: { type: 'object', properties: props, required: req },
    annotations: { readOnlyHint: t.rw === 'read', requiresHumanApproval: t.approval === 'human approval required' },
  };
}
export const exampleInput = (t: Tool): Record<string, unknown> => Object.fromEntries(Object.entries(t.input).map(([k, v]) => [k, v.ex]));
/** The agent the playground calls as by default for this tool. */
export function autoAgent(toolId: string): string {
  const want = toolId === 'request_missing_evidence' ? 'gap' : toolId === 'send_instruction' || toolId === 'request_approval' ? 'coordinator'
    : toolId === 'reconcile_outcome' ? 'reconciler' : 'finder';
  const A = mcpAgents();
  return (A.find((a) => a.tools.includes(toolId) && a.id === want) ?? A.find((a) => a.tools.includes(toolId)))!.id;
}

export type PermKind = 'deny' | 'gate' | 'scope' | 'own' | 'read';
export interface PermCell { k: PermKind; l: string; tip: string }
export function permCell(a: McpAgent, t: Tool, tenant: string): PermCell {
  const m = cached<{ rows: { agent: string; cells: (PermCell & { tool: string })[] }[] }>(withQuery('/api/screens/mcp/matrix', { tenant }));
  const c = m.rows.find((r) => r.agent === a.id)?.cells.find((x) => x.tool === t.id);
  return c ? { k: c.k, l: c.l, tip: c.tip } : { k: 'deny', l: '—', tip: `${a.name} has no scope for ${t.id}` };
}
export const PERM_CHIP: Record<PermKind, string> = { deny: 'chip line', gate: 'chip y', scope: 'chip dk', own: 'chip warn', read: 'chip ok' };

/** May the signed-in account open the case behind a call? */
export const caseOpenable = (caseId: string): boolean => callsA().some((c) => c.caseId === caseId && c.openable);

export interface TraceStep { n: string; ok: boolean; detail: string; ms?: number }
export interface ToolRun {
  ok: boolean; result?: unknown; error?: Record<string, unknown>; trace: TraceStep[]; ms: number; outcome: string; caseId?: string;
}

/**
 * Run a tool in the playground: a real MCP tools/call on /mcp (the bearer token is the signed-in account's, X-Agent the
 * agent it calls as, X-Tenant the tenant). The server checks agent scope, input schema and tenant boundary, answers
 * from the data, and adds the call to the call log.
 */
export async function runPlaygroundTool(toolId: string, agentId: string, tenant: string, raw: string): Promise<ToolRun> {
  return mcpCall(toolId, agentId, tenant, raw);
}

let rpcId = 0;
async function mcpCall(toolId: string, agentId: string, tenant: string, raw: string): Promise<ToolRun> {
  let args: unknown;
  try {
    args = JSON.parse(raw);
  } catch (x) {
    // not sent: the server would only see an empty call (the demo refuses it the same way, before any tool runs)
    const message = 'Input is not valid JSON: ' + (x as Error).message;
    return { ok: false, error: { code: 'validation_error', message }, trace: [{ n: 'Validate input schema', ok: false, detail: 'Not valid JSON' }], ms: 0, outcome: 'error · validation_error' };
  }
  const res = await fetch('/mcp', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json', Accept: 'application/json, text/event-stream',
      Authorization: 'Bearer ' + (accessToken() ?? ''), 'X-Agent': agentId, 'X-Tenant': tenant,
    },
    body: JSON.stringify({ jsonrpc: '2.0', id: ++rpcId, method: 'tools/call', params: { name: toolId, arguments: args } }),
  });
  const body = await res.json().catch(() => null);
  const a = body?.result?.structuredContent;
  invalidate(); // the call log and the case it touched have changed
  if (!res.ok || !a) {
    const message = body?.error?.message ?? body?.message ?? `The MCP server answered ${res.status} ${res.statusText}.`;
    return { ok: false, error: { code: 'error', message }, trace: [{ n: 'Call the MCP server', ok: false, detail: message }], ms: 0, outcome: 'error · server' };
  }
  return { ok: a.ok, result: a.result, error: a.error, trace: a.trace, ms: a.ms, outcome: a.outcome, caseId: a.case_id ?? undefined };
}

// ---------------------------------------------------------------- agent tools from the action registry
export interface RegistryTool { id: string; exposedAs: string; risk: string; riskLabel: string; perm: string; desc: string }
export function registryTools(): RegistryTool[] {
  const order = ['read', 'draft', 'act', 'commit'];
  const all: { id: string; risk: string; perm: string | null; desc: string }[] = actionCatalog();
  const RL = ref('RISK_LABEL');
  return all.filter((A) => A.risk !== 'system').sort((a, b) => order.indexOf(a.risk) - order.indexOf(b.risk)).map((A) => ({
    id: A.id, exposedAs: A.risk === 'commit' ? A.id + '.prepare' : A.id, risk: A.risk, riskLabel: RL[A.risk], perm: A.perm || 'any signed-in role', desc: A.desc,
  }));
}

// ---------------------------------------------------------------- agent test bench
/** The bench ran the demo's in-browser agent layer and is not available yet: the page lists the cases only. */
export interface BenchCase { i: number; label: string }
export const benchCases = (): BenchCase[] =>
  // the reference drops the questions the demo builds from live data (functions): those show their intent id
  ref('AF_EVALS').map((x, i) => ({ i, label: (x.q ?? x.intent) + ' · as ' + x.as }));
