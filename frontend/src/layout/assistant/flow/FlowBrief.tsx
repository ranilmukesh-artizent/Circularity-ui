import type { ModelerScreen } from '../../../api/types';
import { flowBrief, type BriefLink } from '../../../pages/modeler/flowBrief';
import { flowSurface } from './changeStore';
import { Row, Sec } from './Sec';

/** Follow a brief sentence's link: a node is selected on the canvas (and the Inspector opens), a check opens Checks. */
export function follow(link: BriefLink): void {
  const sf = flowSurface();
  if (!sf || !link) return;
  if (link.kind === 'node') sf.select(link.id, 'inspector');
  // the contract's tab union has no 'checks' yet; the Modeler's select ignores a tab it does not know and clears the selection
  else (sf.select as (id: string | null, tab?: string) => void)(null, 'checks');
}

/** A node's name for a link's label: its rule id, else its label. */
const nodeName = (s: ModelerScreen, id: string): string => {
  const n = s.flow.graph.nodes.find((x) => x.id === id);
  return n?.rid || n?.label || id;
};

/** "What I see" (plan 10, 3.3): the flow in 3 to 5 computed sentences, each linking to its node or tab. No model writes them. */
export function FlowBrief({ s }: { s: ModelerScreen }) {
  return (
    <Sec icon="book" title="What I see" tag="Rules">
      {flowBrief(s, s.checks).map((l) => (
        <Row key={l.id} icon={l.icon} go={l.link ? (l.link.kind === 'node' ? 'Select' : 'Open checks') : undefined}
             goLabel={l.link?.kind === 'node' ? `Select ${nodeName(s, l.link.id)} on the canvas` : undefined} onGo={() => follow(l.link)}>{l.text}</Row>
      ))}
    </Sec>
  );
}
