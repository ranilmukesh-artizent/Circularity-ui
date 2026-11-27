/**
 * "Waiting for you (n)" at the top of the assistant (plan 10, section 2.6): the writes agents prepared that hold for
 * this person, the same list as Home's "Proposals for you" (`GET /api/screens/home/proposals`), those for the case or
 * flow in context first. Not drawn when nothing is held. Accept and Reject are the person's own actions (ProposalRow); nothing
 * here runs by itself.
 */
import { Suspense } from 'react';
import { proposals } from '../../api/home';
import { ErrorBoundary } from '../../components/Boundary';
import { Icon } from '../../components/Icon';
import { orderProposals, ProposalItems, type ProposalContext } from '../../components/ProposalRow';
import { heldForFlow } from '../../pages/modeler/flowBrief';

function Strip({ ctx, skipFlow }: { ctx: ProposalContext; skipFlow?: number }) {
  const all = proposals();
  // the Modeler's column lists this flow's held proposals under Proposals: they are not repeated here
  const skip = skipFlow == null ? [] : heldForFlow(all, skipFlow);
  const list = orderProposals(all.filter((p) => !skip.includes(p)), ctx);
  // nothing held: no strip at all (2.6, "collapsed if 0"); an empty heading on every view is noise
  if (!list.length) return null;
  return (
    <details className="as-waiting" data-waiting={list.length} open={list.length <= 3}>
      <summary>
        <Icon name="clock" />
        <span>Waiting for you ({list.length})</span>
        <Icon name="chevD" className="as-chev" />
      </summary>
      <ProposalItems list={list} idPrefix="asp-" label="Waiting for you" />
    </details>
  );
}

/** `skipFlow`: a flow whose held proposals the host already shows (the Modeler column's Proposals section). */
export function WaitingStrip({ caseId, flow, skipFlow }: ProposalContext & { skipFlow?: number }) {
  return (
    <ErrorBoundary>
      {/* nothing while it loads: the strip is collapsed when empty, so a loading line would only jump */}
      <Suspense fallback={null}>
        <Strip ctx={{ caseId, flow }} skipFlow={skipFlow} />
      </Suspense>
    </ErrorBoundary>
  );
}
