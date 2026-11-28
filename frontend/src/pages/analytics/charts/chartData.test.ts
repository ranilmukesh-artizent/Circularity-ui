import { describe, expect, it } from 'vitest';
import { flowGraph, flowSummary, heatData, heatSummary, litPath, MIN_CELL, niceTicks, spreadLabels, tint, trendData } from './chartData';
import { LABELS, row, sample } from './testRows';

describe('heat: typical gain per case, route by class', () => {
  const h = heatData(sample(), LABELS);
  it('uses the median of reconciled cases and a dash under five', () => {
    expect(h.cells.find((c) => c.route === 'redeploy' && c.cls === 'pump')).toMatchObject({ n: 6, median: 10 });
    expect(h.cells.find((c) => c.route === 'resale' && c.cls === 'motor')).toMatchObject({ n: 5, median: -20 });
    expect(heatData([row(), row(), row(), row()], LABELS).cells[0].median).toBeNull();
    expect(MIN_CELL).toBe(5);
  });
  it('has a total per route, per class and overall, from the same rows', () => {
    expect(h.byRoute.map((c) => c.n)).toEqual([6, 5]);
    expect(h.all.n).toBe(11);
    expect(h.all.median).toBe(10);
  });
  it('leaves out routes and classes with no reconciled case, and names the best and worst cell', () => {
    expect(h.routes.map((r) => r.id)).toEqual(['redeploy', 'resale']);
    expect(heatSummary(h)).toContain('Highest typical gain: Redeploy on Pump');
    expect(tint(-20, 20)).toBe(1);
    expect(tint(null, 20)).toBe(0);
  });
});

describe('trend', () => {
  it('adds the monthly uplift into a running total from the first month with data', () => {
    const t = trendData(sample(), LABELS);
    expect(t.map((m) => m.label)).toEqual(['Jan', 'Feb', 'Mar']);
    expect(t.map((m) => m.uplift)).toEqual([60, -80, -20]);
    expect(t.map((m) => m.cumulative)).toEqual([60, -20, -40]);
    expect(t[0].net).toBe(660);
    expect(trendData([], LABELS)).toEqual([]);
  });
});

describe('flow', () => {
  const g = flowGraph(sample(), LABELS);
  it('keeps every decision on its way through: what goes into a route comes out of it', () => {
    expect(g.total).toBe(14);
    for (const n of g.nodes.filter((x) => x.kind === 'route')) {
      const inn = g.links.filter((k) => k.target === n.id).reduce((s, k) => s + k.n, 0);
      const out = g.links.filter((k) => k.source === n.id).reduce((s, k) => s + k.n, 0);
      expect(inn).toBe(n.n);
      expect(out).toBe(n.n);
    }
    expect(g.nodes.filter((x) => x.kind === 'out').reduce((s, x) => s + x.n, 0)).toBe(14);
  });
  it('orders classes by size, outcomes reconciled first, and carries the net recovered', () => {
    expect(g.nodes.filter((x) => x.col === 0).map((x) => x.ref)).toEqual(['pump', 'motor']);
    expect(g.nodes.filter((x) => x.col === 2).map((x) => x.ref)).toEqual(['reconciled', 'pending', 'cancelled']);
    expect(g.nodes.find((x) => x.id === 'out:reconciled')!.net).toBe(6 * 110 + 5 * 80);
  });
  it('says the finding in one sentence', () => {
    expect(flowSummary(g)).toMatch(/^Redeploy takes \d+% of 14 decisions/);
    expect(flowSummary(flowGraph([], LABELS))).toBe('No decisions in this selection.');
  });
  it('lights a part and what it touches', () => {
    const lit = litPath(g, { kind: 'node', id: 'route:resale' })!;
    expect(lit.nodes.has('cls:motor')).toBe(true);
    expect(lit.nodes.has('route:redeploy')).toBe(false);
    expect(litPath(g, null)).toBeNull();
    const k = litPath(g, { kind: 'link', id: 'cls:motor>route:resale' })!;
    expect([...k.links].some((x) => x.startsWith('route:resale>'))).toBe(true);
  });
});

describe('helpers', () => {
  it('spreads labels apart without reordering them', () => {
    const out = spreadLabels([10, 12, 14, 200], 30, 0, 300);
    expect(out[1] - out[0]).toBeGreaterThanOrEqual(30);
    expect(out[2] - out[1]).toBeGreaterThanOrEqual(30);
    expect(out[3]).toBe(200);
    expect(spreadLabels([290, 295], 30, 0, 300).every((y) => y <= 300)).toBe(true);
  });
  it('picks round ticks', () => {
    expect(niceTicks(0, 1000, 4)).toEqual([0, 250, 500, 750, 1000]);
    expect(niceTicks(-50, 100, 3)[0]).toBeLessThanOrEqual(0);
  });
});
