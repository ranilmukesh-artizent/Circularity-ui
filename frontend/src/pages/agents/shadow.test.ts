import { describe, expect, it } from 'vitest';
import type { ModelVersion } from '../../api/agents';
import { shadowLine } from './shadow';

const model = (shadow?: NonNullable<ModelVersion['metrics']['shadow']>): ModelVersion =>
  ({ id: 'MV-007', kind: 'price', metrics: { n: 400, active_id: null, mae_active: null, mae_candidate: null, shadow } }) as ModelVersion;

describe('the price model shadow line (plan 9, P9-6.18, DV-14)', () => {
  it('writes the count, the error and the active error', () => {
    const m = model({ n: 18, min: 30, settled: 6, mae: 14.2, mae_active: 17.4, coverage: null, coverage_active: null });
    expect(shadowLine(m)).toBe('Shadow: 18 of 30 evaluations · MAE $14 (active $17)');
  });

  it('adds the coverage when the shadowed devices sold', () => {
    const m = model({ n: 18, min: 30, settled: 6, mae: 14.2, mae_active: 17.4, coverage: 0.81, coverage_active: 0.76 });
    expect(shadowLine(m)).toBe('Shadow: 18 of 30 evaluations · MAE $14 (active $17) · coverage 81% (active 76%)');
  });

  it('says nothing has settled yet', () => {
    const m = model({ n: 4, min: 30, settled: 0, mae: null, mae_active: null, coverage: null, coverage_active: null });
    expect(shadowLine(m)).toBe('Shadow: 4 of 30 evaluations · no shadowed device has sold yet');
  });

  it('is empty for a model with no shadow', () => {
    expect(shadowLine(model())).toBe('');
  });
});
