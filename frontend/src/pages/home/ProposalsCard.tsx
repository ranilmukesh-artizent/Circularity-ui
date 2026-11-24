/**
 * Home's "Proposals for you" (Gaps-B): writes an agent prepared that hold for a person, listed for every account that
 * may act on one (the server lists only those: the held action's permission, the case in the person's tenants).
 * Accept runs the action as the signed-in person; Reject asks for a reason. With nothing pending the card is not
 * drawn, so Home looks as before.
 */
import { useState } from 'react';
import { acceptProposal, proposals, rgTime, rejectProposal, type HomeProposal } from '../../api/home';
import { Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { Panel } from '../../components/kit/Panel';
import { IconTile } from '../../components/kit/IconTile';
import { useAction } from '../../hooks/useAction';

export function ProposalsCard() {
  const list = proposals();
  const action = useAction();
  const [rejecting, setRejecting] = useState<HomeProposal | null>(null);
  const [reason, setReason] = useState('');
  const [err, setErr] = useState('');
  if (!list.length) return null;
  const accept = async (p: HomeProposal) => {
    const r = await action.run(() => acceptProposal(p.id));
    if (r.ok) toast(`${p.title} ran as you.`);
  };
  const close = () => {
    setRejecting(null);
    setReason('');
    setErr('');
  };
  const reject = async () => {
    if (!rejecting) return;
    const r = await action.run(() => rejectProposal(rejecting.id, reason.trim()), { inline: setErr });
    if (!r.ok) return;
    toast('Proposal rejected.');
    close();
  };
  return (
    <Panel title="Proposals for you" id="frProps" sub="An agent prepared these. Nothing runs until you accept.">
      <ul className="frbl" aria-label="Proposals for you">
        {list.map((p) => (
          <li key={p.id} id={'frp-' + p.id}>
            <IconTile ic="bot" h="agent" cls="sm" />
            <span>
              <b>{p.title}</b>
              {p.case_id && <> · <a href={'#/product/' + p.case_id}>{p.case_id}</a></>}
              <span className="note">{p.why}</span>
              <span className="note">{p.agentName} · {rgTime(p.at)}</span>
              <span className="row">
                <button className="btn sm pri" disabled={action.pending} onClick={() => accept(p)}>Accept</button>
                <button className="btn sm" disabled={action.pending} onClick={() => setRejecting(p)}>Reject</button>
              </span>
            </span>
          </li>
        ))}
      </ul>
      {rejecting && (
        <Modal
          title={'Reject: ' + rejecting.title}
          onClose={close}
          foot={
            <>
              <button className="btn" onClick={close}>Cancel</button>
              <button className="btn pri" disabled={action.pending || !reason.trim()} onClick={reject}>Reject</button>
            </>
          }
        >
          <div className="fld">
            <label htmlFor="frp-reason">Why not? The agent's owner sees this.</label>
            <textarea id="frp-reason" maxLength={300} value={reason} onChange={(e) => { setReason(e.target.value); setErr(''); }} />
            <div className="err" role="alert" hidden={!err}>{err}</div>
          </div>
        </Modal>
      )}
    </Panel>
  );
}
