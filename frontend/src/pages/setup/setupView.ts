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

/** How many of the five stops of the line are done (the same count the line shows). */
export const doneCount = (c: Composition | null): number => pageStops(c).filter((s) => s.state === 'done').length;

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
 *  `flow` (the decision flow, the Modeler's own draft) and `access` (who may do what, Access & Governance's). These seven
 *  stay in the data and in every link; the route line shows five of them (see LINE). */
export type StopId = CompositionStep | 'flow' | 'access';

/** A screen of the page: a stop that has a screen of its own. `access` is a section of the Approve screen. */
export type ScreenId = Exclude<StopId, 'access'>;

export interface StopDef {
  id: StopId;
  label: string;
  title: string;
  help: string;
}

export const PAGE_STOPS: readonly StopDef[] = [
  { id: 'describe', label: 'Template', title: 'Choose a template and describe your business', help: 'Start from the pack closest to your business, then say what is different in your own words. The agent drafts the changes; you check what it read.' },
  { id: 'flow', label: 'Shape the flow', title: 'Shape the decision flow', help: 'The flow your returns follow. Tell the assistant what to change, or edit a step on the canvas. It is the same draft the Modeler shows.' },
  { id: 'mapping', label: 'Systems', title: 'Connect your systems', help: 'For each system: connect it, choose the tables that matter, then map their fields to the canonical model.' },
  { id: 'agents', label: 'Agents', title: 'Set your agents', help: 'How far the agent of each stage may go alone. Guardrails apply whatever you choose.' },
  { id: 'access', label: 'Access', title: 'Who can do what', help: 'Who makes, who approves and who only reads for this organisation. Changes are made in Access & Governance.' },
  { id: 'approve', label: 'Approve', title: 'Approve', help: 'See who can approve, then a different person checks the whole setup and approves it, or sends a step back with a reason.' },
  { id: 'publish', label: 'Publish', title: 'Publish', help: 'Four things must be true before it goes live for a share of one region. Each line says who does it.' },
];

export const isStop = (v: string | null): v is StopId => !!v && PAGE_STOPS.some((s) => s.id === v);
export const stopDef = (id: StopId): StopDef => PAGE_STOPS.find((s) => s.id === id) ?? PAGE_STOPS[0];
/** The screen that shows a stop: an old link to `step=access` opens Approve, where Access is the first section. */
export const screenOf = (id: StopId): ScreenId => (id === 'access' ? 'approve' : id);

/** One stop of the route line: what the person sees as a step. Its id is the id of its first stop, so a link built from it
 *  (`step=describe`) is also a link the page always understood. */
export interface LineDef {
  id: CompositionStep;
  label: string;
  /** the stops it holds; the one with its own id is Compose's step, whose state it follows */
  stops: readonly StopId[];
  /** the screens it shows, in order */
  screens: readonly ScreenId[];
}

export const LINE: readonly LineDef[] = [
  { id: 'describe', label: 'Business flow', stops: ['describe', 'flow'], screens: ['describe', 'flow'] },
  { id: 'mapping', label: 'Systems', stops: ['mapping'], screens: ['mapping'] },
  { id: 'agents', label: 'Agents', stops: ['agents'], screens: ['agents'] },
  { id: 'approve', label: 'Approve', stops: ['approve', 'access'], screens: ['approve'] },
  { id: 'publish', label: 'Publish', stops: ['publish'], screens: ['publish'] },
];
/** Business flow, Systems and Agents are the maker's; Approve and Publish are another person's. */
export const PAGE_HANDOVER = 3;

/** The stop of the line that holds a stop (or screen). */
export const lineOf = (id: StopId): CompositionStep => LINE.find((l) => l.stops.includes(id))?.id ?? 'describe';

/** The screen in view: the one asked for in the link, else the one that is next. `access` reads as Approve. */
export const screenFor = (c: Composition | null, asked: string | null): ScreenId => (c && isStop(asked) ? screenOf(asked) : currentStep(c));

/** What Back and Next say for a screen (the two screens of Business flow are told apart). */
export const SCREEN_LABEL: Record<ScreenId, string> = {
  describe: 'Business flow: template',
  flow: 'Business flow: the flow',
  mapping: 'Systems',
  agents: 'Agents',
  approve: 'Approve',
  publish: 'Publish',
};

/** A screen's place in its line, "Part 1 of 2", when the line has more than one screen; else null. */
export function partLine(id: StopId): string | null {
  const l = LINE.find((x) => x.id === lineOf(id));
  if (!l || l.screens.length < 2) return null;
  return `Part ${l.screens.indexOf(screenOf(id)) + 1} of ${l.screens.length}`;
}

/** The seven stops with their own states. `flowStatus` is the status of the org's decision flow for the pack (pub: as the
 *  template; draft, review or shadow: the person changed it), unknown while it loads. The flow stop is done once it was changed
 *  or the person went on past it; the access stop is done once the setup went to its approver. Neither has a state of its own
 *  on the server. */
