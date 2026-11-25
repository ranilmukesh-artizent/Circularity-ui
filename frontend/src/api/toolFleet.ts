/**
 * The tool fleet case panel (plan 9, P9-3.5, story TF-03; backend/di/services/screens/toolfleet.py): what the Overview shows
 * for a case of the tool fleet template. `grade` is the grade the case is valued on and where it came from: the repair
 * log's graded record with its test result ("workbench"), else the valuer's own estimate ("estimate"). `gates` (P9-3.6) are the gates that apply
 * to the case with the term a failed one names. The other fields are empty until the tasks that fill them. A read only; writes go through the action pipeline.
 */
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
}

export interface ToolFleetView {
  case_id: string;
  pack_version: string;
  flow: string;
  grade: GradeView;
  gates: GateView[];
  life: unknown | null;
  paths: unknown[];
  plan: unknown | null;
  approval: unknown | null;
  followThrough: unknown | null;
}

/** The panel's read for a tool fleet case (GET /api/screens/toolfleet/{id}). */
export const toolFleetView = (caseId: string): ToolFleetView => cached<ToolFleetView>('/api/screens/toolfleet/' + encodeURIComponent(caseId));