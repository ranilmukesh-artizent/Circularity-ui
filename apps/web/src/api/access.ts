/**
 * Access & Governance: accounts, identity provider, Approver delegations, access requests (tenant access and MCP server
 * proposals), and the agent-first governance settings (autonomy, approval limits, kill switches, metrics).
 * GET /api/screens/access (one answer, keyed by section), GET /api/screens/mcp/proposals and the reference lists
 * (di/screens/access.py has the mapping). Every change goes through invoke() in the page; after one that may change
 * what the signed-in account may do, call refreshAccess().
 */
import { cached, ref, refreshMe } from './client';
import { fmtDate } from './format';
import type { Account, RolePolicy } from './types';

// ---------------------------------------------------------------- the API's answer
interface AccessScreen {
  sections: string[];
  accounts: AccountRow[];
  identity: Idp & { roles: string[] };
  delegations: Delegation[];
  requests: { requests: AccessRequest[]; inbox: string[] };
  autonomy: { levels: LevelDef[]; types: AutoType[]; matrix: Record<string, Record<string, Level>> };
  limits: { limits: Record<string, number | null>; self_approve: boolean; run_limits: { actions: number; bulk: number } };
  agentsx: { agents: GovAgent[]; hard_rules: string[] };
  metrics: AgentMetrics;
}
const screen = (): AccessScreen => cached<AccessScreen>('/api/screens/access');

/** Re-read the signed-in account's permissions after an access change (delegations, grants, mapping, limits). */
export const refreshAccess = (): Promise<void> => refreshMe();

// ---------------------------------------------------------------- requests
export type ReqKind = 'tenant' | 'mcp';
export type ReqStatus = 'pending' | 'approved' | 'declined';
export interface McpServerSpec { name: string; owner: string; purpose: string; tools: string[]; access: 'read' | 'write' | string; data: string }
export interface AccessRequest {
  id: string; kind: ReqKind; status: ReqStatus; by: string; byId: string; at: Date | string;
  decidedBy?: string; decidedAt?: Date | string; note?: string;
  tenant?: string; reason?: string; server?: McpServerSpec;
  /** May the signed-in account decide it (the server's canDecide). */
  can_decide?: boolean;
}

export const REQ_KIND: Record<ReqKind, string> = { tenant: 'Tenant access', mcp: 'MCP server proposal' };

export const requests = (): AccessRequest[] => screen().requests.requests.slice();
export const mcpProposals = (): AccessRequest[] => cached<{ proposals: AccessRequest[] }>('/api/screens/mcp/proposals').proposals.slice();
/** May the signed-in account decide this request (pending, and the Approver holds the delegation or is Admin)? */
export const canDecide = (r: AccessRequest): boolean => !!r.can_decide;
/** Requests waiting for the signed-in account. */
export function inboxRequests(): AccessRequest[] {
  const { requests: all, inbox } = screen().requests;
  return all.filter((r) => inbox.includes(r.id));
}

// ---------------------------------------------------------------- delegations
export interface Delegation { k: string; label: string; desc: string; on: boolean }
export function delegations(): Delegation[] {
  return screen().delegations;
}
/** "decisions and overrides", "MCP server proposals" (the demo's dlab). */
export const delegationLabel = (d: Delegation): string => d.label.toLowerCase().replace('mcp', 'MCP');

// ---------------------------------------------------------------- accounts
export interface AccountRow { account: Account; policy: RolePolicy; tenants: string; landsOn: string }
export function accountRows(): AccountRow[] {
  return screen().accounts;
}

// ---------------------------------------------------------------- identity provider
export interface IdpUser { id: string; email: string; acct: string | null; role?: string }
export interface Ooo { email: string; from: string; until: string }
export interface Idp { src: 'approles' | 'groups'; lastSync: Date | string; groups: Record<string, string>; users: IdpUser[]; ooo: Ooo[] }

export const idp = (): Idp => screen().identity;
/** The role a directory user maps to (the server sends it with each user). */
export const idpRoleOf = (u: IdpUser): string => u.role ?? '';
export const idpRoles = (): string[] => ref<string[]>('IDP_ROLES');
export const facilities = (): string[] => ref<string[]>('FACILITIES');
/** "07 Oct 14:20" (the demo's orT). */
export const fmtDateTime = (d: Date | string | null | undefined): string =>
  d ? fmtDate(d) + ' ' + new Date(d).toISOString().slice(11, 16) : '—';

// ---------------------------------------------------------------- trust and governance
export type Level = 'off' | 'suggest' | 'prepare' | 'act';
export interface LevelDef { k: Level; label: string; desc: string }
export interface AutoType { k: string; t: string; acts: string[]; def: Level; max: Level }

export const levels = (): LevelDef[] => ref<string[][]>('AF_LEVELS').map(([k, label, desc]) => ({ k: k as Level, label, desc }));
export const levelRank = (l: Level): number => ref<Record<string, number>>('AF_LV_RANK')[l];
export const autoTypes = (): AutoType[] => ref<AutoType[]>('AF_AUTO_TYPES');
export const autoLevel = (role: string, type: string): Level => screen().autonomy.matrix[role]?.[type] ?? 'prepare';
export const roles = (): string[] => Object.keys(ref<Record<string, RolePolicy>>('ROLE_POLICY'));

/** Approval limit in dollars; null means unlimited. */
export const approvalLimit = (role: string): number | null => {
  const v = screen().limits.limits[role];
  return v === Infinity || v == null ? null : v;
};
export const selfApproveAllowed = (): boolean => screen().limits.self_approve;
export const runLimits = (): { actions: number; bulk: number } => ({ ...screen().limits.run_limits });

export interface GovAgent { id: string; name: string; scopes: string[]; limit: string; stopped: boolean; prepared: number }
export function governedAgents(): GovAgent[] {
  return screen().agentsx.agents;
}
/** The six hard rules (never configurable). */
export const hardRules = (): string[] => ref<string[]>('HARD_RULES').slice();

export interface AgentMetrics {
  interactions: number | null; approvals: number; share: Record<string, { all: number; agent: number }>;
  acceptance: number | null; edit: number | null; undo: number | null; fallback: number | null;
  ttd: number | null; runs: number; ms: number | null;
}
export const agentMetrics = (): AgentMetrics => screen().metrics;
/** 42% or — (the demo's pctTxt). */
export const pctTxt = (v: number | null | undefined): string => (v == null ? '—' : Math.round(v * 100) + '%');
