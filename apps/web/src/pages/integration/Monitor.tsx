/* Monitor (W9): integration health over time, per source and per workflow, against SLA. Per workflow (plan 6 D1): the
 * real runs of the last 24 hours (runs, success, last run, mean and p95 duration) and, expanded, each step's p95
 * duration and the records it still holds by rule; a workflow without a real run shows its seeded history. */
import { Fragment, useState } from 'react';
import { useBackend } from '../../api/useBackend';
import { failedRecords, hourly, latency, monitorWorkflows, slaMinutes, sources, srcAge, srcFailing, successRate, totals, wfStat, workflows } from '../../api/integration';
import { toast } from '../../ui/toast';
import { Kpi } from '../../ui/kit/Kpi';
import { Panel } from '../../ui/kit/Panel';
import { VendorLogo } from '../../ui/kit/VendorLogo';
import { useInt } from './FabricContext';
import { fmtN, sum } from './fabricFormat';
import { FabricStatus } from './FabricStatus';

const ago = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? s + ' sec ago' : s < 3600 ? Math.floor(s / 60) + ' min ago' : s < 172800 ? Math.floor(s / 3600) + ' h ago' : Math.floor(s / 86400) + ' days ago';
};
const hh2 = (i: number) => String(i).padStart(2, '0') + ':00';

