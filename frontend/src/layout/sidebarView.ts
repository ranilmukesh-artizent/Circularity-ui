/** The menu's sections for the sidebar (plan 11, A2): which groups sit under which heading, and whether the collapsible
 *  Advanced section shows its entries. Pure, so the grouping is tested without the page. */
import type { NavGroup } from '../api/nav';

export interface MenuSection { name: string; groups: NavGroup[] }

/** The section that starts collapsed and remembers its state per browser. */
export const COLLAPSIBLE = 'Advanced';

/** Runs of groups with the same section, in the order the server sent them (a heading changes when the section does). */
export function menuSections(groups: NavGroup[]): MenuSection[] {
  const out: MenuSection[] = [];
  for (const g of groups) {
    const last = out[out.length - 1];
    if (last && last.name === g.section) last.groups.push(g);
    else out.push({ name: g.section, groups: [g] });
  }
  return out;
}

/** Is the collapsible section open? What the person chose wins; else it stays closed, unless the page they are on is
 *  inside it (so they never lose sight of where they are). */
export function advancedOpen(stored: boolean | undefined, section: MenuSection, page: string): boolean {
  return stored ?? section.groups.some((g) => g.id === page);
}

/** The line at the foot of a staged menu (nothing published yet). */
export const STAGED_NOTE = 'Decide and Understand open when you publish.';
