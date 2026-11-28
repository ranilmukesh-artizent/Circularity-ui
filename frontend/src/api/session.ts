/**
 * Sign-in, the signed-in account and the access policy (the demo's RBAC block), from di-api:
 * POST /api/auth/login, GET /api/auth/me, GET /api/screens/nav/accounts and /scope, and the reference lists
 * (ROLE_POLICY, RB_AV, TENANTS, PERM_ALIAS, PAGES, RB_SECS). can, canPage and canRoute are evaluated here from
 * /api/auth/me as the demo does (di/services/screens/nav.py has the mapping).
 */
import { ApiError, cached, http, login, logout, openSession, ref, refreshMe, session } from './client';
import type { Account, RolePolicy, RouteRef } from './types';
import { setView, view } from './view';

export const SIGNIN_DOMAIN = 'northfield.example';

export function currentAccount(): Account | null {
  return session()?.account ?? null;
}

export type SignInResult = { ok: true; account: Account } | { ok: false; message: string; field: 'id' | 'pw' };

/**
 * Sign in with an ID or work email and a password (the sign-in form). The server checks both and its messages are the
 * demo's; authentication is simulated (any non-empty password is accepted).
 */
export async function signInWith(idOrEmail: string, password: string, sso = false): Promise<SignInResult> {
  const id = idOrEmail.trim();
  const unknown = sso
    ? 'We could not find an organisation for that email. Check it, or sign in with your password.'
    : 'We could not find that account. Check the email or user ID.';
  if (!id) return { ok: false, message: sso ? 'Enter your work email to continue with single sign-on.' : 'Enter your work email or user ID.', field: 'id' };
  try {
    const me = await login(id, sso ? 'single-sign-on' : password); // simulated identity provider
    return { ok: true, account: me.account };
  } catch (err) {
    if (err instanceof ApiError && err.code === 'unknown_account') return { ok: false, message: unknown, field: 'id' };
    const msg = err instanceof Error ? err.message : String(err);
    const field = err instanceof ApiError && err.code === 'validation_error' && /password/i.test(msg) ? 'pw' : 'id';
    return { ok: false, message: msg, field };
  }
}

/** Is single sign-on set up (GET /api/auth/oidc/config)? Off when the call fails: the password form stays. */
export async function ssoConfig(): Promise<{ enabled: boolean; label?: string }> {
  try {
    return await http<{ enabled: boolean; label?: string }>('/api/auth/oidc/config');
  } catch {
    return { enabled: false };
  }
}

/** Where the browser goes to sign in at the organisation's identity provider (the server redirects on). */
export const SSO_START_URL = '/api/auth/oidc/start';

/** Swap the one-time code the server put in the return URL (`?sso=`) for the session; same result as signInWith. */
export async function exchangeSsoCode(code: string): Promise<SignInResult> {
  try {
    return { ok: true, account: (await openSession('/api/auth/oidc/exchange', { code })).account };
  } catch (err) {
    return { ok: false, message: err instanceof Error ? err.message : String(err), field: 'id' };
  }
}

export function signOut(): void {
  logout();
}

type AccountWithEmail = Account & { email?: string };

export const accounts = (): Account[] => cached<Account[]>('/api/screens/nav/accounts');
export const signInEmail = (a: Account): string => {
  const known = (a as AccountWithEmail).email ?? (accounts() as AccountWithEmail[]).find((x) => x.id === a.id)?.email;
  return known ?? a.id + '@' + SIGNIN_DOMAIN;
};
export const rolePolicy = (role: string): RolePolicy => ref('ROLE_POLICY')[role];
/** Two-letter avatar per role (RB_AV in the demo). */
export const roleAvatar = (role: string): string => ref('RB_AV')[role] ?? role.slice(0, 2);

/** May the signed-in account use this permission (e.g. "approve.decisions", "manageIntegrations")? */
export function can(perm: string): boolean {
  const me = session();
  if (!me) return false;
  const p = ref('PERM_ALIAS')[perm] ?? perm;
  return me.permissions.includes(p);
}

/** May it see this page, or this section of the page? */
export function canPage(page: string, section?: string): boolean {
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

/**
 * Read the session again before a route is refused for its tenant? The tenants an account sees are read at sign-in; one made
 * since (an org unit, a grant) is missing from them until the session is read again, so the first refusal of a route is checked
 * against a fresh session (`readFor`: the route the session was last read for). A second refusal stands.
 */
export const needsSessionRead = (allowed: boolean | 'tenant', readFor: string | null, key: string): boolean =>
  allowed === 'tenant' && readFor !== key;
export const rereadSession = (): Promise<void> => refreshMe();

/**
 * Tabs a page shows every account that can open it, beyond the demo's RB_SECS sections: `#/analytics/packs` is the
 * Analytics page's Packs tab (AnalyticsPage reads route.a === 'packs'; the used-car, telecom and medical case panels link to it).
 */
export const PAGE_TABS: Readonly<Record<string, readonly string[]>> = { analytics: ['packs'] };
const isPageTab = (r: RouteRef): boolean => !!r.a && (PAGE_TABS[r.page] ?? []).includes(r.a);

/** true, false, or 'tenant' when the record belongs to a tenant or warehouse the account cannot see. */
export function canRoute(r: RouteRef): boolean | 'tenant' {
  const p = r.page;
  // a page of the demo's PAGES, or one the server declares beyond them (plan 8: modeler, agents; in me.pages)
  if (!(p in ref('PAGES') || p in (session()?.pages ?? {})) || !canPage(p)) return false;
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
  return !r.a || !(p in ref('RB_SECS')) || isPageTab(r) || canPage(p, r.a);
}

/**
 * Is this route a page that exists at all (for some role)? An unknown page or section is "Page not found", not a
 * silent redirect Home. `known` is the menu's own section ids; a section must be one the demo's RB_SECS lists, or one the
 * menu shows this account, to count as existing. Pages whose second segment is an id (product, case ids) are not judged.
 */
export function isKnownRoute(r: RouteRef, known: string[] = []): boolean {
  const p = r.page;
  if (!(p in ref('PAGES') || p in (session()?.pages ?? {}))) return false;
  const secs = ref('RB_SECS') as Record<string, string[]>;
  if (!r.a || p === 'product' || p === 'oauth' || !(p in secs)) return true;
  return secs[p].includes(r.a) || known.includes(r.a) || isPageTab(r);
}

/** The account's landing route, without the leading "#/" (e.g. "home", "product/received?focus=RT-1048"). */
export function homeRoute(a: Account | null = currentAccount()): string {
  if (!a) return 'command';
  const me = session();
  if (me && me.account.id === a.id) return me.home;
  return a.home || rolePolicy(a.role)?.landing || 'command';
}

export const tenants = (): string[] => ref('TENANTS');
export const allowedTenants = (): string[] => session()?.tenants ?? [];

/** Remember the theme (some views read it). */
export function setBackendTheme(t: 'light' | 'dark'): void {
  if (view().theme !== t) setView({ theme: t });
}

/** The tenant filter in the top bar: 'All' or one tenant. */
export const tenantFilter = (): string => view().tenant;
export function setTenantFilter(t: string): void {
  setView({ tenant: t });
}
