/**
 * The hint under the composer (plan 10, 2.1): a sentence typed in the wrong mode is offered the other one. A plain
 * word check, never a model; the person decides.
 */
import type { AssistantMode } from './types';

const QUESTION_START = /^(what|why|how|which|who|when|does|is|can)\b/i;
const CHANGE_START = /^(never|always|only|require|prefer|exclude|send|route|block)\b/i;

export const looksLikeQuestion = (text: string): boolean => {
  const t = text.trim();
  return t.length > 0 && (t.endsWith('?') || QUESTION_START.test(t));
};

export const looksLikeChange = (text: string): boolean => CHANGE_START.test(text.trim());

/** The mode to offer instead, or null when the text fits the mode it is typed in. */
export function modeHint(mode: AssistantMode, text: string): { to: AssistantMode; text: string; action: string } | null {
  if (mode === 'change' && looksLikeQuestion(text)) return { to: 'ask', text: 'This reads like a question.', action: 'Ask it instead' };
  if (mode === 'ask' && looksLikeChange(text) && !looksLikeQuestion(text)) return { to: 'change', text: 'This reads like a change to the flow.', action: 'Propose it instead' };
  return null;
}
