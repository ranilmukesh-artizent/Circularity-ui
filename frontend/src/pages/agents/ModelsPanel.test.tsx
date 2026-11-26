// @vitest-environment jsdom
// Plan 9, P9-3.10 (TF-15): the Models panel lists a remaining-life candidate with its error, concordance and median hours.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { ModelVersion } from '../../api/agents';
import { ModelNote } from './ModelsPanel';
import { medianLines, qualityLine, skippedLines } from './ratedLife';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const model = (over: Partial<ModelVersion> = {}): ModelVersion => ({
  id: 'MV-007', template: 'tool_fleet', kind: 'rated_life', status: 'candidate', created_by: 'planner-a', approved_by: null,
  created_at: '2026-10-07T09:00:00Z', proposal: null, blocks: { propose: null, promote: null },
  factors: [
    { cls: 'CMH', name: 'Motor armature', shape: 3.1, scale: 1230, median_hours: 1089.6 },
    { cls: 'CMH', name: 'Gearbox', shape: 2.4, scale: 1700, median_hours: 1480 },
  ],
  metrics: {
    n: 180, active_id: null, mae_active: null, mae_candidate: 142.4, mae: 142.4, concordance: 0.612,
    by_class: { CMH: { skipped: [{ name: 'Chuck', n: 12, reason: 'Needs at least 30 verdicts; it keeps its current rating.' }] } },
  },
  ...over,
});

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));

describe('a remaining-life candidate', () => {
  it('says the median hours per component, the error and the concordance', () => {
    expect(medianLines(model())).toEqual(['CMH · Motor armature: median 1,090 h', 'CMH · Gearbox: median 1,480 h']);
    expect(qualityLine(model())).toBe('MAE 142 h, concordance 0.61');
    expect(qualityLine(model({ metrics: { n: 5, active_id: null, mae_active: null, mae_candidate: null } }))).toBe('MAE —, concordance —');
  });

  it('says why a component keeps its rating', () => {
    expect(skippedLines(model())).toEqual(['CMH · Chuck: Needs at least 30 verdicts; it keeps its current rating.']);
  });

  it('renders a rated-life row note with the medians and the skipped component', () => {
    act(() => root.render(<ModelNote m={model()} />));
    const t = host.querySelector('[data-testid="rated-life-note"]')?.textContent ?? '';
    expect(t).toContain('Motor armature: median 1,090 h');
    expect(t).toContain('Chuck: Needs at least 30 verdicts');
  });

  it('keeps the factor line for a price calibration', () => {
    act(() => root.render(<ModelNote m={model({ kind: 'calibration', template: 'industrial', factors: [{ route: 'resell', cls: 'Motor', factor: 0.8 }] })} />));
    expect(host.textContent).toBe('resell · Motor ×0.80');
  });
});
