import { useState } from 'react';
import { approveFlow, discardFlow, publishFlow, rejectFlow, submitFlow } from '../../api/modeler';
import type { ActionResult, ModelerScreen } from '../../api/types';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { poMoney } from './impact';

export const STATUS_LABEL: Record<ModelerScreen['flow']['status'], string> = { draft: 'Draft', review: 'In review', shadow: 'Shadow', pub: 'Published' };
const MIN_REASON = 15;

/**
 * The flow's status and the lifecycle buttons the account may use (the screen's `can`): a maker submits or discards
 * a draft; a different person approves (a shadow run starts), publishes or returns it with a reason.
 */
export function LifecycleBar({ s, flush }: { s: ModelerScreen; flush: () => Promise<void> }) {
  const action = useAction();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const [step, setStep] = useState('');
  const { flow, can } = s;
  const go = async (call: () => Promise<ActionResult<{ log?: string }>>) => {
    await flush();
    const r = await action.run(call, 4200);
    if (r.ok && r.output.log) toast(r.output.log + '.');
    return r.ok;
  };
  const reject = async () => {
    if (await go(() => rejectFlow(flow.id, reason.trim(), step || undefined))) {
      setRejecting(false);
      setReason('');
      setStep('');
    }
  };
  const waiting = flow.status === 'review' || flow.status === 'shadow';
  return (
    <div className="mdl-life">
      <span className={'pill mdl-st ' + flow.status} data-status={flow.status}>{STATUS_LABEL[flow.status]} · v{flow.dver ?? flow.ver}</span>
      {flow.status === 'shadow' && s.shadow && (
        <span className="note" data-shadow>
          Shadow: {s.shadow.n} decisions, {s.shadow.agree} agree, {s.shadow.disagree} differ · {s.shadow.dv >= 0 ? '+' : ''}{poMoney(s.shadow.dv)}
        </span>
      )}
      {can.edit && flow.status === 'draft' && <button className="btn sm pri" disabled={action.pending} onClick={() => go(() => submitFlow(flow.id))}>Submit for approval</button>}
      {can.approve && flow.status === 'review' && <button className="btn sm pri" disabled={action.pending} onClick={() => go(() => approveFlow(flow.id))}>Approve</button>}
      {can.approve && flow.status === 'shadow' && <button className="btn sm pri" disabled={action.pending} onClick={() => go(() => publishFlow(flow.id))}>Publish</button>}
      {can.approve && waiting && !rejecting && <button className="btn sm" onClick={() => setRejecting(true)}>Return to draft</button>}
      {can.edit && flow.status !== 'pub' && <button className="btn sm ghost" disabled={action.pending} onClick={() => go(() => discardFlow(flow.id))}>Discard draft</button>}
      {flow.returned && flow.status === 'draft' && (
        <span className="note" data-returned-note>
          Returned: {flow.returned.reason}
          {flow.returned.node_id && ` (step: ${flow.graph.nodes.find((n) => n.id === flow.returned?.node_id)?.label ?? flow.returned.node_id})`}
        </span>
      )}
      {rejecting && (
        <span className="mdl-row">
          <label className="sr" htmlFor="mdl-reason">Reason</label>
          <input id="mdl-reason" value={reason} placeholder="Why it goes back (15 characters or more)" style={{ width: 280 }} onChange={(e) => setReason(e.target.value)} />
          <label className="sr" htmlFor="mdl-step">Step</label>
          <select id="mdl-step" value={step} onChange={(e) => setStep(e.target.value)}>
            <option value="">Whole flow</option>
            {flow.graph.nodes.map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
          </select>
          <button className="btn sm" disabled={action.pending || reason.trim().length < MIN_REASON} onClick={reject}>Return</button>
          <button className="btn sm ghost" onClick={() => setRejecting(false)}>Cancel</button>
        </span>
      )}
    </div>
  );
}
