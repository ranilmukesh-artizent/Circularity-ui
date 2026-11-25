import { describe, expect, it } from 'vitest';
import type { RepairAccuracy } from '../../api/agents';
import { accuracyRow, barText } from './repairAccuracy';

const row = (over: Partial<RepairAccuracy> = {}): RepairAccuracy => ({
  org_unit_id: 'tool-fleet-a', model_class: 'CRH', as_of: '2026-10-07', n: 42, mae: 31.2, mae_share: 0.09, coverage: 0.81, auto_share: 0.9, instant: true, ...over,
});

describe('the repair estimate accuracy table (plan 9, P9-4.5, SD-08)', () => {
  it('writes a family as one line', () => {
    expect(accuracyRow(row())).toBe('CRH · 42 held out · MAE $31 · 81% inside the range · instant on');
  });

  it('says instant is off for a family under the bar', () => {
    expect(accuracyRow(row({ coverage: 0.55, instant: false }))).toBe('CRH · 42 held out · MAE $31 · 55% inside the range · instant off');
  });

  it('writes the bar', () => {
    expect(barText({ min_coverage: 0.7, max_mae_share: 0.15, holdout_weeks: 8 })).toBe(
      'Instant pricing needs 70% of actuals inside the range and an error of at most 15% of the typical repair, over the last 8 weeks.',
    );
  });
});
