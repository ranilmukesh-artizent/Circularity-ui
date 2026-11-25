/**
 * The AI workflow builder (Workflow Studio's "Build with AI"): a person describes a workflow in words, di-api's
 * workflow.plan reads it and asks the follow-up questions it needs, then proposes a complete, checked plan. The planner
 * is a read: it saves nothing, so it is posted straight to the action endpoint (no cache invalidation per question).
 * Creating the plan is the person's own click: workflow.create with the plan's graph, then workflow.save with its
 * owner, trigger and run settings, both through invoke() with the person's permissions (manageWorkflows).
 *
 * The conversation's state is a small reducer (builderReducer): each round keeps the prompt, the answers given so far
 * and the questions asked, so Back returns to the previous round with its answers, and Edit reopens a slot.
 */
import { invoke } from './actions';
import { ApiError, http } from './client';
import type { ActionResult } from './types';

export interface Choice {
  value: string | number;
  label: string;
  hint: string;
}
export type AnswerValue = string | number | boolean | (string | number)[];
export type Answers = Record<string, AnswerValue>;

export interface Question {
  id: string;
  text: string;
  kind: 'choice' | 'multi' | 'text';
  multi: boolean;
  choices: Choice[];
  default: AnswerValue | null;
  note?: string;
}

export interface PlanStep {
  id: string;
  label: string;
  kind: string;
  fixed: boolean;
  /** fixed: placed by Circularity; required: needed to run; added: the person asked for it. */
  status: 'fixed' | 'added' | 'required';
  why: string;
}

export interface PlanGraph {
  nodes: { id: string; k: string; ref: string; x: number; y: number }[];
  edges: { id: string; a: string; b: string; locked: boolean }[];
}

export interface Plan {
  name: string;
  desc: string;
  type: 'ingest' | 'out' | 'dec' | 'blank';
  type_label: string;
  src: string | null;
  ch: string | null;
  decision: string | null;
  trigger: { t: string; min?: number };
  trigger_text: string;
  owner: string;
  settings: { retries: number; alert: string };
  graph: PlanGraph;
  checks: { errors: string[]; warnings: string[]; notes: string[] };
  steps: PlanStep[];
  /** What the workflow holds: the blocks it needs to run, the ones asked for, and settings changed from their defaults. */
  diff: { required: string[]; added: string[]; changed: string[] };
  summary: string;
  create: Record<string, unknown>;
  save: Record<string, unknown>;
}

export interface Understood {
  slot: string;
  label: string;
  value: string;
  from: 'prompt' | 'answer';
}

export interface PlanReply {
  status: 'questions' | 'ready' | 'blocked';
  questions: Question[];
  notes: string[];
  understood: Understood[];
  answers: Answers;
  plan: Plan | null;
  /** Set for a decision sentence: business rules live in the Modeler (P9-0.16). null for every connection workflow. */
  redirect: { to: 'modeler'; reason: string } | null;
}

/** Example descriptions shown under the prompt box (they plan cleanly against the synthetic systems). */
export const EXAMPLES = [
  'Ingest from Salesforce with currency conversion and de-duplication, every 30 minutes',
  'Build an ingest from Dealer network without currency conversion, with unit normalisation, every 15 minutes',
  'Send approved instructions to SAP S/4HANA by file with a code lookup',
  'Ingest from IBM Maximo in real time with a filter and a branch, alert when two runs fail in a row',
];

/** workflow.plan: the next questions, or the complete plan. Throws ApiError with the server's message on a refusal. */
export async function planWorkflow(prompt: string, answers: Answers = {}): Promise<PlanReply> {
  const r = await http<ActionResult<PlanReply>>('/api/actions/workflow.plan', { method: 'POST', body: { prompt, answers } });
  if (!r.ok) throw new ApiError(400, r.error.code, r.error.message);
  return r.output;
}

export interface AuthorError {
  node: string | null;
  field: string;
  message: string;
}

export interface AuthorReply {
  /** drafted: saved as a draft; questions: the planner needs an answer; handed_over: three repair rounds were not enough. */
  status: 'drafted' | 'questions' | 'handed_over' | 'blocked' | 'redirect';
  graph: PlanGraph | null;
  rounds: number;
  errors: AuthorError[];
  test_run: { status: string; in: number; out: number; held: number; note: string | null } | null;
  draft_id: string | null;
  questions: Question[];
  notes: string[];
  trigger: { t: string; min?: number } | null;
  name: string | null;
  by_model: boolean;
  workflow_id: string | null;
}

/** workflow.author: a checked, test-run draft from the sentence. It saves a draft only; Publish stays the person's button. */
export async function authorWorkflow(prompt: string, answers: Answers = {}): Promise<AuthorReply> {
  const r = await invoke<AuthorReply>('workflow.author', { prompt, answers });
  if (!r.ok) throw new ApiError(400, r.error.code, r.error.message);
  return r.output;
}

