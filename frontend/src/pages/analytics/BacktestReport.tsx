import { useEffect, useState } from 'react';
import { money } from '../../api/format';
import { replayReport, type ReplayReportOut, type RunPick, type WaterfallStep } from '../../api/replay';
import { headline, upliftLine, versionLabel } from '../modeler/replayReport';
import './backtest.css';

/** The sections of the report page, in the order of the pilot research's section 3.5. */
export const SECTIONS = ['numbers', 'waterfall', 'flips', 'agreement', 'quality', 'method'] as const;

/** What the waterfall's bars and rows add up to: the actual net and every change, which is the flow's net. */
export const waterfallTotal = (steps: WaterfallStep[]): number => steps.filter((s) => s.kind !== 'result').reduce((n, s) => n + s.amount, 0);

/** "+$1,250" or "−$300" for a step that changes the net; the start and the end are plain amounts. */
const stepAmount = (s: WaterfallStep): string => (s.kind === 'delta' && s.amount >= 0 ? '+' : '') + money(s.amount);

/**
 * The back-test report (plan 9, P9-7.6, story X-06): what a flow would have decided on a batch of past decisions, for the
 * Executive to read and to print ("Export PDF" is the browser's print, so the print stylesheet in backtest.css is the PDF).
 * Every number and sentence is the server's (`replay.report`: the report, the waterfall, the ten flips explained and the method
 * note); this component only lays them out, in the order of the pilot research's section 3.5: the four numbers, the waterfall,
 * the flip table, agreement and the items held for a person, data-quality findings, and the method note.
 */
