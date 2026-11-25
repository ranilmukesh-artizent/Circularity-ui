/**
 * Access & Governance: accounts, identity provider, Approver delegations, access requests (tenant access and MCP server
 * proposals), and the agent-first governance settings (autonomy, approval limits, kill switches, metrics).
 * GET /api/screens/access (one answer, keyed by section), GET /api/screens/mcp/proposals and the reference lists
 * (di/services/screens/access.py has the mapping). Every change goes through invoke() in the page; after one that may change
 * what the signed-in account may do, call refreshAccess().
 */
import { invoke, read } from './actions';
import { cached, ref, refreshMe } from './client';
import { fmtDate, fmtDateYear } from './format';
import { can, currentAccount } from './session';
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
/**
 * Maker-checker: a pending request the signed-in account made itself and would otherwise decide. The server refuses
 * it; the page shows why, with the buttons disabled.
 */
export const ownPending = (r: AccessRequest): boolean =>
  r.status === 'pending' && r.byId === currentAccount()?.id && can(r.kind === 'tenant' ? 'approve.tenantAccess' : 'approve.mcp');
export const OWN_REQUEST_NOTE = 'You made this request, so another person must decide it.';

// ---------------------------------------------------------------- tenant grants (plan 8 UI gaps)
/** A live tenant grant: not revoked, not past its end (expires_at null: no end). */
export interface TenantGrant {
  account_id: string; account: string; tenant: string; granted_by: string; granted_at: string; expires_at: string | null;
}
/** The live grants, for Admin and the Approver with the tenantAccess delegation (access.grants). */
export const liveGrants = (): TenantGrant[] => (can('approve.tenantAccess') ? read<{ grants: TenantGrant[] }>('access.grants').grants : []);

export interface TenantOption { id: string; name: string; pending: boolean }
export interface MyAccess { requests: AccessRequest[]; grants: { tenant: string; expires_at: string | null }[]; options: TenantOption[] }
/** The signed-in account's own tenant requests, live grants and the tenants it may still ask for (access.myAccess). */
export const myAccess = (): MyAccess => read<MyAccess>('access.myAccess');

/** The ends an approver can choose for a tenant grant, in hours (null: no end). */
export const GRANT_ENDS: { hours: number | null; label: string }[] = [
  { hours: 8, label: '8 hours' },
  { hours: 24, label: '1 day' },
  { hours: 168, label: '7 days' },
  { hours: 720, label: '30 days' },
  { hours: null, label: 'No end' },
];
/** "No end" or "Ends 07 Oct 2026 17:00 UTC". */
export const grantEndText = (expires: string | null | undefined): string =>
  expires ? 'Ends ' + fmtDateYear(expires) + ' ' + new Date(expires).toISOString().slice(11, 16) + ' UTC' : 'No end';

// ---------------------------------------------------------------- role matrix and "test a user" (P9-0.13)
export interface MatrixPermRow { perm: string; roles: Record<string, boolean> }
export interface MatrixPageRow { page: string; roles: Record<string, boolean> }
export interface RoleMatrix { roles: string[]; permissions: MatrixPermRow[]; pages: MatrixPageRow[] }
export interface TestUserResult {
  user_id: string | null; email: string; found: boolean; role: string | null; why: string;
  /** The directory group the role came from (P9-8.10), null for a deputy or an unknown person. */
  via_group: string | null; source: 'directory' | 'group map' | 'none';
  account: { id: string; label: string } | null;
  tenants: string[]; warehouse: string | null; pages: string[]; permissions: string[]; delegations: string[];
  /** Approval limit in dollars; null: no limit. */
  approval_limit: number | null; self_approve: boolean;
}
/** Which role may do what and see which page (access.roleMatrix; needs manageIdentity). */
export const roleMatrix = (): RoleMatrix => read<RoleMatrix>('access.roleMatrix');
/** What a person gets today, without signing in (access.testUser; manageIdentity or tenant access approval). */
export const testUser = (email: string, groups?: string[]): TestUserResult =>
  read<TestUserResult>('access.testUser', groups ? { email, groups } : { email });

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
/** One row of the directory group to role map (P9-8.10); only an approved row inside its dates is in force. */
export interface GroupMapRow {
  id: number; group_id: string; role: string; org_unit_id: string | null; site: string | null; warehouse: string | null;
  valid_from: string | null; valid_to: string | null; status: 'draft' | 'approved' | 'retired';
  created_by: string; approved_by: string | null; created_at: string; approved_at: string | null;
}
export interface GroupMapInput {
  group_id: string; role: string; org_unit_id?: string; site?: string; warehouse?: string; valid_from?: string; valid_to?: string;
}
export interface Idp {
  src: 'approles' | 'groups'; lastSync: Date | string; groups: Record<string, string>; users: IdpUser[]; ooo: Ooo[]; group_map: GroupMapRow[];
}

export const idp = (): Idp => screen().identity;
/** The mapping rows, drafts and retired ones too (the Identity section). */
export const groupMap = (): GroupMapRow[] => idp().group_map;
/** Draft a mapping; another person approves it (access.saveGroupMap). */
export const saveGroupMap = (row: GroupMapInput) => invoke<{ id: number; status: string }>('access.saveGroupMap', { ...row });
/** Put a drafted mapping in force; not the person who drafted it (access.approveGroupMap). */
export const approveGroupMap = (id: number) => invoke<{ id: number; status: string }>('access.approveGroupMap', { id });
/** The role a directory user maps to (the server sends it with each user). */
export const idpRoleOf = (u: IdpUser): string => u.role ?? '';
export const idpRoles = (): string[] => ref('IDP_ROLES');
export const facilities = (): string[] => ref('FACILITIES');
/** "07 Oct 14:20" (the demo's orT). */
export const fmtDateTime = (d: Date | string | null | undefined): string =>
  d ? fmtDate(d) + ' ' + new Date(d).toISOString().slice(11, 16) : '—';

// ---------------------------------------------------------------- trust and governance
export type Level = 'off' | 'suggest' | 'prepare' | 'act';
export interface LevelDef { k: Level; label: string; desc: string }
export interface AutoType { k: string; t: string; acts: string[]; def: Level; max: Level }

export const levels = (): LevelDef[] => ref('AF_LEVELS').map(([k, label, desc]) => ({ k: k as Level, label, desc }));
export const levelRank = (l: Level): number => ref('AF_LV_RANK')[l];
export const autoTypes = (): AutoType[] => ref('AF_AUTO_TYPES');
export const autoLevel = (role: string, type: string): Level => screen().autonomy.matrix[role]?.[type] ?? 'prepare';
export const roles = (): string[] => Object.keys(ref('ROLE_POLICY'));

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
export const hardRules = (): string[] => ref('HARD_RULES').slice();

export interface AgentMetrics {
  interactions: number | null; approvals: number; share: Record<string, { all: number; agent: number }>;
  acceptance: number | null; edit: number | null; undo: number | null; fallback: number | null;
  ttd: number | null; runs: number; ms: number | null;
}
export const agentMetrics = (): AgentMetrics => screen().metrics;
/** 42% or — (the demo's pctTxt). */
export const pctTxt = (v: number | null | undefined): string => (v == null ? '—' : Math.round(v * 100) + '%');
