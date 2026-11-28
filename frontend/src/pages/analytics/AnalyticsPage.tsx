/**
 * Analytics (#/analytics, #/analytics/<section>): the demo's renderAnalytics, with the CXO layer's predicted-vs-actual focus
 * (#/analytics/predicted puts that chart first, with the agent's answer beside it).
 */
import { useEffect, useState, type CSSProperties, type FormEvent, type ReactNode } from 'react';
import { useNavigate } from 'react-router';
import {
  analyticsOrgs, analyticsRows, assetClasses, classIcon, classOptions, closedRow, DEFAULT_FILTER, journeyStep, kfmt, metrics, modelAccuracy, months, routeById, routes,
  type AnalyticsFilter, type ClosedRow,
} from '../../api/analytics';
import { fmtDateYear, money } from '../../api/format';
import { finishedRuns, type RunPick } from '../../api/replay';
import { useBackend } from '../../api/useBackend';
import { allowedTenants, can, canPage, tenantFilter } from '../../api/session';
import { sessionScoped } from '../../api/view';
import type { PageProps } from '../registry';
import { Icon } from '../../components/Icon';
import { openAssistant } from '../../utils/askBus';
import { Drawer } from '../../components/Overlay';
import { Segmented } from '../../components/kit/Segmented';
import { PilotReportButton } from '../../components/PilotReport';
import { BacktestSection } from './BacktestReport';
import { PackHeadlines } from './HeadlineSection';
import { PacksTab } from './PackView';
import { drills, Funnel, Heat, MixChart, ModelTable, Overrides, Scatter, Sustain, Waterfall, type Drill } from './AnalyticsCharts';
import { AnalysisBuilder } from './AnalysisBuilder';
import { AgeChart } from './charts/AgeBands';
import { Flow } from './charts/Flow';
import { HeatGrid } from './charts/HeatGrid';
import { TrendBars } from './charts/TrendBars';
import { ageSpec, flowSpec, fromDrill, heatSpec, measureOf, trendSpec, whole } from './charts/specs';
import { DataDrawer } from './data/DataDrawer';
import { facet, sentencePeriod, type Labels, type Measure, type ViewSpec } from './data/dataView';
import { Headline } from './Headline';

// View state survives leaving and coming back, as the demo's S.fA and S.drill do.
const savedFilter = sessionScoped<AnalyticsFilter>(() => ({ ...DEFAULT_FILTER }));

