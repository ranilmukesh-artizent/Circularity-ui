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
