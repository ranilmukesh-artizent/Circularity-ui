/**
 * One proposal held for a person (plan 10, section 2.6): used by the assistant dock's "Waiting for you" strip and by
 * Home's "Proposals for you" card. An agent prepared it and nothing runs until the signed-in person decides:
 * Accept runs the held action as that person (`proposal.accept`, through the same pipeline and approvals, after one
 * confirming step that names it), Reject asks for a reason (`proposal.reject`). When the agent acted for the
 * signed-in person (`own`) Accept is replaced by a note: another person accepts it (maker-checker, AGENTS.md rule 10).
 */
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { OWN_PROPOSAL_NOTE, reasonText, type HoldReason } from '../api/agents';
import { acceptProposal, rejectProposal, rgTime, type HomeProposal } from '../api/home';
import { useAction } from '../hooks/useAction';
import { toast } from './toast';
import { IconTile } from './kit/IconTile';
import { Modal } from './Overlay';
import { bulkGroups, confidenceText, describeInput } from './proposalDetail';

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

/** What accepting does, in plain words: the held action's input, the agent's confidence and the evidence behind it. Each
 *  part shows only when there is something to say; the hold reasons are the card's "Held because" line. */
function WhatItDoes({ p }: { p: HomeProposal }) {
  const { lines, more } = describeInput(p);
  const conf = confidenceText(p);
  const sources = p.sources ?? [];
  if (!lines.length && !conf && !sources.length) return null;
  return (
    <span className="as-does" data-does>
      <span className="as-does-h">If you accept: {p.title}</span>
      {lines.length > 0 && (
        <dl className="as-does-l">
          {lines.map((l) => (
            <span key={l.label} className="as-does-r"><dt>{l.label}</dt><dd>{l.value}</dd></span>
          ))}
        </dl>
      )}
      {more > 0 && <span className="note">and {more} more {more === 1 ? 'field' : 'fields'}</span>}
      {conf && <span className="note" data-confidence>Agent {conf.charAt(0).toLowerCase() + conf.slice(1)}</span>}
      {sources.length > 0 && (
        <span className="note" data-evidence>
          Evidence: {sources.slice(0, 4).map((x) => (x.fact ? `${x.fact} from ${x.source}` : x.source)).join(' · ')}
          {sources.length > 4 && ` · and ${sources.length - 4} more`}
        </span>
      )}
    </span>
  );
}

export function ProposalRow({ p, id, select }: { p: HomeProposal; id?: string; select?: { checked: boolean; onChange: (on: boolean) => void } }) {
  const action = useAction();
  const uid = useId();
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const [step, setStep] = useState<'idle' | 'accept' | 'reject'>('idle');
  useEffect(() => {
    if (step === 'reject') reasonRef.current?.focus();
  }, [step]);
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
      {select && canAccept(p) && (
        <input type="checkbox" className="as-pick" checked={select.checked} onChange={(e) => select.onChange(e.target.checked)} aria-label={`Select ${p.title}${p.case_id ? ' for ' + p.case_id : ''} to accept with the others`} />
      )}
      <IconTile ic="bot" h="agent" cls="sm" />
      <span className="as-card-b">
        <span className="as-prov">
          {p.agentName} · held {rgTime(p.at)}
          {p.case_id && <> · <a href={'#/product/' + p.case_id}>{p.case_id}</a></>}
        </span>
        <b className="as-card-t">{p.title}</b>
        {p.why && <span className="note">Why: {p.why}</span>}
        {reasons && <span className="note" data-reasons>Held because: {reasons}</span>}
        <WhatItDoes p={p} />
        {step === 'accept' && <span className="note" role="status">{ACCEPT_LIMIT}</span>}
        {step === 'reject' && (
          <span className="fld">
            <label htmlFor={uid}>Why not? The agent's owner sees this.</label>
            <textarea id={uid} name="reason" autoComplete="off" ref={reasonRef} maxLength={300} rows={2} value={reason} onChange={(e) => { setReason(e.target.value); setErr(''); }} />
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

/**
 * The proposals of a list as cards, with bulk accept: when two or more are the same action held for the same reason, a bar
 * offers "Select all" for that group; rows can be ticked one by one (one group at a time). "Accept N" opens a confirmation
 * that lists them; each one then runs as the signed-in person through `proposal.accept`, one at a time, and a refusal of one
 * does not stop the rest. A person's own agent's proposal never joins (maker-checker).
 */
export function ProposalItems({ list, idPrefix, label, className = 'as-list' }: { list: HomeProposal[]; idPrefix: string; label: string; className?: string }) {
  const groups = useMemo(() => bulkGroups(list), [list]);
  const [picked, setPicked] = useState<number[]>([]);
  const [confirm, setConfirm] = useState(false);
  const action = useAction();
  const live = picked.filter((i) => list.some((p) => p.id === i));
  const groupOf = (pid: number) => groups.find((g) => g.ids.includes(pid));
  const toggle = (pid: number, on: boolean) => {
    const g = groupOf(pid);
    if (!g) return;
    const same = live.filter((i) => g.ids.includes(i));
    setPicked(on ? [...same, pid] : same.filter((i) => i !== pid));
  };
  const chosen = list.filter((p) => live.includes(p.id));
  const run = async () => {
    let ok = 0;
    for (const p of chosen) {
      const r = await action.run(() => acceptProposal(p.id));
      if (r.ok) ok += 1;
    }
    setConfirm(false);
    setPicked([]);
    toast(ok === chosen.length ? `${ok} proposals ran as you.` : `${ok} of ${chosen.length} proposals ran as you; the rest were refused.`);
  };
  return (
    <>
      {groups.length > 0 && (
        <div className="as-bulk" role="group" aria-label="Accept proposals with the same reason">
          {groups.map((g) => (
            <span key={g.key} className="as-bulk-g">
              <span>{g.ids.length} with the same reason: {g.label}</span>
              <button type="button" className="btn sm" onClick={() => setPicked(g.ids)}>Select all {g.ids.length}</button>
            </span>
          ))}
          {chosen.length > 0 && (
            <span className="as-bulk-g as-bulk-go">
              <span>{chosen.length} selected</span>
              <button type="button" className="btn sm pri" disabled={action.pending} onClick={() => setConfirm(true)}>Accept {chosen.length}, runs as you</button>
              <button type="button" className="btn sm ghost" onClick={() => setPicked([])}>Clear</button>
            </span>
          )}
        </div>
      )}
      <ul className={className} aria-label={label}>
        {list.map((p) => (
          <ProposalRow key={p.id} p={p} id={idPrefix + p.id} select={groupOf(p.id) ? { checked: live.includes(p.id), onChange: (on) => toggle(p.id, on) } : undefined} />
        ))}
      </ul>
      {confirm && (
        <Modal
          title={`Accept ${chosen.length} proposals`}
          onClose={() => setConfirm(false)}
          foot={
            <>
              <button type="button" className="btn" onClick={() => setConfirm(false)}>Cancel</button>
              <button type="button" className="btn pri" disabled={action.pending} onClick={run}>Run all as me</button>
            </>
          }
        >
          <p className="note">Each is accepted one at a time, with your permissions and approvals. {ACCEPT_LIMIT}</p>
          <ul className="as-bulk-list">
            {chosen.map((p) => (
              <li key={p.id}>
                <b>{p.title}</b>{p.case_id && <> · {p.case_id}</>} <span className="note">by {p.agentName}</span>
              </li>
            ))}
          </ul>
        </Modal>
      )}
    </>
  );
}
