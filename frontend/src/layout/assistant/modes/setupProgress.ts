/**
 * What a Set up turn says while a draft is made and after it (plan 11, C2 and C3). Pure.
 * The server reports no stages, so the stages here follow elapsed time and claim no more than is known: the person sees that the
 * description is being read, matched and drafted, and after a while that a slow model is the likely reason for the wait.
 */
import type { Status } from '../types';

export type DraftSource = 'stored' | 'model' | 'rules';

/** After this long a live draft is called slow, with the reason it may be. */
export const SLOW_MS = 25_000;

const STAGES: ReadonlyArray<readonly [number, string]> = [
  [0, 'your description'],
  [2_000, 'it against the template'],
  [5_000, 'the changes'],
];
const VERBS = ['Reading', 'Matching', 'Drafting'] as const;

/** The working status for a live draft after `elapsedMs`: Reading, Matching, Drafting, then Still drafting. */
export function progressStatus(elapsedMs: number, words: number, org: string): Status {
  if (elapsedMs >= SLOW_MS) {
    return { verb: 'Still drafting', item: 'the changes', limit: 'free-tier models can take up to a minute', state: 'working' };
  }
  let k = 0;
  STAGES.forEach(([from], i) => {
    if (elapsedMs >= from) k = i;
  });
  const item = k === 0 ? `${words} word${words === 1 ? '' : 's'} for ${org}` : STAGES[k][1];
  return { verb: VERBS[k], item, limit: 'drafts only', state: 'working' };
}

/** The server's sample-prompt comparison (compose.py `normalise_prompt`): trimmed, whitespace collapsed, case ignored. */
export const normalisePrompt = (t: string): string => t.trim().split(/\s+/).join(' ').toLowerCase();

/** The text is one of the pack's sample prompts: its stored draft (if any) needs no model, and no model is asked which pack fits. */
export const isSamplePrompt = (text: string, prompts: readonly string[]): boolean => {
  const n = normalisePrompt(text);
  return n !== '' && prompts.some((p) => normalisePrompt(p) === n);
};

/** Where a composition's draft came from: `steps.describe.draft_source`, else the reading's own flag (older compositions). */
export function draftSource(source: unknown, byModel: boolean): DraftSource {
  return source === 'stored' || source === 'model' || source === 'rules' ? source : byModel ? 'model' : 'rules';
}

/** The line where a live draft says which kind of answer it is. */
export function sourceLine(s: DraftSource): string {
  if (s === 'stored') return 'Used the stored draft for this sample';
  return s === 'model' ? "Drafted by a language model, checked by the pack's rules" : 'Read by the rules';
}

/** When no model answered: one plain sentence and what to do. */
export const NO_MODEL = 'No language model answered this time, so only the rules read your description.';
export const NO_MODEL_NEXT = 'Try again in a minute, or use the template as it is.';

/** The Set up page's own start: a fresh composition from the template, with nothing described. */
export const templateHref = (pack: string, org: string): string => `#/setup?new=1&pack=${encodeURIComponent(pack)}&org=${encodeURIComponent(org)}`;

const BUSY = /\b429\b|rate.?limit|too many requests|quota|overloaded|unavailable/i;

/** A failed start in plain words: no status code or provider text; a busy or rate-limited model gets the one sentence. */
export function plainFailure(message: string, code?: string): string {
  if (code === 'network') return 'Could not reach Circularity. Your text is kept.';
  if (BUSY.test(message)) return `${NO_MODEL} ${NO_MODEL_NEXT}`;
  return message;
}
