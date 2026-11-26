import type { ModelVersion } from '../../api/agents';

/** Plan 9, P9-3.10: what a remaining-life model says, in words. Pure, so the Models panel and its test share it. */

/** "Motor armature: median 1,090 h" for each component the model fitted, per tool class. */
export const medianLines = (m: ModelVersion): string[] =>
  m.factors.filter((f) => f.name).map((f) => `${f.cls} · ${f.name}: median ${Math.round(f.median_hours ?? 0).toLocaleString('en-US')} h`);

/** The components that keep their current rating, with why ("Needs at least 30 verdicts; ..."). */
export const skippedLines = (m: ModelVersion): string[] =>
  Object.entries(m.metrics.by_class ?? {}).flatMap(([cls, c]) => c.skipped.map((s) => `${cls} · ${s.name}: ${s.reason}`));

/** "MAE 142 h, concordance 0.61" (a dash where the last 3 months had too few verdicts to hold out). */
export const qualityLine = (m: ModelVersion): string => {
  const { mae, concordance } = m.metrics;
  return `MAE ${mae == null ? '—' : `${Math.round(mae)} h`}, concordance ${concordance == null ? '—' : concordance.toFixed(2)}`;
};
