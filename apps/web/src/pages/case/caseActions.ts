/** The human-in-the-loop actions of the case pages, each one invoke() with the demo's action id and its toast. */
import { actionCatalog, invoke } from '../../api/actions';
import { approverRole, caseById, checkAcknowledgement, evidencePack, nextStep } from '../../api/case';
import { money } from '../../api/format';
import { can } from '../../api/session';
import type { ActionResult } from '../../api/types';
import { askSoon } from '../../ui/askBus';
import { toast } from '../../ui/toast';
import { refused } from '../../ui/useAction';
import type { CaseUi } from './CaseContext';

/** The demo's UI adapters for the case actions. */
export const caseActions = {
  async submit(id: string) {
    const r = await invoke('decision.submit', { case_id: id });
    if (!refused(r, 4200)) toast(id + ' submitted for review. An Approver approves, overrides or declines it.', 4200);
  },
  async requestEvidence(id: string) {
    const r = await invoke<{ what: string; to: string; ref: string }>('evidence.request', { case_id: id });
    if (r.ok) toast(`${r.output.what} sent to ${r.output.to} (${r.output.ref}).`);
    else refused(r, 4200);
  },
  async recordResult(id: string) {
    const r = await invoke<{ recommendation: string | null; net: number }>('evidence.recordResult', { case_id: id });
    if (refused(r, 4200)) return;
    const o = r.output;
    toast(o.recommendation ? `${id} is ready. Recommendation: ${o.recommendation} at ${money(o.net)}.` : `${id} assessed, but no route passes every gate.`, 4200);
  },
  async reevaluate(id: string) {
    const r = await invoke<{ now: string | null; was: string | null; net: number }>('case.reevaluate', { case_id: id });
    if (refused(r, 4200)) return;
    const o = r.output;
    toast(o.now ? `Re-evaluated. New recommendation: ${o.now} at ${money(o.net)}${o.was && o.was !== o.now ? ` (was ${o.was})` : ''}.` : 'Re-evaluated. No route passes every gate.', 4200);
  },
  /** "Check for the next acknowledgement": the systems answer (the worker's). */
  async advance(id: string) {
    const c = caseById(id);
    if (!c) return;
    const r = await checkAcknowledgement(c);
    if (refused(r, 4200)) return;
    const o = r.output;
    toast(`${o.label}: acknowledged by ${o.by} · ${o.ref_label}`);
  },
  async resend(id: string) {
    const r = await invoke('instruction.resend', { case_id: id });
    if (!refused(r, 4200)) toast('Duplicate delivery ignored. The idempotency key already exists, so nothing was created twice.', 4200);
  },
  async confirmOutcome(id: string) {
    const r = await invoke('outcome.confirm', { case_id: id });
    if (!refused(r, 4200)) toast('Outcome confirmed and linked to the decision.');
  },
  downloadPack(id: string) {
    const p = evidencePack(id);
    if (!p) return;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(p, null, 2)], { type: 'application/json' }));
    a.download = 'evidence-pack-' + id + '.json';
    a.click();
    toast('Evidence pack for ' + id + ' downloaded.');
  },
  copy(v: string) {
    (navigator.clipboard ? navigator.clipboard.writeText(v) : Promise.reject()).then(() => toast(v + ' copied.'), () => toast('Copy: ' + v, 5000));
  },
  askSoon,
};

/** The agent's suggested next step for this person (runNext): one action, the approval card, or why it waits. */
export async function runNextStep(id: string, ui: CaseUi, quiet = false) {
  const c = caseById(id);
  if (!c) return;
  const st = nextStep(c);
  if (st.kind === 'approve') return approveGuarded(id, ui);
  let r: ActionResult<Record<string, unknown>>;
  if (st.kind === 'act') r = await invoke(st.action!, st.input);
  else if (st.kind === 'ack') r = (await checkAcknowledgement(c)) as ActionResult<Record<string, unknown>>;
  else return toast(st.label, 4200);
  if (refused(r, 4200)) return;
  if (quiet) return toast('Stage ' + st.n + ': ' + st.label + ' · done.');
  const o = r.output, title = actionCatalog().find((a) => a.id === r.action)?.title;
  toast((title ?? 'Done') + (o.ref ? ' · ' + o.ref : '') + (o.case_id ? ' · ' + o.case_id : '') + '.', 3600);
}

/** afOpenApproval: only an approver, only while the case awaits approval. */
export function approveGuarded(id: string, ui: CaseUi, mode?: 'review') {
  const c = caseById(id);
  if (!c) return;
  if (!can('approve')) return toast('Only ' + (approverRole(c) === 'Approver' ? 'an Approver' : 'Admin') + ' can approve.');
  if (c.stage !== 'awaiting_approval') return toast(id + ' is not awaiting approval.');
  ui.openApproval(id, mode);
}

/** Decline: only an approver (ACT.declineDecision). */
export function declineGuarded(id: string, ui: CaseUi) {
  if (can('approve')) ui.openDecline(id);
}

/** Scroll to a section of the page (tiStep, tiExplain). */
export function scrollToId(id: string) {
  const e = document.getElementById(id);
  e?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
}
