/**
 * The Modeler rail's state (plan 10, T4): which of the five tabs (Overview, Inspector, Checks, Impact, History) shows, whether the
 * rail is open, and which tab the person pinned. Pure, so each rule is tested without a page:
 * - below RAIL_WIDE_PX the rail starts closed (it opens over the canvas on demand), at RAIL_WIDE_PX and wider it starts open;
 * - picking a tab opens and pins it (Inspector is the default, so it pins nothing); picking the active tab closes the rail;
 * - selecting a node opens the Inspector unless the person pinned another tab, which then stays;
 * - clicking a check goes to the Inspector (the node is selected too) and drops the pin; Esc closes.
 */
export type RailTab = 'overview' | 'inspector' | 'checks' | 'impact' | 'history';

export interface RailState {
  open: boolean;
  tab: RailTab;
  /** the tab the person chose by hand; a selection does not switch away from it */
  pinned: RailTab | null;
}

/** From this viewport width the rail sits beside the canvas and starts open (plan 10, 3.4). */
export const RAIL_WIDE_PX = 1600;

export const RAIL_TABS: { id: RailTab; label: string; icon: string }[] = [
  // what the flow holds, what is being watched, its proposals and the last simulation (moved here from the assistant column)
  { id: 'overview', label: 'Overview', icon: 'eye' },
  { id: 'inspector', label: 'Inspector', icon: 'info' },
  { id: 'checks', label: 'Checks', icon: 'checks' },
  { id: 'impact', label: 'Impact', icon: 'trend' },
  { id: 'history', label: 'History', icon: 'rotate' },
];

export const initialRail = (viewportWidth: number): RailState => ({ open: viewportWidth >= RAIL_WIDE_PX, tab: 'inspector', pinned: null });

/** A node was selected on the canvas (or by the assistant's `select`); clearing the selection changes nothing. */
export function afterSelect(st: RailState, nodeId: string | null): RailState {
  if (nodeId === null) return st;
  const tab = st.pinned ?? 'inspector';
  return st.open && st.tab === tab ? st : { ...st, open: true, tab };
}

/** A check in the Checks tab was clicked: its node is selected and the Inspector shows it. */
export const afterCheckClick = (): RailState => ({ open: true, tab: 'inspector', pinned: null });

/** A tab in the strip was clicked. */
export function afterPick(st: RailState, tab: RailTab): RailState {
  if (st.open && st.tab === tab) return { ...st, open: false, pinned: null };
  return { open: true, tab, pinned: tab === 'inspector' ? null : tab };
}

/** The assistant made a proposal for this flow: the Overview tab, where it is listed and applied, opens and stays. */
export const afterProposal = (): RailState => ({ open: true, tab: 'overview', pinned: 'overview' });

export const afterEsc = (st: RailState): RailState => (st.open ? { ...st, open: false, pinned: null } : st);

/** `surface.select(node, 'history')` from the assistant: show that tab now, without pinning it. */
export const afterSurfaceSelect = (st: RailState, nodeId: string | null, tab?: 'inspector' | 'history'): RailState =>
  tab === 'history' ? { ...st, open: true, tab: 'history' } : afterSelect(st, nodeId);
