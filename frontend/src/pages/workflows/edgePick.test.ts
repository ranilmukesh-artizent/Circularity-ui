import { describe, expect, it } from 'vitest';
import { nearestLine, type Line } from './edgePick';

// A main line going right and a branch leaving the same point, curving down: they share their first stretch.
const main: Line = { id: 'v-t', points: [{ x: 0, y: 100 }, { x: 200, y: 100 }] };
const branch: Line = { id: 'v-err', points: [{ x: 0, y: 100 }, { x: 60, y: 100 }, { x: 110, y: 140 }, { x: 140, y: 270 }] };

describe('nearestLine: which link a canvas click means', () => {
  it('picks the main line where it runs apart from the branch, even if the branch is listed (drawn) last', () => {
    expect(nearestLine([main, branch], { x: 120, y: 103 })).toBe('v-t');
    expect(nearestLine([branch, main], { x: 170, y: 98 })).toBe('v-t');
  });

  it('picks the branch where the click is on the branch', () => {
    expect(nearestLine([main, branch], { x: 130, y: 210 })).toBe('v-err');
  });

  it('on the shared stretch the first line listed wins; with no lines there is no answer', () => {
    expect(nearestLine([main, branch], { x: 20, y: 100 })).toBe('v-t');
    expect(nearestLine([], { x: 0, y: 0 })).toBeNull();
  });
});
