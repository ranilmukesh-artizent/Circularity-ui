/** A Home KPI tile from the server's tile record: a link when it opens a list. */
import type { Kpi as KpiData } from '../../api/home';
import { Delta } from '../../components/kit/Delta';
import { Kpi } from '../../components/kit/Kpi';

export const HomeKpi = ({ o }: { o: KpiData }) => (
  <Kpi
    ic={o.ic} h={o.h} v={o.v} l={o.l} sub={o.sub} k={o.k || ''} n={o.n == null ? '' : String(o.n)}
    delta={o.delta && <Delta d={o.delta} />} sp={o.sp} href={o.go ? '#/' + o.go : undefined}
  />
);
