/** Sign-in, the signed-in account and the access policy (the demo's RBAC block). */
import { bump, engine } from '../engine/engine';
import type { Account, RolePolicy, RouteRef } from './types';

const e = () => engine();

export const SIGNIN_DOMAIN = 'northfield.example';

export function currentAccount(): Account | null {
  return e()<{ acct: Account | null }>('S').acct;
}

/** Resolve a typed sign-in ID or work email ("exec", "planner.b@northfield.example") to an account. */
export function resolveSignIn(idOrEmail: string): Account | null {
  return e()<(v: string) => Account | null>('signInResolve')(idOrEmail);
}

export function signIn(account: Account): void {
  e()<(a: Account) => void>('setAcct')(account);
  bump();
}

export function signOut(): void {
  e()<(a: null) => void>('setAcct')(null);
  bump();
}

export const accounts = (): Account[] => e()<Account[]>('ACCOUNTS');
export const accountById = (id: string): Account | undefined => e()<(id: string) => Account | undefined>('ACCT')(id);
export const signInEmail = (a: Account): string => e()<(a: Account) => string>('signInEmail')(a);
export const rolePolicy = (role: string): RolePolicy => e()<Record<string, RolePolicy>>('ROLE_POLICY')[role];
/** Two-letter avatar per role (RB_AV in the demo). */
export const roleAvatar = (role: string): string => e()<Record<string, string>>('RB_AV')[role] ?? role.slice(0, 2);

/** May the signed-in account use this permission (e.g. "approve.decisions", "manageIntegrations")? */
export const can = (perm: string): boolean => e()<(p: string) => boolean>('can')(perm);
/** May it see this page, or this section of the page? */
export const canPage = (page: string, section?: string): boolean => e()<(p: string, s?: string) => boolean>('canPage')(page, section);
/** true, false, or 'tenant' when the record belongs to a tenant or warehouse the account cannot see. */
export const canRoute = (r: RouteRef): boolean | 'tenant' => e()<(r: RouteRef) => boolean | 'tenant'>('canRoute')(r);

/** The account's landing route, without the leading "#/" (e.g. "home", "product/received?focus=RT-1048"). */
export function homeRoute(a: Account | null = currentAccount()): string {
  return e()<(a: Account | null) => string>('homeOf')(a);
}

export const tenants = (): string[] => e()<string[]>('TENANTS');
export const allowedTenants = (): string[] => e()<() => string[]>('allowedTenants')();

/** Keep the backend's idea of the theme in step (some chart colours are computed there). */
export function setBackendTheme(t: 'light' | 'dark'): void {
  e()<{ theme: string }>('S').theme = t;
}

/** The tenant filter in the top bar: 'All' or one tenant. */
export const tenantFilter = (): string => e()<{ tenant: string }>('S').tenant;
export function setTenantFilter(t: string): void {
  e()<{ tenant: string }>('S').tenant = t;
  bump();
}