export function Monitor() {
  useBackend();
  const ui = useInt();
  const [open, setOpen] = useState<string | null>(null);
  const MW = monitorWorkflows();
  const W = workflows(), hh = hourly(), t = totals(), S = sources(), srcs = S.filter((s) => s.status !== 'unavailable');
  const inSla = srcs.filter((s) => s.freshMin != null && s.freshMin <= slaMinutes(s));
  const L = srcs.map(latency).filter((l): l is number => l != null); // a source with no measured call has no latency
  const fr7 = sum(srcs.map((s) => failedRecords(s, 7))), lat = Math.round(sum(L) / (L.length || 1));
  const mx = Math.max(...hh.map((b) => b.ok + b.warn + b.bad)), dips = hh.map((b, i) => ({ i, b })).filter((x) => x.b.bad > 0);
  const dip = (i: number) => {
    const b = hh[i], bad = S.filter((s) => s.status === 'stale' || srcFailing(s)).map((s) => s.vendor);
    toast(`At ${hh2(i)} there were ${b.bad} failed and ${b.warn} warning runs out of ${b.ok + b.warn + b.bad}. ${bad.length ? 'Sources that were stale or failing at the time: ' + bad.join(', ') + '. ' : ''}Failures keep their records in the error handler; open a failing workflow and choose Investigate for the step and the reason.`, 7000);
  };
  return (
    <div id="frMon">
      <div className="frkpis">
        <Kpi ic="checks" h="int" v={t.pct.toFixed(1) + '%'} l="Sync success" sub="last 24 hours" sp={hh.map((b) => b.ok / (b.ok + b.warn + b.bad || 1))} k="success" />
        <Kpi ic="clock" h="money" v={fmtN(lat) + ' ms'} l="Average latency" sub="per sync request" k="latency" />
        <Kpi ic="alert" h="alert" v={fmtN(fr7)} l="Failed records" sub="last 7 days, held for reprocessing" k="failed" />
        <Kpi ic="gauge" h="dec" v={inSla.length + ' / ' + srcs.length} l="Fresh within SLA" sub="connected sources" k="sla" />
        <Kpi ic="workflow" h="insp" v={W.filter((w) => wfStat(w) === 'failing').length} l="Failing workflows" k="wffail" />
      </div>
      <Panel title="Sync runs, last 24 hours" sub="Each bar is one hour; the same history feeds Home and the Source Map">
        <div className="frmonb" aria-hidden="true">
          {hh.map((b, i) => (
            <span key={i} data-tip={`${hh2(i)} · ${b.ok} successful, ${b.warn} warnings, ${b.bad} failures`} title={`${hh2(i)} · ${b.ok} successful, ${b.warn} warnings, ${b.bad} failures`}>
              <i style={{ height: (b.bad / mx) * 100 + '%', background: 'var(--bad)' }} /><i style={{ height: (b.warn / mx) * 100 + '%', background: 'var(--h-dec)' }} /><i style={{ height: (b.ok / mx) * 100 + '%', background: 'var(--ok)' }} />
            </span>
          ))}
        </div>
        <div className="frlegl">
          <span><i style={{ background: 'var(--ok)' }} />Successful {fmtN(t.ok)}</span>
          <span><i style={{ background: 'var(--h-dec)' }} />Warnings {fmtN(t.warn)}</span>
          <span><i style={{ background: 'var(--bad)' }} />Failures {fmtN(t.bad)}</span>
        </div>
        {!!dips.length && (
          <p className="note" style={{ margin: '10px 0 0' }}>
            Dips at {dips.slice(0, 6).map((x, k) => <span key={x.i}>{k ? ', ' : ''}<button className="lnk" onClick={() => dip(x.i)}>{hh2(x.i)}</button></span>)}. Select one for an explanation.
          </p>
        )}
      </Panel>
      <div className="frmon2">
        <Panel title="Per source">
          <div className="tw">
            <table className="t static tight">
              <thead><tr><th>Source</th><th>Freshness</th><th>SLA</th><th className="r">Success</th><th className="r">Failed (7 d)</th><th className="r">Latency</th></tr></thead>
              <tbody>
                {S.map((s) => {
                  const ok = s.freshMin != null && s.freshMin <= slaMinutes(s), l = latency(s);
                  return (
                    <tr key={s.id}>
                      <td><span className="frsys"><VendorLogo vendor={s.vendor} /><span><b>{s.vendor}</b><span className="note">{s.name}</span></span></span></td>
                      <td>{s.freshMin == null ? <span className="note">—</span> : s.fresh}</td>
                      <td>{s.status === 'unavailable' ? <FabricStatus k="unavailable" /> : ok ? <FabricStatus k="success" t={'Within ' + srcAge(slaMinutes(s))} /> : <FabricStatus k="failed" t={'Over ' + srcAge(slaMinutes(s))} />}</td>
                      <td className="r num">{s.status === 'unavailable' ? '—' : successRate(s) + '%'}</td>
                      <td className="r num">{fmtN(failedRecords(s, 7))}</td>
                      <td className="r num">{l == null ? '—' : fmtN(l) + ' ms'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
        <Panel title="Per workflow" sub="Lowest success first">
          <div className="tw">
            <table className="t static tight">
              <thead><tr><th>Workflow</th><th className="r">Runs (24 h)</th><th className="r">Success</th><th>Last run</th><th className="r">Avg duration</th><th className="r">p95 duration</th></tr></thead>
              <tbody>
                {MW.filter((w) => w.runs24).sort((a, b) => a.ok24 / a.runs24 - b.ok24 / b.runs24).slice(0, 14).map((w) => {
                  const st = w.lastState ?? w.last?.state, on = open === w.id;
                  return (
                    <Fragment key={w.id}>
                      <tr>
                        <td>
                          <button className="lnk" aria-expanded={on} aria-label={(on ? 'Hide' : 'Show') + ' the steps of ' + w.name} onClick={() => setOpen(on ? null : w.id)}>{on ? '▾' : '▸'}</button>{' '}
                          <button className="lnk b" onClick={() => ui.go('integration/studio/' + w.id)}>{w.name}</button>
                        </td>
                        <td className="r num">{w.runs24}</td>
                        <td className={'r num ' + (w.ok24 / w.runs24 < 0.9 ? 'neg' : '')}>{Math.round((w.ok24 / w.runs24) * 100)}%</td>
                        <td>{w.last ? <><FabricStatus k={st === 'failed' ? 'failed' : 'success'} /> <span className="note">{ago(Date.now() - w.last.ts)}</span></> : '—'}</td>
                        <td className="r num">{w.avg == null ? '—' : w.avg + ' s'}</td>
                        <td className="r num">{w.p95 == null ? '—' : w.p95 + ' s'}</td>
                      </tr>
                      {on && (
                        <tr>
                          <td colSpan={6}>
                            {!w.real ? (
                              <span className="note">No real run in the last 24 hours: the figures are the workflow's seeded history, without steps.</span>
                            ) : (
                              <table className="t static tight">
                                <thead><tr><th>Step</th><th className="r">p95 duration</th><th>Held records by rule</th></tr></thead>
                                <tbody>
                                  {w.steps.map((s) => (
                                    <tr key={s.id}>
                                      <td>{s.label}</td>
                                      <td className="r num">{s.p95 == null ? '—' : s.p95 + ' s'}</td>
                                      <td>{s.heldN ? Object.entries(s.held).map(([r, n]) => `${r} ${fmtN(n)}`).join(', ') : <span className="note">None held</span>}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
}
