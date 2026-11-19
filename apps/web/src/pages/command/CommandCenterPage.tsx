/**
 * Circularity Command Center (#/command, #/command/<section>): the demo's renderCommand. One page per section; each role
 * sees the sections its layout has (CC_LAYOUT, ccSecOK) and the access policy allows (canPage).
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  capacity, ccFilters, ccKeys, ccLayout, ccMetrics, ccMode, ccOps, ccPick, ccRows, ccScope, ccSecDesc, ccSecLabel, ccSecOK, ccSection,
  classLabel, clearCcFilters, clockText, CC_STAGES, dueSlices, filterOptions, healthDetail, healthStrip, insights, kfmt, kpiTiles,
  rbPath, routeBars, routeShort, setCcFilters, setCcMode, setCcOps, signals, sourceCount, stageSlices, tenantAllowed, visCaseCount,
  visRowCount, workflowCount, type CcFilters, type CcRows, type CcScope, type KpiTile,
} from '../../api/command';
import { fmtNumber } from '../../api/format';
import { useBackend } from '../../api/hooks';
import { canPage, currentAccount, setTenantFilter, tenantFilter } from '../../api/session';
import type { PageProps } from '../registry';
import { Icon } from '../../ui/Icon';
import { toast } from '../../ui/toast';
import { Combo, Donut, HealthRing, RouteBars, Spark, VarList } from './charts';
import { ActionsTable, ApprovalCards, Aome, Exceptions, Handed, Inbox, OpsReadOnly, Outcomes } from './sections';

const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
/** Where each section's panel sits, so a tile can scroll to it when it is on the page. */
const SEC_EL: Record<string, string> = { kpis: 'ccVar', approvals: 'ccApprovals', aome: 'ccAome', handed: 'ccHanded', signals: 'ccSignals' };
const CC_DUE_LBL: Record<string, string> = { d5: '< 5 days', d7: '5–7 days', d10: '8–10 days', d11: '> 10 days' };

