import { describe, expect, it } from 'vitest';
import { autoLayout, placeMissing } from './layout';

const W = 176, H = 62;
/** The default ingest graph's 9 steps: a chain with a fork to an error handler. */
const ids = ['conn', 'canon', 'map', 'val', 'xf', 'snap', 'dec', 'send', 'err'];
const nodes = ids.map((id) => ({ id, w: W, h: H }));
const edges = [['conn', 'canon'], ['canon', 'map'], ['map', 'val'], ['val', 'xf'], ['xf', 'snap'], ['snap', 'dec'], ['dec', 'send'], ['val', 'err']].map(([a, b]) => ({ a, b }));

const overlap = (p: { x: number; y: number }, q: { x: number; y: number }) => Math.abs(p.x - q.x) < W && Math.abs(p.y - q.y) < H;

describe('autoLayout (P9-8.13)', () => {
  it('gives the 9 ingest nodes positions with no overlap', () => {
    const pos = autoLayout(nodes, edges);
    expect(Object.keys(pos).sort()).toEqual([...ids].sort());
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) expect(overlap(pos[ids[i]], pos[ids[j]]), `${ids[i]} / ${ids[j]}`).toBe(false);
  });

  it('is deterministic: the same input twice gives the same output', () => {
    expect(autoLayout(nodes, edges)).toEqual(autoLayout(nodes, edges));
  });

  it('runs left to right, and top down for TB', () => {
    const lr = autoLayout(nodes, edges), tb = autoLayout(nodes, edges, 'TB');
    expect(lr.canon.x).toBeGreaterThan(lr.conn.x);
    expect(tb.canon.y).toBeGreaterThan(tb.conn.y);
  });

  it('ignores a link to a missing node and a self link', () => {
    const pos = autoLayout(nodes.slice(0, 2), [{ a: 'conn', b: 'nope' }, { a: 'conn', b: 'conn' }, { a: 'conn', b: 'canon' }]);
    expect(Object.keys(pos)).toHaveLength(2);
  });
});

describe('placeMissing (P9-8.13)', () => {
  it('keeps stored positions and places only the nodes without one', () => {
    const mixed = [{ ...nodes[0], x: 500, y: 300 }, { ...nodes[1] }, { ...nodes[2], x: NaN, y: 0 }];
    const out = placeMissing(mixed, edges);
    expect(Object.keys(out).sort()).toEqual(['canon', 'map']);
  });
  it('returns nothing when every node is placed', () => {
    expect(placeMissing(nodes.map((n) => ({ ...n, x: 0, y: 0 })), edges)).toEqual({});
  });
});
