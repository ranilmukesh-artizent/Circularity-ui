import { useEffect, useState } from 'react';
import { approveFlow, discardFlow, publishFlow, rejectFlow, submitFlow } from '../../api/modeler';
import { getRollout, ROLLOUT_STEPS } from '../../api/rollout';
import type { ActionResult, ModelerScreen } from '../../api/types';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { poMoney } from './impact';
import { currentStep, showRollout } from './RolloutPanel';

export type RolloutStepId = (typeof ROLLOUT_STEPS)[number];
const STEP_LABEL: Record<RolloutStepId, string> = { replay: 'Replay', shadow: 'Shadow', canary: 'Canary', full: 'Full' };

/**
 * The rollout as a stepper on the bar (plan 10, 3.4): Replay, Shadow, Canary, Full with the current one marked. A step opens
 * the rollout form (or, for Replay, the replay) in the page's drawer through `onStep`; the stage comes from rollout.get.
 */
function RolloutStepper({ s, onStep }: { s: ModelerScreen; onStep: (k: RolloutStepId) => void }) {
  const [cur, setCur] = useState<RolloutStepId | null>(null);
  useEffect(() => {
    let live = true;
    void getRollout(s.flow.id).then((r) => live && r.ok && setCur(r.output.stage === null ? null : currentStep(r.output.stage)));
    return () => {
      live = false;
    };
  }, [s.flow.id, s.flow.status, s.flow.ver]);
  return (
    <ol className="mdl-steps" aria-label="Publish steps">
      {ROLLOUT_STEPS.map((k) => (
        <li key={k}>
          <button type="button" className={k === cur ? 'on' : undefined} aria-current={k === cur ? 'step' : undefined} onClick={() => onStep(k)}>{STEP_LABEL[k]}</button>
        </li>
      ))}
    </ol>
  );
}

export const STATUS_LABEL: Record<ModelerScreen['flow']['status'], string> = { draft: 'Draft', review: 'In review', shadow: 'Shadow', pub: 'Published' };
const MIN_REASON = 15;

/**
 * The flow's status and the lifecycle buttons the account may use (the screen's `can`): a maker submits or discards
 * a draft; a different person approves (a shadow run starts), publishes or returns it with a reason.
 */
export function LifecycleBar({ s, flush, blocking = 0, onStep, quiet = false }: { s: ModelerScreen; flush: () => Promise<void>; blocking?: number; onStep?: (k: RolloutStepId) => void; /** no primary button and no publish: the caller publishes its own way (Set up's publish step) */ quiet?: boolean }) {
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
      <span className={'pill mdl-st ' + flow.status} data-status={flow.status}>{STATUS_LABEL[flow.status]} · v{flow.dver ?? flow.ver}{blocking > 0 && ` · ${blocking} blocking`}</span>
      {onStep && showRollout(s) && <RolloutStepper s={s} onStep={onStep} />}
      {flow.status === 'shadow' && s.shadow && (
        <span className="note" data-shadow>
          Shadow: {s.shadow.n} decisions, {s.shadow.agree} agree, {s.shadow.disagree} differ · {s.shadow.dv >= 0 ? '+' : ''}{poMoney(s.shadow.dv)}
        </span>
      )}
      {can.edit && flow.status === 'draft' && <button className={'btn sm' + (quiet ? '' : ' pri')} disabled={action.pending} onClick={() => go(() => submitFlow(flow.id))}>Submit for approval</button>}
      {can.approve && flow.status === 'review' && <button className={'btn sm' + (quiet ? '' : ' pri')} disabled={action.pending} onClick={() => go(() => approveFlow(flow.id))}>Approve</button>}
      {can.approve && !quiet && flow.status === 'shadow' && <button className="btn sm pri" disabled={action.pending} onClick={() => go(() => publishFlow(flow.id))}>Publish</button>}
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
