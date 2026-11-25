import type { RepairAccuracy, RepairAccuracyBar } from '../../api/agents';
import { money } from '../../api/format';

const pct = (x: number) => `${Math.round(x * 100)}%`;

/** One family of the repair estimate accuracy table as a sentence (plan 9, P9-4.5): "CRH · 42 held out · MAE $31 · 81% inside the range · instant on". */
export const accuracyRow = (r: RepairAccuracy): string =>
  `${r.model_class} · ${r.n} held out · MAE ${money(r.mae)} · ${pct(r.coverage)} inside the range · instant ${r.instant ? 'on' : 'off'}`;

/** The bar a family must clear to be priced without a technician. */
export const barText = (b: RepairAccuracyBar): string =>
  `Instant pricing needs ${pct(b.min_coverage)} of actuals inside the range and an error of at most ${pct(b.max_mae_share)} of the typical repair, over the last ${b.holdout_weeks} weeks.`;
