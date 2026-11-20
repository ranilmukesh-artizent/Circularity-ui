/**
 * Process orchestration (#/orchestration, #/orchestration/<caserun|flow|run|agents>): the demo's renderOrch as the agent-first
 * layer leaves it: the live run board, run details, the run trace and the agents and services.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fmtDate, money } from '../../api/format';
import { useBackend } from '../../api/hooks';
import {
  agentCalls, agents, caseEvents, caseJournal, handoffModel, inputSummary, orCase, orCaseById, orCases, orT, poolsOn, runModel, runStates,
  setOrCase, stageAgent, traceId,
} from '../../api/orchestration';
import { canRoute } from '../../api/session';
import type { PageProps } from '../registry';
import { anchor } from '../analytics/AnalyticsPage';
import { LiveBoard, useReplay } from './LiveBoard';

const canGo = (p: string) => {
  const h = p.split('/');
  return canRoute({ page: h[0], a: h[1] || null, b: h[2] || null }) === true;
};
const badge = (k: string) => <span className={'afb afb-' + k.toLowerCase().replace(/[^a-z]+/g, '')}>{k}</span>;

export function OrchestrationPage({ route, query }: PageProps) {
  useBackend();
  const nav = useNavigate();
  const cs = orCases();
  const want = query.get('case');
  const [picked, setPicked] = useState<string | null>(() => {
    if (want && cs.some((x) => x.id === want)) { setOrCase(want); return want; }
    return orCase()?.id ?? null;
  });
  // follow a new ?case= in the address. Only `want` is a dependency on purpose: re-running when `picked` changes would
  // undo the person's own pick (back to the address's case), and `cs` is a fresh array every render.
  useEffect(() => {
    if (want && want !== picked && cs.some((x) => x.id === want)) { setOrCase(want); setPicked(want); }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see above: runs only when the address's case changes
  }, [want]);
  useEffect(() => {
    if (route.a !== 'agents') return;
    const t = window.setTimeout(() => anchor(document.getElementById('orAgents')), 30);
    return () => window.clearTimeout(t);
  }, [route.a]);
  const replay = useReplay();

  const c = picked ? cs.find((x) => x.id === picked) : undefined;
  if (!c) {
    return (
      <>
        <div className="phead"><div><h1>Process orchestration</h1></div></div>
        <div className="empty"><b>No cases in your scope</b>Nothing to show yet.</div>
      </>
    );
  }
  const pick = (id: string) => { setOrCase(id); setPicked(id); };

  return (
    <div className="or">
      <div className="phead lrph">
        <h1>Process orchestration <span className="chip line">Behind the screen</span></h1>
        <div className="row">
          <label className="sr" htmlFor="or-case">Case</label>
          <select className="sel" id="or-case" value={c.id} onChange={(e) => pick(e.target.value)}>
            {cs.slice(0, 200).map((x) => <option key={x.id} value={x.id}>{x.id} · {x.product}</option>)}
          </select>
          <button className="btn" onClick={replay.fire}>Replay</button>
          {canGo('product/' + c.id) && <button className="btn" onClick={() => nav('/product/' + c.id)}>Open {c.id}</button>}
        </div>
      </div>
      <LiveBoard key={c.id} caseId={c.id} replaySignal={replay.n} />
      <RunDetails id={c.id} />
      <div className="callout info" style={{ marginBottom: 14 }}>
        <b>Circularity decides and instructs.</b> The physical work, orders and stock movements happen in your enterprise systems.
      </div>
      <section className="sect" id="orRun">
        <div className="sh"><h2>Run trace</h2><span className="note">Built from the audit trail and the agent call log</span></div>
        <div className="panel"><div className="pb"><RunTrace id={c.id} /></div></div>
      </section>
      <section className="sect" id="orAgents">
        <div className="sh"><h2>Agents and services</h2></div>
        <div className="panel">
          <div className="tw">
            <table className="t static">
              <thead><tr><th>Agent or service</th><th>Journey step</th><th>Scopes</th><th>Limits</th></tr></thead>
              <tbody>
                {agents().map((a) => (
                  <tr key={a.id}><td><b>{a.name}</b></td><td>{a.step}</td><td className="mono">{a.scopes.join(', ')}</td><td className="note">{a.limit}</td></tr>
                ))}
                <tr><td><b>Gate engine</b></td><td>2–3</td><td className="mono">policy:read</td><td className="note">Deterministic rules; an agent cannot waive a failed gate.</td></tr>
                <tr><td><b>Approval (human)</b></td><td>5</td><td className="mono">—</td><td className="note">There is no auto-approve path.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel" style={{ marginTop: 14 }}>
          <div className="pb">
            <h4 style={{ margin: '0 0 6px' }}>How these stages map to the ten-step journey</h4>
            <p className="note" style={{ margin: 0 }}>
              1 Supply evidence = Pull data + Data preparation · 2–3 = Evaluate gates + ML predictions · 4 = {poolsOn() ? 'Optimise pool' : 'Optimise plan'} and Recommendation · 5 = Present for approval · 6–8 = Hand off to enterprise system · 9–10 = Retrieve actual outcome and reconcile.
            </p>
            <div className="tw" style={{ marginTop: 10 }}>
              <table className="t static">
                <thead><tr><th>Decision</th><th>Instruction goes to</th><th>What that system does</th></tr></thead>
                <tbody>{handoffModel().map((h) => <tr key={h[0]}><td><b>{h[0]}</b></td><td>{h[1]}</td><td className="note">{h[2]}</td></tr>)}</tbody>
              </table>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

/** Run details: approval and execution, action calls and events, collapsed under the board (the demo's lrDetailsHTML). */
function RunDetails({ id }: { id: string }) {
  const c = orCaseById(id)!;
  const ents = caseJournal(id), calls = agentCalls(id).slice(0, 12), evs = caseEvents(id).slice(0, 14);
  return (
    <details className="lrdet" id="lrDetails">
      <summary>Run details <span className="note">approval and execution, action calls, events</span></summary>
      <div className="lrdg">
        <section className="panel">
          <div className="ph"><h3>Approval and execution</h3></div>
          <div className="pb">
            <dl className="afkv">
              <div><dt>Approval</dt><dd>{c.approval ? c.approval.ref + ' · ' + c.approval.by : c.stage === 'awaiting_approval' ? 'Waiting' + (c.submitted ? ' (submitted by ' + c.submitted.by + ')' : ' for submission') : '—'}</dd></div>
              <div><dt>Execution</dt><dd>{c.exec ? c.exec.steps.map((s) => s.label + ' ' + (s.state === 'done' ? '✓' : s.state === 'active' ? '…' : '·')).join(' · ') : 'Not started'}</dd></div>
              <div><dt>Outcome</dt><dd>{c.outcome ? money(c.outcome.net) + ' confirmed' : '—'}</dd></div>
            </dl>
          </div>
        </section>
        <section className="panel">
          <div className="ph"><h3>Action calls</h3><span className="note">Input and output per call</span></div>
          <div className="tw">
            <table className="t static tight">
              <thead><tr><th>Action</th><th>By</th><th>Input</th><th>Result</th></tr></thead>
              <tbody>
                {ents.slice(-10).reverse().map((e, i) => (
                  <tr key={'e' + i}>
                    <td className="mono">{e.id}</td><td>{e.by}{e.prep && <> {badge('Prepared by agent')}</>}</td>
                    <td className="mono note">{inputSummary(e.input)}</td>
                    <td className="note">{e.out ? Object.entries(e.out).map(([k, v]) => k + '=' + String(v)).join(', ') : 'ok'}</td>
                  </tr>
                ))}
                {calls.map((k, i) => (
                  <tr key={'k' + i}><td className="mono">{k.action}</td><td>{k.run} {badge(k.badge)}</td><td className="mono note">{k.input}</td><td className="note">{k.msg}</td></tr>
                ))}
                {!calls.length && !ents.length && <tr><td colSpan={4} className="note">No calls recorded for this case yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
        <section className="panel">
          <div className="ph"><h3>Events for this run</h3><span className="note">Only this case</span></div>
          <div className="pb">
            <ol className="aftl">
              {evs.length ? evs.map((e) => (
                <li key={e.id}><span className="num note">{fmtDate(e.ts)}</span><b className="mono">{e.type}</b><span className="note">{e.note || e.ack || ''}</span></li>
              )) : <li className="note">No events yet.</li>}
            </ol>
          </div>
        </section>
      </div>
    </details>
  );
}

const Red = ({ f }: { f: string }) => <span className="orred" title={'Redacted field: ' + f}>•••</span>;

/** One trace per run: a span per stage, per recorded action and per agent call (the agent-first orTraceHTML). */
function RunTrace({ id }: { id: string }) {
  const run = runModel(id).run, tid = traceId(id), ents = caseJournal(id), calls = agentCalls(id), RS = runStates();
  return (
    <>
      <p className="note" style={{ margin: '0 0 8px' }}>
        One trace per run ({run.id}), one span per stage, per recorded action and per agent call, shaped like the OpenTelemetry GenAI conventions (<span className="mono">invoke_agent</span>,{' '}
        <span className="mono">execute_tool</span>). Built from the journal and the agent runs; sensitive values are redacted.
      </p>
      <div className="tw">
        <table className="t static tight" id="orTrace">
          <thead><tr><th>Span</th><th>Kind</th><th>Performer · preparer</th><th>Parameters</th><th>Time (UTC)</th><th>Status</th></tr></thead>
          <tbody>
            {run.stages.map((s, i) => (
              <tr key={'s' + i}>
                <td className="mono">{tid}/{String(i + 1).padStart(2, '0')}</td><td>stage · {s.t}</td><td>{s.by || stageAgent(s.n)}</td>
                <td className="mono">case_id={id}</td><td className="num">{s.at ? orT(new Date(s.at)) : '—'}</td>
                <td><span className={'chip ' + RS[s.state][1]}>{RS[s.state][0]}</span></td>
              </tr>
            ))}
            {ents.map((e, j) => (
              <tr key={'a' + j}>
                <td className="mono">{tid}/a{j + 1}</td><td>execute_tool · {e.id}</td><td>{e.by}{e.prep ? ' · ' + e.prep : ''}</td>
                <td className="mono">case_id={id}{e.run ? ', run=' + e.run : ''}, tenant=<Red f="tenant" /></td>
                <td className="num">{orT(new Date(e.at))}</td><td><span className="chip ok">ok</span></td>
              </tr>
            ))}
            {calls.map((k, j) => (
              <tr key={'g' + j}>
                <td className="mono">{tid}/g{j + 1}</td><td>invoke_agent → execute_tool · {k.action}</td><td>{k.run}</td>
                <td className="mono">{k.input.replace(/tenant=[^,]+/, 'tenant=•••')}</td><td className="num">{k.ms} ms</td>
                <td><span className={'chip ' + (k.ok ? 'ok' : 'bad')}>{k.ok ? 'ok' : k.code || 'error'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
