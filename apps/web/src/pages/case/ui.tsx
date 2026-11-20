import { createContext, useContext, useEffect, useRef, type CSSProperties } from 'react';
import { useNavigate } from 'react-router-dom';
import { actionCatalog, invoke } from '../../api/actions';
import { agentButton, approverRole, caseById, evidencePack, nextStep, refresh, runLegacyAct, simulateSystemAck, type LegacyHooks } from '../../api/case';
import { money } from '../../api/format';
import { can } from '../../api/session';
import type { ActionResult } from '../../api/types';
import { toast } from '../../ui/toast';

/** The dialogs a case page can open, and the one handler for every demo button inside its HTML blocks. */
export interface CaseUi {
  openApproval(id: string, mode?: 'review'): void;
  openDecline(id: string): void;
  openExplain(id: string): void;
  legacyModal(m: { title: string; body: string; foot: string; wide: boolean } | null): void;
}
export const CaseUiContext = createContext<CaseUi | null>(null);
export const useCaseUi = (): CaseUi => useContext(CaseUiContext)!;

const fail = (r: ActionResult<unknown>): boolean => {
  if (!r.ok) toast(r.error.message, 4200);
  return !r.ok;
};

/** The human-in-the-loop actions, each one invoke() with the demo's action id and its toast (the demo's UI adapters). */
export const caseActions = {
  async submit(id: string) {
    const r = await invoke('decision.submit', { case_id: id });
    if (!fail(r)) toast(id + ' submitted for review. An Approver approves, overrides or declines it.', 4200);
  },
  async requestEvidence(id: string) {
    const r = await invoke<{ what: string; to: string; ref: string }>('evidence.request', { case_id: id });
    if (r.ok) toast(`${r.output.what} sent to ${r.output.to} (${r.output.ref}).`);
    else fail(r);
  },
  async recordResult(id: string) {
    const r = await invoke<{ recommendation: string | null; net: number }>('evidence.recordResult', { case_id: id });
    if (!r.ok) return fail(r);
    const o = r.output;
    toast(o.recommendation ? `${id} is ready. Recommendation: ${o.recommendation} at ${money(o.net)}.` : `${id} assessed, but no route passes every gate.`, 4200);
  },
  async reevaluate(id: string) {
    const r = await invoke<{ now: string | null; was: string | null; net: number }>('case.reevaluate', { case_id: id });
    if (!r.ok) return fail(r);
    const o = r.output;
    toast(o.now ? `Re-evaluated. New recommendation: ${o.now} at ${money(o.net)}${o.was && o.was !== o.now ? ` (was ${o.was})` : ''}.` : 'Re-evaluated. No route passes every gate.', 4200);
  },
  /** "Check for the next acknowledgement": the simulated enterprise system answers. */
  advance(id: string) {
    const r = simulateSystemAck(id);
    if (!r.ok) return fail(r);
    const o = r.output;
    toast(`${o.label}: acknowledged by ${o.by} · ${o.ref_label}`);
  },
  async resend(id: string) {
    const r = await invoke('instruction.resend', { case_id: id });
    if (!fail(r)) toast('Duplicate delivery ignored. The idempotency key already exists, so nothing was created twice.', 4200);
  },
  async confirmOutcome(id: string) {
    const r = await invoke('outcome.confirm', { case_id: id });
    if (!fail(r)) toast('Outcome confirmed and linked to the decision.');
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
  askSoon() {
    toast('Ask Circularity arrives soon.');
  },
};

/** The agent's suggested next step for this person (runNext): one action, the approval card, or why it waits. */
export async function runNextStep(id: string, ui: CaseUi, quiet = false) {
  const c = caseById(id);
  if (!c) return;
  const st = nextStep(c);
  if (st.kind === 'approve') return approveGuarded(id, ui);
  let r: ActionResult<Record<string, unknown>>;
  if (st.kind === 'act') r = await invoke(st.action!, st.input);
  else if (st.kind === 'ack') r = simulateSystemAck(id) as ActionResult<Record<string, unknown>>;
  else return toast(st.label, 4200);
  if (!r.ok) return toast(r.error.message, 4200);
  if (quiet) return toast('Stage ' + st.n + ': ' + st.label + ' · done.');
  const o = r.output, title = actionCatalog().find((a) => a.id === r.action)?.title;
  toast((title ?? 'Done') + (o.ref ? ' · ' + o.ref : '') + (o.case_id ? ' · ' + o.case_id : '') + '.', 3600);
}

/** afOpenApproval: only an approver, only while the case awaits approval. */
export function approveGuarded(id: string, ui: CaseUi, mode?: 'review') {
  const c = caseById(id);
  if (!c) return;
  if (!can('approve')) return toast('Only ' + (approverRole() === 'Approver' ? 'an Approver' : 'Admin') + ' can approve.');
  if (c.stage !== 'awaiting_approval') return toast(id + ' is not awaiting approval.');
  ui.openApproval(id, mode);
}

/** Map a demo button inside an HTML block onto the React handlers; anything else runs the demo's own view handler. */
function handleAct(name: string, arg: string, el: Element, ev: Event, ui: CaseUi, hooks: LegacyHooks, quiet: boolean, value: unknown): boolean {
  switch (name) {
    case 'approve': { const [id, mode] = arg.split('|'); approveGuarded(id, ui, mode === 'review' ? 'review' : undefined); return true; }
    case 'declineDecision': if (can('approve')) ui.openDecline(arg); return true;
    case 'tiSubmit': caseActions.submit(arg); return true;
    case 'reqEvidence': caseActions.requestEvidence(arg); return true;
    case 'simResult': caseActions.recordResult(arg); return true;
    case 'reeval': caseActions.reevaluate(arg); return true;
    case 'advance': caseActions.advance(arg); return true;
    case 'replay': caseActions.resend(arg); return true;
    case 'confirmOutcome': caseActions.confirmOutcome(arg); return true;
    case 'afPack': caseActions.downloadPack(arg); return true;
    case 'stCopy': caseActions.copy(arg); return true;
    case 'cxExplain': ui.openExplain(arg); return true;
    case 'go': hooks.go(arg); return true;
    case 'closeModal': ui.legacyModal(null); return true;
    case 'stAsk': case 'stNotify': case 'afAssist': case 'afPanel': case 'frAskQ': caseActions.askSoon(); return true;
    case 'afDo': {
      const p = agentButton(arg);
      if (!p) return true;
      if (p.approve) { approveGuarded(p.approve, ui); return true; }
      if (p.next) { runNextStep(p.next, ui); return true; }
      if (p.go) { ui.legacyModal(null); hooks.go(p.go); return true; }
      if (p.decline) { if (can('approve')) ui.openDecline(p.decline); return true; }
      if (p.ask) { caseActions.askSoon(); return true; }
      return runLegacyAct(name, arg, el, ev, hooks, quiet);
    }
    default:
      return runLegacyAct(name, value, el, ev, hooks, quiet);
  }
}

/**
 * A block of the demo's own markup (detail tabs, Full analysis, dialogs). Its buttons (data-act), sliders (data-in)
 * and selects/ticks (data-ch) are delegated as the demo's document listeners did.
 */
export function Legacy({ html, className, style, as = 'div' }: { html: string; className?: string; style?: CSSProperties; as?: 'div' | 'span' }) {
  const ui = useCaseUi();
  const nav = useNavigate();
  const ref = useRef<HTMLElement>(null);
  const dragging = useRef(false);
  const hooks: LegacyHooks = {
    toast,
    modal: (m) => ui.legacyModal(m),
    go: (p) => nav('/' + p),
  };
  const latest = useRef({ ui, hooks });
  latest.current = { ui, hooks };

  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const onClick = (e: MouseEvent) => {
      const t = (e.target as Element).closest('[data-act]') as HTMLElement | null;
      if (!t || !root.contains(t)) return;
      if ((t as HTMLButtonElement).disabled || t.getAttribute('aria-disabled') === 'true') {
        if (t.dataset.why) toast(t.dataset.why);
        return;
      }
      e.preventDefault();
      const { ui: u, hooks: h } = latest.current;
      handleAct(t.dataset.act!, t.dataset.arg ?? '', t, e, u, h, false, t.dataset.arg);
    };
    const onInput = (e: Event) => {
      const t = (e.target as Element).closest('[data-in]') as HTMLInputElement | null;
      if (!t || !root.contains(t)) return;
      dragging.current = true;
      const { ui: u, hooks: h } = latest.current;
      handleAct(t.dataset.in!, t.dataset.arg ?? '', t, e, u, h, true, t.value); // re-render on release, not mid-drag
    };
    const onChange = (e: Event) => {
      const el = e.target as HTMLInputElement;
      const t = el.closest('[data-ch]') as HTMLInputElement | null;
      const { ui: u, hooks: h } = latest.current;
      if (t && root.contains(t)) handleAct(t.dataset.ch!, t.dataset.arg ?? '', t, e, u, h, false, t.type === 'checkbox' ? t.checked : t.value);
      else if (dragging.current && el.closest('[data-in]')) { dragging.current = false; refresh(); }
    };
    root.addEventListener('click', onClick);
    root.addEventListener('input', onInput);
    root.addEventListener('change', onChange);
    return () => {
      root.removeEventListener('click', onClick);
      root.removeEventListener('input', onInput);
      root.removeEventListener('change', onChange);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const Tag = as;
  return <Tag ref={ref as never} className={className} style={style} dangerouslySetInnerHTML={{ __html: html }} />;
}
