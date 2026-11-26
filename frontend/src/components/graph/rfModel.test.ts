import { describe, expect, it } from 'vitest';
import { toRfEdges, toRfNodes, type GEdge, type GNode } from './rfModel';

const N = (id: string, x: number, y: number, extra: Partial<GNode> = {}): GNode => ({ id, x, y, w: 168, h: 90, type: 'flow', data: {}, ...extra });

describe('toRfNodes', () => {
  it('marks every node as measured so xyflow keeps its handle bounds (and the edges) when the node is rebuilt on a drag', () => {
    const rf = toRfNodes([N('a', 0, 0), N('b', 10, 20)], {}, false);
    for (const n of rf) expect(n.measured).toEqual({ width: 168, height: 90 });
  });

  it('uses the live drag position over the stored one, and leaves the other nodes where they are', () => {
    const rf = toRfNodes([N('a', 0, 0), N('b', 10, 20)], { a: { x: 55, y: 66 } }, false);
    expect(rf.map((n) => n.position)).toEqual([{ x: 55, y: 66 }, { x: 10, y: 20 }]);
  });

  it('is not draggable when read only', () => {
    expect(toRfNodes([N('a', 0, 0)], {}, true)[0].draggable).toBe(false);
  });
});

describe('toRfEdges', () => {
  it('keeps every edge, with its source and target, whatever the nodes do', () => {
    const e: GEdge[] = [{ id: 'a>b', a: 'a', b: 'b', selected: true }, { id: 'b>c', a: 'b', b: 'c' }];
    const rf = toRfEdges(e);
    expect(rf.map((x) => [x.id, x.source, x.target, x.selected])).toEqual([['a>b', 'a', 'b', true], ['b>c', 'b', 'c', false]]);
  });
});
