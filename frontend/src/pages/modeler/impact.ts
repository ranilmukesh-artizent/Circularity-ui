/** The Modeler's impact wording (the prototype's propHtml, line 2462-2465) over a flow.simulate answer. */
import type { SimResult } from '../../api/types';

/** The prototype's money(n): $12.3k, $1.25M, else whole dollars. */
export function poMoney(n: number): string {
  const s = n < 0 ? '−' : '';
  const a = Math.abs(n);
  if (a >= 1e6) return s + '$' + (a / 1e6).toFixed(2) + 'M';
  if (a >= 1e4) return s + '$' + (a / 1e3).toFixed(1) + 'k';
  return s + '$' + Math.round(a).toLocaleString('en-US');
}

const signed = (dv: number) => (dv >= 0 ? '+' : '−') + poMoney(Math.abs(dv));

/** "N of M open decisions change · ±$X queue net" (device: lots, expected cash and days). */
export function formatImpact(s: SimResult): string {
  if (s.kind === 'device') {
    const dd = s.extra.dd ?? 0;
    return `${s.flips.length} of ${s.n} lots change channel · ${signed(s.dv)} expected cash · ${dd >= 0 ? '+' : ''}${dd.toFixed(1)} days`;
  }
  return `${s.flips.length} of ${s.n} open decisions change · ${signed(s.dv)} queue net`;
}

/** The trade-off note when the change gives up value (dv < 0), else null. */
export function tradeOff(s: SimResult): string | null {
  if (s.dv >= 0) return null;
  const dd = s.extra.dd ?? 0;
  const faster = s.kind === 'device' && dd < 0 ? ' to dispose ' + (-dd).toFixed(1) + ' days faster' : '';
  return `Trade-off: the models already pick the highest-value ${s.kind === 'equip' ? 'path' : 'channel'}, so this rule gives up ${poMoney(-s.dv)}${faster}. Approve it for a business reason such as a customer commitment, risk or capacity.`;
}

/** The what-if levers on the tool-fleet flow (flow.simulate `params`): label, bounds and the neutral value. The server
 *  refuses anything outside the bounds (backend/di/services/actions/modeler_sim.py LEVER_BOUNDS). */
export const LEVERS = {
  market: { label: 'Market', lo: 0.5, hi: 1.5, base: 1, pct: true },
  labor: { label: 'Labour', lo: 0.5, hi: 1.5, base: 1, pct: true },
  lease: { label: 'Lease', lo: 0.5, hi: 1.5, base: 1, pct: true },
  slots: { label: 'Repair slots', lo: 0, hi: 20, base: 8, pct: false },
} as const;

export type LeverName = keyof typeof LEVERS;
export type Levers = Record<LeverName, number>;

/** The server's refusal text for a lever out of range, or null when the value is allowed. */
export function leverError(name: LeverName, value: number): string | null {
  const { lo, hi } = LEVERS[name];
  const whole = name !== 'slots' || Number.isInteger(value);
  return Number.isFinite(value) && whole && value >= lo && value <= hi ? null : `${name} must be between ${lo} and ${hi}.`;
}

/** "<n> decisions change, total net <±$>" for a what-if answer. */
export const formatWhatIf = (s: SimResult): string => `${s.flips.length} decisions change, total net ${signed(s.dv)}`;
