import { describe, expect, it } from 'vitest';
import { RAIL_WIDE_PX, afterCheckClick, afterEsc, afterPick, afterSelect, initialRail, type RailState } from './railTab';

const closed: RailState = { open: false, tab: 'inspector', pinned: null };

describe('railTab', () => {
  it('opens by default only at the wide breakpoint', () => {
    expect(RAIL_WIDE_PX).toBe(1600);
    expect(initialRail(1920).open).toBe(true);
    expect(initialRail(1440).open).toBe(false);
  });

  it('a selection opens the Inspector when nothing is pinned', () => {
    expect(afterSelect(closed, 'n1')).toEqual({ open: true, tab: 'inspector', pinned: null });
    expect(afterSelect({ open: true, tab: 'history', pinned: null }, 'n1').tab).toBe('inspector');
  });

  it('a selection keeps the tab the person pinned', () => {
    const pinned: RailState = { open: true, tab: 'impact', pinned: 'impact' };
    expect(afterSelect(pinned, 'n1')).toEqual(pinned);
    expect(afterSelect({ open: false, tab: 'inspector', pinned: 'impact' }, 'n1')).toEqual({ open: true, tab: 'impact', pinned: 'impact' });
  });

  it('clearing the selection changes nothing', () => {
    const st: RailState = { open: true, tab: 'checks', pinned: 'checks' };
    expect(afterSelect(st, null)).toBe(st);
  });

  it('a check click goes to the Inspector and drops the pin', () => {
    expect(afterCheckClick()).toEqual({ open: true, tab: 'inspector', pinned: null });
    expect(afterCheckClick().open).toBe(true);
  });

  it('picking a tab pins it; picking the active tab closes the rail and unpins', () => {
    expect(afterPick(closed, 'checks')).toEqual({ open: true, tab: 'checks', pinned: 'checks' });
    expect(afterPick(closed, 'inspector')).toEqual({ open: true, tab: 'inspector', pinned: null });
    expect(afterPick({ open: true, tab: 'checks', pinned: 'checks' }, 'checks')).toEqual({ open: false, tab: 'checks', pinned: null });
  });

  it('Esc closes an open rail and unpins; a closed rail is untouched', () => {
    expect(afterEsc({ open: true, tab: 'impact', pinned: 'impact' })).toEqual({ open: false, tab: 'impact', pinned: null });
    expect(afterEsc(closed)).toBe(closed);
  });
});
