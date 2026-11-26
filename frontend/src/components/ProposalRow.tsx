/**
 * One proposal held for a person (plan 10, section 2.6): used by the assistant dock's "Waiting for you" strip and by
 * Home's "Proposals for you" card. An agent prepared it and nothing runs until the signed-in person decides:
 * Accept runs the held action as that person (`proposal.accept`, through the same pipeline and approvals, after one
 * confirming step that names it), Reject asks for a reason (`proposal.reject`). When the agent acted for the
 * signed-in person (`own`) Accept is replaced by a note: another person accepts it (maker-checker, AGENTS.md rule 10).
 */
import { useId, useState } from 'react';
import { OWN_PROPOSAL_NOTE, reasonText, type HoldReason } from '../api/agents';
import { acceptProposal, rejectProposal, rgTime, type HomeProposal } from '../api/home';
import { useAction } from '../hooks/useAction';
import { toast } from './toast';
import { IconTile } from './kit/IconTile';

/** What the person is looking at: a case, or a flow (its proposals are the `flow.`, `overlay.` and `compose.` actions). */
export interface ProposalContext { caseId?: string; flow?: boolean }

/** The confirming line: undo is not promised, the action decides. */
export const ACCEPT_LIMIT = 'Runs as you. Undo it from the case if the action allows.';

/** Does a held proposal belong to what the person is looking at? */
export function inContext(p: Pick<HomeProposal, 'case_id' | 'action'>, ctx: ProposalContext): boolean {
  if (ctx.caseId && p.case_id === ctx.caseId) return true;
  return !!ctx.flow && /^(flow|overlay|compose)\./.test(p.action);
}

/** The proposals for the case or flow in context first, then the rest; each group keeps the server's order. */
export function orderProposals<T extends Pick<HomeProposal, 'case_id' | 'action'>>(list: readonly T[], ctx: ProposalContext): T[] {
  const mine = list.filter((p) => inContext(p, ctx));
  return [...mine, ...list.filter((p) => !mine.includes(p))];
}

/** A person's own agent's proposal cannot be accepted by them. */
export const canAccept = (p: Pick<HomeProposal, 'own'>): boolean => !p.own;

/** Where "View the run" goes: the Agents page opens the run's drawer from `?run=`. */
export const runHref = (runId: string): string => '#/agents?run=' + encodeURIComponent(runId);

export function ProposalRow({ p, id }: { p: HomeProposal; id?: string }) {
  const action = useAction();
  const uid = useId();
  const [step, setStep] = useState<'idle' | 'accept' | 'reject'>('idle');
  const [reason, setReason] = useState('');
  const [err, setErr] = useState('');
  const accept = async () => {
    const r = await action.run(() => acceptProposal(p.id));
    if (r.ok) toast(`${p.title} ran as you.`);
  };
  const reject = async () => {
    const r = await action.run(() => rejectProposal(p.id, reason.trim()), { inline: setErr });
    if (!r.ok) return;
    toast('Proposal rejected.');
    setStep('idle');
  };
  const cancel = () => {
    setStep('idle');
    setReason('');
    setErr('');
  };
  const reasons = reasonText(p.reasons as HoldReason[] | undefined);
  return (
    <li className="as-card held" id={id} aria-label={`${p.agentName}: ${p.title}`}>
      <IconTile ic="bot" h="agent" cls="sm" />
      <span className="as-card-b">
        <span className="as-prov">
          {p.agentName} · held {rgTime(p.at)}
          {p.case_id && <> · <a href={'#/product/' + p.case_id}>{p.case_id}</a></>}
        </span>
        <b className="as-card-t">{p.title}</b>
        {p.why && <span className="note">Why: {p.why}</span>}
        {reasons && <span className="note" data-reasons>Held because: {reasons}</span>}
        {step === 'accept' && <span className="note" role="status">{ACCEPT_LIMIT}</span>}
        {step === 'reject' && (
          <span className="fld">
            <label htmlFor={uid}>Why not? The agent's owner sees this.</label>
            <textarea id={uid} name="reason" autoComplete="off" autoFocus maxLength={300} rows={2} value={reason} onChange={(e) => { setReason(e.target.value); setErr(''); }} />
            <span className="err" role="alert" hidden={!err}>{err}</span>
          </span>
        )}
        <span className="row">
          {step === 'idle' && (
            <>
              {canAccept(p) ? <button type="button" className="btn sm pri" disabled={action.pending} onClick={() => setStep('accept')}>Accept, runs as you</button> : <span className="note">{OWN_PROPOSAL_NOTE}</span>}
              <button type="button" className="btn sm" disabled={action.pending} onClick={() => setStep('reject')}>Reject…</button>
            </>
          )}
          {step === 'accept' && (
            <>
              <button type="button" className="btn sm pri" disabled={action.pending} onClick={accept}>Run as me</button>
              <button type="button" className="btn sm" disabled={action.pending} onClick={cancel}>Cancel</button>
            </>
          )}
          {step === 'reject' && (
            <>
              <button type="button" className="btn sm pri" disabled={action.pending || !reason.trim()} onClick={reject}>Reject proposal</button>
              <button type="button" className="btn sm" disabled={action.pending} onClick={cancel}>Cancel</button>
            </>
          )}
          {p.run_id && <a className="btn sm ghost" href={runHref(p.run_id)}>View the run</a>}
        </span>
      </span>
    </li>
  );
}
