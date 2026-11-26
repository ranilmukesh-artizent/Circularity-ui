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
  /** every problem a refused workflow.import found (P9-0.7): where in the file, and what is wrong */
  problems?: { path: string; message: string }[];
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
  t: 'trigger' | 'agent' | 'gate' | 'guard' | 'rule' | 'decision' | 'approval' | 'path' | 'execute' | 'learn' | 'step' | 'table';
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
  /** a `table` node (P9-8.16): the pack's decision table it stands for, e.g. `cover_terms` */
  table?: string;
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
  /** The what-if levers the run used (tool-fleet flows), else null. */
  params?: Record<string, number> | null;
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

/** A condition of a diversion: a case fact, an operator and a value (backend `modeler.gates.Cond`). */
export interface OverlayCond {
  fact: string;
  op: 'eq' | 'ne' | 'in' | 'gte' | 'lte' | 'exists';
  value?: unknown;
}

interface OverlayOpBase {
  /** "op-<n>", stable */
  id: string;
  by: string;
  note: string;
}

/** One change of a customer overlay (backend `modeler.overlay.OverlayOp`, I-4): never loosens a guardrail. */
export type OverlayOp =
  | (OverlayOpBase & { op: 'tighten'; target: string; field: string; value: number; seen: number })
  | (OverlayOpBase & { op: 'add_approver'; target: string; role: string })
  | (OverlayOpBase & { op: 'add_step'; stage: GuardrailStage; when: OverlayCond[]; step: string; owner_role: string })
  | (OverlayOpBase & { op: 'shortcut'; stage: GuardrailStage; when: OverlayCond[]; to: string })
  | (OverlayOpBase & { op: 'set_param'; path: string; value: number; seen: number });

/** A guardrail field a customer may tighten, with the pack's value and range. */
export interface OverlayGuardrail {
  id: string;
  text: string;
  field: string;
  value: number;
  stricter: 'lower' | 'higher';
  min: number;
  max: number;
  locked: boolean;
}

/** A pack parameter a customer may set through an overlay `set_param`, in its range; `raise_only` means never below the pack's value. */
export interface OverlayParam {
  path: string;
  value: number;
  min: number;
  max: number;
  direction: 'raise_only' | null;
  guardrail: string | null;
  owner: string | null;
}

export interface OverlayConflict {
  op_id: string;
  kind: 'target_gone' | 'changed_by_pack' | 'now_skips_compliance';
  message: string;
  mine: unknown;
  theirs: unknown;
  /** the operation as the customer made it, for "Keep mine" */
  op: OverlayOp | null;
}

export type OverlayStatus = 'none' | 'draft' | 'review' | 'pub';

/** The shown org's customer overlay of the pack (GET /api/screens/modeler, `overlay`). */
export interface OverlayScreen {
  pack_key: string;
  org_unit_id: string;
  pack_version: string;
  status: OverlayStatus;
  ver: number;
  base_version: string | null;
  draft_base_version: string | null;
  /** the pack is newer than the version the shown operations were made against: rebase */
  stale: boolean;
  maker: string | null;
  checker: string | null;
  /** the draft's operations, else the published ones */
  ops: OverlayOp[];
  published: OverlayOp[];
  conflicts: OverlayConflict[];
  notes: string[];
  guardrails: {
    id: string;
    text: string;
    locked: boolean;
    stage_label: string;
    approvers: string[];
    param: { field: string; value: number; stricter: 'lower' | 'higher'; min: number; max: number } | null;
  }[];
  /** the parameters the pack lets a customer set (`customer_layer.params`), with the pack's own value (P9-3.20) */
  params: OverlayParam[];
  stages: { key: GuardrailStage; label: string }[];
  routes: { id: string; name: string }[];
  /** the published overlay this org's cases use: its own or inherited */
  in_force: { org_unit_id: string; ver: number } | null;
  can: { edit: boolean; approve: boolean };
}

/** One stored version of a pack (plan 9, P9-1.6; the pack.* actions): `impact` is what publishing it would change. */
export interface PackVersion {
  id: number;
  key: string;
  version: string;
  org_unit_id: string | null;
  status: 'draft' | 'review' | 'pub' | 'retired';
  maker: string | null;
  checker: string | null;
  note: string | null;
  impact: { changed: number; total: number; dv: number } | null;
  parts: { ok: number; total: number };
  created_at: string;
  published_at: string | null;
}

/** The Modeler's `packs`: the versions of every pack the account may see, and the templates a case can be opened with. */
export interface PacksScreen {
  keys: { key: string; name: string; file_version: string | null; versions: PackVersion[] }[];
  templates: { key: string; name: string }[];
  can: { import: boolean; approve: boolean };
}

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
    /** the last return to the maker, pinned to a step when node_id is set (flow.reject, P9-0.12) */
    returned: { reason: string; node_id: string | null; by: string; at: string } | null;
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
  overlay: OverlayScreen;
  packs: PacksScreen;
}
