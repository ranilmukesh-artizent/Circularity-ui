/** The rental-device panel on the case Overview (plan 9 UI audit gap 7): the checks, the service plan, the follow-through and the link to the pack's worked questions. */
import type { CaseRec } from '../../../api/case';
import { Panel } from '../../../components/kit/Panel';
import { QUESTIONS_HREF, medicalView } from './medView';
import { CertificationWindow, Decontamination, FollowThrough, RepairApproval, TurnaroundService } from './MedicalSections';

export function MedicalPanel({ c }: { c: CaseRec }) {
  const v = medicalView(c);
  if (!v) return null;
  return (
    <Panel title="Rental device" sub={[v.tag, v.cls].filter(Boolean).join(' · ') || undefined}>
      <Decontamination c={c} />
      <h4 className="stpad" style={{ margin: '8px 0 0' }}>Certification against the rental</h4>
      <CertificationWindow c={c} />
      <h4 className="stpad" style={{ margin: '8px 0 0' }}>Turnaround and service</h4>
      <TurnaroundService c={c} />
      <RepairApproval c={c} />
      <h4 className="stpad" style={{ margin: '8px 0 0' }}>Follow-through</h4>
      <FollowThrough c={c} />
      <p className="stpad" style={{ margin: '8px 0 0' }}><a className="lnk" href={QUESTIONS_HREF}>Worked questions for rental devices</a></p>
    </Panel>
  );
}
