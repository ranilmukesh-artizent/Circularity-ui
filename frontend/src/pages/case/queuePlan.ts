/** The "Queue plan" lines of a tool-fleet case (P9-1.4): the named order its return holds, and the orders it lost to another return. */
import type { QueuePlan } from '../../api/case';
import { money } from '../../api/format';

const named = (plan: QueuePlan, order: string): string => `${plan.kinds[order] ?? 'order'} ${order}`;
const upper = (t: string): string => t.charAt(0).toUpperCase() + t.slice(1);

/**
 * "Holds lease renewal LS-201." for the order the plan gives this return, then one line per lost order:
 * "Lease renewal LS-201 goes to RT-1002: it gains $340 more from it." No holds and nothing lost gives no lines.
 */
export function planLines(plan: QueuePlan | null | undefined): string[] {
  if (!plan) return [];
  const out: string[] = [];
  if (plan.holds) out.push(`Holds ${named(plan, plan.holds)}.`);
  for (const x of plan.lost) out.push(`${upper(named(plan, x.order))} goes to ${x.to}: it gains ${money(x.gain)} more from it.`);
  return out;
}
