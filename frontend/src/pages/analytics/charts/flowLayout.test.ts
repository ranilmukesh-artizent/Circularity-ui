import { describe, expect, it } from 'vitest';
import { flowGraph } from './chartData';
import { layoutFlow } from './flowLayout';
import { LABELS, sample } from './testRows';

describe('flow layout (@visx/sankey)', () => {
  const g = flowGraph(sample(), LABELS);
  const lay = layoutFlow(g, 900, 320, 160, 190);
  it('puts the three columns left to right inside the room left for labels', () => {
    const x = (c: number) => lay.nodes.find((n) => n.col === c)!.x0;
    expect(x(0)).toBeGreaterThanOrEqual(160);
    expect(x(0)).toBeLessThan(x(1));
    expect(x(1)).toBeLessThan(x(2));
    expect(Math.max(...lay.nodes.map((n) => n.x1))).toBeLessThanOrEqual(900 - 190 + 0.5);
  });
  it('sizes a band by its count and a block by what passes through it', () => {
    const big = lay.links.find((k) => k.key === 'cls:pump>route:redeploy')!, small = lay.links.find((k) => k.key === 'cls:motor>route:resale')!;
    expect(big.n).toBe(8);
    expect(small.n).toBe(6);
    expect(big.width).toBeGreaterThan(small.width);
    const block = lay.nodes.find((n) => n.id === 'route:redeploy')!;
    expect(block.y1 - block.y0).toBeGreaterThan(0);
    expect(big.path.startsWith('M')).toBe(true);
  });
  it('keeps columns in the order the data asked for', () => {
    const ys = lay.nodes.filter((n) => n.col === 2).sort((a, b) => a.y0 - b.y0).map((n) => n.ref);
    expect(ys).toEqual(['reconciled', 'pending', 'cancelled']);
  });
  it('draws nothing for nothing', () => {
    expect(layoutFlow(flowGraph([], LABELS), 900, 300, 100, 100).nodes).toEqual([]);
  });
});
