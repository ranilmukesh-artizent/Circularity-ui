import { describe, expect, it } from 'vitest';
import { pageTab, visibleTabs } from './ModelerTabs';

const ids = (v: ReturnType<typeof visibleTabs>) => v.map((t) => t.id);

describe('page tabs', () => {
  it('shows Flow, Customer layer and Policies to everyone', () => {
    expect(ids(visibleTabs({ managePacks: false, template: 'industrial' }))).toEqual(['flow', 'layer', 'policies']);
  });
  it('adds Tables for tool_fleet and Packs and Set up for managePacks, in that order', () => {
    expect(ids(visibleTabs({ managePacks: true, template: 'tool_fleet' }))).toEqual(['flow', 'layer', 'policies', 'tables', 'packs', 'setup']);
  });
  it('reads ?tab=, falling back to Flow for an unknown or hidden tab', () => {
    const v = visibleTabs({ managePacks: false, template: 'industrial' });
    expect(pageTab('layer', null, v)).toBe('layer');
    expect(pageTab('packs', null, v)).toBe('flow');
    expect(pageTab('nope', null, v)).toBe('flow');
    expect(pageTab(null, null, v)).toBe('flow');
  });
  it('a ?compose= link opens Set up when no tab is named and the person may set up', () => {
    const v = visibleTabs({ managePacks: true, template: 'industrial' });
    expect(pageTab(null, 7, v)).toBe('setup');
    expect(pageTab('layer', 7, v)).toBe('layer');
    expect(pageTab(null, 7, visibleTabs({ managePacks: false, template: 'industrial' }))).toBe('flow');
  });
});