/** Scroll a section into view and mark it, as the demo's anchorScroll does. */
export function anchor(el: Element | null) {
  if (!el) return;
  document.querySelectorAll('[data-anchor]').forEach((x) => x.removeAttribute('data-anchor'));
  el.setAttribute('data-anchor', '1');
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export function Stp({ n }: { n: number }) {
  const j = journeyStep(n);
  return (
    <span className={'stp ' + (j.kind === 'built' ? '' : j.kind)} title={`Journey step ${j.n}: ${j.label} — ${j.desc}`}>
      <b>{j.n}</b>{j.label}
    </span>
  );
}

const statusChip = (r: ClosedRow) =>
  ({
    reconciled: <span className="chip ok">Reconciled</span>,
    pending: <span className="chip warn">Pending</span>,
    cancelled: <span className="chip line">Demand cancelled</span>,
    expired: <span className="chip line">Offer expired</span>,
  })[r.status];

/** The words the drawer and charts use for months, classes and routes: one object while those lists do not change (the charts memoise on it). */
let lastLabels: { key: string; v: Labels } | null = null;
function labelsFor(M: string[], CL: Record<string, { label: string }>, RT: { id: string; name: string }[]): Labels {
  const v: Labels = { months: M, classes: Object.fromEntries(Object.entries(CL).map(([k, x]) => [k, x.label])), routes: Object.fromEntries(RT.map((r) => [r.id, r.name])) };
  const key = JSON.stringify(v);
  if (lastLabels?.key !== key) lastLabels = { key, v };
  return lastLabels.v;
}

export function AnalyticsPage({ route, query }: PageProps) {
  useBackend();
  const nav = useNavigate();
  const [f, setF] = useState<AnalyticsFilter>(savedFilter.current);
  const [vd, setVd] = useState<ViewSpec | null>(null); // View data: the rows behind the figure that was opened
  const [openRow, setOpenRow] = useState<string | null>(null);
  const deepRun = Number(query.get('backtest')) || null; // #/analytics?backtest=<run_id>
  const [tab, setTab] = useState<'closed' | 'packs' | 'backtest'>(deepRun ? 'backtest' : route.a === 'packs' ? 'packs' : 'closed');
  const [runs, setRuns] = useState<RunPick[]>([]);
  useEffect(() => {
    if (!can('runReplay')) return;
    let live = true;
    void finishedRuns().then((r) => { if (live && r.ok) setRuns(r.output.runs); });
    return () => { live = false; };
  }, []);
  const setFilter = (x: AnalyticsFilter) => { savedFilter.current = x; setF(x); };
  /** a chart's selection (title and test) opened as View data, under the chart's name and section (the server's names, for the export record) */
  const drillFor = (chart: string, section: string, measure: Measure) => (d: Drill) => setVd(fromDrill(d, chart, section, measure));

  const sec = route.a;
  const focus = sec === 'predicted' && canPage('analytics', 'predicted');
  useEffect(() => {
    if (!sec) return;
    const t = window.setTimeout(() => anchor(focus ? document.querySelector('.cxfocus') : document.getElementById('an-' + sec)), 30);
    return () => window.clearTimeout(t);
  }, [sec, focus]);

  const rows = analyticsRows(f), m = metrics(rows), M = months(), orgs = analyticsOrgs();
  const labels = labelsFor(M, assetClasses(), routes());
  const period = sentencePeriod(labels, f.from, f.to);
  const tenants = [...new Set(rows.map((r) => r.tenant))].sort();
  const sel = (k: 'tenant' | 'cls' | 'route', opts: [string, string][], label: string) => (
    <select className="sel" aria-label={label} value={f[k]} onChange={(e) => setFilter({ ...f, [k]: e.target.value })}>
      <option value="">{label}</option>
      {opts.map((o) => <option key={o[0]} value={o[0]}>{o[1]}</option>)}
    </select>
  );
  const kpi = (v: string | number, l: string, s: string, d: Drill, measure: Measure) => (
    <button className="kpi" style={{ background: 'none' }} onClick={() => drillFor('kpi', 'waterfall', measure)(d)}>
      <div className="v num">{v}</div><div className="l">{l}</div><div className="s">{s}</div>
    </button>
  );
  /** a panel: its title, then (on the right) View data, which opens every row behind the chart */
  const panel = (id: string, title: string, extra: ReactNode, body: ReactNode, data?: ViewSpec) => (
    <section className="panel" id={'an-' + id}>
      <div className="ph">
        <h3>{title}</h3>{extra}
        {data && <button type="button" className="btn ghost sm" style={{ marginLeft: 'auto' }} onClick={() => setVd(data)}>View data</button>}
      </div>
      <div className="pb">{body}</div>
    </section>
  );
  const aRow = (cols: string, items: [string, () => ReactNode][]) => {
    const l = items.filter((x) => canPage('analytics', x[0]));
    if (!l.length) return null;
    return (
      <div className={'grid ' + (l.length > 1 ? 'g2 ' : '') + 'anr sect'} style={{ '--cols': l.length > 1 && cols ? cols : 'minmax(0,1fr)' } as CSSProperties}>
        {l.map((x) => <div key={x[0]} style={{ display: 'contents' }}>{x[1]()}</div>)}
      </div>
    );
  };
  const filterModel = (v: string) => setFilter({ ...f, model: f.model === v ? '' : v });

  const predicted = () => panel('predicted', 'Predicted vs actual', <Stp n={10} />, <Scatter rows={rows} />,
    whole('Predicted vs actual', 'predicted', 'predicted', [facet.scored()], measureOf.count, 'Overridden and pending cases are left out, as in the chart.'));
  const models = () =>
    panel('models', 'Model versions: the learning loop', null, (
      <>
        <ModelTable filtered={f.model} onFilter={filterModel} />
        <div className="callout" style={{ marginTop: 12 }}>Overridden cases and pending cases are excluded from model error. Select a version to filter every chart on this page.</div>
      </>
    ), whole('Model versions: the learning loop', 'models', 'models', f.model ? [facet.model(f.model)] : [], measureOf.count, 'These are your rows. The table above counts every tenant\u2019s closed decisions, so its counts can be larger.'));

  const tabs = (
    <Segmented
      name="antab" label="Analytics view" cur={tab} onPick={setTab}
      items={[['closed', 'Decisions'], ['packs', 'Packs'], ...(runs.length > 0 || deepRun ? [['backtest', 'Back-test'] as const] : [])] as const}
    />
  );
  if (tab === 'backtest') {
    return (
      <>
        <div className="phead">
          <div>
            <h1>Analytics</h1>
            <p>What a decision flow would have decided on past decisions, each on the facts known then. Modelled, never realised.</p>
          </div>
        </div>
        <div style={{ marginBottom: 12 }}>{tabs}</div>
        <BacktestSection runs={runs} initial={deepRun} />
      </>
    );
  }
  if (tab === 'packs') {
    return (
      <>
        <div className="phead">
          <div>
            <h1>Analytics</h1>
            <p>What each pack measures, from the pack&apos;s own data: its KPIs, two questions with example cases and its stage agents.</p>
          </div>
        </div>
        <div style={{ marginBottom: 12 }}>{tabs}</div>
        <PacksTab />
      </>
    );
  }

  const sections = canPage('analytics', 'waterfall');
  const flow = () => panel('flow', 'Where do returned assets go, and how do they end?', null, <Flow rows={rows} labels={labels} onViewData={setVd} />, flowSpec());
  const heat = () => panel('heat', 'Which route pays best for each asset class?', <span className="note">typical gain per case</span>, <HeatGrid rows={rows} labels={labels} onViewData={setVd} />, heatSpec());
  const trend = () => panel('trend', 'How much is recovered each month, and how far ahead of the baseline are we?', null, <TrendBars rows={rows} labels={labels} onViewData={setVd} />, trendSpec());
  const age = () => panel('age', 'How long are decisions waiting for approval?', <span className="note">open decisions</span>, <AgeChart org={f.org ?? ''} onViewData={setVd} />,
    ageSpec({ source: 'cases', chart: 'age', key: 'all' }, []));

  return (
    <>
      <div className="phead">
        <div>
          <h1>Analytics</h1>
          {!sections && <p>Engineering economics and sustainability from closed decisions. Every number drills to its cases.</p>}
        </div>
      </div>
      <div style={{ marginBottom: 12 }}>{tabs}</div>
      {sections && <Headline m={m} total={rows.length} period={period} tenants={tenants} />}
      {sections && (
        <>
          <div className="kpis ank4">
            {kpi('+' + kfmt(m.uplift), 'additional net recovery vs baseline', `${kfmt(m.act)} recovered vs ${kfmt(m.base)} baseline (${m.base ? '+' + ((m.act / m.base - 1) * 100).toFixed(0) + '%' : '—'})`, drills.all, measureOf.uplift)}
            {kpi(kfmt(m.avoided), 'confirmed avoided spend', `ERP-confirmed on ${m.rc.filter((r) => r.avoided).length} redeploy and parts decisions`, drills.avoid, measureOf.avoided)}
            {kpi(m.days + ' days', 'median days to realize', `vs ${m.baseDays} today · ${m.baseDays ? Math.round((1 - m.days / m.baseDays) * 100) : 0}% faster`, drills.all, measureOf.days)}
            {kpi(m.unresolved, 'unresolved decisions', `${m.pend} pending outcomes + ${m.liveOpen} awaiting approval`, drills.pend, measureOf.count)}
          </div>
          <div className="note" style={{ margin: '6px 2px 0' }}>
            Step <Stp n={10} /> compares actuals with forecasts. Pending cases are shown as pending, never as failures. Uplift is measured against an agreed current-practice baseline (modelled), not predicted improvement.
          </div>
        </>
      )}
      {sections && <PackHeadlines onViewData={setVd} />}
      {focus && (
        <div className="grid g2 anr sect cxfocus" style={{ '--cols': 'minmax(0,1.1fr) minmax(0,1fr)' } as CSSProperties}>
          {predicted()}
          <AgentAnswer onOpen={() => nav('/analytics/models')} />
        </div>
      )}
      <div className="panel" style={{ margin: '16px 0' }}>
        <div className="filters" style={{ border: 0 }}>
          <span className="note">From</span>
          <select className="sel" aria-label="From month" value={f.from} onChange={(e) => { const v = +e.target.value; setFilter({ ...f, from: v, to: Math.max(f.to, v) }); }}>
            {M.map((x, i) => <option key={x} value={i}>{x}</option>)}
          </select>
          <span className="note">to</span>
          <select className="sel" aria-label="To month" value={f.to} onChange={(e) => { const v = +e.target.value; setFilter({ ...f, to: v, from: Math.min(f.from, v) }); }}>
            {M.map((x, i) => <option key={x} value={i}>{x}</option>)}
          </select>
          {sel('tenant', allowedTenants().map((t) => [t, t]), 'Tenant: ' + (tenantFilter() === 'All' ? 'all' : 'global filter on'))}
          {orgs.length > 1 && (
            <select className="sel" aria-label="Org unit" value={f.org ?? ''} onChange={(e) => setFilter({ ...f, org: e.target.value })}>
              <option value="">Org unit: all</option>
              {orgs.map((o) => <option key={o.id} value={o.id}>{'  '.repeat(o.depth) + o.name}</option>)}
            </select>
          )}
          {f.org && <PilotReportButton id={f.org} name={orgs.find((o) => o.id === f.org)?.name ?? f.org} className="btn ghost sm" />}
          {sel('cls', Object.entries(classOptions()).map(([k, v]) => [k, v.label]), 'Asset class')}
          {sel('route', routes().map((r) => [r.id, r.name]), 'Route')}
          <button className="btn ghost sm" onClick={() => { setFilter({ ...DEFAULT_FILTER }); setVd(null); }}>Reset filters</button>
          <span className="grow" />
          <span className="chip line">{rows.length.toLocaleString()} decisions · {m.rc.length.toLocaleString()} reconciled</span>
        </div>
      </div>
      {aRow('minmax(0,1.6fr) minmax(0,1fr)', [
        ['waterfall', () => panel('waterfall', 'Recovery waterfall: baseline to Circularity', <Stp n={10} />, (
          <><Waterfall m={m} onDrill={drillFor('waterfall', 'waterfall', measureOf.uplift)} /><div className="note">Select a bar to open its cases. Bars show reconciled decisions only.</div></>
        ), whole('Recovery waterfall: baseline to Circularity', 'waterfall', 'waterfall', [facet.status('reconciled')], measureOf.uplift))],
        ['pipeline', () => panel('pipeline', 'Pipeline: case to reconciled', null, <Funnel rows={rows} m={m} onDrill={drillFor('pipeline', 'pipeline', measureOf.count)} />,
          whole('Pipeline: case to reconciled', 'pipeline', 'pipeline', [], measureOf.count, 'Decisions a person approved. Cases opened that no one has approved yet are not rows here.'))],
      ])}
      {aRow('', [['pipeline', flow]])}
      {aRow('minmax(0,1.15fr) minmax(0,1fr)', [['mix', heat], ['waterfall', trend]])}
      {aRow('', [['mix', () => panel('mix', 'Route mix over time', <span className="note">decisions carried out per month</span>, <MixChart rows={rows} onDrill={drillFor('mix', 'mix', measureOf.count)} />,
        whole('Route mix over time', 'mix', 'mix', [facet.carriedOut()], measureOf.count))]])}
      {focus
        ? aRow('', [['models', models]])
        : aRow('minmax(0,1.1fr) minmax(0,1fr)', [['predicted', predicted], ['models', models]])}
      {aRow('minmax(0,1fr) minmax(0,1fr)', [
        ['overrides', () => panel('overrides', 'Overrides', null, <Overrides rows={rows} onDrill={drillFor('overrides', 'overrides', measureOf.override)} />,
          whole('Overrides', 'overrides', 'overrides', [facet.override()], measureOf.override))],
        ['pipeline', age],
      ])}
      {aRow('minmax(0,1.5fr) minmax(0,1fr)', [
        ['eng', () => panel('eng', 'Engineering economic intelligence', <span className="chip warn" style={{ height: 'auto', whiteSpace: 'normal' }}>Association, not demonstrated design cause</span>, (
          <>
            <p className="ink2" style={{ marginTop: 0 }}>
              Average value lost per case, by equipment model and component, where repair difficulty or early failure reduced recovery. Procurement and engineering can use this when choosing future fleets, alongside design evidence.
            </p>
            <Heat rows={rows} onDrill={drillFor('eng', 'eng', measureOf.lost)} />
          </>
        ), whole('Engineering economic intelligence', 'eng', 'eng', [facet.erosion()], measureOf.lost))],
        ['sustain', () => panel('sustain', 'Sustainability', null, <Sustain rows={rows} />,
          whole('Sustainability', 'sustain', 'sustain', [facet.withCo2()], measureOf.co2, 'CO2e is estimated from sample factors, or measured where a partner certificate or ERP movement exists. Estimates and measurements are never mixed in one total.'))],
      ])}
      {sections && <AnalysisBuilder rows={rows} labels={labels} onViewData={setVd} />}
      {vd && (
        <DataDrawer
          spec={vd} rows={rows} filter={f} period={period} labels={labels} canExport={canPage('analytics', vd.section)} onClose={() => setVd(null)}
          onOpenRow={(id, source) => (source === 'cases' ? nav('/product/' + id) : setOpenRow(id))}
        />
      )}
      {openRow && <ClosedDrawer id={openRow} onClose={() => setOpenRow(null)} />}
    </>
  );
}

/** A closed decision (the demo's openClosed drawer). */
function ClosedDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const r = closedRow(id);
  if (!r) return null;
  const M = months(), CL = assetClasses(), up = r.status === 'reconciled' ? (r.actual ?? 0) - r.baseline : null;
  return (
    <Drawer title={r.id} sub="Closed decision" onClose={onClose} foot={<button className="btn" onClick={onClose}>Back to analytics</button>}>
      <div className="row" style={{ gap: 12, marginBottom: 12 }}>
        <span className="thumb" style={{ width: 56, height: 46 }}><Icon name={classIcon(r.cls)} /></span>
        <div><b style={{ fontSize: 16 }}>{CL[r.cls]?.label} · {r.assetId}</b><div className="note">{r.tenant} · {r.site} · {M[r.mi]}</div></div>
      </div>
      <div className="row" style={{ marginBottom: 12 }}>{statusChip(r)}<span className="chip line">Model {r.model}</span><span className="chip line">{r.snapshot}</span></div>
      <table className="terms">
        <tbody>
          <tr><td>Route carried out</td><td>{routeById(r.route).name}</td></tr>
          <tr><td>Predicted net (P10 / P50 / P90)</td><td>{money(r.p10)} / {money(r.p50)} / {money(r.p90)}</td></tr>
          <tr><td>Actual net</td><td>{r.actual == null ? 'Pending: not a failure' : money(r.actual)}</td></tr>
          <tr><td>Current-practice baseline (modelled)</td><td>{money(r.baseline)}</td></tr>
          {up != null && <tr className="tot"><td>Recovery vs baseline</td><td className={up < 0 ? 'neg' : 'pos'}>{money(up)}</td></tr>}
        </tbody>
      </table>
      <dl className="kv" style={{ marginTop: 14 }}>
        <dt>Days to realize</dt><dd>{r.days == null ? '—' : r.days + ' (baseline ' + r.baseDays + ')'}</dd>
        <dt>Confirmed avoided spend</dt><dd>{r.avoided ? money(r.avoided) : '—'}</dd>
        <dt>CO₂e estimated / measured</dt><dd>{r.co2e} kg / {r.co2m == null ? 'not measured' : r.co2m + ' kg'}</dd>
        {r.pool && <><dt>Pool effect</dt><dd>{money(r.pool.g)} greedy → {money(r.pool.o)} pooled</dd></>}
        {r.ero ? <><dt>Value erosion</dt><dd>{money(r.ero)} · {r.comp} · {r.equip}</dd></> : null}
      </dl>
      {r.override && (
        <div className="callout" style={{ marginTop: 14 }}>
          <b>Human override</b><br />
          Recommended {routeById(r.override.rec).name}; carried out {routeById(r.override.exec).name}.<br />
          Reason: {r.override.reason}<br />
          <span className="note">
            Versus the recommended route's estimated outcome ({money(r.override.cf)}): <b className={r.override.delta < 0 ? 'neg' : 'pos'}>{money(r.override.delta)}</b>. Counterfactual is an estimate, not observed.
          </span>
        </div>
      )}
    </Drawer>
  );
}