export function CommandCenterPage({ route }: PageProps) {
  useBackend();
  const nav = useNavigate();
  const [, tick] = useState(0);
  useEffect(() => {
    document.title = 'Command Center · Circularity Decision Workbench';
    const t = window.setInterval(() => tick((n) => n + 1), 30000); // the "last refreshed" clock
    return () => window.clearInterval(t);
  }, []);

  const acct = currentAccount()!;
  const adm = acct.role === 'Admin';
  const L = ccLayout();
  const sec = ccSection(route.a);
  const sc = ccScope();
  const rows = ccRows();
  const f = ccFilters();

  const pick = (arg: string) => {
    if (arg.startsWith('go:')) return nav('/' + arg.slice(3));
    ccPick(arg);
    if (sec !== 'actions' && ccSecOK(ccLayout(), 'actions') && canPage('command', 'actions')) nav('/command/actions');
  };
  const toSection = (k: string) => {
    const el = SEC_EL[k] && document.getElementById(SEC_EL[k]);
    if (el) return el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (ccSecOK(ccLayout(), k) && canPage('command', k)) nav('/command/' + k);
  };
  const tileAct = (t: KpiTile) => {
    const a = t.act;
    if (a.kind === 'pick') pick(a.arg);
    else if (a.kind === 'section') toSection(a.sec);
    else if (a.kind === 'go') nav('/' + a.to);
    else clearCcFilters();
  };

  const charts = L.charts ?? [], row = L.row ?? [];
  const rowS = sec === 'kpis' ? row.filter((x) => x === 'value') : sec === 'signals' ? row.filter((x) => x !== 'value') : [];
  const keys = ccKeys(L);
  const tiles = sec === 'kpis' ? kpiTiles(keys, sc, rows) : [];

  return (
    <div className="cc" data-sec={sec}>
      <div className="phead">
        <div>
          <nav className="crumbs ccsec" aria-label="Command Center section">
            <span>Command Center</span> <span>›</span> <b id="ccSecName">{ccSecLabel(sec)}</b>
          </nav>
          <h1>Circularity Command Center <span className="chip line ccrole">{acct.role} view</span></h1>
          <p>{sec === 'kpis' ? L.sub : ccSecDesc(sec)}</p>
        </div>
        <div className="row ccact">
          {adm && (
            <div className="seg" role="group" aria-label="Command Center view">
              <button aria-pressed={ccMode() !== 'senior'} onClick={() => setCcMode('operational')}>Operational</button>
              <button aria-pressed={ccMode() === 'senior'} onClick={() => setCcMode('senior')}>Senior</button>
            </div>
          )}
          <span className="note ccrf">Last refreshed<br /><b className="num" data-cc-clock>{clockText()}</b></span>
          <button className="iconbtn" aria-label="Refresh data" data-tip="Refresh" onClick={() => { tick((n) => n + 1); toast('Refreshed. All figures recomputed from the latest data.'); }}>
            <Icon name="refresh" />
          </button>
          <button className="btn" onClick={share}><Icon name="share" />Share</button>
          <button className="btn pri" onClick={exportPdf}><Icon name="export" />Export</button>
        </div>
      </div>

      {sec === 'kpis' && L.health && <HealthStrip />}
      {(L.ops || L.fin) && ['kpis', 'actions'].includes(sec) && <Filters f={f} />}
      {sec === 'kpis' && L.ops && (
        <div className="ccinsights">
          <span className="ccit">Needs attention now</span>
          {insights(sc).map(([arg, text]) => <button key={arg} className="ccin" onClick={() => pick(arg)}>{text}</button>)}
        </div>
      )}
      {sec === 'kpis' && (
        <div className="cckpis" id="ccKpis" data-n={keys.length}>
          {tiles.map((t) => <Kpi key={t.key} t={t} onClick={() => tileAct(t)} />)}
        </div>
      )}

      {sec === 'exceptions' && (L.senior || L.exceptions) && canPage('command', 'exceptions') && <Exceptions sc={sc} />}
      {sec === 'exceptions' && L.senior && (
        <>
          <label className="tog exops">
            <input type="checkbox" checked={ccOps()} onChange={(e) => setCcOps(e.target.checked)} /> Show operational queues (read-only)
          </label>
          {ccOps() && <OpsReadOnly sc={sc} />}
        </>
      )}
      {sec === 'aome' && L.aome && canPage('command', 'aome') && <Aome />}
      {sec === 'handed' && L.handed && canPage('command', 'handed') && <Handed />}
      {sec === 'approvals' && L.inbox && canPage('command', 'approvals') && (
        <>
          <ApprovalCards />
          <Inbox onPick={pick} />
        </>
      )}
      {sec === 'outcomes' && L.outcomes && canPage('command', 'outcomes') && <Outcomes />}

      {sec === 'kpis' && charts.length > 0 && (
        <div className="ccgrid4" id="ccCharts" data-n={charts.length}>
          {charts.map((x) => <Chart key={x} k={x} sc={sc} f={f} onPick={pick} />)}
        </div>
      )}
      {sec === 'actions' && L.actions && <ActionsTable sc={sc} onPick={pick} />}
      {rowS.length > 0 && (
        <div className="ccgrid3" id={sec === 'signals' ? 'ccSignals' : undefined} data-n={rowS.length}>
          {rowS.map((x) => <RowPanel key={x} k={x} sc={sc} rows={rows} f={f} onPick={pick} />)}
        </div>
      )}
      {sec === 'kpis' && tiles.length > 0 && (
        <details className="ccdefs" id="ccDefs">
          <summary>What these figures mean</summary>
          <dl>{tiles.map((t) => <Def key={t.key} t={t} />)}</dl>
        </details>
      )}
      {sec === 'health' && L.health === 'full' && <DevHealth />}

      <p className="note ccfoot">
        {L.health === 'full' && !L.ops
          ? `Figures come from the ${sourceCount()} connected sources, ${workflowCount()} workflows and the live event stream.`
          : `Every figure here is computed from the same ${visCaseCount()} live returns and ${visRowCount().toLocaleString()} closed decisions as Product and Analytics${acct.tenant ? ' for your tenants' : ''}. Select any chart, bar or signal to filter. Capacity figures are configured planning values.`}
      </p>
    </div>
  );
}

