import { toolFleetView } from '../../../api/toolFleet';
import { Panel } from '../../../components/kit/Panel';
import { can } from '../../../api/session';
import { ApprovalSection } from './ApprovalSection';
import { GatesSection } from './GatesSection';
import { GradeSection } from './GradeSection';
import { LifeSection } from './LifeSection';
import { PathsSection } from './PathsSection';
import { PlanSection } from './PlanSection';
import { QuarantineCard } from './QuarantineCard';

/** The tool fleet case panel inside the case Overview (plan 9, P9-3.5): the grade, the gates (P9-3.6) and the recall quarantine (P9-3.7); life and paths follow. */
export function ToolFleetPanel({ caseId }: { caseId: string }) {
  const v = toolFleetView(caseId);
  return (
    <Panel title="Tool fleet" sub={`${v.flow} · pack v${v.pack_version}`}>
      <GradeSection grade={v.grade} />
      <LifeSection life={v.life ?? null} disagreement={v.disagreement ?? null} />
      <PathsSection paths={v.paths} best={v.best} second={v.second} standard={v.standard} uplift={v.uplift} />
      <PlanSection plan={v.plan} />
      <GatesSection gates={v.gates} />
      <ApprovalSection approval={v.approval ?? null} />
      <QuarantineCard caseId={caseId} q={v.quarantine ?? null} mayRelease={can('releaseQuarantine')} />
    </Panel>
  );
}