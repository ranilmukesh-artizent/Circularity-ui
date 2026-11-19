/**
 * MCP & Tools: the governed tool catalog, agent registry, permission matrix, call log, enterprise MCP servers consumed
 * as a client, and the tool playground. Server proposals live in access.ts (they are access requests).
 */
import { bump, engine } from '../engine/engine';
import { canRoute } from './session';

/* eslint-disable @typescript-eslint/no-explicit-any */
const e = () => engine();

export interface ToolInput { t: string; req: boolean; ex: unknown }
export interface Tool { id: string; desc: string; rw: 'read' | 'write'; step: number[]; approval: string; input: Record<string, ToolInput> }
export interface McpAgent { id: string; name: string; step: string; scopes: string[]; tools: string[]; limit: string; calls: number }
export interface ClientServer { id: string; name: string; owner: string; status: string; tools: string[]; used: string }
export interface ToolCall { ts: Date | string; agent: string; tool: string; caseId: string; tenant: string; lat: number; outcome: string; step: number }

export const tools = (): Tool[] => e()<Tool[]>('TOOLS');
export const toolById = (id: string): Tool | undefined => tools().find((t) => t.id === id);
export const mcpAgents = (): McpAgent[] => e()<McpAgent[]>('AGENTS');
export const hardRules = (): string[] => e()<string[]>('HARD_RULES').slice();
export const clientServers = (): ClientServer[] => e()<ClientServer[]>('CLIENT_SERVERS').slice();
export const toolCalls = (): ToolCall[] => e()<ToolCall[]>('CALLS').slice();
export const tenantList = (): string[] => e()<string[]>('TENANTS');

/** A journey step as the demo's stp()/stpn() chips show it. */
export interface JourneyStep { n: number; name: string; status: string; desc: string }
export function journeyStep(n: number): JourneyStep {
  const m = e()<(n: number) => number>('jmap')(n);
  const j = e()<any[][]>('JSTEPS')[m - 1];
  return { n: m, name: j[1], status: j[2] === 'built' ? '' : j[2], desc: j[3] };
}

/** The tool's MCP descriptor (name, inputSchema, annotations). */
export const toolSchema = (t: Tool): unknown => e()<(t: Tool) => unknown>('schemaOf')(t);
export const exampleInput = (t: Tool): Record<string, unknown> => e()<(t: Tool) => Record<string, unknown>>('exampleInput')(t);
/** The agent the playground calls as by default for this tool. */
export const autoAgent = (toolId: string): string => e()<(id: string) => string>('autoAgent')(toolId);

export type PermKind = 'deny' | 'gate' | 'scope' | 'own' | 'read';
export interface PermCell { k: PermKind; l: string; tip: string }
export const permCell = (a: McpAgent, t: Tool, tenant: string): PermCell =>
  e()<(a: McpAgent, t: Tool, ten: string) => PermCell>('permCell')(a, t, tenant);
export const PERM_CHIP: Record<PermKind, string> = { deny: 'chip line', gate: 'chip y', scope: 'chip dk', own: 'chip warn', read: 'chip ok' };

/** Syntax-highlighted JSON as the demo prints it (escaped markup with .k/.s/.n spans). */
export const jsonHtml = (o: unknown): string => e()<(o: unknown) => string>('jsonHtml')(o);

/** May the signed-in account open the case behind a call? */
export const caseOpenable = (caseId: string): boolean =>
  !!e()<Record<string, unknown>>('CASE_BY_ID')[caseId] && canRoute({ page: 'product', a: caseId, b: null }) === true;

export interface TraceStep { n: string; ok: boolean; detail: string; ms: number }
export interface ToolRun {
  ok: boolean; result?: unknown; error?: Record<string, unknown>; trace: TraceStep[]; ms: number; outcome: string; caseId?: string;
}

/**
 * Run a tool in the playground (simulation, like the demo's pgRun: it is not a registry action). The call is checked
 * for agent scope, input schema and tenant boundary, answered from the seeded data, and added to the call log.
 */
export function runPlaygroundTool(toolId: string, agentId: string, tenant: string, raw: string): ToolRun {
  const g = e();
  const o = g<(t: string, a: string, ten: string, raw: string) => any>('runTool')(toolId, agentId, tenant, raw);
  const t = toolById(toolId)!;
  g<ToolCall[]>('CALLS').unshift({ ts: new Date(), agent: o.ag.name, tool: toolId, caseId: o.caseId || '—', tenant, lat: o.ms, outcome: o.outcome, step: t.step[0] });
  bump();
  return { ok: o.ok, result: o.result, error: o.error, trace: o.trace, ms: o.ms, outcome: o.outcome, caseId: o.caseId };
}

// ---------------------------------------------------------------- agent tools from the action registry
export interface RegistryTool { id: string; exposedAs: string; risk: string; riskLabel: string; perm: string; desc: string }
export function registryTools(): RegistryTool[] {
  const g = e();
  const order = ['read', 'draft', 'act', 'commit'];
  const L = Object.values(g<Record<string, any>>('ACTIONS')).filter((A) => A.risk !== 'system').sort((a, b) => order.indexOf(a.risk) - order.indexOf(b.risk));
  const RL = g<Record<string, string>>('RISK_LABEL');
  return L.map((A) => ({
    id: A.id, exposedAs: A.risk === 'commit' ? A.id + '.prepare' : A.id, risk: A.risk, riskLabel: RL[A.risk], perm: A.perm || 'any signed-in role', desc: A.desc,
  }));
}

// ---------------------------------------------------------------- agent test bench
export interface BenchCase { i: number; label: string }
export const benchCases = (): BenchCase[] =>
  e()<any[]>('AF_EVALS').map((x, i) => ({ i, label: (typeof x.q === 'function' ? x.q() : x.q) + ' · as ' + x.as }));

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
/** Run one catalog intent test (read-only: the bench restores the session afterwards). */
export function runBench(i: number): BenchResult | null {
  const g = e();
  const r = g<(only?: unknown) => any[]>('afEvalRun')(g<any[]>('AF_EVALS')[i])[0];
  return r ? toResult(r) : null;
}
/** Run every intent and safety test. */
export function runBenchAll(): BenchResult[] {
  return e()<() => any[]>('afEvalRun')().map(toResult);
}
/** The badge markup for a call (the demo's afBadge). */
export const benchBadgeHtml = (k: string): string => e()<(k: string) => string>('afBadge')(k);
