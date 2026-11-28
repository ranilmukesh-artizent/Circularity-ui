/* Pure helpers of Set up (28 Nov 2026): the five steps in a person's words, the stops of the route line for a
   composition, the one next step, and which composition the page opens. No React, no calls. */
import type { Composition, CompositionStep } from '../../api/compose';
import type { Stop } from '../../components/kit/RouteLine';

export interface StepDef {
  id: CompositionStep;
  /** the name on the line */
  label: string;
  /** the heading of the step's panel */
  title: string;
  /** one line: what happens here and who does it */
  help: string;
}

export const STEPS: readonly StepDef[] = [
  { id: 'describe', label: 'Describe', title: 'Describe your business', help: 'Say how returns work in your own words. The agent drafts the decision flow as configuration; you check what it read.' },
  { id: 'mapping', label: 'Connect systems', title: 'Connect your systems', help: 'Each system the draft names is matched to a source. Suggested field mappings wait for you or the system owner.' },
  { id: 'agents', label: 'Set agents', title: 'Set your agents', help: 'Choose how far each stage’s agent may go alone. Guardrails apply whatever you choose.' },
  { id: 'approve', label: 'Approve', title: 'Approve', help: 'A different person checks the whole setup and approves it or sends a step back with a reason.' },
  { id: 'publish', label: 'Publish', title: 'Publish', help: 'An approver starts it for a share of one region first, with the replay report in view.' },
];
/** Describe, connect and agents are the maker's; approve and publish are another person's. */
export const HANDOVER = 3;
export const LANES: [string, string] = ['You', 'An approver'];

export const stepDef = (id: CompositionStep): StepDef => STEPS.find((s) => s.id === id) ?? STEPS[0];
export const isStep = (v: string | null): v is CompositionStep => !!v && STEPS.some((s) => s.id === v);

/** The step that is next for a composition: the first one not done (Publish once everything else is). */
export function currentStep(c: Composition | null): CompositionStep {
  if (!c) return 'describe';
  if (c.status === 'published') return 'publish';
  return STEPS.find((s) => c.steps[s.id]?.state !== 'done')?.id ?? 'publish';
}

/** The route line's stops. Without a composition only Describe is next; a published one has every stop done. */
export function stops(c: Composition | null): Stop[] {
  const now = currentStep(c);
  return STEPS.map((s) => {
    const st = c?.steps[s.id]?.state;
    if (c?.status === 'published' || st === 'done') return { id: s.id, label: s.label, state: 'done' as const, note: 'Done' };
    if (st === 'sent_back') return { id: s.id, label: s.label, state: 'back' as const, note: 'Sent back' };
    if (s.id === now) return { id: s.id, label: s.label, state: 'now' as const, note: s.id === 'approve' && c?.status === 'submitted' ? 'Waiting' : 'Next' };
    return { id: s.id, label: s.label, state: 'todo' as const, note: 'Not started' };
  });
}

/** How many of the five are done. */
export const doneCount = (c: Composition | null): number => stops(c).filter((s) => s.state === 'done').length;

/** The one button: what the person does next, and the step it opens. */
export function nextAction(c: Composition | null): { step: CompositionStep; label: string } {
  const step = currentStep(c);
  if (!c) return { step, label: 'Choose a template' };
  const back = STEPS.find((s) => c.steps[s.id]?.state === 'sent_back');
  if (back) return { step: back.id, label: 'See what was sent back' };
  const label: Record<CompositionStep, string> = {
    describe: 'Review the draft',
    mapping: 'Connect your systems',
    agents: 'Set your agents',
    approve: c.status === 'submitted' ? 'See the approval' : 'Send for approval',
    publish: c.status === 'published' ? 'Open the published setup' : 'Publish',
  };
  return { step, label: label[step] };
}

/** The compositions still in play, newest first (a discarded one is gone). */
export const live = (all: readonly Composition[]): Composition[] => all.filter((c) => c.status !== 'discarded').sort((a, b) => b.id - a.id);

/** Has the organisation published a setup? Home's "Start here" card shows until it has. */
export const hasPublished = (all: readonly Composition[]): boolean => all.some((c) => c.status === 'published');

/** The composition the page opens: the one asked for, else the newest in play (of the org when one is picked). */
export function pick(all: readonly Composition[], id: number | null, org?: string | null): Composition | null {
  const list = live(all);
  if (id != null) return list.find((c) => c.id === id) ?? null;
  return (org ? list.find((c) => c.org_unit_id === org) : list[0]) ?? null;
}

