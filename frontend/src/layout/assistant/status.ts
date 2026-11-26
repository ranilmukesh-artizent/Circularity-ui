/**
 * The status line of a turn (plan 10, 2.4): action word + specific item + limit, present tense while running and past
 * tense when done. Pure: numbers come only from the event or its result, never invented; an unknown tool gets the
 * generic "Reading <tool> · read-only".
 */
import type { Status } from './types';

export interface StatusEvent {
  /** Ask tool name (get_case, list_cases, ...), an action or read id (flow.propose, compose.start ...), or ask.fallback */
  name: string;
  phase: 'running' | 'done' | 'refused' | 'failed';
  args?: Record<string, unknown>;
  result?: Record<string, unknown>;
  message?: string | null;
}

/** What the line may name beyond the event: the flow in view, the org, the pack's guardrail count. */
export interface StatusCtx { flowName?: string; org?: string; guardrails?: number }

const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);
const str = (v: unknown): string | undefined => (typeof v === 'string' && v ? v : undefined);
const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`;

function working(verb: string, item: string, limit?: string): Status {
  return { verb, item, limit, state: 'working' };
}
function done(verb: string, item: string, limit?: string): Status {
  return { verb, item, limit, state: 'done' };
}

/** The rules' fallback names the action behind a tool (backend/di/services/ask/tools.py ACTION_TOOLS). */
const ALIAS: Record<string, string> = { 'cases.list': 'list_cases', 'case.get': 'get_case', 'device.question': 'device_question' };

/** What a refused or failed lookup was about, for "Could not read <this>". */
function subject(e: StatusEvent): string {
  return str(e.args?.case_id) ?? str(e.args?.workflow_id) ?? str(e.args?.id) ?? e.name.replace(/_/g, ' ');
}

export function statusLine(e: StatusEvent, ctx: StatusCtx = {}): Status {
  const a = e.args ?? {}, r = e.result ?? {};
  if (e.phase === 'refused') return { verb: 'Could not read', item: subject(e), limit: e.message ?? 'outside what your role may see', state: 'blocked' };
  if (e.phase === 'failed') return { verb: 'Could not finish', item: e.name.replace(/_/g, ' '), limit: e.message ?? undefined, state: 'failed' };
  const run = e.phase === 'running';
  const flow = ctx.flowName ?? 'the draft';
  switch (ALIAS[e.name] ?? e.name) {
    case 'get_case': {
      const c = str(a.case_id) ?? 'the case';
      if (run) return working('Reading', `${c} and its evidence`, 'read-only');
      const n = num(r.evidence);
      return done('Read', n === undefined ? c : `${c} and ${plural(n, 'evidence record')}`);
    }
    case 'list_cases': {
      if (run) return working('Searching', 'open cases you may see', 'read-only');
      const n = num(r.count);
      return done('Searched', n === undefined ? 'open cases' : `${n} open cases`);
    }
    case 'device_question': {
      const q = str(a.question) ?? str(a.question_id)?.replace(/_/g, ' ');
      if (run) return working('Answering', `${q ? `"${q}"` : 'the question'} from device records`, 'read-only');
      const n = num(r.count);
      return done('Answered', n === undefined ? 'from device records' : `from ${n} device records`);
    }
    case 'ask.fallback':
      return done('Answered', 'by the rules', `because ${str(r.reason) ?? 'the model was unavailable'}`);
    case 'flow.propose': {
      const g = ctx.guardrails;
      if (run) return working('Checking', `the sentence against ${g === undefined ? 'the' : g} guardrails`, 'nothing saved');
      const n = num(r.rules);
      return done('Checked', `against ${g === undefined ? 'the' : g} guardrails`, n === undefined ? undefined : `${plural(n, 'rule')} proposed`);
    }
    case 'flow.simulate': {
      const n = num(r.cases);
      if (run) return working('Simulating', `${flow}${n === undefined ? '' : ` on ${n} open cases`}`, 'nothing saved');
      return done('Simulated', n === undefined ? `${flow}` : `on ${n} open cases`);
    }
    case 'flow.saveDraft': {
      const rule = str(a.rule);
      if (run) return working('Saving', `${rule ? rule + ' to ' : ''}${flow}`, 'not published');
      return done('Saved', `to ${flow}`);
    }
    case 'compose.start': {
      const w = num(a.words);
      if (run) return working('Reading', `${w === undefined ? 'the description' : plural(w, 'word')} for ${ctx.org ?? 'your workspace'}`, 'drafts only');
      const p = str(r.pack);
      return done('Read', w === undefined ? 'the description' : plural(w, 'word'), p ? `matched ${p}` : undefined);
    }
    case 'compose.answer': {
      if (run) return working('Drafting', 'changes from your answer', 'drafts only');
      const n = num(r.changes), s = num(r.assumed);
      return done('Drafted', n === undefined ? 'changes' : plural(n, 'change') + (s ? `, ${s} assumed` : ''));
    }
    case 'proposal.accept': {
      const t = str(a.title), c = str(a.case_id);
      if (run) return working('Running', `${t ? `"${t}"` : 'the held action'}${c ? ` for ${c}` : ''} as you`);
      return done('Ran', 'as you', 'see History');
    }
    default:
      return run ? working('Reading', e.name, 'read-only') : done('Read', e.name);
  }
}

/** One line of text: "Verb item · limit", ending in an ellipsis while it is running. */
export function statusText(s: Status): string {
  const item = s.item ? ' ' + s.item : '';
  // a refusal gives its reason after a colon, the rules' fallback after a comma, every other limit after a dot
  const sep = s.state === 'blocked' ? ': ' : s.item === 'by the rules' ? ', ' : ' · ';
  return `${s.verb}${item}${s.limit ? sep + s.limit : ''}${s.state === 'working' ? '…' : ''}`;
}
