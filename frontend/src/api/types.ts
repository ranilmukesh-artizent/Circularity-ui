export type Role = 'Planner' | 'Approver' | 'Engineer' | 'Finance' | 'Developer' | 'Executive' | 'Warehouse Manager' | 'Admin';

export interface Account {
  id: string;
  role: Role;
  label: string;
  tenant?: string;
  site?: string;
  warehouse?: string;
  home?: string;
}

export interface RolePolicy {
  desc: string;
  landing: string;
  perms: string[];
  pages: Record<string, string[]>;
  asTabs: string[];
  all?: boolean;
  tenantScoped?: boolean;
  warehouseScoped?: boolean;
}

export interface ActionError {
  code:
    | 'validation_error' | 'out_of_scope' | 'tenant_boundary' | 'approval_required' | 'limit_exceeded'
    | 'not_found' | 'conflict' | 'duplicate' | 'network';
  message: string;
}

export type ActionResult<T = Record<string, unknown>> =
  | { ok: true; output: T; key: string | null; action: string; seq?: number }
  | { ok: false; error: ActionError };

/** A parsed app route, the same shape the demo's parse() returns: #/page/a/b */
export interface RouteRef {
  page: string;
  a: string | null;
  b: string | null;
}
