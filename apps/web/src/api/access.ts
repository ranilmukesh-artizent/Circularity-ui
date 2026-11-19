/**
 * Access & Governance: accounts, identity provider, Approver delegations, access requests (tenant access and MCP server
 * proposals), and the agent-first governance settings (autonomy, approval limits, kill switches, metrics).
 * Reads go straight to the engine's state; every change goes through invoke() in the page.
 */
import { engine } from '../engine/engine';
import type { Account, RolePolicy } from './types';

/* eslint-disable @typescript-eslint/no-explicit-any */
const e = () => engine();

// ---------------------------------------------------------------- requests
export type ReqKind = 'tenant' | 'mcp';
export type ReqStatus = 'pending' | 'approved' | 'declined';
export interface McpServerSpec { name: string; owner: string; purpose: string; tools: string[]; access: 'read' | 'write' | string; data: string }
export interface AccessRequest {
  id: string; kind: ReqKind; status: ReqStatus; by: string; byId: string; at: Date | string;
  decidedBy?: string; decidedAt?: Date | string; note?: string;
  tenant?: string; reason?: string; server?: McpServerSpec;
}

export const REQ_KIND: Record<ReqKind, string> = { tenant: 'Tenant access', mcp: 'MCP server proposal' };

export const requests = (): AccessRequest[] => e()<{ reqs: AccessRequest[] }>('S').reqs.slice();
export const mcpProposals = (): AccessRequest[] => requests().filter((r) => r.kind === 'mcp');
/** May the signed-in account decide this request (pending, and the Approver holds the delegation or is Admin)? */
export const canDecide = (r: AccessRequest): boolean => e()<(r: AccessRequest) => boolean>('canDecide')(r);
/** Requests waiting for the signed-in account. */
export const inboxRequests = (): AccessRequest[] => e()<() => AccessRequest[]>('inboxReqs')();

// ---------------------------------------------------------------- delegations
export interface Delegation { k: string; label: string; desc: string; on: boolean }
export function delegations(): Delegation[] {
  const D = e()<string[][]>('DELEG');
  const S = e()<{ deleg: Record<string, boolean> }>('S');
  return D.map(([k, label, desc]) => ({ k, label, desc, on: !!S.deleg[k] }));
}
/** "decisions and overrides", "MCP server proposals" (the demo's dlab). */
export const delegationLabel = (d: Delegation): string => d.label.toLowerCase().replace('mcp', 'MCP');

// ---------------------------------------------------------------- accounts
export interface AccountRow { account: Account; policy: RolePolicy; tenants: string; landsOn: string }
export function accountRows(): AccountRow[] {
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

export const idp = (): Idp => e()<{ idp: Idp }>('S').idp;
export const idpRoleOf = (u: IdpUser): string => e()<(u: IdpUser) => string>('idpRoleOf')(u);
export const idpRoles = (): string[] => e()<string[]>('IDP_ROLES');
export const facilities = (): string[] => e()<string[]>('FACILITIES');
/** "07 Oct 14:20" (the demo's orT). */
export const fmtDateTime = (d: Date | string | null | undefined): string => e()<(d: unknown) => string>('orT')(d);

// ---------------------------------------------------------------- trust and governance
export type Level = 'off' | 'suggest' | 'prepare' | 'act';
export interface LevelDef { k: Level; label: string; desc: string }
export interface AutoType { k: string; t: string; acts: string[]; def: Level; max: Level }

export const levels = (): LevelDef[] => e()<string[][]>('AF_LEVELS').map(([k, label, desc]) => ({ k: k as Level, label, desc }));
export const levelRank = (l: Level): number => e()<Record<string, number>>('AF_LV_RANK')[l];
export const autoTypes = (): AutoType[] => e()<AutoType[]>('AF_AUTO_TYPES');
export const autoLevel = (role: string, type: string): Level => e()<(r: string, k: string) => Level>('afAutoLevel')(role, type);
export const roles = (): string[] => Object.keys(e()<Record<string, RolePolicy>>('ROLE_POLICY'));

interface AfCfg { limits: Record<string, number | null>; self: boolean; off: Record<string, boolean>; max: { actions: number; bulk: number } }
const cfg = (): AfCfg => e()<{ cfg: AfCfg }>('AF').cfg;
/** Approval limit in dollars; null means unlimited. */
export const approvalLimit = (role: string): number | null => {
  const v = cfg().limits[role];
  return v === Infinity || v == null ? null : v;
};
export const selfApproveAllowed = (): boolean => !!cfg().self;
export const runLimits = (): { actions: number; bulk: number } => ({ ...cfg().max });

export interface GovAgent { id: string; name: string; scopes: string[]; limit: string; stopped: boolean; prepared: number }
export function governedAgents(): GovAgent[] {
  const g = e();
  const journal = g<{ journal: { prep?: string }[] }>('AF').journal;
  return g<any[]>('AGENTS').map((a) => ({
    id: a.id, name: a.name, scopes: a.scopes.slice(), limit: a.limit,
    stopped: !!cfg().off[a.id], prepared: journal.filter((x) => x.prep === a.id).length,
  }));
}
/** The six hard rules (never configurable). */
export const hardRules = (): string[] => e()<string[]>('HARD_RULES').slice();

export interface AgentMetrics {
  interactions: number | null; approvals: number; share: Record<string, { all: number; agent: number }>;
  acceptance: number | null; edit: number | null; undo: number | null; fallback: number | null;
  ttd: number | null; runs: number; ms: number | null;
}
export const agentMetrics = (): AgentMetrics => e()<() => AgentMetrics>('afMetrics')();
/** 42% or — (the demo's pctTxt). */
export const pctTxt = (v: number | null | undefined): string => (v == null ? '—' : Math.round(v * 100) + '%');
