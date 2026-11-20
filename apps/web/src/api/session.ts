/**
 * Sign-in, the signed-in account and the access policy (the demo's RBAC block).
 * With VITE_BACKEND=api: POST /api/auth/login, GET /api/auth/me, GET /api/screens/nav/accounts and /scope, and the
 * reference lists (ROLE_POLICY, RB_AV, TENANTS, PERM_ALIAS, PAGES, RB_SECS); can, canPage and canRoute are evaluated
 * here from /api/auth/me as the demo does (di/screens/nav.py has the mapping).
 */
import { bump, engine, engineBooted, onEngineBoot } from '../engine/engine';
import { API } from './backend';
import { ApiError, cached, login, logout, ref, session } from './client';
import type { Account, RolePolicy, RouteRef } from './types';
import { setView, view } from './view';

const e = () => engine();

export const SIGNIN_DOMAIN = 'northfield.example';

export function currentAccount(): Account | null {
  if (API) return session()?.account ?? null;
  return e()<{ acct: Account | null }>('S').acct;
}

/** Resolve a typed sign-in ID or work email ("exec", "planner.b@northfield.example") to an account (engine only). */
export function resolveSignIn(idOrEmail: string): Account | null {
  return e()<(v: string) => Account | null>('signInResolve')(idOrEmail);
}

/** Engine only: switch the in-browser engine to this account. With the API, use signInWith(). */
export function signIn(account: Account): void {
  e()<(a: Account) => void>('setAcct')(account);
  bump();
}

export type SignInResult = { ok: true; account: Account } | { ok: false; message: string; field: 'id' | 'pw' };

/**
 * Sign in with an ID or work email and a password (the sign-in form). With the API the server checks both and its
 * messages are the demo's; authentication is simulated in both modes (any non-empty password is accepted).
 */
export async function signInWith(idOrEmail: string, password: string, sso = false): Promise<SignInResult> {
  const id = idOrEmail.trim();
  const unknown = sso
    ? 'We could not find an organisation for that email. Check it, or sign in with your password.'
    : 'We could not find that account. Check the email or user ID.';
  if (!id) return { ok: false, message: sso ? 'Enter your work email to continue with single sign-on.' : 'Enter your work email or user ID.', field: 'id' };
  if (!API) {
    const a = resolveSignIn(id);
    if (!a) return { ok: false, message: unknown, field: 'id' };
    if (!password && !sso) return { ok: false, message: 'Enter your password.', field: 'pw' };
    signIn(a);
    return { ok: true, account: a };
  }
  try {
    const me = await login(id, sso ? 'single-sign-on' : password); // simulated identity provider
    bridgeEngine(me.account.id);
    return { ok: true, account: me.account };
  } catch (err) {
    if (err instanceof ApiError && err.code === 'unknown_account') return { ok: false, message: unknown, field: 'id' };
    const msg = err instanceof Error ? err.message : String(err);
    const field = err instanceof ApiError && err.code === 'validation_error' && /password/i.test(msg) ? 'pw' : 'id';
    return { ok: false, message: msg, field };
  }
}

export function signOut(): void {
  if (API) {
    logout();
    bridgeEngine(null);
    return;
  }
  e()<(a: null) => void>('setAcct')(null);
  bump();
}

/**
 * While some areas still read the in-browser engine (B17 moves them one by one), keep its signed-in account the same
 * as the server's, so those pages show the same account's view.
 */
function bridgeEngine(id: string | null) {
  if (!engineBooted()) return;
  const g = e();
  g<(a: unknown) => void>('setAcct')(id ? g<(id: string) => unknown>('ACCT')(id) ?? null : null);
  const v = view();
  Object.assign(g<Record<string, unknown>>('S'), { tenant: v.tenant, ccMode: v.ccMode, lastAsset: v.lastAsset ?? undefined });
}
if (API) onEngineBoot(() => bridgeEngine(session()?.account.id ?? null));

export const accounts = (): Account[] => (API ? cached<Account[]>('/api/screens/nav/accounts') : e()<Account[]>('ACCOUNTS'));
export const accountById = (id: string): Account | undefined =>
  API ? accounts().find((a) => a.id === id) : e()<(id: string) => Account | undefined>('ACCT')(id);
