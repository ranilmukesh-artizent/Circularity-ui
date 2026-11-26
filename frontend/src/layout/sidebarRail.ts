/**
 * The sidebar on the Modeler (plan 10, 3.2): the page is agent column, canvas and rail side by side, so below 1600px
 * the sidebar starts as its 68px icon form, unless the person has already opened it there.
 */
export const MODELER_WIDE = 1600;
const PREF_KEY = 'circ-modeler-sidebar';

/** Collapse on entering the Modeler: narrow window, sidebar open, and no earlier choice to keep it open. */
export function collapseOnModeler(page: string, width: number, rail: boolean, kept: 'open' | null): boolean {
  return page === 'modeler' && width < MODELER_WIDE && !rail && kept !== 'open';
}

export function keptOpen(): 'open' | null {
  try {
    return localStorage.getItem(PREF_KEY) === 'open' ? 'open' : null;
  } catch {
    return null; // blocked site data: no memory of a choice
  }
}

export function keepOpen(): void {
  try {
    localStorage.setItem(PREF_KEY, 'open');
  } catch {
    /* private window: the choice lasts for this page only */
  }
}
