/**
 * View settings that belong to this browser, not to the backend: the top bar's tenant filter, the theme, the
 * Command Center view an Admin picked, the asset opened last and the region settings. In the demo these lived on its
 * state object S; here they live in the browser and are sent to the screens as query parameters
 * (tenant_filter, cc_mode, last_asset).
 */
import { bump } from './store';

export interface Region { lang: string; tz: string; cur: string; dfmt?: string; nfmt?: string; [k: string]: unknown }

export interface ViewState {
  tenant: string;
  theme: 'light' | 'dark';
  ccMode: 'operational' | 'senior';
  lastAsset: string | null;
  rg: Region;
  /** Alerts this browser acknowledged (derived alerts have no server record; the demo's S.frAck). */
  acks: Record<string, true>;
}

const KEY = 'circ-view-v1';
const DEFAULTS: ViewState = { tenant: 'All', theme: 'light', ccMode: 'operational', lastAsset: null, rg: { lang: 'en', tz: 'UTC', cur: 'INR' }, acks: {} };

function load(): ViewState {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : { ...DEFAULTS };
  } catch {
    return { ...DEFAULTS };
  }
}

const state: ViewState = load();

export const view = (): Readonly<ViewState> => state;

/** Change view settings (kept in this browser's local storage). */
export function setView(patch: Partial<ViewState>): void {
  Object.assign(state, patch);
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* private window: settings last for this tab only */
  }
  bump();
}
