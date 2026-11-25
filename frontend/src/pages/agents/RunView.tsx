import { Suspense } from 'react';
import { reasonText, runTrace, setAgentEnabled, spanMs, spanRows, stageLabel, type RunTrace, type TraceSpan } from '../../api/agents';
import { ApiError } from '../../api/client';
import { can } from '../../api/session';
import { useAction } from '../../hooks/useAction';

const STATUS_CHIP: Record<string, string> = { running: 'line', waiting: 'y', done: 'ok', failed: 'bad', stopped: 'warn', held: 'y', exception: 'bad', skipped: 'line' };
const AUTONOMY = { recommend: 'recommends only', limits: 'within limits', alone: 'acts alone' } as const;
const at = (iso: string) => iso.slice(0, 10) + ' ' + iso.slice(11, 19);
const num = (v: unknown): number | null => (typeof v === 'number' ? v : null);

/** What a span says in its own terms: the model and tokens of a `model` span, the action of a `tool` or `action` span. */
function spanNote(s: TraceSpan): string {
  const a = s.attrs;
  const parts: string[] = [];
  if (s.kind === 'model') {
    if (a['gen_ai.request.model']) parts.push(String(a['gen_ai.request.model']));
    const i = num(a['gen_ai.usage.input_tokens']), o = num(a['gen_ai.usage.output_tokens']);
    if (i !== null || o !== null) parts.push(`${i ?? 0} in · ${o ?? 0} out tokens`);
    if (a['di.model_route']) parts.push(`answered by ${String(a['di.model_route'])}`);
  } else if (a['di.action']) parts.push(String(a['di.action']));
  if (a['di.proposal_id'] != null) parts.push(`held as proposal ${String(a['di.proposal_id'])}`);
  if (a['di.error']) parts.push(`refused: ${String(a['di.error'])}`);
  if (a['error.message']) parts.push(String(a['error.message']));
  return parts.join(' · ');
}

function Body({ t }: { t: RunTrace }) {
  const act = useAction();
  const run = t.run;
  if (!run) return <p className="note">No agent has run on this case.</p>;
  const paused = t.pauses.length ? !t.pauses[t.pauses.length - 1].on : false;
  const pause = () => act.run(() => setAgentEnabled(run.agent, false));
  return (
    <div className="runview">
      <p style={{ marginTop: 0 }}>
        <b>{run.agentName}</b> · <span className="mono note">{run.playbook}</span> · <span className={'chip ' + (STATUS_CHIP[run.status] ?? 'line')}>{run.status}</span>
        {run.model && <span className="note"> · {run.model}</span>}
        {run.tokens && <span className="note"> · {run.tokens.input ?? 0} in · {run.tokens.output ?? 0} out tokens</span>}
      </p>
      {run.reason && <p className="note">{run.reason}</p>}
      {can('manageAccess') && (
        <p>
          <button className="btn sm" disabled={act.pending || paused || run.status === 'done'} onClick={pause}>Pause agent</button>
          {paused && <span className="note"> The agent is paused: its next step stops the run.</span>}
        </p>
      )}
      {t.pauses.length > 0 && (
        <ul className="note" aria-label="Pause history">{t.pauses.map((p) => <li key={p.at}>{p.on ? 'Started' : 'Paused'} by {p.by} · {at(p.at)}</li>)}</ul>
      )}

      <h4>Stages</h4>
      {t.stages.length ? (
        <div className="tw">
          <table className="t static tight">
            <thead><tr><th>Stage</th><th>Agent</th><th>Status</th><th className="r">Confidence</th><th>What it read</th></tr></thead>
            <tbody>
              {t.stages.map((s) => (
                <tr key={s.stage}>
                  <td><b>{stageLabel(s.stage)}</b><div className="note">{AUTONOMY[s.autonomy]}</div></td>
                  <td className="mono">{s.agent}</td>
                  <td>
                    <span className={'chip ' + (STATUS_CHIP[s.status] ?? 'line')}>{s.status}</span>
                    {s.reasons.length > 0 && <div className="note">{reasonText(s.reasons)}</div>}
                  </td>
                  <td className="r num">{s.confidence === null ? '—' : `${s.confidence.toFixed(2)} of ${s.threshold.toFixed(2)}`}</td>
                  <td className="note">{s.sources.length ? s.sources.map((x) => [x.source, x.age ?? x.fresh].filter(Boolean).join(' ')).join(' · ') : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="note">No stage record yet.</p>}

      <h4>Calls</h4>
      {t.calls.length ? t.calls.map((c) => (
        <div key={c.n} className={'ev ' + (c.ok ? '' : 'missing')}>
          <span className="ic">{c.ok ? '✓' : '✕'}</span>
          <div><b className="mono">{c.n}. {c.tool}</b>{c.held != null && <small>Held as proposal {c.held}</small>}</div>
          <em className="num">{c.at.slice(11, 19)}</em>
        </div>
      )) : <p className="note">No calls yet.</p>}

      <h4>Spans</h4>
      {t.spans.length ? (
        <div className="tw">
          <table className="t static tight">
            <thead><tr><th>Span</th><th>Detail</th><th className="r">ms</th></tr></thead>
            <tbody>
              {spanRows(t.spans).map(({ span, depth }) => (
                <tr key={span.span_id}>
                  <td style={{ paddingLeft: 8 + depth * 16 }}>
                    <span className={'chip ' + (span.status === 'ok' ? 'line' : 'bad')}>{span.kind}</span> <span className="mono">{span.name}</span>
                  </td>
                  <td className="note">{spanNote(span)}</td>
                  <td className="r num">{spanMs(span)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="note">No spans were recorded for this run.</p>}

      {t.proposals.length > 0 && (
        <>
          <h4>Proposals</h4>
          {t.proposals.map((p) => (
            <p key={p.id} className="note" style={{ margin: '0 0 4px' }}>
              <b>{p.action}</b> · proposal {p.id} · {p.status}{p.decided_by ? ` by ${p.decided_by}` : ''}{p.reasons.length ? ' · ' + reasonText(p.reasons) : ''}
            </p>
          ))}
        </>
      )}
      {t.journal.length > 0 && (
        <>
          <h4>Journal</h4>
          <ul className="note" style={{ margin: 0, paddingLeft: 16 }}>{t.journal.map((j) => <li key={j.seq}>{j.action} · {j.actor}{j.preparer ? ` for ${j.preparer}` : ''} · {at(j.at)}</li>)}</ul>
        </>
      )}
    </div>
  );
}

function Loaded({ runId, caseId }: { runId?: string; caseId?: string }) {
  let t: RunTrace;
  try {
    t = runTrace(runId ? { runId } : { caseId: caseId ?? '' });
  } catch (e) {
    if (e instanceof ApiError) return <p className="note">{e.message}</p>;
    throw e;
  }
  return <Body t={t} />;
}

/** One agent run (plan 9, P9-2.6): its stages with confidence against the threshold, calls and spans, proposals and the pause
 * switch with its history. The Agents page opens it for a run (`runId`); the case page's "Agent run" drawer for the case. */
export function RunView(props: { runId?: string; caseId?: string }) {
  return <Suspense fallback={<p className="note">Loading…</p>}><Loaded {...props} /></Suspense>;
}
