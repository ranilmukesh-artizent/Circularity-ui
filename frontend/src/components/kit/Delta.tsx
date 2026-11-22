/** Change against an earlier value (the demo's frDelta): an arrow and a percentage, good or bad. */

export interface DeltaInfo { cls: string; text: string; tip: string }

export const Delta = ({ d }: { d?: DeltaInfo | null }) => (d ? <span className={'frd ' + d.cls} data-tip={d.tip}>{d.text}</span> : null);

/** The change from `prev` to `cur` in percent; `goodUp` says whether up is good (null: neither). Null without a base. */
export function pctDelta(cur: number, prev: number, goodUp: boolean | null): DeltaInfo | null {
  if (prev == null || !isFinite(prev) || prev === 0 || cur == null) return null;
  const p = ((cur - prev) / Math.abs(prev)) * 100;
  if (!isFinite(p)) return null;
  const up = p >= 0, good = goodUp == null ? '' : up === goodUp ? 'good' : 'bad';
  return {
    cls: good,
    tip: 'Against the same measure 30 days earlier',
    text: (up ? '▲' : '▼') + ' ' + (Math.abs(p) < 10 ? Math.abs(p).toFixed(1) : Math.abs(p).toFixed(0)) + '%',
  };
}
