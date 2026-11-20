/**
 * MCP & Tools: the governed tool catalog, agent registry, permission matrix, call log, enterprise MCP servers consumed
 * as a client, and the tool playground. Server proposals live in access.ts (they are access requests).
 *
 * With VITE_BACKEND=api (apps/api/di/screens/mcp.py has the mapping): the agents, the permission matrix, the call log
 * and the client servers from GET /api/screens/mcp/*; the tools, hard rules, tenants, journey steps and risk labels are
 * reference lists; the action registry is GET /api/actions. The playground calls the real MCP server (POST /mcp,
 * JSON-RPC tools/call, apps/api/di/mcp/) as the signed-in account, so its calls land in the real call log. The agent
 * test bench ran the demo's in-browser agent layer and is not available with the API (the server's Ask runs the
 * safety checks: GET /api/checks).
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import { bump, engine } from '../engine/engine';
import { actionCatalog } from './actions';
import { API } from './backend';
import { accessToken, cached, invalidate, ref, withQuery } from './client';
import { canRoute } from './session';

const e = () => engine();

export interface ToolInput { t: string; req: boolean; ex: unknown }
export interface Tool { id: string; desc: string; rw: 'read' | 'write'; step: number[]; approval: string; input: Record<string, ToolInput> }
export interface McpAgent { id: string; name: string; step: string; scopes: string[]; tools: string[]; limit: string; calls: number }
export interface ClientServer { id: string; name: string; owner: string; status: string; tools: string[]; used: string }
export interface ToolCall { ts: Date | string; agent: string; tool: string; caseId: string; tenant: string; lat: number; outcome: string; step: number }

type ApiCall = ToolCall & { openable: boolean };
const callsA = () => cached<{ calls: ApiCall[] }>('/api/screens/mcp/calls').calls;

export const tools = (): Tool[] => (API ? ref<Tool[]>('TOOLS') : e()<Tool[]>('TOOLS'));
export const toolById = (id: string): Tool | undefined => tools().find((t) => t.id === id);
export const mcpAgents = (): McpAgent[] => (API ? cached<{ agents: McpAgent[] }>('/api/screens/mcp/agents').agents : e()<McpAgent[]>('AGENTS'));
export const hardRules = (): string[] => (API ? ref<string[]>('HARD_RULES') : e()<string[]>('HARD_RULES')).slice();
export const clientServers = (): ClientServer[] =>
  (API ? cached<{ servers: ClientServer[] }>('/api/screens/mcp/client').servers : e()<ClientServer[]>('CLIENT_SERVERS')).slice();
export const toolCalls = (): ToolCall[] => (API ? callsA() : e()<ToolCall[]>('CALLS')).slice();
export const tenantList = (): string[] => (API ? ref<string[]>('TENANTS') : e()<string[]>('TENANTS'));

/** A journey step as the demo's stp()/stpn() chips show it. */
export interface JourneyStep { n: number; name: string; status: string; desc: string }
export function journeyStep(n: number): JourneyStep {
  const m = API ? ref<number[]>('JMAP')[n] || n : e()<(n: number) => number>('jmap')(n);
  const j = (API ? ref<any[][]>('JSTEPS') : e()<any[][]>('JSTEPS'))[m - 1];
  return { n: m, name: j[1], status: j[2] === 'built' ? '' : j[2], desc: j[3] };
}

/** The tool's MCP descriptor (name, inputSchema, annotations). */
export function toolSchema(t: Tool): unknown {
  if (!API) return e()<(t: Tool) => unknown>('schemaOf')(t);
  const props: Record<string, { type: string }> = {}, req: string[] = [];
  Object.entries(t.input).forEach(([k, v]) => { props[k] = { type: v.t }; if (v.req) req.push(k); });
  return {
    name: t.id, description: t.desc, inputSchema: { type: 'object', properties: props, required: req },
    annotations: { readOnlyHint: t.rw === 'read', requiresHumanApproval: t.approval === 'human approval required' },
  };
}
export const exampleInput = (t: Tool): Record<string, unknown> =>
  API ? Object.fromEntries(Object.entries(t.input).map(([k, v]) => [k, v.ex])) : e()<(t: Tool) => Record<string, unknown>>('exampleInput')(t);
/** The agent the playground calls as by default for this tool. */
export function autoAgent(toolId: string): string {
  if (!API) return e()<(id: string) => string>('autoAgent')(toolId);
  const want = toolId === 'request_missing_evidence' ? 'gap' : toolId === 'send_instruction' || toolId === 'request_approval' ? 'coordinator'
    : toolId === 'reconcile_outcome' ? 'reconciler' : 'finder';
  const A = mcpAgents();
  return (A.find((a) => a.tools.includes(toolId) && a.id === want) ?? A.find((a) => a.tools.includes(toolId)))!.id;
}

export type PermKind = 'deny' | 'gate' | 'scope' | 'own' | 'read';
export interface PermCell { k: PermKind; l: string; tip: string }
export function permCell(a: McpAgent, t: Tool, tenant: string): PermCell {
  if (!API) return e()<(a: McpAgent, t: Tool, ten: string) => PermCell>('permCell')(a, t, tenant);
  const m = cached<{ rows: { agent: string; cells: (PermCell & { tool: string })[] }[] }>(withQuery('/api/screens/mcp/matrix', { tenant }));
  const c = m.rows.find((r) => r.agent === a.id)?.cells.find((x) => x.tool === t.id);
  return c ? { k: c.k, l: c.l, tip: c.tip } : { k: 'deny', l: '—', tip: `${a.name} has no scope for ${t.id}` };
}
export const PERM_CHIP: Record<PermKind, string> = { deny: 'chip line', gate: 'chip y', scope: 'chip dk', own: 'chip warn', read: 'chip ok' };

