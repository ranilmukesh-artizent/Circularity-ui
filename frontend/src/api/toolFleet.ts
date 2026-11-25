/**
 * The tool fleet case panel (plan 9, P9-3.5, story TF-03; backend/di/services/screens/toolfleet.py): what the Overview shows
 * for a case of the tool fleet template. `grade` is the grade the case is valued on and where it came from: the repair
 * log's graded record with its test result ("workbench"), else the valuer's own estimate ("estimate"). `gates` (P9-3.6) are the gates that apply
 * to the case with the term a failed one names. The other fields are empty until the tasks that fill them. A read only; writes go through the action pipeline.
 */
import { invoke } from './actions';
import type { ActionResult } from './types';
import { cached } from './client';

export interface GradeView {
  grade: string;
  source: 'workbench' | 'estimate';
  /** the workbench inspection reference (DR-50412), null for an estimate */
  ref: string | null;
  /** when it was graded (ISO), null for an estimate */
  at: string | null;
  age_hours: number | null;
}

/** One gate of the case as its gate step left it (P9-3.6): GR-07 is the contract right ("G-CON-2"). */
export interface GateView {
  id: string;
  name: string;
  passed: boolean;
  /** what the gate says: why it passed, or the term it failed on ("Theft recovered: claim CLM-7781 is open") */
  reason: string;
  /** the pack guardrail the gate enforces (GR-07), when it has one */
  guardrail: string | null;
  owner: string;
  kind: string;
  stage: string;
  stageLabel: string;
  hold: boolean;
  locked: boolean;
  /** GR-13 (G-TOOL-TEL) only: whole days since the telematics were last seen (null: none) and the limit (P9-3.8) */
  age_days?: number | null;
  max_age_days?: number;
}

/** The quarantine of a recalled tool (P9-3.7, GR-12): the recall, the paths and parts it blocks, and who released it after the fix. */
export interface QuarantineView {
  recall_id: string;
  /** repair (released after the fix), replace or refund (never released) */
  remedy: string;
  /** the route ids the recall blocks now; empty once released */
  blocked: string[];
  affected_parts: string[];
  released: { by: string; at: string; note: string } | null;
}

/** The computed wear and remaining life of a tool (P9-3.9, TF-06): WTI 0 to 100, the weakest critical component's remaining life, a row per component. */
export interface LifeView {
  wti: number;
  rul_tool: number;
  rul_tool_hours: number;
  weakest: string;
  per_component: { name: string; used_hours: number; consumed_pct: number; rul_pct: number; source: 'plm' | 'pack' | string }[];
  confidence: 'High' | 'Medium' | 'Low';
  /** RUL_tool at the high and low duty, only without telematics */
  range: [number, number] | null;
  inputs: Record<string, unknown>;
  table_version: string;
  rule_version: string;
}

/** One value line of a path (type v value, c cost, h holding), as the valuer states it (P9-3.12). */
export interface PathLine {
  type: 'v' | 'c' | 'h';
  label: string;
  basis: string;
  amt: number;
}

/** One of the six paths valued against the live named demand (P9-3.12, TF-07); `dest` is the named order it fills. */
export interface PathView {
  k: string;
  name: string;
  ok: boolean;
  net: number;
  gross: number;
  cost: number;
  hold: number;
  /** why the path was chosen, or why it is blocked */
  why: string;
  lines: PathLine[];
  dest: { id: string; who: string; kind?: string } | null;
}

export interface ToolFleetView {
  case_id: string;
  pack_version: string;
  flow: string;
  grade: GradeView;
  gates: GateView[];
  /** the recall quarantine, null for a tool no active recall names */
  quarantine: QuarantineView | null;
  /** null for a case with neither telematics hours nor months on contract */
  life: LifeView | null;
  /** the six paths in the pack's order (P9-3.12) */
  paths: PathView[];
  /** the recommended path, the next eligible one, the standard route (the function's default) and best net minus standard net; null with no recommendation */
  best?: string | null;
  second?: string | null;
  standard?: string;
  uplift?: number | null;
  plan: unknown | null;
  approval: unknown | null;
  followThrough: unknown | null;
}

/** The panel's read for a tool fleet case (GET /api/screens/toolfleet/{id}). */
export const toolFleetView = (caseId: string): ToolFleetView => cached<ToolFleetView>('/api/screens/toolfleet/' + encodeURIComponent(caseId));

/** Release a recalled tool from quarantine after the fix (recall.release, Approver or Admin; a replace or refund recall is never released). */
export const releaseQuarantine = (caseId: string, note: string): Promise<ActionResult<{ released: boolean }>> =>
  invoke<{ released: boolean }>('recall.release', { case_id: caseId, note });
