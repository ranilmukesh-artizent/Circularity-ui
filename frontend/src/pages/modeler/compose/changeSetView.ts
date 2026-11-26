/* Pure helpers for showing a composition's drafted change set (plan 10, T3): each typed operation as one plain sentence, the
   assumed count, the blocked lines, the match line and the link to the Set up tab. Shared by the Set up mode of the assistant and
   the Describe step's review. No React, no calls. */
import type { ChangeSet, DraftRule, OverlayOpRef, PackMatch } from '../../../api/compose';
import type { GuardrailStage, OverlayCond } from '../../../api/types';
import { STAGE_LABEL } from '../overlay';

const num = (n: unknown): string => (typeof n === 'number' ? n.toLocaleString('en-US') : String(n));
const stage = (s: unknown): string => STAGE_LABEL[s as GuardrailStage] ?? String(s);

const CMP: Record<OverlayCond['op'], string> = { eq: 'is', ne: 'is not', in: 'is one of', gte: 'is at least', lte: 'is at most', exists: 'is present' };

const cond = (c: OverlayCond): string => (c.op === 'exists' ? `${c.fact} ${CMP.exists}` : `${c.fact} ${CMP[c.op]} ${JSON.stringify(c.value)}`);
const when = (w: unknown): string => {
  const list = Array.isArray(w) ? (w as OverlayCond[]) : [];
  return list.length ? `, when ${list.map(cond).join(' and ')}` : '';
};

/** One typed operation as a plain sentence (never JSON). An operation kind this build does not know is named, not dumped. */
export function opSentence(o: OverlayOpRef): string {
  const f = o as Record<string, unknown>;
  switch (o.op) {
    case 'tighten':
      return `Tighten ${f.target}: ${f.field} from ${num(f.seen)} to ${num(f.value)}.`;
    case 'add_approver':
      return `Add ${f.role} as an approver on ${f.target}.`;
    case 'add_step': {
      const owner = f.owner_role ? `, owned by ${f.owner_role}` : '';
      return `Add the step "${f.step}" at ${stage(f.stage)}${owner}${when(f.when)}.`;
    }
    case 'shortcut':
      return `Skip from ${stage(f.stage)} to ${stage(f.to)}${when(f.when)}.`;
    case 'set_param':
      return `Set ${f.path} from ${num(f.seen)} to ${num(f.value)}.`;
    default:
      return `Change: ${String((o as { op: unknown }).op)}.`;
  }
}

/** A business rule the answer adds, as a sentence. */
export const ruleSentence = (r: DraftRule): string => `Rule ${r.id} at stage ${r.stage_no}: ${r.text}.`;

export interface ChangeLine {
  id: string;
  text: string;
  /** the person did not state it (an operation listed in `assumed`, or a rule the pack's default stood in for) */
  assumed: boolean;
}

/** The operations, then the rules, each as a line. */
export function changeLines(cs: ChangeSet): ChangeLine[] {
  return [
    ...cs.ops.map((o) => ({ id: o.id, text: opSentence(o), assumed: cs.assumed.includes(o.id) })),
    ...(cs.rules ?? []).map((r) => ({ id: r.id, text: ruleSentence(r), assumed: r.assumed })),
  ];
}

/** How many lines the person did not state (an id in `assumed` that names no operation is not counted). */
export const assumedCount = (cs: ChangeSet): number => changeLines(cs).filter((l) => l.assumed).length;

/** "Drafted 4 changes, 1 assumed" (2.4 and 2.5 of plan 10). */
export function changeTitle(cs: ChangeSet): string {
  const n = cs.ops.length + (cs.rules?.length ?? 0);
  if (n === 0) return 'Drafted no changes';
  const a = assumedCount(cs);
  return `Drafted ${n} change${n === 1 ? '' : 's'}${a ? `, ${a} assumed` : ''}`;
}

/** The guardrail's refusals, one line each. */
export const blockedLines = (cs: ChangeSet): string[] => cs.blocked.map((b) => `Blocked by ${b.guardrail}: ${b.text}`);

/** The pack line: the score is `config.read`'s; below the bar it is only the nearest pack (amber). */
export function matchLine(m: PackMatch | null, pack?: string): { text: string; amber: boolean } {
  if (!m) return { text: `Matched pack: ${pack ?? 'none'}`, amber: false };
  const score = Math.round(m.score);
  if (m.nearest_only) return { text: `Nearest pack: ${m.key} (${score}). No pack matched well. Check every change.`, amber: true };
  return { text: `Matched pack: ${m.key} (${score})`, amber: false };
}

/** "Read 62 words, 1 explicit control, systems: SAP". */
export function wordCountLine(words: number, controls: number, systems: string[]): string {
  const base = `Read ${words} word${words === 1 ? '' : 's'}, ${controls} explicit control${controls === 1 ? '' : 's'}`;
  return systems.length ? `${base}, systems: ${systems.join(', ')}` : base;
}

/** The Modeler's Set up tab on one composition (a hash-router path); the template and org keep the page on the composition's pack. */
export const setupHref = (id: number, where: { template?: string; org?: string } = {}): string => {
  const q = new URLSearchParams();
  if (where.template) q.set('template', where.template);
  if (where.org) q.set('org', where.org);
  q.set('tab', 'setup');
  q.set('compose', String(id));
  return `/modeler?${q.toString()}`;
};
