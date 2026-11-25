/**
 * Display helpers for Access's "Roles" panel: the role matrix and the "Test a user" card.
 * Owns the shaping of access.roleMatrix and access.testUser answers into table rows and card lines. Never decides
 * what anyone may do: the server computed every answer (policy.can, policy.can_page) and enforces access.
 * Implements the display side of P9-0.13.
 */
import type { RoleMatrix, TestUserResult } from '../../api/access';

export interface MatrixRow { label: string; key: string; cells: { role: string; allowed: boolean }[] }

const rowOf = (key: string, roles: Record<string, boolean>, order: string[]): MatrixRow => ({
  key,
  label: key,
  cells: order.map((role) => ({ role, allowed: !!roles[role] })),
});

/** The matrix as two lists of rows, cells in the order of `matrix.roles`: permissions first, then pages. */
export function rowsFor(matrix: RoleMatrix): { permissions: MatrixRow[]; pages: MatrixRow[] } {
  return {
    permissions: matrix.permissions.map((p) => rowOf(p.perm, p.roles, matrix.roles)),
    pages: matrix.pages.map((p) => rowOf(p.page, p.roles, matrix.roles)),
  };
}

export interface UserCard { title: string; why: string; lines: { label: string; value: string }[] }

const list = (xs: string[], none: string): string => (xs.length ? xs.join(', ') : none);

/** The card for one tested user: role, why, tenants, warehouse, pages and permissions. */
export function userCard(r: TestUserResult): UserCard {
  return {
    title: r.email + (r.role ? ' · ' + r.role : ''),
    why: r.why,
    lines: [
      { label: 'Found in', value: r.source === 'none' ? 'Nowhere: no mapped group' : r.source === 'group map' ? 'The group map (no account yet)' : 'The directory' },
      { label: 'Account', value: r.account ? r.account.label : 'None' },
      { label: 'Tenants', value: list(r.tenants, 'None') },
      { label: 'Warehouse', value: r.warehouse ?? 'Any' },
      { label: 'Approval limit', value: r.approval_limit == null ? 'No limit' : '$' + r.approval_limit.toLocaleString('en-US') },
      { label: 'Self-approval', value: r.self_approve ? 'Allowed within the limit' : 'Not allowed' },
      { label: 'Delegations', value: list(r.delegations, 'None') },
      { label: 'Pages', value: list(r.pages, 'None') },
      { label: 'Permissions', value: list(r.permissions, 'None') },
    ],
  };
}
