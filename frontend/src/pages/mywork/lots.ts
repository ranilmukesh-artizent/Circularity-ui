/** The wholesale lots card's pure helpers (plan 9, P9-6.11, story DV-07): the line a lot is shown as, the dropped bids, who a lot
 * waits for and whether the signed-in person may approve it. The server decides all of it again (backend/di/services/actions/device_lots.py). */
import type { LotView } from '../../api/device';

/** "$310", "$309.50", "$31,000". */
export function usd(n: number): string {
  const whole = Number.isInteger(Math.round(n * 100) / 100);
  return '$' + n.toLocaleString('en-US', { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: 2 });
}

/** "Galaxy S23 · grade C · 100 units · best approved bid $310 a unit · $31,000", or "... · no approved bid yet". */
export function lotLine(l: LotView): string {
  const head = `${l.model} · grade ${l.grade} · ${l.units} units`;
  if (!l.best_bid) return `${head} · no approved bid yet`;
  const value = l.value_usd ?? l.best_bid.net * l.units;
  return `${head} · best approved bid ${usd(l.best_bid.net)} a unit · ${usd(value)}`;
}

/** "B05: Buyer B05 is not an approved wholesale buyer". */
export const droppedLine = (d: { buyer_code: string; reason: string }): string => `${d.buyer_code}: ${d.reason}`;

/** Who a proposed lot waits for, "Waits for the Approver role (Commercial manager): ...", or '' when it waits for no one. */
export const waitLine = (l: LotView): string =>
  l.waits_for ? `Waits for the ${l.waits_for.role} role (${l.waits_for.owner}): ${l.waits_for.reason}` : '';

/** Why this person may not approve the lot (maker-checker), or null when they may. */
export function canApprove(l: LotView, me: string): string | null {
  if (l.status !== 'proposed') return 'Only a proposed lot is approved.';
  if (me === l.created_by || me === l.proposed_by) return 'You built or proposed this lot, so you cannot approve it.';
  return null;
}
