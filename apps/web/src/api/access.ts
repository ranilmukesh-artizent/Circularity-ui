/**
 * Access & Governance: accounts, identity provider, Approver delegations, access requests (tenant access and MCP server
 * proposals), and the agent-first governance settings (autonomy, approval limits, kill switches, metrics).
 * Engine mode reads the engine's state; with VITE_BACKEND=api, GET /api/screens/access (one answer, keyed by section),
 * GET /api/screens/mcp/proposals and the reference lists (di/screens/access.py has the mapping). Every change goes
 * through invoke() in the page; after one that may change what the signed-in account may do, call refreshAccess().
 */
import { engine } from '../engine/engine';
import { API } from './backend';
import { cached, ref, refreshMe } from './client';
import { fmtDate } from './format';
import type { Account, RolePolicy } from './types';

/* eslint-disable @typescript-eslint/no-explicit-any */
const e = () => engine();

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
export const refreshAccess = (): Promise<void> => (API ? refreshMe() : Promise.resolve());

// ---------------------------------------------------------------- requests
export type ReqKind = 'tenant' | 'mcp';
export type ReqStatus = 'pending' | 'approved' | 'declined';
export interface McpServerSpec { name: string; owner: string; purpose: string; tools: string[]; access: 'read' | 'write' | string; data: string }
export interface AccessRequest {
  id: string; kind: ReqKind; status: ReqStatus; by: string; byId: string; at: Date | string;
  decidedBy?: string; decidedAt?: Date | string; note?: string;
  tenant?: string; reason?: string; server?: McpServerSpec;
  /** API mode: may the signed-in account decide it (the server's canDecide). */
  can_decide?: boolean;
}

export const REQ_KIND: Record<ReqKind, string> = { tenant: 'Tenant access', mcp: 'MCP server proposal' };

export const requests = (): AccessRequest[] => (API ? screen().requests.requests.slice() : e()<{ reqs: AccessRequest[] }>('S').reqs.slice());
export const mcpProposals = (): AccessRequest[] =>
  API ? cached<{ proposals: AccessRequest[] }>('/api/screens/mcp/proposals').proposals.slice() : requests().filter((r) => r.kind === 'mcp');
/** May the signed-in account decide this request (pending, and the Approver holds the delegation or is Admin)? */
export const canDecide = (r: AccessRequest): boolean => (API ? !!r.can_decide : e()<(r: AccessRequest) => boolean>('canDecide')(r));
/** Requests waiting for the signed-in account. */
export function inboxRequests(): AccessRequest[] {
  if (!API) return e()<() => AccessRequest[]>('inboxReqs')();
  const { requests: all, inbox } = screen().requests;
  return all.filter((r) => inbox.includes(r.id));
}

// ---------------------------------------------------------------- delegations
export interface Delegation { k: string; label: string; desc: string; on: boolean }
export function delegations(): Delegation[] {
  if (API) return screen().delegations;
  const D = e()<string[][]>('DELEG');
  const S = e()<{ deleg: Record<string, boolean> }>('S');
  return D.map(([k, label, desc]) => ({ k, label, desc, on: !!S.deleg[k] }));
}
/** "decisions and overrides", "MCP server proposals" (the demo's dlab). */
export const delegationLabel = (d: Delegation): string => d.label.toLowerCase().replace('mcp', 'MCP');

// ---------------------------------------------------------------- accounts
export interface AccountRow { account: Account; policy: RolePolicy; tenants: string; landsOn: string }
export function accountRows(): AccountRow[] {
  if (API) return screen().accounts;
  const g = e();
  const ACCOUNTS = g<Account[]>('ACCOUNTS');
  const RP = g<Record<string, RolePolicy>>('ROLE_POLICY');
  const grants = g<{ grants: Record<string, string[]> }>('S').grants;
  const HOME = g<Record<string, string>>('HOME_LABEL');
  const homeFor = g<(r: string) => string>('homeFor');
  return ACCOUNTS.map((a) => {
    const P = RP[a.role];
    const h = homeFor(a.role);
    return {
      account: a, policy: P,
      tenants: P.tenantScoped ? [a.tenant].concat(grants[a.id] || []).join(', ') : 'All',
      landsOn: HOME[h] || h,
    };
  });
}

