/** The medical-rental stage tabs (plan 9 UI audit gap 7): "Rental checks" at the condition stage, "Follow-through" at the decision stage. */
import { QUESTIONS_HREF } from './medView';
import { CertificationWindow, Decontamination, FollowThrough, RepairApproval, TurnaroundService } from './MedicalSections';
import type { TabProps } from '../tabs';

export const RentalChecksTab = ({ c }: TabProps) => (
  <>
    <Decontamination c={c} />
    <CertificationWindow c={c} />
  </>
);

export const RentalFollowTab = ({ c }: TabProps) => (
  <>
    <RepairApproval c={c} />
    <TurnaroundService c={c} />
    <FollowThrough c={c} />
    <p className="stpad"><a className="lnk" href={QUESTIONS_HREF}>Worked questions for rental devices</a></p>
  </>
);
