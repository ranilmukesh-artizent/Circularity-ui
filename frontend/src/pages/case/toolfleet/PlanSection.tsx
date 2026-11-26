import type { PlanView } from '../../../api/toolFleet';
import { money } from '../../../api/format';

/** "lease renewal FC-30117-R", "sales order SO-1": an order with its short kind when the plan names one. */
export const orderText = (id: string, kinds: Record<string, string>): string => (kinds[id] ? `${kinds[id]} ${id}` : id);

/** The org's open tool returns planned together (plan 9, P9-3.13, TF-08): the order this return takes or the reason it lost one, the orders it competes for and what the plan adds over first come, first served. */
export function PlanSection({ plan }: { plan: PlanView | null | undefined }) {
  if (!plan || (!plan.headline && !plan.contested.length)) return null;
  return (
    <div style={{ marginTop: 8 }} data-testid="tf-plan">
      {plan.headline && (
        <p style={{ margin: '0 0 4px' }} data-testid="tf-plan-headline">
          <strong>{plan.headline}</strong>
        </p>
      )}
      {plan.contested.length > 0 && (
        <p style={{ margin: '0 0 4px' }} data-testid="tf-plan-contested">
          Contested orders: {plan.contested.map((o) => orderText(o, plan.kinds)).join(', ')}
        </p>
      )}
      {plan.lost.map((x) => (
        <p key={x.order} className="muted" style={{ margin: '0 0 4px' }} data-testid="tf-plan-lost">
          {x.order} goes to {x.to}, which gains {money(x.gain)} more from it.
        </p>
      ))}
      <p className="muted" style={{ margin: 0 }} data-testid="tf-plan-gain">
        The queue plan adds {money(plan.gain)} over first come, first served ({money(plan.total)} against {money(plan.fcfs)}).
      </p>
    </div>
  );
}
