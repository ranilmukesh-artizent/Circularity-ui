/**
 * Home's "Proposals for you" (Gaps-B): writes an agent prepared that hold for a person, listed for every account that
 * may act on one (the server lists only those: the held action's permission, the case in the person's tenants).
 * Plan 10: each is the shared `ProposalRow` (the same card as the assistant's "Waiting for you"): Accept runs the
 * action as the signed-in person after a confirming step, Reject asks for a reason. With nothing pending the card is
 * not drawn, so Home looks as before.
 */
import { proposals } from '../../api/home';
import { Panel } from '../../components/kit/Panel';
import { ProposalRow } from '../../components/ProposalRow';

export function ProposalsCard() {
  const list = proposals();
  if (!list.length) return null;
  return (
    <Panel title="Proposals for you" id="frProps" sub="An agent prepared these. Nothing runs until you accept.">
      <ul className="frbl" aria-label="Proposals for you">
        {list.map((p) => <ProposalRow key={p.id} p={p} id={'frp-' + p.id} />)}
      </ul>
    </Panel>
  );
}
