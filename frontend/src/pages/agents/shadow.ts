import type { ModelVersion } from '../../api/agents';
import { money } from '../../api/format';

const pct = (v: number) => `${Math.round(v * 100)}%`;

/**
 * A price candidate's shadow (plan 9, P9-6.18, DV-14): the evaluations it was shadowed on out of those a promotion needs, and its
 * error and coverage against the active model's on the shadowed devices that sold. Empty for a model without a shadow.
 * "Shadow: 18 of 30 evaluations · MAE $14 (active $17) · coverage 81% (active 76%)"
 */
export function shadowLine(m: ModelVersion): string {
  const x = m.metrics.shadow;
  if (!x) return '';
  const head = `Shadow: ${x.n} of ${x.min} evaluations`;
  if (x.mae == null) return `${head} · no shadowed device has sold yet`;
  const mae = ` · MAE ${money(x.mae)} (active ${x.mae_active == null ? '—' : money(x.mae_active)})`;
  const cov = x.coverage == null ? '' : ` · coverage ${pct(x.coverage)} (active ${x.coverage_active == null ? '—' : pct(x.coverage_active)})`;
  return head + mae + cov;
}
