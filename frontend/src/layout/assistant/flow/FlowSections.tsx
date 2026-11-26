import { Suspense, useEffect, type ReactNode } from 'react';
import { proposals, type HomeProposal } from '../../../api/home';
import { useModeler } from '../../../api/modeler';
import { ErrorBoundary, Loading } from '../../../components/Boundary';
import { heldForFlow } from '../../../pages/modeler/flowBrief';
import { useSurface, type FlowSurface } from '../../../utils/workSurface';
import { loadSuggestions, mountSections, useChange } from './changeStore';
import { FlowBrief } from './FlowBrief';
import { LastSim } from './LastSim';
import { Proposals } from './Proposals';
import { Watching } from './Watching';

/** The held proposals of this flow, read where Home reads them (suspends; the fallback shows the sections without them). */
function WithHeld({ flowId, children }: { flowId: number; children: (held: HomeProposal[]) => ReactNode }) {
  return <>{children(heldForFlow(proposals(), flowId))}</>;
}

function Sections({ sf }: { sf: FlowSurface }) {
  // the column reads the screen itself, from the same cache the Modeler page uses, so it needs nothing but the surface
  const s = useModeler(sf.template, sf.org);
  const st = useChange();
  const id = s.flow.id;
  const may = s.can.edit || s.can.approve;
  const loaded = st.suggestions?.flowId === id;
  useEffect(() => mountSections(), []);
  useEffect(() => {
    if (may && !loaded) void loadSuggestions(id);
  }, [may, loaded, id]);
  const body = (held: HomeProposal[]) => (
    <>
      <FlowBrief s={s} />
      <Watching s={s} held={held} />
      <Proposals s={s} held={held} />
      <LastSim s={s} />
    </>
  );
  return (
    <Suspense fallback={body([])}>
      <WithHeld flowId={id}>{body}</WithHeld>
    </Suspense>
  );
}

/**
 * The four agent-first sections of the pinned column (plan 10, 3.3): What I see, Watching, Proposals, Last simulation.
 * T1's pinned `AssistantPanel` renders this above the transcript on the Modeler's Flow tab; it renders nothing when the
 * page has not registered a flow surface.
 */
export function FlowSections() {
  const sf = useSurface();
  if (!sf || sf.kind !== 'flow') return null;
  return (
    <ErrorBoundary resetKey={String(sf.flowId)}>
      <Suspense fallback={<Loading label="Reading the flow…" />}>
        <Sections sf={sf} />
      </Suspense>
    </ErrorBoundary>
  );
}