export function BacktestReport({ out }: { out: ReplayReportOut }) {
  const r = out.report;
  if (!r) return <p className="note" data-bt-empty>This replay has no report yet{out.error ? `: ${out.error}` : ''}.</p>;
  const span = Math.max(1, ...out.waterfall.map((s) => Math.abs(s.amount)));
  return (
    <article className="bt-report" data-bt-report={out.run_id} aria-label="Back-test report">
      <header className="bt-head">
        <h2>Back-test: batch {r.batch_id} under {versionLabel(r.flow_ver)}</h2>
        <p className="note">
          {r.n_decided} of {r.n_items} items decided over {r.days} business days, each on the facts known at its own date. Modelled, not realised.
        </p>
        <button type="button" className="btn sm pri bt-noprint" data-bt-export onClick={() => window.print()}>Export PDF</button>
      </header>

      <section data-bt-section="numbers">
        <h3>The four numbers</h3>
        <table className="tbl" data-bt-mix>
          <thead><tr><th>Route</th><th>Actual</th><th>Flow</th></tr></thead>
          <tbody>
            {r.route_mix.map((m) => <tr key={m.route}><td>{m.route}</td><td>{m.actual_pct.toFixed(1)} %</td><td>{m.flow_pct.toFixed(1)} %</td></tr>)}
          </tbody>
        </table>
        <ul className="bt-loads">
          {headline(r).map((h) => <li key={h.key}>{h.label}: <b>{h.value}</b></li>)}
          <li data-bt-uplift>Uplift: <b>{upliftLine(r.uplift)}</b></li>
        </ul>
      </section>

      <section data-bt-section="waterfall">
        <h3>From the actual net to the flow&apos;s net</h3>
        {out.waterfall.length === 0 ? (
          <p className="note">This run was made before the waterfall was kept; replay the batch again to see it.</p>
        ) : (
          <ol className="bt-wf" data-bt-waterfall>
            {out.waterfall.map((s) => (
              <li key={s.step} data-bt-step={s.kind}>
                <span>{s.step}</span>
                <span className="bt-bar" aria-hidden="true">
                  <i className={s.amount < 0 ? 'neg' : ''} style={{ width: `${Math.round((100 * Math.abs(s.amount)) / span)}%` }} />
                </span>
                <b className="num">{stepAmount(s)}</b>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section data-bt-section="flips">
        <h3>Largest flips, explained</h3>
        {out.top_flips.length === 0 ? (
          <p className="note">The flow agreed with every past route.</p>
        ) : (
          <table className="tbl" data-bt-flips>
            <thead><tr><th>Item</th><th>From</th><th>To</th><th>Change</th><th>Why</th></tr></thead>
            <tbody>
              {out.top_flips.map((f) => (
                <tr key={f.item_id}>
                  <td>{f.item_id}</td><td>{f.from ?? '—'}</td><td>{f.to ?? 'no route'}</td>
                  <td className="num">{money(f.delta)}</td>
                  <td>
                    {f.reason}
                    {f.gate && <div className="note">Decided by {f.gate}</div>}
                    {f.trace && <div className="note">{f.trace}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section data-bt-section="agreement">
        <h3>Agreement and items held for a person</h3>
        <p data-bt-agreement>
          The flow agrees with <b>{r.agreement_pct.toFixed(1)} %</b> of past routes. <b>{r.held_for_person}</b> of {r.n_decided} items would wait
          for a person: that is the control working, not a gap.
        </p>
        {r.by_guardrail.length > 0 && (
          <ul className="bt-loads">
            {r.by_guardrail.map((g) => <li key={g.guardrail}>{g.guardrail} ({g.owner || 'no owner'}): {g.approvals} approvals, {g.exceptions} exceptions</li>)}
          </ul>
        )}
      </section>

      <section data-bt-section="quality">
        <h3>Data-quality findings</h3>
        {r.data_quality.length === 0 && r.leakage.length === 0 ? (
          <p className="note">No findings.</p>
        ) : (
          <ul className="bt-loads" data-bt-quality>
            {r.leakage.length > 0 && <li>{r.leakage.length} fact reading(s) dated after the decision were left out.</li>}
            {r.data_quality.map((d) => <li key={d.reason}>{d.count} × {d.reason}</li>)}
          </ul>
        )}
      </section>

      <section data-bt-section="method" className="bt-method">
        <h3>Method note</h3>
        <p data-bt-method>{out.method_note}</p>
      </section>
    </article>
  );
}

/** "Run 12 · Customer A · Tool fleet flow (v1)": how the picker names a finished run. */
export const runLabel = (r: RunPick): string => `Run ${r.run_id} · ${r.org_unit_id} · ${r.flow_name} (${versionLabel(r.flow_ver)})`;

/**
 * The Back-test section of Analytics: a picker over the finished runs and the report of the one picked (`initial` is the run a
 * deep link `#/analytics?backtest=<run_id>` names). The report is read from `replay.report` when the pick changes.
 */
export function BacktestSection({ runs, initial }: { runs: RunPick[]; initial: number | null }) {
  const [id, setId] = useState<number | null>(initial ?? runs[0]?.run_id ?? null);
  const [out, setOut] = useState<ReplayReportOut | null>(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    if (id === null) return;
    let live = true;
    setErr('');
    void replayReport(id).then((r) => {
      if (!live) return;
      if (r.ok) setOut(r.output);
      else { setOut(null); setErr(r.error.message); }
    });
    return () => { live = false; };
  }, [id]);
  return (
    <section className="panel" id="an-backtest">
      <div className="ph">
        <h3>Back-test</h3>
        <select className="sel bt-noprint" aria-label="Replay run" value={id ?? ''} onChange={(e) => setId(Number(e.target.value))}>
          {runs.map((r) => <option key={r.run_id} value={r.run_id}>{runLabel(r)}</option>)}
          {id !== null && !runs.some((r) => r.run_id === id) && <option value={id}>Run {id}</option>}
        </select>
      </div>
      <div className="pb">
        {err && <p className="mdl-msg blk" role="alert" data-bt-refusal>{err}</p>}
        {out && out.run_id === id && <BacktestReport out={out} />}
      </div>
    </section>
  );
}
