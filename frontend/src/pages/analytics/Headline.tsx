/** The page opens on one sentence a person can repeat in a meeting; the four figures and the charts are the evidence. */
import type { Metrics } from '../../api/analytics';
import { headlineMeta, headlineParts } from './headlineText';
import './charts/charts.css';

export function Headline({ m, total, period, tenants }: { m: Metrics; total: number; period: string; tenants: string[] }) {
  const h = headlineParts(m);
  return (
    <section className="hl" aria-label="What the decisions delivered">
      <p className="hl-sentence" data-testid="headline">
        {h.before}{!h.empty && <b className={h.tone}>{h.amount}</b>}{h.after}
      </p>
      <p className="hl-meta">{headlineMeta(m.rc.length, total, period, tenants)}</p>
    </section>
  );
}