// ---------------------------------------------------------------- identity provider
export interface IdpUser { id: string; email: string; acct: string | null; role?: string }
export interface Ooo { email: string; from: string; until: string }
export interface Idp { src: 'approles' | 'groups'; lastSync: Date | string; groups: Record<string, string>; users: IdpUser[]; ooo: Ooo[] }

export const idp = (): Idp => (API ? screen().identity : e()<{ idp: Idp }>('S').idp);
/** The role a directory user maps to (the server sends it with each user). */
export const idpRoleOf = (u: IdpUser): string => (API ? u.role ?? '' : e()<(u: IdpUser) => string>('idpRoleOf')(u));
export const idpRoles = (): string[] => (API ? ref<string[]>('IDP_ROLES') : e()<string[]>('IDP_ROLES'));
export const facilities = (): string[] => (API ? ref<string[]>('FACILITIES') : e()<string[]>('FACILITIES'));
/** "07 Oct 14:20" (the demo's orT). */
export const fmtDateTime = (d: Date | string | null | undefined): string =>
  d ? fmtDate(d) + ' ' + new Date(d).toISOString().slice(11, 16) : '—';

// ---------------------------------------------------------------- trust and governance
export type Level = 'off' | 'suggest' | 'prepare' | 'act';
export interface LevelDef { k: Level; label: string; desc: string }
export interface AutoType { k: string; t: string; acts: string[]; def: Level; max: Level }

export const levels = (): LevelDef[] =>
  (API ? ref<string[][]>('AF_LEVELS') : e()<string[][]>('AF_LEVELS')).map(([k, label, desc]) => ({ k: k as Level, label, desc }));
export const levelRank = (l: Level): number => (API ? ref<Record<string, number>>('AF_LV_RANK') : e()<Record<string, number>>('AF_LV_RANK'))[l];
export const autoTypes = (): AutoType[] => (API ? ref<AutoType[]>('AF_AUTO_TYPES') : e()<AutoType[]>('AF_AUTO_TYPES'));
export const autoLevel = (role: string, type: string): Level =>
  API ? screen().autonomy.matrix[role]?.[type] ?? 'prepare' : e()<(r: string, k: string) => Level>('afAutoLevel')(role, type);
export const roles = (): string[] => Object.keys(API ? ref<Record<string, RolePolicy>>('ROLE_POLICY') : e()<Record<string, RolePolicy>>('ROLE_POLICY'));

interface AfCfg { limits: Record<string, number | null>; self: boolean; off: Record<string, boolean>; max: { actions: number; bulk: number } }
const cfg = (): AfCfg => e()<{ cfg: AfCfg }>('AF').cfg;
/** Approval limit in dollars; null means unlimited. */
export const approvalLimit = (role: string): number | null => {
  const v = API ? screen().limits.limits[role] : cfg().limits[role];
  return v === Infinity || v == null ? null : v;
};
export const selfApproveAllowed = (): boolean => (API ? screen().limits.self_approve : !!cfg().self);
export const runLimits = (): { actions: number; bulk: number } => ({ ...(API ? screen().limits.run_limits : cfg().max) });

export interface GovAgent { id: string; name: string; scopes: string[]; limit: string; stopped: boolean; prepared: number }
export function governedAgents(): GovAgent[] {
  if (API) return screen().agentsx.agents;
  const g = e();
  const journal = g<{ journal: { prep?: string }[] }>('AF').journal;
  return g<any[]>('AGENTS').map((a) => ({
    id: a.id, name: a.name, scopes: a.scopes.slice(), limit: a.limit,
    stopped: !!cfg().off[a.id], prepared: journal.filter((x) => x.prep === a.id).length,
  }));
}
/** The six hard rules (never configurable). */
export const hardRules = (): string[] => (API ? ref<string[]>('HARD_RULES') : e()<string[]>('HARD_RULES')).slice();

export interface AgentMetrics {
  interactions: number | null; approvals: number; share: Record<string, { all: number; agent: number }>;
  acceptance: number | null; edit: number | null; undo: number | null; fallback: number | null;
  ttd: number | null; runs: number; ms: number | null;
}
export const agentMetrics = (): AgentMetrics => (API ? screen().metrics : e()<() => AgentMetrics>('afMetrics')());
/** 42% or — (the demo's pctTxt). */
export const pctTxt = (v: number | null | undefined): string => (v == null ? '—' : Math.round(v * 100) + '%');
