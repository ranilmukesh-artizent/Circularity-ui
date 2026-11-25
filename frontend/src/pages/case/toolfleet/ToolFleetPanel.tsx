import { toolFleetView } from '../../../api/toolFleet';
import { Panel } from '../../../components/kit/Panel';
import { GradeSection } from './GradeSection';

/** The tool fleet case panel inside the case Overview (plan 9, P9-3.5): the grade now; gates, life and paths follow. */
export function ToolFleetPanel({ caseId }: { caseId: string }) {
  const v = toolFleetView(caseId);
  return (
    <Panel title="Tool fleet" sub={`${v.flow} · pack v${v.pack_version}`}>
      <GradeSection grade={v.grade} />
    </Panel>
  );
}