import { useCallback, useEffect, useState } from 'react';
import { importDemand, importHistory, replayBatches, replayReport, replayRuns, runReplay, type BatchView, type ReplayReport } from '../../api/replay';
import { can, currentAccount } from '../../api/session';
import type { ModelerScreen } from '../../api/types';
import { Panel } from '../../components/kit/Panel';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { constraintLine, finished, headline, upliftLine, versionLabel } from './replayReport';

/** The packs history can be replayed for (the pack of the template on screen). */
export const REPLAY_PACKS = ['tool_fleet', 'device'];

/** "2025-10-01 to 2026-09-28", or a dash when no row was good. */
export const periodLine = (b: Pick<BatchView, 'period'>): string => (b.period ? `${b.period[0]} to ${b.period[1]}` : '—');

/** Show the panel to the roles that run or read replays, for the packs that have one. */
export const showReplay = (s: ModelerScreen): boolean => REPLAY_PACKS.includes(s.template.key) && can('runReplay');

/**
 * Replay (plan 9, P9-7.1 and P9-7.2, story X-06): import a CSV of past decisions for this pack and org unit. The file is read in
 * the browser and sent as text; the server checks every row, keeps the good ones and holds the rest with a reason. Shows the rows
 * kept, the decision period and the held rows (the first 50). "Replay" decides every kept row as of its own date under the
 * flow's draft (or a published version) and shows the four numbers: the route mix, straight-through, approvals and exceptions a
 * day, and the uplift with its 80 % band, then the facts dropped for being later than the decision and the data-quality list.
 * The Executive role reads only: no import or replay button, but the latest report shows.
 */
export function ReplayPanel({ s }: { s: ModelerScreen }) {
  const pack = s.template.key;
  const action = useAction();
  const [batches, setBatches] = useState<BatchView[]>([]);
  const [err, setErr] = useState('');
  const canImport = currentAccount()?.role !== 'Executive';
  const flow = s.flow;
  const [ver, setVer] = useState(flow.dver !== null ? 'draft' : String(flow.ver));
  const [report, setReport] = useState<ReplayReport | null>(null);
  const [waiting, setWaiting] = useState(false);
  const versions = [...(flow.dver !== null ? ['draft'] : []), String(flow.ver), ...s.versions.map((v) => String(v.ver))];

  /** Ask for the run's report until it ends (the replay runs in the worker): done shows it, failed shows why. */
  const follow = useCallback(async (runId: number) => {
    setWaiting(true);
    for (let k = 0; k < 120; k++) {
      const r = await replayReport(runId);
      if (!r.ok) break;
      if (finished(r.output.status)) {
        if (r.output.report) setReport(r.output.report);
        else if (r.output.error) setErr(r.output.error);
        break;
      }
      await new Promise((ok) => setTimeout(ok, 1500));
    }
    setWaiting(false);
  }, []);

  useEffect(() => {
    void (async () => {
      const r = await replayRuns(flow.id);
      const done = r.ok ? r.output.runs.find((x) => x.status === 'done') : undefined;
      if (done) void follow(done.run_id);
    })();
  }, [flow.id, follow]);

  const replayBatch = async (b: BatchView) => {
    setErr('');
    const r = await action.run(() => runReplay(b.id, flow.id, ver), { inline: setErr, ms: 4200 });
    if (r.ok) await follow(r.output.run_id);
  };

  const load = useCallback(async () => {
    const r = await replayBatches(pack, s.org);
    if (r.ok) setBatches(r.output.batches);
  }, [pack, s.org]);
  useEffect(() => {
    void load();
  }, [load]);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setErr('');
    const csv = await file.text();
    const r = await action.run(() => importHistory(pack, s.org, csv), { inline: setErr, ms: 4200 });
    if (!r.ok) return;
    toast(`${r.output.rows} rows read, ${r.output.held} held.`);
    await load();
  };

  const pickDemand = async (b: BatchView, file: File | undefined) => {
    if (!file) return;
    setErr('');
    const csv = await file.text();
    const r = await action.run(() => importDemand(b.id, csv), { inline: setErr, ms: 4200 });
    if (!r.ok) return;
    toast(`${r.output.demand_rows} demand rows kept, ${r.output.demand_held} held.`);
    await load();
  };

  return (
    <Panel title="Replay" sub="Past decisions to test the rules on" cls="mdl-replay">
      {canImport && (
        <div className="mdl-row" data-replay-import>
          <label className="btn sm pri" htmlFor="mdl-rp-file">Import history (CSV)</label>
          <input id="mdl-rp-file" type="file" accept=".csv,text/csv" className="sr" disabled={action.pending}
                 onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = ''; }} />
          <span className="note">De-identified extracts only: item ids are serials or salted hashes.</span>
        </div>
      )}
      {err && <p className="mdl-msg blk" role="alert" data-replay-refusal>{err}</p>}
      {batches.length === 0 && <p className="note" data-replay-empty>No history imported for {s.org} yet.</p>}
      <ul className="mdl-hist">
        {batches.map((b) => (
          <li key={b.id} data-replay-batch={b.id}>
            <b>Batch {b.id}</b>{' '}
            <span className="note">· {b.rows} rows · {b.held} held · {periodLine(b)}</span>
            {canImport && b.rows > b.held && (
              <span className="mdl-row" data-replay-run>
                <select value={ver} onChange={(e) => setVer(e.target.value)} aria-label="Flow version to replay" disabled={waiting}>
                  {versions.map((v) => <option key={v} value={v}>{versionLabel(v)}</option>)}
                </select>
                <button type="button" className="btn sm pri" disabled={action.pending || waiting} onClick={() => void replayBatch(b)}>
                  {ver === 'draft' ? 'Replay the draft' : `Replay ${versionLabel(ver)}`}
                </button>
              </span>
            )}
            {canImport && pack === 'tool_fleet' && b.rows > b.held && (
              <span className="mdl-row" data-replay-demand>
                <label className="btn sm" htmlFor={`mdl-rp-demand-${b.id}`}>Demand at the time (CSV)</label>
                <input id={`mdl-rp-demand-${b.id}`} type="file" accept=".csv,text/csv" className="sr" disabled={action.pending}
                       onChange={(e) => { void pickDemand(b, e.target.files?.[0]); e.target.value = ''; }} />
                <span className="note">{b.demand_rows} demand rows{b.demand_held > 0 ? `, ${b.demand_held} held` : ''}</span>
              </span>
            )}
            {b.held > 0 && (
              <ul className="mdl-hist" data-replay-held>
                {Object.entries(b.held_reasons).map(([why, n]) => <li key={why}>{n} × {why}</li>)}
                {b.held_items.map((h) => <li key={h.n} className="note">row {h.n} · {h.item_id} · {h.held_reason}</li>)}
              </ul>
            )}
          </li>
        ))}
      </ul>
      {waiting && <p className="note" data-replay-waiting>Replaying the history…</p>}
      {report && <ReplayResult r={report} />}
    </Panel>
  );
}

