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

// ---------------------------------------------------------------- the Modeler (plan 8, MVP-4.3; GET /api/screens/modeler)
/** A node of a decision flow (Domain spec D1). Rule nodes carry rid, action, path, scope and owner. */
export interface FlowNode {
  id: string;
  t: 'trigger' | 'agent' | 'gate' | 'guard' | 'rule' | 'decision' | 'approval' | 'path' | 'execute' | 'learn' | 'step';
  x: number;
  y: number;
  label: string;
  sub: string;
  h: number;
  lock: boolean;
  rid?: string;
  action?: 'exclude' | 'require' | 'prefer';
  path?: string | null;
  scope?: Record<string, string[] | number | string | null>;
  owner?: string;
  ai?: boolean;
  src?: string;
}

/** An edge `a > b` with its label. */
export interface FlowEdge {
  id: string;
  a: string;
  b: string;
  l: string;
}

export interface FlowGraph {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

/** A validation check: fail blocks a submit. */
export interface Check {
  level: 'ok' | 'warn' | 'fail';
  msg: string;
  node_id: string | null;
}

/** A simulation over the open queue (flow.simulate): n decisions, the ones that change (flips) and the value change. */
export interface SimResult {
  kind: 'equip' | 'device';
  n: number;
  flips: { case_id: string; from: string | null; to: string | null; dv: number }[];
  dv: number;
  extra: Record<string, number>;
}

export interface FlowPathDef {
  id: string;
  name: string;
  app: string;
  owner: string;
  lead_days: number | null;
}

export type GuardrailStage = 'receive' | 'match' | 'condition' | 'value' | 'decide' | 'execute' | 'close';
export type GuardrailType = 'Compliance' | 'Data quality' | 'Threshold' | 'Approval';

export interface FlowGuardrail {
  id: string;
  text: string;
  owner: string;
  type: GuardrailType;
  stage: GuardrailStage;
  stage_label: string;
  locked: boolean;
}

export interface ScopeDim {
  key: string;
  label: string;
  kind: 'set' | 'min' | 'max';
  values: string[];
}

export interface CompiledRule {
  id: string;
  scope: Record<string, unknown>;
  action: string;
  path: string;
  text: string;
}

export type FlowStatus = 'draft' | 'review' | 'shadow' | 'pub';

export interface ModelerScreen {
  templates: { key: string; name: string }[];
  org: string;
  orgs: string[];
  flow: {
    id: number;
    name: string;
    org_unit_id: string;
    status: FlowStatus;
    ver: number;
    dver: number | null;
    maker: string | null;
    checker: string | null;
    graph: FlowGraph;
    published: FlowGraph;
  };
  template: {
    key: string;
    name: string;
    pre: string;
    paths: FlowPathDef[];
    guardrails: FlowGuardrail[];
    dims: ScopeDim[];
    actors: [string, string, string][];
  };
  /** [x, y, w, h, label]: the fixed band behind the core prediction and agents (tool_fleet, device), else null */
  band: [number, number, number, number, string] | null;
  checks: Check[];
  compiled: CompiledRule[];
  versions: { ver: number; published_by: string | null; published_at: string | null; note: string | null; graph: FlowGraph }[];
  shadow: { n: number; agree: number; disagree: number; dv: number } | null;
  log: { at: string; actor: string; role: string; action: string; note: string | null }[];
  can: { edit: boolean; approve: boolean; fork: boolean };
}
