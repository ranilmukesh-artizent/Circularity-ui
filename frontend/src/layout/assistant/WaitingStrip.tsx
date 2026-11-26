/**
 * "Waiting for you (n)" at the top of the assistant (plan 10, section 2.6): the writes agents prepared that hold for
 * this person, the same list as Home's "Proposals for you" (`GET /api/screens/home/proposals`), those for the case or
 * flow in context first. Collapsed when empty. Accept and Reject are the person's own actions (ProposalRow); nothing
 * here runs by itself.
 */
import { proposals } from '../../api/home';
import { Boundary } from '../../components/Boundary';
import { orderProposals, ProposalRow, type ProposalContext } from '../../components/ProposalRow';

function Strip({ ctx }: { ctx: ProposalContext }) {
  const list = orderProposals(proposals(), ctx);
  return (
    <details className="as-sec as-waiting" data-waiting={list.length} open={list.length > 0}>
      <summary className="as-sec-t">Waiting for you ({list.length})</summary>
      {list.length ? (
        <ul className="as-list frbl" aria-label="Waiting for you">
          {list.map((p) => <ProposalRow key={p.id} p={p} id={'asp-' + p.id} />)}
        </ul>
      ) : (
        <p className="note">Nothing is held for you. Proposals an agent prepares show here and run only when you accept.</p>
      )}
    </details>
  );
}

export function WaitingStrip({ caseId, flow }: ProposalContext) {
  return (
    <Boundary>
      <Strip ctx={{ caseId, flow }} />
    </Boundary>
  );
}