/** The agent's answer beside the chart (the demo's analytics.accuracy intent and its cxacc card). */
function AgentAnswer({ onOpen }: { onOpen: () => void }) {
  const [q, setQ] = useState('');
  let o;
  try {
    o = modelAccuracy();
  } catch (e) {
    return <section className="panel"><div className="pb"><p className="note">{(e as Error).message}</p></div></section>;
  }
  const a = o.versions[0], b = o.versions[o.versions.length - 1];
  const ask = (e: FormEvent) => { e.preventDefault(); if (q.trim()) openAssistant({ mode: 'ask', question: q.trim() }); setQ(''); };
  return (
    <section className="panel" aria-label="Circularity Agent answer">
      <div className="ph"><h3><Icon name="bot" /> Circularity Agent</h3><span className="note">Predicted vs actual: what changed across the model versions?</span></div>
      <div className="pb">
        <p style={{ marginTop: 0 }}>
          Every reconciled decision is scored against its prediction. Error fell from {a.error_pct}% on {a.version} to {b.error_pct}% on {b.version}, and {o.within_band_pct}% of{' '}
          {o.decisions.toLocaleString('en-US')} decisions landed within ±{o.band_pct}%.
        </p>
        <article className="afc afc-cxacc" data-card="cxacc">
          <header className="afch">
            <div><h4>Predicted vs actual · what changed</h4><div className="note">{o.decisions.toLocaleString('en-US')} reconciled decisions; overrides and pending cases excluded</div></div>
            <span className="afbs"><span className="afb afb-retrieved">Retrieved</span><span className="afb afb-model">Model</span></span>
          </header>
          <div className="tw">
            <table className="t static tight">
              <thead><tr><th>Version</th><th>Released</th><th className="r">Decisions</th><th className="r">Error</th><th className="r">Bias</th><th className="r">P10–P90 coverage</th></tr></thead>
              <tbody>
                {o.versions.map((v) => (
                  <tr key={v.version}>
                    <td><b>{v.version}</b></td><td>{fmtDateYear(new Date(v.released))}</td><td className="r num">{v.decisions}</td>
                    <td className="r num">{v.error_pct}%</td><td className={'r num' + (v.bias_pct < 0 ? ' neg' : '')}>{v.bias_pct}%</td><td className="r num">{v.coverage_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="afcite">
            <li><b>Less optimistic</b> <span>{a.version} over-predicted by {Math.abs(a.bias_pct)}%; {b.version} is within {Math.abs(b.bias_pct)}%.</span></li>
            <li><b>Honest ranges</b> <span>The P10–P90 range now holds {b.coverage_pct}% of actual results against an {o.target_coverage_pct}% target, up from {a.coverage_pct}%.</span></li>
            <li><b>How</b> <span>Each release retrained on the cost lines reconciled at stage 10 since the one before. Nothing is retrained without a person approving the new version.</span></li>
          </ul>
          <footer className="afcf"><button className="btn sm" onClick={onOpen}>Open model versions</button></footer>
        </article>
        <form className="row" style={{ marginTop: 12, flexWrap: 'nowrap' }} onSubmit={ask}>
          <label className="sr" htmlFor="an-ask">Ask a follow-up</label>
          <input id="an-ask" type="text" className="grow" placeholder="Ask a follow-up about this chart" value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="btn sm" type="submit">Ask</button>
        </form>
      </div>
    </section>
  );
}