export function stopStates(c: Composition | null, flowStatus?: string | null): Stop[] {
  const five = Object.fromEntries(stops(c).map((s) => [s.id, s]));
  const published = c?.status === 'published';
  const wentOn = !!c && (['mapping', 'agents', 'approve'] as const).some((k) => c.steps[k]?.state === 'done');
  return PAGE_STOPS.map((d): Stop => {
    if (d.id === 'flow') {
      if (published) return { id: d.id, label: d.label, state: 'done', note: 'Done' };
      if (flowStatus && flowStatus !== 'pub') return { id: d.id, label: d.label, state: 'done', note: flowStatus === 'draft' ? 'Changed' : flowStatus === 'review' ? 'In review' : 'In shadow' };
      return { id: d.id, label: d.label, state: wentOn ? 'done' : 'todo', note: c ? 'As the template' : 'Not started' };
    }
    if (d.id === 'access') {
      const passed = published || c?.steps.approve?.state === 'done' || c?.status === 'submitted' || c?.status === 'approved';
      return { id: d.id, label: d.label, state: passed ? 'done' : 'todo', note: passed ? 'Done' : c ? 'Review' : 'Not started' };
    }
    return { ...five[d.id], label: d.label };
  });
}

/** The route line: five stops. A stop that holds two is done when both are; it is sent back when one is; it is next when the
 *  setup's next step is in it; else it is not started and says what is left in it. */
export function pageStops(c: Composition | null, flowStatus?: string | null): Stop[] {
  const seven = stopStates(c, flowStatus);
  return LINE.map((l): Stop => {
    const own = l.stops.map((id) => seven.find((s) => s.id === id) as Stop);
    const first = own.find((s) => s.id === l.id) as Stop;
    if (own.every((s) => s.state === 'done')) return { id: l.id, label: l.label, state: 'done', note: 'Done' };
    const back = own.find((s) => s.state === 'back');
    if (back) return { id: l.id, label: l.label, state: 'back', note: back.note };
    const now = first.state === 'now' ? first : own.find((s) => s.state === 'now');
    if (now) return { id: l.id, label: l.label, state: 'now', note: now.note };
    const left = first.state !== 'done' ? first : (own.find((s) => s.state !== 'done') ?? first);
    return { id: l.id, label: l.label, state: 'todo', note: left.note };
  });
}

/** The screen after and before one, along the page (Business flow's two screens, then Systems, and so on). */
export function neighbours(id: StopId): { prev: ScreenId | null; next: ScreenId | null } {
  const order = LINE.flatMap((l) => l.screens);
  const i = order.indexOf(screenOf(id));
  return { prev: order[i - 1] ?? null, next: order[i + 1] ?? null };
}

// ---------------------------------------------------------------- the template picker (28 Nov 2026)

interface PackWords { key: string; name: string; industry: string; unit: string; classes: string[] }

const words = (t: string): string[] => t.toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length >= 4);
/** Two words meet when one starts with the other ("tools" and "tool", "vehicles" and "vehicle"). */
const meets = (a: string, b: string): boolean => a.startsWith(b) || b.startsWith(a);
/** Words every template shares: they say nothing about which one. */
const COMMON = new Set(['returns', 'return', 'equipment', 'more', 'with', 'from', 'that', 'time', 'asset', 'assets', 'class']);

/** The templates a search shows: every word typed is in the name, the industry, the unit or a class. All of them for no words. */
export function filterPacks<P extends PackWords>(cards: P[], q: string): P[] {
  const asked = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!asked.length) return cards;
  return cards.filter((p) => {
    const hay = [p.name, p.industry, p.unit, ...p.classes].join(' ').toLowerCase();
    return asked.every((w) => hay.includes(w));
  });
}

/** How many of a template's own words (name, unit, classes) the description uses. */
function packScore(p: PackWords, said: string[]): number {
  const own = new Set(words([p.name, p.unit, ...p.classes].join(' ')).filter((w) => !COMMON.has(w)));
  let n = 0;
  for (const w of own) if (said.some((x) => meets(x, w))) n++;
  return n;
}

/**
 * Another template the description reads like: the one that shares the most of its own words with the text, when it shares
 * at least two and more than the chosen template does. Null otherwise (the server still matches the pack when it drafts).
 */
export function suggestPack<P extends PackWords>(text: string, cards: P[], current: string): P | null {
  const said = words(text);
  if (said.length < 3) return null;
  const cur = cards.find((p) => p.key === current);
  const mine = cur ? packScore(cur, said) : 0;
  let best: P | null = null;
  let top = 1;
  for (const p of cards) {
    if (p.key === current) continue;
    const n = packScore(p, said);
    if (n > top && n > mine) {
      best = p;
      top = n;
    }
  }
  return best;
}
