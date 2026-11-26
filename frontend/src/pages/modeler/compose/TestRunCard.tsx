import { useState } from 'react';
import { testRunComposition, type Composition, type StageStop, type TestRun } from '../../../api/compose';
import { useAction } from '../../../hooks/useAction';

const KIND_WORDS: Record<string, string> = {
  missing_field: 'missing field',
  held_record: 'held record',
  guardrail: 'guardrail',
  threshold: 'below the confidence threshold at',
  no_route: 'no route left at',
};

/** `missing_field:condition.grade` reads "missing field condition.grade". */
const reasonWords = (reason: string): string => {
  const at = reason.indexOf(':');
  const words = at < 0 ? undefined : KIND_WORDS[reason.slice(0, at)];
  return words ? `${words} ${reason.slice(at + 1)}` : reason;
};

const stageLabel = (stage: string): string => stage.charAt(0).toUpperCase() + stage.slice(1);

/**
 * "Test run" under the Adapter mapping step (plan 9, P9-8.19; story X-10 enabler; backend `compose.testRun`): the org's past items
 * put through the draft, with where cases stopped by stage and reason. Each count opens the item ids behind it. A test run only
 * reads: it never publishes or approves, and the counts are the server's (a model may only word the summary).
 */
export function TestRunCard({ c }: { c: Composition }) {
  const [run, setRun] = useState<TestRun | null>(null);
  const [shown, setShown] = useState<string | null>(null);
  const action = useAction();

  const start = async () => {
    const r = await action.run(() => testRunComposition(c.id));
    if (r.ok) {
      setRun(r.output);
      setShown(null);
    }
  };

  const stopped = (run?.stages ?? []).filter((s: StageStop) => s.stopped > 0);
  return (
    <div className="cmp-inline" aria-label="Test run">
      <h4>Test run</h4>
      <p className="note">Put the org's past items through this draft and see where cases stop. Nothing is saved, published or approved.</p>
      <div className="row">
        <button className="btn sm" disabled={action.pending} onClick={() => void start()}>{run ? 'Run again' : 'Run test'}</button>
        {action.pending && <span className="note">Running…</span>}
      </div>
      {run && (
        <>
          <p role="status">{run.text}</p>
          {stopped.length === 0 && <p className="note">Every item reached a decision.</p>}
          {stopped.length > 0 && (
            <table className="t static" aria-label="Where cases stopped">
              <thead><tr><th>Stage</th><th>Reached</th><th>Stopped</th><th>Why</th></tr></thead>
              <tbody>
                {stopped.map((s) => (
                  <tr key={s.stage}>
                    <td><b>{stageLabel(s.stage)}</b></td>
                    <td>{s.reached}</td>
                    <td>{s.stopped}</td>
                    <td>
                      {s.reasons.map((r) => {
                        const key = `${s.stage}|${r.reason}`;
                        return (
                          <div key={key}>
                            <button className="btn sm" aria-expanded={shown === key} onClick={() => setShown(shown === key ? null : key)}>
                              {reasonWords(r.reason)}: {r.count}
                            </button>
                            {shown === key && <span className="note"> Example items: {r.examples.join(', ')}</span>}
                          </div>
                        );
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="note">{run.by_model ? 'Summary worded by the model; the counts are computed.' : 'Summary composed from the counts.'}</p>
        </>
      )}
    </div>
  );
}
