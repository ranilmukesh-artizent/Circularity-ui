// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { analysisTitle, formatValue, groupSpec, loadSaved, measureValue, runAnalysis, storeSaved } from './analysisModel';
import { LABELS, sample } from './charts/testRows';
import { emptyState, filterRows } from './data/dataView';

describe('analysis builder', () => {
  it('measures each thing over the rows it is about', () => {
    const rows = sample();
    expect(measureValue('count', rows)).toBe(14);
    expect(measureValue('net', rows)).toBe(6 * 110 + 5 * 80);
    expect(measureValue('uplift', rows)).toBeCloseTo((60 - 100) / 11);
    expect(measureValue('days', rows)).toBe(10);
    expect(measureValue('override', rows)).toBeCloseTo(1 / 11);
    expect(measureValue('net', [])).toBeNull();
  });

  it('breaks one measure down by one thing, best first, and says highest and lowest', () => {
    const r = runAnalysis(sample(), { measure: 'uplift', by: ['route'] }, LABELS);
    expect(r.groups.map((g) => g.label)).toEqual(['Redeploy', 'Resale']);
    expect(r.groups.map((g) => g.value)).toEqual([10, -20]);
    expect(r.summary).toContain('Highest: Redeploy at $10 (6 cases). Lowest: Resale at −$20 (5 cases).');
  });

  it('breaks it down by two things and keeps months in calendar order', () => {
    const r = runAnalysis(sample(), { measure: 'net', by: ['cls', 'month'] }, LABELS);
    expect(r.rowLabels).toEqual(['Pump', 'Motor']);
    expect(r.colLabels).toEqual(['January', 'February', 'March']);
    expect(r.groups.find((g) => g.label === 'Motor, March')).toMatchObject({ value: 80, n: 1 });
    expect(r.groups.find((g) => g.label === 'Pump, March')).toBeUndefined();
  });

  it('opens exactly the rows a bar adds up', () => {
    const a = { measure: 'uplift' as const, by: ['route' as const] };
    const r = runAnalysis(sample(), a, LABELS);
    const g = r.groups.find((x) => x.label === 'Resale')!;
    const spec = groupSpec(a, g);
    expect(filterRows(sample(), spec, emptyState())).toHaveLength(g.n);
    expect(spec.facets.map((f) => f.label)).toEqual(['Status: reconciled', 'Route: Resale']);
    expect(spec.exportable).toBe(false);
  });

  it('counts every status for decisions, and gives one total when nothing is broken down', () => {
    expect(runAnalysis(sample(), { measure: 'count', by: [] }, LABELS).summary).toBe('14 across 14 decisions.');
    expect(runAnalysis([], { measure: 'net', by: ['route'] }, LABELS).summary).toContain('nothing to compare');
  });

  it('titles and formats in plain words', () => {
    expect(analysisTitle({ measure: 'override', by: ['model', 'tenant'] })).toBe('Override rate by model version and tenant');
    expect(formatValue(0.1234, 'pct')).toBe('12.3%');
    expect(formatValue(2.5, 'days')).toBe('2.5 days');
    expect(formatValue(null, 'usd')).toBe('–');
  });
});

describe('saved analyses', () => {
  beforeEach(() => { try { window.localStorage.clear(); } catch { /* none */ } });
  it('keeps them for this browser and survives a damaged store', () => {
    expect(loadSaved()).toEqual([]);
    expect(storeSaved([{ name: 'x', a: { measure: 'net', by: ['route'] } }])).toBe(true);
    expect(loadSaved()).toHaveLength(1);
    window.localStorage.setItem('circ-saved-analyses', '{broken');
    expect(loadSaved()).toEqual([]);
  });
});
