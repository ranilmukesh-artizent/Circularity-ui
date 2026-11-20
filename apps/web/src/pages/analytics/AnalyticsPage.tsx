/**
 * Analytics (#/analytics, #/analytics/<section>): the demo's renderAnalytics, with the CXO layer's predicted-vs-actual focus
 * (#/analytics/predicted puts that chart first, with the agent's answer beside it).
 */
import { useEffect, useState, type CSSProperties, type FormEvent, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  analyticsRows, assetClasses, classIcon, closedRow, DEFAULT_FILTER, journeyStep, kfmt, metrics, modelAccuracy, months, routeById, routes,
  type AnalyticsFilter, type ClosedRow,
} from '../../api/analytics';
import { fmtDateYear, money } from '../../api/format';
import { useBackend } from '../../api/useBackend';
import { allowedTenants, canPage, tenantFilter } from '../../api/session';
import type { PageProps } from '../registry';
import { Icon } from '../../ui/Icon';
import { openAsk } from '../../ui/askBus';
import { Drawer } from '../../ui/Overlay';
import { toast } from '../../ui/toast';
import { downloadCsv } from '../../lib/csv';
import { drills, Funnel, Heat, MixChart, ModelTable, Overrides, PoolChart, Scatter, Sustain, Waterfall, type Drill } from './AnalyticsCharts';

// View state survives leaving and coming back, as the demo's S.fA and S.drill do.
let savedFilter: AnalyticsFilter = { ...DEFAULT_FILTER };
let savedDrill: (Drill & { page: number }) | null = null;

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