/** May the signed-in account open the case behind a call? */
export const caseOpenable = (caseId: string): boolean =>
  API ? callsA().some((c) => c.caseId === caseId && c.openable)
    : !!e()<Record<string, unknown>>('CASE_BY_ID')[caseId] && canRoute({ page: 'product', a: caseId, b: null }) === true;

export interface TraceStep { n: string; ok: boolean; detail: string; ms?: number }
export interface ToolRun {
  ok: boolean; result?: unknown; error?: Record<string, unknown>; trace: TraceStep[]; ms: number; outcome: string; caseId?: string;
}

/**
 * Run a tool in the playground. The call is checked for agent scope, input schema and tenant boundary, answered from
 * the data, and added to the call log. With the API it is a real MCP tools/call on /mcp (the bearer token is the
 * signed-in account's, X-Agent the agent it calls as, X-Tenant the tenant); in the demo, a simulation (pgRun).
 */
export async function runPlaygroundTool(toolId: string, agentId: string, tenant: string, raw: string): Promise<ToolRun> {
  if (API) return mcpCall(toolId, agentId, tenant, raw);
  const g = e();
  const o = g<(t: string, a: string, ten: string, raw: string) => any>('runTool')(toolId, agentId, tenant, raw);
  const t = toolById(toolId)!;
  g<ToolCall[]>('CALLS').unshift({ ts: new Date(), agent: o.ag.name, tool: toolId, caseId: o.caseId || '—', tenant, lat: o.ms, outcome: o.outcome, step: t.step[0] });
  bump();
  return { ok: o.ok, result: o.result, error: o.error, trace: o.trace, ms: o.ms, outcome: o.outcome, caseId: o.caseId };
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
  const all: { id: string; risk: string; perm: string | null; desc: string }[] = API ? actionCatalog() : Object.values(e()<Record<string, any>>('ACTIONS'));
  const RL = API ? ref<Record<string, string>>('RISK_LABEL') : e()<Record<string, string>>('RISK_LABEL');
  return all.filter((A) => A.risk !== 'system').sort((a, b) => order.indexOf(a.risk) - order.indexOf(b.risk)).map((A) => ({
    id: A.id, exposedAs: A.risk === 'commit' ? A.id + '.prepare' : A.id, risk: A.risk, riskLabel: RL[A.risk], perm: A.perm || 'any signed-in role', desc: A.desc,
  }));
}

// ---------------------------------------------------------------- agent test bench
/** The bench runs the demo's in-browser agent layer: not with the API. */
export const benchAvailable = !API;
export interface BenchCase { i: number; label: string }
export const benchCases = (): BenchCase[] =>
  // the reference drops the questions the demo builds from live data (functions): those show their intent id
  (API ? ref<any[]>('AF_EVALS') : e()<any[]>('AF_EVALS')).map((x, i) => ({ i, label: (typeof x.q === 'function' ? x.q() : x.q ?? x.intent) + ' · as ' + x.as }));

export interface BenchCall { action: string; badge: string; input: string; msg: string; ok: boolean }
export interface BenchResult {
  ok: boolean; skipped: boolean; why: string; expected: string; card: string; name: string;
  /** Present when the intent ran: the calls it made, its answer and its cards (rendered markup). */
  run?: { calls: BenchCall[]; text: string; cardsHtml: string[] };
}
function toResult(r: any): BenchResult {
  const card = typeof r.e.card === 'function' ? r.e.card() : r.e.card;
  const cardHtml = e()<(c: unknown) => string>('afCardHTML');
  return {
    ok: !!r.ok, skipped: !!r.skipped, why: r.why || '', expected: r.e.intent || 'fallback', card: card || 'no card',
    name: (typeof r.e.q === 'function' ? r.e.q() : r.e.q) || r.e.name || '',
    run: r.run ? { calls: r.run.calls.map((c: any) => ({ action: c.action, badge: c.badge, input: c.input, msg: c.msg, ok: !!c.ok })), text: r.run.text_out, cardsHtml: r.run.cards.map((c: unknown) => cardHtml(c)) } : undefined,
  };
}
/** Run one catalog intent test (read-only: the bench restores the session afterwards). Null when not available. */
export function runBench(i: number): BenchResult | null {
  if (API) return null;
  const g = e();
  const r = g<(only?: unknown) => any[]>('afEvalRun')(g<any[]>('AF_EVALS')[i])[0];
  return r ? toResult(r) : null;
}
/** Run every intent and safety test (none when not available). */
export function runBenchAll(): BenchResult[] {
  if (API) return [];
  return e()<() => any[]>('afEvalRun')().map(toResult);
}
/** The tooltip of a call's source badge (the demo's AF_BADGE_TIP, drawn by afBadge). */
export const benchBadgeTip = (k: string): string => (API ? ref<Record<string, string>>('AF_BADGE_TIP') : e()<Record<string, string>>('AF_BADGE_TIP'))[k] || k;
