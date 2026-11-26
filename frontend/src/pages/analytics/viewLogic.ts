/** Saved analytics views (plan 9, P9-9.19, UC-20): the small pure helpers of the Saved views panel. Which views exist, who owns
 *  them and what an alert may watch come from the server (`view.list`); nothing here decides access. */
import type { AlertOp, SavedView, ViewAlert } from '../../api/analytics';

export const OPS: { op: AlertOp; label: string }[] = [
  { op: '>', label: 'is above' }, { op: '>=', label: 'is at least' }, { op: '<', label: 'is below' }, { op: '<=', label: 'is at most' },
];

/** The measure as words: `days_in_stock` is "days in stock". */
export const measureLabel = (m: string): string => m.replace(/_/g, ' ');

/** The alert as one line, "Alert when days in stock is above 45", or "No alert". */
export function alertText(a: ViewAlert | null): string {
  if (!a) return 'No alert';
  const op = OPS.find((o) => o.op === a.op)?.label ?? a.op;
  return `Alert when ${measureLabel(a.measure)} ${op} ${a.threshold}`;
}

/** A threshold typed in a field: a finite number, else null (blank, "abc", "1e999"). */
export function parseThreshold(text: string): number | null {
  if (text.trim() === '') return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}

/** The views of a pack, the account's own first (then by name). */
export function viewsOfPack(views: SavedView[], pack: string): SavedView[] {
  return views.filter((v) => v.pack === pack).sort((a, b) => Number(b.mine) - Number(a.mine) || a.name.localeCompare(b.name));
}

/** Who the view is for, one line: "Yours", "Shared by planner-a" and, when shared on, the roles. */
export function audienceText(v: Pick<SavedView, 'mine' | 'owner' | 'shared_with_roles'>): string {
  const roles = v.shared_with_roles.length ? `shared with ${v.shared_with_roles.join(', ')}` : 'not shared';
  return v.mine ? `Yours, ${roles}` : `Shared by ${v.owner}`;
}

/** The roles after a box is ticked or cleared, in the order of `all`. */
export function toggleRole(current: string[], role: string, on: boolean, all: string[]): string[] {
  const next = new Set(current);
  if (on) next.add(role);
  else next.delete(role);
  return all.filter((r) => next.has(r));
}