export function AnalyticsPage({ route }: PageProps) {
  useBackend();
  const nav = useNavigate();
  const [f, setF] = useState<AnalyticsFilter>(savedFilter);
  const [drill, setDrillState] = useState(savedDrill);
  const [openRow, setOpenRow] = useState<string | null>(null);
  const setFilter = (x: AnalyticsFilter) => { savedFilter = x; setF(x); };
  const setDrill = (d: (Drill & { page: number }) | null) => { savedDrill = d; setDrillState(d); };
  const onDrill = (d: Drill) => {
    setDrill({ ...d, page: 0 });
    window.setTimeout(() => document.getElementById('drill')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 30);
  };

  const sec = route.a;
  const focus = sec === 'predicted' && canPage('analytics', 'predicted');
  useEffect(() => {
    if (!sec) return;
    const t = window.setTimeout(() => anchor(focus ? document.querySelector('.cxfocus') : document.getElementById('an-' + sec)), 30);
    return () => window.clearTimeout(t);
  }, [sec, focus]);

  const rows = analyticsRows(f), m = metrics(rows), M = months(), CL = assetClasses();
  const sel = (k: 'tenant' | 'cls' | 'route', opts: [string, string][], label: string) => (
    <select className="sel" aria-label={label} value={f[k]} onChange={(e) => setFilter({ ...f, [k]: e.target.value })}>
      <option value="">{label}</option>
      {opts.map((o) => <option key={o[0]} value={o[0]}>{o[1]}</option>)}
    </select>
  );
  const kpi = (v: string | number, l: string, s: string, d: Drill) => (
    <button className="kpi" style={{ background: 'none' }} onClick={() => onDrill(d)}>
      <div className="v num">{v}</div><div className="l">{l}</div><div className="s">{s}</div>
    </button>
  );
  const panel = (id: string, title: string, extra: ReactNode, body: ReactNode) => (
    <section className="panel" id={'an-' + id}>
      <div className="ph"><h3>{title}</h3>{extra}</div>
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

  const predicted = () => panel('predicted', 'Predicted vs actual', <Stp n={10} />, <Scatter rows={rows} />);
  const models = () =>
    panel('models', 'Model versions: the learning loop', null, (
      <>
        <ModelTable filtered={f.model} onFilter={filterModel} />
        <div className="callout" style={{ marginTop: 12 }}>Overridden cases and pending cases are excluded from model error. Select a version to filter every chart on this page.</div>
      </>
    ));

  return (
    <>
      <div className="phead">
        <div>
          <h1>Analytics</h1>
          <p>
            {canPage('analytics', 'waterfall')
              ? 'Predicted and actual results stay linked, so each decision teaches the next one. The four success measures from the framework lead; every number drills to its cases.'
              : 'Engineering economics and sustainability from closed decisions. Every number drills to its cases.'}
          </p>
        </div>
      </div>
      {focus && (
        <div className="grid g2 anr sect cxfocus" style={{ '--cols': 'minmax(0,1.1fr) minmax(0,1fr)' } as CSSProperties}>
          {predicted()}
          <AgentAnswer onOpen={() => nav('/analytics/models')} />
        </div>
      )}
      <div className="panel" style={{ marginBottom: 16 }}>
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
          {sel('cls', Object.entries(CL).map(([k, v]) => [k, v.label]), 'Asset class')}
          {sel('route', routes().map((r) => [r.id, r.name]), 'Route')}
          <button className="btn ghost sm" onClick={() => { setFilter({ ...DEFAULT_FILTER }); setDrill(null); }}>Reset filters</button>
          <span className="grow" />
          <span className="chip line">{rows.length.toLocaleString()} decisions · {m.rc.length.toLocaleString()} reconciled</span>
        </div>
      </div>
      {canPage('analytics', 'waterfall') && (
        <>
          <div className="kpis ank4">
            {kpi('+' + kfmt(m.uplift), 'additional net recovery vs baseline', `${kfmt(m.act)} recovered vs ${kfmt(m.base)} baseline (${m.base ? '+' + ((m.act / m.base - 1) * 100).toFixed(0) + '%' : '—'})`, drills.all)}
            {kpi(kfmt(m.avoided), 'confirmed avoided spend', `ERP-confirmed on ${m.rc.filter((r) => r.avoided).length} redeploy and parts decisions`, drills.avoid)}
            {kpi(m.days + ' days', 'median days to realize', `vs ${m.baseDays} today · ${m.baseDays ? Math.round((1 - m.days / m.baseDays) * 100) : 0}% faster`, drills.all)}
            {kpi(m.unresolved, 'unresolved decisions', `${m.pend} pending outcomes + ${m.liveOpen} awaiting approval`, drills.pend)}
          </div>
          <div className="note" style={{ margin: '6px 2px 0' }}>
            Step <Stp n={10} /> compares actuals with forecasts. Pending cases are shown as pending, never as failures. Uplift is measured against an agreed current-practice baseline (modelled), not predicted improvement.
          </div>
        </>
      )}
      {aRow('minmax(0,1.6fr) minmax(0,1fr)', [
        ['waterfall', () => panel('waterfall', 'Recovery waterfall: baseline to Circularity', <Stp n={10} />, (
          <><Waterfall m={m} onDrill={onDrill} /><div className="note">Select a bar to open its cases. Bars show reconciled decisions only.</div></>
        ))],
        ['pipeline', () => panel('pipeline', 'Pipeline: case to reconciled', null, <Funnel rows={rows} m={m} onDrill={onDrill} />)],
      ])}
      {aRow('', [['mix', () => panel('mix', 'Route mix over time', <span className="note">decisions carried out per month</span>, <MixChart rows={rows} onDrill={onDrill} />)]])}
      {focus
        ? aRow('', [['models', models]])
        : aRow('minmax(0,1.1fr) minmax(0,1fr)', [['predicted', predicted], ['models', models]])}
      {aRow('minmax(0,1fr) minmax(0,1fr)', [
        ['pool', () => panel('pool', 'Pool efficiency', <Stp n={4} />, <PoolChart rows={rows} />)],
        ['overrides', () => panel('overrides', 'Overrides', null, <Overrides rows={rows} onDrill={onDrill} />)],
      ])}
      {aRow('minmax(0,1.5fr) minmax(0,1fr)', [
        ['eng', () => panel('eng', 'Engineering economic intelligence', <span className="chip warn" style={{ height: 'auto', whiteSpace: 'normal' }}>Association, not demonstrated design cause</span>, (
          <>
            <p className="ink2" style={{ marginTop: 0 }}>
              Average value lost per case, by equipment model and component, where repair difficulty or early failure reduced recovery. Procurement and engineering can use this when choosing future fleets, alongside design evidence.
            </p>
            <Heat rows={rows} onDrill={onDrill} />
          </>
        ))],
        ['sustain', () => panel('sustain', 'Sustainability', null, <Sustain rows={rows} />)],
      ])}
      {drill && <DrillPanel drill={drill} rows={rows} setDrill={setDrill} onOpen={setOpenRow} />}
      {openRow && <ClosedDrawer id={openRow} onClose={() => setOpenRow(null)} />}
    </>
  );
}

function DrillPanel({ drill, rows, setDrill, onOpen }: {
  drill: Drill & { page: number }; rows: ClosedRow[]; setDrill: (d: (Drill & { page: number }) | null) => void; onOpen: (id: string) => void;
}) {
  const M = months(), CL = assetClasses();
  const list = rows.filter(drill.fn).sort((a, b) => Math.abs(b.actual || b.p50) - Math.abs(a.actual || a.p50));
  const pg = drill.page, sh = list.slice(pg * 12, pg * 12 + 12);
  const csv = () => {
    downloadCsv(
      'case,month,tenant,class,route,status,model,predicted_p50,actual,baseline\n' +
        list.map((r) => [r.id, M[r.mi], r.tenant, r.cls, r.route, r.status, r.model, r.p50, r.actual == null ? '' : r.actual, r.baseline].join(',')).join('\n'),
      'circularity-drill.csv',
    );
    toast('Exported ' + list.length + ' cases');
  };
  return (
    <section className="panel sect" id="drill" style={{ marginTop: 20 }}>
      <div className="ph">
        <h3>Drill-through · {drill.title}</h3>
        <span className="chip line">{list.length} cases</span>
        <button className="btn sm" onClick={csv}>Export CSV</button>
        <button className="btn sm ghost" aria-label="Close drill-through" onClick={() => setDrill(null)}><Icon name="close" /></button>
      </div>
      <div className="tw">
        <table className="t">
          <thead><tr><th>Case</th><th>Month</th><th>Tenant</th><th>Class</th><th>Route</th><th>Status</th><th className="r">Predicted P50</th><th className="r">Actual</th><th className="r">vs baseline</th></tr></thead>
          <tbody>
            {sh.length ? sh.map((r) => (
              <tr key={r.id} tabIndex={0} onClick={() => onOpen(r.id)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onOpen(r.id))}>
                <td><b>{r.id}</b></td><td>{M[r.mi]}</td><td>{r.tenant}</td><td>{CL[r.cls]?.label}</td>
                <td>{routeById(r.route).short}{r.override && <> <span className="chip warn">override</span></>}</td>
                <td>{statusChip(r)}</td>
                <td className="r num">{money(r.p50)}</td>
                <td className="r num">{r.actual == null ? '—' : money(r.actual)}</td>
                <td className={'r num ' + (r.actual != null && r.actual - r.baseline < 0 ? 'neg' : 'pos')}>{r.status === 'reconciled' ? money((r.actual ?? 0) - r.baseline) : '—'}</td>
              </tr>
            )) : <tr><td colSpan={9}><div className="empty"><b>No cases</b>Nothing matches this selection.</div></td></tr>}
          </tbody>
        </table>
      </div>
      <div className="filters" style={{ justifyContent: 'space-between', border: 0 }}>
        <span className="note">Page {pg + 1} of {Math.max(1, Math.ceil(list.length / 12))}</span>
        <span className="row">
          <button className="btn sm" disabled={pg === 0} onClick={() => setDrill({ ...drill, page: pg - 1 })}>Previous</button>
          <button className="btn sm" disabled={(pg + 1) * 12 >= list.length} onClick={() => setDrill({ ...drill, page: pg + 1 })}>Next</button>
        </span>
      </div>
    </section>
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
  const ask = (e: FormEvent) => { e.preventDefault(); if (q.trim()) openAsk(q.trim()); setQ(''); };
  return (
    <section className="panel" aria-label="Circularity Agent answer">
      <div className="ph"><h3>✦ Circularity Agent</h3><span className="note">Predicted vs actual: what changed across the model versions?</span></div>
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
