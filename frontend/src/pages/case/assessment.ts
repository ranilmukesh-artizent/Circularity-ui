/** View logic of the regulatory assessment of a medical capital device (plan 9, P9-12.9, NS-MED-01). */
import { when, type AssessmentResult, type CaseRec } from '../../api/case';

/** The outcomes `assessment.record` accepts, in plain words (the value is what the action expects). */
export const OUTCOMES: { value: AssessmentResult; label: string; hint: string }[] = [
  { value: 'servicing', label: 'Servicing', hint: 'Restores the device to its original specification, with no change to performance or intended use.' },
  { value: 'remanufacturing', label: 'Remanufacturing', hint: 'Significantly changes the device. Resale after refurbishment needs the manufacturer status of the market.' },
  { value: 'full_refurbishment', label: 'Full refurbishment', hint: 'Rebuilds the device. Resale after refurbishment needs the manufacturer status of the market.' },
];

export const outcomeLabel = (v: string): string => OUTCOMES.find((o) => o.value === v)?.label ?? v;

/** The template of the cases the action applies to. */
export const ASSESSMENT_TEMPLATE = 'medical_capital';
export const assessable = (c: Pick<CaseRec, 'template'>): boolean => c.template === ASSESSMENT_TEMPLATE;

/** Why the form cannot be saved yet, null when it can. */
export function saveBlock(plannedWork: string, reason: string): string | null {
  if (!plannedWork.trim() && !reason.trim()) return 'Describe the planned work and give the reason to save.';
  if (!plannedWork.trim()) return 'Describe the planned work to save.';
  if (!reason.trim()) return 'Give the reason to save.';
  return null;
}

export interface RecordedAssessment { outcome: string; label: string; plannedWork: string; reason: string; by: string; at: string }

/** The assessment a person recorded on the case (the evidence `servicing_assessment`), null when none. */
export function recordedAssessment(c: CaseRec): RecordedAssessment | null {
  const r = c.evidenceRecords?.find((e) => e.type === 'servicing_assessment');
  const v = r?.value;
  if (!r || !v?.assessment) return null;
  return {
    outcome: v.assessment, label: outcomeLabel(v.assessment), plannedWork: v.planned_work ?? '', reason: v.rationale ?? '',
    by: v.by ?? r.operator ?? '', at: r.at ?? '',
  };
}

/** "Servicing, recorded by engineer on 26 Nov 14:20". */
export const recordedLine = (a: RecordedAssessment): string =>
  `${a.label}, recorded${a.by ? ' by ' + a.by : ''}${a.at ? ' on ' + when(a.at) : ''}`;