function share() {
  const u = window.location.href;
  (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(
    () => toast('Link copied. It opens this Command Center.'),
    () => toast('Copy this link to share: ' + u, 6000),
  );
}
function exportPdf() {
  toast('Opening the print dialog. Choose Save as PDF for a one-page summary.');
  window.setTimeout(() => window.print(), 400);
}

function Def({ t }: { t: KpiTile }) {
  return <><dt>{t.label}</dt><dd>{t.tip}</dd></>;
}

function Kpi({ t, onClick }: { t: KpiTile; onClick: () => void }) {
  return (
    <button className={'cck ' + t.cls} data-tip={t.tip} onClick={onClick}>
      <span className="cckt"><span className="kic"><Icon name={t.icon} /></span><span className="ccl">{t.label}</span></span>
      <span className="ccv num">{t.val}</span>
      <span className="ccs">
        {t.delta && <span className={'ccd ' + t.delta.cls}>{t.delta.arrow} {t.delta.txt}</span>}
        <span className="note">{t.sub}</span>
      </span>
      {t.spark && <span className="ccsp"><Spark s={t.spark} /></span>}
    </button>
  );
}

function HealthStrip() {
  const h = healthStrip();
  return (
    <div className="cchealth" id="ccHealth">
      <span className="livedot"><i />Live</span>
      <span><b className="num">{h.pct.toFixed(1)}%</b> integration health</span>
      <span className="note">
        {h.live} sources live
        {h.stale > 0 && <> · <b style={{ color: 'var(--warn)' }}>{h.stale} stale</b></>}
        {h.unavailable > 0 && <> · <b style={{ color: 'var(--bad)' }}>{h.unavailable} not connected</b></>}
        {h.manual > 0 && ' · ' + h.manual + ' manual'}
      </span>
      {rbPath('integration/map') && <a className="lnk" href="#/integration/map">View connections</a>}
    </div>
  );
}

function Filters({ f }: { f: CcFilters }) {
  const o = filterOptions(), tenant = tenantFilter();
  const active: [keyof CcFilters, string][] = [];
  if (f.stage) active.push(['stage', (CC_STAGES().find((s) => s[0] === f.stage) ?? [0, f.stage])[1] as string]);
  if (f.route) active.push(['route', routeShort(f.route)]);
  if (f.reason) active.push(['reason', f.reason]);
  if (f.due) active.push(['due', CC_DUE_LBL[f.due] ?? f.due]);
  const sel = (k: 'site' | 'cls' | 'route', label: string, opts: [string, string][]) => (
    <label className="ccf">
      <span>{label}</span>
      <select className="sel" aria-label={label} value={f[k]} onChange={(e) => setCcFilters({ [k]: e.target.value })}>
        <option value="">All</option>
        {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
  const setTenant = (v: string) => {
    if (!tenantAllowed(v)) return toast('Request access to ' + v + ' first.');
    setTenantFilter(v);
  };
  return (
    <>
      <div className="ccbarf">
        <label className="ccf">
          <span>Tenant</span>
          <select className="sel" aria-label="Tenant" value={tenant} onChange={(e) => setTenant(e.target.value)}>
            {o.tenants.map((t) => <option key={t.value} value={t.value} disabled={t.disabled}>{t.label}</option>)}
          </select>
        </label>
        {sel('site', 'Site', o.sites.map((x) => [x, x]))}
        {sel('cls', 'Asset class', o.classes)}
        {sel('route', 'Recommended route', o.routes.map((r) => [r[0], r[1]]))}
        <label className="ccf">
          <span>Time horizon</span>
          <select className="sel" aria-label="Time horizon for closed decisions" value={String(f.months)} onChange={(e) => setCcFilters({ months: +e.target.value })}>
            <option value="12">Last 12 months</option>
            <option value="6">Last 6 months</option>
            <option value="3">Last 3 months</option>
          </select>
        </label>
      </div>
      {(active.length > 0 || f.site || f.cls || tenant !== 'All') && (
        <div className="ccactive">
          <span className="note">Filtered:</span>
          {active.map(([k, l]) => <button key={k} className="chip y chipb" onClick={() => setCcFilters({ [k]: '' })}>{l} ✕</button>)}
          {tenant !== 'All' && <span className="chip line">{tenant}</span>}
          {f.site && <span className="chip line">{f.site}</span>}
          {f.cls && <span className="chip line">{classLabel(f.cls)}</span>}
          <button className="btn ghost sm" onClick={clearCcFilters}>Clear all</button>
        </div>
      )}
    </>
  );
}

function Chart({ k, sc, f, onPick }: { k: string; sc: CcScope; f: CcFilters; onPick: (a: string) => void }) {
  if (k === 'lifecycle')
    return (
      <section className="panel">
        <div className="ph"><h3>Lifecycle portfolio</h3></div>
        <div className="pb"><Donut items={stageSlices(sc)} cur={'stage:' + f.stage} top={fmtNumber(sc.all.length)} bottom="Assets" label="Lifecycle portfolio" onPick={onPick} /></div>
      </section>
    );
  if (k === 'treat')
    return (
      <section className="panel">
        <div className="ph"><h3>Channel opportunity</h3><span className="note">Predicted volume (units)</span></div>
        <div className="pb"><RouteBars items={routeBars(sc)} cur={f.route} label="Treatment opportunity" onPick={onPick} /></div>
      </section>
    );
  if (k === 'var')
    return (
      <section className="panel" id="ccVar">
        <div className="ph"><h3>Value at risk by reason</h3><span className="note num">{kfmt(sum(sc.all.map((c) => c._var)))}</span></div>
        <div className="pb ccvlist"><VarList sc={sc} cur={f.reason} onPick={onPick} /></div>
      </section>
    );
  if (k === 'due')
    return (
      <section className="panel">
        <div className="ph"><h3>Assets by time to action</h3></div>
        <div className="pb"><Donut items={dueSlices(sc)} cur={'due:' + f.due} top={fmtNumber(sc.act.length)} bottom="Assets" label="Assets by time to action" onPick={onPick} /></div>
      </section>
    );
  return null;
}

function RowPanel({ k, sc, rows, f, onPick }: { k: string; sc: CcScope; rows: CcRows; f: CcFilters; onPick: (a: string) => void }) {
  if (k === 'signals') {
    const l = signals(sc);
    return (
      <section className="panel">
        <div className="ph"><h3>Emerging signals</h3></div>
        <div className="pb ccsgl" id="ccSig">
          {l.length ? l.map((s) => (
            <button key={s.t} className="ccsg" onClick={() => onPick(s.act)}>
              <span className={'sgi ' + s.lvl}><Icon name={s.ic} /></span>
              <span className="sgt"><b>{s.t}</b><span className="note">{s.note}</span></span>
              <span className="sgn num">{s.n}</span>
            </button>
          )) : <div className="empty"><b>No signals</b>Nothing needs attention.</div>}
        </div>
      </section>
    );
  }
  if (k === 'capacity')
    return (
      <section className="panel">
        <div className="ph"><h3>Capacity and bottlenecks</h3></div>
        <div className="pb ccvlist">
          {capacity(sc).map((x) => (
            <div key={x.k} className="cccp" data-tip={x.label + ': ' + x.u + ' of ' + x.cap + ' planned slots. Capacity values are configured planning figures.'}>
              <span className="ccvl">{x.label}</span>
              <span className="ccvb"><i style={{ width: Math.min(100, x.p * 100) + '%', background: x.color }} /></span>
              <b className="num">{Math.round(x.p * 100)}%</b>
              <span className="note" style={{ color: x.p >= 0.75 ? x.color : 'var(--muted)' }}>{x.msg}</span>
            </div>
          ))}
        </div>
      </section>
    );
  if (k === 'value') return <ValuePanel rows={rows} f={f} />;
  return null;
}

function ValuePanel({ rows, f }: { rows: CcRows; f: CcFilters }) {
  const m = ccMetrics(rows);
  return (
    <section className="panel" id="ccValue">
      <div className="ph">
        <h3>Value realisation</h3>
        <div className="seg" role="group" aria-label="Horizon">
          {[3, 6, 12].map((n) => <button key={n} aria-pressed={f.months === n} onClick={() => setCcFilters({ months: n })}>{n} mo</button>)}
        </div>
      </div>
      <div className="pb">
        <div className="ccrs">
          <div data-tip="Actual net recovery on reconciled decisions in the period. Same as Analytics when filters match."><b className="num">{kfmt(m.act)}</b><span>Net recovery</span></div>
          <div data-tip="Actual ÷ predicted net recovery on reconciled decisions."><b className="num">{m.rcCount && m.p50 ? Math.round((m.act / m.p50) * 100) : 0}%</b><span>Recovery yield</span></div>
          <div data-tip="Median days from decision to reconciled outcome."><b className="num">{m.days ? m.days.toFixed(0) : '—'} days</b><span>Cycle time</span></div>
          <div data-tip="Estimated embodied-carbon avoided on reconciled decisions."><b className="num">{(m.co2e / 1000).toFixed(0)} t</b><span>CO₂e avoided</span></div>
        </div>
        <Combo rows={rows} months={f.months} />
      </div>
    </section>
  );
}

function DevHealth() {
  const h = healthDetail(), sevc = { High: 'bad', Medium: 'warn', Low: 'line' } as const;
  return (
    <div className="sect" id="ccDevHealth">
      <div className="sh">
        <h2>Integration health</h2>
        <span className="livedot"><i />Live</span>
        <span className="grow" />
        <a className="btn sm" href="#/integration/map">Open Source map</a>
      </div>
      <div className="grid g3 smside" id="smSide" style={{ alignItems: 'start' }}>
        <div className="panel">
          <div className="ph"><h3>Integration health</h3><span className="note">Last 24 hours</span></div>
          <div className="pb"><HealthRing h={h} /></div>
        </div>
        <div className="panel">
          <div className="ph"><h3>Mapping exceptions</h3><span className={'chip ' + (h.exceptions.length ? 'warn' : 'ok')}>{h.exceptionCount} open</span></div>
          <div className="tw">
            <table className="t static tight">
              <thead><tr><th>System</th><th>Issue</th><th>Severity</th><th>Status</th></tr></thead>
              <tbody>
                {h.exceptions.length ? h.exceptions.map((e, i) => (
                  <tr key={i}>
                    <td><b>{e.src}</b><div className="note">{e.obj}</div></td>
                    <td>{e.issue}</td>
                    <td><span className={'chip ' + sevc[e.sev]}>{e.sev}</span></td>
                    <td><span className={'chip ' + (e.st === 'Open' ? 'line' : 'y')}>{e.st}</span></td>
                  </tr>
                )) : <tr><td colSpan={4}><div className="empty"><b>No exceptions</b>Every connected system is mapped and fresh.</div></td></tr>}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <div className="ph"><h3>Recent integration events</h3><a className="lnk" href="#/integration/events">View all</a></div>
          <div className="tw">
            <table className="t static tight">
              <thead><tr><th>Time</th><th>System</th><th>Event</th><th>Status</th></tr></thead>
              <tbody>
                {h.events.map((e) => (
                  <tr key={e.id}>
                    <td className="num nowrap">{new Date(e.ts).toISOString().slice(11, 19)}</td>
                    <td>{e.dest}</td>
                    <td className="mono">{e.type}</td>
                    <td><span className={'chip ' + e.kind}>{e.ack.length > 16 ? e.ack.slice(0, 15) + '…' : e.ack}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}


