import { describe, expect, it } from 'vitest';
import type { NavGroup } from '../api/nav';
import { advancedOpen, menuSections } from './sidebarView';

const g = (id: string, section: string): NavGroup => ({ id, label: id, sub: '', icon: 'x', section, leaf: true, href: '#/' + id, kids: [] });

describe('menuSections', () => {
  it('starts a new heading when the section changes and keeps the order', () => {
    const out = menuSections([g('home', ''), g('setup', ''), g('tasks', 'Decide'), g('product', 'Decide'), g('modeler', 'Advanced')]);
    expect(out.map((s) => [s.name, s.groups.map((x) => x.id)])).toEqual([
      ['', ['home', 'setup']], ['Decide', ['tasks', 'product']], ['Advanced', ['modeler']],
    ]);
  });
  it('is empty for an empty menu', () => {
    expect(menuSections([])).toEqual([]);
  });
});

describe('advancedOpen', () => {
  const adv = { name: 'Advanced', groups: [g('modeler', 'Advanced'), g('audit', 'Advanced')] };
  it('is closed by default', () => {
    expect(advancedOpen(undefined, adv, 'home')).toBe(false);
  });
  it('opens by itself when the current page is inside it', () => {
    expect(advancedOpen(undefined, adv, 'audit')).toBe(true);
  });
  it('lets the stored choice win', () => {
    expect(advancedOpen(false, adv, 'audit')).toBe(false);
    expect(advancedOpen(true, adv, 'home')).toBe(true);
  });
});
