import { Suspense, useEffect, type ReactNode } from 'react';
import { proposals, type HomeProposal } from '../../../api/home';
import { useModeler } from '../../../api/modeler';
import type { ModelerScreen } from '../../../api/types';
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

/** The column's own read of the screen (same cache as the page, keyed by template and org). */
function Read({ sf }: { sf: FlowSurface }) {
  return <Sections s={useModeler(sf.template, sf.org)} />;
}

function Sections({ s }: { s: ModelerScreen }) {
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
export function FlowSections({ screen }: { screen?: ModelerScreen }) {
  const sf = useSurface();
  if (!sf || sf.kind !== 'flow') return null;
  // the Modeler passes the screen it shows: a second read under another cache key (the page asks for the default
  // template as '', the surface names it) left the column on "Reading the flow…" for seconds (T8)
  const mine = screen && screen.flow.id === sf.flowId ? screen : null;
  return (
    <ErrorBoundary resetKey={String(sf.flowId)}>
      <Suspense fallback={<Loading label="Reading the flow…" />}>
        {mine ? <Sections s={mine} /> : <Read sf={sf} />}
      </Suspense>
    </ErrorBoundary>
  );
}
