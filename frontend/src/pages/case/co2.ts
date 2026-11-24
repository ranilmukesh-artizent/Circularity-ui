/** The CO₂e avoided a route shows, and the factor source that stands behind it (P9-0.6). */
import { fmtNumber } from '../../api/format';
import type { Route } from '../../api/case';

export function co2Label(route: Pick<Route, 'co2' | 'co2Src'>): { value: string; source: string | null } {
  return { value: fmtNumber(route.co2 ?? 0) + ' kg', source: route.co2Src || null };
}