/** "#/setup?compose=12&step=mapping" (a hash-router path without the #). */
export function setupPath(o: { compose?: number | null; step?: StopId | null; org?: string | null; pack?: string | null; fresh?: boolean } = {}): string {
  const q = new URLSearchParams();
  if (o.org) q.set('org', o.org);
  if (o.fresh) q.set('new', '1');
  if (o.pack) q.set('pack', o.pack);
  if (o.compose != null) q.set('compose', String(o.compose));
  if (o.step) q.set('step', o.step);
  const s = q.toString();
  return '/setup' + (s ? '?' + s : '');
}

/** "Setup 12 · Tool fleet · draft" for the picker. */
export const compositionLabel = (c: Composition, packName?: string): string =>
  `Setup ${c.id}, ${packName ?? c.pack_key.replace(/_/g, ' ')} for ${orgName(c.org_unit_id)}, ${c.status.replace('_', ' ')}`;

/** An org id for people: `workspace` reads "Workspace"; a customer's name stays as it is. */
export function orgName(id: string): string {
  return id.charAt(0).toUpperCase() + id.slice(1).replace(/[_-]+/g, ' ');
}

// ---------------------------------------------------------------- the page's stops (28 Nov 2026, the workspace)

/** A stop of the Set up page: Compose's five steps, plus two the page adds that have no state of their own in a composition:
 *  `flow` (the decision flow, the Modeler's own draft) and `access` (who may do what, Access & Governance's). */
export type StopId = CompositionStep | 'flow' | 'access';

export interface StopDef {
  id: StopId;
  label: string;
  title: string;
  help: string;
}

export const PAGE_STOPS: readonly StopDef[] = [
  { id: 'describe', label: 'Template', title: 'Choose a template and describe your business', help: 'Start from the pack closest to your business, then say what is different in your own words. The agent drafts the changes; you check what it read.' },
  { id: 'flow', label: 'Shape the flow', title: 'Shape the decision flow', help: 'The flow your returns follow. Tell the assistant what to change, or edit a step on the canvas. It is the same draft the Modeler shows.' },
  { id: 'mapping', label: 'Connect systems', title: 'Connect your systems', help: 'For each system: connect it, choose the tables that matter, then map their fields to the canonical model.' },
  { id: 'agents', label: 'Set agents', title: 'Set your agents', help: 'How far the agent of each stage may go alone. Guardrails apply whatever you choose.' },
  { id: 'access', label: 'Access', title: 'Check who can do what', help: 'Who makes, who approves and who only reads for this organisation. Changes are made in Access & Governance.' },
  { id: 'approve', label: 'Approve', title: 'Approve', help: 'A different person checks the whole setup and approves it, or sends a step back with a reason.' },
  { id: 'publish', label: 'Publish', title: 'Publish', help: 'Four things must be true before it goes live for a share of one region. Each line says who does it.' },
];
/** The first five stops are the maker's; approve and publish are another person's. */
export const PAGE_HANDOVER = 5;

export const isStop = (v: string | null): v is StopId => !!v && PAGE_STOPS.some((s) => s.id === v);
export const stopDef = (id: StopId): StopDef => PAGE_STOPS.find((s) => s.id === id) ?? PAGE_STOPS[0];

/** The page's route line: Compose's stops with the two page stops in place. `flowStatus` is the status of the org's decision
 *  flow for the pack (pub: as the template; draft, review or shadow: the person changed it), unknown while it loads. */
export function pageStops(c: Composition | null, flowStatus?: string | null): Stop[] {
  const five = Object.fromEntries(stops(c).map((s) => [s.id, s]));
  const published = c?.status === 'published';
  return PAGE_STOPS.map((d): Stop => {
    if (d.id === 'flow') {
      if (published) return { id: d.id, label: d.label, state: 'done', note: 'Done' };
      if (flowStatus && flowStatus !== 'pub') return { id: d.id, label: d.label, state: 'done', note: flowStatus === 'draft' ? 'Changed' : flowStatus === 'review' ? 'In review' : 'In shadow' };
      return { id: d.id, label: d.label, state: 'todo', note: c ? 'As the template' : 'Not started' };
    }
    if (d.id === 'access') return { id: d.id, label: d.label, state: published ? 'done' : 'todo', note: published ? 'Done' : c ? 'Review' : 'Not started' };
    return { ...five[d.id], label: d.label };
  });
}

/** The stop after and before one, along the page's line. */
export function neighbours(id: StopId): { prev: StopId | null; next: StopId | null } {
  const i = PAGE_STOPS.findIndex((s) => s.id === id);
  return { prev: PAGE_STOPS[i - 1]?.id ?? null, next: PAGE_STOPS[i + 1]?.id ?? null };
}
