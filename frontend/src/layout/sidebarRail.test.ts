import { describe, expect, it } from 'vitest';
import { collapseOnModeler } from './sidebarRail';

describe('collapseOnModeler', () => {
  it('collapses an open sidebar on the Modeler below 1600px', () => {
    expect(collapseOnModeler('modeler', 1440, false, null)).toBe(true);
  });
  it('leaves wide windows, other pages and an already collapsed sidebar alone', () => {
    expect(collapseOnModeler('modeler', 1600, false, null)).toBe(false);
    expect(collapseOnModeler('home', 1440, false, null)).toBe(false);
    expect(collapseOnModeler('modeler', 1440, true, null)).toBe(false);
  });
  it('keeps the sidebar open when the person opened it on the Modeler before', () => {
    expect(collapseOnModeler('modeler', 1440, false, 'open')).toBe(false);
  });
});
