/**
 * The tool fleet case panel (plan 9, P9-3.5, story TF-03; backend/di/services/screens/toolfleet.py): what the Overview shows
 * for a case of the tool fleet template. `grade` is the grade the case is valued on and where it came from: the repair
 * log's graded record with its test result ("workbench"), else the valuer's own estimate ("estimate"). The other
 * fields are empty until the tasks that fill them. A read only; writes go through the action pipeline.
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

export interface ToolFleetView {
  case_id: string;
  pack_version: string;
  flow: string;
  grade: GradeView;
  gates: unknown[];
  life: unknown | null;
  paths: unknown[];
  plan: unknown | null;
  approval: unknown | null;
  followThrough: unknown | null;
}

/** The panel's read for a tool fleet case (GET /api/screens/toolfleet/{id}). */
export const toolFleetView = (caseId: string): ToolFleetView => cached<ToolFleetView>('/api/screens/toolfleet/' + encodeURIComponent(caseId));