export const roundsText = (n: number): string => (n === 0 ? 'Built by the keyword planner' : `Checked in ${n} round${n === 1 ? '' : 's'}`);
export const testRunText = (t: NonNullable<AuthorReply['test_run']>): string => `Test run: in ${t.in} · out ${t.out} · held ${t.held}`;

/** The person's Create workflow: workflow.create with the plan's graph, then workflow.save with its settings. */
export async function createFromPlan(plan: Plan): Promise<ActionResult<{ id: string; name: string }>> {
  const made = await invoke<{ id: string; name: string }>('workflow.create', plan.create);
  if (!made.ok) return made;
  const saved = await invoke<{ id: string; ver: string; name: string }>('workflow.save', { id: made.output.id, ...plan.save });
  if (!saved.ok) return { ok: false, error: { ...saved.error, message: `${made.output.name} was created as a draft, but its settings were not saved: ${saved.error.message}` } };
  return made;
}

// ---------------------------------------------------------------- the conversation's state
export interface Round {
  /** the answers sent for this round */
  sent: Answers;
  reply: PlanReply;
}

export interface BuilderState {
  prompt: string;
  rounds: Round[];
  /** the form's values for the open questions (defaults filled in) */
  form: Answers;
  busy: boolean;
  error: string | null;
}

export type BuilderAction =
  | { t: 'prompt'; prompt: string }
  | { t: 'start' }
  | { t: 'reply'; sent: Answers; reply: PlanReply }
  | { t: 'fail'; message: string }
  | { t: 'set'; id: string; value: AnswerValue }
  | { t: 'back' }
  | { t: 'edit'; slot: string }
  | { t: 'restart' };

export const initialBuilder = (prompt = ''): BuilderState => ({ prompt, rounds: [], form: {}, busy: false, error: null });

/** The form for a round's questions: each question's default, or what the person answered before. */
export function formFor(questions: Question[], before: Answers = {}): Answers {
  const f: Answers = {};
  for (const q of questions) {
    const v = before[q.id] ?? q.default;
    if (v !== null && v !== undefined) f[q.id] = v;
    else if (q.multi) f[q.id] = [];
  }
  return f;
}

/** The answers to send next: everything answered so far plus this round's form. */
export function nextAnswers(s: BuilderState): Answers {
  const last = s.rounds[s.rounds.length - 1];
  return { ...(last ? last.reply.answers : {}), ...s.form };
}

export const current = (s: BuilderState): PlanReply | null => s.rounds[s.rounds.length - 1]?.reply ?? null;

/** Toggle one value of a multi-select answer. */
export function toggled(list: AnswerValue | undefined, value: string | number, on: boolean): (string | number)[] {
  const l = Array.isArray(list) ? list : [];
  return on ? (l.includes(value) ? l : [...l, value]) : l.filter((x) => x !== value);
}

export function builderReducer(s: BuilderState, a: BuilderAction): BuilderState {
  switch (a.t) {
    case 'prompt':
      return { ...s, prompt: a.prompt };
    case 'start':
      return { ...s, busy: true, error: null };
    case 'reply': {
      const prev = s.rounds.length ? s.rounds[s.rounds.length - 1].reply.answers : {};
      return { ...s, busy: false, error: null, rounds: [...s.rounds, { sent: a.sent, reply: a.reply }], form: formFor(a.reply.questions, { ...prev, ...a.sent }) };
    }
    case 'fail':
      return { ...s, busy: false, error: a.message };
    case 'set':
      return { ...s, form: { ...s.form, [a.id]: a.value } };
    case 'back': {
      if (s.rounds.length <= 1) return { ...initialBuilder(s.prompt) };
      const rounds = s.rounds.slice(0, -1);
      const last = rounds[rounds.length - 1];
      // the previous round's questions again, with the answers the person gave them
      return { ...s, rounds, error: null, form: formFor(last.reply.questions, s.rounds[s.rounds.length - 1].sent) };
    }
    case 'edit': {
      // reopen one slot: drop it (and, for the type or the system, what depends on it) and ask again
      const i = s.rounds.findIndex((r) => r.reply.questions.some((q) => q.id === a.slot));
      if (i >= 0) {
        const rounds = s.rounds.slice(0, i + 1);
        return { ...s, rounds, error: null, form: formFor(rounds[i].reply.questions, s.rounds[i + 1]?.sent ?? {}) };
      }
      return s;
    }
    case 'restart':
      return initialBuilder(s.prompt);
  }
}

/** Whether every open question has an answer the planner accepts (text questions may be left to their default). */
export function formComplete(questions: Question[], form: Answers): boolean {
  return questions.every((q) => q.kind === 'text' || q.multi || (form[q.id] !== undefined && form[q.id] !== ''));
}
