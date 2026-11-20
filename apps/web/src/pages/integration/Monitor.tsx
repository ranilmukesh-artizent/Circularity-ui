/* Monitor (W9): integration health over time, per source and per workflow, against SLA. */
import { useBackend } from '../../api/hooks';
import { failedRecords, hourly, latency, slaMinutes, sources, srcAge, srcFailing, successRate, totals, wfStat, workflows } from '../../api/integration';
import { toast } from '../../ui/toast';
import { FrKpi, FrPanel, FrSt, fmtN, sum, useInt, Vlogo } from './ui';

const ago = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? s + ' sec ago' : s < 3600 ? Math.floor(s / 60) + ' min ago' : s < 172800 ? Math.floor(s / 3600) + ' h ago' : Math.floor(s / 86400) + ' days ago';
};
const hh2 = (i: number) => String(i).padStart(2, '0') + ':00';

export function Monitor() {
  useBackend();
  const ui = useInt();
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
        <FrKpi ic="checks" h="int" v={t.pct.toFixed(1) + '%'} l="Sync success" sub="last 24 hours" sp={hh.map((b) => b.ok / (b.ok + b.warn + b.bad || 1))} k="success" />
        <FrKpi ic="clock" h="money" v={fmtN(lat) + ' ms'} l="Average latency" sub="per sync request" k="latency" />
        <FrKpi ic="alert" h="alert" v={fmtN(fr7)} l="Failed records" sub="last 7 days, held for reprocessing" k="failed" />
        <FrKpi ic="gauge" h="dec" v={inSla.length + ' / ' + srcs.length} l="Fresh within SLA" sub="connected sources" k="sla" />
        <FrKpi ic="workflow" h="insp" v={W.filter((w) => wfStat(w) === 'failing').length} l="Failing workflows" k="wffail" />
      </div>
      <FrPanel title="Sync runs, last 24 hours" sub="Each bar is one hour; the same history feeds Home and the Source Map">
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
      </FrPanel>
      <div className="frmon2">
        <FrPanel title="Per source">
          <div className="tw">
            <table className="t static tight">
              <thead><tr><th>Source</th><th>Freshness</th><th>SLA</th><th className="r">Success</th><th className="r">Failed (7 d)</th><th className="r">Latency</th></tr></thead>
              <tbody>
                {S.map((s) => {
                  const ok = s.freshMin != null && s.freshMin <= slaMinutes(s), l = latency(s);
                  return (
                    <tr key={s.id}>
                      <td><span className="frsys"><Vlogo vendor={s.vendor} /><span><b>{s.vendor}</b><span className="note">{s.name}</span></span></span></td>
                      <td>{s.freshMin == null ? <span className="note">—</span> : s.fresh}</td>
                      <td>{s.status === 'unavailable' ? <FrSt k="unavailable" /> : ok ? <FrSt k="success" t={'Within ' + srcAge(slaMinutes(s))} /> : <FrSt k="failed" t={'Over ' + srcAge(slaMinutes(s))} />}</td>
                      <td className="r num">{s.status === 'unavailable' ? '—' : successRate(s) + '%'}</td>
                      <td className="r num">{fmtN(failedRecords(s, 7))}</td>
                      <td className="r num">{l == null ? '—' : fmtN(l) + ' ms'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </FrPanel>
        <FrPanel title="Per workflow" sub="Lowest success first">
          <div className="tw">
            <table className="t static tight">
              <thead><tr><th>Workflow</th><th className="r">Runs (24 h)</th><th className="r">Success</th><th>Last run</th><th className="r">Avg duration</th></tr></thead>
              <tbody>
                {W.filter((w) => w.runsN).sort((a, b) => a.okN! / a.runsN! - b.okN! / b.runsN!).slice(0, 14).map((w) => (
                  <tr key={w.id}>
                    <td><button className="lnk b" onClick={() => ui.go('integration/studio/' + w.id)}>{w.name}</button></td>
                    <td className="r num">{w.runsN}</td>
                    <td className={'r num ' + (w.okN! / w.runsN! < 0.9 ? 'neg' : '')}>{Math.round((w.okN! / w.runsN!) * 100)}%</td>
                    <td>{w.last ? <><FrSt k={w.last.state === 'failed' ? 'failed' : 'success'} /> <span className="note">{ago(Date.now() - w.last.ts)}</span></> : '—'}</td>
                    <td className="r num">{w.last ? w.last.dur + ' s' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </FrPanel>
      </div>
    </div>
  );
}
