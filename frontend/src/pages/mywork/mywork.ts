/** My work's pure helpers (plan 9, P9-1.7): ordering, counts per kind and the due badge. */
import type { WorkItem, WorkKind } from '../../api/mywork';

export const KIND_LABEL: Record<WorkKind, string> = {
  exception: 'Exceptions',
  approval: 'Approvals',
  needs_info: 'Questions',
  proposal: 'Proposals',
  conflict: 'Conflicts',
  task: 'Tasks',
};
export const KINDS = Object.keys(KIND_LABEL) as WorkKind[];

/** By priority (lower first), then due time (earlier first, none last). The input is not changed. */
export function sortItems(items: WorkItem[]): WorkItem[] {
  return [...items].sort((a, b) => a.priority - b.priority || (a.due ?? '9999').localeCompare(b.due ?? '9999'));
}

/** How many items of each kind; every kind is present. */
export function countsByKind(items: WorkItem[]): Record<WorkKind, number> {
  const out = Object.fromEntries(KINDS.map((k) => [k, 0])) as Record<WorkKind, number>;
  for (const i of items) out[i.kind] += 1;
  return out;
}

/** The conflict rows apart from the rest (UI audit gap 20): one group row stands for them so approvals, proposals and
 *  questions come first. Nothing is dropped; the order of both lists is the input's. */
export function groupConflicts(items: WorkItem[]): { rows: WorkItem[]; conflicts: WorkItem[] } {
  return { rows: items.filter((i) => i.kind !== 'conflict'), conflicts: items.filter((i) => i.kind === 'conflict') };
}

/** "154 data conflicts" / "1 data conflict". */
export const conflictGroupTitle = (n: number): string => `${n} data conflict${n === 1 ? '' : 's'}`;

/** "Due 2026-10-08 09:00 UTC", "Overdue since …", or '' without a due time. */
export function dueLabel(i: WorkItem): string {
  if (!i.due) return '';
  const at = new Date(i.due).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
  return (i.overdue ? 'Overdue since ' : 'Due ') + at;
}

/** The number in a work item's id (w:12), or null for a row that is not a work item. */
export function workId(i: WorkItem): number | null {
  return i.id.startsWith('w:') ? Number(i.id.slice(2)) : null;
}

/** The proposal's number (p:7), or null. */
export function proposalId(i: WorkItem): number | null {
  return i.id.startsWith('p:') ? Number(i.id.slice(2)) : null;
}

const NON_RETURN = 'Non-return fee ';

/** P9-3.18: the contract line of a `non_return` exception ("Non-return fee FL-30128-04"), or null for any other row. */
export function nonReturnLine(i: WorkItem): string | null {
  return i.kind === 'exception' && i.id.startsWith('w:') && i.title.startsWith(NON_RETURN) ? i.title.slice(NON_RETURN.length).trim() || null : null;
}

const LABEL_WORD: Record<string, string> = { ref: 'reference', id: 'ID', qty: 'quantity', no: 'number' };

/** A title or cause with its snake_case field names read as words ("work_order_ref" shows as "work order reference").
 *  Ids such as "RT-1073" and "MTR-1108" have no underscore, so they stay as they are. */
export function readable(text: string): string {
  return text.replace(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g, (m) =>
    m.split('_').map((w, k, all) => (k === all.length - 1 && LABEL_WORD[w]) || w).join(' '),
  );
}

/** The text when it says something; '' for a lone dot or other punctuation the backend leaves behind. */
export function meaningful(text: string | null | undefined): string {
  return text && /[\p{L}\p{N}]/u.test(text) ? text : '';
}

/** Who can do it: what only this person can decide first (approvals, then the agents' proposals held for them, then
 *  questions put to them), then exceptions and steps, and the data conflicts last (F20). */
const RANK: Record<WorkKind, number> = { approval: 0, proposal: 1, needs_info: 2, exception: 3, task: 4, conflict: 5 };

/** By who can do it (RANK), then priority, then due time. The input is not changed. */
export function sortForPerson(items: WorkItem[]): WorkItem[] {
  return [...items].sort((a, b) => RANK[a.kind] - RANK[b.kind] || a.priority - b.priority || (a.due ?? '9999').localeCompare(b.due ?? '9999'));
}

/** The summary row for a pile of conflicts, "154 data conflicts hold decisions". */
export function conflictSummary(n: number): string {
  return `${n} data ${n === 1 ? 'conflict holds a decision' : 'conflicts hold decisions'}`;
}

/** How many rows My work draws at first, and how many each "Show more" adds (the list holds hundreds). */
export const PAGE = 50;
