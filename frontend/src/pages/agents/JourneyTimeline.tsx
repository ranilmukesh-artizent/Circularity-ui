import { useEffect, useState } from 'react';
import type { JourneyStage } from '../../api/agents';
import { can } from '../../api/session';
import { Markdown } from '../../components/Markdown';
import { blocked, controls, currentIndex, replayFrames, STATUS_CHIP, stageTitle } from './journeyView';

const text = (v: unknown): string => (typeof v === 'string' ? v : v == null ? '' : String(v));
const REPLAY_MS = 900;

/** The selected stage's panel: purpose, agent, activity, evidence with provenance, calls with input and result, result,
 * validation, state change, next step and the model's reading. A stage with no record shows "Not reached". */
function Panel({ s, caseId }: { s: JourneyStage; caseId: string | null }) {
  const reading = s.reading?.reading;
  return (
    <div className="panel" aria-label={`Stage ${s.n} panel`}>
      <p style={{ marginTop: 0 }}>
        <b>{stageTitle(s)}</b> <span className={'chip ' + STATUS_CHIP[s.status]}>{s.status}</span>
      </p>
      <dl className="note" style={{ margin: 0 }}>
        <dt>Purpose</dt><dd>{s.purpose}</dd>
        <dt>Agent</dt><dd className="mono">{s.agent}</dd>
        <dt>Activity</dt><dd>{s.activity}</dd>
        <dt>Evidence</dt>
        <dd>{s.evidence.length ? <ul>{s.evidence.map((e, i) => <li key={i}>{text(e.fact)} · {text(e.source) || 'source unknown'}{e.at ? ` · ${text(e.at).slice(0, 10)}` : ''}</li>)}</ul> : 'None.'}</dd>
        <dt>Calls</dt>
        <dd>
          {s.calls.length ? (
            <ul>{s.calls.map((c) => <li key={c.n}><span className="mono">{c.n}. {c.tool}</span> {JSON.stringify(c.input)} · {c.held != null ? `held as proposal ${c.held}` : c.ok ? 'ok' : 'refused'}</li>)}</ul>
          ) : 'No call.'}
        </dd>
        <dt>Result</dt><dd>{Object.keys(s.result).length ? <pre className="mono" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(s.result, null, 1)}</pre> : 'None yet.'}</dd>
        <dt>Validation</dt><dd>{s.validation.length ? <ul>{s.validation.map((v, i) => <li key={i}>{v}</li>)}</ul> : 'Nothing to report.'}</dd>
        <dt>State change</dt><dd>{s.state_change}</dd>
        <dt>Next step</dt><dd>{s.next_step}</dd>
        <dt>Reading</dt>
        <dd>
          {reading ? (
            <div aria-label={`Reading of stage ${s.n}`}>
              <div>Reasoned by {s.reading?.model ?? 'a model'}</div>
              <Markdown text={reading.summary} />
              {reading.findings.length > 0 && <ul>{reading.findings.map((f, i) => <li key={i}>{f.text} <span className="mono">({f.source})</span></li>)}</ul>}
              {reading.concerns.map((c, i) => <div key={i}>{c.hold && <span className="chip y">held</span>} {c.text}</div>)}
            </div>
          ) : 'Rules only.'}
        </dd>
      </dl>
      {blocked(s) && caseId && <p><a className="btn sm" href={'#/product/' + caseId}>Escalate on the case</a></p>}
    </div>
  );
}

/** The ten-stage journey of a case run (plan 9, P9-2.21): the timeline, the selected stage's panel and the controls. Next opens
 * the approval card for a person who may approve (else it shows who is awaited); Back and Replay change the view only. */
export function JourneyTimeline({ journey, caseId }: { journey: JourneyStage[]; caseId: string | null }) {
  const [selected, setSelected] = useState(() => currentIndex(journey));
  const [replayAt, setReplayAt] = useState<number | null>(null);
  const frames = replayFrames(journey);
  useEffect(() => {
    if (replayAt === null) return;
    if (replayAt >= frames.length) { setReplayAt(null); return; }
    setSelected(frames[replayAt]);
    const t = setTimeout(() => setReplayAt(replayAt + 1), REPLAY_MS);
    return () => clearTimeout(t);
  }, [replayAt]); // eslint-disable-line react-hooks/exhaustive-deps
  const replaying = replayAt !== null;
  const c = controls(journey, selected, can('approve'), replaying);
  const s = journey[Math.min(selected, journey.length - 1)];
  if (!s) return null;
  return (
    <div className="journey">
      <ol aria-label="Journey stages" style={{ listStyle: 'none', padding: 0, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {journey.map((j, i) => (
          <li key={j.n}>
            <button className={'btn sm' + (i === selected ? '' : ' ghost')} aria-current={i === selected ? 'step' : undefined} onClick={() => { setReplayAt(null); setSelected(i); }}>
              {stageTitle(j)} <span className={'chip ' + STATUS_CHIP[j.status]}>{j.status}</span>
            </button>
          </li>
        ))}
      </ol>
      <p>
        <button className="btn sm ghost" disabled={!c.back} onClick={() => setSelected(selected - 1)}>Back</button>{' '}
        {c.next.kind === 'approve' && caseId
          ? <a className="btn sm" href={'#/product/' + caseId}>{c.next.label}</a>
          : <button className="btn sm" disabled>{c.next.label}</button>}{' '}
        <button className="btn sm ghost" disabled={!c.replay} onClick={() => setReplayAt(0)}>Replay</button>
        {replaying && <button className="btn sm ghost" onClick={() => setReplayAt(null)}>Stop</button>}
        {c.next.note && <span className="note"> {c.next.note}</span>}
      </p>
      <Panel s={s} caseId={caseId} />
    </div>
  );
}
