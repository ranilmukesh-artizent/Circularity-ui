/** The regulatory assessment of a medical capital case (plan 9, P9-12.9, NS-MED-01): what a person recorded (outcome, who, when)
 *  and, for a role that may, the button that opens the form. A person's record: an agent never records it. */
import type { CaseRec } from '../../api/case';
import { recordedAssessment, recordedLine } from './assessment';

export function AssessmentBar({ c, canRecord, onRecord }: { c: CaseRec; canRecord: boolean; onRecord: () => void }) {
  const a = recordedAssessment(c);
  if (!a && !canRecord) return null;
  return (
    <section className="asmbar" aria-label="Regulatory assessment" data-testid="assessment-bar">
      <div className="asmtxt">
        <b>Regulatory assessment</b>
        {a ? (
          <>
            <span data-testid="assessment-recorded">{recordedLine(a)}</span>
            <span className="muted">{a.plannedWork}{a.plannedWork && a.reason ? ' · ' : ''}{a.reason}</span>
          </>
        ) : (
          <span className="muted">Not recorded. Refurbish and resale stays stopped until a person records whether the planned work is servicing.</span>
        )}
      </div>
      {canRecord && <button className="btn pri" onClick={onRecord}>Record assessment</button>}
    </section>
  );
}
