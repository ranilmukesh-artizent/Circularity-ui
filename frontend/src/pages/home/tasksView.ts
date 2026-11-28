/* Pure helpers of My Tasks (28 Nov 2026): the filter in the URL, the sentence under the title, a row's kind in one word. */
import type { WorkKind } from '../../api/mywork';

/** What the page shows: everything (null), one kind, the fraud and compliance holds, or what was handed on. */
export type Show = WorkKind | 'fraud' | 'handed' | null;

/** The kinds only this person can do, in the order the page lists them (the data conflicts are a group of their own). */
export const MINE: readonly WorkKind[] = ['approval', 'proposal', 'needs_info', 'task', 'exception'];

const SHOWS = new Set<string>([...MINE, 'conflict', 'fraud', 'handed']);
/** `?show=` as a filter; anything else is the whole list. */
export const parseShow = (v: string | null): Show => (v && SHOWS.has(v) ? (v as Show) : null);

/** "/tasks?show=approval" (a hash-router path without the #); the whole list is "/tasks". */
export const tasksPath = (show: Show): string => '/tasks' + (show ? '?show=' + show : '');

export const KIND_ONE: Record<WorkKind, string> = {
  approval: 'Approval', proposal: 'Proposal', needs_info: 'Question', task: 'Task', exception: 'Exception', conflict: 'Data conflict',
};

const things = (n: number) => (n === 1 ? '1 thing waits' : `${n} things wait`);

/** "12 things wait on you. 3 are late. 4 more wait on others." */
export function summary(mine: number, late: number, handed: number): string {
  const parts = [mine ? `${things(mine)} on you.` : 'Nothing waits on you.'];
  if (late) parts.push(late === 1 ? '1 is late.' : `${late} are late.`);
  if (handed) parts.push(`${handed} more ${handed === 1 ? 'waits' : 'wait'} on others.`);
  return parts.join(' ');
}

/** How long a handed-on step has waited: "today", "1 day", "3 days". */
export function ageText(days: number): string {
  const d = Math.floor(days);
  return d < 1 ? 'today' : d === 1 ? '1 day' : `${d} days`;
}
