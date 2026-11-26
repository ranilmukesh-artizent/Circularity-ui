/**
 * Wording of the used-car case panels (plan 9 UI audit gap 7; stories UC-06 title and lien, UC-07 odometer, UC-08 recall,
 * UC-10 channels). Pure: it reads the `title`, `odometer`, `recall` and `vehicle` facts and the routes the case screen already
 * carries (backend/di/services/cases/vehicle_evidence.py, car_facts.py, gate_hold.py); nothing here computes a figure.
 * Title, odometer and recall wording touches federal and state law: it needs review by Kinective's Legal team before it is
 * relied on (the UI itself carries no such note).
 */
import type { CaseRec, GateRow, Route } from '../../../api/case';
import { money } from '../../../api/format';
import { gateTime } from '../gates';

export interface CarTitle { status?: string; lien_open?: boolean; lien_release_ref?: string | null; brand?: string | null }
export interface CarOdometer {
  model_year?: number; return_kind?: string; statement_ref?: string; photo_reading?: number; lease_record?: number; not_actual?: boolean;
}
export interface CarRecall { checked_at?: string; open?: boolean; campaigns?: string[]; remedied?: string[]; remedy_ref?: string; fleet_size?: number }

/** The Packs tab of Analytics, where the pack's worked questions are (UC-20, UC-21). */
export const QUESTIONS_HREF = '#/analytics/packs';

export interface CarView { vin: string | null; title?: CarTitle; odometer?: CarOdometer; recall?: CarRecall; returnKind: string | null }

/** The used-car facts of a case, or null for a case of another pack. */
export function usedCarView(c: CaseRec): CarView | null {
  if (c.template !== 'used_cars') return null;
  const x = c as CaseRec & { title?: CarTitle; odometer?: CarOdometer; recall?: CarRecall; vehicle?: { vin?: string } };
  return { vin: x.vehicle?.vin ?? null, title: x.title, odometer: x.odometer, recall: x.recall, returnKind: x.odometer?.return_kind ?? null };
}

const mi = (n: number) => `${n.toLocaleString('en-US')} mi`;

/** "Title clear · no open lien", "Title salvage · lien open, no release on file" or "Title and lien search not on file". */
export function titleLine(t: CarTitle | undefined): string {
  if (!t || !t.status) return 'Title and lien search not on file';
  const lien = t.lien_open ? `lien open, ${t.lien_release_ref ? `release ${t.lien_release_ref}` : 'no release on file'}` : 'no open lien';
  return `Title ${t.status} · ${lien}`;
}

/** "Photo 41,230 mi · lease record 41,100 mi · 130 mi apart", the lessee's statement and a not-actual reading; or "No odometer reading on file". */
export function odometerLine(o: CarOdometer | undefined): string {
  const parts: string[] = [];
  if (o?.photo_reading != null && o.lease_record != null) {
    parts.push(`Photo ${mi(o.photo_reading)}`, `lease record ${mi(o.lease_record)}`, `${mi(Math.abs(o.photo_reading - o.lease_record))} apart`);
  } else if (o?.photo_reading != null) parts.push(`Photo ${mi(o.photo_reading)}`);
  else if (o?.lease_record != null) parts.push(`Lease record ${mi(o.lease_record)}`);
  if (o?.statement_ref) parts.push(`Lessee statement ${o.statement_ref}`);
  if (o?.not_actual) parts.push('reading is not the actual mileage');
  return parts.length ? parts.join(' · ') : 'No odometer reading on file';
}

/** "Open recall: C-2 · checked 2026-10-01 08:00 UTC" (campaigns not yet remedied), "No open recall · checked …" or "Recall check not on file". */
export function recallLine(r: CarRecall | undefined): string {
  if (!r?.checked_at) return 'Recall check not on file';
  const left = (r.campaigns ?? []).filter((id) => !(r.remedied ?? []).includes(id));
  const head = r.open && left.length ? `Open recall: ${left.join(', ')}` : 'No open recall';
  return `${head} · checked ${gateTime(r.checked_at)}`;
}

export interface ChannelRow { id: string; name: string; net: number; best: boolean; note: string }

/** Every channel the car can take with its net and the plan's reason when blocked; the recommended one first, then by net. */
export function channelRows(c: CaseRec): ChannelRow[] {
  const best = (c.chosen || c.recommendation)?.id;
  const rows = c.routes.map((r: Route) => ({ id: r.id, name: r.plan, net: r.net, best: r.id === best, note: r.excluded ? r.failReason ?? 'Not available' : '' }));
  return rows.sort((a, b) => Number(b.best) - Number(a.best) || b.net - a.net);
}

export const netText = (r: ChannelRow): string => (r.note ? r.note : `Net ${money(r.net)}${r.best ? ' · recommended' : ''}`);

/** The title, brand, odometer and recall gates (ids G-VEH-*). */
export const vehicleGates = (gates: GateRow[] | undefined): GateRow[] => (gates ?? []).filter((g) => g.id.startsWith('G-VEH-'));
