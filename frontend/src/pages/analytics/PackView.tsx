import { useState } from 'react';
import { usePackView, type PackKpi, type PackQuestion, type PackStage, type PackViewData } from '../../api/analytics';
import { money } from '../../api/format';
import { Kpi } from '../../components/kit/Kpi';
import { Panel } from '../../components/kit/Panel';

const AUTONOMY: Record<PackStage['autonomy'], string> = { recommend: 'recommends only', limits: 'within limits', alone: 'acts alone' };
const NO_DATA = 'No data yet';

/** A KPI value as the pack's unit says: "%", "$" (money), or a plain number; "No data yet" when the pack has none. */
export function kpiValue(k: Pick<PackKpi, 'value' | 'unit'>): string {
  if (k.value === null) return NO_DATA;
  if (k.unit === '$') return money(k.value);
  const n = Number.isInteger(k.value) ? String(k.value) : k.value.toFixed(1);
  return k.unit ? n + k.unit : n;
}

/** The KPI tiles of a pack (the kit's tile, one per KPI the server sent, whatever its id): the label, the value, the trend. */
export function PackKpiTiles({ kpis }: { kpis: PackKpi[] }) {
  return (
    <div className="frkpis" aria-label="Pack KPIs">
      {kpis.map((k) => (
        <Kpi
          key={k.id} ic="spark" h="int" k={k.id} v={kpiValue(k)} l={k.label} sub={k.error ?? (k.value === null ? k.definition : undefined)}
          sp={k.trend.map((t) => t.value)}
        />
      ))}
    </div>
  );
}

function Question({ q }: { q: PackQuestion }) {
  const mx = Math.max(1, ...q.rows.map((r) => Math.abs(r.value)));
  return (
    <Panel title={q.question} sub={q.rows.length ? undefined : NO_DATA}>
      {q.rows.map((r) => (
        <div key={r.key} style={{ margin: '6px 0' }}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <span>{r.key}</span>
            <b className="num">{Number.isInteger(r.value) ? r.value : r.value.toFixed(1)}</b>
          </div>
          <div className="bar"><i style={{ width: (Math.abs(r.value) / mx) * 100 + '%' }} /></div>
        </div>
      ))}
      {q.examples.length > 0 && (
        <p className="note" style={{ marginBottom: 0 }}>
          Example cases: {q.examples.map((id, i) => <span key={id}>{i > 0 && ', '}<a href={'#/product/' + id}>{id}</a></span>)}
        </p>
      )}
    </Panel>
  );
}

/** A pack's view, drawn from the data it carries: KPI tiles, its questions with example cases, the suggestion rules as configured
 *  and the stage agents. No page code per pack: it renders whatever KPI ids and labels it is given. */
export function PackView({ view }: { view: PackViewData }) {
  return (
    <div data-pack={view.key}>
      <PackKpiTiles kpis={view.kpis} />
      {view.questions.length > 0 && (
        <div className="grid g2 sect">{view.questions.map((q) => <Question key={q.question} q={q} />)}</div>
      )}
      <div className="grid g2 sect">
        <Panel title="Stage agents" sub={view.name}>
          <ul className="note" style={{ margin: 0, paddingLeft: 16 }}>
            {view.stages.map((s) => <li key={s.key}>{s.label}: {s.agent} ({AUTONOMY[s.autonomy]})</li>)}
          </ul>
        </Panel>
        <Panel title="Suggestion rules" sub="As configured in the pack">
          {view.suggestion_rules.length === 0 ? (
            <p className="note" style={{ margin: 0 }}>This pack has no suggestion rules.</p>
          ) : (
            <ul className="note" style={{ margin: 0, paddingLeft: 16 }}>
              {view.suggestion_rules.map((r, i) => <li key={i}>{String(r.text ?? r.id ?? JSON.stringify(r))}</li>)}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}

/** Analytics › Packs: a pack select, then the pack's view (the first pack with KPIs until one is picked). */
export function PacksTab() {
  const [key, setKey] = useState('');
  const view = usePackView(key);
  return (
    <>
      <div className="filters" style={{ border: 0, marginBottom: 12 }}>
        <select className="sel" aria-label="Pack" value={view.key} onChange={(e) => setKey(e.target.value)}>
          {view.packs.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
        </select>
        <span className="note">KPIs and questions come from the pack&apos;s own data, over the cases you may see.</span>
      </div>
      <PackView view={view} />
    </>
  );
}
