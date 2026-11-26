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
