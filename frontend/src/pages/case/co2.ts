/** The CO₂e a route shows on its card, with the provenance behind it (P9-1.12, X-12): avoided, not inventory. */
import { fmtNumber } from '../../api/format';
import type { Co2Prov, Route } from '../../api/case';

export const NO_FACTOR = '—: no factor source on file.';

export interface Co2Card {
  /** The avoided figure, "61 kg", or a dash when the route has none. */
  value: string;
  /** "avoided, not inventory", "transport only, not avoided", or null when the route has no CO2e key (industrial). */
  label: string | null;
  /** The transport kg under the transport-only rule, or null. */
  transport: string | null;
  /** "cfs-2026.2 · how it is computed" (the popover's summary), or null. */
  set: string | null;
  factors: Co2Prov['factors'];
  /** The reason a route without a factor shows no figure, or null. */
  missing: string | null;
}

export function co2Label(route: Pick<Route, 'co2' | 'co2Prov'>): Co2Card {
  const empty: Co2Card = { value: '—', label: null, transport: null, set: null, factors: [], missing: null };
  if (!('co2' in route)) return empty; // industrial routes carry no CO2e line: nothing changes on their cards
  const p = route.co2Prov;
  if (!p) return { ...empty, missing: NO_FACTOR };
  return {
    value: route.co2 == null ? '—' : fmtNumber(route.co2) + ' kg',
    label: p.label,
    transport: p.transportKg == null ? null : fmtNumber(p.transportKg) + ' kg transport',
    set: p.set + ' · how it is computed',
    factors: p.factors,
    missing: null,
  };
}