export const signInEmail = (a: Account): string => {
  if (!API) return e()<(a: Account) => string>('signInEmail')(a);
  const known = (a as Account & { email?: string }).email ?? (accounts() as (Account & { email?: string })[]).find((x) => x.id === a.id)?.email;
  return known ?? a.id + '@' + SIGNIN_DOMAIN;
};
export const rolePolicy = (role: string): RolePolicy =>
  API ? ref<Record<string, RolePolicy>>('ROLE_POLICY')[role] : e()<Record<string, RolePolicy>>('ROLE_POLICY')[role];
/** Two-letter avatar per role (RB_AV in the demo). */
export const roleAvatar = (role: string): string =>
  (API ? ref<Record<string, string>>('RB_AV') : e()<Record<string, string>>('RB_AV'))[role] ?? role.slice(0, 2);

/** May the signed-in account use this permission (e.g. "approve.decisions", "manageIntegrations")? */
export function can(perm: string): boolean {
  if (!API) return e()<(p: string) => boolean>('can')(perm);
  const me = session();
  if (!me) return false;
  const p = ref<Record<string, string>>('PERM_ALIAS')[perm] ?? perm;
  return me.permissions.includes(p);
}

/** May it see this page, or this section of the page? */
export function canPage(page: string, section?: string): boolean {
  if (!API) return e()<(p: string, s?: string) => boolean>('canPage')(page, section);
  const secs = session()?.pages[page];
  if (!secs) return false;
  return !section || secs.includes(section);
}

/** Is a case inside the account's tenants and warehouse? null when there is no such case. */
function recordOK(caseId: string | null): boolean | null {
  const me = session();
  if (!me || !caseId) return null;
  const sc = cached<Record<string, [string, string]>>('/api/screens/nav/scope')[caseId];
  if (!sc) return null;
  const [owner, location] = sc;
  return me.tenants.includes(owner) && (!me.warehouse || location === me.warehouse);
}

/** true, false, or 'tenant' when the record belongs to a tenant or warehouse the account cannot see. */
export function canRoute(r: RouteRef): boolean | 'tenant' {
  if (!API) return e()<(r: RouteRef) => boolean | 'tenant'>('canRoute')(r);
  const p = r.page;
  if (!(p in ref<Record<string, unknown>>('PAGES')) || !canPage(p)) return false;
  if (p === 'product') {
    if (!r.a || ['received', 'expected', 'pools'].includes(r.a)) return canPage(p, r.a || 'received');
    if (r.a === 'asset') {
      if (!canPage(p, 'asset')) return false;
      const ok = recordOK(r.b);
      return ok === false ? 'tenant' : true;
    }
    const ok = recordOK(r.a);
    if (ok !== null) return canPage(p, 'case') ? (ok ? true : 'tenant') : false;
    return canPage(p, 'received');
  }
  if (p === 'mcp' && r.a === 'client') return canPage(p, 'client');
  return !r.a || !(p in ref<Record<string, unknown>>('RB_SECS')) || canPage(p, r.a);
}

/** The account's landing route, without the leading "#/" (e.g. "home", "product/received?focus=RT-1048"). */
export function homeRoute(a: Account | null = currentAccount()): string {
  if (!API) return e()<(a: Account | null) => string>('homeOf')(a);
  if (!a) return 'command';
  const me = session();
  if (me && me.account.id === a.id) return me.home;
  return a.home || rolePolicy(a.role)?.landing || 'command';
}

export const tenants = (): string[] => (API ? ref<string[]>('TENANTS') : e()<string[]>('TENANTS'));
export const allowedTenants = (): string[] => (API ? session()?.tenants ?? [] : e()<() => string[]>('allowedTenants')());

/** Keep the backend's idea of the theme in step (some chart colours are computed there). */
export function setBackendTheme(t: 'light' | 'dark'): void {
  if (API) {
    if (view().theme !== t) setView({ theme: t });
    return;
  }
  e()<{ theme: string }>('S').theme = t;
}

/** The tenant filter in the top bar: 'All' or one tenant. */
export const tenantFilter = (): string => (API ? view().tenant : e()<{ tenant: string }>('S').tenant);
export function setTenantFilter(t: string): void {
  if (API) {
    setView({ tenant: t });
    return;
  }
  e()<{ tenant: string }>('S').tenant = t;
  bump();
}