/** The four numbers first, then the facts left out as later than the decision and the data-quality list. */
function ReplayResult({ r }: { r: ReplayReport }) {
  return (
    <div data-replay-report={r.run_id}>
      <h4>
        Batch {r.batch_id} under {versionLabel(r.flow_ver)}: {r.n_decided} of {r.n_items} items decided over {r.days} business days
      </h4>
      <p><a href={`#/analytics?backtest=${r.run_id}`} data-replay-open-report>Open the report</a> <span className="note">(the Back-test page, with the waterfall and a PDF)</span></p>
      <table className="tbl" data-replay-mix>
        <thead><tr><th>Route</th><th>Actual</th><th>Flow</th></tr></thead>
        <tbody>
          {r.route_mix.map((m) => (
            <tr key={m.route}><td>{m.route}</td><td>{m.actual_pct.toFixed(1)} %</td><td>{m.flow_pct.toFixed(1)} %</td></tr>
          ))}
        </tbody>
      </table>
      <ul className="mdl-hist" data-replay-loads>
        {headline(r).map((h) => <li key={h.key} data-replay-load={h.key}>{h.label}: <b>{h.value}</b></li>)}
        {constraintLine(r) && <li data-replay-constraint>{constraintLine(r)}</li>}
        <li data-replay-uplift>Uplift: <b>{upliftLine(r.uplift)}</b> <span className="note">· the flow agrees with {r.agreement_pct.toFixed(1)} % of past routes</span></li>
      </ul>
      {r.leakage.length > 0 && (
        <p className="note" data-replay-leakage>{r.leakage.length} fact reading(s) dated after the decision were left out.</p>
      )}
      {r.data_quality.length > 0 && (
        <ul className="mdl-hist" data-replay-quality>
          {r.data_quality.map((d) => <li key={d.reason} className="note">{d.count} × {d.reason}</li>)}
        </ul>
      )}
    </div>
  );
}
