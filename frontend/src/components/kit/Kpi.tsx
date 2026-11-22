/** KPI tile (the demo's frKpi): icon, value, label, an optional note, change and sparkline; a link when `href` is set. */
import type { ReactNode } from 'react';
import { IconTile } from './IconTile';
import { Spark } from './Spark';

export function Kpi({ ic, h, v, l, sub, k, n, delta, sp, href }: {
  ic: string; h: string; v: ReactNode; l: string; sub?: string;
  /** data-k ('' when none) */
  k?: string;
  /** data-n; left out when undefined */
  n?: string | number;
  /** the change (a Delta, or other markup); the change row shows when this or `sp` is set */
  delta?: ReactNode;
  sp?: number[];
  href?: string;
}) {
  const body = (
    <>
      <IconTile ic={ic} h={h} />
      <span className="frkv">
        <b className="num">{v}</b>
        <span className="frkl">{l}</span>
        {sub && <span className="note">{sub}</span>}
      </span>
      {(delta || sp) && (
        <span className="frkd">
          {delta}
          {sp && <Spark v={sp} col={`var(--h-${h})`} />}
        </span>
      )}
    </>
  );
  return href != null ? (
    <a className="frkpi" href={href} data-k={k ?? ''} data-n={n}>{body}</a>
  ) : (
    <div className="frkpi" data-k={k ?? ''} data-n={n}>{body}</div>
  );
}
