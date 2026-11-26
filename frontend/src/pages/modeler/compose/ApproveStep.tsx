import { useState } from 'react';
import { approveComposition, compositionHistory, sendBack, submitComposition, type Composition, type CompositionStep } from '../../../api/compose';
import { currentAccount } from '../../../api/session';
import { toast } from '../../../components/toast';
import { useAction } from '../../../hooks/useAction';
import { STEP_ITEMS, approveBlock, stageLine, stateLine } from './composeView';

const MAKER_STEPS = STEP_ITEMS.filter(([k]) => k === 'describe' || k === 'mapping' || k === 'agents');
const MIN_REASON = 15;

/**
 * Step 4 of Compose (plan 9, P9-8.20, story X-10): the approver sees steps 1 to 3 together. "Approve" applies the changes, the
 * mapping and the stage settings as one; it is off for whoever composed the thing, with the maker-checker text. "Send back" pins a
 * reason (15 characters or more) to a step, and to a node when named. The maker's own "Submit for approval" is here too.
 * No agent approves or sends back: the server refuses it, and nothing on this page acts without a person's click.
 */
export function ApproveStep({ c }: { c: Composition }) {
  const me = currentAccount()?.id ?? null;
  const h = compositionHistory(c.id);
  const settings = c.steps.agents.settings as { stage: string }[] | undefined;
  const action = useAction();
  const [step, setStep] = useState<CompositionStep>('describe');
  const [node, setNode] = useState('');
  const [reason, setReason] = useState('');
  const [err, setErr] = useState('');
  const block = approveBlock(c, me);
  const editable = c.status === 'draft' || c.status === 'sent_back';
  const ready = MAKER_STEPS.every(([k]) => c.steps[k].state === 'done');

  const run = async (call: () => ReturnType<typeof approveComposition>, done: string) => {
    setErr('');
    const r = await action.run(call, { all: setErr });
    if (r.ok) toast(done);
  };

  return (
    <div className="cmp-step">
      <table className="t static" aria-label="Steps one to three">
        <thead><tr><th>Step</th><th>State</th><th>What it holds</th></tr></thead>
        <tbody>
          <tr>
            <td><b>Describe</b></td><td>{stateLine(c.steps.describe)}</td>
            <td className="note">{c.change_set.ops.length} change{c.change_set.ops.length === 1 ? '' : 's'} to {c.pack_key}</td>
          </tr>
          <tr>
            <td><b>Adapter mapping</b></td><td>{stateLine(c.steps.mapping)}</td>
            <td className="note">{((c.steps.mapping.fields as { state: string }[] | undefined) ?? []).filter((f) => f.state === 'accepted').length} accepted field mappings</td>
          </tr>
          <tr>
            <td><b>Agents</b></td><td>{stateLine(c.steps.agents)}</td>
            <td className="note">
              {settings?.length ? h.stages.map((s) => `${s.label}: ${stageLine(s)}`).join(' · ') : 'Not set yet'}
            </td>
          </tr>
        </tbody>
      </table>
      {c.status === 'sent_back' && MAKER_STEPS.map(([k, label]) => c.steps[k].note && (
        <p key={k} className="note" role="note">Sent back at {label}{c.steps[k].note?.node_id ? ` (${c.steps[k].note?.node_id})` : ''}: {c.steps[k].note?.reason}</p>
      ))}
      {editable && (
        <div className="row">
          <button className="btn sm pri" disabled={action.pending || !ready} onClick={() => void run(() => submitComposition(c.id), 'Submitted for approval.')}>Submit for approval</button>
          {!ready && <span className="note">Finish steps 1 to 3 first.</span>}
        </div>
      )}
      {c.status === 'submitted' && (
        <>
          <div className="row">
            <button className="btn sm pri" disabled={action.pending || !!block} title={block ?? undefined} onClick={() => void run(() => approveComposition(c.id), 'Approved: the changes, mapping and settings apply together.')}>Approve</button>
            {block && <span className="note">{block}</span>}
          </div>
          <fieldset className="cmp-question">
            <legend>Send back</legend>
            <div className="row">
              <label>Step <select aria-label="Step to send back" value={step} onChange={(e) => setStep(e.target.value as CompositionStep)}>
                {MAKER_STEPS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select></label>
              <label>Node (optional) <input aria-label="Node" value={node} maxLength={80} onChange={(e) => setNode(e.target.value)} placeholder="stage:condition" /></label>
            </div>
            <textarea aria-label="Reason to send back" rows={2} className="cmp-text" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="What should change (15 characters or more)" />
            <div className="row">
              <button className="btn sm" disabled={action.pending || reason.trim().length < MIN_REASON} onClick={() => void run(() => sendBack(c.id, step, reason.trim(), node.trim() || undefined), 'Sent back to its maker.')}>Send back</button>
              {reason.trim().length < MIN_REASON && <span className="note">{reason.trim().length}/{MIN_REASON} characters</span>}
            </div>
          </fieldset>
        </>
      )}
      {(c.status === 'approved' || c.status === 'published') && <p className="note">Approved by {c.approved_by}. Publishing is the next step.</p>}
      {err && <p className="err" role="alert">{err}</p>}
    </div>
  );
}
