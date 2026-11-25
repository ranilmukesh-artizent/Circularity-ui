import { toolFleetView } from '../../../api/toolFleet';
import { Panel } from '../../../components/kit/Panel';
import { GatesSection } from './GatesSection';
import { GradeSection } from './GradeSection';

/** The tool fleet case panel inside the case Overview (plan 9, P9-3.5): the grade and the gates (P9-3.6); life and paths follow. */
export function ToolFleetPanel({ caseId }: { caseId: string }) {
  const v = toolFleetView(caseId);
  return (
    <Panel title="Tool fleet" sub={`${v.flow} · pack v${v.pack_version}`}>
      <GradeSection grade={v.grade} />
      <GatesSection gates={v.gates} />
    </Panel>
  );
}