import { guardrailCount, proposeChange, type Proposal } from '../../../api/modeler';
import type { AssistantContext, ModeDef, Status } from '../types';
import { ChangeEmpty, ChangeTurn } from './ChangeTurn';
import { dismissPending, flowSurface, pendingOfSentence, setPending } from '../flow/changeStore';

/** What a Change flow turn keeps in `turn.data`. */
export interface ChangeData {
  /** ties the turn to the proposal held for it (the turn's own id is the reducer's) */
  key: number;
  proposal: Proposal;
  text: string;
}

let seq = 0;
const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`;

/** The status line of a finished proposal (plan 10, 2.4): action word, specific item, limit. Numbers come from the read. */
export function proposedStatus(p: Proposal, guardrails: number | undefined): Status {
  const gr = guardrails != null ? `against ${plural(guardrails, 'guardrail')}` : 'against the guardrails';
  if (p.kind === 'blocked') return { verb: 'Blocked', item: p.guard ? `by ${p.guard}` : gr, limit: 'nothing saved', state: 'blocked' };
  if (p.kind === 'unclear') return { verb: 'Could not read', item: 'the sentence as a change', limit: 'nothing saved', state: 'done' };
  return { verb: 'Checked', item: gr, limit: `${p.kind === 'rule' ? '1 rule' : '1 step'} proposed`, state: 'done' };
}

const unavailable = (ctx: AssistantContext): string | null =>
  !ctx.flow ? 'Open a flow in the Modeler to change it' : !ctx.flow.canEdit ? 'Needs Modeler edit rights' : null;

/** Change flow mode (plan 10, 2.1): `flow.propose` reads the sentence, checks and simulates it; the person applies it. */
export const changeMode: ModeDef = {
  id: 'change',
  label: 'Change flow',
  placeholder: 'Describe a change to this flow…',
  limits: () => 'Proposes only. You apply it; another person approves it.',
  unavailable,

  async send(text, _ctx, io) {
    const sf = flowSurface();
    const key = ++seq;
    if (!sf) {
      io.patch((t) => ({ ...t, error: 'Open a flow in the Modeler to change it.', status: [{ verb: 'Could not start', item: 'a change', limit: 'nothing saved', state: 'failed' }] }));
      return;
    }
    const n = guardrailCount(sf.template, sf.org);
    io.patch((t) => ({ ...t, status: [{ verb: 'Checking', item: `the sentence against ${n != null ? plural(n, 'guardrail') : 'the guardrails'}`, limit: 'nothing saved', state: 'working' }] }));
    dismissPending();
    await sf.flush();
    let p: Proposal;
    try {
      p = await proposeChange(sf.flowId, text);
    } catch (e) {
      if (io.signal.aborted) return void io.patch((t) => ({ ...t, status: [{ verb: 'Stopped', item: 'the check', limit: 'nothing was saved', state: 'stopped' }] }));
      io.patch((t) => ({ ...t, error: (e as Error).message, status: [{ verb: 'Could not check', item: 'the sentence', limit: 'nothing saved', state: 'failed' }] }));
      return;
    }
    if (io.signal.aborted) {
      io.patch((t) => ({ ...t, status: [{ verb: 'Stopped', item: 'the check', limit: 'nothing was saved', state: 'stopped' }] }));
      return;
    }
    if ((p.kind === 'rule' || p.kind === 'step' || p.kind === 'blocked') && p.graph) setPending(pendingOfSentence(p, text, key, sf));
    io.patch((t) => ({ ...t, data: { key, proposal: p, text } satisfies ChangeData, status: [proposedStatus(p, n)] }));
  },

  Turn: ChangeTurn,
  Empty: ChangeEmpty,
};
